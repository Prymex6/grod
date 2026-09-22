"""The endpoints `docker push` and `docker pull` talk to.

They sit at the root under /v2, the way the container tools expect, and an image
address looks like grod.example/<login>/<project>. The rights of the project
decide everything: whoever may read it may pull, whoever may push code may push
an image.
"""

import base64
import binascii
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request, Response, status
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from grod.accounts.models import User
from grod.artifacts.registry import service, storage
from grod.db import get_db_session
from grod.quotas import service as quotas
from grod.repositories import service as projects
from grod.repositories import tokens
from grod.repositories.models import Project

router = APIRouter(prefix="/v2", tags=["registry"])

DbSession = Annotated[AsyncSession, Depends(get_db_session)]

BASIC_PREFIX = "Basic "
CREDENTIAL_PARTS = 2
API_VERSION = {"Docker-Distribution-Api-Version": "registry/2.0"}
AUTHENTICATE = {**API_VERSION, "WWW-Authenticate": 'Basic realm="Grod"'}
DEFAULT_MANIFEST_TYPE = "application/vnd.docker.distribution.manifest.v2+json"
CATALOG_LIMIT = 100


def _error(status_code: int, code: str, message: str, *, headers: dict[str, str]) -> JSONResponse:
    """The shape of refusal the container tools know how to read."""
    return JSONResponse(
        {"errors": [{"code": code, "message": message, "detail": None}]},
        status_code=status_code,
        headers=headers,
    )


def _unauthorized() -> JSONResponse:
    return _error(
        status.HTTP_401_UNAUTHORIZED,
        "UNAUTHORIZED",
        "Sign in with an access token",
        headers=AUTHENTICATE,
    )


def _unknown_name() -> JSONResponse:
    # A project nobody may read must look exactly like a missing one.
    return _error(
        status.HTTP_404_NOT_FOUND, "NAME_UNKNOWN", "No such repository", headers=API_VERSION
    )


async def _holder(db: AsyncSession, authorization: str | None) -> tokens.TokenHolder | None:
    """Read the account out of a Basic header whose password is a token."""
    if authorization is None or not authorization.startswith(BASIC_PREFIX):
        return None
    try:
        decoded = base64.b64decode(authorization.removeprefix(BASIC_PREFIX)).decode()
    except binascii.Error, UnicodeDecodeError:
        return None
    parts = decoded.split(":", 1)
    if len(parts) != CREDENTIAL_PARTS:
        return None
    return await tokens.authenticate(db, parts[1])


async def _caller(db: AsyncSession, authorization: str | None, *, writing: bool) -> User | None:
    """Who is pushing or pulling, if their token says they may."""
    holder = await _holder(db, authorization)
    if holder is None:
        return None
    needed = tokens.SCOPE_WRITE if writing else tokens.SCOPE_READ
    return holder.user if needed in holder.scopes else None


async def _project(
    db: AsyncSession, owner: str, slug: str, authorization: str | None, *, writing: bool
) -> Project | JSONResponse:
    """Find the project behind an image name, or say why it cannot be used."""
    user = await _caller(db, authorization, writing=writing)
    found = await projects.find(db, owner_login=owner, slug=slug)
    if found is None:
        return _unauthorized() if user is None else _unknown_name()

    access = await projects.access_of(db, project=found.project, user=user)
    if not access.read or (writing and not access.write):
        return _unauthorized() if user is None else _unknown_name()
    return found.project


@router.get("/")
async def read_version(
    db: DbSession, authorization: Annotated[str | None, Header()] = None
) -> Response:
    """Say that this is a registry, and check the credentials if any came.

    A caller who sends nothing is let through, so pulling a public image needs
    no account; a caller who sends a token has it weighed, so `docker login`
    finds out at once whether it is any good.
    """
    if authorization is None:
        return JSONResponse({}, headers=API_VERSION)
    if await _holder(db, authorization) is None:
        return _unauthorized()
    return JSONResponse({}, headers=API_VERSION)


@router.get("/_catalog")
async def read_catalog(
    db: DbSession, authorization: Annotated[str | None, Header()] = None
) -> Response:
    """Return the repositories this caller may see."""
    user = await _caller(db, authorization, writing=False)
    found = await service.list_repositories(db, user=user, limit=CATALOG_LIMIT)
    return JSONResponse({"repositories": found}, headers=API_VERSION)


@router.post("/{owner}/{slug}/blobs/uploads/")
async def start_upload(
    owner: str,
    slug: str,
    request: Request,
    db: DbSession,
    digest: str | None = None,
    authorization: Annotated[str | None, Header()] = None,
) -> Response:
    """Open an upload, or take the whole blob in one go when it comes along."""
    project = await _project(db, owner, slug, authorization, writing=True)
    if isinstance(project, JSONResponse):
        return project

    announced = int(request.headers.get("content-length", 0) or 0)
    try:
        await quotas.ensure_room_for_bytes(db, owner_id=project.owner_id, adding=announced)
    except quotas.OverQuotaError:
        return _error(
            status.HTTP_403_FORBIDDEN,
            "DENIED",
            "This account already holds as much as it may",
            headers=API_VERSION,
        )

    upload_id = storage.start_upload()
    name = f"{owner}/{slug}"
    if digest is None:
        await storage.append(upload_id, request.stream())
        return Response(
            status_code=status.HTTP_202_ACCEPTED,
            headers={
                **API_VERSION,
                "Location": f"/v2/{name}/blobs/uploads/{upload_id}",
                "Docker-Upload-Uuid": str(upload_id),
                "Range": "0-0",
            },
        )

    await storage.append(upload_id, request.stream())
    return await _finish(db, project=project, name=name, upload_id=upload_id, digest=digest)


@router.patch("/{owner}/{slug}/blobs/uploads/{upload_id}")
async def continue_upload(
    owner: str,
    slug: str,
    upload_id: UUID,
    request: Request,
    db: DbSession,
    authorization: Annotated[str | None, Header()] = None,
) -> Response:
    """Add another piece to an upload already under way."""
    project = await _project(db, owner, slug, authorization, writing=True)
    if isinstance(project, JSONResponse):
        return project

    try:
        await quotas.ensure_room_for_bytes(
            db, owner_id=project.owner_id, adding=int(request.headers.get("content-length", 0) or 0)
        )
    except quotas.OverQuotaError:
        return _error(
            status.HTTP_403_FORBIDDEN,
            "DENIED",
            "This account already holds as much as it may",
            headers=API_VERSION,
        )

    try:
        held = await storage.append(upload_id, request.stream())
    except storage.NoSuchUploadError:
        return _error(
            status.HTTP_404_NOT_FOUND, "BLOB_UPLOAD_UNKNOWN", "No such upload", headers=API_VERSION
        )
    return Response(
        status_code=status.HTTP_202_ACCEPTED,
        headers={
            **API_VERSION,
            "Location": f"/v2/{owner}/{slug}/blobs/uploads/{upload_id}",
            "Docker-Upload-Uuid": str(upload_id),
            "Range": f"0-{max(held - 1, 0)}",
        },
    )


@router.put("/{owner}/{slug}/blobs/uploads/{upload_id}")
async def complete_upload(
    owner: str,
    slug: str,
    upload_id: UUID,
    request: Request,
    db: DbSession,
    digest: str = "",
    authorization: Annotated[str | None, Header()] = None,
) -> Response:
    """Take the last piece, weigh the blob and keep it."""
    project = await _project(db, owner, slug, authorization, writing=True)
    if isinstance(project, JSONResponse):
        return project

    try:
        await storage.append(upload_id, request.stream())
    except storage.NoSuchUploadError:
        return _error(
            status.HTTP_404_NOT_FOUND, "BLOB_UPLOAD_UNKNOWN", "No such upload", headers=API_VERSION
        )
    return await _finish(
        db, project=project, name=f"{owner}/{slug}", upload_id=upload_id, digest=digest
    )


async def _finish(
    db: AsyncSession, *, project: Project, name: str, upload_id: UUID, digest: str
) -> Response:
    """Close an upload: the bytes have to be what the caller promised."""
    try:
        size = await storage.finish(upload_id, project_id=project.id, digest=digest)
    except storage.InvalidDigestError:
        return _error(
            status.HTTP_400_BAD_REQUEST,
            "DIGEST_INVALID",
            "The blob does not match its digest",
            headers=API_VERSION,
        )
    except storage.NoSuchUploadError:
        return _error(
            status.HTTP_404_NOT_FOUND, "BLOB_UPLOAD_UNKNOWN", "No such upload", headers=API_VERSION
        )

    await service.keep_blob(db, project=project, digest=digest, size=size)
    return Response(
        status_code=status.HTTP_201_CREATED,
        headers={
            **API_VERSION,
            "Location": f"/v2/{name}/blobs/{digest}",
            "Docker-Content-Digest": digest,
        },
    )


@router.delete("/{owner}/{slug}/blobs/uploads/{upload_id}")
async def cancel_upload(
    owner: str,
    slug: str,
    upload_id: UUID,
    db: DbSession,
    authorization: Annotated[str | None, Header()] = None,
) -> Response:
    """Give up on an upload and throw away what it collected."""
    project = await _project(db, owner, slug, authorization, writing=True)
    if isinstance(project, JSONResponse):
        return project
    await storage.cancel(upload_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT, headers=API_VERSION)


@router.head("/{owner}/{slug}/blobs/{digest}")
async def check_blob(
    owner: str,
    slug: str,
    digest: str,
    db: DbSession,
    authorization: Annotated[str | None, Header()] = None,
) -> Response:
    """Say whether a blob is already here, so a push can skip it."""
    project = await _project(db, owner, slug, authorization, writing=False)
    if isinstance(project, JSONResponse):
        return project

    blob = await service.find_blob(db, project=project, digest=digest)
    if blob is None:
        return _error(
            status.HTTP_404_NOT_FOUND, "BLOB_UNKNOWN", "No such blob", headers=API_VERSION
        )
    return Response(
        headers={
            **API_VERSION,
            "Content-Length": str(blob.size),
            "Docker-Content-Digest": digest,
        }
    )


@router.get("/{owner}/{slug}/blobs/{digest}")
async def read_blob(
    owner: str,
    slug: str,
    digest: str,
    db: DbSession,
    authorization: Annotated[str | None, Header()] = None,
) -> Response:
    """Hand over one piece of an image."""
    project = await _project(db, owner, slug, authorization, writing=False)
    if isinstance(project, JSONResponse):
        return project

    blob = await service.find_blob(db, project=project, digest=digest)
    if blob is None:
        return _error(
            status.HTTP_404_NOT_FOUND, "BLOB_UNKNOWN", "No such blob", headers=API_VERSION
        )
    path = storage.blob_path(project.id, digest)
    if not path.is_file():
        return _error(
            status.HTTP_404_NOT_FOUND, "BLOB_UNKNOWN", "No such blob", headers=API_VERSION
        )
    return FileResponse(
        path,
        media_type="application/octet-stream",
        headers={**API_VERSION, "Docker-Content-Digest": digest},
    )


@router.get("/{owner}/{slug}/tags/list")
async def read_tags(
    owner: str,
    slug: str,
    db: DbSession,
    authorization: Annotated[str | None, Header()] = None,
) -> Response:
    """Return every name given to an image of this repository."""
    project = await _project(db, owner, slug, authorization, writing=False)
    if isinstance(project, JSONResponse):
        return project
    found = await service.list_tags(db, project=project)
    return JSONResponse({"name": f"{owner}/{slug}", "tags": found}, headers=API_VERSION)


@router.put("/{owner}/{slug}/manifests/{reference}")
async def write_manifest(
    owner: str,
    slug: str,
    reference: str,
    request: Request,
    db: DbSession,
    authorization: Annotated[str | None, Header()] = None,
) -> Response:
    """Keep the document that ties an image together, and tag it."""
    project = await _project(db, owner, slug, authorization, writing=True)
    if isinstance(project, JSONResponse):
        return project

    body = await request.body()
    content_type = request.headers.get("content-type", DEFAULT_MANIFEST_TYPE)
    try:
        manifest = await service.write_manifest(
            db, project=project, reference=reference, body=body, content_type=content_type
        )
    except service.MissingBlobError as error:
        return _error(
            status.HTTP_400_BAD_REQUEST,
            "MANIFEST_BLOB_UNKNOWN",
            f"The image needs {error.digest}, which was never pushed",
            headers=API_VERSION,
        )
    except service.InvalidManifestError:
        return _error(
            status.HTTP_400_BAD_REQUEST,
            "MANIFEST_INVALID",
            "The manifest is not a JSON object",
            headers=API_VERSION,
        )
    except service.InvalidTagError:
        return _error(
            status.HTTP_400_BAD_REQUEST, "TAG_INVALID", "Invalid tag", headers=API_VERSION
        )

    return Response(
        status_code=status.HTTP_201_CREATED,
        headers={
            **API_VERSION,
            "Location": f"/v2/{owner}/{slug}/manifests/{manifest.digest}",
            "Docker-Content-Digest": manifest.digest,
        },
    )


def _manifest_headers(manifest: Any) -> dict[str, str]:  # noqa: ANN401  (one mapped row)
    return {
        **API_VERSION,
        "Docker-Content-Digest": manifest.digest,
        "Content-Length": str(manifest.size),
    }


@router.get("/{owner}/{slug}/manifests/{reference}")
async def read_manifest(
    owner: str,
    slug: str,
    reference: str,
    db: DbSession,
    authorization: Annotated[str | None, Header()] = None,
) -> Response:
    """Hand over the document that says what an image is made of."""
    project = await _project(db, owner, slug, authorization, writing=False)
    if isinstance(project, JSONResponse):
        return project

    manifest = await service.find_manifest(db, project=project, reference=reference)
    if manifest is None:
        return _error(
            status.HTTP_404_NOT_FOUND, "MANIFEST_UNKNOWN", "No such image", headers=API_VERSION
        )
    return Response(
        content=manifest.body,
        media_type=manifest.content_type,
        headers=_manifest_headers(manifest),
    )


@router.head("/{owner}/{slug}/manifests/{reference}")
async def check_manifest(
    owner: str,
    slug: str,
    reference: str,
    db: DbSession,
    authorization: Annotated[str | None, Header()] = None,
) -> Response:
    """Say whether an image is here, without sending it."""
    project = await _project(db, owner, slug, authorization, writing=False)
    if isinstance(project, JSONResponse):
        return project

    manifest = await service.find_manifest(db, project=project, reference=reference)
    if manifest is None:
        return _error(
            status.HTTP_404_NOT_FOUND, "MANIFEST_UNKNOWN", "No such image", headers=API_VERSION
        )
    return Response(media_type=manifest.content_type, headers=_manifest_headers(manifest))


@router.delete("/{owner}/{slug}/manifests/{reference}")
async def remove_manifest(
    owner: str,
    slug: str,
    reference: str,
    db: DbSession,
    authorization: Annotated[str | None, Header()] = None,
) -> Response:
    """Take an image down, by digest, or take one name off it."""
    project = await _project(db, owner, slug, authorization, writing=True)
    if isinstance(project, JSONResponse):
        return project

    removed = (
        await service.delete_manifest(db, project=project, digest=reference)
        if service.is_digest(reference)
        else await service.delete_tag(db, project=project, name=reference)
    )
    if not removed:
        return _error(
            status.HTTP_404_NOT_FOUND, "MANIFEST_UNKNOWN", "No such image", headers=API_VERSION
        )
    return Response(status_code=status.HTTP_202_ACCEPTED, headers=API_VERSION)

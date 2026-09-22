"""Endpoints for the secrets of a project and the files it publishes."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession

from grod.accounts.dependencies import CurrentUser, OptionalUser
from grod.accounts.schemas import ApiModel
from grod.artifacts import service
from grod.artifacts.models import (
    FILENAME_MAX_LENGTH,
    NAME_MAX_LENGTH,
    NAME_PATTERN,
    VALUE_MAX_LENGTH,
    VERSION_MAX_LENGTH,
    Package,
)
from grod.artifacts.registry import service as registry
from grod.collaboration.router import NOT_ALLOWED_DETAIL, readable
from grod.config import Settings, get_settings
from grod.db import get_db_session
from grod.quotas import service as quotas
from grod.quotas.errors import refusal

router = APIRouter(prefix="/projects/{owner}/{slug}", tags=["artifacts"])

DbSession = Annotated[AsyncSession, Depends(get_db_session)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]

NOTHING_KEPT_DETAIL = "The project keeps nothing under that name"
PACKAGE_NOT_FOUND = "No such package"
IMAGE_NOT_FOUND = "No such image"


class SecretWrite(ApiModel):
    """A secret to keep. The value never comes back out of the API."""

    name: str = Field(pattern=NAME_PATTERN, min_length=1, max_length=NAME_MAX_LENGTH)
    value: str = Field(min_length=1, max_length=VALUE_MAX_LENGTH)
    masked: bool = True
    protected: bool = False


class SecretView(ApiModel):
    """A secret as the settings page shows it: everything but the value."""

    name: str
    masked: bool
    protected: bool
    created_at: datetime


class PackageView(ApiModel):
    """One published file."""

    id: UUID
    name: str
    version: str
    filename: str
    size: int
    digest: str
    created_at: datetime
    url: str


class ImageView(ApiModel):
    """One tagged container image of a project."""

    tag: str
    digest: str
    size: int
    created_at: datetime
    # What to write after `docker pull`.
    reference: str


class RegistryView(ApiModel):
    """What the registry of one project holds."""

    images: list[ImageView]
    blobs: int
    bytes: int


def _secret_view(secret: service.Secret) -> SecretView:
    return SecretView(
        name=secret.name,
        masked=secret.masked,
        protected=secret.protected,
        created_at=secret.created_at,
    )


def _package_view(package: Package, owner: str, slug: str) -> PackageView:
    address = (
        f"/api/v1/projects/{owner}/{slug}/packages/"
        f"{package.name}/{package.version}/{package.filename}"
    )
    return PackageView(
        id=package.id,
        name=package.name,
        version=package.version,
        filename=package.filename,
        size=package.size,
        digest=package.digest,
        created_at=package.created_at,
        url=address,
    )


@router.get("/secrets")
async def list_secrets(owner: str, slug: str, db: DbSession, user: CurrentUser) -> list[SecretView]:
    """Return the names of the secrets a project keeps, never their values."""
    project, access = await readable(db, owner, slug, user)
    if not access.manage:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=NOT_ALLOWED_DETAIL)
    return [_secret_view(secret) for secret in await service.list_secrets(db, project=project)]


@router.put("/secrets", status_code=status.HTTP_201_CREATED)
async def set_secret(
    owner: str, slug: str, body: SecretWrite, db: DbSession, user: CurrentUser
) -> SecretView:
    """Keep a secret, or write a new value over the one that is there."""
    project, access = await readable(db, owner, slug, user)
    if not access.manage:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=NOT_ALLOWED_DETAIL)

    try:
        secret = await service.set_secret(
            db,
            project=project,
            name=body.name,
            value=body.value,
            masked=body.masked,
            protected=body.protected,
        )
    except service.InvalidNameError:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="A secret is named like a shell variable"
        ) from None
    return _secret_view(secret)


@router.delete("/secrets/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_secret(owner: str, slug: str, name: str, db: DbSession, user: CurrentUser) -> None:
    """Forget a secret."""
    project, access = await readable(db, owner, slug, user)
    if not access.manage:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=NOT_ALLOWED_DETAIL)
    if not await service.delete_secret(db, project=project, name=name):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NOTHING_KEPT_DETAIL)


@router.get("/packages")
async def list_packages(
    owner: str, slug: str, db: DbSession, user: OptionalUser
) -> list[PackageView]:
    """Return what a project published."""
    project, _ = await readable(db, owner, slug, user)
    found = await service.list_packages(db, project=project)
    return [_package_view(package, owner, slug) for package in found]


@router.put("/packages/{name}/{version}/{filename}", status_code=status.HTTP_201_CREATED)
async def publish_package(
    owner: str,
    slug: str,
    name: Annotated[str, Field(max_length=NAME_MAX_LENGTH)],
    version: Annotated[str, Field(max_length=VERSION_MAX_LENGTH)],
    filename: Annotated[str, Field(max_length=FILENAME_MAX_LENGTH)],
    request: Request,
    db: DbSession,
    user: CurrentUser,
) -> PackageView:
    """Publish a file. The body of the request is the file itself."""
    project, access = await readable(db, owner, slug, user)
    if not access.write:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=NOT_ALLOWED_DETAIL)
    if "/" in filename or filename in {"", ".", ".."}:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid file name")

    try:
        announced = int(request.headers.get("content-length", 0))
        await quotas.ensure_room_for_bytes(db, owner_id=project.owner_id, adding=announced)
    except quotas.OverQuotaError as error:
        raise refusal(error) from None
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid length") from None

    try:
        package = await service.publish_package(
            db,
            project=project,
            name=name,
            version=version,
            filename=filename,
            content=request.stream(),
            uploaded_by=user,
        )
    except service.PackageTooLargeError:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="The file is too large"
        ) from None
    return _package_view(package, owner, slug)


@router.get("/packages/{name}/{version}/{filename}")
async def download_package(
    owner: str,
    slug: str,
    name: str,
    version: str,
    filename: str,
    db: DbSession,
    user: OptionalUser,
) -> FileResponse:
    """Download a published file."""
    project, _ = await readable(db, owner, slug, user)
    found = await service.find_package(
        db, project=project, name=name, version=version, filename=filename
    )
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=PACKAGE_NOT_FOUND)
    return FileResponse(
        found.path, filename=found.package.filename, media_type="application/octet-stream"
    )


@router.delete("/packages/{package_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_package(
    owner: str, slug: str, package_id: UUID, db: DbSession, user: CurrentUser
) -> None:
    """Remove a published file."""
    project, access = await readable(db, owner, slug, user)
    if not access.manage:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=NOT_ALLOWED_DETAIL)

    package = await db.get(Package, package_id)
    if package is None or package.project_id != project.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=PACKAGE_NOT_FOUND)
    await service.delete_package(db, package=package)


def _registry_host(settings: Settings) -> str:
    """The host a `docker pull` is addressed to, without the scheme."""
    return str(settings.public_url).rstrip("/").split("://", 1)[-1]


@router.get("/images")
async def read_registry(
    owner: str, slug: str, db: DbSession, user: OptionalUser, settings: SettingsDependency
) -> RegistryView:
    """Return the container images a project keeps, and what they take up."""
    project, _ = await readable(db, owner, slug, user)
    found = await registry.list_images(db, project=project)
    held = await registry.usage(db, project=project)
    host = _registry_host(settings)
    return RegistryView(
        images=[
            ImageView(
                tag=image.tag,
                digest=image.digest,
                size=image.size,
                created_at=image.created_at,
                reference=f"{host}/{owner}/{slug}:{image.tag}",
            )
            for image in found
        ],
        blobs=held.blobs,
        bytes=held.bytes,
    )


@router.delete("/images/{tag}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_image(owner: str, slug: str, tag: str, db: DbSession, user: CurrentUser) -> None:
    """Take one tag off an image of this project."""
    project, access = await readable(db, owner, slug, user)
    if not access.manage:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=NOT_ALLOWED_DETAIL)
    if not await registry.delete_tag(db, project=project, name=tag):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=IMAGE_NOT_FOUND)

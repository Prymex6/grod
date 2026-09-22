"""Keeping container images: blobs, the manifests over them and the tags."""

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from grod.accounts.models import User
from grod.artifacts.registry.models import (
    DIGEST_PATTERN,
    TAG_PATTERN,
    ContainerBlob,
    ContainerManifest,
    ContainerTag,
)
from grod.community.models import Group
from grod.repositories import service as projects
from grod.repositories.models import Project

DIGEST_RULE = re.compile(DIGEST_PATTERN)
TAG_RULE = re.compile(TAG_PATTERN)


class MissingBlobError(Exception):
    """The manifest points at something that was never pushed."""

    def __init__(self, digest: str) -> None:
        super().__init__(digest)
        self.digest = digest


class InvalidManifestError(Exception):
    """The manifest is not JSON, or does not say what it is."""


class InvalidTagError(Exception):
    """A tag is named like a tag, not like anything else."""


@dataclass(frozen=True)
class Usage:
    """How much of the registry one project takes."""

    tags: int
    manifests: int
    blobs: int
    bytes: int


@dataclass(frozen=True)
class ImageView:
    """One tag together with the manifest it names."""

    tag: str
    digest: str
    size: int
    created_at: Any


def digest_of(body: bytes) -> str:
    """The name a document is known by: the sha256 of its exact bytes."""
    return f"sha256:{hashlib.sha256(body).hexdigest()}"


def is_digest(reference: str) -> bool:
    """Whether a reference names a manifest outright instead of tagging it."""
    return DIGEST_RULE.match(reference) is not None


async def find_blob(
    session: AsyncSession, *, project: Project, digest: str
) -> ContainerBlob | None:
    """Return one blob of a project, if it is there."""
    result = await session.execute(
        select(ContainerBlob).where(
            ContainerBlob.project_id == project.id, ContainerBlob.digest == digest
        )
    )
    return result.scalar_one_or_none()


async def keep_blob(
    session: AsyncSession, *, project: Project, digest: str, size: int
) -> ContainerBlob:
    """Write down a blob that is already on disk, or leave the one that is."""
    found = await find_blob(session, project=project, digest=digest)
    if found is not None:
        return found

    blob = ContainerBlob(project_id=project.id, digest=digest, size=size)
    session.add(blob)
    try:
        await session.commit()
    except IntegrityError:
        # Two pushes of the same layer crossed; the first one stands.
        await session.rollback()
        existing = await find_blob(session, project=project, digest=digest)
        if existing is None:
            raise
        return existing
    return blob


def _referenced(document: dict[str, Any]) -> list[str]:
    """The blobs a manifest needs, by digest.

    An index points at other manifests rather than at blobs, so it needs
    nothing of its own and comes back empty.
    """
    if "manifests" in document:
        return []

    wanted: list[str] = []
    config = document.get("config")
    if isinstance(config, dict):
        digest = config.get("digest")
        if isinstance(digest, str):
            wanted.append(digest)
    layers = document.get("layers")
    if isinstance(layers, list):
        wanted += [
            layer["digest"]
            for layer in layers
            if isinstance(layer, dict) and isinstance(layer.get("digest"), str)
        ]
    return wanted


async def write_manifest(
    session: AsyncSession,
    *,
    project: Project,
    reference: str,
    body: bytes,
    content_type: str,
) -> ContainerManifest:
    """Keep a manifest, and point the tag at it when the reference is one.

    Everything the manifest names has to be there already; a registry that
    accepts a manifest over blobs it does not hold hands out broken images.
    """
    try:
        document = json.loads(body)
    except json.JSONDecodeError as error:
        raise InvalidManifestError("not JSON") from error
    if not isinstance(document, dict):
        raise InvalidManifestError("not an object")

    for digest in _referenced(document):
        if await find_blob(session, project=project, digest=digest) is None:
            raise MissingBlobError(digest)

    digest = digest_of(body)
    manifest = await find_manifest_by_digest(session, project=project, digest=digest)
    if manifest is None:
        manifest = ContainerManifest(
            project_id=project.id,
            digest=digest,
            content_type=content_type,
            body=body.decode("utf-8", errors="replace"),
            size=len(body),
        )
        session.add(manifest)
        await session.commit()

    if not is_digest(reference):
        await _tag(session, project=project, name=reference, manifest=manifest)
    return manifest


async def _tag(
    session: AsyncSession, *, project: Project, name: str, manifest: ContainerManifest
) -> ContainerTag:
    """Give a manifest a name, moving the name off whatever held it."""
    if TAG_RULE.match(name) is None:
        raise InvalidTagError(name)

    result = await session.execute(
        select(ContainerTag).where(ContainerTag.project_id == project.id, ContainerTag.name == name)
    )
    found = result.scalar_one_or_none()
    if found is None:
        found = ContainerTag(project_id=project.id, name=name, manifest_id=manifest.id)
        session.add(found)
    else:
        found.manifest_id = manifest.id
    await session.commit()
    return found


async def find_manifest_by_digest(
    session: AsyncSession, *, project: Project, digest: str
) -> ContainerManifest | None:
    """Return one manifest of a project by its own name."""
    result = await session.execute(
        select(ContainerManifest).where(
            ContainerManifest.project_id == project.id, ContainerManifest.digest == digest
        )
    )
    return result.scalar_one_or_none()


async def find_manifest(
    session: AsyncSession, *, project: Project, reference: str
) -> ContainerManifest | None:
    """Return the manifest a reference means: a digest, or a tag."""
    if is_digest(reference):
        return await find_manifest_by_digest(session, project=project, digest=reference)

    result = await session.execute(
        select(ContainerManifest)
        .join(ContainerTag, ContainerTag.manifest_id == ContainerManifest.id)
        .where(ContainerTag.project_id == project.id, ContainerTag.name == reference)
    )
    return result.scalar_one_or_none()


async def list_tags(session: AsyncSession, *, project: Project) -> list[str]:
    """Return the tags of a project, in order."""
    result = await session.execute(
        select(ContainerTag.name)
        .where(ContainerTag.project_id == project.id)
        .order_by(ContainerTag.name)
    )
    return list(result.scalars())


async def list_images(session: AsyncSession, *, project: Project) -> list[ImageView]:
    """Return the tags together with what each one weighs.

    The size is the manifest plus everything it points at, which is what a
    `docker pull` really has to fetch.
    """
    result = await session.execute(
        select(ContainerTag, ContainerManifest)
        .join(ContainerManifest, ContainerTag.manifest_id == ContainerManifest.id)
        .where(ContainerTag.project_id == project.id)
        .order_by(ContainerTag.name)
    )
    images: list[ImageView] = []
    for tag, manifest in result:
        size = manifest.size + await _weight(session, project=project, manifest=manifest)
        images.append(
            ImageView(
                tag=tag.name, digest=manifest.digest, size=size, created_at=manifest.created_at
            )
        )
    return images


def _children(document: dict[str, Any]) -> list[str]:
    """The manifests an index points at, by digest."""
    listed = document.get("manifests")
    if not isinstance(listed, list):
        return []
    return [
        child["digest"]
        for child in listed
        if isinstance(child, dict) and isinstance(child.get("digest"), str)
    ]


async def _weight(session: AsyncSession, *, project: Project, manifest: ContainerManifest) -> int:
    """How much one manifest weighs together with everything under it.

    An index holds no blobs of its own — it names one manifest per architecture
    — so the weight of an image built for several of them is the sum of those.
    """
    try:
        document = json.loads(manifest.body)
    except json.JSONDecodeError:
        return 0
    if not isinstance(document, dict):
        return 0

    total = 0
    for digest in _children(document):
        child = await find_manifest_by_digest(session, project=project, digest=digest)
        if child is not None:
            total += child.size + await _weight(session, project=project, manifest=child)

    wanted = _referenced(document)
    if not wanted:
        return total
    result = await session.execute(
        select(func.coalesce(func.sum(ContainerBlob.size), 0)).where(
            ContainerBlob.project_id == project.id, ContainerBlob.digest.in_(wanted)
        )
    )
    return total + int(result.scalar_one())


async def delete_manifest(session: AsyncSession, *, project: Project, digest: str) -> bool:
    """Forget one manifest together with every tag that named it."""
    manifest = await find_manifest_by_digest(session, project=project, digest=digest)
    if manifest is None:
        return False
    await session.delete(manifest)
    await session.commit()
    return True


async def delete_tag(session: AsyncSession, *, project: Project, name: str) -> bool:
    """Take a name off an image; the image itself stays."""
    result = await session.execute(
        select(ContainerTag).where(ContainerTag.project_id == project.id, ContainerTag.name == name)
    )
    found = result.scalar_one_or_none()
    if found is None:
        return False
    await session.delete(found)
    await session.commit()
    return True


async def usage(session: AsyncSession, *, project: Project) -> Usage:
    """How much of the registry one project takes altogether."""
    counted = await session.execute(
        select(
            func.count(ContainerBlob.id),
            func.coalesce(func.sum(ContainerBlob.size), 0),
        ).where(ContainerBlob.project_id == project.id)
    )
    blobs, held = counted.one()
    manifests = await session.scalar(
        select(func.count(ContainerManifest.id)).where(ContainerManifest.project_id == project.id)
    )
    tags = await session.scalar(
        select(func.count(ContainerTag.id)).where(ContainerTag.project_id == project.id)
    )
    return Usage(
        tags=int(tags or 0), manifests=int(manifests or 0), blobs=int(blobs), bytes=int(held)
    )


async def list_repositories(session: AsyncSession, *, user: User | None, limit: int) -> list[str]:
    """The repositories that hold an image and the caller is allowed to see.

    A catalog that named repositories nobody may pull from would tell a
    stranger what exists, so every row is weighed before it is listed.
    """
    holding = select(ContainerManifest.project_id).distinct()
    result = await session.execute(
        select(Project, User, Group.slug)
        .join(User, User.id == Project.owner_id)
        .outerjoin(Group, Group.id == Project.group_id)
        .where(Project.id.in_(holding))
        .order_by(Project.created_at.desc())
        .limit(limit)
    )

    names: list[str] = []
    for project, owner, group_slug in result:
        access = await projects.access_of(session, project=project, user=user)
        if access.read:
            names.append(f"{group_slug or owner.login}/{project.slug}")
    return names

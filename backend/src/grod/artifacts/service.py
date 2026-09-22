"""Keeping the secrets of a project and the files it publishes."""

import asyncio
import hashlib
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from grod.accounts.models import User
from grod.artifacts import crypto
from grod.artifacts.models import NAME_PATTERN, Package, Secret
from grod.config import get_settings
from grod.repositories.models import Project

__all__ = [
    "AlreadyExistsError",
    "InvalidNameError",
    "Package",
    "PackageTooLargeError",
    "Secret",
    "StoredPackage",
    "delete_package",
    "delete_secret",
    "find_package",
    "list_packages",
    "list_secrets",
    "mask",
    "package_path",
    "publish_package",
    "secrets_for_job",
    "set_secret",
]

NAME_RULE = re.compile(NAME_PATTERN)
MASK = "********"
MIN_MASKED_LENGTH = 8
CHUNK_SIZE = 1024 * 1024
MAX_PACKAGE_BYTES = 500 * 1024 * 1024


class InvalidNameError(Exception):
    """A secret is named like a shell variable, so a job can use it."""


class AlreadyExistsError(Exception):
    """The project already keeps something under that name."""


class PackageTooLargeError(Exception):
    """The file is larger than this instance accepts."""


@dataclass(frozen=True)
class StoredPackage:
    """A published file together with where it lies on disk."""

    package: Package
    path: Path


def package_path(project_id: UUID, package_id: UUID) -> Path:
    """Where the contents of one published file live."""
    return get_settings().packages_path / str(project_id) / str(package_id)


async def list_secrets(session: AsyncSession, *, project: Project) -> list[Secret]:
    """Return the secrets of a project, by name."""
    result = await session.execute(
        select(Secret).where(Secret.project_id == project.id).order_by(Secret.name)
    )
    return list(result.scalars())


async def set_secret(
    session: AsyncSession,
    *,
    project: Project,
    name: str,
    value: str,
    masked: bool = True,
    protected: bool = False,
) -> Secret:
    """Add a secret, or write a new value over the one that is there."""
    if NAME_RULE.match(name) is None:
        raise InvalidNameError(name)

    result = await session.execute(
        select(Secret).where(Secret.project_id == project.id, Secret.name == name)
    )
    secret = result.scalar_one_or_none()
    if secret is None:
        secret = Secret(
            project_id=project.id,
            name=name,
            value_encrypted=crypto.encrypt(value),
            masked=masked,
            protected=protected,
        )
        session.add(secret)
    else:
        secret.value_encrypted = crypto.encrypt(value)
        secret.masked = masked
        secret.protected = protected

    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise AlreadyExistsError(name) from error
    return secret


async def delete_secret(session: AsyncSession, *, project: Project, name: str) -> bool:
    """Remove a secret. Returns whether there was one."""
    result = await session.execute(
        select(Secret).where(Secret.project_id == project.id, Secret.name == name)
    )
    secret = result.scalar_one_or_none()
    if secret is None:
        return False
    await session.delete(secret)
    await session.commit()
    return True


async def secrets_for_job(
    session: AsyncSession, *, project: Project, protected_branch: bool
) -> dict[str, str]:
    """Return the secrets a job may see, in clear, ready to become variables.

    A protected secret only goes to a job that runs on a protected branch, so
    a stranger cannot read it by pushing a branch with a printing script.
    """
    values: dict[str, str] = {}
    for secret in await list_secrets(session, project=project):
        if secret.protected and not protected_branch:
            continue
        try:
            values[secret.name] = crypto.decrypt(secret.value_encrypted)
        except crypto.UnreadableSecretError:
            # A secret from another instance stays out rather than breaking the job.
            continue
    return values


def mask(text: str, secrets: dict[str, str], masked_names: set[str]) -> str:
    """Replace the masked values with stars wherever they appear in a log."""
    for name, value in secrets.items():
        if name in masked_names and len(value) >= MIN_MASKED_LENGTH:
            text = text.replace(value, MASK)
    return text


async def list_packages(session: AsyncSession, *, project: Project) -> list[Package]:
    """Return what a project published, newest first."""
    result = await session.execute(
        select(Package).where(Package.project_id == project.id).order_by(Package.created_at.desc())
    )
    return list(result.scalars())


async def find_package(
    session: AsyncSession, *, project: Project, name: str, version: str, filename: str
) -> StoredPackage | None:
    """Find one published file by its address."""
    result = await session.execute(
        select(Package).where(
            Package.project_id == project.id,
            Package.name == name,
            Package.version == version,
            Package.filename == filename,
        )
    )
    package = result.scalar_one_or_none()
    if package is None:
        return None
    path = package_path(project.id, package.id)
    if not path.is_file():
        return None
    return StoredPackage(package=package, path=path)


async def publish_package(
    session: AsyncSession,
    *,
    project: Project,
    name: str,
    version: str,
    filename: str,
    content: AsyncIterator[bytes],
    uploaded_by: User | None = None,
) -> Package:
    """Store an uploaded file and remember where it belongs.

    Publishing the same address twice replaces the file, the way a registry
    that keeps one artifact per version does.
    """
    result = await session.execute(
        select(Package).where(
            Package.project_id == project.id,
            Package.name == name,
            Package.version == version,
            Package.filename == filename,
        )
    )
    package = result.scalar_one_or_none()
    if package is None:
        package = Package(
            project_id=project.id,
            name=name,
            version=version,
            filename=filename,
            size=0,
            digest="",
            uploaded_by_id=uploaded_by.id if uploaded_by else None,
        )
        session.add(package)
        await session.flush()

    path = package_path(project.id, package.id)
    size, digest = await _write(path, content)

    package.size = size
    package.digest = digest
    await session.commit()
    return package


async def _write(path: Path, content: AsyncIterator[bytes]) -> tuple[int, str]:
    """Write the upload to disk, counting its size and its digest as it goes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_suffix(".part")
    hasher = hashlib.sha256()
    size = 0

    handle = await asyncio.to_thread(staging.open, "wb")
    try:
        async for chunk in content:
            size += len(chunk)
            if size > MAX_PACKAGE_BYTES:
                raise PackageTooLargeError(size)
            hasher.update(chunk)
            await asyncio.to_thread(handle.write, chunk)
    except BaseException:
        await asyncio.to_thread(handle.close)
        staging.unlink(missing_ok=True)
        raise
    await asyncio.to_thread(handle.close)

    await asyncio.to_thread(staging.replace, path)
    return size, hasher.hexdigest()


async def delete_package(session: AsyncSession, *, package: Package) -> None:
    """Remove a published file together with its contents."""
    path = package_path(package.project_id, package.id)
    await session.delete(package)
    await session.commit()
    await asyncio.to_thread(path.unlink, True)

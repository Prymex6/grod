"""Publishing a folder of a repository as a static site."""

import asyncio
import io
import shutil
import tarfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grod.config import get_settings
from grod.pages.models import DEFAULT_DIRECTORY, Site
from grod.repositories import git
from grod.repositories.models import Project

__all__ = [
    "NothingToPublishError",
    "ServedFile",
    "Site",
    "configure",
    "find",
    "publish",
    "remove",
    "resolve_file",
    "site_path",
]

INDEX_FILE = "index.html"
NOT_FOUND_FILE = "404.html"
MAX_SITE_BYTES = 200 * 1024 * 1024


class NothingToPublishError(Exception):
    """The branch or the folder the site points at does not exist."""


@dataclass(frozen=True)
class ServedFile:
    """A file of a published site, ready to be sent."""

    path: Path
    media_type: str


def site_path(project_id: UUID) -> Path:
    """Where the published files of a project live."""
    return get_settings().pages_path / str(project_id)


async def find(session: AsyncSession, *, project: Project) -> Site | None:
    """Return the site of a project, if it has one."""
    result = await session.execute(select(Site).where(Site.project_id == project.id))
    return result.scalar_one_or_none()


async def configure(
    session: AsyncSession,
    *,
    project: Project,
    branch: str,
    directory: str = DEFAULT_DIRECTORY,
    enabled: bool = True,
) -> Site:
    """Set up, or change, what a project publishes."""
    site = await find(session, project=project)
    if site is None:
        site = Site(project_id=project.id, branch=branch, directory=directory, enabled=enabled)
        session.add(site)
    else:
        site.branch = branch
        site.directory = directory
        site.enabled = enabled
    await session.commit()
    return site


async def remove(session: AsyncSession, *, site: Site) -> None:
    """Take a site down and delete the files it published."""
    await session.delete(site)
    await session.commit()
    await asyncio.to_thread(shutil.rmtree, site_path(site.project_id), True)


async def publish(session: AsyncSession, *, project: Project, site: Site) -> Site:
    """Copy the chosen folder at the tip of the branch into the served directory.

    The files land in a fresh directory first and only then take the place of
    the old ones, so a visitor never sees a half-written site.
    """
    try:
        commit = await git.resolve_ref(project.id, site.branch)
    except git.RefNotFoundError as error:
        raise NothingToPublishError(site.branch) from error

    prefix = site.directory.strip("/")
    try:
        archive = await git.archive(project.id, commit, path=prefix or None)
    except (git.RefNotFoundError, git.PathNotFoundError) as error:
        raise NothingToPublishError(prefix) from error

    target = site_path(project.id)
    staging = target.with_name(f"{target.name}.new")
    await asyncio.to_thread(_unpack, archive, staging, prefix)
    await asyncio.to_thread(_swap, staging, target)

    site.published_commit = commit
    site.published_at = datetime.now(UTC)
    await session.commit()
    return site


def _unpack(archive: bytes, staging: Path, prefix: str) -> None:
    """Write the archive into a fresh directory, dropping the folder prefix."""
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        # The archive comes from the platform's own repository; "data" still
        # refuses entries that would land outside the directory.
        tar.extractall(staging, filter="data")

    # git archive with a path keeps that path in front of every entry.
    if prefix:
        inner = staging / prefix
        if inner.is_dir():
            for item in inner.iterdir():
                shutil.move(str(item), staging / item.name)
            shutil.rmtree(inner, ignore_errors=True)


def _swap(staging: Path, target: Path) -> None:
    """Put the new files in place of the old ones."""
    previous = target.with_name(f"{target.name}.old")
    shutil.rmtree(previous, ignore_errors=True)
    if target.exists():
        target.rename(previous)
    staging.rename(target)
    shutil.rmtree(previous, ignore_errors=True)


def resolve_file(project_id: UUID, path: str) -> ServedFile | None:
    """Find the file a visitor asked for, or the page that stands in for it.

    A path that tries to leave the directory of the site is refused, and a
    folder is served through its index file, the way every static host does.
    """
    root = site_path(project_id).resolve()
    if not root.is_dir():
        return None

    wanted = (root / path.lstrip("/")).resolve() if path else root
    if wanted != root and root not in wanted.parents:
        return None

    if wanted.is_dir():
        wanted = wanted / INDEX_FILE
    if wanted.is_file():
        return ServedFile(path=wanted, media_type=_media_type(wanted))

    fallback = root / NOT_FOUND_FILE
    if fallback.is_file():
        return ServedFile(path=fallback, media_type=_media_type(fallback))
    return None


def _media_type(path: Path) -> str:
    """Guess the type of a file from its name."""
    import mimetypes

    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"

"""Running a workspace, and bringing what was done in it back as a commit.

The code goes in as an archive of one commit and comes back the same way, so
the container never needs credentials, a network or a way out of itself.
"""

import hashlib
import io
import re
import tarfile
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from grod.accounts.models import User
from grod.apps import containers
from grod.repositories import git
from grod.repositories.models import Project
from grod.workspaces.models import (
    DEFAULT_CPUS,
    DEFAULT_IMAGE,
    DEFAULT_MEMORY_MB,
    NAME_PATTERN,
    WORKDIR,
    Workspace,
    WorkspaceState,
)

NAME_RULE = re.compile(NAME_PATTERN)
CONTAINER_PREFIX = "grod-workspaces"
MAX_ERROR_LENGTH = 2000
# What one save may carry back. A workspace is for code, not for a data set.
MAX_FILES = 2000
MAX_TOTAL_BYTES = 50 * 1024 * 1024
# Everything Git keeps about itself stays out of the container and out of a save.
SKIPPED_PREFIXES = (".git/",)


class InvalidNameError(Exception):
    """A workspace is named like a host name."""


class NameTakenError(Exception):
    """The account already has a workspace with that name."""


class NotRunningError(Exception):
    """There is no container to look into."""


class TooMuchError(Exception):
    """The workspace holds more than one commit may carry back."""


@dataclass(frozen=True)
class Change:
    """One file a save would write, or take out."""

    path: str
    content: bytes | None


def container_name(workspace: Workspace) -> str:
    """The name the engine knows this workspace by."""
    return f"{CONTAINER_PREFIX}-{workspace.id}"


def blob_name(content: bytes) -> str:
    """The name Git would know this content by, without asking Git."""
    header = f"blob {len(content)}\0".encode()
    return hashlib.sha1(header + content, usedforsecurity=False).hexdigest()


async def list_workspaces(session: AsyncSession, *, owner_id: UUID) -> list[Workspace]:
    """Return the workspaces of an account, newest first."""
    result = await session.execute(
        select(Workspace)
        .where(Workspace.owner_id == owner_id)
        .order_by(Workspace.created_at.desc())
    )
    return list(result.scalars())


async def find(session: AsyncSession, *, owner_id: UUID, name: str) -> Workspace | None:
    """Return one workspace of an account by name."""
    result = await session.execute(
        select(Workspace).where(Workspace.owner_id == owner_id, Workspace.name == name.lower())
    )
    return result.scalar_one_or_none()


async def create(
    session: AsyncSession,
    *,
    owner: User,
    project: Project,
    name: str,
    branch: str,
    image: str = DEFAULT_IMAGE,
) -> Workspace:
    """Describe a workspace. Nothing runs until it is started."""
    address = name.lower()
    if NAME_RULE.match(address) is None:
        raise InvalidNameError(name)

    workspace = Workspace(
        owner_id=owner.id,
        project_id=project.id,
        name=address,
        branch=branch,
        image=image,
    )
    session.add(workspace)
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise NameTakenError(name) from error
    return workspace


async def start(session: AsyncSession, *, workspace: Workspace, project: Project) -> Workspace:
    """Put the code of the branch into a fresh container and leave it waiting."""
    await _forget_container(workspace)

    try:
        commit = await git.resolve_ref(project.id, workspace.branch)
        archive = await git.archive(project.id, commit)
    except (git.RefNotFoundError, git.GitError) as error:
        return await _failed(session, workspace, str(error))

    try:
        container_id = await containers.run_idle(
            name=container_name(workspace),
            image=workspace.image,
            memory_mb=DEFAULT_MEMORY_MB,
            cpus=float(DEFAULT_CPUS),
            workdir=WORKDIR,
        )
        await containers.copy_into(container_id, archive=archive, path=WORKDIR)
    except containers.ContainerError as error:
        return await _failed(session, workspace, str(error))

    workspace.container_id = container_id
    workspace.commit = commit
    workspace.state = WorkspaceState.RUNNING
    workspace.last_error = ""
    await session.commit()
    return workspace


async def _failed(session: AsyncSession, workspace: Workspace, why: str) -> Workspace:
    workspace.state = WorkspaceState.FAILED
    workspace.container_id = None
    workspace.last_error = why[:MAX_ERROR_LENGTH]
    await session.commit()
    return workspace


async def stop(session: AsyncSession, *, workspace: Workspace) -> Workspace:
    """Take the container down. Anything not saved goes with it."""
    await _forget_container(workspace)
    workspace.container_id = None
    workspace.state = WorkspaceState.STOPPED
    await session.commit()
    return workspace


async def _forget_container(workspace: Workspace) -> None:
    """Remove the container of a workspace, if there is one."""
    try:
        await containers.remove(container_name(workspace))
    except containers.ContainerError:
        # There was nothing to remove, which is exactly what was wanted.
        return


async def delete(session: AsyncSession, *, workspace: Workspace) -> None:
    """Remove a workspace together with its container."""
    await _forget_container(workspace)
    await session.delete(workspace)
    await session.commit()


async def sweep(session: AsyncSession) -> int:
    """Remove containers of workspaces that no longer exist. Returns how many.

    Taking a workspace down can fail — a terminal still attached to it is
    enough — and the row goes either way, because that is what was asked for.
    Without this the container would sit on the machine with nothing pointing
    at it, so the listing tidies up whatever was left behind.
    """
    try:
        found = await containers.names_starting_with(f"{CONTAINER_PREFIX}-")
    except containers.ContainerError:
        return 0

    result = await session.execute(select(Workspace.id))
    known = {f"{CONTAINER_PREFIX}-{workspace_id}" for workspace_id in result.scalars()}

    removed = 0
    for name in found:
        if name in known:
            continue
        try:
            await containers.remove(name)
        except containers.ContainerError:
            continue
        removed += 1
    return removed


async def refresh(session: AsyncSession, *, workspace: Workspace) -> Workspace:
    """Ask the engine whether the container is still there."""
    if workspace.container_id is None:
        return workspace

    found = await containers.state(workspace.container_id)
    if found is None or not found.running:
        workspace.state = WorkspaceState.STOPPED
        workspace.container_id = None
        await session.commit()
    return workspace


def _wanted(name: str) -> bool:
    """Whether a path out of the container belongs in a commit."""
    return not name.startswith(SKIPPED_PREFIXES) and "/.git/" not in name


def read_archive(raw: bytes) -> dict[str, bytes]:
    """Turn what came out of the container into files, by path."""
    files: dict[str, bytes] = {}
    total = 0
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        for member in archive:
            if not member.isfile():
                continue
            # docker cp names the folder itself first; the paths hang off it.
            path = member.name.split("/", 1)[1] if "/" in member.name else member.name
            if not path or not _wanted(path):
                continue

            total += member.size
            if len(files) >= MAX_FILES or total > MAX_TOTAL_BYTES:
                raise TooMuchError(path)

            handle = archive.extractfile(member)
            if handle is not None:
                files[path] = handle.read()
    return files


async def changes(session: AsyncSession, *, workspace: Workspace, project: Project) -> list[Change]:
    """What the workspace holds that the commit it started from did not."""
    del session
    if workspace.container_id is None:
        raise NotRunningError(workspace.name)

    raw = await containers.copy_out(workspace.container_id, path=f"{WORKDIR}/.")
    held = read_archive(raw)

    before = {
        entry.path: entry.object_id
        for entry in await git.list_files(project.id, ref=workspace.commit, limit=MAX_FILES)
    }

    found: list[Change] = []
    for path, content in sorted(held.items()):
        if before.get(path) != blob_name(content):
            found.append(Change(path=path, content=content))
    found += [Change(path=path, content=None) for path in sorted(before) if path not in held]
    return found


async def save(
    session: AsyncSession,
    *,
    workspace: Workspace,
    project: Project,
    author: User,
    message: str,
) -> tuple[str, int]:
    """Write what the workspace changed into the branch it came from."""
    found = await changes(session, workspace=workspace, project=project)
    if not found:
        return workspace.commit, 0

    commit = await git.commit_files(
        project.id,
        branch=workspace.branch,
        edits=[git.FileEdit(path=change.path, content=change.content) for change in found],
        message=message,
        author_name=author.display_name,
        author_email=author.email,
        parent=workspace.commit,
    )
    workspace.commit = commit
    await session.commit()
    return commit, len(found)

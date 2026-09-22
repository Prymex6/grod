"""Endpoints of Warsztat: workspaces, and the terminal inside one."""

import asyncio
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession

from grod.accounts import service as accounts
from grod.accounts import sessions
from grod.accounts.dependencies import CurrentUser
from grod.accounts.models import User
from grod.accounts.schemas import ApiModel
from grod.apps import containers
from grod.collaboration.router import NOT_ALLOWED_DETAIL, readable
from grod.config import get_settings
from grod.db import get_db_session, get_session_factory
from grod.quotas import service as quotas
from grod.quotas.errors import refusal
from grod.repositories import after_push, git, pushes
from grod.repositories import service as projects
from grod.repositories.models import Project
from grod.workspaces import service
from grod.workspaces.models import (
    DEFAULT_IMAGE,
    IMAGE_MAX_LENGTH,
    NAME_MAX_LENGTH,
    NAME_PATTERN,
    Workspace,
    WorkspaceState,
)

router = APIRouter(prefix="/workspaces", tags=["workspaces"])

DbSession = Annotated[AsyncSession, Depends(get_db_session)]

NOT_FOUND_DETAIL = "No such workspace"
NO_ENGINE_DETAIL = "This instance has no container engine"
MESSAGE_MAX_LENGTH = 1000
# What the terminal reads from the shell in one go.
TERMINAL_CHUNK = 4096


class WorkspaceCreate(ApiModel):
    """A new workspace over one branch of one project."""

    name: str = Field(pattern=NAME_PATTERN, min_length=2, max_length=NAME_MAX_LENGTH)
    owner: str
    slug: str
    branch: str
    image: str = Field(default=DEFAULT_IMAGE, max_length=IMAGE_MAX_LENGTH)


class WorkspaceView(ApiModel):
    """A workspace as the console shows it."""

    id: str
    name: str
    project: str
    branch: str
    image: str
    commit: str
    state: WorkspaceState
    last_error: str
    created_at: datetime


class ChangeView(ApiModel):
    """One file the workspace holds differently than the branch does."""

    path: str
    removed: bool
    size: int


class SaveRequest(ApiModel):
    """What to write on the commit that carries the work back."""

    message: str = Field(min_length=1, max_length=MESSAGE_MAX_LENGTH)


class SaveView(ApiModel):
    """What a save came to."""

    commit: str
    files: int


def _view(workspace: Workspace, project: str) -> WorkspaceView:
    return WorkspaceView(
        id=str(workspace.id),
        name=workspace.name,
        project=project,
        branch=workspace.branch,
        image=workspace.image,
        commit=workspace.commit,
        state=workspace.state,
        last_error=workspace.last_error,
        created_at=workspace.created_at,
    )


async def _project_of(db: AsyncSession, workspace: Workspace) -> Project:
    """The project a workspace works on."""
    project = await db.get(Project, workspace.project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL)
    return project


async def _address_of(db: AsyncSession, project: Project) -> str:
    """How the project is written in the console: owner/slug."""
    owner = await accounts.find_by_id(db, project.owner_id)
    return f"{owner.login if owner else '?'}/{project.slug}"


async def _mine(db: AsyncSession, name: str, user: User) -> Workspace:
    """Find a workspace of the signed-in account."""
    workspace = await service.find(db, owner_id=user.id, name=name)
    if workspace is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL)
    return workspace


@router.get("")
async def list_workspaces(db: DbSession, user: CurrentUser) -> list[WorkspaceView]:
    """Return the workspaces of the signed-in account."""
    # Opening the list is also when anything left behind gets cleared away.
    await service.sweep(db)
    found = await service.list_workspaces(db, owner_id=user.id)
    views: list[WorkspaceView] = []
    for workspace in found:
        refreshed = await service.refresh(db, workspace=workspace)
        project = await _project_of(db, refreshed)
        views.append(_view(refreshed, await _address_of(db, project)))
    return views


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_workspace(
    body: WorkspaceCreate, db: DbSession, user: CurrentUser
) -> WorkspaceView:
    """Describe a workspace. Nothing runs until it is started."""
    project, access = await readable(db, body.owner, body.slug, user)
    # Work done here comes back as a commit, so it belongs to whoever may push.
    if not access.write:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=NOT_ALLOWED_DETAIL)

    try:
        await quotas.ensure_room_for_one_more(db, owner_id=user.id, thing=quotas.Thing.WORKSPACE)
    except quotas.OverQuotaError as error:
        raise refusal(error) from None

    try:
        workspace = await service.create(
            db,
            owner=user,
            project=project,
            name=body.name,
            branch=body.branch,
            image=body.image,
        )
    except service.InvalidNameError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid name") from None
    except service.NameTakenError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="You already have a workspace with that name"
        ) from None
    return _view(workspace, await _address_of(db, project))


@router.get("/{name}")
async def read_workspace(name: str, db: DbSession, user: CurrentUser) -> WorkspaceView:
    """Return one workspace, asking the engine whether it still runs."""
    workspace = await service.refresh(db, workspace=await _mine(db, name, user))
    project = await _project_of(db, workspace)
    return _view(workspace, await _address_of(db, project))


@router.post("/{name}/start")
async def start_workspace(name: str, db: DbSession, user: CurrentUser) -> WorkspaceView:
    """Put the code of the branch into a fresh container."""
    workspace = await _mine(db, name, user)
    if not await containers.available():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=NO_ENGINE_DETAIL)

    project = await _project_of(db, workspace)
    started = await service.start(db, workspace=workspace, project=project)
    return _view(started, await _address_of(db, project))


@router.post("/{name}/stop")
async def stop_workspace(name: str, db: DbSession, user: CurrentUser) -> WorkspaceView:
    """Take the container down. Anything not saved goes with it."""
    workspace = await service.stop(db, workspace=await _mine(db, name, user))
    project = await _project_of(db, workspace)
    return _view(workspace, await _address_of(db, project))


@router.get("/{name}/changes")
async def read_changes(name: str, db: DbSession, user: CurrentUser) -> list[ChangeView]:
    """Return what the workspace holds differently than the branch it came from."""
    workspace = await _mine(db, name, user)
    project = await _project_of(db, workspace)
    try:
        found = await service.changes(db, workspace=workspace, project=project)
    except service.NotRunningError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="This workspace is not running"
        ) from None
    except service.TooMuchError:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="This workspace holds more than one commit may carry back",
        ) from None
    except containers.ContainerError as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(error)) from None

    return [
        ChangeView(
            path=change.path,
            removed=change.content is None,
            size=0 if change.content is None else len(change.content),
        )
        for change in found
    ]


@router.post("/{name}/save")
async def save_workspace(
    name: str, body: SaveRequest, db: DbSession, user: CurrentUser
) -> SaveView:
    """Write what was done in the workspace into the branch, as one commit."""
    workspace = await _mine(db, name, user)
    project = await _project_of(db, workspace)
    # Rights can be taken away after a workspace was made, so they are weighed
    # again here rather than trusted from the moment it was created.
    access = await projects.access_of(db, project=project, user=user)
    if not access.write:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=NOT_ALLOWED_DETAIL)

    before = await pushes.branch_tips(project)
    try:
        commit, files = await service.save(
            db, workspace=workspace, project=project, author=user, message=body.message
        )
    except service.NotRunningError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="This workspace is not running"
        ) from None
    except service.TooMuchError:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="This workspace holds more than one commit may carry back",
        ) from None
    except git.StaleBranchError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="Somebody changed this branch in the meantime"
        ) from None
    except containers.ContainerError as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(error)) from None

    if files:
        await after_push.handle(db, project=project, before=before, pusher=user)
    return SaveView(commit=commit, files=files)


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workspace(name: str, db: DbSession, user: CurrentUser) -> None:
    """Remove a workspace together with its container."""
    await service.delete(db, workspace=await _mine(db, name, user))


async def _websocket_user(websocket: WebSocket, db: AsyncSession) -> User | None:
    """Who is on the other end of the socket, read from the session cookie."""
    token = websocket.cookies.get(get_settings().session_cookie_name)
    if not token:
        return None
    user_id = await sessions.read_session(token)
    if user_id is None:
        return None
    return await accounts.get_by_id(db, user_id)


@router.websocket("/{name}/terminal")
async def terminal(websocket: WebSocket, name: str) -> None:
    """Join the browser to a shell inside the container.

    The socket carries bytes both ways and nothing else: what the person types
    goes to the shell, what the shell prints comes back.
    """
    await websocket.accept()
    async with get_session_factory()() as db:
        user = await _websocket_user(websocket, db)
        if user is None:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        workspace = await service.find(db, owner_id=user.id, name=name)
        if workspace is None or workspace.container_id is None:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        container_id = workspace.container_id

    try:
        shell = await containers.open_shell(container_id)
    except containers.ContainerError:
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        return

    try:
        await _join(websocket, shell)
    finally:
        if shell.returncode is None:
            shell.kill()


async def _join(websocket: WebSocket, shell: asyncio.subprocess.Process) -> None:
    """Carry bytes between the socket and the shell until one of them stops."""

    out = shell.stdout
    into = shell.stdin
    if out is None or into is None:
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        return

    async def to_browser() -> None:
        while chunk := await out.read(TERMINAL_CHUNK):
            await websocket.send_text(chunk.decode(errors="replace"))

    async def to_shell() -> None:
        while True:
            typed = await websocket.receive_text()
            into.write(typed.encode())
            await into.drain()

    reader = asyncio.create_task(to_browser())
    writer = asyncio.create_task(to_shell())
    try:
        await asyncio.wait({reader, writer}, return_when=asyncio.FIRST_COMPLETED)
    except WebSocketDisconnect:
        pass
    finally:
        for task in (reader, writer):
            task.cancel()

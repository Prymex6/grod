"""Endpoints for the applications an account runs."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession

from grod.accounts.dependencies import CurrentUser
from grod.accounts.schemas import ApiModel
from grod.apps import containers, service
from grod.apps.models import (
    COMMAND_MAX_LENGTH,
    DEFAULT_CPUS,
    DEFAULT_MEMORY_MB,
    IMAGE_MAX_LENGTH,
    NAME_MAX_LENGTH,
    NAME_PATTERN,
    Application,
    AppState,
)
from grod.db import get_db_session
from grod.iam import scope
from grod.iam import service as iam
from grod.iam.dependencies import CurrentActor
from grod.iam.models import ResourceKind, Role
from grod.quotas import service as quotas
from grod.quotas.errors import refusal
from grod.quotas.service import Thing

router = APIRouter(prefix="/apps", tags=["apps"])

DbSession = Annotated[AsyncSession, Depends(get_db_session)]

NOT_FOUND_DETAIL = "No such application"
MIN_MEMORY_MB = 32
MAX_MEMORY_MB = 8192
MIN_CPUS = 0.1
MAX_CPUS = 8.0
MIN_PORT = 1
MAX_PORT = 65535
MAX_LOG_LINES = 1000


class ApplicationCreate(ApiModel):
    """A new application. Nothing runs until it is started."""

    name: str = Field(pattern=NAME_PATTERN, min_length=3, max_length=NAME_MAX_LENGTH)
    image: str = Field(min_length=1, max_length=IMAGE_MAX_LENGTH)
    command: str = Field(default="", max_length=COMMAND_MAX_LENGTH)
    environment: dict[str, str] = Field(default_factory=dict)
    port: int | None = Field(default=None, ge=MIN_PORT, le=MAX_PORT)
    memory_mb: int = Field(default=DEFAULT_MEMORY_MB, ge=MIN_MEMORY_MB, le=MAX_MEMORY_MB)
    cpus: float = Field(default=DEFAULT_CPUS, ge=MIN_CPUS, le=MAX_CPUS)


class ApplicationView(ApiModel):
    """An application as the console shows it."""

    id: str
    name: str
    image: str
    command: str
    environment: dict[str, str]
    port: int | None
    host_port: int | None
    memory_mb: int
    cpus: float
    state: AppState
    last_error: str
    created_at: datetime
    url: str | None


class LogView(ApiModel):
    """What an application printed."""

    log: str


class EngineView(ApiModel):
    """Whether this instance can run applications at all."""

    available: bool


def _view(application: Application) -> ApplicationView:
    address = (
        f"http://127.0.0.1:{application.host_port}" if application.host_port is not None else None
    )
    return ApplicationView(
        id=str(application.id),
        name=application.name,
        image=application.image,
        command=application.command,
        environment=service.environment_of(application),
        port=application.port,
        host_port=application.host_port,
        memory_mb=application.memory_mb,
        cpus=float(application.cpus),
        state=application.state,
        last_error=application.last_error,
        created_at=application.created_at,
        url=address,
    )


async def _allowed(db: AsyncSession, name: str, actor: iam.Actor, needed: Role) -> Application:
    """Find an application this actor may do that much with."""
    application = await scope.allowed(
        db, Application, actor=actor, kind=ResourceKind.APPLICATION, name=name, needed=needed
    )
    if application is None:
        # One nobody may touch must look exactly like one that is not there.
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL)
    return application


@router.get("/engine")
async def read_engine() -> EngineView:
    """Say whether a container engine answers on this machine."""
    return EngineView(available=await containers.available())


@router.get("")
async def list_applications(db: DbSession, actor: CurrentActor) -> list[ApplicationView]:
    """Return the applications the caller may see."""
    found = await scope.visible(db, Application, actor=actor, kind=ResourceKind.APPLICATION)
    return [_view(await service.refresh(db, application=item)) for item in found]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_application(
    body: ApplicationCreate, db: DbSession, user: CurrentUser
) -> ApplicationView:
    """Describe an application."""
    try:
        await quotas.ensure_room_for_one_more(db, owner_id=user.id, thing=Thing.APPLICATION)
    except quotas.OverQuotaError as error:
        raise refusal(error) from None

    try:
        application = await service.create(
            db,
            owner=user,
            name=body.name,
            image=body.image,
            command=body.command,
            environment=body.environment,
            port=body.port,
            memory_mb=body.memory_mb,
            cpus=body.cpus,
        )
    except service.InvalidNameError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid name") from None
    except service.NameTakenError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="You already have an application with that name"
        ) from None
    except service.NoFreePortError:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, detail="No free port is left on this instance"
        ) from None
    return _view(application)


@router.get("/{name}")
async def read_application(name: str, db: DbSession, actor: CurrentActor) -> ApplicationView:
    """Return one application, asking the engine how it is doing."""
    application = await _allowed(db, name, actor, Role.VIEWER)
    return _view(await service.refresh(db, application=application))


@router.post("/{name}/start")
async def start_application(name: str, db: DbSession, actor: CurrentActor) -> ApplicationView:
    """Start the application, or restart it when it already runs."""
    application = await _allowed(db, name, actor, Role.OPERATOR)
    try:
        started = await service.start(db, application=application)
    except service.EngineUnavailableError:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="This instance has no container engine",
        ) from None
    return _view(started)


@router.post("/{name}/stop")
async def stop_application(name: str, db: DbSession, actor: CurrentActor) -> ApplicationView:
    """Stop the application."""
    application = await _allowed(db, name, actor, Role.OPERATOR)
    return _view(await service.stop(db, application=application))


@router.get("/{name}/logs")
async def read_logs(
    name: str,
    db: DbSession,
    actor: CurrentActor,
    tail: Annotated[int, Query(le=MAX_LOG_LINES)] = 200,
) -> LogView:
    """Return what the application printed."""
    application = await _allowed(db, name, actor, Role.VIEWER)
    return LogView(log=await service.logs(application, tail=tail))


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_application(name: str, db: DbSession, actor: CurrentActor) -> None:
    """Remove an application together with its container."""
    application = await _allowed(db, name, actor, Role.ADMIN)
    await service.delete(db, application=application)

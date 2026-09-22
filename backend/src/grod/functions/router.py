"""Endpoints for functions and calling them."""

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession

from grod.accounts.dependencies import CurrentUser
from grod.accounts.schemas import ApiModel
from grod.db import get_db_session
from grod.functions import service
from grod.functions.models import (
    DEFAULT_MEMORY_MB,
    DEFAULT_TIMEOUT_SECONDS,
    NAME_MAX_LENGTH,
    NAME_PATTERN,
    SOURCE_MAX_LENGTH,
    Function,
    Runtime,
)
from grod.iam import scope
from grod.iam import service as iam
from grod.iam.dependencies import CurrentActor
from grod.iam.models import ResourceKind, Role
from grod.quotas import service as quotas
from grod.quotas.errors import refusal
from grod.quotas.service import Thing

router = APIRouter(prefix="/functions", tags=["functions"])

DbSession = Annotated[AsyncSession, Depends(get_db_session)]

NOT_FOUND_DETAIL = "No such function"
MIN_TIMEOUT_SECONDS = 1
MAX_TIMEOUT_SECONDS = 60
MIN_MEMORY_MB = 64
MAX_MEMORY_MB = 2048


class FunctionCreate(ApiModel):
    """A new function. Empty source means the example of its runtime."""

    name: str = Field(pattern=NAME_PATTERN, min_length=3, max_length=NAME_MAX_LENGTH)
    runtime: Runtime = Runtime.PYTHON
    source: str = Field(default="", max_length=SOURCE_MAX_LENGTH)
    timeout_seconds: int = Field(
        default=DEFAULT_TIMEOUT_SECONDS, ge=MIN_TIMEOUT_SECONDS, le=MAX_TIMEOUT_SECONDS
    )
    memory_mb: int = Field(default=DEFAULT_MEMORY_MB, ge=MIN_MEMORY_MB, le=MAX_MEMORY_MB)


class FunctionUpdate(ApiModel):
    """Changing a function; every field is optional."""

    source: str | None = Field(default=None, max_length=SOURCE_MAX_LENGTH)
    timeout_seconds: int | None = Field(
        default=None, ge=MIN_TIMEOUT_SECONDS, le=MAX_TIMEOUT_SECONDS
    )
    memory_mb: int | None = Field(default=None, ge=MIN_MEMORY_MB, le=MAX_MEMORY_MB)


class FunctionView(ApiModel):
    """A function as the console shows it."""

    id: str
    name: str
    runtime: Runtime
    source: str
    timeout_seconds: int
    memory_mb: int
    calls: int
    failures: int
    last_called_at: datetime | None
    last_duration_ms: int | None
    last_error: str
    created_at: datetime


class CallView(ApiModel):
    """What one call produced."""

    ok: bool
    answer: Any
    output: str
    error: str
    duration_ms: int
    timed_out: bool


def _view(function: Function) -> FunctionView:
    return FunctionView(
        id=str(function.id),
        name=function.name,
        runtime=function.runtime,
        source=function.source,
        timeout_seconds=function.timeout_seconds,
        memory_mb=function.memory_mb,
        calls=function.calls,
        failures=function.failures,
        last_called_at=function.last_called_at,
        last_duration_ms=function.last_duration_ms,
        last_error=function.last_error,
        created_at=function.created_at,
    )


async def _allowed(db: AsyncSession, name: str, actor: iam.Actor, needed: Role) -> Function:
    """Find a function this actor may do that much with."""
    function = await scope.allowed(
        db, Function, actor=actor, kind=ResourceKind.FUNCTION, name=name, needed=needed
    )
    if function is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL)
    return function


@router.get("")
async def list_functions(db: DbSession, actor: CurrentActor) -> list[FunctionView]:
    """Return the functions the caller may see."""
    found = await scope.visible(db, Function, actor=actor, kind=ResourceKind.FUNCTION)
    return [_view(function) for function in found]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_function(body: FunctionCreate, db: DbSession, user: CurrentUser) -> FunctionView:
    """Keep a new function."""
    try:
        await quotas.ensure_room_for_one_more(db, owner_id=user.id, thing=Thing.FUNCTION)
    except quotas.OverQuotaError as error:
        raise refusal(error) from None

    try:
        function = await service.create(
            db,
            owner=user,
            name=body.name,
            runtime=body.runtime,
            source=body.source,
            timeout_seconds=body.timeout_seconds,
            memory_mb=body.memory_mb,
        )
    except service.InvalidNameError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid name") from None
    except service.NameTakenError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="You already have a function with that name"
        ) from None
    return _view(function)


@router.get("/{name}")
async def read_function(name: str, db: DbSession, actor: CurrentActor) -> FunctionView:
    """Return one function with its code."""
    return _view(await _allowed(db, name, actor, Role.VIEWER))


@router.patch("/{name}")
async def change_function(
    name: str, body: FunctionUpdate, db: DbSession, actor: CurrentActor
) -> FunctionView:
    """Change the code of a function, or the room it runs in."""
    function = await _allowed(db, name, actor, Role.ADMIN)
    changed = await service.update(
        db,
        function=function,
        source=body.source,
        timeout_seconds=body.timeout_seconds,
        memory_mb=body.memory_mb,
    )
    return _view(changed)


@router.post("/{name}/call")
async def call_function(
    name: str,
    # Without Body() FastAPI would read a bare value as a query parameter.
    event: Annotated[Any, Body()],  # noqa: ANN401  (whatever JSON the caller sent)
    db: DbSession,
    actor: CurrentActor,
) -> CallView:
    """Run the function once with the body of the request as its event."""
    function = await _allowed(db, name, actor, Role.OPERATOR)
    try:
        result = await service.call(db, function=function, event=event)
    except service.EngineUnavailableError:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="This instance has no container engine",
        ) from None
    return CallView(
        ok=result.ok,
        answer=result.answer,
        output=result.output,
        error=result.error,
        duration_ms=result.duration_ms,
        timed_out=result.timed_out,
    )


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_function(name: str, db: DbSession, actor: CurrentActor) -> None:
    """Forget a function."""
    function = await _allowed(db, name, actor, Role.ADMIN)
    await service.delete(db, function=function)

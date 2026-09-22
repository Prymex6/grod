"""Endpoints for what is watched and how it has been doing."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession

from grod.accounts.dependencies import CurrentUser
from grod.accounts.schemas import ApiModel
from grod.db import get_db_session
from grod.iam import scope
from grod.iam import service as iam
from grod.iam.dependencies import CurrentActor
from grod.iam.models import ResourceKind, Role
from grod.monitoring import service
from grod.monitoring.models import (
    DEFAULT_EXPECTED_STATUS,
    DEFAULT_INTERVAL_SECONDS,
    DEFAULT_TIMEOUT_SECONDS,
    NAME_MAX_LENGTH,
    URL_MAX_LENGTH,
    Check,
    CheckResult,
    CheckState,
)

router = APIRouter(prefix="/checks", tags=["monitoring"])

DbSession = Annotated[AsyncSession, Depends(get_db_session)]

NOT_FOUND_DETAIL = "No such check"
MIN_INTERVAL_SECONDS = 10
MAX_INTERVAL_SECONDS = 3600
MIN_TIMEOUT_SECONDS = 1
MAX_TIMEOUT_SECONDS = 60
MIN_STATUS = 100
MAX_STATUS = 599
MAX_RESULTS = 200


class CheckCreate(ApiModel):
    """A new address to watch."""

    name: str = Field(min_length=1, max_length=NAME_MAX_LENGTH)
    url: str = Field(min_length=1, max_length=URL_MAX_LENGTH)
    interval_seconds: int = Field(
        default=DEFAULT_INTERVAL_SECONDS, ge=MIN_INTERVAL_SECONDS, le=MAX_INTERVAL_SECONDS
    )
    expected_status: int = Field(default=DEFAULT_EXPECTED_STATUS, ge=MIN_STATUS, le=MAX_STATUS)
    timeout_seconds: int = Field(
        default=DEFAULT_TIMEOUT_SECONDS, ge=MIN_TIMEOUT_SECONDS, le=MAX_TIMEOUT_SECONDS
    )


class CheckUpdate(ApiModel):
    """Changing a check; every field is optional."""

    url: str | None = Field(default=None, min_length=1, max_length=URL_MAX_LENGTH)
    interval_seconds: int | None = Field(
        default=None, ge=MIN_INTERVAL_SECONDS, le=MAX_INTERVAL_SECONDS
    )
    expected_status: int | None = Field(default=None, ge=MIN_STATUS, le=MAX_STATUS)
    enabled: bool | None = None


class CheckView(ApiModel):
    """A check with how it is doing."""

    id: str
    name: str
    url: str
    interval_seconds: int
    expected_status: int
    enabled: bool
    state: CheckState
    last_checked_at: datetime | None
    last_duration_ms: int | None
    last_error: str
    uptime: float
    average_ms: int
    created_at: datetime


class ResultView(ApiModel):
    """One look at one address."""

    ok: bool
    status_code: int | None
    duration_ms: int
    error: str
    created_at: datetime


async def _view(db: AsyncSession, check: Check) -> CheckView:
    summary = await service.summarise(db, check=check)
    return CheckView(
        id=str(check.id),
        name=check.name,
        url=check.url,
        interval_seconds=check.interval_seconds,
        expected_status=check.expected_status,
        enabled=check.enabled,
        state=check.state,
        last_checked_at=check.last_checked_at,
        last_duration_ms=check.last_duration_ms,
        last_error=check.last_error,
        uptime=summary.uptime,
        average_ms=summary.average_ms,
        created_at=check.created_at,
    )


def _result_view(result: CheckResult) -> ResultView:
    return ResultView(
        ok=result.ok,
        status_code=result.status_code,
        duration_ms=result.duration_ms,
        error=result.error,
        created_at=result.created_at,
    )


async def _allowed(db: AsyncSession, name: str, actor: iam.Actor, needed: Role) -> Check:
    """Find a check this actor may do that much with."""
    check = await scope.allowed(
        db,
        Check,
        actor=actor,
        kind=ResourceKind.CHECK,
        name=name,
        needed=needed,
        lowered=False,
    )
    if check is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL)
    return check


@router.get("")
async def list_checks(db: DbSession, actor: CurrentActor) -> list[CheckView]:
    """Return what the caller may see being watched."""
    found = await scope.visible(db, Check, actor=actor, kind=ResourceKind.CHECK)
    return [await _view(db, check) for check in found]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_check(body: CheckCreate, db: DbSession, user: CurrentUser) -> CheckView:
    """Start watching an address."""
    try:
        check = await service.create(
            db,
            owner=user,
            name=body.name,
            url=body.url,
            interval_seconds=body.interval_seconds,
            expected_status=body.expected_status,
            timeout_seconds=body.timeout_seconds,
        )
    except service.NameTakenError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="You already watch something under that name"
        ) from None
    return await _view(db, check)


@router.get("/{name}")
async def read_check(name: str, db: DbSession, actor: CurrentActor) -> CheckView:
    """Return one check."""
    return await _view(db, await _allowed(db, name, actor, Role.VIEWER))


@router.patch("/{name}")
async def change_check(
    name: str, body: CheckUpdate, db: DbSession, actor: CurrentActor
) -> CheckView:
    """Change what is watched, or how often."""
    check = await _allowed(db, name, actor, Role.ADMIN)
    changed = await service.update(
        db,
        check=check,
        url=body.url,
        interval_seconds=body.interval_seconds,
        expected_status=body.expected_status,
        enabled=body.enabled,
    )
    return await _view(db, changed)


@router.post("/{name}/run")
async def run_check_now(name: str, db: DbSession, actor: CurrentActor) -> CheckView:
    """Look at the address right now instead of waiting for the loop."""
    check = await _allowed(db, name, actor, Role.OPERATOR)
    await service.run_check(db, check=check)
    return await _view(db, check)


@router.get("/{name}/results")
async def read_results(
    name: str,
    db: DbSession,
    actor: CurrentActor,
    limit: Annotated[int, Query(le=MAX_RESULTS)] = 50,
) -> list[ResultView]:
    """Return what the last looks found."""
    check = await _allowed(db, name, actor, Role.VIEWER)
    found = await service.list_results(db, check=check, limit=limit)
    return [_result_view(result) for result in found]


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_check(name: str, db: DbSession, actor: CurrentActor) -> None:
    """Stop watching an address."""
    check = await _allowed(db, name, actor, Role.ADMIN)
    await service.delete(db, check=check)

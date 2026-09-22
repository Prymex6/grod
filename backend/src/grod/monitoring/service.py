"""Looking at the addresses somebody asked the platform to watch."""

import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import delete as sql_delete
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from grod.accounts.models import User
from grod.monitoring.models import Check, CheckResult, CheckState

MILLISECONDS = 1000
# Enough history for a day of looking every minute, and no more.
KEPT_RESULTS = 2000
SUMMARY_HOURS = 24


class NameTakenError(Exception):
    """The account already watches something under that name."""


@dataclass(frozen=True)
class Summary:
    """How an address has been doing lately."""

    checks: int
    failures: int
    uptime: float
    average_ms: int


async def find(session: AsyncSession, *, owner: User, name: str) -> Check | None:
    """Return one check of an account by name."""
    result = await session.execute(
        select(Check).where(Check.owner_id == owner.id, Check.name == name)
    )
    return result.scalar_one_or_none()


async def create(
    session: AsyncSession,
    *,
    owner: User,
    name: str,
    url: str,
    interval_seconds: int,
    expected_status: int,
    timeout_seconds: int,
) -> Check:
    """Start watching an address."""
    check = Check(
        owner_id=owner.id,
        name=name,
        url=url,
        interval_seconds=interval_seconds,
        expected_status=expected_status,
        timeout_seconds=timeout_seconds,
    )
    session.add(check)
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise NameTakenError(name) from error
    return check


async def update(
    session: AsyncSession,
    *,
    check: Check,
    url: str | None = None,
    interval_seconds: int | None = None,
    expected_status: int | None = None,
    enabled: bool | None = None,
) -> Check:
    """Change what is watched, or how often."""
    if url is not None:
        check.url = url
    if interval_seconds is not None:
        check.interval_seconds = interval_seconds
    if expected_status is not None:
        check.expected_status = expected_status
    if enabled is not None:
        check.enabled = enabled
    await session.commit()
    return check


async def delete(session: AsyncSession, *, check: Check) -> None:
    """Stop watching an address and forget what was found."""
    await session.delete(check)
    await session.commit()


async def run_check(session: AsyncSession, *, check: Check) -> CheckResult:
    """Look at the address once and write down what happened."""
    started = time.monotonic()
    status_code: int | None = None
    error = ""

    try:
        async with httpx.AsyncClient(timeout=float(check.timeout_seconds)) as client:
            answer = await client.get(check.url, follow_redirects=True)
        status_code = answer.status_code
        ok = status_code == check.expected_status
        if not ok:
            error = f"Answered {status_code}, expected {check.expected_status}"
    except httpx.HTTPError as failure:
        ok = False
        error = str(failure) or failure.__class__.__name__

    duration = int((time.monotonic() - started) * MILLISECONDS)
    result = CheckResult(
        check_id=check.id,
        ok=ok,
        status_code=status_code,
        duration_ms=duration,
        error=error,
    )
    session.add(result)

    check.state = CheckState.UP if ok else CheckState.DOWN
    check.last_checked_at = datetime.now(UTC)
    check.last_duration_ms = duration
    check.last_error = error
    await session.commit()

    await _forget_old(session, check=check)
    return result


async def _forget_old(session: AsyncSession, *, check: Check) -> None:
    """Keep the history of a check from growing without end."""
    result = await session.execute(
        select(func.count()).select_from(CheckResult).where(CheckResult.check_id == check.id)
    )
    if result.scalar_one() <= KEPT_RESULTS:
        return

    oldest = (
        select(CheckResult.id)
        .where(CheckResult.check_id == check.id)
        .order_by(CheckResult.created_at.desc())
        .offset(KEPT_RESULTS)
    )
    await session.execute(sql_delete(CheckResult).where(CheckResult.id.in_(oldest)))
    await session.commit()


async def list_results(
    session: AsyncSession, *, check: Check, limit: int = 50
) -> list[CheckResult]:
    """Return what the last looks found, newest first."""
    result = await session.execute(
        select(CheckResult)
        .where(CheckResult.check_id == check.id)
        .order_by(CheckResult.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars())


async def summarise(session: AsyncSession, *, check: Check) -> Summary:
    """How the address has been doing over the last day."""
    since = datetime.now(UTC) - timedelta(hours=SUMMARY_HOURS)
    result = await session.execute(
        select(
            func.count(),
            func.count().filter(CheckResult.ok.is_(False)),
            func.coalesce(func.avg(CheckResult.duration_ms), 0),
        ).where(CheckResult.check_id == check.id, CheckResult.created_at >= since)
    )
    checks, failures, average = result.one()
    uptime = 100.0 if checks == 0 else round((checks - failures) * 100.0 / checks, 2)
    return Summary(checks=checks, failures=failures, uptime=uptime, average_ms=int(average or 0))


async def due_checks(session: AsyncSession) -> list[Check]:
    """Return every check whose time has come."""
    now = datetime.now(UTC)
    result = await session.execute(select(Check).where(Check.enabled.is_(True)))

    due: list[Check] = []
    for check in result.scalars():
        if check.last_checked_at is None:
            due.append(check)
            continue
        if (now - check.last_checked_at).total_seconds() >= check.interval_seconds:
            due.append(check)
    return due

"""Taking error reports in and gathering them into issues."""

import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from grod.accounts.models import User
from grod.errors.models import KEY_PREFIX, Issue, Level, Report, Source

KEY_BYTES = 24
MAX_STACK_LENGTH = 100_000
MAX_MESSAGE_LENGTH = 1000
# How many lines of the stack decide that two reports are the same problem.
FINGERPRINT_LINES = 3
# What a line of a stack looks like when it names a place in the code;
# Python writes File "...", line N, and most other runtimes write "at ... (file:N)".
FRAME_MARKS = ('File "', " at ", "	at ", ".py:", ".js:", ".ts:")


class NameTakenError(Exception):
    """The account already has a source with that name."""


@dataclass(frozen=True)
class IssueCounts:
    """How much a source has to say."""

    issues: int
    unresolved: int
    reports: int


def _fingerprint(kind: str, stack: str) -> str:
    """What makes two reports the same problem.

    The kind of the error and the first lines of its stack; the message often
    carries changing values, so it stays out of this.
    """
    lines = [line.strip() for line in stack.splitlines() if line.strip()]
    marrow = "\n".join([kind, *lines[:FINGERPRINT_LINES]])
    return hashlib.sha256(marrow.encode()).hexdigest()


def _culprit(stack: str) -> str:
    """The place in the code a person looks at first.

    That is the deepest frame the stack names, not the last line: the last
    line usually only repeats the error itself.
    """
    lines = [line.strip() for line in stack.splitlines() if line.strip()]
    frames = [line for line in lines if any(mark in line for mark in FRAME_MARKS)]
    chosen = frames[-1] if frames else (lines[-1] if lines else "")
    return chosen[:MAX_MESSAGE_LENGTH]


async def find(session: AsyncSession, *, owner: User, name: str) -> Source | None:
    """Return one source of an account by name."""
    result = await session.execute(
        select(Source).where(Source.owner_id == owner.id, Source.name == name)
    )
    return result.scalar_one_or_none()


async def find_by_key(session: AsyncSession, key: str) -> Source | None:
    """Return the source a reporting key belongs to."""
    result = await session.execute(select(Source).where(Source.key == key))
    return result.scalar_one_or_none()


async def create(session: AsyncSession, *, owner: User, name: str) -> Source:
    """Start taking reports from an application."""
    source = Source(
        owner_id=owner.id, name=name, key=f"{KEY_PREFIX}_{secrets.token_urlsafe(KEY_BYTES)}"
    )
    session.add(source)
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise NameTakenError(name) from error
    return source


async def delete_source(session: AsyncSession, *, source: Source) -> None:
    """Stop taking reports and forget what came in."""
    await session.delete(source)
    await session.commit()


async def report(
    session: AsyncSession,
    *,
    source: Source,
    kind: str,
    message: str,
    stack: str = "",
    level: Level = Level.ERROR,
    environment: str = "",
    release: str = "",
    context: dict[str, Any] | None = None,
) -> Issue:
    """Take one report in and add it to the issue it belongs to."""
    now = datetime.now(UTC)
    fingerprint = _fingerprint(kind, stack)

    result = await session.execute(
        select(Issue).where(Issue.source_id == source.id, Issue.fingerprint == fingerprint)
    )
    issue = result.scalar_one_or_none()
    if issue is None:
        issue = Issue(
            source_id=source.id,
            fingerprint=fingerprint,
            kind=kind[:MAX_MESSAGE_LENGTH],
            message=message[:MAX_MESSAGE_LENGTH],
            level=level,
            culprit=_culprit(stack),
            count=0,
            first_seen_at=now,
            last_seen_at=now,
        )
        session.add(issue)
        await session.flush()

    issue.count += 1
    issue.last_seen_at = now
    issue.message = message[:MAX_MESSAGE_LENGTH]
    issue.level = level
    # A problem that comes back is open again, whatever anybody said before.
    issue.resolved = False

    session.add(
        Report(
            issue_id=issue.id,
            message=message[:MAX_MESSAGE_LENGTH],
            stack=stack[:MAX_STACK_LENGTH],
            environment=environment,
            release=release,
            context=json.dumps(context or {}),
        )
    )
    await session.commit()
    return issue


async def list_issues(
    session: AsyncSession, *, source: Source, resolved: bool | None = None, limit: int = 50
) -> list[Issue]:
    """Return the issues of a source, the freshest first."""
    query = select(Issue).where(Issue.source_id == source.id)
    if resolved is not None:
        query = query.where(Issue.resolved.is_(resolved))
    result = await session.execute(query.order_by(Issue.last_seen_at.desc()).limit(limit))
    return list(result.scalars())


async def find_issue(session: AsyncSession, *, source: Source, issue_id: str) -> Issue | None:
    """Return one issue of a source."""
    issue = await session.get(Issue, issue_id)
    if issue is None or issue.source_id != source.id:
        return None
    return issue


async def list_reports(session: AsyncSession, *, issue: Issue, limit: int = 20) -> list[Report]:
    """Return the single reports of an issue, newest first."""
    result = await session.execute(
        select(Report)
        .where(Report.issue_id == issue.id)
        .order_by(Report.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars())


async def set_resolved(session: AsyncSession, *, issue: Issue, resolved: bool) -> Issue:
    """Say an issue is dealt with, or open it again."""
    issue.resolved = resolved
    await session.commit()
    return issue


async def counts(session: AsyncSession, *, source: Source) -> IssueCounts:
    """How much a source has to say."""
    result = await session.execute(
        select(
            func.count(),
            func.count().filter(Issue.resolved.is_(False)),
            func.coalesce(func.sum(Issue.count), 0),
        ).where(Issue.source_id == source.id)
    )
    issues, unresolved, reports = result.one()
    return IssueCounts(issues=issues, unresolved=unresolved, reports=reports)

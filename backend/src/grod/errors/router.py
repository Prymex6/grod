"""Endpoints for what reports errors, and what those errors add up to."""

import json
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession

from grod.accounts.dependencies import CurrentUser
from grod.accounts.schemas import ApiModel
from grod.db import get_db_session
from grod.errors import service
from grod.errors.models import (
    ENVIRONMENT_MAX_LENGTH,
    KIND_MAX_LENGTH,
    MESSAGE_MAX_LENGTH,
    NAME_MAX_LENGTH,
    RELEASE_MAX_LENGTH,
    Issue,
    Level,
    Report,
    Source,
)
from grod.iam import scope
from grod.iam import service as iam
from grod.iam.dependencies import CurrentActor
from grod.iam.models import ResourceKind, Role

router = APIRouter(prefix="/errors", tags=["errors"])

DbSession = Annotated[AsyncSession, Depends(get_db_session)]

NOT_FOUND_DETAIL = "No such source"
ISSUE_NOT_FOUND_DETAIL = "No such issue"
MAX_ISSUES = 200
MAX_REPORTS = 100


class SourceCreate(ApiModel):
    """A new application that will report its errors."""

    name: str = Field(min_length=1, max_length=NAME_MAX_LENGTH)


class SourceView(ApiModel):
    """A source with the key it reports under."""

    id: str
    name: str
    key: str
    issues: int
    unresolved: int
    reports: int
    created_at: datetime


class IssueView(ApiModel):
    """One problem, with how often it has happened."""

    id: str
    kind: str
    message: str
    culprit: str
    level: Level
    count: int
    resolved: bool
    first_seen_at: datetime
    last_seen_at: datetime


class ReportView(ApiModel):
    """One error as it was reported."""

    message: str
    stack: str
    environment: str
    release: str
    context: dict[str, Any]
    created_at: datetime


class ReportIn(ApiModel):
    """What an application sends when something goes wrong."""

    kind: str = Field(min_length=1, max_length=KIND_MAX_LENGTH)
    message: str = Field(default="", max_length=MESSAGE_MAX_LENGTH)
    stack: str = Field(default="", max_length=service.MAX_STACK_LENGTH)
    level: Level = Level.ERROR
    environment: str = Field(default="", max_length=ENVIRONMENT_MAX_LENGTH)
    release: str = Field(default="", max_length=RELEASE_MAX_LENGTH)
    context: dict[str, Any] = Field(default_factory=dict)


class AcceptedView(ApiModel):
    """The answer an application gets for its report."""

    issue_id: str
    count: int


async def _source_view(db: AsyncSession, source: Source) -> SourceView:
    found = await service.counts(db, source=source)
    return SourceView(
        id=str(source.id),
        name=source.name,
        key=source.key,
        issues=found.issues,
        unresolved=found.unresolved,
        reports=found.reports,
        created_at=source.created_at,
    )


def _issue_view(issue: Issue) -> IssueView:
    return IssueView(
        id=str(issue.id),
        kind=issue.kind,
        message=issue.message,
        culprit=issue.culprit,
        level=issue.level,
        count=issue.count,
        resolved=issue.resolved,
        first_seen_at=issue.first_seen_at,
        last_seen_at=issue.last_seen_at,
    )


def _report_view(report: Report) -> ReportView:
    return ReportView(
        message=report.message,
        stack=report.stack,
        environment=report.environment,
        release=report.release,
        context=json.loads(report.context or "{}"),
        created_at=report.created_at,
    )


async def _allowed(db: AsyncSession, name: str, actor: iam.Actor, needed: Role) -> Source:
    """Find a source this actor may do that much with."""
    source = await scope.allowed(
        db,
        Source,
        actor=actor,
        kind=ResourceKind.ERROR_SOURCE,
        name=name,
        needed=needed,
        lowered=False,
    )
    if source is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL)
    return source


@router.get("/sources")
async def list_sources(db: DbSession, actor: CurrentActor) -> list[SourceView]:
    """Return what the caller may see reporting errors."""
    found = await scope.visible(db, Source, actor=actor, kind=ResourceKind.ERROR_SOURCE)
    return [await _source_view(db, source) for source in found]


@router.post("/sources", status_code=status.HTTP_201_CREATED)
async def create_source(body: SourceCreate, db: DbSession, user: CurrentUser) -> SourceView:
    """Start taking reports from an application."""
    try:
        source = await service.create(db, owner=user, name=body.name)
    except service.NameTakenError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="You already have a source with that name"
        ) from None
    return await _source_view(db, source)


@router.get("/sources/{name}")
async def read_source(name: str, db: DbSession, actor: CurrentActor) -> SourceView:
    """Return one source."""
    return await _source_view(db, await _allowed(db, name, actor, Role.VIEWER))


@router.delete("/sources/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source(name: str, db: DbSession, actor: CurrentActor) -> None:
    """Stop taking reports and forget what came in."""
    source = await _allowed(db, name, actor, Role.ADMIN)
    await service.delete_source(db, source=source)


@router.get("/sources/{name}/issues")
async def list_issues(
    name: str,
    db: DbSession,
    actor: CurrentActor,
    resolved: bool | None = None,
    limit: Annotated[int, Query(le=MAX_ISSUES)] = 50,
) -> list[IssueView]:
    """Return the problems of one source, the freshest first."""
    source = await _allowed(db, name, actor, Role.VIEWER)
    found = await service.list_issues(db, source=source, resolved=resolved, limit=limit)
    return [_issue_view(issue) for issue in found]


@router.get("/sources/{name}/issues/{issue_id}")
async def read_issue(name: str, issue_id: str, db: DbSession, actor: CurrentActor) -> IssueView:
    """Return one problem."""
    source = await _allowed(db, name, actor, Role.VIEWER)
    issue = await service.find_issue(db, source=source, issue_id=issue_id)
    if issue is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=ISSUE_NOT_FOUND_DETAIL)
    return _issue_view(issue)


@router.get("/sources/{name}/issues/{issue_id}/reports")
async def read_reports(
    name: str,
    issue_id: str,
    db: DbSession,
    actor: CurrentActor,
    limit: Annotated[int, Query(le=MAX_REPORTS)] = 20,
) -> list[ReportView]:
    """Return the single reports that make up a problem."""
    source = await _allowed(db, name, actor, Role.VIEWER)
    issue = await service.find_issue(db, source=source, issue_id=issue_id)
    if issue is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=ISSUE_NOT_FOUND_DETAIL)
    return [_report_view(report) for report in await service.list_reports(db, issue=issue)]


@router.post("/sources/{name}/issues/{issue_id}/resolve")
async def resolve_issue(
    name: str, issue_id: str, db: DbSession, actor: CurrentActor, resolved: bool = True
) -> IssueView:
    """Say a problem is dealt with, or open it again."""
    source = await _allowed(db, name, actor, Role.OPERATOR)
    issue = await service.find_issue(db, source=source, issue_id=issue_id)
    if issue is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=ISSUE_NOT_FOUND_DETAIL)
    return _issue_view(await service.set_resolved(db, issue=issue, resolved=resolved))


# Applications report under their own key, without an account of their own.
report_router = APIRouter(prefix="/report", tags=["errors"])


@report_router.post("", status_code=status.HTTP_202_ACCEPTED)
async def take_report(
    body: ReportIn,
    db: DbSession,
    x_grod_key: Annotated[str | None, Header()] = None,
) -> AcceptedView:
    """Take one error report from an application."""
    if x_grod_key is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="A reporting key is required")
    source = await service.find_by_key(db, x_grod_key)
    if source is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Unknown reporting key")

    issue = await service.report(
        db,
        source=source,
        kind=body.kind,
        message=body.message,
        stack=body.stack,
        level=body.level,
        environment=body.environment,
        release=body.release,
        context=body.context,
    )
    return AcceptedView(issue_id=str(issue.id), count=issue.count)

"""Endpoints for what a scan found in the code of a project."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from grod.accounts.dependencies import CurrentUser
from grod.accounts.schemas import ApiModel
from grod.collaboration.router import NOT_ALLOWED_DETAIL, readable
from grod.db import get_db_session
from grod.repositories import git
from grod.repositories.models import Project
from grod.scanning import rules, service
from grod.scanning.models import Finding, FindingState

router = APIRouter(prefix="/projects/{owner}/{slug}", tags=["scanning"])

DbSession = Annotated[AsyncSession, Depends(get_db_session)]

NOT_FOUND_DETAIL = "No such finding"


class FindingView(ApiModel):
    """One secret a scan saw, as the console shows it."""

    id: UUID
    rule: str
    # A rule that matches anything shaped like a password is worth having but
    # is wrong more often, so the console can say which findings to trust.
    certain: bool
    path: str
    line: int
    # The line with the secret starred out; the value itself is never kept.
    snippet: str
    commit: str
    state: FindingState
    created_at: datetime
    last_seen_at: datetime


class FindingUpdate(ApiModel):
    """What was decided about a finding."""

    state: FindingState


class ScanView(ApiModel):
    """What one scan changed."""

    commit: str
    files: int
    opened: int
    closed: int
    open_total: int


def _view(finding: Finding) -> FindingView:
    return FindingView(
        id=finding.id,
        rule=finding.rule,
        certain=rules.is_certain(finding.rule),
        path=finding.path,
        line=finding.line,
        snippet=finding.snippet,
        commit=finding.commit,
        state=finding.state,
        created_at=finding.created_at,
        last_seen_at=finding.last_seen_at,
    )


async def _writable(db: AsyncSession, owner: str, slug: str, user: CurrentUser) -> Project:
    """Findings say where a secret sits, so only the project side may read them.

    A public project is readable by everybody, but pointing strangers at the
    line with the password would be worse than saying nothing at all.
    """
    project, access = await readable(db, owner, slug, user)
    if not access.write:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=NOT_ALLOWED_DETAIL)
    return project


@router.get("/findings")
async def list_findings(
    owner: str, slug: str, db: DbSession, user: CurrentUser, state: FindingState | None = None
) -> list[FindingView]:
    """Return what the last scan of this project found."""
    project = await _writable(db, owner, slug, user)
    found = await service.list_findings(db, project=project, state=state)
    return [_view(finding) for finding in found]


@router.post("/findings/scan")
async def scan_now(owner: str, slug: str, db: DbSession, user: CurrentUser) -> ScanView:
    """Look through the default branch now instead of waiting for a push."""
    project = await _writable(db, owner, slug, user)
    try:
        result = await service.scan(db, project=project)
    except git.GitError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="There is nothing to look through yet"
        ) from None
    return ScanView(
        commit=result.commit,
        files=result.files,
        opened=result.opened,
        closed=result.closed,
        open_total=result.open_total,
    )


@router.patch("/findings/{finding_id}")
async def change_finding(
    owner: str,
    slug: str,
    finding_id: UUID,
    body: FindingUpdate,
    db: DbSession,
    user: CurrentUser,
) -> FindingView:
    """Say a finding is fine as it is, or put it back on the list."""
    project = await _writable(db, owner, slug, user)
    finding = await service.find(db, project=project, finding_id=finding_id)
    if finding is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL)
    return _view(await service.set_state(db, finding=finding, state=body.state))

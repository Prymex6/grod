"""Endpoints for project members, issues and their comments."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from grod.accounts import service as accounts
from grod.accounts.dependencies import CurrentUser, OptionalUser
from grod.accounts.models import User
from grod.collaboration import merge_queue, service
from grod.collaboration.models import Issue, IssueComment, IssueState
from grod.collaboration.schemas import (
    AuthorView,
    CommentCreate,
    CommentView,
    IssueCreate,
    IssueUpdate,
    IssueView,
    MemberCreate,
    MemberView,
    MergeRulesView,
    MergeRulesWrite,
    QueuePlaceView,
)
from grod.db import get_db_session
from grod.repositories import service as projects
from grod.repositories.models import Project

router = APIRouter(prefix="/projects/{owner}/{slug}", tags=["collaboration"])

DbSession = Annotated[AsyncSession, Depends(get_db_session)]

NOT_FOUND_DETAIL = "No such project"
ISSUE_NOT_FOUND_DETAIL = "No such issue"
NOT_ALLOWED_DETAIL = "You may not change this"


def _author(user: User) -> AuthorView:
    return AuthorView(login=user.login, display_name=user.display_name)


def _issue_view(issue: Issue, author: User) -> IssueView:
    return IssueView(
        id=issue.id,
        number=issue.number,
        title=issue.title,
        description=issue.description,
        state=issue.state,
        author=_author(author),
        created_at=issue.created_at,
        updated_at=issue.updated_at,
        closed_at=issue.closed_at,
    )


def _comment_view(comment: IssueComment, author: User) -> CommentView:
    return CommentView(
        id=comment.id,
        body=comment.body,
        author=_author(author),
        created_at=comment.created_at,
    )


async def readable(
    db: AsyncSession, owner: str, slug: str, user: User | None
) -> tuple[Project, projects.Access]:
    """Find a project the caller may read, together with their rights."""
    found = await projects.find(db, owner_login=owner, slug=slug)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL)

    access = await projects.access_of(db, project=found.project, user=user)
    if not access.read:
        # A project nobody may read must look exactly like a missing one.
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL)
    return found.project, access


async def _manageable(
    db: AsyncSession, owner: str, slug: str, user: User
) -> tuple[Project, projects.Access]:
    """Find a project whose settings the caller may change."""
    project, access = await readable(db, owner, slug, user)
    if not access.manage:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=NOT_ALLOWED_DETAIL)
    return project, access


@router.get("/members")
async def list_members(
    owner: str, slug: str, db: DbSession, user: OptionalUser
) -> list[MemberView]:
    """Return the members of a project."""
    project, _ = await readable(db, owner, slug, user)
    members = await projects.list_members(db, project=project)
    return [
        MemberView(
            login=account.login,
            display_name=account.display_name,
            role=member.role,
            created_at=member.created_at,
        )
        for member, account in members
    ]


@router.post("/members", status_code=status.HTTP_201_CREATED)
async def add_member(
    owner: str, slug: str, body: MemberCreate, db: DbSession, user: CurrentUser
) -> MemberView:
    """Add somebody to a project, or change the role they already have."""
    project, _ = await _manageable(db, owner, slug, user)

    account = await accounts.find_by_login(db, body.login)
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No such account")

    try:
        member = await projects.add_member(db, project=project, user=account, role=body.role)
    except projects.OwnerCannotBeMemberError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="The owner already has every right"
        ) from None

    return MemberView(
        login=account.login,
        display_name=account.display_name,
        role=member.role,
        created_at=member.created_at,
    )


@router.delete("/members/{login}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    owner: str, slug: str, login: str, db: DbSession, user: CurrentUser
) -> None:
    """Take somebody off a project."""
    project, _ = await _manageable(db, owner, slug, user)

    account = await accounts.find_by_login(db, login)
    if account is None or not await projects.remove_member(db, project=project, user=account):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No such member")


@router.get("/issues")
async def list_issues(
    owner: str,
    slug: str,
    db: DbSession,
    user: OptionalUser,
    state: IssueState | None = None,
) -> list[IssueView]:
    """Return the issues of a project, newest first."""
    project, _ = await readable(db, owner, slug, user)
    issues = await service.list_issues(db, project=project, state=state)
    return [_issue_view(item.issue, item.author) for item in issues]


@router.post("/issues", status_code=status.HTTP_201_CREATED)
async def open_issue(
    owner: str, slug: str, body: IssueCreate, db: DbSession, user: CurrentUser
) -> IssueView:
    """Open an issue. Anybody who may read the project may do that."""
    project, _ = await readable(db, owner, slug, user)
    issue = await service.open_issue(
        db, project=project, author=user, title=body.title, description=body.description
    )
    return _issue_view(issue, user)


async def _issue_or_404(db: AsyncSession, project: Project, number: int) -> service.IssueWithAuthor:
    found = await service.find_issue(db, project=project, number=number)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=ISSUE_NOT_FOUND_DETAIL)
    return found


@router.get("/issues/{number}")
async def read_issue(
    owner: str, slug: str, number: int, db: DbSession, user: OptionalUser
) -> IssueView:
    """Return one issue."""
    project, _ = await readable(db, owner, slug, user)
    found = await _issue_or_404(db, project, number)
    return _issue_view(found.issue, found.author)


@router.patch("/issues/{number}")
async def change_issue(
    owner: str,
    slug: str,
    number: int,
    body: IssueUpdate,
    db: DbSession,
    user: CurrentUser,
) -> IssueView:
    """Change the title, the description or the state of an issue."""
    project, access = await readable(db, owner, slug, user)
    found = await _issue_or_404(db, project, number)

    if not service.may_change(found.issue, user=user, manages_project=access.manage):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=NOT_ALLOWED_DETAIL)

    issue = await service.update_issue(
        db,
        issue=found.issue,
        title=body.title,
        description=body.description,
        state=body.state,
    )
    return _issue_view(issue, found.author)


@router.get("/issues/{number}/comments")
async def list_comments(
    owner: str, slug: str, number: int, db: DbSession, user: OptionalUser
) -> list[CommentView]:
    """Return the discussion under an issue."""
    project, _ = await readable(db, owner, slug, user)
    found = await _issue_or_404(db, project, number)
    comments = await service.list_comments(db, issue=found.issue)
    return [_comment_view(item.comment, item.author) for item in comments]


@router.post("/issues/{number}/comments", status_code=status.HTTP_201_CREATED)
async def add_comment(
    owner: str,
    slug: str,
    number: int,
    body: CommentCreate,
    db: DbSession,
    user: CurrentUser,
) -> CommentView:
    """Answer an issue."""
    project, _ = await readable(db, owner, slug, user)
    found = await _issue_or_404(db, project, number)
    comment = await service.add_comment(db, issue=found.issue, author=user, body=body.body)
    return _comment_view(comment, user)


@router.delete("/issues/{number}/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_comment(
    owner: str,
    slug: str,
    number: int,
    comment_id: UUID,
    db: DbSession,
    user: CurrentUser,
) -> None:
    """Remove a comment; its author or a maintainer may do that."""
    project, access = await readable(db, owner, slug, user)
    await _issue_or_404(db, project, number)

    try:
        removed = await service.delete_comment(
            db, comment_id=comment_id, user=user, manages_project=access.manage
        )
    except service.NotAllowedError:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=NOT_ALLOWED_DETAIL) from None
    if not removed:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No such comment")


@router.get("/merge-queue")
async def read_merge_queue(
    owner: str, slug: str, db: DbSession, user: OptionalUser
) -> list[QueuePlaceView]:
    """Everything standing in line to be merged, first to go first."""
    project, _ = await readable(db, owner, slug, user)
    places = await merge_queue.list_queue(db, project=project)
    return [
        QueuePlaceView(
            state=place.entry.state,
            position=place.position,
            tested_commit=place.entry.tested_commit,
            pipeline_id=place.entry.pipeline_id,
            last_error=place.entry.last_error,
            created_at=place.entry.created_at,
            number=place.merge_request.number,
            title=place.merge_request.title,
        )
        for place in places
    ]


@router.get("/merge-rules")
async def read_merge_rules(
    owner: str, slug: str, db: DbSession, user: OptionalUser
) -> MergeRulesView:
    """What has to be true before anything of this project may be merged."""
    project, _ = await readable(db, owner, slug, user)
    return MergeRulesView(
        required_approvals=project.required_approvals,
        required_checks=await merge_queue.required_checks(db, project=project),
    )


@router.put("/merge-rules")
async def write_merge_rules(
    owner: str, slug: str, body: MergeRulesWrite, db: DbSession, user: CurrentUser
) -> MergeRulesView:
    """Set the rules, replacing whatever was there."""
    project, access = await readable(db, owner, slug, user)
    if not access.manage:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=NOT_ALLOWED_DETAIL)

    project.required_approvals = body.required_approvals
    await db.commit()
    checks = await merge_queue.set_required_checks(db, project=project, names=body.required_checks)
    return MergeRulesView(required_approvals=project.required_approvals, required_checks=checks)

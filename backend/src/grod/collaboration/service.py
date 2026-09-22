"""Issues: opening them, answering them and closing them."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from grod.accounts.models import User
from grod.collaboration.models import Issue, IssueComment, IssueState
from grod.repositories.models import Project

FIRST_NUMBER = 1
NUMBER_ATTEMPTS = 5


class IssueNotFoundError(Exception):
    """No issue with that number in this project."""


class NotAllowedError(Exception):
    """The account may not change this issue."""


@dataclass(frozen=True)
class IssueWithAuthor:
    """An issue together with the account that opened it."""

    issue: Issue
    author: User


@dataclass(frozen=True)
class CommentWithAuthor:
    """A comment together with the account that wrote it."""

    comment: IssueComment
    author: User


async def _next_number(session: AsyncSession, project: Project) -> int:
    highest = await session.execute(
        select(func.max(Issue.number)).where(Issue.project_id == project.id)
    )
    return (highest.scalar() or 0) + FIRST_NUMBER


async def open_issue(
    session: AsyncSession, *, project: Project, author: User, title: str, description: str
) -> Issue:
    """Open an issue and give it the next free number in the project."""
    for _ in range(NUMBER_ATTEMPTS):
        issue = Issue(
            project_id=project.id,
            number=await _next_number(session, project),
            author_id=author.id,
            title=title,
            description=description,
        )
        session.add(issue)
        try:
            await session.commit()
        except IntegrityError:
            # Two issues opened at once can pick the same number; try again.
            await session.rollback()
            continue
        return issue
    raise IssueNotFoundError


async def find_issue(
    session: AsyncSession, *, project: Project, number: int
) -> IssueWithAuthor | None:
    """Return one issue of a project by its number."""
    result = await session.execute(
        select(Issue, User)
        .join(User, User.id == Issue.author_id)
        .where(Issue.project_id == project.id, Issue.number == number)
    )
    row = result.first()
    if row is None:
        return None
    issue, author = row
    return IssueWithAuthor(issue=issue, author=author)


async def list_issues(
    session: AsyncSession, *, project: Project, state: IssueState | None = None
) -> list[IssueWithAuthor]:
    """Return the issues of a project, newest first."""
    query = (
        select(Issue, User)
        .join(User, User.id == Issue.author_id)
        .where(Issue.project_id == project.id)
        .order_by(Issue.number.desc())
    )
    if state is not None:
        query = query.where(Issue.state == state)
    result = await session.execute(query)
    return [IssueWithAuthor(issue=issue, author=author) for issue, author in result.all()]


async def count_issues(session: AsyncSession, *, project: Project, state: IssueState) -> int:
    """Count the issues of a project in one state."""
    result = await session.execute(
        select(func.count())
        .select_from(Issue)
        .where(Issue.project_id == project.id, Issue.state == state)
    )
    return int(result.scalar() or 0)


def may_change(issue: Issue, *, user: User, manages_project: bool) -> bool:
    """The author and anyone who manages the project may change an issue."""
    return manages_project or issue.author_id == user.id


async def update_issue(
    session: AsyncSession,
    *,
    issue: Issue,
    title: str | None = None,
    description: str | None = None,
    state: IssueState | None = None,
) -> Issue:
    """Change the title, the description or the state of an issue."""
    if title is not None:
        issue.title = title
    if description is not None:
        issue.description = description
    if state is not None and state != issue.state:
        issue.state = state
        issue.closed_at = datetime.now(UTC) if state == IssueState.CLOSED else None
    issue.updated_at = datetime.now(UTC)
    await session.commit()
    return issue


async def add_comment(
    session: AsyncSession, *, issue: Issue, author: User, body: str
) -> IssueComment:
    """Add one entry to the discussion under an issue."""
    comment = IssueComment(issue_id=issue.id, author_id=author.id, body=body)
    session.add(comment)
    await session.commit()
    return comment


async def list_comments(session: AsyncSession, *, issue: Issue) -> list[CommentWithAuthor]:
    """Return the discussion under an issue, oldest first."""
    result = await session.execute(
        select(IssueComment, User)
        .join(User, User.id == IssueComment.author_id)
        .where(IssueComment.issue_id == issue.id)
        .order_by(IssueComment.created_at)
    )
    return [CommentWithAuthor(comment=comment, author=author) for comment, author in result.all()]


async def delete_comment(
    session: AsyncSession, *, comment_id: UUID, user: User, manages_project: bool
) -> bool:
    """Remove a comment; its author or a maintainer may do that."""
    comment = await session.get(IssueComment, comment_id)
    if comment is None:
        return False
    if not manages_project and comment.author_id != user.id:
        raise NotAllowedError
    await session.delete(comment)
    await session.commit()
    return True

"""Merge requests: asking for a branch to be merged, and doing it."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from grod.accounts.models import User
from grod.collaboration import stacks
from grod.collaboration.models import MergeRequest, MergeRequestComment, MergeState
from grod.repositories import git
from grod.repositories.models import Project

FIRST_NUMBER = 1
NUMBER_ATTEMPTS = 5
MAX_COMMITS = 100
MAX_FILES = 100


class SameBranchError(Exception):
    """A branch cannot be merged into itself."""


class BranchNotFoundError(Exception):
    """One of the two branches does not exist."""


class AlreadyClosedError(Exception):
    """The merge request is already merged or closed."""


class MergeConflictError(Exception):
    """Git could not merge the two branches on its own."""

    def __init__(self, conflicts: list[str]) -> None:
        super().__init__("merge conflict")
        self.conflicts = conflicts


@dataclass(frozen=True)
class MergeRequestWithAuthor:
    """A merge request together with the account that opened it."""

    merge_request: MergeRequest
    author: User


@dataclass(frozen=True)
class CommentWithAuthor:
    """One entry of the review discussion."""

    comment: MergeRequestComment
    author: User


async def _next_number(session: AsyncSession, project: Project) -> int:
    highest = await session.execute(
        select(func.max(MergeRequest.number)).where(MergeRequest.project_id == project.id)
    )
    return (highest.scalar() or 0) + FIRST_NUMBER


async def open_merge_request(
    session: AsyncSession,
    *,
    project: Project,
    author: User,
    title: str,
    description: str,
    source_branch: str,
    target_branch: str,
) -> MergeRequest:
    """Open a merge request between two branches of the project."""
    if source_branch == target_branch:
        raise SameBranchError

    for branch in (source_branch, target_branch):
        try:
            await git.resolve_ref(project.id, branch)
        except git.RefNotFoundError as error:
            raise BranchNotFoundError(branch) from error

    for _ in range(NUMBER_ATTEMPTS):
        merge_request = MergeRequest(
            project_id=project.id,
            number=await _next_number(session, project),
            author_id=author.id,
            title=title,
            description=description,
            source_branch=source_branch,
            target_branch=target_branch,
        )
        session.add(merge_request)
        try:
            await session.commit()
        except IntegrityError:
            # Two requests opened at once can pick the same number; try again.
            await session.rollback()
            continue
        return merge_request
    raise BranchNotFoundError(source_branch)


async def find(
    session: AsyncSession, *, project: Project, number: int
) -> MergeRequestWithAuthor | None:
    """Return one merge request of a project by its number."""
    result = await session.execute(
        select(MergeRequest, User)
        .join(User, User.id == MergeRequest.author_id)
        .where(MergeRequest.project_id == project.id, MergeRequest.number == number)
    )
    row = result.first()
    if row is None:
        return None
    merge_request, author = row
    return MergeRequestWithAuthor(merge_request=merge_request, author=author)


async def list_merge_requests(
    session: AsyncSession, *, project: Project, state: MergeState | None = None
) -> list[MergeRequestWithAuthor]:
    """Return the merge requests of a project, newest first."""
    query = (
        select(MergeRequest, User)
        .join(User, User.id == MergeRequest.author_id)
        .where(MergeRequest.project_id == project.id)
        .order_by(MergeRequest.number.desc())
    )
    if state is not None:
        query = query.where(MergeRequest.state == state)
    result = await session.execute(query)
    return [
        MergeRequestWithAuthor(merge_request=merge_request, author=author)
        for merge_request, author in result.all()
    ]


async def changes(
    session: AsyncSession, *, project: Project, merge_request: MergeRequest
) -> list[git.FileChange]:
    """Return the files the source branch changes."""
    del session
    return await git.diff(
        project.id,
        base=merge_request.target_branch,
        head=merge_request.source_branch,
        max_files=MAX_FILES,
    )


async def commits(
    session: AsyncSession, *, project: Project, merge_request: MergeRequest
) -> list[git.Commit]:
    """Return the commits the source branch adds."""
    del session
    return await git.commits_between(
        project.id,
        base=merge_request.target_branch,
        head=merge_request.source_branch,
        limit=MAX_COMMITS,
    )


async def merge(
    session: AsyncSession,
    *,
    project: Project,
    merge_request: MergeRequest,
    user: User,
) -> MergeRequest:
    """Merge the source branch into the target one and close the request."""
    if merge_request.state != MergeState.OPEN:
        raise AlreadyClosedError

    outcome = await git.merge_branches(
        project.id,
        target=merge_request.target_branch,
        source=merge_request.source_branch,
        message=f"Merge request !{merge_request.number}: {merge_request.title}",
        author_name=user.display_name,
        author_email=user.email,
    )
    if not outcome.merged:
        raise MergeConflictError(outcome.conflicts)

    merge_request.state = MergeState.MERGED
    merge_request.merge_commit = outcome.commit
    merge_request.merged_at = datetime.now(UTC)
    merge_request.updated_at = merge_request.merged_at
    await session.commit()

    # Whatever stood on this one now stands where this one went.
    await stacks.restack(session, project=project, merged=merge_request)
    return merge_request


async def close(session: AsyncSession, *, merge_request: MergeRequest) -> MergeRequest:
    """Close a merge request without merging it."""
    if merge_request.state != MergeState.OPEN:
        raise AlreadyClosedError
    merge_request.state = MergeState.CLOSED
    merge_request.closed_at = datetime.now(UTC)
    merge_request.updated_at = merge_request.closed_at
    await session.commit()
    return merge_request


async def reopen(session: AsyncSession, *, merge_request: MergeRequest) -> MergeRequest:
    """Reopen a merge request that was closed without merging."""
    if merge_request.state != MergeState.CLOSED:
        raise AlreadyClosedError
    merge_request.state = MergeState.OPEN
    merge_request.closed_at = None
    merge_request.updated_at = datetime.now(UTC)
    await session.commit()
    return merge_request


async def add_comment(
    session: AsyncSession,
    *,
    merge_request: MergeRequest,
    author: User,
    body: str,
    file_path: str | None = None,
    line_number: int | None = None,
) -> MergeRequestComment:
    """Add a review comment, either general or pinned to a line."""
    comment = MergeRequestComment(
        merge_request_id=merge_request.id,
        author_id=author.id,
        body=body,
        file_path=file_path,
        line_number=line_number,
    )
    session.add(comment)
    await session.commit()
    return comment


async def list_comments(
    session: AsyncSession, *, merge_request: MergeRequest
) -> list[CommentWithAuthor]:
    """Return the review discussion, oldest first."""
    result = await session.execute(
        select(MergeRequestComment, User)
        .join(User, User.id == MergeRequestComment.author_id)
        .where(MergeRequestComment.merge_request_id == merge_request.id)
        .order_by(MergeRequestComment.created_at)
    )
    return [CommentWithAuthor(comment=comment, author=author) for comment, author in result.all()]


async def delete_comment(
    session: AsyncSession, *, comment_id: UUID, user: User, manages_project: bool
) -> bool:
    """Remove a review comment; its author or a maintainer may do that."""
    comment = await session.get(MergeRequestComment, comment_id)
    if comment is None:
        return False
    if not manages_project and comment.author_id != user.id:
        return False
    await session.delete(comment)
    await session.commit()
    return True

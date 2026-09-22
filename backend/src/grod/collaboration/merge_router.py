"""Endpoints for merge requests: their diff, their review and the merge itself."""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from grod.accounts.dependencies import CurrentUser, OptionalUser
from grod.accounts.models import User
from grod.ci import findings
from grod.ci import service as pipelines
from grod.collaboration import approvals, merge_queue, merge_requests, stacks, suggestions
from grod.collaboration.models import (
    MergeQueueEntry,
    MergeRequest,
    MergeRequestComment,
    MergeState,
)
from grod.collaboration.router import NOT_ALLOWED_DETAIL, readable
from grod.collaboration.schemas import (
    ApprovalStateView,
    ApprovalView,
    AuthorView,
    FileChangeView,
    FindingView,
    MergeCommitView,
    MergeRequestCreate,
    MergeRequestView,
    QueueEntryView,
    ReviewCommentCreate,
    ReviewCommentView,
    StackStepView,
)
from grod.db import get_db_session
from grod.repositories import after_push, git, pushes
from grod.repositories.models import Project

router = APIRouter(prefix="/projects/{owner}/{slug}/merge-requests", tags=["merge requests"])

DbSession = Annotated[AsyncSession, Depends(get_db_session)]

NOT_FOUND_DETAIL = "No such merge request"
SHORT_HASH_LENGTH = 8


def _author(user: User) -> AuthorView:
    return AuthorView(login=user.login, display_name=user.display_name)


def _view(merge_request: MergeRequest, author: User) -> MergeRequestView:
    return MergeRequestView(
        id=merge_request.id,
        number=merge_request.number,
        title=merge_request.title,
        description=merge_request.description,
        state=merge_request.state,
        source_branch=merge_request.source_branch,
        target_branch=merge_request.target_branch,
        merge_commit=merge_request.merge_commit,
        author=_author(author),
        created_at=merge_request.created_at,
        updated_at=merge_request.updated_at,
        merged_at=merge_request.merged_at,
        closed_at=merge_request.closed_at,
    )


def _comment_view(comment: MergeRequestComment, author: User) -> ReviewCommentView:
    return ReviewCommentView(
        id=comment.id,
        body=comment.body,
        file_path=comment.file_path,
        line_number=comment.line_number,
        author=_author(author),
        created_at=comment.created_at,
    )


async def _found_or_404(
    db: AsyncSession, project: Project, number: int
) -> merge_requests.MergeRequestWithAuthor:
    found = await merge_requests.find(db, project=project, number=number)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL)
    return found


def _may_change(merge_request: MergeRequest, *, user: User, manages_project: bool) -> bool:
    """Its author may close or reopen it, and so may anybody running the project."""
    return manages_project or merge_request.author_id == user.id


@router.get("")
async def list_merge_requests(
    owner: str,
    slug: str,
    db: DbSession,
    user: OptionalUser,
    state: MergeState | None = None,
) -> list[MergeRequestView]:
    """Return the merge requests of a project, newest first."""
    project, _ = await readable(db, owner, slug, user)
    found = await merge_requests.list_merge_requests(db, project=project, state=state)
    return [_view(item.merge_request, item.author) for item in found]


@router.post("", status_code=status.HTTP_201_CREATED)
async def open_merge_request(
    owner: str, slug: str, body: MergeRequestCreate, db: DbSession, user: CurrentUser
) -> MergeRequestView:
    """Open a merge request. It takes the right to push, because merging writes."""
    project, access = await readable(db, owner, slug, user)
    if not access.write:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=NOT_ALLOWED_DETAIL)

    try:
        merge_request = await merge_requests.open_merge_request(
            db,
            project=project,
            author=user,
            title=body.title,
            description=body.description,
            source_branch=body.source_branch,
            target_branch=body.target_branch,
        )
    except merge_requests.SameBranchError:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail="A branch cannot be merged into itself"
        ) from None
    except merge_requests.BranchNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"No such branch: {error}") from None

    return _view(merge_request, user)


@router.get("/{number}")
async def read_merge_request(
    owner: str, slug: str, number: int, db: DbSession, user: OptionalUser
) -> MergeRequestView:
    """Return one merge request."""
    project, _ = await readable(db, owner, slug, user)
    found = await _found_or_404(db, project, number)
    return _view(found.merge_request, found.author)


@router.get("/{number}/changes")
async def read_changes(
    owner: str, slug: str, number: int, db: DbSession, user: OptionalUser
) -> list[FileChangeView]:
    """Return the files the merge request changes, with their patches."""
    project, _ = await readable(db, owner, slug, user)
    found = await _found_or_404(db, project, number)
    try:
        changes = await merge_requests.changes(
            db, project=project, merge_request=found.merge_request
        )
    except git.RefNotFoundError:
        # A branch can disappear after the request was opened.
        return []
    return [
        FileChangeView(
            path=change.path,
            additions=change.additions,
            deletions=change.deletions,
            binary=change.binary,
            patch=change.patch,
        )
        for change in changes
    ]


@router.get("/{number}/commits")
async def read_commits(
    owner: str, slug: str, number: int, db: DbSession, user: OptionalUser
) -> list[MergeCommitView]:
    """Return the commits the merge request would bring in."""
    project, _ = await readable(db, owner, slug, user)
    found = await _found_or_404(db, project, number)
    try:
        commits = await merge_requests.commits(
            db, project=project, merge_request=found.merge_request
        )
    except git.RefNotFoundError:
        return []
    return [
        MergeCommitView(
            hash=commit.hash,
            short_hash=commit.hash[:SHORT_HASH_LENGTH],
            subject=commit.subject,
            author_name=commit.author_name,
            authored_at=commit.authored_at,
        )
        for commit in commits
    ]


@router.post("/{number}/merge")
async def merge(
    owner: str, slug: str, number: int, db: DbSession, user: CurrentUser
) -> MergeRequestView:
    """Merge the source branch into the target one. It takes the right to push."""
    project, access = await readable(db, owner, slug, user)
    if not access.write:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=NOT_ALLOWED_DETAIL)

    found = await _found_or_404(db, project, number)
    state = await approvals.state_of(db, project=project, merge_request=found.merge_request)
    if not state.satisfied:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "message": "This request does not have the approvals it needs",
                "required": state.required,
                "counted": state.counted,
                "missingOwners": state.missing_owners,
            },
        )

    try:
        merged = await merge_requests.merge(
            db, project=project, merge_request=found.merge_request, user=user
        )
    except merge_requests.AlreadyClosedError:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Already merged or closed") from None
    except merge_requests.MergeConflictError as error:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"message": "The branches conflict", "conflicts": error.conflicts},
        ) from None
    except git.RefNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="A branch is gone") from None

    return _view(merged, found.author)


@router.post("/{number}/close")
async def close(
    owner: str, slug: str, number: int, db: DbSession, user: CurrentUser
) -> MergeRequestView:
    """Close a merge request without merging it."""
    project, access = await readable(db, owner, slug, user)
    found = await _found_or_404(db, project, number)
    if not _may_change(found.merge_request, user=user, manages_project=access.manage):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=NOT_ALLOWED_DETAIL)

    try:
        closed = await merge_requests.close(db, merge_request=found.merge_request)
    except merge_requests.AlreadyClosedError:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Already merged or closed") from None
    return _view(closed, found.author)


@router.post("/{number}/reopen")
async def reopen(
    owner: str, slug: str, number: int, db: DbSession, user: CurrentUser
) -> MergeRequestView:
    """Reopen a merge request that was closed without merging."""
    project, access = await readable(db, owner, slug, user)
    found = await _found_or_404(db, project, number)
    if not _may_change(found.merge_request, user=user, manages_project=access.manage):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=NOT_ALLOWED_DETAIL)

    try:
        reopened = await merge_requests.reopen(db, merge_request=found.merge_request)
    except merge_requests.AlreadyClosedError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="A merged request stays merged"
        ) from None
    return _view(reopened, found.author)


@router.get("/{number}/comments")
async def list_comments(
    owner: str, slug: str, number: int, db: DbSession, user: OptionalUser
) -> list[ReviewCommentView]:
    """Return the review discussion."""
    project, _ = await readable(db, owner, slug, user)
    found = await _found_or_404(db, project, number)
    comments = await merge_requests.list_comments(db, merge_request=found.merge_request)
    return [_comment_view(item.comment, item.author) for item in comments]


@router.post("/{number}/comments", status_code=status.HTTP_201_CREATED)
async def add_comment(
    owner: str,
    slug: str,
    number: int,
    body: ReviewCommentCreate,
    db: DbSession,
    user: CurrentUser,
) -> ReviewCommentView:
    """Review a merge request, either in general or on one line of one file."""
    project, _ = await readable(db, owner, slug, user)
    found = await _found_or_404(db, project, number)
    comment = await merge_requests.add_comment(
        db,
        merge_request=found.merge_request,
        author=user,
        body=body.body,
        file_path=body.file_path,
        line_number=body.line_number,
    )
    return _comment_view(comment, user)


@router.delete("/{number}/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_comment(
    owner: str,
    slug: str,
    number: int,
    comment_id: UUID,
    db: DbSession,
    user: CurrentUser,
) -> None:
    """Remove a review comment; its author or a maintainer may do that."""
    project, access = await readable(db, owner, slug, user)
    await _found_or_404(db, project, number)

    removed = await merge_requests.delete_comment(
        db, comment_id=comment_id, user=user, manages_project=access.manage
    )
    if not removed:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No such comment")


def _entry_view(entry: MergeQueueEntry, *, position: int = 0) -> QueueEntryView:
    return QueueEntryView(
        state=entry.state,
        position=position,
        tested_commit=entry.tested_commit,
        pipeline_id=entry.pipeline_id,
        last_error=entry.last_error,
        created_at=entry.created_at,
    )


@router.post("/{number}/queue", status_code=status.HTTP_201_CREATED)
async def enter_queue(
    owner: str, slug: str, number: int, db: DbSession, user: CurrentUser
) -> QueueEntryView:
    """Stand in line to be merged once the merge result passes its tests."""
    project, access = await readable(db, owner, slug, user)
    if not access.write:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=NOT_ALLOWED_DETAIL)

    found = await _found_or_404(db, project, number)
    try:
        entry = await merge_queue.enter(
            db, project=project, merge_request=found.merge_request, user=user
        )
    except merge_queue.NotOpenError:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Already merged or closed") from None
    except merge_queue.AlreadyQueuedError:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Already in the queue") from None
    return _entry_view(entry)


@router.get("/{number}/queue")
async def read_queue_place(
    owner: str, slug: str, number: int, db: DbSession, user: OptionalUser
) -> QueueEntryView | None:
    """Where this merge request stands in line, or nothing when it does not."""
    project, _ = await readable(db, owner, slug, user)
    found = await _found_or_404(db, project, number)
    entry = await merge_queue.find_entry(db, merge_request=found.merge_request)
    if entry is None:
        return None

    places = await merge_queue.list_queue(db, project=project)
    position = next((place.position for place in places if place.entry.id == entry.id), 0)
    return _entry_view(entry, position=position)


@router.delete("/{number}/queue", status_code=status.HTTP_204_NO_CONTENT)
async def leave_queue(owner: str, slug: str, number: int, db: DbSession, user: CurrentUser) -> None:
    """Step out of the line."""
    project, access = await readable(db, owner, slug, user)
    if not access.write:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=NOT_ALLOWED_DETAIL)

    found = await _found_or_404(db, project, number)
    entry = await merge_queue.find_entry(db, merge_request=found.merge_request)
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Not in the queue")
    await merge_queue.leave(db, project=project, entry=entry, merge_request=found.merge_request)


def _state_view(state: approvals.ApprovalState) -> ApprovalStateView:
    return ApprovalStateView(
        given=[
            ApprovalView(
                login=given.login,
                display_name=given.display_name,
                commit=given.commit,
                stale=given.stale,
            )
            for given in state.given
        ],
        required=state.required,
        counted=state.counted,
        missing_owners=state.missing_owners,
        satisfied=state.satisfied,
    )


@router.get("/{number}/approvals")
async def read_approvals(
    owner: str, slug: str, number: int, db: DbSession, user: OptionalUser
) -> ApprovalStateView:
    """Who said yes, and whether that is enough to let the change in."""
    project, _ = await readable(db, owner, slug, user)
    found = await _found_or_404(db, project, number)
    state = await approvals.state_of(db, project=project, merge_request=found.merge_request)
    return _state_view(state)


@router.post("/{number}/approve", status_code=status.HTTP_201_CREATED)
async def approve(
    owner: str, slug: str, number: int, db: DbSession, user: CurrentUser
) -> ApprovalStateView:
    """Say the change may go in, as it stands now."""
    project, access = await readable(db, owner, slug, user)
    # Reading the project is enough to review it; pushing is a separate right.
    del access
    found = await _found_or_404(db, project, number)

    try:
        tip = await git.resolve_ref(project.id, found.merge_request.source_branch)
    except git.RefNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="A branch is gone") from None

    try:
        await approvals.approve(db, merge_request=found.merge_request, user=user, commit=tip)
    except approvals.OwnApprovalError:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail="You cannot approve your own request"
        ) from None
    except approvals.AlreadyApprovedError:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Already approved") from None

    state = await approvals.state_of(db, project=project, merge_request=found.merge_request)
    return _state_view(state)


@router.delete("/{number}/approve")
async def revoke_approval(
    owner: str, slug: str, number: int, db: DbSession, user: CurrentUser
) -> ApprovalStateView:
    """Take back a yes."""
    project, _ = await readable(db, owner, slug, user)
    found = await _found_or_404(db, project, number)
    if not await approvals.revoke(db, merge_request=found.merge_request, user=user):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="You have not approved this")

    state = await approvals.state_of(db, project=project, merge_request=found.merge_request)
    return _state_view(state)


@router.get("/{number}/findings")
async def read_findings(
    owner: str, slug: str, number: int, db: DbSession, user: OptionalUser
) -> list[FindingView]:
    """What the tools said about the lines of this change.

    The remarks come from the last run of the source branch, so they follow
    the code: a new push replaces them with what the tools say now.
    """
    project, _ = await readable(db, owner, slug, user)
    found = await _found_or_404(db, project, number)

    pipeline = await pipelines.newest_for_ref(
        db, project=project, ref=found.merge_request.source_branch
    )
    if pipeline is None:
        return []

    jobs = await pipelines.list_jobs(db, pipeline=pipeline)
    remarks = await findings.list_for_jobs(db, job_ids=[job.id for job in jobs])
    return [
        FindingView(
            path=remark.path,
            line=remark.line,
            column=remark.column,
            tool=remark.tool,
            message=remark.message,
        )
        for remark in remarks
    ]


@router.post("/{number}/comments/{comment_id}/apply")
async def apply_suggestion(
    owner: str, slug: str, number: int, comment_id: UUID, db: DbSession, user: CurrentUser
) -> MergeCommitView:
    """Write a suggestion from a review into the branch, as a commit."""
    project, access = await readable(db, owner, slug, user)
    if not access.write:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=NOT_ALLOWED_DETAIL)

    found = await _found_or_404(db, project, number)
    comment = await db.get(MergeRequestComment, comment_id)
    if comment is None or comment.merge_request_id != found.merge_request.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No such comment")

    before = await pushes.branch_tips(project)
    try:
        commit = await suggestions.apply(
            db,
            project=project,
            merge_request=found.merge_request,
            comment=comment,
            user=user,
        )
    except suggestions.NoSuggestionError:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="This comment carries no suggestion"
        ) from None
    except suggestions.NotOnALineError:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="This comment is not about a line"
        ) from None
    except suggestions.LineIsGoneError, git.PathNotFoundError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="The file has changed since the suggestion"
        ) from None
    except git.StaleBranchError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="Somebody changed this branch in the meantime"
        ) from None
    except git.RefNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="A branch is gone") from None

    await after_push.handle(db, project=project, before=before, pusher=user)
    return MergeCommitView(
        hash=commit,
        short_hash=commit[:SHORT_HASH_LENGTH],
        author_name=user.display_name,
        authored_at=datetime.now(UTC),
        subject=f"Apply suggestion to {comment.file_path}:{comment.line_number}",
    )


@router.get("/{number}/stack")
async def read_stack(
    owner: str, slug: str, number: int, db: DbSession, user: OptionalUser
) -> list[StackStepView]:
    """The whole stack this request belongs to, the one that goes in first at the top.

    Nothing declares a stack: a request whose target is another request's
    source stands on it, so the stack is read off the branches themselves.
    """
    project, _ = await readable(db, owner, slug, user)
    found = await _found_or_404(db, project, number)
    steps = await stacks.stack_of(db, project=project, merge_request=found.merge_request)

    # One alone is not a stack, and saying so would only add noise.
    if len(steps) < 2:
        return []
    return [
        StackStepView(
            number=step.merge_request.number,
            title=step.merge_request.title,
            state=step.merge_request.state,
            source_branch=step.merge_request.source_branch,
            target_branch=step.merge_request.target_branch,
            position=step.position,
        )
        for step in steps
    ]

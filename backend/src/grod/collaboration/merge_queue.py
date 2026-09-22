"""The line merge requests stand in before they are allowed into a branch.

A change that passes on its own can still break the branch it has not seen, so
what the queue tests is the **result** of merging: the merge commit is built
first, tested on a throwaway branch, and only a green run lets the target move
onto it. If the target moved in the meantime, the result is stale and the whole
thing is built again.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grod.accounts.models import User
from grod.ci import service as pipelines
from grod.ci.models import FINISHED_STATES, Job, Pipeline, RunState
from grod.collaboration import approvals, stacks
from grod.collaboration.models import (
    QUEUE_BRANCH_PREFIX,
    MergeQueueEntry,
    MergeRequest,
    MergeState,
    QueueState,
    RequiredCheck,
)
from grod.repositories import after_push, git, pushes
from grod.repositories.models import Project

logger = logging.getLogger(__name__)

ACTIVE_STATES = (QueueState.WAITING, QueueState.TESTING)
MAX_ERROR_LENGTH = 2000


class NotOpenError(Exception):
    """A merge request that is already closed cannot stand in line."""


class AlreadyQueuedError(Exception):
    """This merge request is in the queue already."""


@dataclass(frozen=True)
class QueuePlace:
    """One entry together with where it stands."""

    entry: MergeQueueEntry
    merge_request: MergeRequest
    position: int


def branch_of(merge_request: MergeRequest) -> str:
    """The throwaway branch the merge result is tested on."""
    return f"{QUEUE_BRANCH_PREFIX}/mr-{merge_request.number}"


async def find_entry(
    session: AsyncSession, *, merge_request: MergeRequest
) -> MergeQueueEntry | None:
    """The place a merge request holds in line, if it holds one."""
    result = await session.execute(
        select(MergeQueueEntry).where(
            MergeQueueEntry.merge_request_id == merge_request.id,
            MergeQueueEntry.state.in_(ACTIVE_STATES),
        )
    )
    return result.scalar_one_or_none()


async def list_queue(session: AsyncSession, *, project: Project) -> list[QueuePlace]:
    """Everything standing in line for one project, first to go first."""
    result = await session.execute(
        select(MergeQueueEntry, MergeRequest)
        .join(MergeRequest, MergeRequest.id == MergeQueueEntry.merge_request_id)
        .where(
            MergeQueueEntry.project_id == project.id,
            MergeQueueEntry.state.in_(ACTIVE_STATES),
        )
        .order_by(MergeQueueEntry.created_at)
    )
    return [
        QueuePlace(entry=entry, merge_request=merge_request, position=index)
        for index, (entry, merge_request) in enumerate(result, start=1)
    ]


async def enter(
    session: AsyncSession, *, project: Project, merge_request: MergeRequest, user: User
) -> MergeQueueEntry:
    """Put a merge request in line."""
    if merge_request.state != MergeState.OPEN:
        raise NotOpenError
    if await find_entry(session, merge_request=merge_request) is not None:
        raise AlreadyQueuedError

    entry = MergeQueueEntry(
        project_id=project.id,
        merge_request_id=merge_request.id,
        requested_by_id=user.id,
        state=QueueState.WAITING,
    )
    session.add(entry)
    await session.commit()
    return entry


async def leave(
    session: AsyncSession, *, project: Project, entry: MergeQueueEntry, merge_request: MergeRequest
) -> MergeQueueEntry:
    """Take a merge request out of the line."""
    entry.state = QueueState.CANCELLED
    await session.commit()
    await _forget_branch(project, merge_request)
    return entry


async def required_checks(session: AsyncSession, *, project: Project) -> list[str]:
    """The jobs that have to pass before anything of this project is merged."""
    result = await session.execute(
        select(RequiredCheck.job_name)
        .where(RequiredCheck.project_id == project.id)
        .order_by(RequiredCheck.job_name)
    )
    return list(result.scalars())


async def set_required_checks(
    session: AsyncSession, *, project: Project, names: list[str]
) -> list[str]:
    """Write down which jobs are required, replacing whatever was there."""
    result = await session.execute(
        select(RequiredCheck).where(RequiredCheck.project_id == project.id)
    )
    for existing in result.scalars():
        await session.delete(existing)

    wanted = sorted({name.strip() for name in names if name.strip()})
    session.add_all(RequiredCheck(project_id=project.id, job_name=name) for name in wanted)
    await session.commit()
    return wanted


async def advance(session: AsyncSession) -> None:
    """Move every queue one step. Called by the loop, and by the tests."""
    result = await session.execute(
        select(MergeQueueEntry)
        .where(MergeQueueEntry.state.in_(ACTIVE_STATES))
        .order_by(MergeQueueEntry.created_at)
    )

    seen: set[UUID] = set()
    for entry in result.scalars():
        # Only the first of each project moves; the rest wait their turn.
        if entry.project_id in seen:
            continue
        seen.add(entry.project_id)
        try:
            await _step(session, entry)
        except Exception:
            # One stuck queue must never stop the others.
            logger.exception("The queue of project %s stumbled", entry.project_id)
            await session.rollback()


async def _step(session: AsyncSession, entry: MergeQueueEntry) -> None:
    """Take one entry as far as it can go right now."""
    project = await session.get(Project, entry.project_id)
    merge_request = await session.get(MergeRequest, entry.merge_request_id)
    if project is None or merge_request is None:
        entry.state = QueueState.CANCELLED
        await session.commit()
        return

    if merge_request.state != MergeState.OPEN:
        await _give_up(session, project, entry, merge_request, "The request was closed")
        return

    # Nothing is worth testing that could not be merged anyway.
    state = await approvals.state_of(session, project=project, merge_request=merge_request)
    if not state.satisfied:
        await _give_up(session, project, entry, merge_request, _why_not_approved(state))
        return

    if entry.state == QueueState.WAITING:
        await _start_testing(session, project, entry, merge_request)
    else:
        await _look_at_the_run(session, project, entry, merge_request)


async def _start_testing(
    session: AsyncSession,
    project: Project,
    entry: MergeQueueEntry,
    merge_request: MergeRequest,
) -> None:
    """Build the merge result and set a pipeline running on it."""
    author = await session.get(User, entry.requested_by_id)
    if author is None:
        await _give_up(session, project, entry, merge_request, "The account is gone")
        return

    try:
        outcome = await git.merge_preview(
            project.id,
            target=merge_request.target_branch,
            source=merge_request.source_branch,
            message=f"Merge request !{merge_request.number}: {merge_request.title}",
            author_name=author.display_name,
            author_email=author.email,
        )
    except (git.RefNotFoundError, git.GitError) as error:
        await _give_up(session, project, entry, merge_request, str(error))
        return

    if not outcome.merged or outcome.commit is None:
        await _give_up(
            session,
            project,
            entry,
            merge_request,
            "The branches clash: " + ", ".join(outcome.conflicts),
        )
        return

    branch = branch_of(merge_request)
    await git.point_branch(project.id, branch=branch, commit=outcome.commit)

    try:
        started = await pipelines.start(
            session,
            project=project,
            ref=branch,
            commit=outcome.commit,
            triggered_by=author,
        )
    except pipelines.NoConfigError:
        # Nothing to test, so there is nothing to wait for.
        await _merge_it(session, project, entry, merge_request, outcome.commit, outcome.base)
        return

    entry.state = QueueState.TESTING
    entry.tested_commit = outcome.commit
    entry.base_commit = outcome.base
    entry.pipeline_id = started.pipeline.id
    await session.commit()


async def _look_at_the_run(
    session: AsyncSession,
    project: Project,
    entry: MergeQueueEntry,
    merge_request: MergeRequest,
) -> None:
    """Decide what the finished pipeline means for this entry."""
    pipeline = await session.get(Pipeline, entry.pipeline_id) if entry.pipeline_id else None
    if pipeline is None:
        await _give_up(session, project, entry, merge_request, "The run is gone")
        return
    if pipeline.state not in FINISHED_STATES:
        return

    if pipeline.state != RunState.SUCCESS:
        await _give_up(session, project, entry, merge_request, "The tests did not pass")
        return

    missing = await _missing_checks(session, project=project, pipeline=pipeline)
    if missing:
        await _give_up(
            session, project, entry, merge_request, "Missing checks: " + ", ".join(missing)
        )
        return

    tip = await _tip_of(project, merge_request.target_branch)
    if tip != entry.base_commit:
        # Somebody else got in first, so what was tested is not what would be
        # merged now. Back in line, to be built again on the new tip.
        entry.state = QueueState.WAITING
        entry.pipeline_id = None
        await session.commit()
        await _forget_branch(project, merge_request)
        return

    await _merge_it(session, project, entry, merge_request, entry.tested_commit, entry.base_commit)


async def _missing_checks(
    session: AsyncSession, *, project: Project, pipeline: Pipeline
) -> list[str]:
    """Required jobs the run does not report as passed."""
    wanted = set(await required_checks(session, project=project))
    if not wanted:
        return []

    result = await session.execute(
        select(Job.name).where(Job.pipeline_id == pipeline.id, Job.state == RunState.SUCCESS)
    )
    return sorted(wanted - set(result.scalars()))


async def _merge_it(
    session: AsyncSession,
    project: Project,
    entry: MergeQueueEntry,
    merge_request: MergeRequest,
    commit: str,
    base: str,
) -> None:
    """Move the target branch onto the tested commit and close the request."""
    before = await pushes.branch_tips(project)
    try:
        await git.point_branch(
            project.id, branch=merge_request.target_branch, commit=commit, expected=base or None
        )
    except git.GitError as error:
        # The branch moved between the look and the move; try again next tick.
        entry.state = QueueState.WAITING
        entry.pipeline_id = None
        entry.last_error = str(error)[:MAX_ERROR_LENGTH]
        await session.commit()
        return

    merge_request.state = MergeState.MERGED
    merge_request.merge_commit = commit
    merge_request.merged_at = datetime.now(UTC)
    merge_request.updated_at = merge_request.merged_at
    entry.state = QueueState.MERGED
    entry.tested_commit = commit
    await session.commit()

    await _forget_branch(project, merge_request)
    # Whatever stood on this one now stands where this one went.
    await stacks.restack(session, project=project, merged=merge_request)

    author = await session.get(User, entry.requested_by_id)
    await after_push.handle(session, project=project, before=before, pusher=author)


async def _give_up(
    session: AsyncSession,
    project: Project,
    entry: MergeQueueEntry,
    merge_request: MergeRequest,
    why: str,
) -> None:
    """Take an entry out of the line and say what went wrong."""
    entry.state = QueueState.FAILED
    entry.last_error = why[:MAX_ERROR_LENGTH]
    await session.commit()
    await _forget_branch(project, merge_request)


async def _tip_of(project: Project, branch: str) -> str:
    """Where a branch stands, or an empty string when it is gone."""
    try:
        return await git.resolve_ref(project.id, branch)
    except git.RefNotFoundError, git.GitError:
        return ""


async def _forget_branch(project: Project, merge_request: MergeRequest) -> None:
    """Remove the throwaway branch, if it is still there."""
    try:
        await git.delete_branch(project.id, branch_of(merge_request))
    except git.GitError:
        return


def _why_not_approved(state: approvals.ApprovalState) -> str:
    """Say in one line what the request is still waiting for."""
    if state.missing_owners:
        return "Waiting for an owner: " + ", ".join(state.missing_owners)
    return f"Waiting for approvals: {state.counted} of {state.required}"

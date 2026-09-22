"""Merge requests standing one on another, and what happens when one goes in.

A stack is not a new kind of thing here: a request whose target is another
request's source **is** the one above it. So nothing has to be declared — the
platform reads the stack off the branches that are already there.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grod.collaboration.models import MergeRequest, MergeState
from grod.repositories.models import Project

# A stack deeper than this is a mistake or a loop, not a way of working.
MAX_DEPTH = 20


@dataclass(frozen=True)
class Step:
    """One request of a stack, and where it stands in it."""

    merge_request: MergeRequest
    # 1 is the bottom of the stack: the one that goes in first.
    position: int


async def _open_with_source(
    session: AsyncSession, *, project: Project, branch: str
) -> MergeRequest | None:
    """The open request that would put this branch somewhere."""
    result = await session.execute(
        select(MergeRequest).where(
            MergeRequest.project_id == project.id,
            MergeRequest.source_branch == branch,
            MergeRequest.state == MergeState.OPEN,
        )
    )
    return result.scalars().first()


async def _open_with_target(
    session: AsyncSession, *, project: Project, branch: str
) -> list[MergeRequest]:
    """The open requests standing on this branch."""
    result = await session.execute(
        select(MergeRequest)
        .where(
            MergeRequest.project_id == project.id,
            MergeRequest.target_branch == branch,
            MergeRequest.state == MergeState.OPEN,
        )
        .order_by(MergeRequest.number)
    )
    return list(result.scalars())


async def parent_of(
    session: AsyncSession, *, project: Project, merge_request: MergeRequest
) -> MergeRequest | None:
    """The request this one stands on, if it stands on one."""
    return await _open_with_source(session, project=project, branch=merge_request.target_branch)


async def children_of(
    session: AsyncSession, *, project: Project, merge_request: MergeRequest
) -> list[MergeRequest]:
    """The requests standing on this one."""
    return await _open_with_target(session, project=project, branch=merge_request.source_branch)


async def stack_of(
    session: AsyncSession, *, project: Project, merge_request: MergeRequest
) -> list[Step]:
    """The whole stack one request belongs to, bottom first.

    Only one way up is followed: where two requests stand on the same branch
    the stack forks, and a fork is not a stack any more.
    """
    below: list[MergeRequest] = []
    walker = merge_request
    seen = {merge_request.id}
    for _ in range(MAX_DEPTH):
        parent = await parent_of(session, project=project, merge_request=walker)
        if parent is None or parent.id in seen:
            break
        below.append(parent)
        seen.add(parent.id)
        walker = parent

    above: list[MergeRequest] = []
    walker = merge_request
    for _ in range(MAX_DEPTH):
        children = await children_of(session, project=project, merge_request=walker)
        if len(children) != 1:
            break
        child = children[0]
        if child.id in seen:
            break
        above.append(child)
        seen.add(child.id)
        walker = child

    ordered = [*reversed(below), merge_request, *above]
    return [Step(merge_request=item, position=index) for index, item in enumerate(ordered, start=1)]


async def restack(
    session: AsyncSession, *, project: Project, merged: MergeRequest
) -> list[MergeRequest]:
    """Point whatever stood on a merged request at where it went instead.

    No history is rewritten. The branch above already holds the commits of the
    one below, and the target now holds them too, so the difference left over
    is exactly the work of the branch above — which is what should be reviewed.
    """
    moved: list[MergeRequest] = []
    for child in await children_of(session, project=project, merge_request=merged):
        child.target_branch = merged.target_branch
        moved.append(child)

    if moved:
        await session.commit()
    return moved

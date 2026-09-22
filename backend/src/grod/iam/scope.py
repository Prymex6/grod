"""Finding the cloud resources a caller may reach, whatever module they sit in.

Applications, functions, databases and the rest all keep the same two columns — who owns the
row and what it is called — so the lookup is written once here instead of nine
times, and every router only says which table and which role it means.
"""

from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from grod.db import TimestampedTable
from grod.iam import service
from grod.iam.models import ResourceKind, Role, SubjectKind


def _reach(
    table: Any,  # noqa: ANN401  (any of the cloud tables)
    *,
    actor: service.Actor,
    shared: set[UUID],
) -> ColumnElement[bool] | None:
    """The rows this actor could possibly reach, or None when there are none.

    A person reaches their own rows and whatever was shared with them. A machine
    identity is left with the grants alone: owning the machine is not the same
    as owning what the machine was allowed to touch.
    """
    parts: list[ColumnElement[bool]] = []
    if actor.kind == SubjectKind.USER:
        parts.append(table.owner_id == actor.owner_id)
    if shared:
        parts.append(table.id.in_(shared))
    if not parts:
        return None
    return or_(*parts)


async def visible[T: TimestampedTable](
    session: AsyncSession, model: type[T], *, actor: service.Actor, kind: ResourceKind
) -> list[T]:
    """Return the rows of one table the actor may see, newest first."""
    # The cloud tables share these columns but no common class, so the mapping
    # to them is loose on purpose, the way it is in the IAM router.
    table: Any = model
    shared = await service.readable_ids(session, actor=actor, kind=kind)
    reach = _reach(table, actor=actor, shared=shared)
    if reach is None:
        return []
    result = await session.execute(select(model).where(reach).order_by(table.created_at.desc()))
    return list(result.scalars())


async def allowed[T: TimestampedTable](
    session: AsyncSession,
    model: type[T],
    *,
    actor: service.Actor,
    kind: ResourceKind,
    name: str,
    needed: Role,
    lowered: bool = True,
) -> T | None:
    """Return the row of that name the actor may do that much with.

    Two accounts may use the same name, so every row the actor can reach under
    that name is tried and the first one that allows the work wins. ``lowered``
    says whether the table keeps names in lower case, as most modules do.
    """
    table: Any = model
    shared = await service.readable_ids(session, actor=actor, kind=kind)
    reach = _reach(table, actor=actor, shared=shared)
    if reach is None:
        return None

    wanted = name.lower() if lowered else name
    # The owner comes back as its own column, because the row itself is only
    # known to be a table with an identifier.
    result = await session.execute(
        select(model, table.owner_id)
        .where(reach, table.name == wanted)
        .order_by(table.created_at.desc())
    )
    for row in result:
        # The row comes back untyped, so both halves are named here.
        candidate: T = row[0]
        owner_id: UUID = row[1]
        if await service.allows(
            session,
            actor=actor,
            kind=kind,
            resource_id=candidate.id,
            owner_id=owner_id,
            needed=needed,
        ):
            return candidate
    return None

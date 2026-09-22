"""Working out who may do what, and keeping the machine identities.

Every cloud module asks one question here: may this actor do this much with
this resource? The answer is the same everywhere, so the rules live in one
place instead of being written again in each module.
"""

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete as sql_delete
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from grod.accounts import passwords
from grod.accounts.models import User
from grod.community.models import GroupMember
from grod.iam.models import (
    KEY_PREFIX,
    ROLE_ORDER,
    Grant,
    ResourceKind,
    Role,
    ServiceAccount,
    SubjectKind,
)

TOKEN_BYTES = 32
TOKEN_PARTS = 3


class NameTakenError(Exception):
    """The account already has a service account with that name."""


class UnknownSubjectError(Exception):
    """Nobody answers to the handle the grant was meant for."""


@dataclass(frozen=True)
class Actor:
    """Who is making the call: a person or a machine.

    A service account is not a user, so both are carried here rather than
    pretending one is the other.
    """

    id: UUID
    kind: SubjectKind
    # The account behind it: the person themselves, or whoever owns the machine.
    owner_id: UUID
    name: str


def actor_of_user(user: User) -> Actor:
    """The actor a signed-in person is."""
    return Actor(id=user.id, kind=SubjectKind.USER, owner_id=user.id, name=user.login)


def actor_of_service(account: ServiceAccount) -> Actor:
    """The actor a machine identity is."""
    return Actor(
        id=account.id,
        kind=SubjectKind.SERVICE,
        owner_id=account.owner_id,
        name=account.name,
    )


def _format(account_id: UUID, secret: str) -> str:
    return f"{KEY_PREFIX}_{account_id.hex}_{secret}"


def _parse(value: str) -> tuple[UUID, str] | None:
    # The secret is url-safe base64, so it may contain underscores itself.
    parts = value.split("_", TOKEN_PARTS - 1)
    if len(parts) != TOKEN_PARTS or parts[0] != KEY_PREFIX:
        return None
    try:
        return UUID(hex=parts[1]), parts[2]
    except ValueError:
        return None


async def create_service_account(
    session: AsyncSession, *, owner: User, name: str
) -> tuple[ServiceAccount, str]:
    """Create a machine identity and hand back the token it signs in with."""
    secret = secrets.token_urlsafe(TOKEN_BYTES)
    account = ServiceAccount(
        owner_id=owner.id, name=name, token_hash=passwords.hash_password(secret)
    )
    session.add(account)
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise NameTakenError(name) from error
    return account, _format(account.id, secret)


async def authenticate_service(session: AsyncSession, value: str) -> ServiceAccount | None:
    """Return the machine identity behind a token, if the secret matches."""
    parsed = _parse(value)
    if parsed is None:
        return None
    account_id, secret = parsed

    account = await session.get(ServiceAccount, account_id)
    if account is None or not account.active:
        return None
    if not passwords.verify_password(secret, account.token_hash):
        return None

    account.last_used_at = datetime.now(UTC)
    await session.commit()
    return account


async def list_service_accounts(session: AsyncSession, *, owner: User) -> list[ServiceAccount]:
    """Return the machine identities of an account, newest first."""
    result = await session.execute(
        select(ServiceAccount)
        .where(ServiceAccount.owner_id == owner.id)
        .order_by(ServiceAccount.created_at.desc())
    )
    return list(result.scalars())


async def find_service_account(
    session: AsyncSession, *, owner: User, name: str
) -> ServiceAccount | None:
    """Return one machine identity of an account by name."""
    result = await session.execute(
        select(ServiceAccount).where(
            ServiceAccount.owner_id == owner.id, ServiceAccount.name == name
        )
    )
    return result.scalar_one_or_none()


async def delete_service_account(session: AsyncSession, *, account: ServiceAccount) -> None:
    """Remove a machine identity together with what it was allowed to do."""
    await session.execute(
        sql_delete(Grant).where(
            Grant.subject_kind == SubjectKind.SERVICE, Grant.subject_id == account.id
        )
    )
    await session.delete(account)
    await session.commit()


async def grant(
    session: AsyncSession,
    *,
    kind: ResourceKind,
    resource_id: UUID,
    subject_kind: SubjectKind,
    subject_id: UUID,
    role: Role,
    granted_by: User | None = None,
) -> Grant:
    """Give somebody a permission, or change the one they already have."""
    result = await session.execute(
        select(Grant).where(
            Grant.resource_kind == kind,
            Grant.resource_id == resource_id,
            Grant.subject_kind == subject_kind,
            Grant.subject_id == subject_id,
        )
    )
    found = result.scalar_one_or_none()
    if found is None:
        found = Grant(
            resource_kind=kind,
            resource_id=resource_id,
            subject_kind=subject_kind,
            subject_id=subject_id,
            role=role,
            granted_by_id=granted_by.id if granted_by else None,
        )
        session.add(found)
    else:
        found.role = role
    await session.commit()
    return found


async def revoke(
    session: AsyncSession,
    *,
    kind: ResourceKind,
    resource_id: UUID,
    subject_kind: SubjectKind,
    subject_id: UUID,
) -> bool:
    """Take a permission away. Returns whether there was one."""
    result = await session.execute(
        select(Grant).where(
            Grant.resource_kind == kind,
            Grant.resource_id == resource_id,
            Grant.subject_kind == subject_kind,
            Grant.subject_id == subject_id,
        )
    )
    found = result.scalar_one_or_none()
    if found is None:
        return False
    await session.delete(found)
    await session.commit()
    return True


async def list_grants(
    session: AsyncSession, *, kind: ResourceKind, resource_id: UUID
) -> list[Grant]:
    """Return every permission given for one resource."""
    result = await session.execute(
        select(Grant)
        .where(Grant.resource_kind == kind, Grant.resource_id == resource_id)
        .order_by(Grant.created_at)
    )
    return list(result.scalars())


async def role_of(
    session: AsyncSession, *, actor: Actor, kind: ResourceKind, resource_id: UUID, owner_id: UUID
) -> Role | None:
    """The strongest role an actor has for one resource, if any.

    Whoever owns a resource may do everything with it. A machine identity acts
    on its own: owning the machine is not the same as owning what the machine
    was allowed to touch, so it only gets what it was granted.
    """
    if actor.kind == SubjectKind.USER and actor.id == owner_id:
        return Role.ADMIN

    subjects: list[tuple[SubjectKind, UUID]] = [(actor.kind, actor.id)]
    if actor.kind == SubjectKind.USER:
        result = await session.execute(
            select(GroupMember.group_id).where(GroupMember.user_id == actor.id)
        )
        subjects += [(SubjectKind.GROUP, group_id) for group_id in result.scalars()]

    best: Role | None = None
    for subject_kind, subject_id in subjects:
        found = await session.execute(
            select(Grant.role).where(
                Grant.resource_kind == kind,
                Grant.resource_id == resource_id,
                Grant.subject_kind == subject_kind,
                Grant.subject_id == subject_id,
            )
        )
        role = found.scalar_one_or_none()
        if role is not None and (best is None or ROLE_ORDER[role] > ROLE_ORDER[best]):
            best = role
    return best


async def allows(
    session: AsyncSession,
    *,
    actor: Actor,
    kind: ResourceKind,
    resource_id: UUID,
    owner_id: UUID,
    needed: Role,
) -> bool:
    """Whether an actor may do that much with that resource."""
    role = await role_of(
        session, actor=actor, kind=kind, resource_id=resource_id, owner_id=owner_id
    )
    return role is not None and ROLE_ORDER[role] >= ROLE_ORDER[needed]


async def readable_ids(session: AsyncSession, *, actor: Actor, kind: ResourceKind) -> set[UUID]:
    """The resources of one kind an actor may see besides their own."""
    subjects: list[tuple[SubjectKind, UUID]] = [(actor.kind, actor.id)]
    if actor.kind == SubjectKind.USER:
        result = await session.execute(
            select(GroupMember.group_id).where(GroupMember.user_id == actor.id)
        )
        subjects += [(SubjectKind.GROUP, group_id) for group_id in result.scalars()]

    found: set[UUID] = set()
    for subject_kind, subject_id in subjects:
        result = await session.execute(
            select(Grant.resource_id).where(
                Grant.resource_kind == kind,
                Grant.subject_kind == subject_kind,
                Grant.subject_id == subject_id,
            )
        )
        found |= set(result.scalars())
    return found

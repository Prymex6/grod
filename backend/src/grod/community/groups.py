"""Groups: creating them, who belongs to them and what that allows."""

import re
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from grod.accounts import service as accounts
from grod.accounts.models import User
from grod.community.models import Group, GroupMember, GroupRole
from grod.repositories.models import SLUG_PATTERN, Project, Visibility

SLUG_RULE = re.compile(SLUG_PATTERN)

# Which group roles let a member do what, from the weakest to the strongest.
WRITING_ROLES = (GroupRole.DEVELOPER, GroupRole.MAINTAINER, GroupRole.OWNER)
MANAGING_ROLES = (GroupRole.MAINTAINER, GroupRole.OWNER)


class InvalidSlugError(Exception):
    """The address of the group does not fit the rules."""


class SlugAlreadyUsedError(Exception):
    """An account or another group already answers at this address."""


class LastOwnerError(Exception):
    """A group must keep at least one owner."""


@dataclass(frozen=True)
class MemberWithAccount:
    """A member of a group together with their account."""

    member: GroupMember
    account: User


async def slug_is_free(session: AsyncSession, slug: str) -> bool:
    """A group address may not clash with an account handle or another group."""
    if await accounts.find_by_login(session, slug) is not None:
        return False
    return await find(session, slug) is None


async def find(session: AsyncSession, slug: str) -> Group | None:
    """Return the group at this address, if any."""
    result = await session.execute(select(Group).where(Group.slug == slug.lower()))
    return result.scalar_one_or_none()


async def create(
    session: AsyncSession,
    *,
    creator: User,
    slug: str,
    name: str,
    description: str = "",
    visibility: Visibility = Visibility.PRIVATE,
    parent: Group | None = None,
) -> Group:
    """Create a group; whoever creates it becomes its owner."""
    address = slug.lower()
    if SLUG_RULE.match(address) is None:
        raise InvalidSlugError(slug)
    if not await slug_is_free(session, address):
        raise SlugAlreadyUsedError(slug)

    group = Group(
        slug=address,
        name=name,
        description=description,
        visibility=visibility,
        parent_id=parent.id if parent else None,
    )
    session.add(group)
    try:
        await session.flush()
    except IntegrityError as error:
        await session.rollback()
        raise SlugAlreadyUsedError(slug) from error

    session.add(GroupMember(group_id=group.id, user_id=creator.id, role=GroupRole.OWNER))
    await session.commit()
    return group


async def update(
    session: AsyncSession,
    *,
    group: Group,
    name: str | None = None,
    description: str | None = None,
    visibility: Visibility | None = None,
) -> Group:
    """Change what a group says about itself."""
    if name is not None:
        group.name = name
    if description is not None:
        group.description = description
    if visibility is not None:
        group.visibility = visibility
    await session.commit()
    return group


async def delete(session: AsyncSession, *, group: Group) -> None:
    """Remove a group. Its projects go with it, so the caller checks first."""
    await session.delete(group)
    await session.commit()


async def role_of(session: AsyncSession, *, group: Group, user: User | None) -> GroupRole | None:
    """Return the role an account has in a group, if any."""
    if user is None:
        return None
    result = await session.execute(
        select(GroupMember).where(GroupMember.group_id == group.id, GroupMember.user_id == user.id)
    )
    member = result.scalar_one_or_none()
    return member.role if member else None


async def list_members(session: AsyncSession, *, group: Group) -> list[MemberWithAccount]:
    """Return the members of a group with their accounts, oldest first."""
    result = await session.execute(
        select(GroupMember, User)
        .join(User, User.id == GroupMember.user_id)
        .where(GroupMember.group_id == group.id)
        .order_by(GroupMember.created_at)
    )
    return [MemberWithAccount(member=member, account=account) for member, account in result.all()]


async def add_member(
    session: AsyncSession, *, group: Group, user: User, role: GroupRole
) -> GroupMember:
    """Add somebody to a group, or change the role they already have."""
    result = await session.execute(
        select(GroupMember).where(GroupMember.group_id == group.id, GroupMember.user_id == user.id)
    )
    member = result.scalar_one_or_none()
    if member is None:
        member = GroupMember(group_id=group.id, user_id=user.id, role=role)
        session.add(member)
    else:
        if member.role == GroupRole.OWNER and role != GroupRole.OWNER:
            await _refuse_without_owner(session, group=group, leaving=user)
        member.role = role
    await session.commit()
    return member


async def remove_member(session: AsyncSession, *, group: Group, user: User) -> bool:
    """Take somebody out of a group. The last owner may not leave."""
    result = await session.execute(
        select(GroupMember).where(GroupMember.group_id == group.id, GroupMember.user_id == user.id)
    )
    member = result.scalar_one_or_none()
    if member is None:
        return False
    if member.role == GroupRole.OWNER:
        await _refuse_without_owner(session, group=group, leaving=user)
    await session.delete(member)
    await session.commit()
    return True


async def _refuse_without_owner(session: AsyncSession, *, group: Group, leaving: User) -> None:
    """Raise when this account is the only owner left."""
    result = await session.execute(
        select(GroupMember.user_id).where(
            GroupMember.group_id == group.id,
            GroupMember.role == GroupRole.OWNER,
            GroupMember.user_id != leaving.id,
        )
    )
    if result.first() is None:
        raise LastOwnerError


async def list_for_member(session: AsyncSession, *, user: User) -> list[Group]:
    """Return the groups an account belongs to, newest first."""
    result = await session.execute(
        select(Group)
        .join(GroupMember, GroupMember.group_id == Group.id)
        .where(GroupMember.user_id == user.id)
        .order_by(Group.created_at.desc())
    )
    return list(result.scalars())


async def list_projects(session: AsyncSession, *, group: Group) -> list[Project]:
    """Return the projects of a group, newest first."""
    result = await session.execute(
        select(Project).where(Project.group_id == group.id).order_by(Project.created_at.desc())
    )
    return list(result.scalars())


async def may_read(session: AsyncSession, *, group: Group, user: User | None) -> bool:
    """Whether an account may see that a group exists at all."""
    if group.visibility == Visibility.PUBLIC:
        return True
    if user is None:
        return False
    if group.visibility == Visibility.INTERNAL:
        return True
    return await role_of(session, group=group, user=user) is not None


async def group_ids_of(session: AsyncSession, *, user: User) -> set[UUID]:
    """Every group the account belongs to, for filtering listings."""
    result = await session.execute(
        select(GroupMember.group_id).where(GroupMember.user_id == user.id)
    )
    return set(result.scalars())

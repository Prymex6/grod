"""Projects: creating them, finding them and deciding who may see them."""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from fnmatch import fnmatch
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from grod.accounts import service as accounts
from grod.accounts.models import User
from grod.community.models import Group, GroupMember, GroupRole
from grod.repositories import git
from grod.repositories.models import (
    DEFAULT_BRANCH,
    SLUG_PATTERN,
    Project,
    ProjectMember,
    ProjectStar,
    ProtectedBranch,
    Role,
    Visibility,
)

SLUG_RULE = re.compile(SLUG_PATTERN)


class SlugAlreadyUsedError(Exception):
    """The owner already has a project with this address."""


class InvalidSlugError(Exception):
    """The address may only hold lower-case letters, digits, dots and dashes."""


class PatternAlreadyProtectedError(Exception):
    """The project already protects branches matching this pattern."""


class OwnerCannotBeMemberError(Exception):
    """The owner already has every right there is."""


@dataclass(frozen=True)
class ProjectWithOwner:
    """A project with the account that created it and the namespace it lives in."""

    project: Project
    owner: User
    # The first part of the address: an account handle or a group slug.
    namespace: str


async def create(
    session: AsyncSession,
    *,
    owner: User,
    slug: str,
    name: str,
    description: str = "",
    visibility: Visibility = Visibility.PRIVATE,
    group: Group | None = None,
) -> Project:
    """Create a project and its empty repository on disk."""
    if not SLUG_RULE.match(slug):
        raise InvalidSlugError(slug)

    project = Project(
        owner_id=owner.id,
        group_id=group.id if group else None,
        slug=slug,
        name=name,
        description=description,
        visibility=visibility,
        default_branch=DEFAULT_BRANCH,
    )
    session.add(project)
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise SlugAlreadyUsedError(slug) from error

    await git.create_repository(project.id, default_branch=project.default_branch)
    await git.write_protection(project.id, [])
    return project


async def delete(session: AsyncSession, *, project: Project) -> None:
    """Remove a project together with its repository."""
    await session.delete(project)
    await session.commit()
    await git.delete_repository(project.id)


async def find(session: AsyncSession, *, owner_login: str, slug: str) -> ProjectWithOwner | None:
    """Return a project by its address.

    The first part of the address is either an account handle or a group slug,
    so both namespaces are tried, accounts first.
    """
    namespace = owner_login.lower()
    address = slug.lower()

    account = await accounts.find_by_login(session, namespace)
    if account is not None:
        result = await session.execute(
            select(Project).where(
                Project.owner_id == account.id,
                Project.group_id.is_(None),
                Project.slug == address,
            )
        )
        project = result.scalar_one_or_none()
        if project is None:
            return None
        return ProjectWithOwner(project=project, owner=account, namespace=namespace)

    group_result = await session.execute(select(Group).where(Group.slug == namespace))
    group = group_result.scalar_one_or_none()
    if group is None:
        return None
    result = await session.execute(
        select(Project, User)
        .join(User, User.id == Project.owner_id)
        .where(Project.group_id == group.id, Project.slug == address)
    )
    row = result.first()
    if row is None:
        return None
    project, creator = row
    return ProjectWithOwner(project=project, owner=creator, namespace=namespace)


async def find_by_id(session: AsyncSession, project_id: UUID) -> Project | None:
    """Return one project by its identifier."""
    return await session.get(Project, project_id)


async def list_for_owner(session: AsyncSession, *, owner: User) -> list[Project]:
    """Return the personal projects of an account, newest first."""
    result = await session.execute(
        select(Project)
        .where(Project.owner_id == owner.id, Project.group_id.is_(None))
        .order_by(Project.created_at.desc())
    )
    return list(result.scalars())


def _with_namespace(rows: Sequence[Any]) -> list[ProjectWithOwner]:
    """Name the namespace of each row: the group slug, or the owner handle."""
    return [
        ProjectWithOwner(project=project, owner=owner, namespace=group_slug or owner.login)
        for project, owner, group_slug in rows
    ]


async def list_public(session: AsyncSession, *, limit: int) -> list[ProjectWithOwner]:
    """Return public projects for the explore page."""
    result = await session.execute(
        select(Project, User, Group.slug)
        .join(User, User.id == Project.owner_id)
        .outerjoin(Group, Group.id == Project.group_id)
        .where(Project.visibility == Visibility.PUBLIC)
        .order_by(Project.created_at.desc())
        .limit(limit)
    )
    return _with_namespace(result.all())


WRITING_ROLES = (Role.DEVELOPER, Role.MAINTAINER)
GROUP_WRITING_ROLES = (GroupRole.DEVELOPER, GroupRole.MAINTAINER, GroupRole.OWNER)


@dataclass(frozen=True)
class Access:
    """What one person may do in one project."""

    read: bool
    write: bool
    manage: bool
    own: bool


async def access_of(session: AsyncSession, *, project: Project, user: User | None) -> Access:
    """Work out the rights of an account in a project.

    A project in a group takes the rights of the group as well: the role there
    counts even for somebody who is not a member of the project itself.
    """
    if user is None:
        public = project.visibility == Visibility.PUBLIC
        return Access(read=public, write=False, manage=False, own=False)
    if project.owner_id == user.id and project.group_id is None:
        return Access(read=True, write=True, manage=True, own=True)

    role = await member_role(session, project=project, user=user)
    group_role = await _group_role_of(session, project=project, user=user)
    if group_role == GroupRole.OWNER:
        return Access(read=True, write=True, manage=True, own=True)

    belongs = role is not None or group_role is not None
    visible = project.visibility in {Visibility.PUBLIC, Visibility.INTERNAL} or belongs
    return Access(
        read=visible,
        write=role in WRITING_ROLES or group_role in GROUP_WRITING_ROLES,
        manage=role == Role.MAINTAINER or group_role == GroupRole.MAINTAINER,
        own=False,
    )


async def _group_role_of(
    session: AsyncSession, *, project: Project, user: User
) -> GroupRole | None:
    """Return the role the account has in the group that owns the project."""
    if project.group_id is None:
        return None
    result = await session.execute(
        select(GroupMember.role).where(
            GroupMember.group_id == project.group_id, GroupMember.user_id == user.id
        )
    )
    return result.scalar_one_or_none()


async def member_role(session: AsyncSession, *, project: Project, user: User) -> Role | None:
    """Return the role of an account in a project, if it has one."""
    result = await session.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project.id, ProjectMember.user_id == user.id
        )
    )
    member = result.scalar_one_or_none()
    return member.role if member else None


async def list_members(
    session: AsyncSession, *, project: Project
) -> list[tuple[ProjectMember, User]]:
    """Return the members of a project with their accounts."""
    result = await session.execute(
        select(ProjectMember, User)
        .join(User, User.id == ProjectMember.user_id)
        .where(ProjectMember.project_id == project.id)
        .order_by(ProjectMember.created_at)
    )
    return [(member, user) for member, user in result.all()]


async def add_member(
    session: AsyncSession, *, project: Project, user: User, role: Role
) -> ProjectMember:
    """Add somebody to a project, or change the role they already have."""
    if user.id == project.owner_id:
        raise OwnerCannotBeMemberError

    existing = await session.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project.id, ProjectMember.user_id == user.id
        )
    )
    member = existing.scalar_one_or_none()
    if member is None:
        member = ProjectMember(project_id=project.id, user_id=user.id, role=role)
        session.add(member)
    else:
        member.role = role
    await session.commit()
    return member


async def remove_member(session: AsyncSession, *, project: Project, user: User) -> bool:
    """Take somebody off a project."""
    result = await session.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project.id, ProjectMember.user_id == user.id
        )
    )
    member = result.scalar_one_or_none()
    if member is None:
        return False
    await session.delete(member)
    await session.commit()
    return True


def may_read(project: Project, user: User | None) -> bool:
    """Read access that needs no database lookup: visibility and ownership."""
    if project.visibility == Visibility.PUBLIC:
        return True
    if user is None:
        return False
    if project.visibility == Visibility.INTERNAL:
        return True
    return project.owner_id == user.id


def may_write(project: Project, user: User | None) -> bool:
    """Write access of the owner; members are checked through access_of."""
    return user is not None and project.owner_id == user.id


async def list_protected_branches(
    session: AsyncSession, *, project: Project
) -> list[ProtectedBranch]:
    """Return the protection rules of a project."""
    result = await session.execute(
        select(ProtectedBranch)
        .where(ProtectedBranch.project_id == project.id)
        .order_by(ProtectedBranch.pattern)
    )
    return list(result.scalars())


async def _refresh_protection(session: AsyncSession, project: Project) -> None:
    rules = await list_protected_branches(session, project=project)
    await git.write_protection(project.id, [rule.pattern for rule in rules])


async def protect_branch(
    session: AsyncSession, *, project: Project, pattern: str
) -> ProtectedBranch:
    """Protect branches matching a pattern and update the hook on disk."""
    rule = ProtectedBranch(project_id=project.id, pattern=pattern)
    session.add(rule)
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise PatternAlreadyProtectedError(pattern) from error
    await _refresh_protection(session, project)
    return rule


async def unprotect_branch(session: AsyncSession, *, project: Project, pattern: str) -> bool:
    """Drop one protection rule and update the hook on disk."""
    rules = await list_protected_branches(session, project=project)
    matching = next((rule for rule in rules if rule.pattern == pattern), None)
    if matching is None:
        return False
    await session.delete(matching)
    await session.commit()
    await _refresh_protection(session, project)
    return True


async def owner_of(session: AsyncSession, project: Project) -> User | None:
    """Return the account that owns a project."""
    return await accounts.get_by_id(session, project.owner_id)


async def star(session: AsyncSession, *, project: Project, user: User) -> None:
    """Mark a project as starred by an account; starring twice changes nothing."""
    session.add(ProjectStar(project_id=project.id, user_id=user.id))
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()


async def unstar(session: AsyncSession, *, project: Project, user: User) -> bool:
    """Take a star back. Returns whether there was one."""
    result = await session.execute(
        select(ProjectStar).where(
            ProjectStar.project_id == project.id, ProjectStar.user_id == user.id
        )
    )
    found = result.scalar_one_or_none()
    if found is None:
        return False
    await session.delete(found)
    await session.commit()
    return True


async def star_counts(session: AsyncSession, *, project_ids: Sequence[UUID]) -> dict[UUID, int]:
    """Count the stars of several projects at once, to keep listings cheap."""
    if not project_ids:
        return {}
    result = await session.execute(
        select(ProjectStar.project_id, func.count())
        .where(ProjectStar.project_id.in_(project_ids))
        .group_by(ProjectStar.project_id)
    )
    counts: dict[UUID, int] = {}
    for project_id, count in result.all():
        counts[project_id] = count
    return counts


async def starred_by(
    session: AsyncSession, *, user: User | None, project_ids: Sequence[UUID]
) -> set[UUID]:
    """Which of these projects the account has starred."""
    if user is None or not project_ids:
        return set()
    result = await session.execute(
        select(ProjectStar.project_id).where(
            ProjectStar.user_id == user.id, ProjectStar.project_id.in_(project_ids)
        )
    )
    return set(result.scalars())


async def list_starred(session: AsyncSession, *, user: User) -> list[ProjectWithOwner]:
    """Return the projects an account starred, newest star first."""
    result = await session.execute(
        select(Project, User, Group.slug)
        .join(ProjectStar, ProjectStar.project_id == Project.id)
        .join(User, User.id == Project.owner_id)
        .outerjoin(Group, Group.id == Project.group_id)
        .where(ProjectStar.user_id == user.id)
        .order_by(ProjectStar.created_at.desc())
    )
    return _with_namespace(result.all())


async def list_visible_of(
    session: AsyncSession, *, owner: User, viewer: User | None
) -> list[Project]:
    """Return the projects of an account that the viewer is allowed to see."""
    query = select(Project).where(Project.owner_id == owner.id, Project.group_id.is_(None))
    if viewer is None:
        query = query.where(Project.visibility == Visibility.PUBLIC)
    elif viewer.id != owner.id:
        # A signed-in visitor sees the internal ones too, and anything they take part in.
        member_projects = select(ProjectMember.project_id).where(ProjectMember.user_id == viewer.id)
        query = query.where(
            Project.visibility.in_({Visibility.PUBLIC, Visibility.INTERNAL})
            | Project.id.in_(member_projects)
        )
    result = await session.execute(query.order_by(Project.created_at.desc()))
    return list(result.scalars())


async def count_stars_given(session: AsyncSession, *, user: User) -> int:
    """How many projects an account has starred."""
    result = await session.execute(
        select(func.count()).select_from(ProjectStar).where(ProjectStar.user_id == user.id)
    )
    return result.scalar_one()


async def branch_is_protected(session: AsyncSession, *, project: Project, branch: str) -> bool:
    """Whether a branch matches one of the protection rules of a project."""
    rules = await list_protected_branches(session, project=project)
    return any(fnmatch(branch, rule.pattern) for rule in rules)

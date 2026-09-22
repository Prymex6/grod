"""Endpoints for groups: the shared namespaces that own projects."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession

from grod.accounts import service as accounts
from grod.accounts.dependencies import CurrentUser, OptionalUser
from grod.accounts.models import User
from grod.accounts.schemas import ApiModel
from grod.community import groups
from grod.community.models import Group, GroupRole
from grod.config import Settings, get_settings
from grod.db import get_db_session
from grod.repositories import service as projects
from grod.repositories import views
from grod.repositories.models import (
    DESCRIPTION_MAX_LENGTH,
    LOGIN_REFERENCE_MAX_LENGTH,
    NAME_MAX_LENGTH,
    SLUG_MAX_LENGTH,
    SLUG_PATTERN,
    Visibility,
)
from grod.repositories.schemas import ProjectView

router = APIRouter(prefix="/groups", tags=["community"])

DbSession = Annotated[AsyncSession, Depends(get_db_session)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]

NOT_FOUND_DETAIL = "No such group"
NOT_ALLOWED_DETAIL = "You may not change this"


class GroupCreate(ApiModel):
    """A new group. Its address shares the space with account handles."""

    slug: str = Field(pattern=SLUG_PATTERN, min_length=1, max_length=SLUG_MAX_LENGTH)
    name: str = Field(min_length=1, max_length=NAME_MAX_LENGTH)
    description: str = Field(default="", max_length=DESCRIPTION_MAX_LENGTH)
    visibility: Visibility = Visibility.PRIVATE


class GroupUpdate(ApiModel):
    """Changing a group; every field is optional."""

    name: str | None = Field(default=None, min_length=1, max_length=NAME_MAX_LENGTH)
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX_LENGTH)
    visibility: Visibility | None = None


class GroupView(ApiModel):
    """A group as the console shows it."""

    id: str
    slug: str
    name: str
    description: str
    visibility: Visibility
    created_at: datetime
    role: GroupRole | None
    member_count: int


class GroupMemberCreate(ApiModel):
    """Add somebody to a group, or change their role."""

    login: str = Field(min_length=1, max_length=LOGIN_REFERENCE_MAX_LENGTH)
    role: GroupRole = GroupRole.GUEST


class GroupMemberView(ApiModel):
    """A member of a group."""

    login: str
    display_name: str
    role: GroupRole
    created_at: datetime


async def _view(db: AsyncSession, group: Group, user: User | None) -> GroupView:
    members = await groups.list_members(db, group=group)
    role = next(
        (item.member.role for item in members if user is not None and item.account.id == user.id),
        None,
    )
    return GroupView(
        id=str(group.id),
        slug=group.slug,
        name=group.name,
        description=group.description,
        visibility=group.visibility,
        created_at=group.created_at,
        role=role,
        member_count=len(members),
    )


async def _readable(db: AsyncSession, slug: str, user: User | None) -> Group:
    """Find a group the caller may see, or answer 404 either way."""
    group = await groups.find(db, slug)
    if group is None or not await groups.may_read(db, group=group, user=user):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL)
    return group


async def _managed(db: AsyncSession, slug: str, user: User) -> Group:
    """Find a group whose settings or members the caller may change."""
    group = await _readable(db, slug, user)
    role = await groups.role_of(db, group=group, user=user)
    if role not in groups.MANAGING_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=NOT_ALLOWED_DETAIL)
    return group


@router.get("")
async def list_groups(db: DbSession, user: CurrentUser) -> list[GroupView]:
    """Return the groups the signed-in account belongs to."""
    found = await groups.list_for_member(db, user=user)
    return [await _view(db, group, user) for group in found]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_group(body: GroupCreate, db: DbSession, user: CurrentUser) -> GroupView:
    """Create a group; whoever creates it becomes its owner."""
    try:
        group = await groups.create(
            db,
            creator=user,
            slug=body.slug,
            name=body.name,
            description=body.description,
            visibility=body.visibility,
        )
    except groups.SlugAlreadyUsedError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="This address is already taken"
        ) from None
    except groups.InvalidSlugError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid address") from None
    return await _view(db, group, user)


@router.get("/{slug}")
async def read_group(slug: str, db: DbSession, user: OptionalUser) -> GroupView:
    """Return one group."""
    group = await _readable(db, slug, user)
    return await _view(db, group, user)


@router.patch("/{slug}")
async def change_group(slug: str, body: GroupUpdate, db: DbSession, user: CurrentUser) -> GroupView:
    """Change the name, the description or the visibility of a group."""
    group = await _managed(db, slug, user)
    changed = await groups.update(
        db,
        group=group,
        name=body.name,
        description=body.description,
        visibility=body.visibility,
    )
    return await _view(db, changed, user)


@router.delete("/{slug}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(slug: str, db: DbSession, user: CurrentUser) -> None:
    """Remove a group. Only an owner may, and only once it holds no project."""
    group = await _readable(db, slug, user)
    if await groups.role_of(db, group=group, user=user) != GroupRole.OWNER:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=NOT_ALLOWED_DETAIL)
    if await groups.list_projects(db, group=group):
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="Remove the projects of the group first"
        )
    await groups.delete(db, group=group)


@router.get("/{slug}/projects")
async def list_group_projects(
    slug: str, db: DbSession, user: OptionalUser, settings: SettingsDependency
) -> list[ProjectView]:
    """Return the projects of a group that the caller may see."""
    group = await _readable(db, slug, user)
    found = await groups.list_projects(db, group=group)

    visible = []
    for project in found:
        access = await projects.access_of(db, project=project, user=user)
        if access.read:
            creator = await accounts.find_by_id(db, project.owner_id)
            if creator is not None:
                visible.append(
                    projects.ProjectWithOwner(project=project, owner=creator, namespace=group.slug)
                )
    return await views.project_views(db, visible, user, settings, None)


@router.get("/{slug}/members")
async def list_group_members(slug: str, db: DbSession, user: OptionalUser) -> list[GroupMemberView]:
    """Return the members of a group."""
    group = await _readable(db, slug, user)
    return [
        GroupMemberView(
            login=item.account.login,
            display_name=item.account.display_name,
            role=item.member.role,
            created_at=item.member.created_at,
        )
        for item in await groups.list_members(db, group=group)
    ]


@router.post("/{slug}/members", status_code=status.HTTP_201_CREATED)
async def add_group_member(
    slug: str, body: GroupMemberCreate, db: DbSession, user: CurrentUser
) -> GroupMemberView:
    """Add somebody to a group, or change the role they already have."""
    group = await _managed(db, slug, user)
    account = await accounts.find_by_login(db, body.login)
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No such account")

    role = await groups.role_of(db, group=group, user=user)
    if body.role == GroupRole.OWNER and role != GroupRole.OWNER:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail="Only an owner may name another owner"
        )

    try:
        member = await groups.add_member(db, group=group, user=account, role=body.role)
    except groups.LastOwnerError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="A group needs at least one owner"
        ) from None

    return GroupMemberView(
        login=account.login,
        display_name=account.display_name,
        role=member.role,
        created_at=member.created_at,
    )


@router.delete("/{slug}/members/{login}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_group_member(slug: str, login: str, db: DbSession, user: CurrentUser) -> None:
    """Take somebody out of a group; anybody may take themselves out."""
    group = await _readable(db, slug, user)
    account = await accounts.find_by_login(db, login)
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No such member")

    if account.id != user.id:
        role = await groups.role_of(db, group=group, user=user)
        if role not in groups.MANAGING_ROLES:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail=NOT_ALLOWED_DETAIL)

    try:
        removed = await groups.remove_member(db, group=group, user=account)
    except groups.LastOwnerError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="A group needs at least one owner"
        ) from None
    if not removed:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No such member")

"""Endpoints of IAM: machine identities and the permissions they hold."""

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grod.accounts import service as accounts
from grod.accounts.dependencies import CurrentUser
from grod.accounts.schemas import ApiModel
from grod.community import groups
from grod.community.models import Group
from grod.db import get_db_session
from grod.iam import service
from grod.iam.models import (
    NAME_MAX_LENGTH,
    Grant,
    ResourceKind,
    Role,
    ServiceAccount,
    SubjectKind,
)

router = APIRouter(prefix="/iam", tags=["iam"])

# Query parameters are spelled the way the JSON is, not the way Python is.
ResourceKindQuery = Annotated[ResourceKind, Query(alias="resourceKind")]
ResourceIdQuery = Annotated[UUID, Query(alias="resourceId")]
SubjectKindQuery = Annotated[SubjectKind, Query(alias="subjectKind")]
SubjectIdQuery = Annotated[UUID, Query(alias="subjectId")]

DbSession = Annotated[AsyncSession, Depends(get_db_session)]

NOT_FOUND_DETAIL = "No such service account"
NOT_ALLOWED_DETAIL = "You may not change this"


class ServiceAccountCreate(ApiModel):
    """A new machine identity."""

    name: str = Field(min_length=1, max_length=NAME_MAX_LENGTH)


class ServiceAccountView(ApiModel):
    """A machine identity as the console shows it."""

    id: str
    name: str
    active: bool
    last_used_at: datetime | None
    created_at: datetime


class NewServiceAccountView(ServiceAccountView):
    """A freshly created identity, with the token shown only once."""

    token: str


class GrantWrite(ApiModel):
    """Give somebody a permission for one resource."""

    resource_kind: ResourceKind
    resource_id: UUID
    # Whom it is for: an account handle, a group address, or a service name.
    subject_kind: SubjectKind
    subject: str = Field(min_length=1, max_length=NAME_MAX_LENGTH)
    role: Role = Role.VIEWER


class GrantView(ApiModel):
    """One permission."""

    id: str
    resource_kind: ResourceKind
    resource_id: UUID
    subject_kind: SubjectKind
    subject_id: UUID
    subject: str
    role: Role
    created_at: datetime


def _account_view(account: ServiceAccount) -> ServiceAccountView:
    return ServiceAccountView(
        id=str(account.id),
        name=account.name,
        active=account.active,
        last_used_at=account.last_used_at,
        created_at=account.created_at,
    )


async def _subject_name(db: AsyncSession, grant: Grant) -> str:
    """The handle behind a grant, so the console shows a name and not an id."""
    if grant.subject_kind == SubjectKind.USER:
        user = await accounts.find_by_id(db, grant.subject_id)
        return user.login if user else ""
    if grant.subject_kind == SubjectKind.GROUP:
        group = await db.get(Group, grant.subject_id)
        return group.slug if group else ""
    account = await db.get(ServiceAccount, grant.subject_id)
    return account.name if account else ""


async def _grant_view(db: AsyncSession, grant: Grant) -> GrantView:
    return GrantView(
        id=str(grant.id),
        resource_kind=grant.resource_kind,
        resource_id=grant.resource_id,
        subject_kind=grant.subject_kind,
        subject_id=grant.subject_id,
        subject=await _subject_name(db, grant),
        role=grant.role,
        created_at=grant.created_at,
    )


async def _subject_id(db: AsyncSession, *, kind: SubjectKind, name: str, user: CurrentUser) -> UUID:
    """Find who a grant is meant for, by the handle the caller wrote."""
    if kind == SubjectKind.USER:
        account = await accounts.find_by_login(db, name)
        if account is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No such account")
        return account.id
    if kind == SubjectKind.GROUP:
        group = await groups.find(db, name)
        if group is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No such group")
        return group.id

    service_account = await service.find_service_account(db, owner=user, name=name)
    if service_account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL)
    return service_account.id


@router.get("/service-accounts")
async def list_service_accounts(db: DbSession, user: CurrentUser) -> list[ServiceAccountView]:
    """Return the machine identities of the signed-in account."""
    found = await service.list_service_accounts(db, owner=user)
    return [_account_view(account) for account in found]


@router.post("/service-accounts", status_code=status.HTTP_201_CREATED)
async def create_service_account(
    body: ServiceAccountCreate, db: DbSession, user: CurrentUser
) -> NewServiceAccountView:
    """Create a machine identity and hand back its token, once."""
    try:
        account, token = await service.create_service_account(db, owner=user, name=body.name)
    except service.NameTakenError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="You already have one with that name"
        ) from None
    return NewServiceAccountView(**_account_view(account).model_dump(), token=token)


@router.delete("/service-accounts/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_service_account(name: str, db: DbSession, user: CurrentUser) -> None:
    """Remove a machine identity together with its permissions."""
    account = await service.find_service_account(db, owner=user, name=name)
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL)
    await service.delete_service_account(db, account=account)


@router.get("/grants")
async def list_grants(
    resource_kind: ResourceKindQuery,
    resource_id: ResourceIdQuery,
    db: DbSession,
    user: CurrentUser,
) -> list[GrantView]:
    """Return the permissions given for one resource.

    Only somebody who may change the resource may see who else may touch it,
    so the caller has to hold the strongest role.
    """
    actor = service.actor_of_user(user)
    if not await _may_share(db, actor=actor, kind=resource_kind, resource_id=resource_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=NOT_ALLOWED_DETAIL)
    found = await service.list_grants(db, kind=resource_kind, resource_id=resource_id)
    return [await _grant_view(db, grant) for grant in found]


@router.post("/grants", status_code=status.HTTP_201_CREATED)
async def write_grant(body: GrantWrite, db: DbSession, user: CurrentUser) -> GrantView:
    """Give somebody a permission, or change the one they have."""
    actor = service.actor_of_user(user)
    if not await _may_share(db, actor=actor, kind=body.resource_kind, resource_id=body.resource_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=NOT_ALLOWED_DETAIL)

    subject_id = await _subject_id(db, kind=body.subject_kind, name=body.subject, user=user)
    grant = await service.grant(
        db,
        kind=body.resource_kind,
        resource_id=body.resource_id,
        subject_kind=body.subject_kind,
        subject_id=subject_id,
        role=body.role,
        granted_by=user,
    )
    return await _grant_view(db, grant)


@router.delete("/grants", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_grant(
    resource_kind: ResourceKindQuery,
    resource_id: ResourceIdQuery,
    subject_kind: SubjectKindQuery,
    subject_id: SubjectIdQuery,
    db: DbSession,
    user: CurrentUser,
) -> None:
    """Take a permission away."""
    actor = service.actor_of_user(user)
    if not await _may_share(db, actor=actor, kind=resource_kind, resource_id=resource_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=NOT_ALLOWED_DETAIL)

    removed = await service.revoke(
        db,
        kind=resource_kind,
        resource_id=resource_id,
        subject_kind=subject_kind,
        subject_id=subject_id,
    )
    if not removed:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No such permission")


async def _may_share(
    db: AsyncSession, *, actor: service.Actor, kind: ResourceKind, resource_id: UUID
) -> bool:
    """Whether this actor may hand out permissions for that resource.

    The owner of a resource always may; anybody else needs the strongest role
    they could have been given. The owner is read off the resource itself, so
    asking about somebody else's thing answers no.
    """
    owner_id = await owner_of(db, kind=kind, resource_id=resource_id)
    if owner_id is None:
        return False
    role = await service.role_of(
        db, actor=actor, kind=kind, resource_id=resource_id, owner_id=owner_id
    )
    return role == Role.ADMIN


async def owner_of(db: AsyncSession, *, kind: ResourceKind, resource_id: UUID) -> UUID | None:
    """Return the account a resource belongs to, whatever kind it is."""
    from grod.apidocs.models import ApiDoc
    from grod.apps.models import Application
    from grod.databases.models import ManagedDatabase
    from grod.errors.models import Source
    from grod.functions.models import Function
    from grod.monitoring.models import Check
    from grod.queues.models import Queue
    from grod.routing.models import Route
    from grod.storage.models import Bucket

    # Every one of these tables carries an owner, but they share no common
    # class, so the mapping is loose on purpose.
    tables: dict[ResourceKind, Any] = {
        ResourceKind.BUCKET: Bucket,
        ResourceKind.APPLICATION: Application,
        ResourceKind.FUNCTION: Function,
        ResourceKind.DATABASE: ManagedDatabase,
        ResourceKind.QUEUE: Queue,
        ResourceKind.ROUTE: Route,
        ResourceKind.CHECK: Check,
        ResourceKind.ERROR_SOURCE: Source,
        ResourceKind.API_DOC: ApiDoc,
    }
    table = tables[kind]
    result = await db.execute(select(table.owner_id).where(table.id == resource_id))
    return result.scalar_one_or_none()

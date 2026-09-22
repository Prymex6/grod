"""What the console shows about how much of the instance an account takes."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from grod.accounts.dependencies import CurrentUser
from grod.accounts.schemas import ApiModel
from grod.db import get_db_session
from grod.quotas import service

router = APIRouter(prefix="/account", tags=["quotas"])

DbSession = Annotated[AsyncSession, Depends(get_db_session)]


class LimitsView(ApiModel):
    """What this account may hold."""

    storage_bytes: int
    buckets: int
    applications: int
    functions: int
    databases: int
    queues: int
    workspaces: int


class UsageView(ApiModel):
    """What this account holds now, beside what it may hold."""

    storage_bytes: int
    files: int
    packages: int
    layers: int
    buckets: int
    applications: int
    functions: int
    databases: int
    queues: int
    workspaces: int
    limits: LimitsView


@router.get("/usage")
async def read_usage(db: DbSession, user: CurrentUser) -> UsageView:
    """Return what the signed-in account takes, and what it is allowed."""
    held = await service.usage_of(db, owner_id=user.id)
    limits = await service.limits_of(db, owner_id=user.id)
    return UsageView(
        storage_bytes=held.storage_bytes,
        files=held.files,
        packages=held.packages,
        layers=held.layers,
        buckets=held.buckets,
        applications=held.applications,
        functions=held.functions,
        databases=held.databases,
        queues=held.queues,
        workspaces=held.workspaces,
        limits=LimitsView(
            storage_bytes=limits.storage_bytes,
            buckets=limits.buckets,
            applications=limits.applications,
            functions=limits.functions,
            databases=limits.databases,
            queues=limits.queues,
            workspaces=limits.workspaces,
        ),
    )

"""Counting what an account holds, and saying no when it has enough.

Every module asks the same two questions here — may this account keep one more
of these, and may it keep these many bytes — so the answer is the same
everywhere and a new limit is added in one place.
"""

import enum
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from grod.apps.models import Application
from grod.artifacts.models import Package
from grod.artifacts.registry.models import ContainerBlob
from grod.config import get_settings
from grod.databases.models import ManagedDatabase
from grod.functions.models import Function
from grod.queues.models import Queue
from grod.quotas.models import AccountLimits
from grod.repositories.models import Project
from grod.storage.models import Bucket, StoredObject
from grod.workspaces.models import Workspace


class Thing(enum.StrEnum):
    """The kinds of thing an account is allowed only so many of."""

    BUCKET = "buckets"
    APPLICATION = "applications"
    FUNCTION = "functions"
    DATABASE = "databases"
    QUEUE = "queues"
    WORKSPACE = "workspaces"


# What each kind is counted in. The tables carry the same two columns but
# share no common class, so the mapping to them is loose on purpose.
TABLES: dict[Thing, Any] = {
    Thing.BUCKET: Bucket,
    Thing.APPLICATION: Application,
    Thing.FUNCTION: Function,
    Thing.DATABASE: ManagedDatabase,
    Thing.QUEUE: Queue,
    Thing.WORKSPACE: Workspace,
}


class OverQuotaError(Exception):
    """The account already holds as much of this as it may."""

    def __init__(self, thing: str, limit: int) -> None:
        super().__init__(thing)
        self.thing = thing
        self.limit = limit


@dataclass(frozen=True)
class Limits:
    """What one account may hold."""

    storage_bytes: int
    buckets: int
    applications: int
    functions: int
    databases: int
    queues: int
    workspaces: int


@dataclass(frozen=True)
class Usage:
    """What one account holds now."""

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


async def limits_of(session: AsyncSession, *, owner_id: UUID) -> Limits:
    """The limits of one account: its own where it has them, else the defaults."""
    settings = get_settings()
    result = await session.execute(select(AccountLimits).where(AccountLimits.owner_id == owner_id))
    given = result.scalar_one_or_none()

    if given is None:
        return Limits(
            storage_bytes=settings.quota_storage_bytes,
            buckets=settings.quota_buckets,
            applications=settings.quota_applications,
            functions=settings.quota_functions,
            databases=settings.quota_databases,
            queues=settings.quota_queues,
            workspaces=settings.quota_workspaces,
        )

    return Limits(
        storage_bytes=_or_default(given.storage_bytes, settings.quota_storage_bytes),
        buckets=_or_default(given.buckets, settings.quota_buckets),
        applications=_or_default(given.applications, settings.quota_applications),
        functions=_or_default(given.functions, settings.quota_functions),
        databases=_or_default(given.databases, settings.quota_databases),
        queues=_or_default(given.queues, settings.quota_queues),
        workspaces=_or_default(given.workspaces, settings.quota_workspaces),
    )


def _or_default(given: int | None, default: int) -> int:
    """Whatever the account was given, or what everybody gets."""
    return default if given is None else given


async def count_of(session: AsyncSession, *, owner_id: UUID, thing: Thing) -> int:
    """How many of one kind of thing an account keeps."""
    table = TABLES[thing]
    result = await session.execute(select(func.count(table.id)).where(table.owner_id == owner_id))
    return int(result.scalar_one())


async def storage_of(session: AsyncSession, *, owner_id: UUID) -> tuple[int, int, int, int]:
    """The bytes an account holds, and how they split: files, packages, layers.

    Repositories are not counted: their size on disk is not written anywhere,
    and asking Git for it on every upload would make each one slower.
    """
    files = await session.execute(
        select(func.coalesce(func.sum(StoredObject.size), 0), func.count(StoredObject.id))
        .join(Bucket, Bucket.id == StoredObject.bucket_id)
        .where(Bucket.owner_id == owner_id)
    )
    file_bytes, file_count = files.one()

    packages = await session.execute(
        select(func.coalesce(func.sum(Package.size), 0), func.count(Package.id))
        .join(Project, Project.id == Package.project_id)
        .where(Project.owner_id == owner_id)
    )
    package_bytes, package_count = packages.one()

    layers = await session.execute(
        select(func.coalesce(func.sum(ContainerBlob.size), 0), func.count(ContainerBlob.id))
        .join(Project, Project.id == ContainerBlob.project_id)
        .where(Project.owner_id == owner_id)
    )
    layer_bytes, layer_count = layers.one()

    held = int(file_bytes) + int(package_bytes) + int(layer_bytes)
    return held, int(file_count), int(package_count), int(layer_count)


async def usage_of(session: AsyncSession, *, owner_id: UUID) -> Usage:
    """Everything one account holds right now."""
    held, files, packages, layers = await storage_of(session, owner_id=owner_id)
    return Usage(
        storage_bytes=held,
        files=files,
        packages=packages,
        layers=layers,
        buckets=await count_of(session, owner_id=owner_id, thing=Thing.BUCKET),
        applications=await count_of(session, owner_id=owner_id, thing=Thing.APPLICATION),
        functions=await count_of(session, owner_id=owner_id, thing=Thing.FUNCTION),
        databases=await count_of(session, owner_id=owner_id, thing=Thing.DATABASE),
        queues=await count_of(session, owner_id=owner_id, thing=Thing.QUEUE),
        workspaces=await count_of(session, owner_id=owner_id, thing=Thing.WORKSPACE),
    )


async def ensure_room_for_one_more(session: AsyncSession, *, owner_id: UUID, thing: Thing) -> None:
    """Refuse when the account already keeps as many of these as it may."""
    limits = await limits_of(session, owner_id=owner_id)
    allowed: int = getattr(limits, thing.value)
    if await count_of(session, owner_id=owner_id, thing=thing) >= allowed:
        raise OverQuotaError(thing.value, allowed)


async def ensure_room_for_bytes(session: AsyncSession, *, owner_id: UUID, adding: int) -> None:
    """Refuse when what is coming would not fit in what is left.

    The size is what the caller says it is sending; a caller that lies is
    caught by the next upload, when the bytes it really wrote are counted.
    """
    limits = await limits_of(session, owner_id=owner_id)
    held, _, _, _ = await storage_of(session, owner_id=owner_id)
    if held + max(adding, 0) > limits.storage_bytes:
        raise OverQuotaError("storageBytes", limits.storage_bytes)

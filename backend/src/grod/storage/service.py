"""Buckets and the files inside them."""

import asyncio
import hashlib
import re
import shutil
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from grod.accounts.models import User
from grod.config import get_settings
from grod.storage.models import (
    KEY_MAX_LENGTH,
    NAME_PATTERN,
    Bucket,
    BucketAccess,
    StoredObject,
)

__all__ = [
    "Bucket",
    "BucketAccess",
    "BucketUsage",
    "InvalidKeyError",
    "InvalidNameError",
    "NameTakenError",
    "ObjectTooLargeError",
    "StoredFile",
    "StoredObject",
    "bucket_path",
    "check_key",
    "create",
    "delete_bucket",
    "delete_object",
    "find",
    "find_object",
    "list_objects",
    "object_path",
    "put_object",
    "set_access",
    "usage",
]

NAME_RULE = re.compile(NAME_PATTERN)
MAX_OBJECT_BYTES = 5 * 1024 * 1024 * 1024
DEFAULT_CONTENT_TYPE = "application/octet-stream"


class InvalidNameError(Exception):
    """A bucket is named like a host name: lower case, digits and dashes."""


class NameTakenError(Exception):
    """Another bucket already has that name."""


class InvalidKeyError(Exception):
    """The key of an object is empty, too long or walks out of the bucket."""


class ObjectTooLargeError(Exception):
    """The file is larger than this instance accepts."""


@dataclass(frozen=True)
class StoredFile:
    """An object together with where its contents lie."""

    stored: StoredObject
    path: Path


@dataclass(frozen=True)
class BucketUsage:
    """How much a bucket holds."""

    objects: int
    bytes: int


def bucket_path(bucket_id: UUID) -> Path:
    """Where the files of one bucket live."""
    return get_settings().storage_path / str(bucket_id)


def object_path(bucket_id: UUID, object_id: UUID) -> Path:
    """Where the contents of one object live.

    Objects are kept under their identifier, never under their key, so a key
    with slashes or dots can never reach outside the folder of the bucket.
    """
    return bucket_path(bucket_id) / str(object_id)


def check_key(key: str) -> str:
    """Return the key as it will be stored, or refuse it."""
    cleaned = key.strip("/")
    if not cleaned or len(cleaned) > KEY_MAX_LENGTH:
        raise InvalidKeyError(key)
    if any(part in {"", ".", ".."} for part in cleaned.split("/")):
        raise InvalidKeyError(key)
    return cleaned


async def find(session: AsyncSession, name: str) -> Bucket | None:
    """Return the bucket with this name, if any."""
    result = await session.execute(select(Bucket).where(Bucket.name == name.lower()))
    return result.scalar_one_or_none()


async def create(
    session: AsyncSession,
    *,
    owner: User,
    name: str,
    access: BucketAccess = BucketAccess.PRIVATE,
) -> Bucket:
    """Create a bucket. Names are unique across the whole instance."""
    address = name.lower()
    if NAME_RULE.match(address) is None:
        raise InvalidNameError(name)

    bucket = Bucket(owner_id=owner.id, name=address, access=access)
    session.add(bucket)
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise NameTakenError(name) from error
    return bucket


async def set_access(session: AsyncSession, *, bucket: Bucket, access: BucketAccess) -> Bucket:
    """Open a bucket to everybody, or close it again."""
    bucket.access = access
    await session.commit()
    return bucket


async def delete_bucket(session: AsyncSession, *, bucket: Bucket) -> None:
    """Remove a bucket together with everything it holds."""
    path = bucket_path(bucket.id)
    await session.delete(bucket)
    await session.commit()
    await asyncio.to_thread(shutil.rmtree, path, True)


async def list_objects(
    session: AsyncSession, *, bucket: Bucket, prefix: str = "", limit: int = 100
) -> list[StoredObject]:
    """Return the objects of a bucket, by key, optionally under one prefix."""
    query = select(StoredObject).where(StoredObject.bucket_id == bucket.id)
    if prefix:
        query = query.where(StoredObject.key.startswith(prefix))
    result = await session.execute(query.order_by(StoredObject.key).limit(limit))
    return list(result.scalars())


async def usage(session: AsyncSession, *, bucket: Bucket) -> BucketUsage:
    """Count what a bucket holds."""
    result = await session.execute(
        select(func.count(), func.coalesce(func.sum(StoredObject.size), 0)).where(
            StoredObject.bucket_id == bucket.id
        )
    )
    objects, total = result.one()
    return BucketUsage(objects=objects, bytes=total)


async def find_object(session: AsyncSession, *, bucket: Bucket, key: str) -> StoredFile | None:
    """Find one object of a bucket by its key."""
    cleaned = check_key(key)
    result = await session.execute(
        select(StoredObject).where(StoredObject.bucket_id == bucket.id, StoredObject.key == cleaned)
    )
    stored = result.scalar_one_or_none()
    if stored is None:
        return None
    path = object_path(bucket.id, stored.id)
    if not path.is_file():
        return None
    return StoredFile(stored=stored, path=path)


async def put_object(
    session: AsyncSession,
    *,
    bucket: Bucket,
    key: str,
    content: AsyncIterator[bytes],
    content_type: str = DEFAULT_CONTENT_TYPE,
) -> StoredObject:
    """Write a file into a bucket, replacing what was under that key."""
    cleaned = check_key(key)

    result = await session.execute(
        select(StoredObject).where(StoredObject.bucket_id == bucket.id, StoredObject.key == cleaned)
    )
    stored = result.scalar_one_or_none()
    if stored is None:
        stored = StoredObject(
            bucket_id=bucket.id, key=cleaned, size=0, content_type=content_type, digest=""
        )
        session.add(stored)
        await session.flush()

    size, digest = await _write(object_path(bucket.id, stored.id), content)
    stored.size = size
    stored.digest = digest
    stored.content_type = content_type
    await session.commit()
    return stored


async def _write(path: Path, content: AsyncIterator[bytes]) -> tuple[int, str]:
    """Write an upload to disk, counting its size and digest as it goes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_suffix(".part")
    hasher = hashlib.sha256()
    size = 0

    handle = await asyncio.to_thread(staging.open, "wb")
    try:
        async for chunk in content:
            size += len(chunk)
            if size > MAX_OBJECT_BYTES:
                raise ObjectTooLargeError(size)
            hasher.update(chunk)
            await asyncio.to_thread(handle.write, chunk)
    except BaseException:
        await asyncio.to_thread(handle.close)
        staging.unlink(missing_ok=True)
        raise
    await asyncio.to_thread(handle.close)

    await asyncio.to_thread(staging.replace, path)
    return size, hasher.hexdigest()


async def delete_object(session: AsyncSession, *, bucket: Bucket, key: str) -> bool:
    """Remove one object. Returns whether there was one."""
    cleaned = check_key(key)
    result = await session.execute(
        select(StoredObject).where(StoredObject.bucket_id == bucket.id, StoredObject.key == cleaned)
    )
    stored = result.scalar_one_or_none()
    if stored is None:
        return False

    path = object_path(bucket.id, stored.id)
    await session.delete(stored)
    await session.commit()
    await asyncio.to_thread(path.unlink, True)
    return True

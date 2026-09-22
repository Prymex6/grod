"""Endpoints for buckets and the files inside them."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession

from grod.accounts.dependencies import CurrentUser
from grod.accounts.schemas import ApiModel
from grod.db import get_db_session
from grod.iam import scope
from grod.iam import service as iam
from grod.iam.dependencies import CurrentActor, OptionalActor
from grod.iam.models import ResourceKind, Role
from grod.quotas import service as quotas
from grod.quotas.errors import refusal
from grod.quotas.service import Thing
from grod.storage import service
from grod.storage.models import NAME_MAX_LENGTH, NAME_PATTERN, Bucket, BucketAccess

router = APIRouter(prefix="/storage", tags=["storage"])

DbSession = Annotated[AsyncSession, Depends(get_db_session)]

NOT_FOUND_DETAIL = "No such bucket"
OBJECT_NOT_FOUND_DETAIL = "No such object"
NOT_ALLOWED_DETAIL = "This bucket is not yours"
MAX_OBJECTS = 1000


class BucketCreate(ApiModel):
    """A new bucket."""

    name: str = Field(pattern=NAME_PATTERN, min_length=3, max_length=NAME_MAX_LENGTH)
    access: BucketAccess = BucketAccess.PRIVATE


class BucketUpdate(ApiModel):
    """Open a bucket to everybody, or close it again."""

    access: BucketAccess


class BucketView(ApiModel):
    """A bucket as the console shows it."""

    id: str
    name: str
    access: BucketAccess
    created_at: datetime
    objects: int
    bytes: int


class ObjectView(ApiModel):
    """One file inside a bucket."""

    key: str
    size: int
    content_type: str
    digest: str
    created_at: datetime
    url: str


def _object_view(stored: service.StoredObject, bucket: Bucket) -> ObjectView:
    return ObjectView(
        key=stored.key,
        size=stored.size,
        content_type=stored.content_type,
        digest=stored.digest,
        created_at=stored.created_at,
        url=f"/api/v1/storage/buckets/{bucket.name}/objects/{stored.key}",
    )


async def _view(db: AsyncSession, bucket: Bucket) -> BucketView:
    held = await service.usage(db, bucket=bucket)
    return BucketView(
        id=str(bucket.id),
        name=bucket.name,
        access=bucket.access,
        created_at=bucket.created_at,
        objects=held.objects,
        bytes=held.bytes,
    )


async def _allowed(db: AsyncSession, name: str, actor: iam.Actor | None, needed: Role) -> Bucket:
    """Find a bucket this actor may do that much with.

    A public bucket may be read by anybody; everything else needs a grant, or
    the bucket has to belong to whoever is asking.
    """
    bucket = await service.find(db, name)
    if bucket is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL)

    if needed == Role.VIEWER and bucket.access == BucketAccess.PUBLIC:
        return bucket
    if actor is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL)

    if not await iam.allows(
        db,
        actor=actor,
        kind=ResourceKind.BUCKET,
        resource_id=bucket.id,
        owner_id=bucket.owner_id,
        needed=needed,
    ):
        # A bucket nobody may touch must look exactly like a missing one.
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL)
    return bucket


@router.get("/buckets")
async def list_buckets(db: DbSession, actor: CurrentActor) -> list[BucketView]:
    """Return the buckets the caller may see."""
    found = await scope.visible(db, Bucket, actor=actor, kind=ResourceKind.BUCKET)
    return [await _view(db, bucket) for bucket in found]


@router.post("/buckets", status_code=status.HTTP_201_CREATED)
async def create_bucket(body: BucketCreate, db: DbSession, user: CurrentUser) -> BucketView:
    """Create a bucket. Its name is unique across the whole instance."""
    try:
        await quotas.ensure_room_for_one_more(db, owner_id=user.id, thing=Thing.BUCKET)
    except quotas.OverQuotaError as error:
        raise refusal(error) from None

    try:
        bucket = await service.create(db, owner=user, name=body.name, access=body.access)
    except service.InvalidNameError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid bucket name") from None
    except service.NameTakenError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="A bucket with that name already exists"
        ) from None
    return await _view(db, bucket)


@router.get("/buckets/{name}")
async def read_bucket(name: str, db: DbSession, actor: OptionalActor) -> BucketView:
    """Return one bucket."""
    bucket = await _allowed(db, name, actor, Role.VIEWER)
    return await _view(db, bucket)


@router.patch("/buckets/{name}")
async def change_bucket(
    name: str, body: BucketUpdate, db: DbSession, actor: CurrentActor
) -> BucketView:
    """Open a bucket to everybody, or close it again."""
    bucket = await _allowed(db, name, actor, Role.ADMIN)
    await service.set_access(db, bucket=bucket, access=body.access)
    return await _view(db, bucket)


@router.delete("/buckets/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bucket(name: str, db: DbSession, actor: CurrentActor) -> None:
    """Remove a bucket together with everything it holds."""
    bucket = await _allowed(db, name, actor, Role.ADMIN)
    await service.delete_bucket(db, bucket=bucket)


@router.get("/buckets/{name}/objects")
async def list_objects(
    name: str,
    db: DbSession,
    actor: OptionalActor,
    prefix: str = "",
    limit: Annotated[int, Query(le=MAX_OBJECTS)] = 100,
) -> list[ObjectView]:
    """Return what a bucket holds, by key."""
    bucket = await _allowed(db, name, actor, Role.VIEWER)
    found = await service.list_objects(db, bucket=bucket, prefix=prefix, limit=limit)
    return [_object_view(stored, bucket) for stored in found]


@router.put("/buckets/{name}/objects/{key:path}", status_code=status.HTTP_201_CREATED)
async def put_object(
    name: str, key: str, request: Request, db: DbSession, actor: CurrentActor
) -> ObjectView:
    """Write a file into a bucket. The body of the request is the file."""
    bucket = await _allowed(db, name, actor, Role.OPERATOR)
    try:
        # The header is what the caller says it is sending; what it really
        # wrote is counted the next time somebody asks for room.
        announced = int(request.headers.get("content-length", 0))
        await quotas.ensure_room_for_bytes(db, owner_id=bucket.owner_id, adding=announced)
    except quotas.OverQuotaError as error:
        raise refusal(error) from None
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid length") from None

    try:
        stored = await service.put_object(
            db,
            bucket=bucket,
            key=key,
            content=request.stream(),
            content_type=request.headers.get("content-type", service.DEFAULT_CONTENT_TYPE),
        )
    except service.InvalidKeyError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid object key") from None
    except service.ObjectTooLargeError:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="The file is too large"
        ) from None
    return _object_view(stored, bucket)


@router.get("/buckets/{name}/objects/{key:path}")
async def get_object(name: str, key: str, db: DbSession, actor: OptionalActor) -> FileResponse:
    """Read one file out of a bucket."""
    bucket = await _allowed(db, name, actor, Role.VIEWER)
    try:
        found = await service.find_object(db, bucket=bucket, key=key)
    except service.InvalidKeyError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid object key") from None
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=OBJECT_NOT_FOUND_DETAIL)
    return FileResponse(found.path, media_type=found.stored.content_type)


@router.delete("/buckets/{name}/objects/{key:path}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_object(name: str, key: str, db: DbSession, actor: CurrentActor) -> None:
    """Remove one file from a bucket."""
    bucket = await _allowed(db, name, actor, Role.OPERATOR)
    try:
        removed = await service.delete_object(db, bucket=bucket, key=key)
    except service.InvalidKeyError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid object key") from None
    if not removed:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=OBJECT_NOT_FOUND_DETAIL)

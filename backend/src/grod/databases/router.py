"""Endpoints for the databases an account keeps."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession

from grod.accounts.dependencies import CurrentUser
from grod.accounts.schemas import ApiModel
from grod.databases import postgres, service
from grod.databases.models import NAME_MAX_LENGTH, NAME_PATTERN, DatabaseEngine, ManagedDatabase
from grod.db import get_db_session
from grod.iam import scope
from grod.iam import service as iam
from grod.iam.dependencies import CurrentActor
from grod.iam.models import ResourceKind, Role
from grod.quotas import service as quotas
from grod.quotas.errors import refusal
from grod.quotas.service import Thing

router = APIRouter(prefix="/databases", tags=["databases"])

DbSession = Annotated[AsyncSession, Depends(get_db_session)]

NOT_FOUND_DETAIL = "No such database"


class DatabaseCreate(ApiModel):
    """A new database."""

    name: str = Field(pattern=NAME_PATTERN, min_length=3, max_length=NAME_MAX_LENGTH)


class DatabaseView(ApiModel):
    """A database as the console shows it, without the password."""

    id: str
    name: str
    engine: DatabaseEngine
    database_name: str
    role_name: str
    host: str
    port: int
    size_bytes: int
    created_at: datetime


class ConnectionView(ApiModel):
    """How to reach a database, password and all."""

    host: str
    port: int
    database: str
    user: str
    password: str
    url: str


async def _view(record: ManagedDatabase) -> DatabaseView:
    connection = await service.connection_of(record)
    return DatabaseView(
        id=str(record.id),
        name=record.name,
        engine=record.engine,
        database_name=record.database_name,
        role_name=record.role_name,
        host=connection.host,
        port=connection.port,
        size_bytes=record.size_bytes,
        created_at=record.created_at,
    )


def _connection_view(connection: postgres.Connection) -> ConnectionView:
    return ConnectionView(
        host=connection.host,
        port=connection.port,
        database=connection.database,
        user=connection.user,
        password=connection.password,
        url=connection.url,
    )


async def _allowed(db: AsyncSession, name: str, actor: iam.Actor, needed: Role) -> ManagedDatabase:
    """Find a database this actor may do that much with."""
    record = await scope.allowed(
        db, ManagedDatabase, actor=actor, kind=ResourceKind.DATABASE, name=name, needed=needed
    )
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL)
    return record


@router.get("")
async def list_databases(db: DbSession, actor: CurrentActor) -> list[DatabaseView]:
    """Return the databases of the signed-in account."""
    found = await scope.visible(db, ManagedDatabase, actor=actor, kind=ResourceKind.DATABASE)
    return [await _view(await service.refresh_size(db, record=record)) for record in found]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_database(body: DatabaseCreate, db: DbSession, user: CurrentUser) -> DatabaseView:
    """Create a database with its own role."""
    try:
        await quotas.ensure_room_for_one_more(db, owner_id=user.id, thing=Thing.DATABASE)
    except quotas.OverQuotaError as error:
        raise refusal(error) from None

    try:
        record = await service.create(db, owner=user, name=body.name)
    except service.InvalidNameError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid name") from None
    except service.NameTakenError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="You already have a database with that name"
        ) from None
    return await _view(record)


@router.get("/{name}")
async def read_database(name: str, db: DbSession, actor: CurrentActor) -> DatabaseView:
    """Return one database with the room it takes."""
    record = await _allowed(db, name, actor, Role.VIEWER)
    return await _view(await service.refresh_size(db, record=record))


@router.get("/{name}/connection")
async def read_connection(name: str, db: DbSession, actor: CurrentActor) -> ConnectionView:
    """Return everything needed to connect, password included."""
    # The password is the database itself, so looking at it is not enough here.
    record = await _allowed(db, name, actor, Role.OPERATOR)
    return _connection_view(await service.connection_of(record))


@router.post("/{name}/rotate-password")
async def rotate_password(name: str, db: DbSession, actor: CurrentActor) -> ConnectionView:
    """Give the database a new password; the old one stops working at once."""
    record = await _allowed(db, name, actor, Role.ADMIN)
    await service.rotate_password(db, record=record)
    return _connection_view(await service.connection_of(record))


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_database(name: str, db: DbSession, actor: CurrentActor) -> None:
    """Remove a database together with everything in it."""
    record = await _allowed(db, name, actor, Role.ADMIN)
    await service.delete(db, record=record)

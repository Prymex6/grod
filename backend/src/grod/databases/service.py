"""Handing out databases and taking them back."""

import re
import secrets
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from grod.accounts.models import User
from grod.artifacts import crypto
from grod.databases import postgres
from grod.databases.models import NAME_PATTERN, DatabaseEngine, ManagedDatabase

NAME_RULE = re.compile(NAME_PATTERN)
PASSWORD_BYTES = 24
# Both names carry the identifier of the record, so nothing ever clashes.
DATABASE_PREFIX = "grod_db_"
ROLE_PREFIX = "grod_user_"
IDENTIFIER_LENGTH = 12


class InvalidNameError(Exception):
    """A database is named like a host name."""


class NameTakenError(Exception):
    """The account already has a database with that name."""


def _identifiers(record_id: UUID) -> tuple[str, str]:
    """The names the server will know this database and its role by."""
    short = record_id.hex[:IDENTIFIER_LENGTH]
    return f"{DATABASE_PREFIX}{short}", f"{ROLE_PREFIX}{short}"


async def find(session: AsyncSession, *, owner: User, name: str) -> ManagedDatabase | None:
    """Return one database of an account by name."""
    result = await session.execute(
        select(ManagedDatabase).where(
            ManagedDatabase.owner_id == owner.id, ManagedDatabase.name == name.lower()
        )
    )
    return result.scalar_one_or_none()


async def create(session: AsyncSession, *, owner: User, name: str) -> ManagedDatabase:
    """Create a database with its own role and remember how to reach it."""
    address = name.lower()
    if NAME_RULE.match(address) is None:
        raise InvalidNameError(name)

    password = secrets.token_urlsafe(PASSWORD_BYTES)
    record = ManagedDatabase(
        owner_id=owner.id,
        name=address,
        engine=DatabaseEngine.POSTGRES,
        # Filled in once the record has an identifier of its own.
        database_name="",
        role_name="",
        password_encrypted=crypto.encrypt(password),
    )
    session.add(record)
    try:
        await session.flush()
    except IntegrityError as error:
        await session.rollback()
        raise NameTakenError(name) from error

    record.database_name, record.role_name = _identifiers(record.id)
    try:
        await postgres.create_database(
            database=record.database_name, role=record.role_name, password=password
        )
    except SQLAlchemyError:
        # Nothing was created on the server, so the record goes away too.
        await session.rollback()
        raise

    await session.commit()
    return record


async def connection_of(record: ManagedDatabase) -> postgres.Connection:
    """Everything an application needs to reach this database."""
    host, port = postgres.public_address()
    return postgres.Connection(
        host=host,
        port=port,
        database=record.database_name,
        user=record.role_name,
        password=crypto.decrypt(record.password_encrypted),
    )


async def rotate_password(session: AsyncSession, *, record: ManagedDatabase) -> str:
    """Give the database a new password and forget the old one."""
    password = secrets.token_urlsafe(PASSWORD_BYTES)
    await postgres.set_password(role=record.role_name, password=password)
    record.password_encrypted = crypto.encrypt(password)
    await session.commit()
    return password


async def refresh_size(session: AsyncSession, *, record: ManagedDatabase) -> ManagedDatabase:
    """Ask the server how much room the database takes."""
    record.size_bytes = await postgres.size_of(record.database_name)
    await session.commit()
    return record


async def delete(session: AsyncSession, *, record: ManagedDatabase) -> None:
    """Remove the database, its role and the record of it."""
    await postgres.drop_database(database=record.database_name, role=record.role_name)
    await session.delete(record)
    await session.commit()

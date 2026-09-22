"""The only place in Grod that speaks administrative SQL to the database server.

Creating a database and a role means running statements that cannot take
parameters, so every identifier is quoted here and nowhere else. Keeping that
in one small module is what makes it safe to read.
"""

import re
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from grod.config import get_settings

# An identifier Grod builds itself: letters, digits and underscores only.
IDENTIFIER_RULE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")
# CREATE ROLE and ALTER ROLE take no parameters, so the password has to be
# written into the statement. Grod generates it with secrets.token_urlsafe,
# which produces exactly this alphabet, and refuses anything else.
PASSWORD_RULE = re.compile(r"^[A-Za-z0-9_-]{8,200}$")
# Postgres talks to one database at a time; CREATE DATABASE needs another one.
MAINTENANCE_DATABASE = "postgres"


class InvalidIdentifierError(Exception):
    """Somebody tried to use a name the platform did not build."""


class InvalidPasswordError(Exception):
    """The password is not one the platform generated."""


@dataclass(frozen=True)
class Connection:
    """Everything an application needs to reach its database."""

    host: str
    port: int
    database: str
    user: str
    password: str

    @property
    def url(self) -> str:
        """The address in the form every library understands."""
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"


def _checked(identifier: str) -> str:
    """Return an identifier that is safe to put into a statement."""
    if IDENTIFIER_RULE.match(identifier) is None:
        raise InvalidIdentifierError(identifier)
    return identifier


def _checked_password(password: str) -> str:
    """Return a password that is safe to put into a statement."""
    if PASSWORD_RULE.match(password) is None:
        raise InvalidPasswordError
    return password


def _maintenance_engine() -> AsyncEngine:
    """Connect to the server itself, not to one of the databases it holds.

    CREATE DATABASE cannot run inside a transaction, so the connection is
    opened in autocommit mode.
    """
    url = make_url(str(get_settings().database_url)).set(database=MAINTENANCE_DATABASE)
    return create_async_engine(url, isolation_level="AUTOCOMMIT", poolclass=None)


def public_address() -> tuple[str, int]:
    """Where applications reach the database server."""
    settings = get_settings()
    url = make_url(str(settings.database_url))
    return settings.database_public_host or (url.host or "localhost"), url.port or 5432


async def create_database(*, database: str, role: str, password: str) -> None:
    """Create a role and a database it owns."""
    safe_database = _checked(database)
    safe_role = _checked(role)

    safe_password = _checked_password(password)

    engine = _maintenance_engine()
    try:
        async with engine.connect() as connection:
            await connection.execute(
                text(f"CREATE ROLE \"{safe_role}\" LOGIN PASSWORD '{safe_password}'")
            )
            await connection.execute(text(f'CREATE DATABASE "{safe_database}" OWNER "{safe_role}"'))
    finally:
        await engine.dispose()


async def set_password(*, role: str, password: str) -> None:
    """Give a role a new password."""
    safe_role = _checked(role)
    safe_password = _checked_password(password)

    engine = _maintenance_engine()
    try:
        async with engine.connect() as connection:
            await connection.execute(text(f"ALTER ROLE \"{safe_role}\" PASSWORD '{safe_password}'"))
    finally:
        await engine.dispose()


async def drop_database(*, database: str, role: str) -> None:
    """Remove a database together with the role that owned it."""
    safe_database = _checked(database)
    safe_role = _checked(role)

    engine = _maintenance_engine()
    try:
        async with engine.connect() as connection:
            # Anybody still connected would keep the database alive.
            await connection.execute(
                text(f'DROP DATABASE IF EXISTS "{safe_database}" WITH (FORCE)')
            )
            await connection.execute(text(f'DROP ROLE IF EXISTS "{safe_role}"'))
    finally:
        await engine.dispose()


async def size_of(database: str) -> int:
    """How much room a database takes on the server."""
    safe_database = _checked(database)
    engine = _maintenance_engine()
    try:
        async with engine.connect() as connection:
            result = await connection.execute(
                text("SELECT pg_database_size(:name)"), {"name": safe_database}
            )
            return int(result.scalar_one())
    except SQLAlchemyError:
        # A database that is gone simply takes no room.
        return 0
    finally:
        await engine.dispose()

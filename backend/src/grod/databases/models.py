"""Databases an account asked the platform for."""

import enum
from uuid import UUID

from sqlalchemy import BigInteger, Enum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from grod.db import TimestampedTable

NAME_MAX_LENGTH = 40
IDENTIFIER_MAX_LENGTH = 63
# The name the account gives it; the real names on the server are derived from it.
NAME_PATTERN = r"^[a-z0-9][a-z0-9-]{1,38}[a-z0-9]$"


class DatabaseEngine(enum.StrEnum):
    """What kind of database this is."""

    POSTGRES = "postgres"


class ManagedDatabase(TimestampedTable):
    """One database with its own role, kept for an account."""

    __tablename__ = "managed_databases"
    __table_args__ = (
        UniqueConstraint("owner_id", "name", name="uq_managed_databases_owner_name"),
        UniqueConstraint("database_name", name="uq_managed_databases_database_name"),
    )

    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH), index=True)
    engine: Mapped[DatabaseEngine] = mapped_column(
        Enum(DatabaseEngine, name="database_engine", native_enum=False, length=16),
        default=DatabaseEngine.POSTGRES,
    )
    # What the server really calls the database and the role that owns it.
    database_name: Mapped[str] = mapped_column(String(IDENTIFIER_MAX_LENGTH))
    role_name: Mapped[str] = mapped_column(String(IDENTIFIER_MAX_LENGTH))
    # The password is kept the way secrets are: encrypted with the instance key.
    password_encrypted: Mapped[str] = mapped_column(Text)
    # What the server reported the last time somebody looked.
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)

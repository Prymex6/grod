"""Functions and what happened the last time each one ran."""

import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from grod.db import TimestampedTable

NAME_MAX_LENGTH = 63
SOURCE_MAX_LENGTH = 100_000
NAME_PATTERN = r"^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$"

DEFAULT_TIMEOUT_SECONDS = 10
DEFAULT_MEMORY_MB = 128


class Runtime(enum.StrEnum):
    """The language a function is written in."""

    PYTHON = "python"
    NODE = "node"


class Function(TimestampedTable):
    """One piece of code that runs when somebody calls it."""

    __tablename__ = "functions"
    __table_args__ = (UniqueConstraint("owner_id", "name", name="uq_functions_owner_name"),)

    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH), index=True)
    runtime: Mapped[Runtime] = mapped_column(
        Enum(Runtime, name="function_runtime", native_enum=False, length=16),
        default=Runtime.PYTHON,
    )
    source: Mapped[str] = mapped_column(Text, default="")
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=DEFAULT_TIMEOUT_SECONDS)
    memory_mb: Mapped[int] = mapped_column(Integer, default=DEFAULT_MEMORY_MB)
    # Counters the console shows; the details of one call live in the log below.
    calls: Mapped[int] = mapped_column(Integer, default=0)
    failures: Mapped[int] = mapped_column(Integer, default=0)
    last_called_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    last_duration_ms: Mapped[int | None] = mapped_column(Integer, default=None)
    last_error: Mapped[str] = mapped_column(Text, default="")

"""Checks the platform runs, and what each one found."""

import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from grod.db import TimestampedTable

NAME_MAX_LENGTH = 100
URL_MAX_LENGTH = 500
DEFAULT_INTERVAL_SECONDS = 60
DEFAULT_EXPECTED_STATUS = 200
DEFAULT_TIMEOUT_SECONDS = 10


class CheckState(enum.StrEnum):
    """What the last look found."""

    UNKNOWN = "unknown"  # nobody has looked yet
    UP = "up"
    DOWN = "down"


class Check(TimestampedTable):
    """One address the platform looks at now and then."""

    __tablename__ = "checks"
    __table_args__ = (UniqueConstraint("owner_id", "name", name="uq_checks_owner_name"),)

    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH))
    url: Mapped[str] = mapped_column(String(URL_MAX_LENGTH))
    interval_seconds: Mapped[int] = mapped_column(Integer, default=DEFAULT_INTERVAL_SECONDS)
    expected_status: Mapped[int] = mapped_column(Integer, default=DEFAULT_EXPECTED_STATUS)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=DEFAULT_TIMEOUT_SECONDS)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    state: Mapped[CheckState] = mapped_column(
        Enum(CheckState, name="check_state", native_enum=False, length=16),
        default=CheckState.UNKNOWN,
    )
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    last_duration_ms: Mapped[int | None] = mapped_column(Integer, default=None)
    last_error: Mapped[str] = mapped_column(Text, default="")


class CheckResult(TimestampedTable):
    """One look at one address."""

    __tablename__ = "check_results"

    check_id: Mapped[UUID] = mapped_column(ForeignKey("checks.id", ondelete="CASCADE"), index=True)
    ok: Mapped[bool] = mapped_column(Boolean)
    status_code: Mapped[int | None] = mapped_column(Integer, default=None)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default="")

"""What reports errors, the issues they add up to, and the single reports."""

import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from grod.db import TimestampedTable

NAME_MAX_LENGTH = 100
KIND_MAX_LENGTH = 200
MESSAGE_MAX_LENGTH = 1000
FINGERPRINT_LENGTH = 64
ENVIRONMENT_MAX_LENGTH = 50
RELEASE_MAX_LENGTH = 100
KEY_MAX_LENGTH = 100
# Keys look like the tokens of the platform, so they are easy to tell apart.
KEY_PREFIX = "grodczuj"


class Level(enum.StrEnum):
    """How bad the report is."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    FATAL = "fatal"


class Source(TimestampedTable):
    """One application that reports its errors to the platform."""

    __tablename__ = "error_sources"
    __table_args__ = (
        UniqueConstraint("owner_id", "name", name="uq_error_sources_owner_name"),
        UniqueConstraint("key", name="uq_error_sources_key"),
    )

    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH))
    # The key the application sends with every report; it may be read back,
    # because it only allows writing reports, never reading them.
    key: Mapped[str] = mapped_column(String(KEY_MAX_LENGTH), index=True)


class Issue(TimestampedTable):
    """Reports that look like the same problem, counted together."""

    __tablename__ = "error_issues"
    __table_args__ = (
        UniqueConstraint("source_id", "fingerprint", name="uq_error_issues_fingerprint"),
    )

    source_id: Mapped[UUID] = mapped_column(
        ForeignKey("error_sources.id", ondelete="CASCADE"), index=True
    )
    # What makes two reports the same problem: the kind and where it came from.
    fingerprint: Mapped[str] = mapped_column(String(FINGERPRINT_LENGTH), index=True)
    kind: Mapped[str] = mapped_column(String(KIND_MAX_LENGTH))
    message: Mapped[str] = mapped_column(String(MESSAGE_MAX_LENGTH))
    level: Mapped[Level] = mapped_column(
        Enum(Level, name="error_level", native_enum=False, length=16), default=Level.ERROR
    )
    culprit: Mapped[str] = mapped_column(String(MESSAGE_MAX_LENGTH), default="")
    count: Mapped[int] = mapped_column(Integer, default=0)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)


class Report(TimestampedTable):
    """One error as it was reported."""

    __tablename__ = "error_reports"

    issue_id: Mapped[UUID] = mapped_column(
        ForeignKey("error_issues.id", ondelete="CASCADE"), index=True
    )
    message: Mapped[str] = mapped_column(String(MESSAGE_MAX_LENGTH))
    stack: Mapped[str] = mapped_column(Text, default="")
    environment: Mapped[str] = mapped_column(String(ENVIRONMENT_MAX_LENGTH), default="")
    release: Mapped[str] = mapped_column(String(RELEASE_MAX_LENGTH), default="")
    # Anything else the application wanted to say, as JSON.
    context: Mapped[str] = mapped_column(Text, default="{}")

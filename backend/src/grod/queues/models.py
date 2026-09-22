"""Queues an account keeps. The messages themselves live in Valkey."""

from uuid import UUID

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from grod.db import TimestampedTable

NAME_MAX_LENGTH = 63
NAME_PATTERN = r"^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$"

DEFAULT_VISIBILITY_SECONDS = 30
DEFAULT_MAX_ATTEMPTS = 5


class Queue(TimestampedTable):
    """One queue: a name, and the rules for handing its messages out."""

    __tablename__ = "queues"
    __table_args__ = (UniqueConstraint("owner_id", "name", name="uq_queues_owner_name"),)

    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH), index=True)
    # How long a taken message stays hidden before it comes back.
    visibility_seconds: Mapped[int] = mapped_column(Integer, default=DEFAULT_VISIBILITY_SECONDS)
    # After this many tries a message is set aside instead of going round again.
    max_attempts: Mapped[int] = mapped_column(Integer, default=DEFAULT_MAX_ATTEMPTS)

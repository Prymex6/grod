"""Limits given to one account, where they differ from the instance defaults."""

from uuid import UUID

from sqlalchemy import BigInteger, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from grod.db import TimestampedTable


class AccountLimits(TimestampedTable):
    """What one account may hold, where it was given something else.

    Every column may be empty, and an empty one means "whatever this instance
    gives everybody"; a row exists only for an account that was granted more
    than that, or held to less.
    """

    __tablename__ = "account_limits"
    __table_args__ = (UniqueConstraint("owner_id", name="uq_account_limits_owner"),)

    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    storage_bytes: Mapped[int | None] = mapped_column(BigInteger, default=None)
    buckets: Mapped[int | None] = mapped_column(default=None)
    applications: Mapped[int | None] = mapped_column(default=None)
    functions: Mapped[int | None] = mapped_column(default=None)
    databases: Mapped[int | None] = mapped_column(default=None)
    queues: Mapped[int | None] = mapped_column(default=None)
    workspaces: Mapped[int | None] = mapped_column(default=None)

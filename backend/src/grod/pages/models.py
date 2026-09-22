"""What a project publishes as a static site."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from grod.db import TimestampedTable

BRANCH_MAX_LENGTH = 200
DIRECTORY_MAX_LENGTH = 500
COMMIT_HASH_LENGTH = 40
DEFAULT_DIRECTORY = "public"


class Site(TimestampedTable):
    """The site of one project: which branch and folder it is built from."""

    __tablename__ = "sites"

    # One project publishes at most one site, so the address stays predictable.
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), unique=True, index=True
    )
    branch: Mapped[str] = mapped_column(String(BRANCH_MAX_LENGTH))
    # Folder inside the repository; empty means the whole tree.
    directory: Mapped[str] = mapped_column(String(DIRECTORY_MAX_LENGTH), default=DEFAULT_DIRECTORY)
    enabled: Mapped[bool] = mapped_column(default=True)
    published_commit: Mapped[str | None] = mapped_column(String(COMMIT_HASH_LENGTH), default=None)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

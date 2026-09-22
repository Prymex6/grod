"""What a scan of a repository found, and what was done about it."""

import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from grod.db import TimestampedTable

RULE_MAX_LENGTH = 50
PATH_MAX_LENGTH = 1000
SNIPPET_MAX_LENGTH = 200
COMMIT_LENGTH = 40
# The secret itself is never kept; this is the length of its fingerprint.
FINGERPRINT_LENGTH = 64


class FindingState(enum.StrEnum):
    """Where one finding stands."""

    OPEN = "open"  # it is in the repository now
    IGNORED = "ignored"  # somebody looked and said it is fine
    FIXED = "fixed"  # the last scan no longer found it


class Finding(TimestampedTable):
    """One secret a scan saw in the code of a project.

    The value that matched is never written down — only a fingerprint of it, so
    the same secret moving to another line stays one finding instead of two.
    """

    __tablename__ = "findings"
    __table_args__ = (
        UniqueConstraint("project_id", "rule", "path", "fingerprint", name="uq_findings_address"),
    )

    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    rule: Mapped[str] = mapped_column(String(RULE_MAX_LENGTH), index=True)
    path: Mapped[str] = mapped_column(String(PATH_MAX_LENGTH))
    line: Mapped[int] = mapped_column()
    # The line with the secret starred out, so the console can show where it is.
    snippet: Mapped[str] = mapped_column(String(SNIPPET_MAX_LENGTH))
    fingerprint: Mapped[str] = mapped_column(String(FINGERPRINT_LENGTH))
    commit: Mapped[str] = mapped_column(String(COMMIT_LENGTH))
    state: Mapped[FindingState] = mapped_column(
        Enum(FindingState, name="finding_state", native_enum=False, length=16),
        default=FindingState.OPEN,
        index=True,
    )
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

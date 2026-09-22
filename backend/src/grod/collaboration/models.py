"""Issues and their comments."""

import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from grod.db import TimestampedTable

TITLE_MAX_LENGTH = 200
BODY_MAX_LENGTH = 100_000


class IssueState(enum.StrEnum):
    """An issue is either being worked on or done with."""

    OPEN = "open"
    CLOSED = "closed"


class Issue(TimestampedTable):
    """A task or a bug report inside a project."""

    __tablename__ = "issues"
    __table_args__ = (UniqueConstraint("project_id", "number", name="uq_issues_project_number"),)

    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    # Numbered per project, so people can say "issue 7" and be understood.
    number: Mapped[int] = mapped_column(Integer)
    author_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(TITLE_MAX_LENGTH))
    description: Mapped[str] = mapped_column(Text, default="")
    state: Mapped[IssueState] = mapped_column(
        Enum(IssueState, name="issue_state", native_enum=False, length=16), default=IssueState.OPEN
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class IssueComment(TimestampedTable):
    """One entry of the discussion under an issue."""

    __tablename__ = "issue_comments"

    issue_id: Mapped[UUID] = mapped_column(ForeignKey("issues.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    body: Mapped[str] = mapped_column(Text)


BRANCH_MAX_LENGTH = 200
COMMIT_HASH_LENGTH = 40
# A job of the pipeline is named in the file, so the same limit as there.
JOB_NAME_MAX_LENGTH = 100
PATH_MAX_LENGTH = 1024


class MergeState(enum.StrEnum):
    """Where a merge request stands."""

    OPEN = "open"
    MERGED = "merged"
    CLOSED = "closed"


class MergeRequest(TimestampedTable):
    """A request to merge one branch of a project into another."""

    __tablename__ = "merge_requests"
    __table_args__ = (
        UniqueConstraint("project_id", "number", name="uq_merge_requests_project_number"),
    )

    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    # Numbered per project, the way issues are.
    number: Mapped[int] = mapped_column(Integer)
    author_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(TITLE_MAX_LENGTH))
    description: Mapped[str] = mapped_column(Text, default="")
    source_branch: Mapped[str] = mapped_column(String(BRANCH_MAX_LENGTH))
    target_branch: Mapped[str] = mapped_column(String(BRANCH_MAX_LENGTH))
    state: Mapped[MergeState] = mapped_column(
        Enum(MergeState, name="merge_state", native_enum=False, length=16), default=MergeState.OPEN
    )
    merge_commit: Mapped[str | None] = mapped_column(String(COMMIT_HASH_LENGTH), default=None)
    merged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class MergeRequestComment(TimestampedTable):
    """One entry of a code review."""

    __tablename__ = "merge_request_comments"

    merge_request_id: Mapped[UUID] = mapped_column(
        ForeignKey("merge_requests.id", ondelete="CASCADE"), index=True
    )
    author_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    body: Mapped[str] = mapped_column(Text)
    # Set when the comment belongs to one line of one file.
    file_path: Mapped[str | None] = mapped_column(String(PATH_MAX_LENGTH), default=None)
    line_number: Mapped[int | None] = mapped_column(Integer, default=None)


class QueueState(enum.StrEnum):
    """Where one merge request stands in the queue."""

    WAITING = "waiting"  # in line, nothing built yet
    TESTING = "testing"  # the merge result is being tested
    MERGED = "merged"  # it went in
    FAILED = "failed"  # the tests said no, or the branches clashed
    CANCELLED = "cancelled"  # somebody took it out of the line


# The branches the queue builds to test on; they are thrown away afterwards.
QUEUE_BRANCH_PREFIX = "grod-queue"


class MergeQueueEntry(TimestampedTable):
    """One merge request waiting its turn to be merged.

    The queue exists so that what is tested is the **result** of merging, not
    the branch on its own: a change that passes alone can still break the
    target branch it has not seen.
    """

    __tablename__ = "merge_queue"
    __table_args__ = (
        # One request may stand in line only once at a time. Rows of finished
        # attempts stay for the history, so the index leaves them alone.
        Index(
            "uq_merge_queue_active",
            "merge_request_id",
            unique=True,
            postgresql_where=text("state IN ('waiting', 'testing')"),
        ),
    )

    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    merge_request_id: Mapped[UUID] = mapped_column(
        ForeignKey("merge_requests.id", ondelete="CASCADE"), index=True
    )
    # Who asked for it, so the commit carries a name.
    requested_by_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    state: Mapped[QueueState] = mapped_column(
        Enum(QueueState, name="queue_state", native_enum=False, length=16),
        default=QueueState.WAITING,
        index=True,
    )
    # The merge commit under test, and where the target stood when it was built.
    tested_commit: Mapped[str] = mapped_column(String(COMMIT_HASH_LENGTH), default="")
    base_commit: Mapped[str] = mapped_column(String(COMMIT_HASH_LENGTH), default="")
    pipeline_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("pipelines.id", ondelete="SET NULL"), default=None
    )
    last_error: Mapped[str] = mapped_column(String(2000), default="")


class RequiredCheck(TimestampedTable):
    """A job of the pipeline that has to pass before anything is merged."""

    __tablename__ = "required_checks"
    __table_args__ = (UniqueConstraint("project_id", "job_name", name="uq_required_checks_job"),)

    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    job_name: Mapped[str] = mapped_column(String(JOB_NAME_MAX_LENGTH))


class Approval(TimestampedTable):
    """One person saying the change may go in.

    The commit it was given on is written down, so an approval stops counting
    once new work arrives: what was read is no longer what would be merged.
    """

    __tablename__ = "approvals"
    __table_args__ = (UniqueConstraint("merge_request_id", "user_id", name="uq_approvals_person"),)

    merge_request_id: Mapped[UUID] = mapped_column(
        ForeignKey("merge_requests.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    commit: Mapped[str] = mapped_column(String(COMMIT_HASH_LENGTH), default="")

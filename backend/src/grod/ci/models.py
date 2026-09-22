"""Pipelines, their jobs and the runners that carry them out."""

import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from grod.db import TimestampedTable

REF_MAX_LENGTH = 200
COMMIT_HASH_LENGTH = 40
NAME_MAX_LENGTH = 100
IMAGE_MAX_LENGTH = 200
TOKEN_HASH_MAX_LENGTH = 255
TAGS_MAX_LENGTH = 200


class RunState(enum.StrEnum):
    """Where a pipeline or one of its jobs stands."""

    PENDING = "pending"  # waiting for a runner
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELED = "canceled"


FINISHED_STATES = (RunState.SUCCESS, RunState.FAILED, RunState.CANCELED)


class Pipeline(TimestampedTable):
    """One run of the whole file, for one commit on one branch."""

    __tablename__ = "pipelines"
    __table_args__ = (UniqueConstraint("project_id", "number", name="uq_pipelines_project_number"),)

    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    # Numbered per project, the way issues and merge requests are.
    number: Mapped[int] = mapped_column(Integer)
    ref: Mapped[str] = mapped_column(String(REF_MAX_LENGTH))
    commit: Mapped[str] = mapped_column(String(COMMIT_HASH_LENGTH))
    commit_subject: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH * 5), default="")
    # Empty when a push came in over Git without the platform knowing who pushed.
    triggered_by_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True, default=None
    )
    state: Mapped[RunState] = mapped_column(
        Enum(RunState, name="run_state", native_enum=False, length=16), default=RunState.PENDING
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


PATH_MAX_LENGTH = 1000
MESSAGE_MAX_LENGTH = 500


class Job(TimestampedTable):
    """One job of a pipeline, with the script frozen when it was created."""

    __tablename__ = "jobs"

    pipeline_id: Mapped[UUID] = mapped_column(
        ForeignKey("pipelines.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH))
    stage: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH))
    # The order the stages run in, kept here so the queue is one query.
    stage_order: Mapped[int] = mapped_column(Integer, default=0)
    image: Mapped[str | None] = mapped_column(String(IMAGE_MAX_LENGTH), default=None)
    # The script and the variables as the file had them at that commit.
    script: Mapped[str] = mapped_column(Text, default="")
    variables: Mapped[str] = mapped_column(Text, default="{}")
    state: Mapped[RunState] = mapped_column(
        Enum(RunState, name="run_state", native_enum=False, length=16), default=RunState.PENDING
    )
    log: Mapped[str] = mapped_column(Text, default="")
    runner_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("runners.id", ondelete="SET NULL"), index=True, default=None
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class Runner(TimestampedTable):
    """A machine that asks the platform for jobs and runs them."""

    __tablename__ = "runners"

    name: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH))
    # A runner belongs to one project; an instance runner has none.
    project_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, default=None
    )
    # Identifier and secret work the way access tokens do: only the hash is kept.
    token_hash: Mapped[str] = mapped_column(String(TOKEN_HASH_MAX_LENGTH))
    tags: Mapped[str] = mapped_column(String(TAGS_MAX_LENGTH), default="")
    active: Mapped[bool] = mapped_column(default=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class JobFinding(TimestampedTable):
    """One remark a tool made about one line, pulled out of a job log.

    Kept beside the job rather than as a comment, so a new run replaces the
    old remarks instead of piling another copy onto the conversation.
    """

    __tablename__ = "job_findings"

    job_id: Mapped[UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    # Which job said it, so the console can name the tool.
    tool: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH))
    path: Mapped[str] = mapped_column(String(PATH_MAX_LENGTH), index=True)
    line: Mapped[int] = mapped_column(Integer)
    column: Mapped[int | None] = mapped_column(Integer, default=None)
    message: Mapped[str] = mapped_column(String(MESSAGE_MAX_LENGTH))

"""One workspace: a container holding the code of a branch."""

import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from grod.db import TimestampedTable

NAME_MAX_LENGTH = 63
NAME_PATTERN = r"^[a-z0-9][a-z0-9-]{1,62}$"
IMAGE_MAX_LENGTH = 255
BRANCH_MAX_LENGTH = 255
COMMIT_LENGTH = 40
CONTAINER_ID_MAX_LENGTH = 64

DEFAULT_IMAGE = "python:3.14-slim"
DEFAULT_MEMORY_MB = 1024
DEFAULT_CPUS = "1.0"
# Where the code is put inside the container.
WORKDIR = "/workspaces"


class WorkspaceState(enum.StrEnum):
    """Where a workspace stands."""

    STOPPED = "stopped"
    RUNNING = "running"
    FAILED = "failed"


class Workspace(TimestampedTable):
    """A place to work on one branch of one project."""

    __tablename__ = "workspaces"
    __table_args__ = (UniqueConstraint("owner_id", "name", name="uq_workspaces_owner_name"),)

    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH))
    branch: Mapped[str] = mapped_column(String(BRANCH_MAX_LENGTH))
    image: Mapped[str] = mapped_column(String(IMAGE_MAX_LENGTH), default=DEFAULT_IMAGE)
    # The commit the code was taken from, so a save knows what it changed.
    commit: Mapped[str] = mapped_column(String(COMMIT_LENGTH), default="")
    container_id: Mapped[str | None] = mapped_column(String(CONTAINER_ID_MAX_LENGTH), default=None)
    state: Mapped[WorkspaceState] = mapped_column(
        Enum(WorkspaceState, name="workspace_state", native_enum=False, length=16),
        default=WorkspaceState.STOPPED,
    )
    last_error: Mapped[str] = mapped_column(String(2000), default="")
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

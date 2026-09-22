"""Applications the platform runs for an account."""

import enum
from uuid import UUID

from sqlalchemy import Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from grod.db import TimestampedTable

NAME_MAX_LENGTH = 63
IMAGE_MAX_LENGTH = 300
COMMAND_MAX_LENGTH = 1000
CONTAINER_ID_LENGTH = 64
# An application is named like a host name, so it can later stand in an address.
NAME_PATTERN = r"^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$"

DEFAULT_MEMORY_MB = 256
DEFAULT_CPUS = 0.5


class AppState(enum.StrEnum):
    """Where an application stands."""

    STOPPED = "stopped"
    RUNNING = "running"
    FAILED = "failed"


class Application(TimestampedTable):
    """One container the platform keeps running for an account."""

    __tablename__ = "applications"
    __table_args__ = (UniqueConstraint("owner_id", "name", name="uq_applications_owner_name"),)

    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH), index=True)
    image: Mapped[str] = mapped_column(String(IMAGE_MAX_LENGTH))
    # Empty means the image decides what to run.
    command: Mapped[str] = mapped_column(String(COMMAND_MAX_LENGTH), default="")
    # Variables as JSON; secrets belong in the vault, not here.
    environment: Mapped[str] = mapped_column(Text, default="{}")
    # The port the application listens on inside the container, and the one
    # the platform opened for it on the host.
    port: Mapped[int | None] = mapped_column(Integer, default=None)
    host_port: Mapped[int | None] = mapped_column(Integer, default=None)
    memory_mb: Mapped[int] = mapped_column(Integer, default=DEFAULT_MEMORY_MB)
    cpus: Mapped[str] = mapped_column(String(16), default=str(DEFAULT_CPUS))
    state: Mapped[AppState] = mapped_column(
        Enum(AppState, name="app_state", native_enum=False, length=16), default=AppState.STOPPED
    )
    container_id: Mapped[str | None] = mapped_column(String(CONTAINER_ID_LENGTH), default=None)
    # What the engine said when starting failed, so the console can show it.
    last_error: Mapped[str] = mapped_column(Text, default="")

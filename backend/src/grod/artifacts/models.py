"""Secrets of a project and the files it publishes as packages."""

from uuid import UUID

from sqlalchemy import BigInteger, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from grod.db import TimestampedTable

NAME_MAX_LENGTH = 100
VALUE_MAX_LENGTH = 10_000
VERSION_MAX_LENGTH = 100
FILENAME_MAX_LENGTH = 255
DIGEST_LENGTH = 64
# A secret whose name says so is never printed by a job, even by mistake.
NAME_PATTERN = r"^[A-Za-z_][A-Za-z0-9_]*$"


class Secret(TimestampedTable):
    """One value a project keeps out of its repository."""

    __tablename__ = "secrets"
    __table_args__ = (UniqueConstraint("project_id", "name", name="uq_secrets_project_name"),)

    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH))
    # Encrypted with the key of the instance; never stored or logged in clear.
    value_encrypted: Mapped[str] = mapped_column(Text)
    # A masked secret is replaced by stars in job logs.
    masked: Mapped[bool] = mapped_column(default=True)
    # A protected secret only reaches jobs of protected branches.
    protected: Mapped[bool] = mapped_column(default=False)


class Package(TimestampedTable):
    """One file a project published, found by its name and version."""

    __tablename__ = "packages"
    __table_args__ = (
        UniqueConstraint("project_id", "name", "version", "filename", name="uq_packages_address"),
    )

    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH), index=True)
    version: Mapped[str] = mapped_column(String(VERSION_MAX_LENGTH))
    filename: Mapped[str] = mapped_column(String(FILENAME_MAX_LENGTH))
    size: Mapped[int] = mapped_column(BigInteger)
    # SHA-256 of the contents, so a download can be checked.
    digest: Mapped[str] = mapped_column(String(DIGEST_LENGTH))
    uploaded_by_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True, default=None
    )

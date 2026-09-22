"""Projects and the access tokens used to reach them over Git."""

import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import ARRAY, DateTime, Enum, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from grod.db import TimestampedTable

SLUG_MAX_LENGTH = 64
NAME_MAX_LENGTH = 100
DESCRIPTION_MAX_LENGTH = 500
SLUG_PATTERN = r"^[a-z0-9][a-z0-9._-]*$"
DEFAULT_BRANCH = "main"

TOKEN_NAME_MAX_LENGTH = 100
SSH_KEY_NAME_MAX_LENGTH = 100
LOGIN_REFERENCE_MAX_LENGTH = 64
BRANCH_PATTERN_MAX_LENGTH = 100
SSH_KEY_MAX_LENGTH = 4096
FINGERPRINT_MAX_LENGTH = 100


class Role(enum.StrEnum):
    """What a member may do in a project."""

    GUEST = "guest"  # read, and take part in issues
    DEVELOPER = "developer"  # also push to branches
    MAINTAINER = "maintainer"  # also change the project settings


class Visibility(enum.StrEnum):
    """Who may read a project."""

    PRIVATE = "private"
    INTERNAL = "internal"
    PUBLIC = "public"


class Project(TimestampedTable):
    """A repository with its metadata; the Git data lives on disk."""

    __tablename__ = "projects"
    __table_args__ = (
        # A slug is unique inside one namespace: an account or a group.
        Index(
            "uq_projects_owner_slug",
            "owner_id",
            "slug",
            unique=True,
            postgresql_where=text("group_id IS NULL"),
        ),
        Index(
            "uq_projects_group_slug",
            "group_id",
            "slug",
            unique=True,
            postgresql_where=text("group_id IS NOT NULL"),
        ),
    )

    # Whoever created it; for a group project this is still the author.
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    group_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"), index=True, default=None
    )
    slug: Mapped[str] = mapped_column(String(SLUG_MAX_LENGTH), index=True)
    name: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH))
    description: Mapped[str] = mapped_column(String(DESCRIPTION_MAX_LENGTH), default="")
    visibility: Mapped[Visibility] = mapped_column(
        Enum(Visibility, name="project_visibility", native_enum=False, length=16),
        default=Visibility.PRIVATE,
    )
    default_branch: Mapped[str] = mapped_column(String(SLUG_MAX_LENGTH), default=DEFAULT_BRANCH)
    # How many people have to say yes before a merge request may go in.
    # Zero means nobody has to, which is what a project starts with.
    required_approvals: Mapped[int] = mapped_column(default=0)


class AccessToken(TimestampedTable):
    """A personal access token: the password Git asks for when pushing."""

    __tablename__ = "access_tokens"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(TOKEN_NAME_MAX_LENGTH))
    # The secret half is stored hashed; the row is found by its identifier.
    secret_hash: Mapped[str] = mapped_column(String(255))
    scopes: Mapped[list[str]] = mapped_column(ARRAY(String(32)))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class SshKey(TimestampedTable):
    """A public key that may reach the repositories over SSH."""

    __tablename__ = "ssh_keys"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(SSH_KEY_NAME_MAX_LENGTH))
    algorithm: Mapped[str] = mapped_column(String(64))
    public_key: Mapped[str] = mapped_column(String(SSH_KEY_MAX_LENGTH))
    # The fingerprint identifies the key on sign-in, so it must be unique.
    fingerprint: Mapped[str] = mapped_column(
        String(FINGERPRINT_MAX_LENGTH), unique=True, index=True
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class ProtectedBranch(TimestampedTable):
    """Branches whose history may not be rewritten or deleted."""

    __tablename__ = "protected_branches"
    __table_args__ = (
        UniqueConstraint("project_id", "pattern", name="uq_protected_branches_project_pattern"),
    )

    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    # A shell pattern, so "release/*" protects a whole family of branches.
    pattern: Mapped[str] = mapped_column(String(BRANCH_PATTERN_MAX_LENGTH))


class ProjectMember(TimestampedTable):
    """Someone besides the owner who takes part in a project."""

    __tablename__ = "project_members"
    __table_args__ = (UniqueConstraint("project_id", "user_id", name="uq_project_members"),)

    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[Role] = mapped_column(
        Enum(Role, name="project_role", native_enum=False, length=16), default=Role.GUEST
    )


class ProjectStar(TimestampedTable):
    """Somebody marked a project as worth watching."""

    __tablename__ = "project_stars"
    __table_args__ = (UniqueConstraint("project_id", "user_id", name="uq_project_stars"),)

    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

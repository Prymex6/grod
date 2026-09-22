"""Grants, and the machine identities that can hold them."""

import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from grod.db import TimestampedTable

NAME_MAX_LENGTH = 100
TOKEN_HASH_MAX_LENGTH = 255
# A service account proves who it is with a token shaped like the other ones.
KEY_PREFIX = "grodsrv"


class ResourceKind(enum.StrEnum):
    """The kinds of thing a grant can be about."""

    BUCKET = "bucket"
    APPLICATION = "application"
    FUNCTION = "function"
    DATABASE = "database"
    QUEUE = "queue"
    ROUTE = "route"
    CHECK = "check"
    ERROR_SOURCE = "error_source"
    API_DOC = "api_doc"


class Role(enum.StrEnum):
    """What a grant allows, from the least to the most."""

    VIEWER = "viewer"  # look, and nothing more
    OPERATOR = "operator"  # use it: write data, start it, call it
    ADMIN = "admin"  # change how it is set up, and take it down


# The order the roles stand in, so one can be compared with another.
ROLE_ORDER = {Role.VIEWER: 1, Role.OPERATOR: 2, Role.ADMIN: 3}


class SubjectKind(enum.StrEnum):
    """Who a grant is given to."""

    USER = "user"
    GROUP = "group"
    SERVICE = "service"


class Grant(TimestampedTable):
    """One permission: somebody may do something with one resource."""

    __tablename__ = "grants"
    __table_args__ = (
        UniqueConstraint(
            "resource_kind",
            "resource_id",
            "subject_kind",
            "subject_id",
            name="uq_grants_resource_subject",
        ),
    )

    resource_kind: Mapped[ResourceKind] = mapped_column(
        Enum(ResourceKind, name="resource_kind", native_enum=False, length=20), index=True
    )
    resource_id: Mapped[UUID] = mapped_column(index=True)
    subject_kind: Mapped[SubjectKind] = mapped_column(
        Enum(SubjectKind, name="subject_kind", native_enum=False, length=16)
    )
    subject_id: Mapped[UUID] = mapped_column(index=True)
    role: Mapped[Role] = mapped_column(
        Enum(Role, name="grant_role", native_enum=False, length=16), default=Role.VIEWER
    )
    # Who handed the permission out, so the trail is not lost.
    granted_by_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None
    )


class ServiceAccount(TimestampedTable):
    """A machine identity: an application that acts on its own."""

    __tablename__ = "service_accounts"
    __table_args__ = (UniqueConstraint("owner_id", "name", name="uq_service_accounts_owner_name"),)

    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH))
    # Only the hash is kept, the way access tokens are.
    token_hash: Mapped[str] = mapped_column(String(TOKEN_HASH_MAX_LENGTH))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

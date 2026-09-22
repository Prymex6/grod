"""Groups: a shared namespace that owns projects, like an organisation."""

import enum
from uuid import UUID

from sqlalchemy import Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from grod.db import TimestampedTable
from grod.repositories.models import (
    DESCRIPTION_MAX_LENGTH,
    NAME_MAX_LENGTH,
    SLUG_MAX_LENGTH,
    Visibility,
)


class GroupRole(enum.StrEnum):
    """What a member may do in a group and in every project it owns."""

    GUEST = "guest"  # read the projects of the group
    DEVELOPER = "developer"  # also push to them
    MAINTAINER = "maintainer"  # also change their settings and add members
    OWNER = "owner"  # also rename or delete the group itself


class Group(TimestampedTable):
    """A namespace shared by several accounts.

    Its slug lives in the same space as account handles, because both appear
    as the first part of a project address.
    """

    __tablename__ = "groups"

    slug: Mapped[str] = mapped_column(String(SLUG_MAX_LENGTH), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH))
    description: Mapped[str] = mapped_column(String(DESCRIPTION_MAX_LENGTH), default="")
    visibility: Mapped[Visibility] = mapped_column(
        Enum(Visibility, name="group_visibility", native_enum=False, length=16),
        default=Visibility.PRIVATE,
    )
    # Set for a subgroup; a group without a parent sits at the top.
    parent_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"), index=True, default=None
    )


class GroupMember(TimestampedTable):
    """Somebody who takes part in a group."""

    __tablename__ = "group_members"
    __table_args__ = (UniqueConstraint("group_id", "user_id", name="uq_group_members"),)

    group_id: Mapped[UUID] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[GroupRole] = mapped_column(
        Enum(GroupRole, name="group_role", native_enum=False, length=16), default=GroupRole.GUEST
    )

"""Routes: names that stand in front of what the platform runs."""

import enum
from uuid import UUID

from sqlalchemy import Boolean, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from grod.db import TimestampedTable

NAME_MAX_LENGTH = 63
TARGET_MAX_LENGTH = 300
# A route is named like a host name; later it can become one.
NAME_PATTERN = r"^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$"


class RouteTarget(enum.StrEnum):
    """What stands behind a route."""

    APPLICATION = "application"  # an application, by its name
    ADDRESS = "address"  # any address the platform can reach


class Route(TimestampedTable):
    """One name the platform answers at, and what it hands the call to."""

    __tablename__ = "routes"
    __table_args__ = (UniqueConstraint("name", name="uq_routes_name"),)

    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # Unique across the instance, because it is an address.
    name: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH), index=True)
    target_kind: Mapped[RouteTarget] = mapped_column(
        Enum(RouteTarget, name="route_target", native_enum=False, length=16),
        default=RouteTarget.APPLICATION,
    )
    # The name of the application, or the address to hand the call to.
    target: Mapped[str] = mapped_column(String(TARGET_MAX_LENGTH))
    # A private route asks for an account that owns it before it hands anything over.
    public: Mapped[bool] = mapped_column(Boolean, default=True)

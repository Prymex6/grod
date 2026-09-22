"""One offering on the fair: a project template or a ready application."""

import enum
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from grod.db import TimestampedTable

SLUG_MAX_LENGTH = 63
SLUG_PATTERN = r"^[a-z0-9][a-z0-9-]{1,62}$"
TITLE_MAX_LENGTH = 200
DESCRIPTION_MAX_LENGTH = 2000
IMAGE_MAX_LENGTH = 255
BRANCH_MAX_LENGTH = 255


class OfferingKind(enum.StrEnum):
    """What somebody gets when they take it."""

    # A repository to start a project from.
    TEMPLATE = "template"
    # A container image to run in Osada.
    APPLICATION = "application"


class Offering(TimestampedTable):
    """Something one account put out for everybody on this instance.

    A template points at a project whose repository is copied; an application
    points at an image that is started in Osada. Either way, taking it makes
    something of the taker's own — nothing is shared afterwards.
    """

    __tablename__ = "offerings"
    __table_args__ = (UniqueConstraint("slug", name="uq_offerings_slug"),)

    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # The project it was published from; templates are copied out of it.
    project_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, default=None
    )
    kind: Mapped[OfferingKind] = mapped_column(
        String(20), default=OfferingKind.TEMPLATE, index=True
    )
    slug: Mapped[str] = mapped_column(String(SLUG_MAX_LENGTH))
    title: Mapped[str] = mapped_column(String(TITLE_MAX_LENGTH))
    description: Mapped[str] = mapped_column(Text, default="")
    # For a template: which branch is copied. For an application: the image.
    branch: Mapped[str] = mapped_column(String(BRANCH_MAX_LENGTH), default="")
    image: Mapped[str] = mapped_column(String(IMAGE_MAX_LENGTH), default="")
    published: Mapped[bool] = mapped_column(Boolean, default=True)
    taken: Mapped[int] = mapped_column(default=0)

"""API descriptions an account keeps."""

import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from grod.db import TimestampedTable

NAME_MAX_LENGTH = 63
TITLE_MAX_LENGTH = 200
VERSION_MAX_LENGTH = 50
URL_MAX_LENGTH = 500
NAME_PATTERN = r"^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$"


class DocSource(enum.StrEnum):
    """Where the description comes from."""

    UPLOADED = "uploaded"  # somebody sent the document itself
    URL = "url"  # the platform fetches it from an address


class ApiDoc(TimestampedTable):
    """One description of an API, in the OpenAPI form."""

    __tablename__ = "api_docs"
    __table_args__ = (UniqueConstraint("owner_id", "name", name="uq_api_docs_owner_name"),)

    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH), index=True)
    source: Mapped[DocSource] = mapped_column(
        Enum(DocSource, name="doc_source", native_enum=False, length=16),
        default=DocSource.UPLOADED,
    )
    # Set when the platform fetches the document instead of keeping it.
    url: Mapped[str] = mapped_column(String(URL_MAX_LENGTH), default="")
    # The document itself, as JSON; kept even for a URL, as the last good copy.
    document: Mapped[str] = mapped_column(Text, default="{}")
    title: Mapped[str] = mapped_column(String(TITLE_MAX_LENGTH), default="")
    version: Mapped[str] = mapped_column(String(VERSION_MAX_LENGTH), default="")
    # A public description may be read by anybody who knows the address.
    public: Mapped[bool] = mapped_column(Boolean, default=False)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    last_error: Mapped[str] = mapped_column(Text, default="")

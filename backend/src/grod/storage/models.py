"""Buckets and the objects they hold."""

import enum
from uuid import UUID

from sqlalchemy import BigInteger, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from grod.db import TimestampedTable

NAME_MAX_LENGTH = 63
KEY_MAX_LENGTH = 1024
CONTENT_TYPE_MAX_LENGTH = 200
DIGEST_LENGTH = 64
# Bucket names look like host names, so they can later stand in an address.
NAME_PATTERN = r"^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$"


class BucketAccess(enum.StrEnum):
    """Who may read what a bucket holds."""

    PRIVATE = "private"  # only the account that owns it
    PUBLIC = "public"  # anybody with the address


class Bucket(TimestampedTable):
    """A named place one account keeps files in."""

    __tablename__ = "buckets"
    __table_args__ = (UniqueConstraint("name", name="uq_buckets_name"),)

    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # Unique across the instance, the way S3 bucket names are.
    name: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH), index=True)
    access: Mapped[BucketAccess] = mapped_column(
        Enum(BucketAccess, name="bucket_access", native_enum=False, length=16),
        default=BucketAccess.PRIVATE,
    )


class StoredObject(TimestampedTable):
    """One file inside a bucket, found by its key."""

    __tablename__ = "stored_objects"
    __table_args__ = (UniqueConstraint("bucket_id", "key", name="uq_stored_objects_key"),)

    bucket_id: Mapped[UUID] = mapped_column(
        ForeignKey("buckets.id", ondelete="CASCADE"), index=True
    )
    # A key may contain slashes; it is a name, not a path on disk.
    key: Mapped[str] = mapped_column(String(KEY_MAX_LENGTH), index=True)
    size: Mapped[int] = mapped_column(BigInteger)
    content_type: Mapped[str] = mapped_column(
        String(CONTENT_TYPE_MAX_LENGTH), default="application/octet-stream"
    )
    digest: Mapped[str] = mapped_column(String(DIGEST_LENGTH))

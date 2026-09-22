"""What a container image is made of, kept per project.

An image is a manifest plus the blobs it points at, and a tag is a name for one
manifest. Everything hangs off the project, so the rights that decide who may
push to the repository decide who may push an image too.
"""

from uuid import UUID

from sqlalchemy import BigInteger, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from grod.db import TimestampedTable

# "sha256:" and sixty-four hexadecimal characters.
DIGEST_MAX_LENGTH = 71
DIGEST_PATTERN = r"^sha256:[0-9a-f]{64}$"
TAG_MAX_LENGTH = 128
TAG_PATTERN = r"^[A-Za-z0-9_][A-Za-z0-9._-]{0,127}$"
CONTENT_TYPE_MAX_LENGTH = 255
# A manifest is a small JSON document; the layers live in blobs.
MANIFEST_MAX_BYTES = 4 * 1024 * 1024


class ContainerBlob(TimestampedTable):
    """One piece of an image: a layer, or the configuration."""

    __tablename__ = "container_blobs"
    __table_args__ = (UniqueConstraint("project_id", "digest", name="uq_container_blobs_address"),)

    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    digest: Mapped[str] = mapped_column(String(DIGEST_MAX_LENGTH), index=True)
    size: Mapped[int] = mapped_column(BigInteger)


class ContainerManifest(TimestampedTable):
    """The document that says which blobs make up one image."""

    __tablename__ = "container_manifests"
    __table_args__ = (
        UniqueConstraint("project_id", "digest", name="uq_container_manifests_address"),
    )

    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    digest: Mapped[str] = mapped_column(String(DIGEST_MAX_LENGTH), index=True)
    content_type: Mapped[str] = mapped_column(String(CONTENT_TYPE_MAX_LENGTH))
    # Kept byte for byte: the digest is taken over exactly what came in.
    body: Mapped[str] = mapped_column(Text)
    size: Mapped[int] = mapped_column(BigInteger)


class ContainerTag(TimestampedTable):
    """A name for one manifest, the way `:latest` names one."""

    __tablename__ = "container_tags"
    __table_args__ = (UniqueConstraint("project_id", "name", name="uq_container_tags_name"),)

    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(TAG_MAX_LENGTH))
    manifest_id: Mapped[UUID] = mapped_column(
        ForeignKey("container_manifests.id", ondelete="CASCADE"), index=True
    )

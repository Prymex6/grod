"""Create the container registry of a project

Revision ID: 0026
Revises: 0025
Create Date: 2026-09-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMP = sa.DateTime(timezone=True)
DIGEST_LENGTH = 71


def upgrade() -> None:
    op.create_table(
        "container_blobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("digest", sa.String(length=DIGEST_LENGTH), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("project_id", "digest", name="uq_container_blobs_address"),
    )
    op.create_index(op.f("ix_container_blobs_project_id"), "container_blobs", ["project_id"])
    op.create_index(op.f("ix_container_blobs_digest"), "container_blobs", ["digest"])

    op.create_table(
        "container_manifests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("digest", sa.String(length=DIGEST_LENGTH), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("project_id", "digest", name="uq_container_manifests_address"),
    )
    op.create_index(
        op.f("ix_container_manifests_project_id"), "container_manifests", ["project_id"]
    )
    op.create_index(op.f("ix_container_manifests_digest"), "container_manifests", ["digest"])

    op.create_table(
        "container_tags",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("manifest_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["manifest_id"], ["container_manifests.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("project_id", "name", name="uq_container_tags_name"),
    )
    op.create_index(op.f("ix_container_tags_project_id"), "container_tags", ["project_id"])
    op.create_index(op.f("ix_container_tags_manifest_id"), "container_tags", ["manifest_id"])


def downgrade() -> None:
    op.drop_table("container_tags")
    op.drop_table("container_manifests")
    op.drop_table("container_blobs")

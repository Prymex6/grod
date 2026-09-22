"""Create the buckets of Spichlerz and their objects

Revision ID: 0016
Revises: 0015
Create Date: 2026-09-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "buckets",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=63), nullable=False),
        sa.Column(
            "access",
            sa.Enum("private", "public", name="bucket_access", native_enum=False),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("name", name="uq_buckets_name"),
    )
    op.create_index(op.f("ix_buckets_owner_id"), "buckets", ["owner_id"])
    op.create_index(op.f("ix_buckets_name"), "buckets", ["name"])

    op.create_table(
        "stored_objects",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.Column("bucket_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=1024), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("content_type", sa.String(length=200), nullable=False),
        sa.Column("digest", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["bucket_id"], ["buckets.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("bucket_id", "key", name="uq_stored_objects_key"),
    )
    op.create_index(op.f("ix_stored_objects_bucket_id"), "stored_objects", ["bucket_id"])
    op.create_index(op.f("ix_stored_objects_key"), "stored_objects", ["key"])


def downgrade() -> None:
    op.drop_table("stored_objects")
    op.drop_table("buckets")

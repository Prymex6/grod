"""Create the applications Osada runs

Revision ID: 0017
Revises: 0016
Create Date: 2026-09-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "applications",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=63), nullable=False),
        sa.Column("image", sa.String(length=300), nullable=False),
        sa.Column("command", sa.String(length=1000), nullable=False),
        sa.Column("environment", sa.Text(), nullable=False),
        sa.Column("port", sa.Integer(), nullable=True),
        sa.Column("host_port", sa.Integer(), nullable=True),
        sa.Column("memory_mb", sa.Integer(), nullable=False),
        sa.Column("cpus", sa.String(length=16), nullable=False),
        sa.Column(
            "state",
            sa.Enum("stopped", "running", "failed", name="app_state", native_enum=False),
            nullable=False,
        ),
        sa.Column("container_id", sa.String(length=64), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("owner_id", "name", name="uq_applications_owner_name"),
    )
    op.create_index(op.f("ix_applications_owner_id"), "applications", ["owner_id"])
    op.create_index(op.f("ix_applications_name"), "applications", ["name"])


def downgrade() -> None:
    op.drop_table("applications")

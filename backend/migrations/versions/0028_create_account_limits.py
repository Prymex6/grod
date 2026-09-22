"""Create the limits given to single accounts

Revision ID: 0028
Revises: 0027
Create Date: 2026-09-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "account_limits",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("storage_bytes", sa.BigInteger(), nullable=True),
        sa.Column("buckets", sa.Integer(), nullable=True),
        sa.Column("applications", sa.Integer(), nullable=True),
        sa.Column("functions", sa.Integer(), nullable=True),
        sa.Column("databases", sa.Integer(), nullable=True),
        sa.Column("queues", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("owner_id", name="uq_account_limits_owner"),
    )
    op.create_index(op.f("ix_account_limits_owner_id"), "account_limits", ["owner_id"])


def downgrade() -> None:
    op.drop_table("account_limits")

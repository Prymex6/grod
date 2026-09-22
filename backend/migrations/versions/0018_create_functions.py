"""Create the functions of Młyn

Revision ID: 0018
Revises: 0017
Create Date: 2026-09-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "functions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=63), nullable=False),
        sa.Column(
            "runtime",
            sa.Enum("python", "node", name="function_runtime", native_enum=False),
            nullable=False,
        ),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("memory_mb", sa.Integer(), nullable=False),
        sa.Column("calls", sa.Integer(), nullable=False),
        sa.Column("failures", sa.Integer(), nullable=False),
        sa.Column("last_called_at", TIMESTAMP, nullable=True),
        sa.Column("last_duration_ms", sa.Integer(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("owner_id", "name", name="uq_functions_owner_name"),
    )
    op.create_index(op.f("ix_functions_owner_id"), "functions", ["owner_id"])
    op.create_index(op.f("ix_functions_name"), "functions", ["name"])


def downgrade() -> None:
    op.drop_table("functions")

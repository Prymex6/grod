"""Create the checks of Strażnica

Revision ID: 0022
Revises: 0021
Create Date: 2026-09-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "checks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("interval_seconds", sa.Integer(), nullable=False),
        sa.Column("expected_status", sa.Integer(), nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column(
            "state",
            sa.Enum("unknown", "up", "down", name="check_state", native_enum=False),
            nullable=False,
        ),
        sa.Column("last_checked_at", TIMESTAMP, nullable=True),
        sa.Column("last_duration_ms", sa.Integer(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("owner_id", "name", name="uq_checks_owner_name"),
    )
    op.create_index(op.f("ix_checks_owner_id"), "checks", ["owner_id"])

    op.create_table(
        "check_results",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.Column("check_id", sa.Uuid(), nullable=False),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["check_id"], ["checks.id"], ondelete="CASCADE"),
    )
    op.create_index(op.f("ix_check_results_check_id"), "check_results", ["check_id"])


def downgrade() -> None:
    op.drop_table("check_results")
    op.drop_table("checks")

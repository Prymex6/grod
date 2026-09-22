"""Create what the tools said about single lines

Revision ID: 0034
Revises: 0033
Create Date: 2026-09-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0034"
down_revision: str | None = "0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "job_findings",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("tool", sa.String(length=100), nullable=False),
        sa.Column("path", sa.String(length=1000), nullable=False),
        sa.Column("line", sa.Integer(), nullable=False),
        sa.Column("column", sa.Integer(), nullable=True),
        sa.Column("message", sa.String(length=500), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
    )
    op.create_index(op.f("ix_job_findings_job_id"), "job_findings", ["job_id"])
    op.create_index(op.f("ix_job_findings_path"), "job_findings", ["path"])


def downgrade() -> None:
    op.drop_table("job_findings")

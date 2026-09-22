"""Create what a scan of a repository found

Revision ID: 0027
Revises: 0026
Create Date: 2026-09-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "findings",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("rule", sa.String(length=50), nullable=False),
        sa.Column("path", sa.String(length=1000), nullable=False),
        sa.Column("line", sa.Integer(), nullable=False),
        sa.Column("snippet", sa.String(length=200), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("commit", sa.String(length=40), nullable=False),
        sa.Column(
            "state",
            sa.Enum("open", "ignored", "fixed", name="finding_state", native_enum=False),
            nullable=False,
        ),
        sa.Column("last_seen_at", TIMESTAMP, nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "project_id", "rule", "path", "fingerprint", name="uq_findings_address"
        ),
    )
    op.create_index(op.f("ix_findings_project_id"), "findings", ["project_id"])
    op.create_index(op.f("ix_findings_rule"), "findings", ["rule"])
    op.create_index(op.f("ix_findings_state"), "findings", ["state"])


def downgrade() -> None:
    op.drop_table("findings")

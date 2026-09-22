"""Create what Czujka keeps: sources, issues and reports

Revision ID: 0023
Revises: 0022
Create Date: 2026-09-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "error_sources",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("owner_id", "name", name="uq_error_sources_owner_name"),
        sa.UniqueConstraint("key", name="uq_error_sources_key"),
    )
    op.create_index(op.f("ix_error_sources_owner_id"), "error_sources", ["owner_id"])
    op.create_index(op.f("ix_error_sources_key"), "error_sources", ["key"])

    op.create_table(
        "error_issues",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=200), nullable=False),
        sa.Column("message", sa.String(length=1000), nullable=False),
        sa.Column(
            "level",
            sa.Enum("info", "warning", "error", "fatal", name="error_level", native_enum=False),
            nullable=False,
        ),
        sa.Column("culprit", sa.String(length=1000), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("first_seen_at", TIMESTAMP, nullable=False),
        sa.Column("last_seen_at", TIMESTAMP, nullable=False),
        sa.Column("resolved", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["error_sources.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("source_id", "fingerprint", name="uq_error_issues_fingerprint"),
    )
    op.create_index(op.f("ix_error_issues_source_id"), "error_issues", ["source_id"])
    op.create_index(op.f("ix_error_issues_fingerprint"), "error_issues", ["fingerprint"])

    op.create_table(
        "error_reports",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.Column("issue_id", sa.Uuid(), nullable=False),
        sa.Column("message", sa.String(length=1000), nullable=False),
        sa.Column("stack", sa.Text(), nullable=False),
        sa.Column("environment", sa.String(length=50), nullable=False),
        sa.Column("release", sa.String(length=100), nullable=False),
        sa.Column("context", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["issue_id"], ["error_issues.id"], ondelete="CASCADE"),
    )
    op.create_index(op.f("ix_error_reports_issue_id"), "error_reports", ["issue_id"])


def downgrade() -> None:
    op.drop_table("error_reports")
    op.drop_table("error_issues")
    op.drop_table("error_sources")

"""Create the static sites of projects

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "sites",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("branch", sa.String(length=200), nullable=False),
        sa.Column("directory", sa.String(length=500), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("published_commit", sa.String(length=40), nullable=True),
        sa.Column("published_at", TIMESTAMP, nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
    )
    op.create_index(op.f("ix_sites_project_id"), "sites", ["project_id"], unique=True)


def downgrade() -> None:
    op.drop_table("sites")

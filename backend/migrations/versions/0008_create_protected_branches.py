"""Create the protected_branches table

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "protected_branches",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("pattern", sa.String(length=100), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("project_id", "pattern", name="uq_protected_branches_project_pattern"),
    )
    op.create_index(op.f("ix_protected_branches_project_id"), "protected_branches", ["project_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_protected_branches_project_id"), table_name="protected_branches")
    op.drop_table("protected_branches")

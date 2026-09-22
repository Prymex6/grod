"""Create the workspaces of Warsztat

Revision ID: 0029
Revises: 0028
Create Date: 2026-09-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "workspaces",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=63), nullable=False),
        sa.Column("branch", sa.String(length=255), nullable=False),
        sa.Column("image", sa.String(length=255), nullable=False),
        sa.Column("commit", sa.String(length=40), nullable=False),
        sa.Column("container_id", sa.String(length=64), nullable=True),
        sa.Column(
            "state",
            sa.Enum("stopped", "running", "failed", name="workspace_state", native_enum=False),
            nullable=False,
        ),
        sa.Column("last_error", sa.String(length=2000), nullable=False),
        sa.Column("last_used_at", TIMESTAMP, nullable=True),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("owner_id", "name", name="uq_workspaces_owner_name"),
    )
    op.create_index(op.f("ix_workspaces_owner_id"), "workspaces", ["owner_id"])
    op.create_index(op.f("ix_workspaces_project_id"), "workspaces", ["project_id"])


def downgrade() -> None:
    op.drop_table("workspaces")

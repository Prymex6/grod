"""Create approvals and the number a project asks for

Revision ID: 0033
Revises: 0032
Create Date: 2026-09-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0033"
down_revision: str | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("required_approvals", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_table(
        "approvals",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.Column("merge_request_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("commit", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(["merge_request_id"], ["merge_requests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("merge_request_id", "user_id", name="uq_approvals_person"),
    )
    op.create_index(op.f("ix_approvals_merge_request_id"), "approvals", ["merge_request_id"])
    op.create_index(op.f("ix_approvals_user_id"), "approvals", ["user_id"])


def downgrade() -> None:
    op.drop_table("approvals")
    op.drop_column("projects", "required_approvals")

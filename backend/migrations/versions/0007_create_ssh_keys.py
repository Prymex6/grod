"""Create the ssh_keys table

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ssh_keys",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("algorithm", sa.String(length=64), nullable=False),
        sa.Column("public_key", sa.String(length=4096), nullable=False),
        sa.Column("fingerprint", sa.String(length=100), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index(op.f("ix_ssh_keys_user_id"), "ssh_keys", ["user_id"])
    op.create_index(op.f("ix_ssh_keys_fingerprint"), "ssh_keys", ["fingerprint"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_ssh_keys_fingerprint"), table_name="ssh_keys")
    op.drop_index(op.f("ix_ssh_keys_user_id"), table_name="ssh_keys")
    op.drop_table("ssh_keys")

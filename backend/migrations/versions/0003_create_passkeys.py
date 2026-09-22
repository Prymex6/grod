"""Create the passkeys table

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "passkeys",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("credential_id", sa.LargeBinary(), nullable=False),
        sa.Column("public_key", sa.LargeBinary(), nullable=False),
        sa.Column("sign_count", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index(op.f("ix_passkeys_user_id"), "passkeys", ["user_id"])
    op.create_index(op.f("ix_passkeys_credential_id"), "passkeys", ["credential_id"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_passkeys_credential_id"), table_name="passkeys")
    op.drop_index(op.f("ix_passkeys_user_id"), table_name="passkeys")
    op.drop_table("passkeys")

"""Create the oauth_grants table

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "oauth_grants",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("scopes", sa.ARRAY(sa.String(length=64)), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["client_id"], ["oauth_clients.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "client_id", name="uq_oauth_grants_user_client"),
    )
    op.create_index(op.f("ix_oauth_grants_user_id"), "oauth_grants", ["user_id"])
    op.create_index(op.f("ix_oauth_grants_client_id"), "oauth_grants", ["client_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_oauth_grants_client_id"), table_name="oauth_grants")
    op.drop_index(op.f("ix_oauth_grants_user_id"), table_name="oauth_grants")
    op.drop_table("oauth_grants")

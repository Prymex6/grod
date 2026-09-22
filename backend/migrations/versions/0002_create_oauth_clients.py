"""Create the oauth_clients table

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "oauth_clients",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("client_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("client_secret_hash", sa.String(length=255), nullable=True),
        sa.Column("redirect_uris", sa.ARRAY(sa.String(length=2048)), nullable=False),
        sa.Column("scopes", sa.ARRAY(sa.String(length=64)), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index(op.f("ix_oauth_clients_client_id"), "oauth_clients", ["client_id"], unique=True)
    op.create_index(op.f("ix_oauth_clients_owner_id"), "oauth_clients", ["owner_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_oauth_clients_owner_id"), table_name="oauth_clients")
    op.drop_index(op.f("ix_oauth_clients_client_id"), table_name="oauth_clients")
    op.drop_table("oauth_clients")

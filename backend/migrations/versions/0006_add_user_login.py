"""Give every account a handle for repository addresses

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("login", sa.String(length=64), nullable=True))
    # Existing accounts get a handle from the local part of their address.
    op.execute(
        """
        UPDATE users
        SET login = regexp_replace(split_part(email, '@', 1), '[^a-z0-9._-]+', '-', 'g')
        WHERE login IS NULL
        """
    )
    op.alter_column("users", "login", nullable=False)
    op.create_index(op.f("ix_users_login"), "users", ["login"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_users_login"), table_name="users")
    op.drop_column("users", "login")

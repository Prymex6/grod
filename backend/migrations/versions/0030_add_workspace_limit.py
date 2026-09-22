"""Add the workspace limit to the limits of an account

Revision ID: 0030
Revises: 0029
Create Date: 2026-09-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0030"
down_revision: str | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("account_limits", sa.Column("workspaces", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("account_limits", "workspaces")

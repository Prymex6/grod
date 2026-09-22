"""Create the routes of Drogowskaz

Revision ID: 0021
Revises: 0020
Create Date: 2026-09-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "routes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=63), nullable=False),
        sa.Column(
            "target_kind",
            sa.Enum("application", "address", name="route_target", native_enum=False),
            nullable=False,
        ),
        sa.Column("target", sa.String(length=300), nullable=False),
        sa.Column("public", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("name", name="uq_routes_name"),
    )
    op.create_index(op.f("ix_routes_owner_id"), "routes", ["owner_id"])
    op.create_index(op.f("ix_routes_name"), "routes", ["name"])


def downgrade() -> None:
    op.drop_table("routes")

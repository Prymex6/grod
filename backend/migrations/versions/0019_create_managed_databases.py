"""Create the databases Księgi hands out

Revision ID: 0019
Revises: 0018
Create Date: 2026-09-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "managed_databases",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=40), nullable=False),
        sa.Column(
            "engine",
            sa.Enum("postgres", name="database_engine", native_enum=False),
            nullable=False,
        ),
        sa.Column("database_name", sa.String(length=63), nullable=False),
        sa.Column("role_name", sa.String(length=63), nullable=False),
        sa.Column("password_encrypted", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("owner_id", "name", name="uq_managed_databases_owner_name"),
        sa.UniqueConstraint("database_name", name="uq_managed_databases_database_name"),
    )
    op.create_index(op.f("ix_managed_databases_owner_id"), "managed_databases", ["owner_id"])
    op.create_index(op.f("ix_managed_databases_name"), "managed_databases", ["name"])


def downgrade() -> None:
    op.drop_table("managed_databases")

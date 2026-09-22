"""Create the grants of IAM and the machine identities

Revision ID: 0025
Revises: 0024
Create Date: 2026-09-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMP = sa.DateTime(timezone=True)
RESOURCE_KINDS = (
    "bucket",
    "application",
    "function",
    "database",
    "queue",
    "route",
    "check",
    "error_source",
    "api_doc",
)


def upgrade() -> None:
    op.create_table(
        "service_accounts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("token_hash", sa.String(length=255), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("last_used_at", TIMESTAMP, nullable=True),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("owner_id", "name", name="uq_service_accounts_owner_name"),
    )
    op.create_index(op.f("ix_service_accounts_owner_id"), "service_accounts", ["owner_id"])

    op.create_table(
        "grants",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.Column(
            "resource_kind",
            sa.Enum(*RESOURCE_KINDS, name="resource_kind", native_enum=False),
            nullable=False,
        ),
        sa.Column("resource_id", sa.Uuid(), nullable=False),
        sa.Column(
            "subject_kind",
            sa.Enum("user", "group", "service", name="subject_kind", native_enum=False),
            nullable=False,
        ),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column(
            "role",
            sa.Enum("viewer", "operator", "admin", name="grant_role", native_enum=False),
            nullable=False,
        ),
        sa.Column("granted_by_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["granted_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint(
            "resource_kind",
            "resource_id",
            "subject_kind",
            "subject_id",
            name="uq_grants_resource_subject",
        ),
    )
    op.create_index(op.f("ix_grants_resource_kind"), "grants", ["resource_kind"])
    op.create_index(op.f("ix_grants_resource_id"), "grants", ["resource_id"])
    op.create_index(op.f("ix_grants_subject_id"), "grants", ["subject_id"])


def downgrade() -> None:
    op.drop_table("grants")
    op.drop_table("service_accounts")

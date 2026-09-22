"""Create the projects and access_tokens tables

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column(
            "visibility",
            sa.Enum("private", "internal", "public", name="project_visibility", native_enum=False),
            nullable=False,
        ),
        sa.Column("default_branch", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("owner_id", "slug", name="uq_projects_owner_slug"),
    )
    op.create_index(op.f("ix_projects_owner_id"), "projects", ["owner_id"])
    op.create_index(op.f("ix_projects_slug"), "projects", ["slug"])

    op.create_table(
        "access_tokens",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("secret_hash", sa.String(length=255), nullable=False),
        sa.Column("scopes", sa.ARRAY(sa.String(length=32)), nullable=False),
        sa.Column("expires_at", TIMESTAMP, nullable=True),
        sa.Column("last_used_at", TIMESTAMP, nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index(op.f("ix_access_tokens_user_id"), "access_tokens", ["user_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_access_tokens_user_id"), table_name="access_tokens")
    op.drop_table("access_tokens")
    op.drop_index(op.f("ix_projects_slug"), table_name="projects")
    op.drop_index(op.f("ix_projects_owner_id"), table_name="projects")
    op.drop_table("projects")

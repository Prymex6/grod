"""Create groups and give projects a namespace

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMP = sa.DateTime(timezone=True)
VISIBILITY = sa.Enum("private", "internal", "public", name="group_visibility", native_enum=False)


def upgrade() -> None:
    op.create_table(
        "groups",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("visibility", VISIBILITY, nullable=False),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["parent_id"], ["groups.id"], ondelete="CASCADE"),
    )
    op.create_index(op.f("ix_groups_slug"), "groups", ["slug"], unique=True)
    op.create_index(op.f("ix_groups_parent_id"), "groups", ["parent_id"])

    op.create_table(
        "group_members",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.Column("group_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "role",
            sa.Enum(
                "guest", "developer", "maintainer", "owner", name="group_role", native_enum=False
            ),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("group_id", "user_id", name="uq_group_members"),
    )
    op.create_index(op.f("ix_group_members_group_id"), "group_members", ["group_id"])
    op.create_index(op.f("ix_group_members_user_id"), "group_members", ["user_id"])

    # A project now sits either in an account or in a group, so the address is
    # unique inside one namespace, not across both at once.
    op.add_column("projects", sa.Column("group_id", sa.Uuid(), nullable=True))
    op.create_index(op.f("ix_projects_group_id"), "projects", ["group_id"])
    op.create_foreign_key(
        "fk_projects_group_id", "projects", "groups", ["group_id"], ["id"], ondelete="CASCADE"
    )
    op.drop_constraint("uq_projects_owner_slug", "projects", type_="unique")
    op.create_index(
        "uq_projects_owner_slug",
        "projects",
        ["owner_id", "slug"],
        unique=True,
        postgresql_where=sa.text("group_id IS NULL"),
    )
    op.create_index(
        "uq_projects_group_slug",
        "projects",
        ["group_id", "slug"],
        unique=True,
        postgresql_where=sa.text("group_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_projects_group_slug", table_name="projects")
    op.drop_index("uq_projects_owner_slug", table_name="projects")
    op.create_unique_constraint("uq_projects_owner_slug", "projects", ["owner_id", "slug"])
    op.drop_constraint("fk_projects_group_id", "projects", type_="foreignkey")
    op.drop_index(op.f("ix_projects_group_id"), table_name="projects")
    op.drop_column("projects", "group_id")
    op.drop_table("group_members")
    op.drop_table("groups")

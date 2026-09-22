"""Create project members, issues and issue comments

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMP = sa.DateTime(timezone=True)


def _created_at() -> sa.Column[sa.DateTime]:
    return sa.Column("created_at", TIMESTAMP, server_default=sa.func.now(), nullable=False)


def upgrade() -> None:
    op.create_table(
        "project_members",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _created_at(),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "role",
            sa.Enum("guest", "developer", "maintainer", name="project_role", native_enum=False),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("project_id", "user_id", name="uq_project_members"),
    )
    op.create_index(op.f("ix_project_members_project_id"), "project_members", ["project_id"])
    op.create_index(op.f("ix_project_members_user_id"), "project_members", ["user_id"])

    op.create_table(
        "issues",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _created_at(),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "state",
            sa.Enum("open", "closed", name="issue_state", native_enum=False),
            nullable=False,
        ),
        sa.Column("closed_at", TIMESTAMP, nullable=True),
        sa.Column("updated_at", TIMESTAMP, nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("project_id", "number", name="uq_issues_project_number"),
    )
    op.create_index(op.f("ix_issues_project_id"), "issues", ["project_id"])
    op.create_index(op.f("ix_issues_author_id"), "issues", ["author_id"])

    op.create_table(
        "issue_comments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _created_at(),
        sa.Column("issue_id", sa.Uuid(), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["issue_id"], ["issues.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index(op.f("ix_issue_comments_issue_id"), "issue_comments", ["issue_id"])
    op.create_index(op.f("ix_issue_comments_author_id"), "issue_comments", ["author_id"])


def downgrade() -> None:
    op.drop_table("issue_comments")
    op.drop_table("issues")
    op.drop_table("project_members")

"""Create merge requests and their comments

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "merge_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("source_branch", sa.String(length=200), nullable=False),
        sa.Column("target_branch", sa.String(length=200), nullable=False),
        sa.Column(
            "state",
            sa.Enum("open", "merged", "closed", name="merge_state", native_enum=False),
            nullable=False,
        ),
        sa.Column("merge_commit", sa.String(length=40), nullable=True),
        sa.Column("merged_at", TIMESTAMP, nullable=True),
        sa.Column("closed_at", TIMESTAMP, nullable=True),
        sa.Column("updated_at", TIMESTAMP, nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("project_id", "number", name="uq_merge_requests_project_number"),
    )
    op.create_index(op.f("ix_merge_requests_project_id"), "merge_requests", ["project_id"])
    op.create_index(op.f("ix_merge_requests_author_id"), "merge_requests", ["author_id"])

    op.create_table(
        "merge_request_comments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.Column("merge_request_id", sa.Uuid(), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("file_path", sa.String(length=1024), nullable=True),
        sa.Column("line_number", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["merge_request_id"], ["merge_requests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index(
        op.f("ix_merge_request_comments_merge_request_id"),
        "merge_request_comments",
        ["merge_request_id"],
    )
    op.create_index(
        op.f("ix_merge_request_comments_author_id"), "merge_request_comments", ["author_id"]
    )


def downgrade() -> None:
    op.drop_table("merge_request_comments")
    op.drop_table("merge_requests")

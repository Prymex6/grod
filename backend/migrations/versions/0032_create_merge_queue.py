"""Create the merge queue and the required checks

Revision ID: 0032
Revises: 0031
Create Date: 2026-09-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0032"
down_revision: str | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMP = sa.DateTime(timezone=True)
QUEUE_STATES = ("waiting", "testing", "merged", "failed", "cancelled")


def upgrade() -> None:
    op.create_table(
        "merge_queue",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("merge_request_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by_id", sa.Uuid(), nullable=False),
        sa.Column(
            "state",
            sa.Enum(*QUEUE_STATES, name="queue_state", native_enum=False),
            nullable=False,
        ),
        sa.Column("tested_commit", sa.String(length=40), nullable=False),
        sa.Column("base_commit", sa.String(length=40), nullable=False),
        sa.Column("pipeline_id", sa.Uuid(), nullable=True),
        sa.Column("last_error", sa.String(length=2000), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["merge_request_id"], ["merge_requests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["pipeline_id"], ["pipelines.id"], ondelete="SET NULL"),
    )
    op.create_index(op.f("ix_merge_queue_project_id"), "merge_queue", ["project_id"])
    op.create_index(op.f("ix_merge_queue_merge_request_id"), "merge_queue", ["merge_request_id"])
    op.create_index(op.f("ix_merge_queue_requested_by_id"), "merge_queue", ["requested_by_id"])
    op.create_index(op.f("ix_merge_queue_state"), "merge_queue", ["state"])
    # One merge request may stand in line only once at a time; the rows of
    # finished attempts stay, so the partial index leaves them alone.
    op.create_index(
        "uq_merge_queue_active",
        "merge_queue",
        ["merge_request_id"],
        unique=True,
        postgresql_where=sa.text("state IN ('waiting', 'testing')"),
    )

    op.create_table(
        "required_checks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("job_name", sa.String(length=100), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("project_id", "job_name", name="uq_required_checks_job"),
    )
    op.create_index(op.f("ix_required_checks_project_id"), "required_checks", ["project_id"])


def downgrade() -> None:
    op.drop_table("required_checks")
    op.drop_table("merge_queue")

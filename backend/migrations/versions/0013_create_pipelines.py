"""Create pipelines, jobs and runners

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMP = sa.DateTime(timezone=True)


def _state() -> sa.Enum:
    return sa.Enum(
        "pending", "running", "success", "failed", "canceled", name="run_state", native_enum=False
    )


def upgrade() -> None:
    op.create_table(
        "runners",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("token_hash", sa.String(length=255), nullable=False),
        sa.Column("tags", sa.String(length=200), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("last_seen_at", TIMESTAMP, nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
    )
    op.create_index(op.f("ix_runners_project_id"), "runners", ["project_id"])

    op.create_table(
        "pipelines",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("ref", sa.String(length=200), nullable=False),
        sa.Column("commit", sa.String(length=40), nullable=False),
        sa.Column("commit_subject", sa.String(length=500), nullable=False),
        sa.Column("triggered_by_id", sa.Uuid(), nullable=True),
        sa.Column("state", _state(), nullable=False),
        sa.Column("started_at", TIMESTAMP, nullable=True),
        sa.Column("finished_at", TIMESTAMP, nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["triggered_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("project_id", "number", name="uq_pipelines_project_number"),
    )
    op.create_index(op.f("ix_pipelines_project_id"), "pipelines", ["project_id"])
    op.create_index(op.f("ix_pipelines_triggered_by_id"), "pipelines", ["triggered_by_id"])

    op.create_table(
        "jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.Column("pipeline_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("stage", sa.String(length=100), nullable=False),
        sa.Column("stage_order", sa.Integer(), nullable=False),
        sa.Column("image", sa.String(length=200), nullable=True),
        sa.Column("script", sa.Text(), nullable=False),
        sa.Column("variables", sa.Text(), nullable=False),
        sa.Column("state", _state(), nullable=False),
        sa.Column("log", sa.Text(), nullable=False),
        sa.Column("runner_id", sa.Uuid(), nullable=True),
        sa.Column("started_at", TIMESTAMP, nullable=True),
        sa.Column("finished_at", TIMESTAMP, nullable=True),
        sa.ForeignKeyConstraint(["pipeline_id"], ["pipelines.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["runner_id"], ["runners.id"], ondelete="SET NULL"),
    )
    op.create_index(op.f("ix_jobs_pipeline_id"), "jobs", ["pipeline_id"])
    op.create_index(op.f("ix_jobs_runner_id"), "jobs", ["runner_id"])


def downgrade() -> None:
    op.drop_table("jobs")
    op.drop_table("pipelines")
    op.drop_table("runners")

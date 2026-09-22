"""Create the secrets and packages of projects

Revision ID: 0015
Revises: 0014
Create Date: 2026-09-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "secrets",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("value_encrypted", sa.Text(), nullable=False),
        sa.Column("masked", sa.Boolean(), nullable=False),
        sa.Column("protected", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("project_id", "name", name="uq_secrets_project_name"),
    )
    op.create_index(op.f("ix_secrets_project_id"), "secrets", ["project_id"])

    op.create_table(
        "packages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("version", sa.String(length=100), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("digest", sa.String(length=64), nullable=False),
        sa.Column("uploaded_by_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint(
            "project_id", "name", "version", "filename", name="uq_packages_address"
        ),
    )
    op.create_index(op.f("ix_packages_project_id"), "packages", ["project_id"])
    op.create_index(op.f("ix_packages_name"), "packages", ["name"])
    op.create_index(op.f("ix_packages_uploaded_by_id"), "packages", ["uploaded_by_id"])


def downgrade() -> None:
    op.drop_table("packages")
    op.drop_table("secrets")

"""Permanent per-session usage summary.

Revision ID: 0054_session_usage_summary
Revises: 0053_volume_mount_lock
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0054_session_usage_summary"
down_revision = "0053_volume_mount_lock"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "session",
        sa.Column("usage_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("session", "usage_summary")

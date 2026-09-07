"""Privileged (root) sessions, policy-gated.

Revision ID: 0055_session_privileged
Revises: 0054_session_usage_summary
"""
import sqlalchemy as sa
from alembic import op

revision = "0055_session_privileged"
down_revision = "0054_session_usage_summary"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "session",
        sa.Column("privileged", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("session", "privileged")

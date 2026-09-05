"""session.last_reported_at / restart_count — the operator's per-session heartbeat.

Revision ID: 0050_session_liveness
Revises: 0049_notification_deleted_at
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0050_session_liveness"
down_revision = "0049_notification_deleted_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("session", sa.Column("last_reported_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("session", sa.Column("restart_count", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("session", "restart_count")
    op.drop_column("session", "last_reported_at")

"""Volume mount lock.

Revision ID: 0053_volume_mount_lock
Revises: 0052_gpu_device_alias
"""
import sqlalchemy as sa
from alembic import op

revision = "0053_volume_mount_lock"
down_revision = "0052_gpu_device_alias"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "storage_volume",
        sa.Column("mount_locked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("storage_volume", "mount_locked")

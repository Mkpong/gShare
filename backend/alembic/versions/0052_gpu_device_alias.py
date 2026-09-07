"""GPU card alias.

Revision ID: 0052_gpu_device_alias
Revises: 0051_drop_boards
"""
import sqlalchemy as sa
from alembic import op

revision = "0052_gpu_device_alias"
down_revision = "0051_drop_boards"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("gpu_device", sa.Column("alias", sa.String(32), nullable=True))
    # One name per card within a cluster; NULLs do not collide.
    op.create_index("uq_gpu_device_cluster_alias", "gpu_device", ["cluster_id", "alias"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_gpu_device_cluster_alias", table_name="gpu_device")
    op.drop_column("gpu_device", "alias")

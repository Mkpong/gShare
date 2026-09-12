"""Record where a volume's data lives.

A volume's PVC is created lazily by whichever cluster's operator first runs a session that mounts
it, and until now nothing wrote that down: the administrator's volume list could not say which
storage server a volume sits on, and with several pools the answer was reconstructed from mount
history. The operator already reports every PVC each sync tick; this adds the columns that report
fills — the provisioning cluster, the StorageClass the claim names (the pool is the pair), and
when it was first seen. Existing rows fill in on the next tick; volumes with no PVC yet stay NULL.

Revision ID: 0062_volume_placement
Revises: 0061_org_name_unique_live
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0062_volume_placement"
down_revision = "0061_org_name_unique_live"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("storage_volume", sa.Column("cluster_id", sa.String(), nullable=True))
    op.add_column("storage_volume", sa.Column("storage_class", sa.String(), nullable=True))
    op.add_column("storage_volume", sa.Column("provisioned_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        "fk_storage_volume_cluster", "storage_volume", "cluster", ["cluster_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("ix_storage_volume_cluster_id", "storage_volume", ["cluster_id"])


def downgrade() -> None:
    op.drop_index("ix_storage_volume_cluster_id", table_name="storage_volume")
    op.drop_constraint("fk_storage_volume_cluster", "storage_volume", type_="foreignkey")
    op.drop_column("storage_volume", "provisioned_at")
    op.drop_column("storage_volume", "storage_class")
    op.drop_column("storage_volume", "cluster_id")

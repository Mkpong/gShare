"""Register volume-backing pools, with their cluster and who may share them.

Storage was inferred from whichever nodes carried role="storage", and their disks were added up
into one number. A volume lives on exactly one pool — the StorageClass its PVC names decides
where — so the sum licensed volumes no single server could hold, and the figure was the node's
root disk rather than the pool behind it. A pool is now a registered object: it belongs to the
cluster its server sits in, says which clusters may place volumes on it, and carries a capacity
the operator measures from the CSI driver instead of one an administrator guesses.

The existing storage-role nodes are carried over as pools so nothing has to be re-registered by
hand; their capacity starts empty and is filled in by the first operator report.

Revision ID: 0059_storage_pool
Revises: 0058_audit_cluster
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0059_storage_pool"
down_revision = "0058_audit_cluster"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "storage_pool",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("cluster_id", sa.String(), sa.ForeignKey("cluster.id"), nullable=False),
        sa.Column("node_id", sa.String(), sa.ForeignKey("gpu_node.id"), nullable=True),
        sa.Column("node_hostname", sa.String(), nullable=True),
        sa.Column("storage_class", sa.String(), nullable=False),
        sa.Column("share_scope", sa.String(), nullable=False, server_default="all"),
        sa.Column("capacity_bytes", sa.BigInteger(), nullable=True),
        sa.Column("capacity_source", sa.String(), nullable=True),
        sa.Column("capacity_reported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("manual_capacity_gb", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("cluster_id", "storage_class", name="uq_storage_pool_cluster_class"),
    )
    op.create_index("ix_storage_pool_cluster_id", "storage_pool", ["cluster_id"])
    op.create_index("ix_storage_pool_node_id", "storage_pool", ["node_id"])
    op.create_table(
        "storage_pool_share",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("pool_id", sa.String(), sa.ForeignKey("storage_pool.id"), nullable=False),
        sa.Column("cluster_id", sa.String(), sa.ForeignKey("cluster.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("pool_id", "cluster_id", name="uq_storage_pool_share"),
    )
    op.create_index("ix_storage_pool_share_pool_id", "storage_pool_share", ["pool_id"])
    op.create_index("ix_storage_pool_share_cluster_id", "storage_pool_share", ["cluster_id"])

    # Carry over what the fleet already has: one pool per storage-role node. The StorageClass is
    # unknown at this level, so it is left as the deployment default and corrected by the first
    # operator report (which names the class it provisions from) or by an administrator.
    op.execute("""
        INSERT INTO storage_pool (id, name, cluster_id, node_id, node_hostname, storage_class,
                                  share_scope, created_at, updated_at)
        SELECT 'stp_migrated_' || n.id, COALESCE(n.hostname, n.id), n.cluster_id, n.id, n.hostname,
               'gshare-data', 'all', now(), now()
        FROM gpu_node n
        WHERE n.role = 'storage' AND n.cluster_id IS NOT NULL
          AND NOT EXISTS (
            SELECT 1 FROM storage_pool p
            WHERE p.cluster_id = n.cluster_id AND p.storage_class = 'gshare-data'
          )
    """)


def downgrade() -> None:
    op.drop_table("storage_pool_share")
    op.drop_table("storage_pool")

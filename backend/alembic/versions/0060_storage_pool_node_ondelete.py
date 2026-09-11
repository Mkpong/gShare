"""Let a storage node be removed without the pool blocking it.

`storage_pool.node_id` names the machine a pool sits on, for display. It was a plain foreign key,
so the two paths that remove a node — finishing a decommission, and deregistering a cluster, both
of which hard-delete the row — hit a foreign-key violation and failed. A decommissioned node then
never finished leaving: the callback errored, the row stayed `decommissioning`, and the next
inventory report brought it back.

The link is descriptive, not identifying: a pool is (cluster, storage class), and `node_hostname`
keeps the readable trace. So the reference clears itself when the node goes.

Revision ID: 0060_storage_pool_node_ondelete
Revises: 0059_storage_pool
"""
from __future__ import annotations

from alembic import op

revision = "0060_storage_pool_node_ondelete"
down_revision = "0059_storage_pool"
branch_labels = None
depends_on = None

_FK = "fk_storage_pool_node_id_gpu_node"


def upgrade() -> None:
    op.drop_constraint(_FK, "storage_pool", type_="foreignkey")
    op.create_foreign_key(_FK, "storage_pool", "gpu_node", ["node_id"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    op.drop_constraint(_FK, "storage_pool", type_="foreignkey")
    op.create_foreign_key(_FK, "storage_pool", "gpu_node", ["node_id"], ["id"])

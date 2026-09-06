"""Removing a node also removes it from Kubernetes, in two phases.

Phase 1 (this plane): clear the cards, park the row as `decommissioning`.
Phase 2 (the operator): delete the Node object, call back, the row goes.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.api.infra_router import delete_node
from app.api.schemas.internal import OperatorNodeUpsert
from app.auth.rbac import Principal
from app.cluster.inventory_sync import InventorySync
from app.core import ids
from app.core.errors import DomainError
from app.db.models import Cluster, GpuDevice, GpuNode
from app.internal.inventory_router import decommissioning_nodes, node_decommissioned

CLU = "clu_t"


def _super() -> Principal:
    return Principal(user_id="usr_admin", global_roles={"super_admin"})


async def _node(db, status: str = "offline") -> GpuNode:
    node = GpuNode(id=ids.new("node"), cluster_id=CLU, hostname="gpu3", status=status,
                   cpu=32, mem=128, disk=500)
    async with db.begin():
        db.add_all([
            Cluster(id=CLU, name="local", api_server="https://k8s", runtime="containerd",
                    kubeconfig_secret_ref="secret"),
            node,
            GpuDevice(id=ids.new("device"), cluster_id=CLU, node_id=node.id,
                      gpu_uuid=ids.new("device"), model="RTX PRO 5000", mode="fractional",
                      status="ready", total_mem_mb=49152, used_mem_mb=0,
                      total_cores=100, used_cores=0),
        ])
    return node


@pytest.mark.asyncio
async def test_a_node_that_is_still_up_is_refused(db):
    node = await _node(db, status="ready")
    with pytest.raises(DomainError) as exc:
        await delete_node(node.id, _super(), db)
    assert exc.value.code == "node_busy"


@pytest.mark.asyncio
async def test_delete_parks_the_node_and_clears_its_cards(db):
    node = await _node(db)
    await delete_node(node.id, _super(), db)

    row = await db.get(GpuNode, node.id)
    assert row is not None and row.status == "decommissioning"
    cards = (await db.execute(select(GpuDevice).where(GpuDevice.node_id == node.id))).scalars().all()
    assert cards == []

    claims = {"sub": f"operator:{CLU}"}
    assert (await decommissioning_nodes(claims, db))["hostnames"] == ["gpu3"]


@pytest.mark.asyncio
async def test_inventory_does_not_resurrect_a_node_being_removed(db):
    node = await _node(db)
    await delete_node(node.id, _super(), db)

    # The Node object still exists, so the operator keeps reporting it.
    await InventorySync(db).upsert_node(
        OperatorNodeUpsert(node_id="gpu3", node_cpu=32, node_mem_gb=128, node_disk_gb=500,
                           node_ready=False),
        CLU,
    )
    row = await db.get(GpuNode, node.id)
    assert row.status == "decommissioning"


@pytest.mark.asyncio
async def test_the_operator_callback_retires_the_row(db):
    node = await _node(db)
    await delete_node(node.id, _super(), db)

    claims = {"sub": f"operator:{CLU}"}
    assert (await node_decommissioned(claims, {"hostname": "gpu3"}, db))["accepted"] is True
    assert await db.get(GpuNode, node.id) is None
    # A repeated callback is harmless.
    assert (await node_decommissioned(claims, {"hostname": "gpu3"}, db))["accepted"] is True

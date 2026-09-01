"""Node removal: refuse while live work remains, keep the billing history when it does not."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.api.infra_router import delete_node
from app.core import ids
from app.core.errors import DomainError
from app.db.models import Allocation, GpuDevice, GpuNode
from app.db.models import Session as SessionRow


async def _node_with_card(db, hostname="gpu-x"):
    node = GpuNode(id=ids.new("node"), cluster_id=ids.new("cluster"), hostname=hostname,
                   status="offline", cpu=8, mem=32)
    dev = GpuDevice(id=ids.new("device"), node_id=node.id, cluster_id=node.cluster_id,
                    model="RTX PRO 6000", gpu_uuid=ids.new("dev"),
                    total_mem_mb=97887, total_cores=100)
    async with db.begin():
        db.add_all([node, dev])
    return node, dev


class _Principal:
    user_id = "usr_test"
    global_role = "super_admin"
    memberships: dict = {}
    org_admin_orgs: list = []

    def require(self, **_kw):  # RBAC is exercised by its own tests
        return None


@pytest.mark.asyncio
async def test_delete_node_refuses_while_an_allocation_is_live(db):
    node, dev = await _node_with_card(db)
    sess = SessionRow(
        id=ids.new("session"), owner_user_id=ids.new("user"), cluster_id=node.cluster_id,
        offering_id=ids.new("offering"), image_id=ids.new("image"), resource_class="gpu",
        mode="fractional", status="running", gpu_mem_mb=4096, gpu_cores=10,
    )
    async with db.begin():
        db.add(sess)
        db.add(Allocation(id=ids.new("allocation"), session_id=sess.id, device_id=dev.id,
                          gpu_uuid=dev.gpu_uuid, gpu_mem_mb=4096, gpu_cores=10, status="bound"))

    with pytest.raises(DomainError) as err:
        await delete_node(node.id, principal=_Principal(), db=db)
    assert err.value.code == "node_busy"

    # Nothing was removed by the refused call.
    assert await db.get(GpuNode, node.id) is not None
    assert await db.get(GpuDevice, dev.id) is not None


@pytest.mark.asyncio
async def test_delete_node_detaches_history_and_removes_inventory(db):
    node, dev = await _node_with_card(db, hostname="gpu-y")
    sess = SessionRow(
        id=ids.new("session"), owner_user_id=ids.new("user"), cluster_id=node.cluster_id,
        offering_id=ids.new("offering"), image_id=ids.new("image"), resource_class="gpu",
        mode="fractional", status="terminated", gpu_mem_mb=4096, gpu_cores=10,
    )
    alloc = Allocation(id=ids.new("allocation"), session_id=sess.id, device_id=dev.id,
                       gpu_uuid=dev.gpu_uuid, gpu_mem_mb=4096, gpu_cores=10,
                       status="released", ended_at=datetime.now(UTC))
    async with db.begin():
        db.add_all([sess, alloc])

    await delete_node(node.id, principal=_Principal(), db=db)

    assert await db.get(GpuNode, node.id) is None
    assert await db.get(GpuDevice, dev.id) is None
    # The billing trail survives, minus the card that no longer exists.
    row = (await db.execute(select(Allocation).where(Allocation.id == alloc.id))).scalar_one()
    assert row.device_id is None
    assert row.gpu_uuid == dev.gpu_uuid

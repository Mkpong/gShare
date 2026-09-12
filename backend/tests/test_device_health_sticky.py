"""A faulted card stays faulted. Marking a card unhealthy ends every session bound to it; if the
next inventory report could flip it back to ready, the sessions would be gone and the card handed
straight back out seconds later."""
from __future__ import annotations

import pytest

from app.api.schemas.internal import OperatorGpuDeviceUpsert
from app.cluster.inventory_sync import InventorySync
from app.core import ids
from app.db.models import Cluster, GpuDevice, GpuNode
from tests.fkseed import seed


def _report(cluster_id: str, status: str) -> OperatorGpuDeviceUpsert:
    return OperatorGpuDeviceUpsert(
        node_id="n1", uuid="GPU-x", mode="fractional", total_mem_mb=16000,
        used_mem_mb=0, used_cores=0, total_cores=100, status=status,
        cluster_id=cluster_id, model="A100",
    )


@pytest.mark.asyncio
async def test_inventory_never_resurrects_a_faulted_card(db):
    cluster = Cluster(id=ids.new("cluster"), name="c", api_server="https://k8s",
                      runtime="containerd", kubeconfig_secret_ref="ref")
    node = GpuNode(id=ids.new("node"), hostname="n1", cluster_id=cluster.id, status="ready")
    dev = GpuDevice(id="GPU-x", node_id=node.id, cluster_id=cluster.id, model="A100",
                    gpu_uuid="GPU-x", total_mem_mb=16000, status="unhealthy", mode="fractional")
    await seed(db, [cluster, node, dev])

    sync = InventorySync(db)
    # the card is physically fine and says so; the fault was a decision, so it must stand
    await sync.upsert_device(_report(cluster.id, "ready"), cluster.id)
    await db.commit()
    db.expunge_all()
    got = await db.get(GpuDevice, "GPU-x")
    assert got.status == "unhealthy", "a routine report must not return a faulted card to service"
    got.status = "ready"
    await db.commit()

    # the other direction still works: a report CAN fail a healthy card
    await sync.upsert_device(_report(cluster.id, "unhealthy"), cluster.id)
    await db.commit()
    db.expunge_all()
    assert (await db.get(GpuDevice, "GPU-x")).status == "unhealthy"

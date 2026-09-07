"""The dashboard's "free" and the scheduler's "placeable" must be the same set.

They were not: a card yielded to the lending pool, or one mid pool-transition, was excluded from
placement yet still counted as free VRAM — so a session could be shown capacity and then queue
with no visible reason.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.api.sessions_router import gpu_availability
from app.core import ids
from app.db.models import Cluster, GpuDevice, GpuNode
from app.domain.placement import placeable_device_clauses


async def _fleet(db):
    cluster = Cluster(id="clu_t", name="c", api_server="https://k8s", runtime="containerd",
                      kubeconfig_secret_ref="ref")
    ready = GpuNode(id=ids.new("node"), cluster_id="clu_t", hostname="n-ready", status="ready")
    cordoned = GpuNode(id=ids.new("node"), cluster_id="clu_t", hostname="n-cordoned", status="cordoned")
    def dev(uuid, node, **kw):
        base = dict(id=uuid, node_id=node.id, cluster_id="clu_t", model="A100", gpu_uuid=uuid,
                    total_mem_mb=40000, total_cores=100, status="ready", mode="fractional",
                    mode_state="ready", lend_state="")
        base.update(kw)
        return GpuDevice(**base)
    devices = [
        dev("GPU-ok", ready),                              # the only placeable card
        dev("GPU-lent", ready, lend_state="lent"),         # a spot session borrowed it
        dev("GPU-yielded", ready, lend_state="yielded"),   # its resident yielded it
        dev("GPU-draining", ready, mode_state="draining"), # mid pool transition
        dev("GPU-faulted", ready, status="unhealthy"),     # administrator marked it faulted
        dev("GPU-cordoned-node", cordoned),                # node takes no new work
    ]
    async with db.begin():
        db.add_all([cluster, ready, cordoned, *devices])
    return devices


@pytest.mark.asyncio
async def test_only_the_placeable_card_is_offered(db):
    await _fleet(db)
    rows = (await db.scalars(
        select(GpuDevice).join(GpuNode, GpuNode.id == GpuDevice.node_id, isouter=True)
        .where(*placeable_device_clauses())
    )).all()
    assert [d.gpu_uuid for d in rows] == ["GPU-ok"]


@pytest.mark.asyncio
async def test_availability_endpoint_reports_the_same_card(db):
    await _fleet(db)
    from app.auth.rbac import Principal
    root = Principal(user_id="usr_root", global_role="super_admin", global_roles={"super_admin"})
    out = await gpu_availability(fleet=True, cluster_id=None, principal=root, db=db)
    models = out["data"] if isinstance(out, dict) else out
    # one model, one usable card — the lent, yielded, draining, faulted and cordoned ones are gone
    assert sum(len(m.get("devices", [])) for m in models) == 1

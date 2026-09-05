"""A faulty card leaves placement and ends the sessions bound to it; a repaired one comes back quietly."""
from __future__ import annotations

import pytest

from app.core import ids
from app.db.models import Allocation, GpuDevice, GpuNode, Session
from app.domain import device_health


@pytest.mark.asyncio
async def test_unhealthy_ends_bound_sessions_and_ready_does_not(db, monkeypatch):
    node = GpuNode(id=ids.new("node"), cluster_id="clu_t", hostname="gpu-a", status="ready")
    dev = GpuDevice(id=ids.new("device"), node_id=node.id, cluster_id="clu_t", model="X",
                    gpu_uuid=ids.new("dev"), total_mem_mb=1000, total_cores=100)
    other = GpuDevice(id=ids.new("device"), node_id=node.id, cluster_id="clu_t", model="X",
                      gpu_uuid=ids.new("dev"), total_mem_mb=1000, total_cores=100)
    def sess(status="running"):
        return Session(id=ids.new("session"), owner_user_id=ids.new("user"), cluster_id="clu_t",
                       offering_id="off_t", image_id="img_t", resource_class="gpu", mode="fractional",
                       status=status, gpu_mem_mb=100, gpu_cores=10)
    on_dev, on_other, ended_before = sess(), sess(), sess("terminated")
    async with db.begin():
        db.add_all([node, dev, other, on_dev, on_other, ended_before])
        db.add_all([
            Allocation(id=ids.new("allocation"), session_id=on_dev.id, device_id=dev.id, status="bound"),
            Allocation(id=ids.new("allocation"), session_id=on_other.id, device_id=other.id, status="bound"),
            Allocation(id=ids.new("allocation"), session_id=ended_before.id, device_id=dev.id, status="bound"),
        ])
    calls: list[tuple[str, str]] = []

    class _Svc:
        def __init__(self, _db):
            pass

        async def terminate(self, sid, *, forced=False, reason="user_stopped"):
            calls.append((sid, reason))

    monkeypatch.setattr("app.domain.session_service.SessionService", _Svc)
    ended = await device_health.set_device_health(db, dev, "unhealthy", actor="usr_root", reason="xid 79")
    assert ended == [on_dev.id] and calls == [(on_dev.id, "gpu_fault")]
    assert dev.status == "unhealthy"

    calls.clear()
    assert await device_health.set_device_health(db, dev, "ready", actor="usr_root") == []
    assert dev.status == "ready" and calls == []

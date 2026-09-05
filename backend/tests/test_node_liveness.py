"""A node is alive when its kubelet answers — not when its Node object exists."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.api.schemas.internal import OperatorNodeUpsert
from app.cluster.inventory_sync import InventorySync
from app.core import ids
from app.core.config import settings
from app.db.models import Cluster, GpuNode, Notification, User
from app.db.models import Session as SessionRow
from app.workers import node_liveness


async def _node(db, *, status, seen_delta_sec, cluster_id=None, hostname=None):
    n = GpuNode(
        id=ids.new("node"), cluster_id=cluster_id or ids.new("cluster"),
        hostname=hostname or ids.new("node"), status=status,
        last_seen_at=datetime.now(UTC) - timedelta(seconds=seen_delta_sec),
    )
    async with db.begin():
        db.add(n)
    return n


def _naive(dt):
    # SQLite hands timestamps back without tzinfo; compare on the wall-clock value only.
    return dt.replace(tzinfo=None) if dt is not None else None


async def _root(db) -> User:
    root = User(id=ids.new("user"), email=f"{ids.new('user')}@t", name="root", global_role="super_admin")
    async with db.begin():
        db.add(root)
    return root


@pytest.mark.asyncio
async def test_stale_node_goes_offline_and_cordon_is_left_alone(db, monkeypatch):
    monkeypatch.setattr(node_liveness, "get_sessionmaker", lambda: (lambda: db))
    cid = ids.new("cluster")
    stale = await _node(db, status="ready", seen_delta_sec=settings.NODE_STALE_SEC + 60, cluster_id=cid)
    cordoned = await _node(db, status="cordoned", seen_delta_sec=settings.NODE_STALE_SEC + 60, cluster_id=cid)
    # A fresh sibling proves the operator is alive; without one, silence is the operator's.
    await _node(db, status="ready", seen_delta_sec=5, cluster_id=cid)

    await node_liveness.run()

    db.expunge_all()
    assert (await db.get(GpuNode, stale.id)).status == "offline"
    assert (await db.get(GpuNode, cordoned.id)).status == "cordoned"


@pytest.mark.asyncio
async def test_not_ready_report_marks_offline_at_once_and_ready_report_restores(db):
    root = await _root(db)
    cid = ids.new("cluster")
    async with db.begin():
        db.add(Cluster(id=cid, name="c", api_server="https://t:6443", runtime="k8s", kubeconfig_secret_ref="sec"))
    node = await _node(db, status="ready", seen_delta_sec=1, cluster_id=cid, hostname="gpu-x")
    seen_before = node.last_seen_at

    await InventorySync(db).upsert_node(OperatorNodeUpsert(node_id="gpu-x", node_ready=False), cid)
    db.expunge_all()
    n = await db.get(GpuNode, node.id)
    assert n.status == "offline"
    assert _naive(n.last_seen_at) == _naive(seen_before)   # a NotReady report is not a heartbeat
    await db.commit()   # close the read transaction the get() opened

    await InventorySync(db).upsert_node(OperatorNodeUpsert(node_id="gpu-x", node_ready=True), cid)
    db.expunge_all()
    n = await db.get(GpuNode, node.id)
    assert n.status == "ready" and _naive(n.last_seen_at) > _naive(seen_before)

    kinds = [r.type for r in (await db.execute(
        select(Notification).where(Notification.user_id == root.id).order_by(Notification.created_at)
    )).scalars()]
    assert kinds == ["node_offline", "node_online"]


@pytest.mark.asyncio
async def test_old_operator_without_the_field_still_heartbeats(db):
    cid = ids.new("cluster")
    async with db.begin():
        db.add(Cluster(id=cid, name="c", api_server="https://t:6443", runtime="k8s", kubeconfig_secret_ref="sec"))
    node = await _node(db, status="ready", seen_delta_sec=120, cluster_id=cid, hostname="gpu-y")
    seen_before = node.last_seen_at
    await InventorySync(db).upsert_node(OperatorNodeUpsert(node_id="gpu-y"), cid)
    db.expunge_all()
    after = (await db.get(GpuNode, node.id)).last_seen_at
    assert _naive(after) > _naive(seen_before)


@pytest.mark.asyncio
async def test_sessions_on_an_offline_node_are_terminated(db, monkeypatch):
    monkeypatch.setattr(node_liveness, "get_sessionmaker", lambda: (lambda: db))
    dead = await _node(db, status="offline", seen_delta_sec=0, hostname="gpu-dead")
    running = SessionRow(
        id=ids.new("session"), owner_user_id=ids.new("user"), cluster_id=dead.cluster_id,
        offering_id="off_t", image_id="img_t", resource_class="gpu", mode="fractional",
        status="running", node_hostname="gpu-dead", gpu_mem_mb=1024, gpu_cores=10,
    )
    paused = SessionRow(
        id=ids.new("session"), owner_user_id=ids.new("user"), cluster_id=dead.cluster_id,
        offering_id="off_t", image_id="img_t", resource_class="gpu", mode="fractional",
        status="paused", node_hostname="gpu-dead", gpu_mem_mb=1024, gpu_cores=10,
    )
    async with db.begin():
        db.add_all([running, paused])

    calls: list[tuple[str, str]] = []

    class _Svc:
        def __init__(self, _db):
            pass

        async def terminate(self, sid, *, forced=False, reason="user_stopped"):
            calls.append((sid, reason))

    monkeypatch.setattr(node_liveness, "SessionService", _Svc)
    await node_liveness.run()
    # Only the session with a pod is ended; the paused one has none and can resume elsewhere.
    assert calls == [(running.id, "node_offline")]


@pytest.mark.asyncio
async def test_operator_silence_marks_nothing_offline(db, monkeypatch):
    """Every node of a cluster stale at once = the operator is down, not the fleet."""
    monkeypatch.setattr(node_liveness, "get_sessionmaker", lambda: (lambda: db))
    cid = ids.new("cluster")
    a = await _node(db, status="ready", seen_delta_sec=settings.NODE_STALE_SEC + 60, cluster_id=cid)
    b = await _node(db, status="ready", seen_delta_sec=settings.NODE_STALE_SEC + 90, cluster_id=cid)
    await node_liveness.run()
    db.expunge_all()
    assert (await db.get(GpuNode, a.id)).status == "ready"
    assert (await db.get(GpuNode, b.id)).status == "ready"

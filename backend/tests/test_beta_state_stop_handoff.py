"""Beta: a pause must not release the GPU reservation while the pod is still running.

stop() used to commit `paused` and release the Allocation BEFORE asking the operator to tear the
pod down. When that handoff failed (cluster unreachable, CR gone) the row said paused, the ledger
said the card was free, and the pod kept computing on it for free — and the next admission could
be placed onto the same card on top of it.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core import ids
from app.db.models import Allocation, GpuDevice, GpuNode, Session
from app.domain.session_service import SessionService
from tests.fkseed import seed

pytestmark = pytest.mark.asyncio


async def _running(db):
    node = GpuNode(id=ids.new("node"), cluster_id="clu_a", hostname="gpu-a", status="ready")
    dev = GpuDevice(id=ids.new("device"), node_id=node.id, cluster_id="clu_a", model="X",
                    gpu_uuid="GPU-1", total_mem_mb=16000, total_cores=100,
                    used_mem_mb=1000, used_cores=10)
    sess = Session(id=ids.new("session"), owner_user_id=ids.new("user"), cluster_id="clu_a",
                   offering_id="off_t", image_id="img_t", resource_class="gpu", mode="fractional",
                   status="running", gpu_mem_mb=1000, gpu_cores=10,
                   credit_per_hour_snapshot=Decimal("0"),
                   started_at=datetime.now(UTC) - timedelta(minutes=10))
    alloc = Allocation(id=ids.new("allocation"), session_id=sess.id, device_id=dev.id,
                       gpu_uuid="GPU-1", gpu_mem_mb=1000, gpu_cores=10, status="bound")
    await seed(db, [node, dev, sess, alloc])
    return sess, dev


async def test_failed_pause_handoff_keeps_the_session_running_and_the_card_reserved(db):
    sess, dev = await _running(db)
    svc = SessionService(db)

    async def _boom(sess_, paused, **kw):
        raise RuntimeError("cluster unreachable")

    svc.handoff.set_paused = _boom
    with pytest.raises(RuntimeError):
        await svc.stop(sess.id)
    await db.rollback()
    db.expunge_all()
    row = await db.get(Session, sess.id)
    card = await db.get(GpuDevice, dev.id)
    live = await db.scalar(select(Allocation).where(Allocation.session_id == sess.id, Allocation.ended_at.is_(None)))
    assert row.status == "running"
    assert live is not None
    assert (card.used_mem_mb, card.used_cores) == (1000, 10)


async def test_successful_pause_releases_after_the_handoff(db):
    sess, dev = await _running(db)
    svc = SessionService(db)
    order: list[str] = []

    async def _ok(sess_, paused, **kw):
        # The ledger must still hold the card when the operator is told to pause.
        live = await db.scalar(select(Allocation).where(Allocation.session_id == sess_.id, Allocation.ended_at.is_(None)))
        order.append("handoff:" + ("held" if live is not None else "released"))
        return 3

    svc.handoff.set_paused = _ok
    await svc.stop(sess.id)
    db.expunge_all()
    row = await db.get(Session, sess.id)
    card = await db.get(GpuDevice, dev.id)
    live = await db.scalar(select(Allocation).where(Allocation.session_id == sess.id, Allocation.ended_at.is_(None)))
    assert order == ["handoff:held"]
    assert row.status == "paused" and row.status_reason == "user_stopped"
    assert live is None and (card.used_mem_mb, card.used_cores) == (0, 0)

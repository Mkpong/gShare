"""A node whose inventory heartbeat stops goes offline, and comes back when it resumes."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.core import ids
from app.core.config import settings
from app.db.models import GpuNode
from app.workers import node_liveness


async def _node(db, *, status, seen_delta_sec):
    n = GpuNode(
        id=ids.new("node"), cluster_id=ids.new("cluster"), hostname=ids.new("node"),
        status=status,
        last_seen_at=datetime.now(UTC) - timedelta(seconds=seen_delta_sec),
    )
    async with db.begin():
        db.add(n)
    return n


@pytest.mark.asyncio
async def test_stale_node_goes_offline_and_recovers(db, monkeypatch):
    monkeypatch.setattr(node_liveness, "get_sessionmaker", lambda: (lambda: db))
    stale = await _node(db, status="ready", seen_delta_sec=settings.NODE_STALE_SEC + 60)
    fresh = await _node(db, status="offline", seen_delta_sec=5)
    cordoned = await _node(db, status="cordoned", seen_delta_sec=settings.NODE_STALE_SEC + 60)

    await node_liveness.run()

    db.expunge_all()
    assert (await db.get(GpuNode, stale.id)).status == "offline"
    assert (await db.get(GpuNode, fresh.id)).status == "ready"
    # A cordon is an operator decision; the heartbeat must not lift or override it.
    assert (await db.get(GpuNode, cordoned.id)).status == "cordoned"

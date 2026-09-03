"""node_liveness — mark nodes offline when their inventory heartbeat stops, and back when it resumes.

The operator stamps ``GpuNode.last_seen_at`` on every inventory report. A node that is powered
down, drained out of the cluster, or cut off from the API server simply stops reporting: nothing
else moves its status, so without this loop it would sit at "ready" forever and the console would
keep offering capacity that cannot be scheduled (availability and admission both filter on the
node's status, so a stale "ready" is worse than a wrong number — it is a queued session that never
starts).

Cordoned nodes are left alone in both directions: cordon is an operator decision and only an
operator lifts it.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.config import settings
from app.core.logging import get_logger
from app.db.base import get_sessionmaker
from app.db.models import GpuNode

log = get_logger(__name__)


async def run() -> None:
    cutoff = datetime.now(UTC) - timedelta(seconds=settings.NODE_STALE_SEC)
    marked = restored = 0
    async with get_sessionmaker()() as db:
        async with db.begin():
            nodes = (await db.scalars(select(GpuNode))).all()
            for node in nodes:
                if node.status == "cordoned":
                    continue
                seen = node.last_seen_at
                if seen is not None and seen.tzinfo is None:
                    seen = seen.replace(tzinfo=UTC)
                stale = seen is None or seen < cutoff
                if stale and node.status != "offline":
                    node.status = "offline"
                    marked += 1
                elif not stale and node.status == "offline":
                    # The operator is reporting again: put the node back in the placement pool.
                    node.status = "ready"
                    restored += 1
    if marked or restored:
        log.info("node_liveness: offline=%d restored=%d", marked, restored)

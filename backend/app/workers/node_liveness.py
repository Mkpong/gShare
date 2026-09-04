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
from app.db.models import GpuNode, User
from app.domain.notification_service import NotificationService

log = get_logger(__name__)


async def run() -> None:
    cutoff = datetime.now(UTC) - timedelta(seconds=settings.NODE_STALE_SEC)
    marked: list[GpuNode] = []
    restored: list[GpuNode] = []
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
                    marked.append(node)
                elif not stale and node.status == "offline":
                    # The operator is reporting again: put the node back in the placement pool.
                    node.status = "ready"
                    restored.append(node)
            if marked or restored:
                await _notify_operators(db, marked, restored)
    if marked or restored:
        log.info("node_liveness: offline=%d restored=%d", len(marked), len(restored))


async def _notify_operators(db, marked: list[GpuNode], restored: list[GpuNode]) -> None:
    """A node silently leaving the fleet is an incident for whoever runs the cluster: tell every
    super_admin, once per transition, through the same notification channel the console already
    surfaces (bell + history). Nothing is sent for cordon, which is their own decision."""
    supers = list(
        (
            await db.execute(
                select(User.id).where(User.global_role == "super_admin", User.deleted_at.is_(None))
            )
        ).scalars()
    )
    if not supers:
        return
    svc = NotificationService(db)
    stale_min = max(1, settings.NODE_STALE_SEC // 60)
    for node in marked:
        await svc.notify(
            supers, "node_offline", f"Node offline: {node.hostname}",
            f"No inventory report for {stale_min} minutes; the node is out of placement.",
            params={"hostname": node.hostname, "stale_min": stale_min}, node_id=node.id,
        )
    for node in restored:
        await svc.notify(
            supers, "node_online", f"Node back online: {node.hostname}",
            "Inventory reports resumed; the node takes placements again.",
            params={"hostname": node.hostname}, node_id=node.id,
        )

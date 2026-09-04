"""Node liveness transitions — one place, so every path that flips a node offline or back
(the operator reporting a NotReady condition, the stale-heartbeat sweep) behaves the same and
tells the same people.

A cordon is never touched here: it is an operator's decision and only an operator lifts it.
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.db.models import GpuNode, User
from app.domain.notification_service import NotificationService

log = get_logger(__name__)

# Statuses a heartbeat may move: anything else (cordoned) is owned by an administrator.
LIVE_STATUSES = ("ready", "busy")


def touch(node: GpuNode, ready: bool | None) -> str | None:
    """Apply one inventory report to ``node``. Returns the transition made ("offline",
    "ready") or None. Callers persist the node and notify via ``notify_transitions``."""
    if ready is False:
        # No heartbeat for a node whose kubelet is not answering — the Node object still
        # existing is not liveness. Take it out of placement right away rather than after the
        # stale window: Kubernetes has already decided the node is unreachable.
        if node.status in LIVE_STATUSES:
            node.status = "offline"
            return "offline"
        return None
    node.last_seen_at = datetime.now(UTC)
    if node.status == "offline":
        node.status = "ready"
        return "ready"
    return None


def stale_sweep(node: GpuNode, cutoff: datetime) -> str | None:
    """The fallback for a dead operator (no reports at all): silent past ``cutoff`` → offline."""
    if node.status == "cordoned":
        return None
    seen = node.last_seen_at
    if seen is not None and seen.tzinfo is None:
        seen = seen.replace(tzinfo=UTC)
    if (seen is None or seen < cutoff) and node.status != "offline":
        node.status = "offline"
        return "offline"
    return None


async def notify_transitions(db: AsyncSession, offline: list[GpuNode], online: list[GpuNode]) -> None:
    """Tell every super_admin, once per transition, through the channel the console already
    surfaces (bell + history)."""
    if not offline and not online:
        return
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
    for node in offline:
        await svc.notify(
            supers, "node_offline", f"Node offline: {node.hostname}",
            "The node stopped answering; it is out of placement and its sessions are being ended.",
            params={"hostname": node.hostname, "stale_min": stale_min}, node_id=node.id,
        )
    for node in online:
        await svc.notify(
            supers, "node_online", f"Node back online: {node.hostname}",
            "The node is reporting again; it takes placements again.",
            params={"hostname": node.hostname}, node_id=node.id,
        )
    log.info("node status: offline=%s online=%s", [n.hostname for n in offline], [n.hostname for n in online])

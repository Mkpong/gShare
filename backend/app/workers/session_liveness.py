"""session_liveness — a running session whose pod the operator has stopped seeing is settled.

The operator heartbeats every running/preparing session (``phase=heartbeat``); the control
plane never inspects Kubernetes itself. When the heartbeat stops but the operator is otherwise
alive — its node inventory is still fresh — the pod is gone without a terminal phase (deleted by
hand, evicted from a node that later vanished, lost with an operator restart mid-teardown) and
the session would otherwise bill and hold its GPU slice forever.

The guard matters: with the operator down every session goes quiet at once, and ending them all
would turn a control-plane outage into data loss. Then this loop only logs.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.core.config import settings
from app.core.logging import get_logger
from app.db.base import get_sessionmaker
from app.db.models import GpuNode, Session
from app.domain.session_service import SessionService

log = get_logger(__name__)

REASON = "pod_lost"


async def run() -> None:
    now = datetime.now(UTC)
    stale_before = now - timedelta(seconds=settings.SESSION_STALE_SEC)
    async with get_sessionmaker()() as db:
        # Operator liveness per cluster: the newest node heartbeat.
        fresh = {
            cid for cid, seen in (await db.execute(
                select(GpuNode.cluster_id, func.max(GpuNode.last_seen_at)).group_by(GpuNode.cluster_id)
            )).all()
            if seen is not None and _aware(seen) >= now - timedelta(seconds=settings.NODE_STALE_SEC)
        }
        rows = (await db.execute(
            select(Session.id, Session.cluster_id, Session.name).where(
                Session.status.in_(("running", "preparing")),
                Session.deleted_at.is_(None),
                Session.last_reported_at.is_not(None),
                Session.last_reported_at < stale_before,
            )
        )).all()
    lost = [(sid, name) for sid, cid, name in rows if cid in fresh]
    skipped = [sid for sid, cid, _ in rows if cid not in fresh]
    if skipped:
        log.warning("session_liveness: %d stale sessions on clusters with no operator heartbeat — leaving them", len(skipped))
    for sid, name in lost:
        async with get_sessionmaker()() as db:
            try:
                await SessionService(db).terminate(sid, forced=True, reason=REASON)
                log.info("session_liveness: session %s (%s) lost its pod — settled", sid, name)
            except Exception:  # noqa: BLE001
                log.exception("session_liveness: could not settle lost session %s", sid)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)

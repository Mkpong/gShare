"""node_liveness — the fallback and the consequence of a node going offline.

The operator marks a node offline the moment its Ready condition drops (inventory_sync). This
loop covers the case where the operator itself stops reporting (``NODE_STALE_SEC`` of silence →
offline), restores nothing by itself (a fresh report does that), and — either way a node ended up
offline — ends the sessions that were placed on it: their pods are unreachable, so leaving them
"running" would bill the owner for a machine that is gone and keep the GPU slice reserved.
Paused sessions are left alone (no pod; they can resume on another node).
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.config import settings
from app.core.logging import get_logger
from app.db.base import get_sessionmaker
from app.db.models import GpuNode, Session
from app.domain import node_status
from app.domain.session_service import SessionService

log = get_logger(__name__)

# Sessions with a pod (or one on the way) that cannot survive their node leaving.
STRANDED_STATUSES = ("preparing", "running")
REASON = "node_offline"


async def run() -> None:
    cutoff = datetime.now(UTC) - timedelta(seconds=settings.NODE_STALE_SEC)
    marked: list[GpuNode] = []
    offline_hosts: set[str] = set()
    async with get_sessionmaker()() as db:
        async with db.begin():
            nodes = (await db.scalars(select(GpuNode))).all()
            # Operator liveness per cluster: if NO node of a cluster has a fresh heartbeat, the
            # silence is the operator's, not the nodes' — marking them all offline (and ending
            # every session on them) would turn a control-plane outage into data loss.
            alive_clusters = {
                n.cluster_id for n in nodes
                if n.last_seen_at is not None and _aware(n.last_seen_at) >= cutoff
            }
            for node in nodes:
                if node.cluster_id not in alive_clusters:
                    continue
                if node_status.stale_sweep(node, cutoff) == "offline":
                    marked.append(node)
            for node in nodes:
                if node.status == "offline" and node.cluster_id in alive_clusters:
                    offline_hosts.add(node.hostname)
            silent = {n.cluster_id for n in nodes} - alive_clusters
            if silent:
                log.warning("node_liveness: no operator heartbeat for clusters %s — leaving their nodes and sessions alone", sorted(silent))
            if marked:
                await node_status.notify_transitions(db, marked, [])
    if marked:
        log.info("node_liveness: stale → offline %s", [n.hostname for n in marked])
    if offline_hosts:
        await _end_stranded_sessions(offline_hosts)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


async def _end_stranded_sessions(hosts: set[str]) -> None:
    async with get_sessionmaker()() as db:
        stranded = (
            await db.scalars(
                select(Session.id).where(
                    Session.node_hostname.in_(sorted(hosts)),
                    Session.status.in_(STRANDED_STATUSES),
                    Session.deleted_at.is_(None),
                )
            )
        ).all()
    for sid in stranded:
        # One session per unit of work: terminate() manages its own transactions and locks, and
        # a failure on one session must not stop the others from being settled.
        async with get_sessionmaker()() as db:
            try:
                await SessionService(db).terminate(sid, forced=True, reason=REASON)
                log.info("node_liveness: terminated stranded session %s", sid)
            except Exception:  # noqa: BLE001
                log.exception("node_liveness: could not terminate stranded session %s", sid)

"""Internal inventory callbacks: operator reflects measured GPU inventory.

POST /internal/inventory/gpu-devices — upsert one GpuDevice (+ its GpuNode) into the ledger.
POST /internal/inventory/drift — Σused>total drift signal (logged; ledger stays the truth).
POST /internal/nodes/health-events — node health transition (cordon/alert) — accepted/logged.
RS256 internal JWT required (aud=gshare-internal). Python is the only DB writer.
"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.internal import (
    OperatorGpuDeviceUpsert,
    OperatorNodeHealthEvent,
    OperatorNodeUpsert,
)
from app.auth.internal_jwt import operator_cluster, require_internal_jwt, require_operator_cluster
from app.cluster.inventory_sync import InventorySync
from app.core import ids
from app.core.logging import get_logger
from app.db.base import get_db
from app.db.models import GpuNode, NodeHealthEvent
from app.domain.audit_service import AuditService

log = get_logger(__name__)
router = APIRouter(tags=["internal"])


@router.post("/internal/inventory/gpu-devices", status_code=status.HTTP_202_ACCEPTED)
async def upsert_gpu_device(
    ev: OperatorGpuDeviceUpsert,
    claims: dict = Depends(require_internal_jwt),     # aud=gshare-internal
    db: AsyncSession = Depends(get_db),
):
    # The token says which cluster is reporting; a payload that names another one is refused
    # rather than believed, so no attached cluster can rewrite a neighbour's inventory.
    require_operator_cluster(claims, ev.cluster_id, what="inventory report")
    cluster_id = operator_cluster(claims) or ev.cluster_id or str(claims.get("sub", ""))
    await InventorySync(db).upsert_device(ev, cluster_id)
    return {"accepted": True}


@router.post("/internal/inventory/nodes", status_code=status.HTTP_202_ACCEPTED)
async def upsert_node(
    ev: OperatorNodeUpsert,
    claims: dict = Depends(require_internal_jwt),     # aud=gshare-internal
    db: AsyncSession = Depends(get_db),
):
    # The token says which cluster is reporting; a payload that names another one is refused
    # rather than believed, so no attached cluster can rewrite a neighbour's inventory.
    require_operator_cluster(claims, ev.cluster_id, what="inventory report")
    cluster_id = operator_cluster(claims) or ev.cluster_id or str(claims.get("sub", ""))
    await InventorySync(db).upsert_node(ev, cluster_id)
    return {"accepted": True}


@router.get("/internal/nodes/cordoned")
async def cordoned_nodes(
    claims: dict = Depends(require_internal_jwt),
    db: AsyncSession = Depends(get_db),
):
    """Hostnames the ledger holds as cordoned, for the operator to mirror onto the Kubernetes
    nodes (spec.unschedulable). The control plane never touches Kubernetes itself; without this
    mirror a gShare cordon only steered the ledger's card placement and kube-scheduler could still
    put a CPU session — or a resumed one — straight back on a node being drained."""
    sub = str(claims.get("sub", ""))
    cluster_id = sub.split(":", 1)[1] if sub.startswith("operator:") else sub
    rows = await db.scalars(
        select(GpuNode.hostname).where(GpuNode.cluster_id == cluster_id, GpuNode.status == "cordoned")
    )
    return {"hostnames": sorted(set(rows.all()))}


@router.get("/internal/nodes/decommissioning")
async def decommissioning_nodes(
    claims: dict = Depends(require_internal_jwt),
    db: AsyncSession = Depends(get_db),
):
    """Hostnames an administrator asked to remove from the cluster.

    The console's delete button clears the ledger and parks the node here; the operator deletes
    the matching Node object and calls back below. Without that second step the Node object
    survives, every inventory pass recreates the row, and the node reappears in the console —
    which is why removing a node used to need a manual `kubectl delete node`.
    """
    sub = str(claims.get("sub", ""))
    cluster_id = sub.split(":", 1)[1] if sub.startswith("operator:") else sub
    rows = await db.scalars(
        select(GpuNode.hostname).where(
            GpuNode.cluster_id == cluster_id, GpuNode.status == "decommissioning"
        )
    )
    return {"hostnames": sorted(set(rows.all()))}


@router.post("/internal/nodes/decommissioned", status_code=status.HTTP_202_ACCEPTED)
async def node_decommissioned(
    claims: dict = Depends(require_internal_jwt),
    body: dict = Body(default_factory=dict),
    db: AsyncSession = Depends(get_db),
):
    """The operator confirms the Node object is gone; the ledger row goes with it."""
    hostname = str(body.get("hostname") or "").strip()
    if not hostname:
        return {"accepted": False}
    sub = str(claims.get("sub", ""))
    cluster_id = sub.split(":", 1)[1] if sub.startswith("operator:") else sub
    node = (
        await db.execute(
            select(GpuNode).where(
                GpuNode.cluster_id == cluster_id,
                GpuNode.hostname == hostname,
                GpuNode.status == "decommissioning",
            )
        )
    ).scalar_one_or_none()
    if node is None:
        return {"accepted": True}   # already finalised
    await AuditService(db).record(
        actor=f"operator:{cluster_id}", action="node.delete", target=node.id, result="ok",
        hostname=hostname, cluster_id=cluster_id, removed_from_cluster=True,
    )
    await db.delete(node)
    await db.commit()
    log.info("node %s removed from the cluster and the ledger", hostname)
    return {"accepted": True}


@router.post("/internal/inventory/drift", status_code=status.HTTP_202_ACCEPTED)
async def report_drift(
    _claims: dict = Depends(require_internal_jwt),
    body: dict = Body(default_factory=dict),
):
    # Ledger is the source of truth; we log the drift signal for reconciliation/alerting.
    log.warning("inventory drift reported: %s", body)
    return {"accepted": True}


@router.post("/internal/nodes/health-events", status_code=status.HTTP_202_ACCEPTED)
async def node_health_event(
    ev: OperatorNodeHealthEvent,
    claims: dict = Depends(require_internal_jwt),
    db: AsyncSession = Depends(get_db),
):
    """Record a NodeHealthEvent and, on a cordon action, mark GpuNode.status=cordoned.

    The operator already cordoned the K8s node; the ledger reflects it so the console/scheduler
    stop placing new sessions there.

    The operator's HealthReconciler addresses the node by its Kubernetes NAME (the hostname): it
    has no ledger id. The row is therefore resolved by (token cluster, hostname) — with the ledger
    id still accepted for older callers — and the event carries the row's id, which the FK needs.
    Looking the hostname up as an id never matched: the cordon never reached the ledger and the
    event insert violated the FK on Postgres.
    """
    require_operator_cluster(claims, ev.cluster_id, what="health event")
    cluster_id = operator_cluster(claims) or ev.cluster_id
    async with db.begin():
        node_q = select(GpuNode).where(
            or_(GpuNode.hostname == ev.node_id, GpuNode.id == ev.node_id)
        )
        if cluster_id is not None:
            node_q = node_q.where(GpuNode.cluster_id == cluster_id)
        node = (await db.execute(node_q.limit(1))).scalar_one_or_none()
        hostname = ev.node_id
        if node is None:
            # No dangling FK row for a node the ledger does not know; the signal is still logged.
            log.warning("node health event for unknown node=%s cluster=%s kind=%s action=%s",
                        ev.node_id, cluster_id, ev.kind, ev.action)
            return {"accepted": True}
        db.add(
            NodeHealthEvent(
                id=ev.id or ids.new("healthevent"),
                node_id=node.id,
                kind=ev.kind,
                severity=ev.severity,
                action=ev.action,
            )
        )
        hostname = node.hostname
        if (ev.action or "").lower() == "cordon":
            node.status = "cordoned"
        # Warning, critical, and cordon events notify the system administrators.
        if (ev.severity or "").lower() in ("warn", "warning", "critical") or (ev.action or "").lower() == "cordon":
            from app.domain.notification_service import NotificationService
            from app.domain.webhook_outbox import emit_webhook_safe

            notifier = NotificationService(db)
            await notifier.notify(
                await notifier.system_admins(), "node_health",
                f"Node health: {ev.kind}",
                f"Node '{hostname}': {ev.kind} (severity={ev.severity}, action={ev.action}).",
                params={"hostname": hostname, "kind": ev.kind, "severity": ev.severity,
                        "action": ev.action},
                node_id=ev.node_id, kind=ev.kind, action=ev.action,
            )
            await emit_webhook_safe(db, "node_health.event", {
                "node_id": ev.node_id, "hostname": hostname, "kind": ev.kind,
                "severity": ev.severity, "action": ev.action,
            })
    log.warning("node health event: node=%s kind=%s action=%s", ev.node_id, ev.kind, ev.action)
    return {"accepted": True}

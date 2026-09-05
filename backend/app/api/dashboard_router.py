"""User dashboard summary. Aggregates KPIs the console dashboard renders:
credit, active sessions, GPU VRAM, region (GPU model) availability, resource allocation.
Read-only; principal-scoped (owner's sessions/wallet). Real ledger/inventory values."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_principal
from app.api.schemas.dashboard import DashboardSummary
from app.auth.rbac import Principal
from app.db.base import get_db
from app.db.models import CreditWallet, GpuDevice, GpuNode, Membership, Project, Session
from app.domain.node_pools import resolve_pool_access
from app.domain.policy import resolve_effective_policy

router = APIRouter(tags=["dashboard"])


def managed_owner_filter(principal: Principal, scope: str):
    """The session-owner predicate for the summary.

    ``mine`` (default) is the caller's own sessions. ``managed`` widens it to the people the caller
    administers — every user in the groups they are group_admin of, every group of the organizations
    they are org_admin of, or everyone for a super_admin. A plain member asking for ``managed`` gets
    ``mine``: there is nothing wider to show, and the answer must never leak beyond their tenancy.
    """
    if scope != "managed":
        return Session.owner_user_id == principal.user_id
    if principal.global_role == "super_admin":
        return None
    group_ids = {g for g, role in principal.memberships.items() if role in ("group_admin", "org_admin")}
    org_groups = None
    if principal.org_admin_orgs:
        org_groups = select(Project.id).where(
            Project.org_id.in_(list(principal.org_admin_orgs)), Project.deleted_at.is_(None)
        )
    if not group_ids and org_groups is None:
        return Session.owner_user_id == principal.user_id
    members = select(Membership.user_id).where(Membership.group_id.is_not(None))
    if group_ids and org_groups is not None:
        members = members.where(
            or_(Membership.group_id.in_(list(group_ids)), Membership.group_id.in_(org_groups))
        )
    elif group_ids:
        members = members.where(Membership.group_id.in_(list(group_ids)))
    else:
        members = members.where(Membership.group_id.in_(org_groups))
    # The admin's own sessions count too — they are part of what they run.
    return or_(Session.owner_user_id.in_(members), Session.owner_user_id == principal.user_id)


def _where(stmt, pred):
    return stmt if pred is None else stmt.where(pred)


@router.get("/dashboard/summary", response_model=DashboardSummary)
async def dashboard_summary(
    scope: Literal["mine", "managed"] = Query(default="mine"),
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    # Whose sessions: the caller's own, or — for an administrator's dashboard — the tenants they
    # manage (see managed_owner_filter).
    owner = managed_owner_filter(principal, scope)
    running = (
        await db.scalar(
            _where(select(func.count()).select_from(Session), owner)
            .where(Session.status == "running")
        )
    ) or 0
    active = (
        await db.scalar(
            _where(select(func.count()).select_from(Session), owner)
            .where(Session.status.in_(("pending", "preparing", "running", "paused")))
        )
    ) or 0

    # The owner's credit wallet: balance and reserved.
    wallet = (
        await db.execute(
            select(CreditWallet).where(
                CreditWallet.owner_type == "user", CreditWallet.owner_id == principal.user_id
            )
        )
    ).scalar_one_or_none()
    credit = {
        "available": float(wallet.balance - wallet.reserved) if wallet else None,
        "balance": float(wallet.balance) if wallet else None,
        "reserved": float(wallet.reserved) if wallet else None,
    }

    # The caller's groups: sessions are admitted under a GROUP context, so both the policy and the
    # node-pool view below are resolved per group (several groups → union / strictest).
    group_ids = list(
        (
            await db.execute(
                select(Membership.group_id).where(
                    Membership.user_id == principal.user_id, Membership.group_id.is_not(None)
                )
            )
        ).scalars()
    ) or [None]

    # GPU inventory over the cluster's ready devices: availability per model and the cluster VRAM
    # KPI. Both are scoped to the pools the caller may place on (computed below) — a tenant must
    # not see VRAM on cards dedicated to another organization as "cluster" capacity.
    # A cordoned or offline node cannot take a new session, so its cards are not "available":
    # the wizard (sessions_router.gpu_availability) and admission (scheduler.reserve_slice) apply
    # the same node-state filter, and the three views must agree.
    devices = (
        await db.execute(
            select(GpuDevice)
            .join(GpuNode, GpuNode.id == GpuDevice.node_id, isouter=True)
            .where(
                GpuDevice.status == "ready",
                or_(GpuNode.id.is_(None), GpuNode.status == "ready"),
            )
        )
    ).scalars().all()

    # Node pools: per-model availability counts only cards on nodes the caller may place on
    # (union of the allowed sets across the caller's groups, per cluster).
    node_pool: dict[str, str | None] = {}
    node_ids = {d.node_id for d in devices}
    if node_ids:
        node_pool = {
            n: p
            for n, p in (
                await db.execute(
                    select(GpuNode.id, GpuNode.pool_id).where(GpuNode.id.in_(node_ids))
                )
            ).all()
        }
    allowed_by_cluster: dict[str, set[str | None]] = {}
    pools: list[dict] = []
    seen_pool_ids: set[str | None] = set()
    for cid in sorted({d.cluster_id for d in devices}):
        allowed: set[str | None] = set()
        for g in group_ids:
            access = await resolve_pool_access(
                db, cluster_id=cid, user_id=principal.user_id, group_id=g
            )
            allowed |= access.allowed()
            for p in access.pools:
                if p["id"] not in seen_pool_ids:
                    seen_pool_ids.add(p["id"])
                    pools.append(p)
        allowed_by_cluster[cid] = allowed
    has_unassigned = any(
        node_pool.get(d.node_id) is None and None in allowed_by_cluster.get(d.cluster_id, set())
        for d in devices
    )
    if has_unassigned and None not in seen_pool_ids:
        pools.append({"id": None, "name": "shared", "kind": "shared", "tier": "shared"})
    # Same rule as /sessions/gpu-availability (single source: node_pools.accessible_devices);
    # the per-cluster sets above are still needed for the pools chip list.
    visible = [
        d for d in devices
        if node_pool.get(d.node_id) in allowed_by_cluster.get(d.cluster_id, set())
    ]
    # The cluster VRAM KPI reflects only accessible cards, consistent with per-model availability.
    total_mem = sum(d.total_mem_mb or 0 for d in visible)
    used_mem = sum(d.used_mem_mb or 0 for d in visible)
    by_model: dict[str, dict] = {}
    for d in visible:
        m = by_model.setdefault(
            d.model or "unknown",
            {"model": d.model or "unknown", "total": 0, "free": 0, "free_mb": 0, "total_mb": 0},
        )
        m["total"] += 1
        m["total_mb"] += d.total_mem_mb or 0
        m["free_mb"] += max(0, (d.total_mem_mb or 0) - (d.used_mem_mb or 0))
        if (d.used_mem_mb or 0) == 0 and (d.used_cores or 0) == 0:
            m["free"] += 1
    regions = sorted(by_model.values(), key=lambda x: x["model"])

    # The instance cap is the caller's effective policy max_concurrent — the number a user can
    # actually run at once. Sessions are admitted under a GROUP context, so the policy must be
    # resolved with the caller's groups, not bare (which would skip a stricter group/org policy
    # and show the global one). With several groups the strictest value wins, per field, so the
    # dashboard never promises more than admission would allow.
    pols = [await resolve_effective_policy(db, principal.user_id, g) for g in group_ids]
    pols = [p for p in pols if p is not None]

    def _min_field(getter) -> int | None:
        vals = [v for v in (getter(p) for p in pols) if v]
        return min(vals) if vals else None

    pol_max_concurrent = _min_field(lambda p: p.max_concurrent)
    inst_total = pol_max_concurrent or max(active, 1)

    # Host compute held by the caller's active sessions, against the policy's aggregate limits
    # (cpu / mem_gb; session disk counts toward storage_gb, mirroring the quota check).
    comp = (
        await db.execute(
            _where(
                select(
                    func.coalesce(func.sum(Session.cpu), 0),
                    func.coalesce(func.sum(Session.mem_gb), 0),
                    func.coalesce(func.sum(Session.disk_gb), 0),
                    func.coalesce(func.sum(Session.gpu_mem_mb), 0),
                    func.coalesce(func.sum(Session.gpu_cores), 0),
                ).where(Session.status.in_(("pending", "preparing", "running"))),
                owner,
            )
        )
    ).one()
    if scope == "managed":
        # An administrator's VRAM figure is what THEIR people hold, not the cluster's occupancy —
        # the latter includes other tenants and is the super_admin dashboard's number.
        used_mem = int(comp[3])

    def _lim(key: str) -> int | None:
        return _min_field(lambda p: int((p.limits or {}).get(key) or 0))

    compute = {
        "cpu": {"used": int(comp[0]), "limit": _lim("cpu")},
        "mem_gb": {"used": int(comp[1]), "limit": _lim("mem_gb")},
        "disk_gb": {"used": int(comp[2]), "limit": _lim("storage_gb")},
    }

    return {
        "credit": credit,
        "sessions": {"running": running, "active": active},
        # Cluster-wide inventory occupancy — availability context, everyone's sessions included.
        "vram": {"used_mb": used_mem, "total_mb": total_mem},
        "regions": regions,
        "pools": pools,
        # The caller's own quota view: MY active sessions against MY policy — a member must never
        # see the fleet totals here and read them as their own usage.
        "allocation": {
            "instances": {"used": active, "total": inst_total},
            "vram": {"used_mb": int(comp[3]), "limit_mb": _lim("gpu_mem_mb")},
            # GPU core share is a policy dimension like the rest — without it the console shows a
            # quota the user cannot see themselves against.
            "gpu_cores": {"used": int(comp[4]), "limit": _lim("gpu_cores")},
        },
        "compute": compute,
    }

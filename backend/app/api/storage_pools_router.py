"""Volume-backing pools: registering where volumes actually live.

Storage used to be inferred — whichever nodes carried role="storage", their root disks added
together — which answered neither "which server" nor "how big is the pool". A pool is registered
instead: it belongs to the cluster its server sits in, states which clusters may place volumes on
it, and carries a capacity the operator measures from the CSI driver rather than one anybody
types in.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_principal
from app.auth.rbac import Principal
from app.core import ids
from app.core.errors import AlreadyExists, DomainError, NotFound
from app.db.base import get_db
from app.db.models import Cluster, GpuNode, StoragePool, StoragePoolShare
from app.domain.audit_service import AuditService
from app.domain.storage_pools import pool_capacity_gb

router = APIRouter(prefix="/storage/pools", tags=["storage"])

_SCOPES = ("all", "selected")


class _Validation(DomainError):
    code, http = "validation_failed", 422


class PoolCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    cluster_id: str                       # the cluster whose storage server this is
    storage_class: str = Field(min_length=1, max_length=200)
    node_id: str | None = None
    share_scope: str = Field(default="all", pattern="^(all|selected)$")
    shared_with: list[str] = []           # cluster ids, for share_scope=selected
    manual_capacity_gb: int | None = Field(default=None, ge=0)


class PoolPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    storage_class: str | None = Field(default=None, min_length=1, max_length=200)
    node_id: str | None = None
    share_scope: str | None = Field(default=None, pattern="^(all|selected)$")
    shared_with: list[str] | None = None
    manual_capacity_gb: int | None = Field(default=None, ge=0)


async def _view(db: AsyncSession, p: StoragePool, names: dict[str, str]) -> dict[str, Any]:
    cap, source = pool_capacity_gb(p)
    shared = list((await db.scalars(
        select(StoragePoolShare.cluster_id).where(StoragePoolShare.pool_id == p.id)
    )).all())
    return {
        "id": p.id,
        "name": p.name,
        "cluster_id": p.cluster_id,
        "cluster_name": names.get(p.cluster_id),
        "node_id": p.node_id,
        "node_hostname": p.node_hostname,
        "storage_class": p.storage_class,
        "share_scope": p.share_scope,
        "shared_with": shared,
        "shared_with_names": [names.get(c) for c in shared],
        "capacity_gb": cap,
        # csi = the driver measured it; manual = an administrator stated it; null = neither, and
        # the dashboard then falls back to the storage node's root disk and says so.
        "capacity_source": source,
        "capacity_reported_at": p.capacity_reported_at,
        "manual_capacity_gb": p.manual_capacity_gb,
        "created_at": p.created_at,
    }


async def _cluster_names(db: AsyncSession) -> dict[str, str]:
    return dict((await db.execute(select(Cluster.id, Cluster.name))).all())


async def _load(db: AsyncSession, pool_id: str) -> StoragePool:
    pool = await db.get(StoragePool, pool_id)
    if pool is None or pool.deleted_at is not None:
        raise NotFound("storage pool not found", {"pool_id": pool_id})
    return pool


async def _set_shares(db: AsyncSession, pool: StoragePool, cluster_ids: list[str]) -> None:
    """Replace the pool's explicit share list. The owning cluster is implicit and never listed."""
    wanted = {c for c in cluster_ids if c and c != pool.cluster_id}
    if wanted:
        known = set((await db.scalars(select(Cluster.id).where(Cluster.id.in_(wanted)))).all())
        missing = sorted(wanted - known)
        if missing:
            raise NotFound("cluster not found", {"cluster_id": missing[0]})
    existing = {
        row.cluster_id: row
        for row in (await db.scalars(
            select(StoragePoolShare).where(StoragePoolShare.pool_id == pool.id)
        )).all()
    }
    for cid in wanted - set(existing):
        db.add(StoragePoolShare(id=ids.new("storage_pool_share"), pool_id=pool.id, cluster_id=cid))
    for cid in set(existing) - wanted:
        await db.delete(existing[cid])


@router.get("")
async def list_pools(
    cluster_id: str | None = Query(default=None),
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    """Every registered pool; `cluster_id` narrows to the ones that cluster may use."""
    principal.require(action="storage_pool.read")
    from app.domain.storage_pools import usable_pools

    pools = await usable_pools(db, cluster_id)
    names = await _cluster_names(db)
    return {"data": [await _view(db, p, names) for p in pools]}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_pool(
    body: PoolCreate,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    """Register a pool. Capacity is left empty: the operator's next tick measures it."""
    principal.require(action="storage_pool.write")
    async with db.begin():
        cluster = await db.get(Cluster, body.cluster_id)
        if cluster is None or cluster.deleted_at is not None:
            raise NotFound("cluster not found", {"cluster_id": body.cluster_id})
        dup = (await db.scalars(
            select(StoragePool).where(
                StoragePool.cluster_id == body.cluster_id,
                StoragePool.storage_class == body.storage_class,
                StoragePool.deleted_at.is_(None),
            )
        )).first()
        if dup is not None:
            raise AlreadyExists(
                "a pool for this cluster and storage class already exists",
                {"pool_id": dup.id, "storage_class": body.storage_class},
            )
        hostname = None
        if body.node_id:
            node = await db.get(GpuNode, body.node_id)
            if node is None:
                raise NotFound("node not found", {"node_id": body.node_id})
            if node.cluster_id != body.cluster_id:
                raise _Validation("that node is in another cluster",
                                  {"node_id": body.node_id, "cluster_id": node.cluster_id})
            hostname = node.hostname
        pool = StoragePool(
            id=ids.new("storage_pool"), name=body.name.strip(), cluster_id=body.cluster_id,
            node_id=body.node_id, node_hostname=hostname, storage_class=body.storage_class.strip(),
            share_scope=body.share_scope, manual_capacity_gb=body.manual_capacity_gb,
            capacity_source="manual" if body.manual_capacity_gb else None,
        )
        db.add(pool)
        await db.flush()
        await _set_shares(db, pool, body.shared_with if body.share_scope == "selected" else [])
        await AuditService(db).record(
            actor=principal.user_id, action="storage_pool.create", target=pool.id, result="ok",
            cluster_id=pool.cluster_id, name=pool.name, storage_class=pool.storage_class,
            share_scope=pool.share_scope,
        )
    names = await _cluster_names(db)
    return await _view(db, pool, names)


@router.patch("/{pool_id}")
async def update_pool(
    pool_id: str,
    body: PoolPatch,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    principal.require(action="storage_pool.write")
    async with db.begin():
        pool = await _load(db, pool_id)
        changes: dict[str, Any] = {}
        if body.name is not None and body.name.strip() != pool.name:
            changes["name"] = {"from": pool.name, "to": body.name.strip()}
            pool.name = body.name.strip()
        if body.storage_class is not None and body.storage_class.strip() != pool.storage_class:
            # The class is the join key for the operator's capacity report; a changed class means
            # the stored measurement describes something else.
            changes["storage_class"] = {"from": pool.storage_class, "to": body.storage_class.strip()}
            pool.storage_class = body.storage_class.strip()
            pool.capacity_bytes = None
            pool.capacity_source = "manual" if pool.manual_capacity_gb else None
            pool.capacity_reported_at = None
        if body.node_id is not None:
            node = await db.get(GpuNode, body.node_id) if body.node_id else None
            if body.node_id and node is None:
                raise NotFound("node not found", {"node_id": body.node_id})
            if node is not None and node.cluster_id != pool.cluster_id:
                raise _Validation("that node is in another cluster",
                                  {"node_id": body.node_id, "cluster_id": node.cluster_id})
            changes["node_id"] = {"from": pool.node_id, "to": body.node_id or None}
            pool.node_id = body.node_id or None
            pool.node_hostname = node.hostname if node is not None else None
        if body.manual_capacity_gb is not None and body.manual_capacity_gb != pool.manual_capacity_gb:
            changes["manual_capacity_gb"] = {"from": pool.manual_capacity_gb, "to": body.manual_capacity_gb}
            pool.manual_capacity_gb = body.manual_capacity_gb or None
            if pool.capacity_bytes is None:
                pool.capacity_source = "manual" if pool.manual_capacity_gb else None
        if body.share_scope is not None and body.share_scope != pool.share_scope:
            changes["share_scope"] = {"from": pool.share_scope, "to": body.share_scope}
            pool.share_scope = body.share_scope
        if body.shared_with is not None or pool.share_scope == "all":
            await _set_shares(db, pool, body.shared_with or [] if pool.share_scope == "selected" else [])
        if changes:
            await AuditService(db).record(
                actor=principal.user_id, action="storage_pool.update", target=pool.id,
                result="ok", cluster_id=pool.cluster_id, changes=changes,
            )
    names = await _cluster_names(db)
    return await _view(db, pool, names)


@router.delete("/{pool_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pool(
    pool_id: str,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    """Deregister a pool. Nothing on the storage server is touched — this only stops gShare
    counting it; the volumes already on it keep working through their StorageClass."""
    principal.require(action="storage_pool.write")
    async with db.begin():
        pool = await _load(db, pool_id)
        await _set_shares(db, pool, [])
        from datetime import UTC, datetime

        pool.deleted_at = datetime.now(UTC)
        await AuditService(db).record(
            actor=principal.user_id, action="storage_pool.delete", target=pool.id, result="ok",
            cluster_id=pool.cluster_id, name=pool.name,
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)

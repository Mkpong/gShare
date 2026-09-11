"""Which volume-backing pools a cluster may use, and how big they are.

A volume lives on exactly one pool: the StorageClass its PVC names decides where, and gShare
chooses nothing. Two consequences run through everything here.

Pools are never summed. Two 2 TB servers are not a 4 TB pool, and adding them up licensed volumes
no single server could hold. The bound is the largest pool a placement could actually use.

Capacity is measured, not typed in. The operator reads the CSI driver's own answer
(CSIStorageCapacity) and reports it; `STORAGE_POOL_CAPACITY_GB` and the storage node's root disk
are fallbacks for a site whose driver publishes nothing, and each reading says which it is so a
guess never passes for a measurement.
"""
from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import GpuNode, StoragePool, StoragePoolShare

GB = 1024 ** 3


async def usable_pools(db: AsyncSession, cluster_id: str | None) -> list[StoragePool]:
    """Live pools a session on `cluster_id` could be placed on; every live pool when None.

    A pool serves its own cluster always, every cluster when it is shared fleet-wide, and the
    clusters named in StoragePoolShare when sharing is restricted.
    """
    stmt = select(StoragePool).where(StoragePool.deleted_at.is_(None))
    if cluster_id:
        shared_with = select(StoragePoolShare.pool_id).where(
            StoragePoolShare.cluster_id == cluster_id
        )
        stmt = stmt.where(
            or_(
                StoragePool.cluster_id == cluster_id,
                StoragePool.share_scope == "all",
                StoragePool.id.in_(shared_with),
            )
        )
    return list((await db.execute(stmt.order_by(StoragePool.name.asc()))).scalars().all())


def pool_capacity_gb(pool: StoragePool) -> tuple[int | None, str | None]:
    """(capacity, source) for one pool, measurement first."""
    if pool.capacity_bytes:
        return int(pool.capacity_bytes // GB), "csi"
    if pool.manual_capacity_gb:
        return int(pool.manual_capacity_gb), "manual"
    return None, None


async def pool_bound_gb(db: AsyncSession, cluster_id: str | None = None) -> tuple[int | None, str]:
    """The largest capacity a volume placed from `cluster_id` could actually land in.

    Returns (capacity_gb, source). None means nothing is known — no registered pool with a
    capacity, no configured figure and no storage node — and callers treat that as "no gate"
    rather than as zero.
    """
    best, source = 0, ""
    for pool in await usable_pools(db, cluster_id):
        cap, src = pool_capacity_gb(pool)
        if cap and cap > best:
            best, source = cap, src or ""
    if best:
        return best, source
    # No pool carries a capacity yet. The chart's figure is the administrator's own statement
    # about the pool, so it outranks the node disk — which is the machine's system drive and only
    # ever a rough stand-in.
    if settings.STORAGE_POOL_CAPACITY_GB:
        return int(settings.STORAGE_POOL_CAPACITY_GB), "manual"
    node_disk = await db.scalar(
        select(GpuNode.disk).where(GpuNode.role == "storage").order_by(GpuNode.disk.desc()).limit(1)
    )
    if node_disk:
        return int(node_disk), "node_disk"
    return None, ""

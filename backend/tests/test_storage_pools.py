"""Pools are registered, scoped to clusters, and measured — not inferred from node disks.

Before this, storage was whichever nodes carried role="storage", their root disks summed into one
number. That answered neither which server a volume lands on nor how big the pool behind it is,
and the sum licensed volumes no single server could hold.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.api.schemas.internal import OperatorPoolCapacity, OperatorVolumeSync
from app.cluster.volume_sync import VolumeSync
from app.core import ids
from app.core.config import settings
from app.db.models import Cluster, GpuNode, StoragePool, StoragePoolShare
from app.domain.storage_pools import GB, pool_bound_gb, pool_capacity_gb, usable_pools


async def _cluster(db, cid: str) -> None:
    async with db.begin():
        db.add(Cluster(id=cid, name=cid, role="primary", api_server="https://x", runtime="containerd",
                       status="connected", kubeconfig_secret_ref=""))


async def _pool(db, *, cluster_id: str, name: str, scope: str = "all",
                storage_class: str = "gshare-data", capacity_bytes: int | None = None,
                manual_gb: int | None = None) -> StoragePool:
    p = StoragePool(id=ids.new("storage_pool"), name=name, cluster_id=cluster_id,
                    storage_class=storage_class, share_scope=scope,
                    capacity_bytes=capacity_bytes, manual_capacity_gb=manual_gb,
                    capacity_source="csi" if capacity_bytes else ("manual" if manual_gb else None))
    async with db.begin():
        db.add(p)
    return p


@pytest.mark.asyncio
async def test_a_pool_serves_its_own_cluster_and_shared_ones(db):
    await _cluster(db, "clu_a")
    await _cluster(db, "clu_b")
    own = await _pool(db, cluster_id="clu_a", name="A only", scope="selected")
    everyone = await _pool(db, cluster_id="clu_a", name="fleet", scope="all",
                           storage_class="gshare-shared")
    assert {p.id for p in await usable_pools(db, "clu_a")} == {own.id, everyone.id}
    assert {p.id for p in await usable_pools(db, "clu_b")} == {everyone.id}
    await db.commit()   # close the read transaction before the write below opens its own
    # Sharing A's restricted pool with B explicitly brings it into B's view.
    async with db.begin():
        db.add(StoragePoolShare(id=ids.new("storage_pool_share"), pool_id=own.id, cluster_id="clu_b"))
    assert {p.id for p in await usable_pools(db, "clu_b")} == {own.id, everyone.id}


@pytest.mark.asyncio
async def test_pools_are_never_summed(db):
    """Two 2 TB servers are not a 4 TB pool: a volume lands on one of them."""
    await _cluster(db, "clu_a")
    await _pool(db, cluster_id="clu_a", name="one", capacity_bytes=2000 * GB)
    await _pool(db, cluster_id="clu_a", name="two", capacity_bytes=2000 * GB,
                storage_class="gshare-other")
    cap, source = await pool_bound_gb(db, "clu_a")
    assert (cap, source) == (2000, "csi")


@pytest.mark.asyncio
async def test_a_measurement_outranks_a_typed_in_figure(db):
    await _cluster(db, "clu_a")
    p = await _pool(db, cluster_id="clu_a", name="p", capacity_bytes=1424 * GB, manual_gb=9999)
    assert pool_capacity_gb(p) == (1424, "csi")


@pytest.mark.asyncio
async def test_the_configured_figure_beats_the_node_disk(db, monkeypatch):
    """Both are stand-ins, but one is a statement about the pool and the other is a system drive."""
    async with db.begin():
        db.add(GpuNode(id=ids.new("node"), cluster_id="clu_a", hostname="store", status="ready",
                       role="storage", disk=2062))
    monkeypatch.setattr(settings, "STORAGE_POOL_CAPACITY_GB", 1424)
    assert await pool_bound_gb(db) == (1424, "manual")


@pytest.mark.asyncio
async def test_nothing_known_is_not_zero(db, monkeypatch):
    monkeypatch.setattr(settings, "STORAGE_POOL_CAPACITY_GB", 0)
    assert await pool_bound_gb(db) == (None, "")


@pytest.mark.asyncio
async def test_the_operator_report_fills_in_the_capacity(db):
    await _cluster(db, "clu_a")
    pool = await _pool(db, cluster_id="clu_a", name="p")
    before = datetime.now(UTC)
    await VolumeSync(db).sync(OperatorVolumeSync(
        volumes=[], cluster_id="clu_a",
        pools=[OperatorPoolCapacity(storage_class="gshare-data", capacity_bytes=1424 * GB)],
    ))
    async with db.begin():
        row = await db.get(StoragePool, pool.id)
        assert row.capacity_bytes == 1424 * GB
        assert row.capacity_source == "csi"
        assert row.capacity_reported_at >= before


@pytest.mark.asyncio
async def test_capacity_for_an_unregistered_class_is_ignored(db):
    """A reading with no registered pool has no owner and no sharing rule; inventing one would
    decide both on the administrator's behalf."""
    await _cluster(db, "clu_a")
    pool = await _pool(db, cluster_id="clu_a", name="p")
    await VolumeSync(db).sync(OperatorVolumeSync(
        volumes=[], cluster_id="clu_a",
        pools=[OperatorPoolCapacity(storage_class="something-else", capacity_bytes=99 * GB)],
    ))
    async with db.begin():
        assert (await db.get(StoragePool, pool.id)).capacity_bytes is None
        assert await db.scalar(
            __import__("sqlalchemy").select(__import__("sqlalchemy").func.count())
            .select_from(StoragePool)
        ) == 1

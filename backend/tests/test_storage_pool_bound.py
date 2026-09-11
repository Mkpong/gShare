"""Several storage servers are not one pool.

A volume lives on exactly one pool: the StorageClass its PVC names decides where, and gShare picks
nothing. Adding the storage nodes' disks together therefore licensed volumes no single server
could hold — a 3 TB volume waved through by two 2 TB servers, then ENOSPC at first write. The gate
and the dashboard also read the capacity from different places, so an administrator who corrected
one figure did not correct the other.
"""
from __future__ import annotations

import pytest

from app.api.volumes_router import _physical_storage
from app.core import ids
from app.core.config import settings
from app.db.models import GpuNode, StorageVolume


async def _servers(db, *disks: int) -> None:
    async with db.begin():
        db.add_all([
            GpuNode(id=ids.new("node"), cluster_id="clu_a", hostname=f"store{i}", status="ready",
                    role="storage", disk=d)
            for i, d in enumerate(disks)
        ])


@pytest.mark.asyncio
async def test_two_servers_do_not_make_one_big_pool(db):
    await _servers(db, 2000, 2000)
    cap, allocated = await _physical_storage(db)
    assert cap == int(2000 * 0.95)          # the largest single server, not 4000
    assert allocated == 0


@pytest.mark.asyncio
async def test_the_largest_server_is_the_bound(db):
    await _servers(db, 500, 3000, 1000)
    cap, _ = await _physical_storage(db)
    assert cap == int(3000 * 0.95)


@pytest.mark.asyncio
async def test_the_administrators_figure_wins(db, monkeypatch):
    """The operator reports a node's root disk, not the ZFS pool behind it. When the chart states
    the real capacity, the gate must use it — the dashboard already did."""
    await _servers(db, 2000, 2000)
    monkeypatch.setattr(settings, "STORAGE_POOL_CAPACITY_GB", 7000)
    cap, _ = await _physical_storage(db)
    assert cap == int(7000 * 0.95)


@pytest.mark.asyncio
async def test_no_storage_server_means_no_gate(db):
    assert await _physical_storage(db) == (None, 0)


@pytest.mark.asyncio
async def test_allocation_counts_every_live_volume(db):
    await _servers(db, 2000)
    async with db.begin():
        db.add_all([
            StorageVolume(id=ids.new("volume"), scope="user", scope_id="usr_1", type="home",
                          access_mode="RWO", quota_gb=40, used_gb=0),
            StorageVolume(id=ids.new("volume"), scope="user", scope_id="usr_2", type="home",
                          access_mode="RWO", quota_gb=60, used_gb=0),
        ])
    _, allocated = await _physical_storage(db)
    assert allocated == 100

"""Pools are registered, scoped to clusters, and measured — not inferred from node disks.

Before this, storage was whichever nodes carried role="storage", their root disks summed into one
number. That answered neither which server a volume lands on nor how big the pool behind it is,
and the sum licensed volumes no single server could hold.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.api.schemas.internal import OperatorPoolCapacity, OperatorVolumeSync
from app.cluster.volume_sync import VolumeSync
from app.core import ids
from app.core.config import settings
from app.db.models import Cluster, GpuNode, StoragePool, StoragePoolShare
from app.domain.storage_pools import GB, pool_bound_gb, pool_capacity_gb, usable_pools
from tests.fkseed import seed


async def _cluster(db, cid: str) -> None:
    await seed(db, [
        Cluster(id=cid, name=cid, role="primary", api_server="https://x", runtime="containerd",
                   status="connected", kubeconfig_secret_ref=""),
    ])


async def _pool(db, *, cluster_id: str, name: str, scope: str = "all",
                storage_class: str = "gshare-data", capacity_bytes: int | None = None,
                manual_gb: int | None = None) -> StoragePool:
    p = StoragePool(id=ids.new("storage_pool"), name=name, cluster_id=cluster_id,
                    storage_class=storage_class, share_scope=scope,
                    capacity_bytes=capacity_bytes, manual_capacity_gb=manual_gb,
                    capacity_source="csi" if capacity_bytes else ("manual" if manual_gb else None))
    await seed(db, [p])
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
    await seed(db, [
        StoragePoolShare(id=ids.new("storage_pool_share"), pool_id=own.id, cluster_id="clu_b"),
    ])
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
    await seed(db, [
        GpuNode(id=ids.new("node"), cluster_id="clu_a", hostname="store", status="ready",
                   role="storage", disk=2062),
    ])
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


@pytest.mark.asyncio
async def test_deregistering_a_cluster_retires_its_pools_and_shares(db):
    """A pool of a deregistered cluster is not a place a volume can go; leaving it live kept its
    capacity in the fleet's bound and its row on the dashboard."""
    from app.api.clusters_router import deregister_cluster
    from app.auth.rbac import Principal

    await _cluster(db, "clu_gone")
    await _cluster(db, "clu_stays")
    dying = await _pool(db, cluster_id="clu_gone", name="going", capacity_bytes=2000 * GB)
    living = await _pool(db, cluster_id="clu_stays", name="staying", scope="selected",
                         capacity_bytes=500 * GB)
    async with db.begin():
        # The dying cluster was allowed onto the surviving cluster's restricted pool.
        db.add(StoragePoolShare(id=ids.new("storage_pool_share"), pool_id=living.id,
                                cluster_id="clu_gone"))
    assert (await pool_bound_gb(db))[0] == 2000
    dying_id, living_id = dying.id, living.id   # ids before the commit expires the instances

    await deregister_cluster("clu_gone", Principal(user_id="usr_su", global_roles={"super_admin"}), db)

    db.expunge_all()   # the deregistration committed; read the rows back, not the cached ones
    async with db.begin():
        retired = dict((await db.execute(
            select(StoragePool.id, StoragePool.deleted_at)
        )).all())
    assert retired[dying_id] is not None
    assert retired[living_id] is None
    # Its share of someone else's pool goes too, and the fleet bound follows.
    assert {p.id for p in await usable_pools(db, "clu_stays")} == {living_id}
    assert (await pool_bound_gb(db))[0] == 500


# ── the volume list names the pool a volume sits on ──────────────────────────────────────

@pytest.mark.asyncio
async def test_volume_list_names_the_pool_its_data_lives_on(db):
    from app.api.deps import Pagination
    from app.api.volumes_router import list_volumes
    from app.auth.rbac import Principal
    from app.db.models import StorageVolume
    await _cluster(db, "clu_p")
    pool = await _pool(db, cluster_id="clu_p", name="nas-01 (ZFS tank)", storage_class="gshare-data")
    placed = StorageVolume(id=ids.new("volume"), scope="user", scope_id="u_1", type="home", name="home",
                           access_mode="RWX", quota_gb=5, used_gb=0, cluster_id="clu_p", storage_class="gshare-data")
    fresh = StorageVolume(id=ids.new("volume"), scope="user", scope_id="u_1", type="home", name="new",
                          access_mode="RWX", quota_gb=5, used_gb=0)
    await seed(db, [placed, fresh])
    rows = await list_volumes(scope=None, scope_id=None, type=None, access_mode=None, all_scopes=True,
                              page=Pagination(1, 50), principal=Principal(user_id="root", global_roles={"super_admin"}), db=db)
    by = {r.id: r for r in rows}
    assert (by[placed.id].pool_id, by[placed.id].pool_name, by[placed.id].cluster_name) == (pool.id, "nas-01 (ZFS tank)", "clu_p")
    assert by[fresh.id].pool_name is None and by[fresh.id].cluster_id is None


# ── a pool is known by its server's hostname ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_pool_with_a_node_is_named_after_the_hostname(db):
    from app.api.storage_pools_router import PoolCreate, PoolPatch, create_pool, update_pool
    from app.auth.rbac import Principal
    from app.db.models import GpuNode
    await _cluster(db, "clu_n")
    node = GpuNode(id=ids.new("node"), cluster_id="clu_n", hostname="nas-01", status="ready")
    await seed(db, [node])
    root = Principal(user_id="root", global_roles={"super_admin"})
    made = await create_pool(PoolCreate(name="nickname", cluster_id="clu_n", storage_class="gshare-data", node_id=node.id),
                             principal=root, db=db)
    assert made["name"] == "nas-01"
    await db.commit()   # the handler's read-back leaves an autobegun transaction; close it like a request would
    # a typed name never overrides the hostname while the node is linked
    edited = await update_pool(made["id"], PoolPatch(name="other"), principal=root, db=db)
    assert edited["name"] == "nas-01"


@pytest.mark.asyncio
async def test_a_pool_without_a_node_needs_a_typed_name(db):
    from app.api.storage_pools_router import PoolCreate, create_pool
    from app.auth.rbac import Principal
    from app.core.errors import DomainError
    await _cluster(db, "clu_x")
    root = Principal(user_id="root", global_roles={"super_admin"})
    with pytest.raises(DomainError):
        await create_pool(PoolCreate(cluster_id="clu_x", storage_class="gshare-data"), principal=root, db=db)
    await db.rollback()
    made = await create_pool(PoolCreate(name="appliance-1", cluster_id="clu_x", storage_class="gshare-data"), principal=root, db=db)
    assert made["name"] == "appliance-1"


# ── the dashboard tile: fleet total on top, each pool's own allocation below ─────────────

@pytest.mark.asyncio
async def test_dashboard_storage_reports_each_pools_allocation_and_the_fleet_total(db):
    from app.api.infra_router import metrics_cluster
    from app.auth.rbac import Principal
    from app.db.models import StorageVolume
    await _cluster(db, "clu_m")
    a = await _pool(db, cluster_id="clu_m", name="nas-a", storage_class="gshare-data", manual_gb=1000)
    b = await _pool(db, cluster_id="clu_m", name="nas-b", storage_class="gshare-nfs", manual_gb=3000)
    async with db.begin():
        db.add_all([
            StorageVolume(id=ids.new("volume"), scope="user", scope_id="u", type="home", name="v1", access_mode="RWX",
                          quota_gb=100, used_gb=0, cluster_id="clu_m", storage_class="gshare-data"),
            StorageVolume(id=ids.new("volume"), scope="user", scope_id="u", type="home", name="v2", access_mode="RWX",
                          quota_gb=50, used_gb=0, cluster_id="clu_m", storage_class="gshare-data"),
            StorageVolume(id=ids.new("volume"), scope="user", scope_id="u", type="home", name="v3", access_mode="RWX",
                          quota_gb=700, used_gb=0, cluster_id="clu_m", storage_class="gshare-nfs"),
            # PVC not created yet: on no pool, but still part of the fleet's provisioned quota.
            StorageVolume(id=ids.new("volume"), scope="user", scope_id="u", type="home", name="v4", access_mode="RWX",
                          quota_gb=20, used_gb=0),
        ])
    m = await metrics_cluster(region=None, cluster_id="clu_m",
                              principal=Principal(user_id="root", global_roles={"super_admin"}), db=db)
    st = m["storage"]
    used = {p["name"]: p["used_gb"] for p in st["pools"]}
    assert used == {"nas-a": 150, "nas-b": 700}
    assert st["capacity_gb"] == 4000            # the header meter: every pool added up
    assert st["disk_gb"]["total"] == 3000       # the placement bound stays the largest pool
    assert st["disk_gb"]["used"] == 870 and st["unplaced_gb"] == 20
    assert {p["name"]: p["capacity_gb"] for p in st["pools"]} == {"nas-a": 1000, "nas-b": 3000}
    assert a.id != b.id


# ── a deregistered class can be registered again ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_class_can_be_registered_again_after_its_pool_was_removed(db):
    from app.api.storage_pools_router import (
        PoolCreate,
        PoolPatch,
        create_pool,
        delete_pool,
        update_pool,
    )
    from app.auth.rbac import Principal
    from app.core.errors import AlreadyExists
    await _cluster(db, "clu_r")
    root = Principal(user_id="root", global_roles={"super_admin"})
    first = await create_pool(PoolCreate(name="nas-02", cluster_id="clu_r", storage_class="gshare-nfs", manual_capacity_gb=2000),
                              principal=root, db=db)
    await db.commit()
    await delete_pool(first["id"], principal=root, db=db)
    await db.commit()
    # the same key again: before, the soft-deleted row still held the unique constraint → 500
    again = await create_pool(PoolCreate(name="nas-02", cluster_id="clu_r", storage_class="gshare-nfs", manual_capacity_gb=2500),
                              principal=root, db=db)
    await db.commit()
    assert again["id"] != first["id"] and again["capacity_gb"] == 2500
    live = (await db.scalars(select(StoragePool).where(StoragePool.cluster_id == "clu_r"))).all()
    assert [p.id for p in live] == [again["id"]]      # the retired row is gone, not kept beside it
    await db.commit()
    # moving another pool onto a live class is still refused, and onto a retired one succeeds
    other = await create_pool(PoolCreate(name="nas-03", cluster_id="clu_r", storage_class="gshare-data"), principal=root, db=db)
    await db.commit()
    with pytest.raises(AlreadyExists):
        await update_pool(other["id"], PoolPatch(storage_class="gshare-nfs"), principal=root, db=db)
    await db.rollback()
    await delete_pool(again["id"], principal=root, db=db)
    await db.commit()
    moved = await update_pool(other["id"], PoolPatch(storage_class="gshare-nfs"), principal=root, db=db)
    assert moved["storage_class"] == "gshare-nfs"

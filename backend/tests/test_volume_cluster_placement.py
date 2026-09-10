"""A session mounting volumes must land where those volumes' data already lives.

A volume's PVC is created lazily by whichever cluster's operator first runs a session that mounts
it, and nothing tied the volume to that cluster. A later session placed elsewhere therefore found
no PVC, had a fresh empty one created, and showed the user an empty home directory — same ledger
row, same quota, two divergent datasets, no error anywhere.
"""
from __future__ import annotations

import pytest

from app.core import ids
from app.db.models import Session as SessionModel
from app.db.models import StorageVolume, VolumeMount
from app.domain.scheduler import SchedulerService


class _Req:
    """The parts of SessionCreate the placement guard reads."""

    def __init__(self, volume_ids, cluster_id=None):
        self.volume_mounts = [type("M", (), {"volume_id": v})() for v in volume_ids]
        self.cluster_id = cluster_id


async def _volume_used_on(db, cluster_id: str) -> str:
    """A volume that has been mounted by a session on `cluster_id`."""
    vol = StorageVolume(id=ids.new("volume"), scope="user", scope_id="usr_1", type="home",
                        access_mode="RWO", quota_gb=10, used_gb=0)
    sess = SessionModel(id=ids.new("session"), owner_user_id="usr_1", cluster_id=cluster_id,
                        offering_id="off_1", image_id="img_1", resource_class="gpu",
                        mode="fractional", status="terminated")
    db.add_all([vol, sess])
    await db.flush()
    db.add(VolumeMount(id=ids.new("volume_mount"), volume_id=vol.id, session_id=sess.id,
                       mount_path="/home/coder", mode="rw"))
    await db.commit()
    return vol.id


@pytest.mark.asyncio
async def test_a_used_volume_pins_the_session_to_its_cluster(db):
    vid = await _volume_used_on(db, "clu_a")
    svc = SchedulerService(db)
    assert await svc._clusters_holding_volumes(_Req([vid])) == {"clu_a"}


@pytest.mark.asyncio
async def test_two_volumes_on_different_clusters_leave_nowhere_to_run(db):
    """The intersection is empty — no cluster holds both, so placement must refuse rather than
    silently pick one and fork the other."""
    a = await _volume_used_on(db, "clu_a")
    b = await _volume_used_on(db, "clu_b")
    svc = SchedulerService(db)
    assert await svc._clusters_holding_volumes(_Req([a, b])) == set()


@pytest.mark.asyncio
async def test_an_unused_volume_does_not_constrain_placement(db):
    """A volume nobody has mounted has no data anywhere yet; it may land on any cluster."""
    vol = StorageVolume(id=ids.new("volume"), scope="user", scope_id="usr_1", type="home",
                        access_mode="RWO", quota_gb=10, used_gb=0)
    db.add(vol)
    await db.commit()
    svc = SchedulerService(db)
    assert await svc._clusters_holding_volumes(_Req([vol.id])) is None


@pytest.mark.asyncio
async def test_a_session_without_volumes_is_unconstrained(db):
    svc = SchedulerService(db)
    assert await svc._clusters_holding_volumes(_Req([])) is None


# ── through create_session itself ────────────────────────────────────────────────────────────
# The helper above is only half the guard: create_session runs it between validators that each
# open their own transaction, and a bare query there autobegan one the next `db.begin()` tripped
# over — every session that named a cluster AND mounted a volume was a 500.

from decimal import Decimal  # noqa: E402

from app.api.schemas.session import SessionCreate, VolumeMountSpec  # noqa: E402
from app.auth.rbac import Principal  # noqa: E402
from app.core.errors import VolumeOnAnotherCluster  # noqa: E402
from app.db.models import CreditWallet, GpuNode, Image, Offering, VolumePermission  # noqa: E402


async def _cpu_fixture(db):
    user_id = ids.new("user")
    offering = Offering(id=ids.new("offering"), name="cpu", resource_class="cpu",
                        credit_per_hour=Decimal("0"), cpu=2, mem_gb=4, disk_gb=10)
    image = Image(id=ids.new("image"), name="ubuntu")
    wallet = CreditWallet(id=ids.new("wallet"), owner_type="user", owner_id=user_id,
                          balance=Decimal("0"), reserved=Decimal("0"))
    vol = StorageVolume(id=ids.new("volume"), scope="user", scope_id=user_id, type="home",
                        access_mode="RWO", quota_gb=10, used_gb=0, owner_id=user_id)
    node = GpuNode(id=ids.new("node"), cluster_id="clu_a", hostname="cpu0", status="ready",
                   role="cpu", cpu=8, mem=32, disk=200)
    async with db.begin():
        db.add_all([offering, image, wallet, vol, node])
        await db.flush()
        db.add(VolumePermission(id=ids.new("volume_permission"), volume_id=vol.id,
                                user_id=user_id, role="owner"))
    return user_id, offering, image, vol


def _pinned_req(cluster_id, offering, image, vol):
    return SessionCreate(offering_id=offering.id, image_id=image.id, resource_class="cpu",
                         cluster_id=cluster_id,
                         volume_mounts=[VolumeMountSpec(volume_id=vol.id, mount_path="/home/coder")])


@pytest.mark.asyncio
async def test_pinned_cluster_with_an_unused_volume_creates_the_session(db, fake_handoff):
    user_id, offering, image, vol = await _cpu_fixture(db)
    svc = SchedulerService(db)
    svc.handoff = fake_handoff
    out = await svc.create_session(_pinned_req("clu_a", offering, image, vol),
                                   Principal(user_id=user_id), idem="pin-1")
    assert out.cluster_id == "clu_a"


@pytest.mark.asyncio
async def test_pinned_cluster_refuses_a_volume_whose_data_is_elsewhere(db, fake_handoff):
    user_id, offering, image, vol = await _cpu_fixture(db)
    other = SessionModel(id=ids.new("session"), owner_user_id=user_id, cluster_id="clu_b",
                         offering_id=offering.id, image_id=image.id, resource_class="cpu",
                         status="terminated")
    async with db.begin():
        db.add(other)
        await db.flush()
        db.add(VolumeMount(id=ids.new("volume_mount"), volume_id=vol.id, session_id=other.id,
                           mount_path="/home/coder", mode="rw"))
    svc = SchedulerService(db)
    svc.handoff = fake_handoff
    with pytest.raises(VolumeOnAnotherCluster):
        await svc.create_session(_pinned_req("clu_a", offering, image, vol),
                                 Principal(user_id=user_id), idem="pin-2")

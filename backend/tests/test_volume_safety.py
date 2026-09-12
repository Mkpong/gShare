"""Volume safety: quotas only grow, an owner's lock stops new mounts, and the system administrator
can force-delete a volume that sessions keep mounted."""
from __future__ import annotations

import pytest

from app.api.schemas.session import SessionCreate, VolumeMountSpec
from app.api.schemas.volume import VolumeCreate, VolumePatch
from app.api.volumes_router import VolumeMounted, create_volume, delete_volume, update_volume
from app.auth.rbac import Principal
from app.core import ids
from app.core.errors import VolumeLocked, VolumeShrinkNotAllowed
from app.db.models import Session, StorageVolume, VolumeMount
from app.domain.scheduler import SchedulerService
from tests.fkseed import seed, user_row


def _super() -> Principal:
    return Principal(user_id="usr_admin", global_roles={"super_admin"})


def _member() -> Principal:
    return Principal(user_id="usr_m", memberships={"grp_x": "member"})


async def _shared(db) -> StorageVolume:
    # The principals below own rows (volume_permission.user_id, session.owner_user_id), so they
    # have to exist on the ledger.
    await seed(db, [user_row("usr_admin"), user_row("usr_m"), user_row("usr_ga")])
    body = VolumeCreate(scope="global", scope_id="global", type="dataset", name="ds",
                        access_mode="ROX", quota_gb=50)
    vol = await create_volume(body, _super(), db)
    return await db.get(StorageVolume, vol.id)


def _mount_req(volume_id: str) -> SessionCreate:
    return SessionCreate(offering_id="off_t", image_id="img_t", resource_class="cpu",
                         volume_mounts=[VolumeMountSpec(volume_id=volume_id, mount_path="/mnt/ds", mode="ro")])


@pytest.mark.asyncio
async def test_quota_only_grows(db):
    vol = await _shared(db)
    with pytest.raises(VolumeShrinkNotAllowed):
        await update_volume(vol.id, VolumePatch(quota_gb=40), _super(), db)
    grown = await update_volume(vol.id, VolumePatch(quota_gb=60), _super(), db)
    assert grown.quota_gb == 60
    same = await update_volume(vol.id, VolumePatch(quota_gb=60), _super(), db)  # no-op is fine
    assert same.quota_gb == 60


@pytest.mark.asyncio
async def test_lock_blocks_new_mounts_until_lifted(db):
    vid = (await _shared(db)).id  # the id only: a refused mount rolls back and expires the row

    async def try_mount(principal: Principal) -> None:
        await db.commit()  # _validate_mounts opens its own transaction
        await SchedulerService(db)._validate_mounts(_mount_req(vid), principal)

    await try_mount(_member())  # a shared volume is readable by everyone
    locked = await update_volume(vid, VolumePatch(mount_locked=True), _super(), db)
    assert locked.mount_locked is True
    with pytest.raises(VolumeLocked):
        await try_mount(_member())
    with pytest.raises(VolumeLocked):  # the owner too — the lock is there to drain the volume
        await try_mount(_super())
    await update_volume(vid, VolumePatch(mount_locked=False), _super(), db)
    await try_mount(_member())


@pytest.mark.asyncio
async def test_force_delete_terminates_mounting_sessions(db, monkeypatch):
    vol = await _shared(db)
    live = Session(id=ids.new("session"), owner_user_id="usr_m", cluster_id="clu_t", offering_id="off_t",
                   image_id="img_t", resource_class="cpu", mode="cpu", status="running")
    paused = Session(id=ids.new("session"), owner_user_id="usr_m", cluster_id="clu_t", offering_id="off_t",
                     image_id="img_t", resource_class="cpu", mode="cpu", status="paused")
    ended = Session(id=ids.new("session"), owner_user_id="usr_m", cluster_id="clu_t", offering_id="off_t",
                    image_id="img_t", resource_class="cpu", mode="cpu", status="terminated")
    await seed(db, [live, paused, ended])
    await seed(db, [
        VolumeMount(id=ids.new("mount"), session_id=s.id, volume_id=vol.id, mount_path="/mnt/ds",
                    mode="ro")
        for s in (live, paused, ended)
    ])

    cut: list[tuple[str, bool, str]] = []

    async def fake_terminate(self, session_id, *, forced=False, reason="user_stopped"):
        cut.append((session_id, forced, reason))

    from app.domain.session_service import SessionService
    monkeypatch.setattr(SessionService, "terminate", fake_terminate)

    with pytest.raises(VolumeMounted):
        await delete_volume(vol.id, confirm=vol.id, force=False, principal=_super(), db=db)
    # group_admin cannot force even where they may delete
    from app.core.errors import Forbidden
    with pytest.raises(Forbidden):
        await delete_volume(vol.id, confirm=vol.id, force=True,
                            principal=Principal(user_id="usr_ga", memberships={"grp_x": "group_admin"}), db=db)
    await delete_volume(vol.id, confirm=vol.id, force=True, principal=_super(), db=db)
    assert sorted(sid for sid, _, _ in cut) == sorted([live.id, paused.id])   # not the ended one
    assert all(forced and reason == "volume_force_deleted" for _, forced, reason in cut)
    await db.refresh(vol)
    assert vol.deleted_at is not None
    # the audit row names the sessions that were cut off
    from sqlalchemy import select

    from app.db.models import AuditLog
    row = (await db.scalars(select(AuditLog).where(AuditLog.action == "storage.volume.force_delete"))).first()
    assert row is not None and sorted(row.detail["terminated_sessions"]) == sorted([live.id, paused.id])

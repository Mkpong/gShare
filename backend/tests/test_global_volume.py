"""Shared (global) volumes: created by the system administrator, readable by everyone."""
from __future__ import annotations

import pytest

from app.api.deps import Pagination
from app.api.schemas.volume import VolumeCreate
from app.api.volumes_router import _implicit_group_role, create_volume, list_volumes
from app.auth.rbac import Principal
from app.core.errors import Forbidden


def _super() -> Principal:
    return Principal(user_id="usr_admin", global_roles={"super_admin"})


def _member() -> Principal:
    return Principal(user_id="usr_m", memberships={"grp_x": "member"})


def _body(**kw) -> VolumeCreate:
    base = dict(scope="global", scope_id="anything", type="dataset", name="imagenet-mini",
                access_mode="ROX", quota_gb=50)
    base.update(kw)
    return VolumeCreate(**base)


@pytest.mark.asyncio
async def test_super_admin_creates_a_shared_volume_everyone_can_read(db):
    vol = await create_volume(_body(), _super(), db)
    assert vol.scope == "global" and vol.scope_id == "global" and vol.access_mode == "ROX"
    # a plain member sees it in their own list, read-only
    rows = await list_volumes(scope=None, scope_id=None, type=None, access_mode=None, all_scopes=False,
                              page=Pagination(page=1, size=50), principal=_member(), db=db)
    mine = [r for r in rows if r.id == vol.id]
    assert mine and mine[0].role == "ro"
    assert _implicit_group_role(_member(), vol) == "ro"


@pytest.mark.asyncio
async def test_rwx_shared_volume_is_writable_by_members(db):
    vol = await create_volume(_body(access_mode="RWX", name="scratch-all"), _super(), db)
    assert _implicit_group_role(_member(), vol) == "rw"


@pytest.mark.asyncio
async def test_only_super_admin_may_create_or_delete(db):
    with pytest.raises(Forbidden):
        await create_volume(_body(), Principal(user_id="usr_ga", memberships={"grp_x": "group_admin"}), db)
    with pytest.raises(Forbidden):
        await create_volume(_body(), Principal(user_id="usr_oa", memberships={"grp_x": "org_admin"}), db)

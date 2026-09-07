"""Placement policy is a system setting, not a deploy-time constant: an administrator switches
binpack/spread from the console and the next reservation follows it."""
from __future__ import annotations

import pytest

from app.api.system_router import PlacementUpdate, get_placement, gpu_packing, set_placement
from app.auth.rbac import Principal
from app.domain.scheduler import SchedulerService


class _Dev:
    def __init__(self, uuid, used_mem, total_mem=24000, used_cores=0, total_cores=100):
        self.gpu_uuid = uuid
        self.used_mem_mb, self.total_mem_mb = used_mem, total_mem
        self.used_cores, self.total_cores = used_cores, total_cores
        self.mode = "fractional"


def test_binpack_fills_the_fullest_card_and_spread_the_emptiest():
    devs = [_Dev("full-ish", 12000), _Dev("empty", 0)]
    assert SchedulerService._pick_device(devs, 4000, 10, spread=False).gpu_uuid == "full-ish"
    assert SchedulerService._pick_device(devs, 4000, 10, spread=True).gpu_uuid == "empty"


@pytest.mark.asyncio
async def test_setting_round_trips_and_defaults(db):
    root = Principal(user_id="usr_root", global_role="super_admin", global_roles={"super_admin"})
    assert await gpu_packing(db) == "binpack"          # deployment default when unset
    out = await set_placement(PlacementUpdate(gpu_packing="spread"), root, db)
    assert out.gpu_packing == "spread"
    assert await gpu_packing(db) == "spread"
    assert (await get_placement(root, db)).gpu_packing == "spread"
    await set_placement(PlacementUpdate(gpu_packing="binpack"), root, db)
    assert await gpu_packing(db) == "binpack"


@pytest.mark.asyncio
async def test_only_a_system_administrator_may_change_it(db):
    from app.core.errors import Forbidden
    member = Principal(user_id="usr_m", memberships={"grp_x": "member"})
    with pytest.raises(Forbidden):
        await set_placement(PlacementUpdate(gpu_packing="spread"), member, db)

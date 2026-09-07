"""GPU card aliases: named by a super admin, unique per cluster, shown wherever a card is named."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.api.infra_router import _DeviceAliasBody, set_device_alias
from app.auth.rbac import Principal
from app.core import ids
from app.core.errors import DomainError, Forbidden
from app.db.models import Cluster, GpuDevice, GpuNode


def _super() -> Principal:
    return Principal(user_id="usr_admin", global_roles={"super_admin"})


async def _cards(db) -> tuple[GpuDevice, GpuDevice]:
    node = GpuNode(id=ids.new("node"), cluster_id="clu_t", hostname="gpu-a", status="ready")
    a = GpuDevice(id=ids.new("device"), cluster_id="clu_t", node_id=node.id, gpu_uuid="GPU-a", model="RTX 4090",
                  mode="fractional", status="ready", total_mem_mb=24564, used_mem_mb=0, total_cores=100, used_cores=0)
    b = GpuDevice(id=ids.new("device"), cluster_id="clu_t", node_id=node.id, gpu_uuid="GPU-b", model="RTX 4090",
                  mode="fractional", status="ready", total_mem_mb=24564, used_mem_mb=0, total_cores=100, used_cores=0)
    async with db.begin():
        db.add_all([Cluster(id="clu_t", name="t", api_server="https://k", runtime="containerd",
                            kubeconfig_secret_ref="s"), node, a, b])
    return a, b


@pytest.mark.asyncio
async def test_set_clear_and_uniqueness(db):
    a, b = await _cards(db)
    out = await set_device_alias(a.id, _DeviceAliasBody(alias="  lab-A-01 "), _super(), db)
    assert out["alias"] == "lab-A-01"
    with pytest.raises(DomainError) as exc:
        await set_device_alias(b.id, _DeviceAliasBody(alias="lab-A-01"), _super(), db)
    assert exc.value.code == "alias_taken"
    # the same card may keep its own alias
    assert (await set_device_alias(a.id, _DeviceAliasBody(alias="lab-A-01"), _super(), db))["alias"] == "lab-A-01"
    assert (await set_device_alias(a.id, _DeviceAliasBody(alias=None), _super(), db))["alias"] is None
    assert (await set_device_alias(b.id, _DeviceAliasBody(alias="lab-A-01"), _super(), db))["alias"] == "lab-A-01"


@pytest.mark.asyncio
async def test_length_limit_and_permission(db):
    a, _ = await _cards(db)
    with pytest.raises(ValidationError):
        _DeviceAliasBody(alias="x" * 33)
    with pytest.raises(Forbidden):
        await set_device_alias(a.id, _DeviceAliasBody(alias="nope"), Principal(user_id="usr_x", memberships={}), db)

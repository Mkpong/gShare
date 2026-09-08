"""The dashboard reports the caller's volumes and the ceiling on them.

`compute.disk_gb` is the sessions' scratch disk; volumes are a separate allowance, and leaving
them off the dashboard made a full storage quota invisible until provisioning failed."""
from __future__ import annotations

import pytest

from app.api.dashboard_router import dashboard_summary
from app.auth.rbac import Principal
from app.core import ids
from app.db.models import ResourcePolicy, StorageVolume

OWNER = "usr_stor01"
P = Principal(user_id=OWNER, global_role="member", global_roles={"member"})


@pytest.mark.asyncio
async def test_storage_counts_only_the_callers_live_volumes(db):
    db.add_all([
        StorageVolume(id=ids.new("volume"), scope="user", scope_id=OWNER, type="home",
                      access_mode="RWO", owner_id=OWNER, quota_gb=50, used_gb=12),
        StorageVolume(id=ids.new("volume"), scope="user", scope_id=OWNER, type="dataset",
                      name="d", access_mode="RWX", owner_id=OWNER, quota_gb=30, used_gb=3),
        # somebody else's volume, and a deleted one of the caller's: neither counts
        StorageVolume(id=ids.new("volume"), scope="user", scope_id="usr_other", type="home",
                      access_mode="RWO", quota_gb=999, used_gb=999),
    ])
    gone = StorageVolume(id=ids.new("volume"), scope="user", scope_id=OWNER, type="scratch",
                         access_mode="RWO", quota_gb=100, used_gb=100)
    db.add(gone)
    await db.commit()
    from datetime import UTC, datetime
    gone.deleted_at = datetime.now(UTC)
    db.add(ResourcePolicy(id=ids.new("policy"), scope="global", scope_id="*",
                          limits={"volume_gb": 200}))
    await db.commit()

    out = await dashboard_summary(scope="mine", principal=P, db=db)
    assert out["storage"] == {
        "volumes": 2, "provisioned_gb": 80, "used_gb": 15, "limit_gb": 200,
    }

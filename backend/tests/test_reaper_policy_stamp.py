"""CPU sessions must resolve reaper windows from limits.cpu_session_*, never the GPU fields.

Regression: the idle/max resolvers ignored resource_class, so a user-scope GPU max_runtime of
60 minutes was stamped onto the same user's CPU session, which the reaper then terminated.
"""
from __future__ import annotations

import pytest

from app.cluster.crd import GShareSessionCRD
from app.core import ids
from app.db.models import ResourcePolicy


@pytest.mark.asyncio
async def test_cpu_sessions_use_cpu_session_windows(db):
    user_id = ids.new("user")
    async with db.begin():
        db.add(ResourcePolicy(
            id=ids.new("policy"), scope="user", scope_id=user_id,
            max_concurrent=2, max_queued=2, max_runtime=60, idle_timeout=3600,
            limits={"cpu_session_idle_timeout_sec": 0, "cpu_session_max_runtime_min": 0},
        ))
    crd = GShareSessionCRD(db=db)

    gpu_spec = {"owner": user_id, "group_id": None, "resource_class": "gpu"}
    assert await crd._resolve_idle_timeout_sec(gpu_spec) == 3600
    assert await crd._resolve_max_runtime_sec(gpu_spec) == 3600

    cpu_spec = {"owner": user_id, "group_id": None, "resource_class": "cpu"}
    # Explicit 0 = unlimited for idle; 0 max-runtime means "no cap annotation".
    assert await crd._resolve_idle_timeout_sec(cpu_spec) == 0
    assert await crd._resolve_max_runtime_sec(cpu_spec) is None

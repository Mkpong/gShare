"""A resume re-stamps the reaper windows for the session's OWN class and marks the run start."""
from __future__ import annotations

from contextlib import asynccontextmanager

import pytest

from app.cluster.crd import GShareSessionCRD
from app.db.models import Cluster


class _FakeApi:
    def __init__(self):
        self.bodies: list[list[dict]] = []

    async def patch_namespaced_custom_object(self, **kw):
        self.bodies.append(kw["body"])


@pytest.mark.asyncio
async def test_resume_patch_is_class_aware_and_stamps_run_start(db, monkeypatch):
    async with db.begin():
        db.add(Cluster(id="clu_t", name="t", api_server="https://t:6443", runtime="k8s", kubeconfig_secret_ref="sec"))
    api = _FakeApi()

    @asynccontextmanager
    async def _factory(_cluster):
        yield api

    async def _fake_factory(cluster):
        return _factory(cluster)

    crd = GShareSessionCRD(db, client_factory=_fake_factory)
    seen: list[dict] = []

    async def _max(spec_like):
        seen.append(dict(spec_like))
        return 0

    async def _idle(spec_like):
        return 0

    monkeypatch.setattr(crd, "_resolve_max_runtime_sec", _max)
    monkeypatch.setattr(crd, "_resolve_idle_timeout_sec", _idle)

    await crd.set_paused("clu_t", "ses_t", False, owner="usr_t", group_id="grp_t", resource_class="cpu")

    assert seen and seen[0]["resource_class"] == "cpu"
    paths = [op["path"] for op in api.bodies[0]]
    assert "/metadata/annotations/gshare.io~1run-started-at" in paths
    assert {"op": "add", "path": "/spec/paused", "value": False} in api.bodies[0]

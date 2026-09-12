"""An operator token speaks only for its own cluster.

Every attached cluster holds a token signed by the same control-plane key. Before this, the
callbacks checked the audience and nothing else, so the operator of one cluster could report a
session on another cluster as terminated (settling its hold), rewrite a neighbour's node and card
inventory, or feed the live-usage view of sessions it never ran.
"""
from __future__ import annotations

import pytest

from app.api.schemas.internal import (
    OperatorGpuDeviceUpsert,
    OperatorNodeUpsert,
    OperatorStatusEvent,
)
from app.auth.internal_jwt import operator_cluster, require_operator_cluster
from app.core import ids
from app.core.errors import Forbidden
from app.db.models import Session as SessionModel
from app.internal import inventory_router, status_router
from tests.fkseed import seed


def test_subject_parsing():
    assert operator_cluster({"sub": "operator:clu_a"}) == "clu_a"
    assert operator_cluster({"sub": "image-builder"}) is None
    assert operator_cluster({}) is None


def test_mismatch_is_forbidden_and_unscoped_tokens_pass():
    require_operator_cluster({"sub": "operator:clu_a"}, "clu_a", what="session")
    require_operator_cluster({"sub": "image-builder"}, "clu_a", what="session")
    require_operator_cluster({"sub": "operator:clu_a"}, None, what="session")
    with pytest.raises(Forbidden):
        require_operator_cluster({"sub": "operator:clu_b"}, "clu_a", what="session")


async def _session_on(db, cluster_id: str) -> str:
    sess = SessionModel(id=ids.new("session"), owner_user_id="usr_1", cluster_id=cluster_id,
                        offering_id="off_1", image_id="img_1", resource_class="gpu",
                        mode="fractional", status="running")
    await seed(db, [sess])
    return sess.id


@pytest.mark.parametrize("as_cr_name", [False, True])
@pytest.mark.asyncio
async def test_status_callback_from_another_cluster_is_refused(db, monkeypatch, as_cr_name):
    """Both addressing forms are covered: the operator posts the CR name (lower-cased, `_`→`-`),
    so a guard that only matched the raw id would wave every real callback through."""
    seen = []

    async def fake_on_status(self, session_id, ev):
        seen.append((session_id, ev.phase))

    monkeypatch.setattr(status_router.StatusSync, "on_status", fake_on_status)
    sid = await _session_on(db, "clu_a")
    addressed = sid.lower().replace("_", "-") if as_cr_name else sid
    ev = OperatorStatusEvent(phase="terminated", ts="2026-09-09T00:00:00Z")
    with pytest.raises(Forbidden):
        await status_router.report_status(addressed, ev, {"sub": "operator:clu_b"}, db)
    assert seen == []
    await status_router.report_status(addressed, ev, {"sub": "operator:clu_a"}, db)
    assert seen == [(addressed, "terminated")]


@pytest.mark.asyncio
async def test_inventory_report_for_another_cluster_is_refused(db, monkeypatch):
    got = []

    async def fake_upsert_node(self, ev, cluster_id):
        got.append(("node", cluster_id))

    async def fake_upsert_device(self, ev, cluster_id):
        got.append(("device", cluster_id))

    monkeypatch.setattr(inventory_router.InventorySync, "upsert_node", fake_upsert_node)
    monkeypatch.setattr(inventory_router.InventorySync, "upsert_device", fake_upsert_device)
    with pytest.raises(Forbidden):
        await inventory_router.upsert_node(
            OperatorNodeUpsert(node_id="n1", cluster_id="clu_a"), {"sub": "operator:clu_b"}, db)
    with pytest.raises(Forbidden):
        await inventory_router.upsert_gpu_device(
            OperatorGpuDeviceUpsert(uuid="GPU-1", node_id="n1", model="RTX", total_mem_mb=1, cluster_id="clu_a"),
            {"sub": "operator:clu_b"}, db)
    # The token is authoritative: a payload without a cluster lands on the token's cluster.
    await inventory_router.upsert_node(OperatorNodeUpsert(node_id="n1"), {"sub": "operator:clu_b"}, db)
    assert got == [("node", "clu_b")]


@pytest.mark.asyncio
async def test_the_guard_does_not_hold_a_transaction_open(db):
    """The real StatusSync runs after the guard. Resolving the cluster with a bare query left an
    autobegun transaction that StatusSync's own `begin()` then refused — every callback 500'd and
    sessions sat at `pending` while their pods were already running."""
    sess = SessionModel(id=ids.new("session"), owner_user_id="usr_1", cluster_id="clu_a",
                        offering_id="off_1", image_id="img_1", resource_class="gpu",
                        mode="fractional", status="pending")
    await seed(db, [sess])
    ev = OperatorStatusEvent(phase="preparing", ts="2026-09-09T00:00:00Z")
    await status_router.report_status(sess.id.lower().replace("_", "-"), ev,
                                      {"sub": "operator:clu_a"}, db)
    async with db.begin():
        assert (await db.get(SessionModel, sess.id)).status == "preparing"

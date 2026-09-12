"""Beta: every internal operator callback is bound to the token's cluster, and the node health
contract matches what the operator actually sends (a hostname, not a ledger id)."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.api.schemas.internal import (
    OperatorAuditEvent,
    OperatorNodeHealthEvent,
    OperatorVolumeSync,
)
from app.core import ids
from app.core.errors import Forbidden
from app.db.models import Cluster, GpuNode, ImageBuild, NodeHealthEvent
from app.internal import audit_router, imagebuild_status_router, inventory_router, volumes_router
from tests.fkseed import seed, user_row

pytestmark = pytest.mark.asyncio


async def _node(db, cluster_id: str, hostname: str) -> GpuNode:
    node = GpuNode(id=ids.new("node"), cluster_id=cluster_id, hostname=hostname, status="ready")
    await seed(db, [
        Cluster(id=cluster_id, name=cluster_id, api_server="https://x", runtime="containerd",
                kubeconfig_secret_ref="kc"),
        node,
    ])
    return node


def _health(node_id: str, **kw) -> OperatorNodeHealthEvent:
    base = dict(node_id=node_id, kind="xid", severity="critical", action="cordon")
    base.update(kw)
    return OperatorNodeHealthEvent(**base)


# ── node health: the operator reports the Kubernetes node NAME ──


async def test_health_event_addressed_by_hostname_cordons_the_ledger_node(db):
    """The operator's HealthReconciler sends NodeID = node.Name (the hostname). The ledger row is
    keyed by its own id, so the callback has to resolve (token cluster, hostname); looking the
    hostname up as an id never matched, the cordon never reached the ledger, and the FK on the
    event row failed on Postgres."""
    node = await _node(db, "clu_a", "gpu-a")
    await inventory_router.node_health_event(_health("gpu-a"), {"sub": "operator:clu_a"}, db)
    db.expunge_all()
    row = await db.get(GpuNode, node.id)
    assert row.status == "cordoned"
    ev = (await db.scalars(select(NodeHealthEvent))).all()
    assert len(ev) == 1 and ev[0].node_id == node.id     # FK-valid ledger id, not the hostname


async def test_health_event_from_another_clusters_operator_is_refused(db):
    node = await _node(db, "clu_b", "gpu-b")
    with pytest.raises(Forbidden):
        await inventory_router.node_health_event(
            _health("gpu-b", cluster_id="clu_b"), {"sub": "operator:clu_a"}, db)
    await db.rollback()
    db.expunge_all()
    assert (await db.get(GpuNode, node.id)).status == "ready"
    assert (await db.scalars(select(NodeHealthEvent))).all() == []


async def test_health_event_cannot_cordon_a_same_named_node_on_another_cluster(db):
    """Two clusters may both have a node called gpu-a; the token decides which one is meant."""
    mine = await _node(db, "clu_a", "gpu-a")
    other = GpuNode(id=ids.new("node"), cluster_id="clu_b", hostname="gpu-a", status="ready")
    await seed(db, [
        Cluster(id="clu_b", name="b", api_server="https://y", runtime="containerd",
                kubeconfig_secret_ref="kc"),
        other,
    ])
    await inventory_router.node_health_event(_health("gpu-a"), {"sub": "operator:clu_a"}, db)
    db.expunge_all()
    assert (await db.get(GpuNode, mine.id)).status == "cordoned"
    assert (await db.get(GpuNode, other.id)).status == "ready"


async def test_health_event_for_an_unknown_node_is_accepted_without_a_dangling_row(db):
    await _node(db, "clu_a", "gpu-a")
    out = await inventory_router.node_health_event(_health("ghost"), {"sub": "operator:clu_a"}, db)
    assert out == {"accepted": True}
    db.expunge_all()
    assert (await db.scalars(select(NodeHealthEvent))).all() == []


# ── audit: the actor is the token, not the payload ──


async def test_audit_actor_cannot_name_another_cluster(db):
    ev = OperatorAuditEvent(actor="operator:clu_b", action="node.cordon", target="gpu-b",
                            result="ok", ts=datetime.now(UTC))
    with pytest.raises(Forbidden):
        await audit_router.audit_operator(ev, {"sub": "operator:clu_a"}, db)


# ── volumes: the report's cluster must be the token's ──


async def test_volume_sync_from_another_cluster_is_refused(db, monkeypatch):
    seen: list[str | None] = []

    async def _sync(self, report):
        seen.append(report.cluster_id)
        from app.api.schemas.internal import VolumeSyncResponse
        return VolumeSyncResponse(volumes=[], orphans=0)

    monkeypatch.setattr(volumes_router.VolumeSync, "sync", _sync)
    with pytest.raises(Forbidden):
        await volumes_router.sync_volumes(OperatorVolumeSync(volumes=[], cluster_id="clu_b"),
                                          {"sub": "operator:clu_a"}, db)
    assert seen == []
    # A report without a cluster (older operator) lands on the token's cluster.
    await volumes_router.sync_volumes(OperatorVolumeSync(volumes=[]), {"sub": "operator:clu_a"}, db)
    assert seen == ["clu_a"]


# ── image builds: the build's cluster must be the token's ──


async def test_image_build_status_from_another_cluster_is_refused(db):
    build = ImageBuild(id=ids.new("build"), group_id="grp_1", owner_user_id="usr_1", name="b",
                       source="dockerfile", status="running", cluster_id="clu_b")
    # The handler notifies the build's owner, and notification.user_id is a real foreign key.
    await seed(db, [user_row("usr_1"), build])
    bid = build.id
    ev = imagebuild_status_router.BuildStatusEvent(phase="succeeded", image_ref="evil/registry:1")
    with pytest.raises(Forbidden):
        await imagebuild_status_router.report_build_status(bid, ev, {"sub": "operator:clu_a"}, db)
    await db.rollback()
    db.expunge_all()
    row = await db.get(ImageBuild, bid)
    assert row.status == "running" and row.image_id is None
    await db.commit()
    out = await imagebuild_status_router.report_build_status(bid, ev, {"sub": "operator:clu_b"}, db)
    assert out["status"] == "succeeded"

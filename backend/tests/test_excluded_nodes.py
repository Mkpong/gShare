"""Drain safety: a resumed or newly placed pod must avoid the nodes the ledger holds as unusable."""
from __future__ import annotations

import pytest

from app.cluster.crd import GShareSessionCRD, _to_crd_spec
from app.cluster.handoff import Handoff
from app.core import ids
from app.db.models import GpuNode, Session


def _cpu_session() -> Session:
    return Session(
        id=ids.new("session"), owner_user_id="usr_t", cluster_id="clu_t", offering_id="off_t",
        image_id="img_t", resource_class="cpu", mode="fractional", status="paused", cpu=2, mem_gb=4,
    )


def test_spec_carries_the_exclusion_in_camel_case():
    sess = _cpu_session()
    sess._excluded_nodes = ["cpu01", "gpu-dead"]
    spec = GShareSessionCRD().to_session_spec(sess, None, image_ref="img:1")
    assert spec["excluded_nodes"] == ["cpu01", "gpu-dead"]
    assert _to_crd_spec(spec)["excludedNodes"] == ["cpu01", "gpu-dead"]
    assert "excluded_nodes" not in GShareSessionCRD().to_session_spec(_cpu_session(), None, image_ref="img:1")


@pytest.mark.asyncio
async def test_excluded_nodes_are_the_cordoned_and_offline_ones_of_that_cluster(db):
    async with db.begin():
        db.add_all([
            GpuNode(id=ids.new("node"), cluster_id="clu_t", hostname="ok", status="ready"),
            GpuNode(id=ids.new("node"), cluster_id="clu_t", hostname="draining", status="cordoned"),
            GpuNode(id=ids.new("node"), cluster_id="clu_t", hostname="dead", status="offline"),
            GpuNode(id=ids.new("node"), cluster_id="clu_other", hostname="elsewhere", status="cordoned"),
        ])
    assert await Handoff(db).excluded_nodes(_cpu_session()) == ["dead", "draining"]

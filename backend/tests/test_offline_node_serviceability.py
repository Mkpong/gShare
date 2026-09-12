"""A decommissioned node's leftover cards must not make a request look serviceable.

gpu3 was wiped and removed from the console, but its Kubernetes Node object stayed, so the
operator kept re-registering the node (offline) and its two cards (ready). Serviceability
counted those cards, so a request for that GPU model was queued forever instead of being
rejected with a reason.
"""
from __future__ import annotations

import pytest

from app.api.schemas.session import SessionCreate
from app.core import ids
from app.db.models import GpuDevice, GpuNode, Offering, Session
from app.domain.scheduler import SchedulerService, Unserviceable
from tests.fkseed import seed


def _device(node_id: str, model: str) -> GpuDevice:
    return GpuDevice(
        id=ids.new("device"), cluster_id="clu_t", node_id=node_id, gpu_uuid=ids.new("device"),
        model=model, mode="fractional", status="ready", total_mem_mb=49152, used_mem_mb=0,
        total_cores=100, used_cores=0,
    )


async def _fixture(db, node_status: str) -> tuple[Session, SessionCreate]:
    node = GpuNode(id=ids.new("node"), cluster_id="clu_t", hostname="gpu3", status=node_status)
    offering = Offering(id=ids.new("offering"), name="PRO 5000", resource_class="gpu",
                        gpu_model="NVIDIA RTX PRO 5000 Blackwell", gpu_mem_mb=49152)
    await seed(db, [node, offering, _device(node.id, offering.gpu_model)])
    sess = Session(
        id=ids.new("session"), owner_user_id="usr_t", cluster_id="clu_t", offering_id=offering.id,
        image_id="img_t", resource_class="gpu", mode="fractional", status="pending",
        gpu_mem_mb=8192, gpu_cores=25,
    )
    req = SessionCreate(offering_id=offering.id, image_id="img_t", resource_class="gpu",
                        mode="fractional", cluster_id="clu_t", gpu_mem_mb=8192, gpu_cores=25)
    return sess, req


@pytest.mark.asyncio
async def test_cards_on_an_offline_node_do_not_make_a_request_serviceable(db):
    sess, req = await _fixture(db, "offline")
    with pytest.raises(Unserviceable):
        await SchedulerService(db)._assert_serviceable(sess, req)


@pytest.mark.asyncio
async def test_cards_on_a_cordoned_node_do_not_make_a_request_serviceable(db):
    sess, req = await _fixture(db, "cordoned")
    with pytest.raises(Unserviceable):
        await SchedulerService(db)._assert_serviceable(sess, req)


@pytest.mark.asyncio
async def test_a_ready_node_still_serves(db):
    sess, req = await _fixture(db, "ready")
    await SchedulerService(db)._assert_serviceable(sess, req)   # no raise

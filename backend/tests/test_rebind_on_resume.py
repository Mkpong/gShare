"""A session that comes back on a different card must say so: the bound card and the pod name
follow the pod, because the read model resolves the node FROM the bound card."""
from __future__ import annotations

import pytest

from app.cluster.status_sync import StatusSync
from app.core import ids
from app.db.models import Session
from tests.fkseed import seed


def _event(**kw):
    from datetime import UTC, datetime

    from app.api.schemas.internal import OperatorStatusEvent
    return OperatorStatusEvent(phase="Running", ts=datetime.now(UTC), **kw)


@pytest.mark.asyncio
async def test_resumed_session_rebinds_to_the_card_it_actually_runs_on(db, monkeypatch):
    sess = Session(id=ids.new("session"), owner_user_id="usr_x", cluster_id="clu_local",
                   offering_id="off_t", image_id="img_t", resource_class="gpu", mode="fractional",
                   status="preparing", gpu_mem_mb=12288, gpu_cores=50,
                   bound_gpu_uuid="GPU-old", node_hostname="retired-node", pod_ref="ses-old")
    await seed(db, [sess])

    sync = StatusSync(db)
    # the ledger side is exercised elsewhere; here the question is only what the row records
    async def noop(*a, **k):
        return False
    monkeypatch.setattr(StatusSync, "_ensure_allocation", noop)
    monkeypatch.setattr(StatusSync, "_bump_device_usage", noop)

    await sync._on_running(sess, _event(session_id=sess.id, node_name="live-node",
                                        bound_gpu_uuid="GPU-new", pod_ref="ses-new"))
    assert sess.bound_gpu_uuid == "GPU-new"   # not the card it ran on last time
    assert sess.node_hostname == "live-node"
    assert sess.pod_ref == "ses-new"
    assert sess.status == "running"

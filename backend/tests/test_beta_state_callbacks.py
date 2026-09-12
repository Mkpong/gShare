"""Beta: abnormal operator callbacks through the status path.

Duplicate, out-of-order, late and cross-cluster reports must never move money or GPU capacity a
second time, and must never bring a finished session back. Everything here drives StatusSync (and
the status router for the token guard) exactly as the operator would.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.api.schemas.internal import OperatorStatusEvent
from app.cluster.status_sync import StatusSync
from app.core import ids
from app.core.errors import Forbidden
from app.db.models import (
    Allocation,
    CreditTransaction,
    CreditWallet,
    GpuDevice,
    GpuNode,
    Notification,
    Session,
    SessionEvent,
)
from app.internal import status_router
from tests.fkseed import seed

pytestmark = pytest.mark.asyncio

CLUSTER = "clu_a"
GPU = "GPU-aaaa-0001"


async def _seed(db, *, status: str = "preparing", wallet: bool = False, **kw):
    """One ready card and one fractional session on it (1000 MB / 10 cores)."""
    node = GpuNode(id=ids.new("node"), cluster_id=CLUSTER, hostname="gpu-a", status="ready")
    dev = GpuDevice(id=ids.new("device"), node_id=node.id, cluster_id=CLUSTER, model="X",
                    gpu_uuid=GPU, total_mem_mb=16000, total_cores=100)
    fields = dict(
        id=ids.new("session"), owner_user_id=ids.new("user"), cluster_id=CLUSTER,
        offering_id="off_t", image_id="img_t", resource_class="gpu", mode="fractional",
        status=status, gpu_mem_mb=1000, gpu_cores=10, device_total_mem_mb=16000,
        credit_per_hour_snapshot=Decimal("0"),
    )
    objs = [node, dev]
    if wallet:
        w = CreditWallet(id=ids.new("wallet"), owner_type="user", owner_id=fields["owner_user_id"],
                         balance=Decimal("100"), reserved=Decimal("0"))
        objs.append(w)
        fields["billing_wallet_id"] = w.id
        fields["credit_per_hour_snapshot"] = Decimal("6")
    fields.update(kw)
    sess = Session(**fields)
    objs.append(sess)
    await seed(db, objs)
    return sess, dev


def _ev(phase: str, **kw) -> OperatorStatusEvent:
    base = dict(phase=phase, ts=datetime.now(UTC), bound_gpu_uuid=GPU, node_name="gpu-a",
                pod_ref="gshare-sessions/ses-x")
    base.update(kw)
    return OperatorStatusEvent(**base)


async def _live_allocs(db, sid: str) -> int:
    return await db.scalar(
        select(func.count(Allocation.id)).where(Allocation.session_id == sid, Allocation.ended_at.is_(None))
    )


async def _events(db, sid: str, kind: str) -> int:
    return await db.scalar(
        select(func.count(SessionEvent.id)).where(SessionEvent.session_id == sid, SessionEvent.kind == kind)
    )


async def _notifs(db, uid: str, typ: str) -> int:
    return await db.scalar(
        select(func.count(Notification.id)).where(Notification.user_id == uid, Notification.type == typ)
    )


async def _settles(db, sid: str) -> int:
    return await db.scalar(
        select(func.count(CreditTransaction.id)).where(CreditTransaction.idempotency_key == f"settle:{sid}")
    )


# ── duplicates ──


async def test_duplicate_running_binds_the_card_once(db):
    sess, dev = await _seed(db)
    sync = StatusSync(db)
    await sync.on_status(sess.id, _ev("running"))
    await sync.on_status(sess.id, _ev("running"))
    db.expunge_all()
    row = await db.get(Session, sess.id)
    card = await db.get(GpuDevice, dev.id)
    assert row.status == "running" and row.bound_gpu_uuid == GPU and row.node_hostname == "gpu-a"
    assert await _live_allocs(db, sess.id) == 1
    assert (card.used_mem_mb, card.used_cores) == (1000, 10)
    assert await _events(db, sess.id, "running") == 1
    assert await _notifs(db, row.owner_user_id, "session_running") == 1


async def test_duplicate_terminated_settles_once(db):
    sess, dev = await _seed(db, wallet=True)
    sync = StatusSync(db)
    await sync.on_status(sess.id, _ev("running"))
    await sync.on_status(sess.id, _ev("terminated", ts=datetime.now(UTC) + timedelta(minutes=2)))
    await sync.on_status(sess.id, _ev("terminated", ts=datetime.now(UTC) + timedelta(minutes=3)))
    db.expunge_all()
    row = await db.get(Session, sess.id)
    card = await db.get(GpuDevice, dev.id)
    wallet = await db.get(CreditWallet, row.billing_wallet_id)
    assert row.status == "terminated"
    assert await _live_allocs(db, sess.id) == 0
    assert (card.used_mem_mb, card.used_cores) == (0, 0)
    assert await _settles(db, sess.id) == 1
    assert wallet.reserved == Decimal("0.00")
    assert await _events(db, sess.id, "terminated") == 1
    assert await _notifs(db, row.owner_user_id, "session_terminated") == 1


async def test_error_after_terminated_is_a_no_op(db):
    sess, _dev = await _seed(db, wallet=True)
    sync = StatusSync(db)
    await sync.on_status(sess.id, _ev("running"))
    await sync.on_status(sess.id, _ev("terminated"))
    db.expunge_all()
    ended = (await db.get(Session, sess.id)).terminated_at
    await db.commit()
    await sync.on_status(sess.id, _ev("error", message="Evicted: node lost"))
    db.expunge_all()
    row = await db.get(Session, sess.id)
    assert row.status == "terminated" and row.terminated_at == ended
    assert row.status_reason is None            # a repeat cannot rewrite a settled row's cause
    assert await _settles(db, sess.id) == 1
    assert await _events(db, sess.id, "error") == 0
    assert await _notifs(db, row.owner_user_id, "session_error") == 0


# ── late / out-of-order ──


@pytest.mark.parametrize("finished", ["terminated", "error", "terminating"])
async def test_late_running_report_never_rebinds_a_finished_session(db, finished):
    """A `running` that lands after the session ended (a retried callback, an operator restart
    observing a pod the finalizer has not yet removed) must not reserve the card again: the
    session will never release it, so the capacity is gone until someone edits the ledger."""
    sess, dev = await _seed(db, status=finished, terminated_at=datetime.now(UTC))
    await StatusSync(db).on_status(sess.id, _ev("running"))
    db.expunge_all()
    row = await db.get(Session, sess.id)
    card = await db.get(GpuDevice, dev.id)
    assert row.status == finished
    assert await _live_allocs(db, sess.id) == 0
    assert (card.used_mem_mb, card.used_cores) == (0, 0)
    assert await _events(db, sess.id, "running") == 0


@pytest.mark.parametrize("phase", ["terminated", "error"])
async def test_terminal_report_from_an_older_generation_after_a_resume_is_ignored(db, phase):
    """The operator reconciled the stop's generation after the resume committed: its report is
    newer than the run start, so only the generation tells it apart."""
    from app.core.redis import get_redis

    sess, dev = await _seed(db, status="running", started_at=datetime.now(UTC) - timedelta(seconds=5))
    async with db.begin():
        db.add(Allocation(id=ids.new("allocation"), session_id=sess.id, device_id=dev.id,
                          gpu_uuid=GPU, gpu_mem_mb=1000, gpu_cores=10, status="bound"))
        dev.used_mem_mb, dev.used_cores = 1000, 10
    await get_redis().set(f"resume-gen:{sess.id}", "9")
    await StatusSync(db).on_status(sess.id, _ev(phase, generation=8, message="max-runtime-exceeded"))
    db.expunge_all()
    row = await db.get(Session, sess.id)
    card = await db.get(GpuDevice, dev.id)
    assert row.status == "running" and row.status_reason is None
    assert await _live_allocs(db, sess.id) == 1
    assert (card.used_mem_mb, card.used_cores) == (1000, 10)


async def test_paused_with_a_reason_from_an_older_generation_is_still_ignored(db):
    from app.core.redis import get_redis

    sess, _dev = await _seed(db, status="running", started_at=datetime.now(UTC) - timedelta(minutes=30))
    await get_redis().set(f"resume-gen:{sess.id}", "9")
    await StatusSync(db).on_status(sess.id, _ev("paused", generation=8, message="idle-reaped"))
    db.expunge_all()
    assert (await db.get(Session, sess.id)).status == "running"


async def test_preparing_for_a_running_session_keeps_it_running(db):
    """A pod being replaced (DeletionTimestamp set) is reported Preparing, not terminal."""
    sess, _dev = await _seed(db, status="running", started_at=datetime.now(UTC))
    await StatusSync(db).on_status(sess.id, _ev("preparing", pod_ref="gshare-sessions/ses-y"))
    db.expunge_all()
    row = await db.get(Session, sess.id)
    assert row.status == "running" and row.pod_ref == "gshare-sessions/ses-y"


async def test_heartbeat_never_resurrects_a_finished_session(db):
    sess, _dev = await _seed(db, status="terminated", terminated_at=datetime.now(UTC))
    await StatusSync(db).on_status(sess.id, _ev("heartbeat", restart_count=0, container_state="Running"))
    db.expunge_all()
    row = await db.get(Session, sess.id)
    assert row.status == "terminated" and await _live_allocs(db, sess.id) == 0


async def test_terminated_from_paused_skips_the_final_consume(db, monkeypatch):
    """A paused session was trued up at stop(); a final consume from started_at would bill the
    whole paused gap."""
    sess, _dev = await _seed(db, status="paused", wallet=True,
                             started_at=datetime.now(UTC) - timedelta(hours=3))
    sync = StatusSync(db)
    seen: list[bool] = []

    async def _settle(session, key, *, final_consume=True):
        seen.append(final_consume)

    monkeypatch.setattr(sync.credit, "settle", _settle)
    await sync.on_status(sess.id, _ev("terminated"))
    assert seen == [False]
    db.expunge_all()
    assert (await db.get(Session, sess.id)).status == "terminated"


async def test_terminated_for_a_queued_session_refunds_the_hold(db):
    """A pending (queued) session has a hold and no card; the operator has nothing to tear down,
    but a CR could still be deleted by hand. The hold must come back."""
    from app.domain.credit_engine import CreditEngine

    sess, _dev = await _seed(db, status="pending", wallet=True)
    await CreditEngine(db).hold(sess.billing_wallet_id, Decimal("10"), key=f"hold:{sess.id}")
    await db.commit()
    await StatusSync(db).on_status(sess.id, _ev("terminated", bound_gpu_uuid=None, node_name=None))
    db.expunge_all()
    row = await db.get(Session, sess.id)
    wallet = await db.get(CreditWallet, row.billing_wallet_id)
    assert row.status == "terminated"
    assert wallet.reserved == Decimal("0.00") and wallet.balance == Decimal("100.00")


# ── addressing and the cluster guard ──


async def test_callback_for_an_unknown_session_is_accepted_and_changes_nothing(db):
    before = await db.scalar(select(func.count(Session.id)))
    await db.commit()   # the router's guard opens its own transaction
    out = await status_router.report_status(
        "ses-01doesnotexist", _ev("running"), {"sub": "operator:clu_zzz"}, db)
    assert out == {"accepted": True}
    assert await db.scalar(select(func.count(Session.id))) == before
    assert await db.scalar(select(func.count(Allocation.id))) == 0


@pytest.mark.parametrize("phase", ["running", "heartbeat", "paused", "error"])
async def test_every_phase_is_refused_from_another_clusters_token(db, phase):
    sess, dev = await _seed(db, status="running", started_at=datetime.now(UTC) - timedelta(minutes=5))
    cr_name = sess.id.lower().replace("_", "-")
    with pytest.raises(Forbidden):
        await status_router.report_status(cr_name, _ev(phase, restart_count=1, message="idle-reaped"),
                                          {"sub": "operator:clu_b"}, db)
    db.expunge_all()
    row = await db.get(Session, sess.id)
    assert row.status == "running" and row.last_reported_at is None
    assert await _live_allocs(db, sess.id) == 0


async def test_unscoped_token_still_passes_the_guard(db):
    """A token without an operator: subject (image builder, older deployments) is not cluster
    scoped and is let through — documented, so it stays a conscious choice."""
    sess, _dev = await _seed(db, status="pending")
    await status_router.report_status(sess.id, _ev("preparing"), {"sub": "image-builder"}, db)
    db.expunge_all()
    assert (await db.get(Session, sess.id)).status == "preparing"


# ── GS-C09: the stale test must not hang on two different wall clocks ──


async def test_a_current_generation_pause_survives_an_operator_clock_that_lags(db):
    """The operator's node clock is 2 minutes behind the API's. Its Paused report describes the
    generation the resume produced, so it is about THIS run and must be applied — comparing the
    two clocks made the control plane drop it as an echo and leave the pod's card reserved."""
    from app.core.redis import get_redis

    sess, dev = await _seed(db, status="running", started_at=datetime.now(UTC))
    async with db.begin():
        db.add(Allocation(id=ids.new("allocation"), session_id=sess.id, device_id=dev.id,
                          gpu_uuid=GPU, gpu_mem_mb=1000, gpu_cores=10, status="bound"))
        dev.used_mem_mb, dev.used_cores = 1000, 10
    await get_redis().set(f"resume-gen:{sess.id}", "9")
    await StatusSync(db).on_status(
        sess.id, _ev("paused", generation=9, message="idle-reaped",
                     ts=datetime.now(UTC) - timedelta(minutes=2)))
    db.expunge_all()
    row = await db.get(Session, sess.id)
    card = await db.get(GpuDevice, dev.id)
    assert row.status == "paused" and row.status_reason == "idle"
    assert await _live_allocs(db, sess.id) == 0
    assert (card.used_mem_mb, card.used_cores) == (0, 0)


async def test_a_newer_generation_terminated_survives_an_operator_clock_that_lags(db):
    from app.core.redis import get_redis

    sess, _dev = await _seed(db, status="running", started_at=datetime.now(UTC))
    await get_redis().set(f"resume-gen:{sess.id}", "9")
    await StatusSync(db).on_status(
        sess.id, _ev("terminated", generation=10, ts=datetime.now(UTC) - timedelta(minutes=2)))
    db.expunge_all()
    assert (await db.get(Session, sess.id)).status == "terminated"


async def test_without_a_generation_the_run_start_still_rejects_the_echo(db):
    """Older operators report no generation: the run-start timestamp stays the only test, so the
    echo of a pause a resume overtook is still discarded."""
    sess, _dev = await _seed(db, status="running", started_at=datetime.now(UTC))
    await StatusSync(db).on_status(
        sess.id, _ev("paused", message="idle-reaped", ts=datetime.now(UTC) - timedelta(minutes=2)))
    db.expunge_all()
    assert (await db.get(Session, sess.id)).status == "running"


async def test_a_generation_without_a_resume_marker_still_falls_back_to_the_run_start(db):
    """No marker means no resume this session can be echoing (or a lost one); with nothing to
    compare the generation against, the timestamp remains the guard."""
    sess, _dev = await _seed(db, status="running", started_at=datetime.now(UTC))
    await StatusSync(db).on_status(
        sess.id, _ev("terminated", generation=4, ts=datetime.now(UTC) - timedelta(minutes=2)))
    db.expunge_all()
    assert (await db.get(Session, sess.id)).status == "running"

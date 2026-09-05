"""Session heartbeat: the control plane only believes a session is alive while the operator keeps saying so."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.api.schemas.internal import OperatorStatusEvent
from app.cluster.status_sync import StatusSync
from app.core import ids
from app.core.config import settings
from app.db.models import GpuNode, Session
from app.workers import session_liveness


def _session(**kw) -> Session:
    base = dict(
        id=ids.new("session"), owner_user_id=ids.new("user"), cluster_id="clu_t", offering_id="off_t",
        image_id="img_t", resource_class="gpu", mode="fractional", status="running",
        gpu_mem_mb=1024, gpu_cores=10, node_hostname="gpu-a",
    )
    base.update(kw)
    return Session(**base)


def _ev(**kw) -> OperatorStatusEvent:
    base = dict(phase="heartbeat", ts=datetime.now(UTC), node_name="gpu-a", restart_count=0, container_state="Running")
    base.update(kw)
    return OperatorStatusEvent(**base)


@pytest.mark.asyncio
async def test_heartbeat_stamps_the_session(db):
    sess = _session()
    async with db.begin():
        db.add(sess)
    await StatusSync(db).on_status(sess.id, _ev(restart_count=1))
    db.expunge_all()
    row = await db.get(Session, sess.id)
    assert row.last_reported_at is not None and row.restart_count == 1 and row.status == "running"


@pytest.mark.asyncio
async def test_crash_loop_ends_the_session(db, monkeypatch):
    sess = _session()
    async with db.begin():
        db.add(sess)
    monkeypatch.setattr(settings, "SESSION_CRASH_LOOP_RESTARTS", 3)
    await StatusSync(db).on_status(sess.id, _ev(restart_count=2, container_state="Waiting:CrashLoopBackOff"))
    db.expunge_all()
    assert (await db.get(Session, sess.id)).status == "running"      # below the threshold
    await db.commit()   # close the read transaction before the next sync begins its own
    await StatusSync(db).on_status(sess.id, _ev(restart_count=3, container_state="Waiting:CrashLoopBackOff"))
    db.expunge_all()
    row = await db.get(Session, sess.id)
    assert row.status == "error" and row.status_reason == "crash_loop"


class _Svc:
    calls: list[tuple[str, str]] = []

    def __init__(self, _db):
        pass

    async def terminate(self, sid, *, forced=False, reason="user_stopped"):
        _Svc.calls.append((sid, reason))


@pytest.mark.asyncio
async def test_stale_session_is_settled_only_while_the_operator_is_alive(db, monkeypatch):
    monkeypatch.setattr(session_liveness, "get_sessionmaker", lambda: (lambda: db))
    monkeypatch.setattr(session_liveness, "SessionService", _Svc)
    _Svc.calls = []
    stale_at = datetime.now(UTC) - timedelta(seconds=settings.SESSION_STALE_SEC + 60)
    lost = _session(cluster_id="clu_alive", last_reported_at=stale_at)
    fresh = _session(cluster_id="clu_alive", last_reported_at=datetime.now(UTC))
    never = _session(cluster_id="clu_alive")                       # pre-feature row: no stamp yet
    orphan = _session(cluster_id="clu_dead", last_reported_at=stale_at)
    async with db.begin():
        db.add_all([
            lost, fresh, never, orphan,
            GpuNode(id=ids.new("node"), cluster_id="clu_alive", hostname="n1", status="ready",
                    last_seen_at=datetime.now(UTC)),
            GpuNode(id=ids.new("node"), cluster_id="clu_dead", hostname="n2", status="ready",
                    last_seen_at=stale_at),
        ])
    await session_liveness.run()
    assert _Svc.calls == [(lost.id, "pod_lost")]


@pytest.mark.asyncio
async def test_stale_paused_report_after_a_resume_is_ignored(db):
    """Drain: stop() then start() within a second; the operator's Paused echo lands after the resume."""
    sess = _session(started_at=datetime.now(UTC))
    async with db.begin():
        db.add(sess)
    await StatusSync(db).on_status(sess.id, _ev(phase="paused", ts=datetime.now(UTC) - timedelta(seconds=5), restart_count=None, container_state=None))
    db.expunge_all()
    row = await db.get(Session, sess.id)
    assert row.status == "running" and row.status_reason is None


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["terminated", "error"])
async def test_stale_terminal_report_after_a_pod_replacement_is_ignored(db, phase):
    sess = _session(started_at=datetime.now(UTC))
    async with db.begin():
        db.add(sess)
    await StatusSync(db).on_status(sess.id, _ev(phase=phase, ts=datetime.now(UTC) - timedelta(seconds=5), restart_count=None, container_state=None))
    db.expunge_all()
    assert (await db.get(Session, sess.id)).status == "running"


@pytest.mark.asyncio
async def test_running_report_never_creates_an_allocation_for_a_cpu_session(db):
    from sqlalchemy import select as _select

    from app.db.models import Allocation
    sess = _session(resource_class="cpu", gpu_mem_mb=None, gpu_cores=None, cpu=2, mem_gb=4, status="preparing")
    async with db.begin():
        db.add(sess)
    await StatusSync(db).on_status(sess.id, _ev(phase="running", restart_count=None, container_state=None))
    assert await db.scalar(_select(Allocation).where(Allocation.session_id == sess.id)) is None


@pytest.mark.asyncio
async def test_paused_report_from_an_older_generation_is_ignored(db):
    """The operator reconciled the stop's generation after the resume committed: newer timestamp,
    older generation."""
    from app.core.redis import get_redis
    sess = _session(started_at=datetime.now(UTC) - timedelta(seconds=5))
    async with db.begin():
        db.add(sess)
    await get_redis().set(f"resume-gen:{sess.id}", "7")
    await StatusSync(db).on_status(sess.id, _ev(phase="paused", ts=datetime.now(UTC), generation=6, restart_count=None, container_state=None))
    db.expunge_all()
    assert (await db.get(Session, sess.id)).status == "running"


@pytest.mark.asyncio
async def test_paused_echo_without_a_reason_never_pauses_a_running_session(db):
    """Backend stop → resume within milliseconds: the operator's Paused (no reason) lands after."""
    sess = _session(started_at=datetime.now(UTC) - timedelta(seconds=1))
    async with db.begin():
        db.add(sess)
    await StatusSync(db).on_status(sess.id, _ev(phase="paused", ts=datetime.now(UTC), restart_count=None, container_state=None, message=None))
    db.expunge_all()
    row = await db.get(Session, sess.id)
    assert row.status == "running" and row.status_reason is None


@pytest.mark.asyncio
async def test_reaper_pause_with_a_reason_still_pauses(db):
    sess = _session(started_at=datetime.now(UTC) - timedelta(minutes=30))
    async with db.begin():
        db.add(sess)
    await StatusSync(db).on_status(sess.id, _ev(phase="paused", ts=datetime.now(UTC), restart_count=None, container_state=None, message="idle-reaped"))
    db.expunge_all()
    row = await db.get(Session, sess.id)
    assert row.status == "paused" and row.status_reason == "idle"


@pytest.mark.asyncio
async def test_pause_ack_is_recorded_for_a_backend_pause(db):
    from app.core.redis import get_redis
    sess = _session(status="paused")
    async with db.begin():
        db.add(sess)
    await StatusSync(db).on_status(sess.id, _ev(phase="paused", ts=datetime.now(UTC), restart_count=None, container_state=None))
    assert await get_redis().get(f"pause-ack:{sess.id}") is not None


@pytest.mark.asyncio
async def test_heartbeat_follows_the_pod_to_its_new_node(db):
    sess = _session(node_hostname="cpu01")
    async with db.begin():
        db.add(sess)
    await StatusSync(db).on_status(sess.id, _ev(node_name="cpu02"))
    db.expunge_all()
    assert (await db.get(Session, sess.id)).node_hostname == "cpu02"

"""Drain parking: a vacated session waits in the queue and resumes when room returns."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core import ids
from app.core.errors import InsufficientCredit, NoCapacity
from app.db.models import QueueEntry, Session
from app.domain import queue_ranking, scheduler


def _paused(**kw) -> Session:
    base = dict(
        id=ids.new("session"), owner_user_id=ids.new("user"), cluster_id="clu_t", offering_id="off_t",
        image_id="img_t", resource_class="gpu", mode="fractional", status="paused",
        status_reason="drained", gpu_mem_mb=1024, gpu_cores=10,
    )
    base.update(kw)
    return Session(**base)


@pytest.mark.asyncio
async def test_enqueue_resume_is_idempotent_and_invisible_to_the_pending_head(db):
    sess = _paused()
    async with db.begin():
        db.add(sess)
    async with db.begin():
        await scheduler.enqueue_resume(db, sess.id)
        await scheduler.enqueue_resume(db, sess.id)
    rows = (await db.execute(select(QueueEntry).where(QueueEntry.session_id == sess.id))).scalars().all()
    assert len(rows) == 1 and rows[0].session_req == {"resume": True}
    # The pending-session head skips parked resumes instead of dropping them as stale.
    assert await queue_ranking.head(db) is None
    await db.commit()


@pytest.mark.asyncio
async def test_parked_session_resumes_when_start_succeeds(db, monkeypatch):
    sess = _paused()
    async with db.begin():
        db.add(sess)
        await scheduler.enqueue_resume(db, sess.id)
    started: list[str] = []

    class _Svc:
        def __init__(self, _db):
            pass

        async def start(self, sid):
            started.append(sid)

    monkeypatch.setattr("app.domain.session_service.SessionService", _Svc)
    assert await scheduler.resume_parked_from_queue(db) == "admitted"
    assert started == [sess.id]
    assert await db.scalar(select(QueueEntry).where(QueueEntry.session_id == sess.id)) is None
    assert await scheduler.resume_parked_from_queue(db) == "empty"


@pytest.mark.asyncio
@pytest.mark.parametrize("exc, outcome, keeps_entry", [
    (NoCapacity("no room", {}), "blocked", True),
    (InsufficientCredit(available=0, need=1), "skipped", False),
])
async def test_parked_session_outcomes(db, monkeypatch, exc, outcome, keeps_entry):
    sess = _paused()
    async with db.begin():
        db.add(sess)
        await scheduler.enqueue_resume(db, sess.id)

    class _Svc:
        def __init__(self, _db):
            pass

        async def start(self, sid):
            raise exc

    monkeypatch.setattr("app.domain.session_service.SessionService", _Svc)
    assert await scheduler.resume_parked_from_queue(db) == outcome
    row = await db.scalar(select(QueueEntry).where(QueueEntry.session_id == sess.id))
    assert (row is not None) == keeps_entry

"""Concurrency tests on the opt-in Postgres backend (hypothesis H-7).

Each actor runs on its OWN AsyncSession from ``db_engine``'s pool, so the FOR UPDATE serialization,
the UNIQUE idempotency keys and the partial unique index on live allocations are exercised by real
concurrent transactions. Everything here skips automatically without ``GSHARE_TEST_DATABASE_URL``,
except the Redis-only races at the end, which run on fakeredis everywhere.
"""
from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core import ids
from app.core.errors import InsufficientCredit
from app.db.models import (
    Allocation,
    GpuDevice,
    QueueEntry,
    Session,
)
from app.domain.credit_engine import CreditEngine
from tests.beta_support import (
    check_ledger,
    ledger_rows,
    make_gpu_session,
    make_refs,
    make_wallet,
    wallet_state,
)
from tests.fkseed import seed

pytestmark = pytest.mark.asyncio
requires_pg = pytest.mark.skipif(
    not os.environ.get("GSHARE_TEST_DATABASE_URL"),
    reason="needs the opt-in Postgres backend (GSHARE_TEST_DATABASE_URL)",
)


@pytest.fixture
def maker(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)


async def _on_own_session(maker, fn):
    async with maker() as s:
        return await fn(s)


async def _gather(maker, fns):
    return await asyncio.gather(
        *(_on_own_session(maker, fn) for fn in fns), return_exceptions=True
    )


# ── credit engine ──────────────────────────────────────────────────────────────────────────
@requires_pg
async def test_concurrent_holds_never_exceed_the_balance(db, maker):
    wallet = await make_wallet(db, "100")

    def _hold(i):
        async def run(s):
            await CreditEngine(s).hold(wallet, Decimal("30"), key=f"hold:ses_{i}")
            return "ok"
        return run

    results = await _gather(maker, [_hold(i) for i in range(10)])
    ok = [r for r in results if r == "ok"]
    refused = [r for r in results if isinstance(r, InsufficientCredit)]
    other = [r for r in results if r != "ok" and not isinstance(r, InsufficientCredit)]
    assert other == [], other
    assert len(ok) == 3 and len(refused) == 7   # 3 x 30 = 90 fits, the fourth does not
    balance, reserved = await wallet_state(db, wallet)
    assert (balance, reserved) == (Decimal("100.00"), Decimal("90.00"))
    assert len(await ledger_rows(db, wallet)) == 3
    await check_ledger(db, wallet, Decimal("100"))


@requires_pg
async def test_concurrent_holds_with_one_key_apply_once(db, maker):
    """The same idempotency key raced by several callers: one reservation, one row (H-6)."""
    wallet = await make_wallet(db, "100")

    async def run(s):
        await CreditEngine(s).hold(wallet, Decimal("30"), key="hold:ses_same")
        return "ok"

    results = await _gather(maker, [run] * 6)
    assert all(r == "ok" for r in results), results
    assert (await wallet_state(db, wallet))[1] == Decimal("30.00")
    assert len(await ledger_rows(db, wallet)) == 1


@requires_pg
async def test_concurrent_consume_of_one_bucket_charges_once(db, maker):
    refs = await make_refs(db)
    wallet = await make_wallet(db, "100", owner_id=refs.user_id)
    started = datetime.now(UTC) - timedelta(minutes=30)
    sess = await make_gpu_session(db, refs, wallet, "60", started)
    sid = sess.id

    async def run(s):
        row = await s.get(Session, sid)
        await s.commit()
        await CreditEngine(s).consume(row, 7, started + timedelta(minutes=30))
        return "ok"

    results = await _gather(maker, [run] * 6)
    assert all(r == "ok" for r in results), results
    assert (await wallet_state(db, wallet))[0] == Decimal("70.00")
    assert len(await ledger_rows(db, wallet, ref=sid)) == 1
    await check_ledger(db, wallet, Decimal("100"))


@requires_pg
async def test_concurrent_settle_of_one_session_refunds_once_and_spares_the_neighbour(db, maker):
    """Two sessions hold on one wallet. Six concurrent settles of A must produce exactly one
    refund of A's leftover and leave B's reservation untouched."""
    refs = await make_refs(db)
    wallet = await make_wallet(db, "1000", owner_id=refs.user_id)
    started = datetime.now(UTC) - timedelta(minutes=30)
    a = await make_gpu_session(db, refs, wallet, "60", started)
    b = await make_gpu_session(db, refs, wallet, "60", started)
    engine = CreditEngine(db)
    await engine.hold(wallet, Decimal("100"), key=f"hold:{a.id}")
    await engine.hold(wallet, Decimal("80"), key=f"hold:{b.id}")
    await engine.consume(a, 1, started + timedelta(minutes=30))   # A owes 30
    aid = a.id

    async def run(s):
        row = await s.get(Session, aid)
        await s.commit()
        await CreditEngine(s).settle(row, key=f"settle:{aid}", final_consume=False)
        return "ok"

    results = await _gather(maker, [run] * 6)
    assert all(r == "ok" for r in results), results
    balance, reserved = await wallet_state(db, wallet)
    assert (balance, reserved) == (Decimal("970.00"), Decimal("80.00"))
    rows = await ledger_rows(db, wallet, ref=aid)
    assert [r.amount for r in rows if r.type == "refund"] == [Decimal("70.00")]
    assert len([r for r in rows if r.type == "settle"]) == 1
    await check_ledger(db, wallet, Decimal("1000"))


# ── GPU admission ──────────────────────────────────────────────────────────────────────────
async def _pending_gpu_sessions(db, refs, wallet, n, *, mem=8000, cores=50):
    out = []
    for _ in range(n):
        s = await make_gpu_session(db, refs, wallet, "60", None, status="pending",
                                   gpu_mem_mb=mem, gpu_cores=cores, total_mem_mb=None)
        out.append(s.id)
    return out


async def _live_allocs(db):
    rows = (await db.execute(
        select(Allocation.session_id, Allocation.device_id, Allocation.gpu_mem_mb)
        .where(Allocation.ended_at.is_(None))
    )).all()
    await db.commit()
    return rows


@requires_pg
async def test_concurrent_admission_on_one_card_never_overcommits(db, maker):
    """Four 8000 MB requests race for one 16000 MB card: exactly two are placed and the card's
    used counter equals the sum of its live allocations."""
    from app.domain.scheduler import SchedulerService

    refs = await make_refs(db, devices=1)
    wallet = await make_wallet(db, "1000", owner_id=refs.user_id)
    sids = await _pending_gpu_sessions(db, refs, wallet, 4)

    def _reserve(sid):
        async def run(s):
            svc = SchedulerService(s)
            async with s.begin():
                sess = await s.get(Session, sid)
                req = svc._req_from_entry(None, sess)
                return await svc.reserve_slice(sess, req)
        return run

    results = await _gather(maker, [_reserve(sid) for sid in sids])
    errors = [r for r in results if isinstance(r, BaseException)]
    assert errors == [], errors
    assert sorted(results) == [False, False, True, True]
    allocs = await _live_allocs(db)
    assert len(allocs) == 2 and sum(a.gpu_mem_mb for a in allocs) == 16000
    dev = (await db.execute(select(GpuDevice.used_mem_mb, GpuDevice.total_mem_mb))).one()
    await db.commit()
    assert dev.used_mem_mb == 16000 <= dev.total_mem_mb


@requires_pg
async def test_concurrent_dequeue_admits_the_head_exactly_once(db, maker, monkeypatch):
    """Two queue tickers racing on the same head must not reserve the session twice: the loser
    is stopped by the FOR UPDATE on the card plus the live-allocation unique index."""
    from app.domain import queue_ranking, scheduler
    from tests.conftest import FakeHandoff

    refs = await make_refs(db, devices=1)
    wallet = await make_wallet(db, "1000", owner_id=refs.user_id)
    (sid,) = await _pending_gpu_sessions(db, refs, wallet, 1)
    await seed(db, [QueueEntry(id=ids.new("queue"), session_id=sid, session_req={}, priority=0)])

    barrier = asyncio.Barrier(2)
    real_head = queue_ranking.head

    async def head_then_wait(s):
        entry = await real_head(s)
        await barrier.wait()   # both tickers have read the same head before either reserves
        return entry

    monkeypatch.setattr(scheduler.queue_ranking, "head", head_then_wait)

    async def run(s):
        svc = scheduler.SchedulerService(s)
        svc.handoff = FakeHandoff()
        return await svc.reschedule_from_queue()

    results = await _gather(maker, [run, run])
    admitted = [r for r in results if r == "admitted"]
    assert len(admitted) == 1, results
    allocs = await _live_allocs(db)
    assert len(allocs) == 1 and allocs[0].session_id == sid
    dev = (await db.execute(select(GpuDevice.used_mem_mb))).scalar_one()
    await db.commit()
    assert dev == 8000
    left = await db.scalar(select(func.count()).select_from(QueueEntry))
    await db.commit()
    assert left == 0


# ── workers ────────────────────────────────────────────────────────────────────────────────
@requires_pg
async def test_two_billing_ticks_at_once_charge_each_session_once(db, maker, monkeypatch):
    from app.workers import billing_worker

    refs = await make_refs(db)
    wallet = await make_wallet(db, "1000", owner_id=refs.user_id)
    started = datetime.now(UTC) - timedelta(minutes=10)
    sids = [(await make_gpu_session(db, refs, wallet, "60", started)).id for _ in range(3)]
    monkeypatch.setattr(billing_worker, "get_sessionmaker", lambda: maker)

    await asyncio.gather(billing_worker.run(), billing_worker.run(), billing_worker.run())
    for sid in sids:
        rows = await ledger_rows(db, wallet, ref=sid)
        assert len(rows) == 1 and rows[0].type == "consume", rows
    # 3 sessions x ceil(10 min) x 60/h = 30 in total, once.
    assert (await wallet_state(db, wallet))[0] == Decimal("970.00")
    await check_ledger(db, wallet, Decimal("1000"))


@requires_pg
async def test_session_create_with_one_idempotency_key_yields_one_session(db, maker, fake_handoff):
    """Redis SET NX idempotency: two API workers racing on the same Idempotency-Key must return
    the same session and create one row (the loser polls for the winner's id)."""
    from app.api.schemas.session import SessionCreate
    from app.auth.rbac import Principal
    from app.domain.scheduler import SchedulerService

    refs = await make_refs(db, devices=1)
    wallet = await make_wallet(db, "1000", owner_id=refs.user_id)
    principal = Principal(user_id=refs.user_id)

    async def run(s):
        svc = SchedulerService(s)
        svc.handoff = fake_handoff
        req = SessionCreate(offering_id=refs.offering_id, image_id=refs.image_id,
                            resource_class="gpu", cluster_id=refs.cluster_id, gpu_mem_mb=8000,
                            gpu_cores=50, mode="fractional", billing_wallet_id=wallet)
        return (await svc.create_session(req, principal, idem="same-key")).id

    results = await _gather(maker, [run, run, run])
    errors = [r for r in results if isinstance(r, BaseException)]
    assert errors == [], errors
    assert len(set(results)) == 1
    n = await db.scalar(select(func.count()).select_from(Session))
    await db.commit()
    assert n == 1
    assert (await wallet_state(db, wallet))[1] > Decimal("0")   # one hold
    assert len(await ledger_rows(db, wallet)) == 1


# ── Redis-only races (fakeredis; run everywhere) ──────────────────────────────────────────
async def test_set_nx_race_has_exactly_one_winner(fake_redis):
    results = await asyncio.gather(*(fake_redis.set("idem:beta", str(i), nx=True, ex=60)
                                     for i in range(25)))
    assert sum(1 for r in results if r) == 1


async def test_runner_lock_lets_one_replica_run_a_job(fake_redis, monkeypatch):
    """Two worker replicas ticking the same job under the Redis owner-token lock: the job runs
    once per tick and the lock is released by its owner."""
    from app.workers import runner

    ran: list[int] = []

    async def job():
        ran.append(1)
        await asyncio.sleep(0.05)

    async def stop_after_first_tick(_interval):
        raise asyncio.CancelledError

    monkeypatch.setattr(runner.asyncio, "sleep", stop_after_first_tick)
    outcomes = await asyncio.gather(
        runner.loop(job, 60, "beta_job"), runner.loop(job, 60, "beta_job"),
        return_exceptions=True,
    )
    assert all(isinstance(o, asyncio.CancelledError) for o in outcomes)
    assert ran == [1]

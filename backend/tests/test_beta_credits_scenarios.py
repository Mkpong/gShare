"""Beta-test scenarios for the credit engine (hold -> consume -> settle/refund).

Every scenario finishes with ``check_ledger``: the wallet's balance must equal its starting
balance plus the sum of every balance-moving ledger row (hold/refund/settle move ``reserved``
only), the last row's ``balance_after`` must match the wallet, and 0 <= reserved <= balance.
Runs on the in-memory SQLite ``db`` fixture and, with ``GSHARE_TEST_DATABASE_URL`` set, on
Postgres.
"""
from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.core import ids
from app.core.errors import Forbidden, InsufficientCredit
from app.db.models import (
    CreditTransaction,
    CreditWallet,
    Membership,
    Organization,
    Project,
    Session,
)
from app.domain.credit_engine import CreditEngine
from tests.beta_support import (
    check_ledger,
    ledger_rows,
    make_gpu_session,
    make_refs,
    make_user,
    make_wallet,
    wallet_state,
)
from tests.fkseed import seed

pytestmark = pytest.mark.asyncio


# ── 1 balance exactly equal to the hold ──────────────────────────────────────────────────────
async def test_balance_equal_to_hold_runs_the_full_hour_then_settles_to_zero(db, fake_redis):
    """A wallet funded to exactly one hour must run that hour, be exhausted only at its end, and
    settle to 0/0 with no refund and no negative balance."""
    refs = await make_refs(db)
    wallet = await make_wallet(db, "60", owner_id=refs.user_id)
    engine = CreditEngine(db)
    started = datetime.now(UTC) - timedelta(hours=1)
    sess = await make_gpu_session(db, refs, wallet, "60", started)

    await engine.hold(wallet, Decimal("60"), key=f"hold:{sess.id}")
    assert await wallet_state(db, wallet) == (Decimal("60.00"), Decimal("60.00"))

    for minute in (1, 30, 59):
        await engine.consume(sess, minute, started + timedelta(minutes=minute))
        balance, reserved = await wallet_state(db, wallet)
        assert balance == Decimal(60 - minute) and reserved == balance
        # Own reservation covers the rest of the hour: not exhausted yet.
        assert await fake_redis.get(f"grace:{sess.id}") is None, minute

    await engine.consume(sess, 60, started + timedelta(minutes=60))
    assert await wallet_state(db, wallet) == (Decimal("0.00"), Decimal("0.00"))
    assert await fake_redis.get(f"grace:{sess.id}") is not None  # exhausted exactly at the end

    await engine.settle(sess, key=f"settle:{sess.id}", final_consume=False)
    rows = await ledger_rows(db, wallet, ref=sess.id)
    assert [r.type for r in rows if r.type == "refund"] == []  # nothing left to refund
    assert sum(-r.amount for r in rows if r.type == "consume") == Decimal("60.00")
    await check_ledger(db, wallet, Decimal("60"))


# ── 2 balance zero ─────────────────────────────────────────────────────────────────────────
async def test_zero_balance_rejects_hold_and_consume_is_a_clean_no_charge(db, fake_redis):
    refs = await make_refs(db)
    wallet = await make_wallet(db, "0", owner_id=refs.user_id)
    engine = CreditEngine(db)
    started = datetime.now(UTC) - timedelta(minutes=5)
    sess = await make_gpu_session(db, refs, wallet, "60", started)
    await engine.consume(sess, 5, started + timedelta(minutes=5))
    # Nothing to debit: no consume row, no negative balance, but grace is armed.
    assert await ledger_rows(db, wallet, ref=sess.id) == []
    assert await fake_redis.get(f"grace:{sess.id}") is not None
    await engine.settle(sess, key=f"settle:{sess.id}")
    rows = await ledger_rows(db, wallet, ref=sess.id)
    assert [r.type for r in rows] == ["settle"] and rows[0].amount == Decimal("0")
    await check_ledger(db, wallet, Decimal("0"))

    # Last, because a rejected hold leaves the aiosqlite connection awaiting rollback (see
    # test_credit_engine): even one cent is refused on an empty wallet.
    with pytest.raises(InsufficientCredit) as exc:
        await engine.hold(wallet, Decimal("0.01"), key="hold:ses_zero")
    assert exc.value.http == 402
    if db.bind.dialect.name == "postgresql":
        await db.rollback()
        assert len(await ledger_rows(db, wallet)) == len(rows)   # no row left behind
        assert await wallet_state(db, wallet) == (Decimal("0.00"), Decimal("0.00"))


# ── 3 sub-cent amounts: rounding direction and zero drift ─────────────────────────────────
async def test_hold_rounds_half_up_to_the_cent(db):
    wallet = await make_wallet(db, "100")
    engine = CreditEngine(db)
    await engine.hold(wallet, Decimal("10.005"), key="hold:ses_a")
    assert (await wallet_state(db, wallet))[1] == Decimal("10.01")  # half-up, never truncated
    await engine.hold(wallet, Decimal("10.004"), key="hold:ses_b")
    assert (await wallet_state(db, wallet))[1] == Decimal("20.01")
    rows = await ledger_rows(db, wallet)
    assert [r.amount for r in rows] == [Decimal("10.01"), Decimal("10.00")]
    await check_ledger(db, wallet, Decimal("100"))


async def test_running_total_differencing_has_no_per_minute_rounding_drift(db):
    """rate 1.00/h at 1/3 occupancy owes 0.00556/min: rounding each minute on its own would bill
    0.01 x 60 = 0.60 for the hour; differencing must bill round(1/3) = 0.33."""
    refs = await make_refs(db)
    wallet = await make_wallet(db, "10", owner_id=refs.user_id)
    engine = CreditEngine(db)
    started = datetime.now(UTC) - timedelta(hours=1)
    # occupancy = max(5000/15000, 0/100) = 1/3
    sess = await make_gpu_session(db, refs, wallet, "1.00", started, gpu_mem_mb=5000,
                                  gpu_cores=0, total_mem_mb=15000)
    for minute in range(1, 61):
        await engine.consume(sess, minute, started + timedelta(minutes=minute))
    balance, _ = await wallet_state(db, wallet)
    assert Decimal("10") - balance == Decimal("0.33")
    rows = await ledger_rows(db, wallet, ref=sess.id)
    assert all(r.amount <= Decimal("-0.01") for r in rows)  # only non-zero debits are recorded
    assert sum(-r.amount for r in rows) == Decimal("0.33")
    await check_ledger(db, wallet, Decimal("10"))


async def test_sub_cent_rate_charges_nothing_until_a_cent_is_owed(db):
    refs = await make_refs(db)
    wallet = await make_wallet(db, "10", owner_id=refs.user_id)
    engine = CreditEngine(db)
    started = datetime.now(UTC) - timedelta(minutes=10)
    sess = await make_gpu_session(db, refs, wallet, "0.10", started)  # 0.00167/min
    await engine.consume(sess, 1, started + timedelta(minutes=1))   # owed 0.00 -> nothing
    assert await ledger_rows(db, wallet, ref=sess.id) == []
    await engine.consume(sess, 3, started + timedelta(minutes=3))   # owed 0.005 -> 0.01
    assert (await wallet_state(db, wallet))[0] == Decimal("9.99")
    await check_ledger(db, wallet, Decimal("10"))


# ── 4 pause / resume cycles ───────────────────────────────────────────────────────────────
async def _backdate_rows(db, session_id: str, at: datetime) -> None:
    """Move this session's ledger rows to the simulated clock: in production the rows are
    written at the moment of the charge, which is what the run-scoped sum relies on."""
    async with db.begin():
        await db.execute(
            update(CreditTransaction)
            .where(CreditTransaction.ref == session_id, CreditTransaction.created_at > at)
            .values(created_at=at)
        )


async def test_pause_resume_cycles_bill_only_the_running_intervals(db):
    """Run 30 min, pause (true-up), resume with a rebased started_at, run 20 min, pause, resume,
    run 10 min, terminate from paused. Total billed must be 60 min = 60 credits; the paused gaps
    must not be billed; the hold refunds exactly hold - consumed."""
    refs = await make_refs(db)
    wallet = await make_wallet(db, "200", owner_id=refs.user_id)
    engine = CreditEngine(db)
    t0 = datetime.now(UTC) - timedelta(hours=6)
    sess = await make_gpu_session(db, refs, wallet, "60", t0)
    await engine.hold(wallet, Decimal("60"), key=f"hold:{sess.id}")

    bucket = 1000
    await engine.consume(sess, bucket, t0 + timedelta(minutes=20))
    bucket += 1
    await engine.consume(sess, bucket, t0 + timedelta(minutes=30))   # pause true-up: 30
    await _backdate_rows(db, sess.id, t0 + timedelta(minutes=30))
    assert (await wallet_state(db, wallet))[0] == Decimal("170.00")

    resumed_at = t0 + timedelta(hours=2)   # a two-hour paused gap on the session's timeline
    for run_minutes, expected_balance in ((20, Decimal("150.00")), (10, Decimal("140.00"))):
        async with db.begin():
            row = await db.get(Session, sess.id)
            row.started_at = resumed_at
        db.expunge_all()
        sess = await db.get(Session, sess.id)
        await db.commit()
        bucket += 1
        await engine.consume(sess, bucket, resumed_at + timedelta(minutes=run_minutes // 2))
        bucket += 1
        await engine.consume(sess, bucket, resumed_at + timedelta(minutes=run_minutes))
        await _backdate_rows(db, sess.id, resumed_at + timedelta(minutes=run_minutes))
        balance, reserved = await wallet_state(db, wallet)
        assert balance == expected_balance, (run_minutes, balance)
        assert reserved == max(Decimal("0"), Decimal("60") - (Decimal("200") - balance))
        resumed_at += timedelta(hours=2)

    # Terminate from paused: no final consume (the clock kept running while nothing ran).
    await engine.settle(sess, key=f"settle:{sess.id}", final_consume=False)
    balance, reserved = await wallet_state(db, wallet)
    assert (balance, reserved) == (Decimal("140.00"), Decimal("0.00"))
    rows = await ledger_rows(db, wallet, ref=sess.id)
    assert sum(-r.amount for r in rows if r.type == "consume") == Decimal("60.00")
    assert [r.amount for r in rows if r.type == "refund"] == []  # hold 60 fully consumed
    await check_ledger(db, wallet, Decimal("200"))


async def test_terminate_from_paused_refunds_the_unused_slice_of_the_hold(db):
    refs = await make_refs(db)
    wallet = await make_wallet(db, "200", owner_id=refs.user_id)
    engine = CreditEngine(db)
    started = datetime.now(UTC) - timedelta(minutes=15)
    sess = await make_gpu_session(db, refs, wallet, "60", started, status="paused")
    await engine.hold(wallet, Decimal("60"), key=f"hold:{sess.id}")
    await engine.consume(sess, 7, started + timedelta(minutes=15))   # pause true-up: 15
    await engine.settle(sess, key=f"settle:{sess.id}", final_consume=False)
    balance, reserved = await wallet_state(db, wallet)
    assert (balance, reserved) == (Decimal("185.00"), Decimal("0.00"))
    rows = await ledger_rows(db, wallet, ref=sess.id)
    assert [r.amount for r in rows if r.type == "refund"] == [Decimal("45.00")]
    await check_ledger(db, wallet, Decimal("200"))


# ── 5 settle twice / out of order ─────────────────────────────────────────────────────────
async def test_settle_twice_is_idempotent_and_refunds_once(db):
    refs = await make_refs(db)
    wallet = await make_wallet(db, "100", owner_id=refs.user_id)
    engine = CreditEngine(db)
    started = datetime.now(UTC) - timedelta(minutes=30)
    sess = await make_gpu_session(db, refs, wallet, "60", started)
    await engine.hold(wallet, Decimal("60"), key=f"hold:{sess.id}")
    await engine.consume(sess, 1, started + timedelta(minutes=30))   # 30 charged
    await engine.settle(sess, key=f"settle:{sess.id}")
    first = await wallet_state(db, wallet)
    assert first[1] == Decimal("0.00")
    # Re-take a hold that must NOT be released again by a duplicate settle.
    await engine.hold(wallet, Decimal("10"), key="hold:other")
    await engine.settle(sess, key=f"settle:{sess.id}")
    await engine.settle(sess, key=f"settle:{sess.id}", final_consume=False)
    balance, reserved = await wallet_state(db, wallet)
    assert balance == first[0] and reserved == Decimal("10.00")
    rows = await ledger_rows(db, wallet, ref=sess.id)
    assert len([r for r in rows if r.type == "settle"]) == 1
    assert len([r for r in rows if r.type == "refund"]) == 1
    await check_ledger(db, wallet, Decimal("100"))


async def test_consume_after_settle_does_not_charge_a_settled_session(db):
    """A late per-minute tick that lands after settle must not reopen billing: the session is
    terminal, its hold is refunded, and a charge now would move balance with no way to settle
    it again (settle:{ses} is already spent)."""
    refs = await make_refs(db)
    wallet = await make_wallet(db, "100", owner_id=refs.user_id)
    engine = CreditEngine(db)
    started = datetime.now(UTC) - timedelta(minutes=30)
    sess = await make_gpu_session(db, refs, wallet, "60", started)
    await engine.hold(wallet, Decimal("60"), key=f"hold:{sess.id}")
    await engine.consume(sess, 1, started + timedelta(minutes=30))
    await engine.settle(sess, key=f"settle:{sess.id}")
    settled = await wallet_state(db, wallet)

    await engine.consume(sess, 2, started + timedelta(minutes=45))   # out-of-order late tick
    assert await wallet_state(db, wallet) == settled
    rows = await ledger_rows(db, wallet, ref=sess.id)
    assert rows[-1].type == "settle"   # the settle marker stays the last word
    await check_ledger(db, wallet, Decimal("100"))


async def test_settle_before_the_last_tick_bills_the_partial_minute_once(db):
    """settle(final_consume=True) closes the final partial minute; a tick for the same minute that
    arrives afterwards must find nothing left to charge."""
    refs = await make_refs(db)
    wallet = await make_wallet(db, "100", owner_id=refs.user_id)
    engine = CreditEngine(db)
    # started 30m30s ago: settle owes ceil -> 31 minutes = 31.00
    started = datetime.now(UTC) - timedelta(minutes=30, seconds=30)
    sess = await make_gpu_session(db, refs, wallet, "60", started)
    await engine.hold(wallet, Decimal("60"), key=f"hold:{sess.id}")
    await engine.consume(sess, 1, started + timedelta(minutes=30))   # 30
    await engine.settle(sess, key=f"settle:{sess.id}", final_consume=True)
    balance, reserved = await wallet_state(db, wallet)
    assert balance == Decimal("69.00") and reserved == Decimal("0.00")
    rows = await ledger_rows(db, wallet, ref=sess.id)
    assert [r.amount for r in rows if r.type == "refund"] == [Decimal("29.00")]
    await check_ledger(db, wallet, Decimal("100"))


# ── 6 exhaustion -> grace -> pause -> top-up -> auto-resume attempt ───────────────────────
async def test_exhaustion_grace_pause_and_topup_resume_flow(db, fake_redis, monkeypatch):
    from app.cluster.handoff import Handoff
    from app.domain import session_service as ss_mod
    from app.workers import grace_enforcer

    refs = await make_refs(db)
    wallet = await make_wallet(db, "5", owner_id=refs.user_id)
    engine = CreditEngine(db)
    started = datetime.now(UTC) - timedelta(hours=1)
    sess = await make_gpu_session(db, refs, wallet, "300", started)
    sid = sess.id

    # Exhaustion: 300 owed, 5 available -> charged down to 0, grace armed.
    await engine.consume(sess, 1, started + timedelta(hours=1))
    assert await wallet_state(db, wallet) == (Decimal("0.00"), Decimal("0.00"))
    assert await fake_redis.get(f"grace:{sid}") is not None

    paused_calls: list[tuple[str, bool]] = []

    async def _fake_set_paused(self, s, paused, *, graceful_demote=None):
        paused_calls.append((s.id, paused))
        return 0

    monkeypatch.setattr(Handoff, "set_paused", _fake_set_paused)
    monkeypatch.setattr(grace_enforcer, "get_sessionmaker", lambda: (lambda: db))

    # Inside the window: only a warning, the session keeps running.
    await grace_enforcer.run()
    db.expunge_all()
    assert (await db.get(Session, sid)).status == "running"
    await db.commit()
    assert await fake_redis.get(f"grace-warned:{sid}") is not None
    assert paused_calls == []

    # Window expired and still short -> graceful pause (credit_exhausted), hold kept.
    await fake_redis.set(f"grace:{sid}", str(time.time() - ss_mod.GRACE_PERIOD_SEC - 1))
    await grace_enforcer.run()
    db.expunge_all()
    row = await db.get(Session, sid)
    assert (row.status, row.status_reason) == ("paused", "credit_exhausted")
    await db.commit()
    assert paused_calls == [(sid, True)]
    assert await fake_redis.get(f"grace:{sid}") is None
    assert await fake_redis.get(f"credit-paused:{sid}") is not None
    # Still broke: the resume pass leaves it paused and keeps the marker.
    started_calls: list[str] = []

    async def _fake_start(self, session_id):
        started_calls.append(session_id)

    monkeypatch.setattr(ss_mod.SessionService, "start", _fake_start)
    await grace_enforcer.run()
    assert started_calls == []
    assert await fake_redis.get(f"credit-paused:{sid}") is not None

    # Top up -> the next tick auto-resumes and drops the marker.
    async with db.begin():
        w = await db.get(CreditWallet, wallet, with_for_update=True)
        w.balance += Decimal("50")
        db.add(CreditTransaction(
            id=ids.new("transaction"), wallet_id=w.id, type="topup", amount=Decimal("50"),
            balance_after=w.balance, idempotency_key="topup:beta", ref=None,
        ))
    await grace_enforcer.run()
    assert started_calls == [sid]
    assert await fake_redis.get(f"credit-paused:{sid}") is None
    await check_ledger(db, wallet, Decimal("5"))


# ── 7 monthly refill ───────────────────────────────────────────────────────────────────────
def _refill_ready(db, monkeypatch):
    from app.workers import credit_refill

    monkeypatch.setattr(credit_refill, "get_sessionmaker", lambda: (lambda: db))
    return credit_refill


async def test_monthly_refill_tops_up_to_grant_keeps_surplus_and_respects_reserved(
    db, fake_redis, monkeypatch
):
    refill = _refill_ready(db, monkeypatch)
    low = await make_wallet(db, "30", grant="100")
    high = await make_wallet(db, "150", grant="100")          # surplus is kept (top-up, not reset)
    held = await make_wallet(db, "50", reserved="50", grant="40")   # reserved above grant: untouched
    held_low = await make_wallet(db, "20", reserved="20", grant="100")
    none = await make_wallet(db, "5", grant="0")              # 0 disables refills

    await refill.run()
    db.expunge_all()
    assert await wallet_state(db, low) == (Decimal("100.00"), Decimal("0.00"))
    assert await wallet_state(db, high) == (Decimal("150.00"), Decimal("0.00"))
    assert await wallet_state(db, held) == (Decimal("50.00"), Decimal("50.00"))
    assert await wallet_state(db, held_low) == (Decimal("100.00"), Decimal("20.00"))
    assert await wallet_state(db, none) == (Decimal("5.00"), Decimal("0.00"))
    for w, initial in ((low, "30"), (high, "150"), (held, "50"), (held_low, "20"), (none, "5")):
        await check_ledger(db, w, Decimal(initial))
    rows = await ledger_rows(db, low)
    assert [(r.type, r.amount, r.ref) for r in rows] == [("adjust", Decimal("70.00"), "monthly_refill")]

    # Same month again: the Redis month marker makes the second tick a no-op.
    await refill.run()
    db.expunge_all()
    assert await wallet_state(db, low) == (Decimal("100.00"), Decimal("0.00"))


async def test_monthly_refill_replay_after_marker_loss_never_credits_twice(
    db, fake_redis, monkeypatch
):
    """Redis lost the month marker (restart without persistence) after a sweep that already
    credited wallet A. The replay must not credit A again, must not raise, and must still finish
    the sweep for wallets the earlier run had not reached."""
    refill = _refill_ready(db, monkeypatch)
    a = await make_wallet(db, "30", grant="100")
    b = await make_wallet(db, "10", grant="100")
    await refill.run()
    db.expunge_all()
    assert (await wallet_state(db, a))[0] == Decimal("100.00")

    # A spends 40; then the marker is lost and the worker re-runs.
    async with db.begin():
        row = await db.get(CreditWallet, a, with_for_update=True)
        row.balance -= Decimal("40")
        db.add(CreditTransaction(
            id=ids.new("transaction"), wallet_id=a, type="consume", amount=Decimal("-40"),
            balance_after=row.balance, idempotency_key="consume:beta:1", ref="ses",
        ))
    keys = [k async for k in fake_redis.scan_iter(match="credit_refill:done:*")]
    assert keys
    await fake_redis.delete(*keys)

    await refill.run()   # must not raise, must not double-credit
    db.expunge_all()
    assert (await wallet_state(db, a))[0] == Decimal("60.00")   # no second refill this month
    assert (await wallet_state(db, b))[0] == Decimal("100.00")
    assert len([r for r in await ledger_rows(db, a) if r.type == "adjust"]) == 1
    await check_ledger(db, a, Decimal("30"))
    await check_ledger(db, b, Decimal("10"))


async def test_monthly_refill_failed_sweep_releases_the_month_marker(db, fake_redis, monkeypatch):
    """A sweep that crashes half-way must not leave the month marker claimed: the hourly tick has
    to retry, or the unreached wallets go without their refill for the whole month."""
    from app.workers import credit_refill

    await make_wallet(db, "1", grant="100")
    calls = {"n": 0}

    def _flaky_sessionmaker():
        calls["n"] += 1
        if calls["n"] == 2:   # the schedule read succeeds; the sweep session blows up
            raise RuntimeError("db gone")
        return lambda: db

    monkeypatch.setattr(credit_refill, "get_sessionmaker", _flaky_sessionmaker)
    with pytest.raises(RuntimeError):
        await credit_refill.run()
    keys = [k async for k in fake_redis.scan_iter(match="credit_refill:done:*")]
    assert keys == [], "month marker must be released after a failed sweep"


# ── 8 hierarchical allocation / monthly grant ceilings ────────────────────────────────────
async def _org_tree(db):
    org = Organization(id=ids.new("org"), name=ids.new("org"))
    prj = Project(id=ids.new("group"), org_id=org.id, name="p")
    prj2 = Project(id=ids.new("group"), org_id=org.id, name="p2")
    await seed(db, [org, prj, prj2])
    return org.id, prj.id, prj2.id


async def test_allocate_cannot_hand_out_more_than_the_parent_received(db):
    from app.api.credits_router import allocate
    from app.api.schemas.credit import AllocateBody
    from app.auth.rbac import Principal

    org, prj, _ = await _org_tree(db)
    org_w = await make_wallet(db, "100", reserved="30", owner_type="org", owner_id=org)
    prj_w = await make_wallet(db, "0", owner_type="group", owner_id=prj)
    admin = Principal(user_id=await make_user(db), org_admin_orgs={org})

    # available = 100 - 30 = 70: 70.01 is refused, 70 is granted.
    with pytest.raises(InsufficientCredit):
        await allocate(AllocateBody(from_wallet_id=org_w, to_wallet_id=prj_w,
                                    amount=Decimal("70.01")), principal=admin, idem="a1", db=db)
    await db.rollback()
    await allocate(AllocateBody(from_wallet_id=org_w, to_wallet_id=prj_w,
                                amount=Decimal("70")), principal=admin, idem="a2", db=db)
    assert await wallet_state(db, org_w) == (Decimal("30.00"), Decimal("30.00"))
    assert await wallet_state(db, prj_w) == (Decimal("70.00"), Decimal("0.00"))
    # Replay with the same key moves nothing.
    await allocate(AllocateBody(from_wallet_id=org_w, to_wallet_id=prj_w,
                                amount=Decimal("70")), principal=admin, idem="a2", db=db)
    assert await wallet_state(db, prj_w) == (Decimal("70.00"), Decimal("0.00"))
    await check_ledger(db, org_w, Decimal("100"))
    await check_ledger(db, prj_w, Decimal("0"))


async def test_monthly_grant_siblings_cannot_exceed_the_parent_grant(db):
    from app.api.credits_router import set_monthly_grant
    from app.api.schemas.credit import MonthlyGrantBody
    from app.auth.rbac import Principal
    from app.core.errors import DomainError

    org, prj, prj2 = await _org_tree(db)
    await make_wallet(db, "0", owner_type="org", owner_id=org, grant="100")
    w1 = await make_wallet(db, "0", owner_type="group", owner_id=prj, grant="60")
    w2 = await make_wallet(db, "0", owner_type="group", owner_id=prj2)
    admin = Principal(user_id=await make_user(db), org_admin_orgs={org})

    with pytest.raises(DomainError) as exc:
        await set_monthly_grant(w2, MonthlyGrantBody(amount=Decimal("40.01")),
                                principal=admin, db=db)
    assert exc.value.code == "validation_failed"
    await db.rollback()
    await set_monthly_grant(w2, MonthlyGrantBody(amount=Decimal("40")), principal=admin, db=db)
    db.expunge_all()
    assert (await db.get(CreditWallet, w2)).monthly_grant == Decimal("40.00")
    assert (await db.get(CreditWallet, w1)).monthly_grant == Decimal("60.00")


async def test_monthly_grant_increase_credits_balance_through_the_ledger(db):
    """The immediate credit on a grant increase moves balance, so it must be a ledger row:
    otherwise the transaction history no longer explains the wallet balance."""
    from app.api.credits_router import bulk_monthly_grant, set_monthly_grant
    from app.api.schemas.credit import BulkMonthlyGrantBody, MonthlyGrantBody
    from app.auth.rbac import Principal

    org, prj, _ = await _org_tree(db)
    await make_wallet(db, "0", owner_type="org", owner_id=org, grant="1000")
    prj_w = await make_wallet(db, "10", owner_type="group", owner_id=prj, grant="0")
    admin = Principal(user_id=await make_user(db), org_admin_orgs={org})

    await set_monthly_grant(prj_w, MonthlyGrantBody(amount=Decimal("100")),
                            principal=admin, db=db)
    assert (await wallet_state(db, prj_w))[0] == Decimal("100.00")
    await check_ledger(db, prj_w, Decimal("10"))   # +90 must be on the ledger

    # A decrease credits nothing and writes nothing.
    await set_monthly_grant(prj_w, MonthlyGrantBody(amount=Decimal("50")),
                            principal=admin, db=db)
    assert (await wallet_state(db, prj_w))[0] == Decimal("100.00")
    assert len(await ledger_rows(db, prj_w)) == 1

    # Bulk grant on member wallets: same rule.
    users = [await make_user(db) for _ in range(2)]
    member_ws = [await make_wallet(db, "5", owner_id=u) for u in users]
    await seed(db, [
        Membership(id=ids.new("membership"), user_id=u, group_id=prj, role="member")
        for u in users
    ])
    gadmin = Principal(user_id=await make_user(db), memberships={prj: "group_admin"})
    await bulk_monthly_grant(BulkMonthlyGrantBody(group_id=prj, amount=Decimal("25")),
                             principal=gadmin, db=db)
    for w in member_ws:
        assert (await wallet_state(db, w))[0] == Decimal("25.00")
        await check_ledger(db, w, Decimal("5"))


# ── 9 billing another user's or a group wallet ────────────────────────────────────────────
async def test_session_cannot_bill_another_users_or_a_group_wallet(db, fake_handoff):
    from app.api.schemas.session import SessionCreate
    from app.auth.rbac import Principal
    from app.domain.scheduler import SchedulerService

    refs = await make_refs(db, devices=1)
    _org, prj, _ = await _org_tree(db)
    my_w = await make_wallet(db, "1000", owner_id=refs.user_id)
    other_w = await make_wallet(db, "1000")
    group_w = await make_wallet(db, "1000", owner_type="group", owner_id=prj)
    principal = Principal(user_id=refs.user_id, memberships={prj: "group_admin"})
    svc = SchedulerService(db)
    svc.handoff = fake_handoff

    def _req(wallet_id: str) -> SessionCreate:
        return SessionCreate(offering_id=refs.offering_id, image_id=refs.image_id,
                             resource_class="gpu", cluster_id=refs.cluster_id, group_id=prj,
                             gpu_mem_mb=8000, gpu_cores=50, mode="fractional",
                             billing_wallet_id=wallet_id)

    for n, foreign in enumerate((other_w, group_w)):
        with pytest.raises(Forbidden):
            await svc.create_session(_req(foreign), principal, idem=f"foreign-{n}")
        await db.rollback()
        db.expunge_all()
        assert await wallet_state(db, foreign) == (Decimal("1000.00"), Decimal("0.00"))
        assert await ledger_rows(db, foreign) == []
    assert fake_handoff.last_spec is None

    # Own wallet: admitted, hold taken on MY wallet only.
    out = await svc.create_session(_req(my_w), principal, idem="mine")
    assert fake_handoff.last_spec is not None
    db.expunge_all()
    assert (await db.get(Session, out.id)).billing_wallet_id == my_w
    await db.commit()
    balance, reserved = await wallet_state(db, my_w)
    assert reserved > Decimal("0") and balance == Decimal("1000.00")
    assert await wallet_state(db, other_w) == (Decimal("1000.00"), Decimal("0.00"))
    assert await wallet_state(db, group_w) == (Decimal("1000.00"), Decimal("0.00"))
    await check_ledger(db, my_w, Decimal("1000"))


# ── 10 sigma constraint is enforced by the database, not only by the engine ───────────────
async def test_wallet_sigma_constraint_rejects_reserved_above_balance(db):
    if db.bind.dialect.name != "postgresql":
        pytest.skip("asserts the migrated Postgres schema; SQLite create_all is not the contract")
    wallet = await make_wallet(db, "10")
    with pytest.raises(IntegrityError):
        async with db.begin():
            row = await db.get(CreditWallet, wallet, with_for_update=True)
            row.reserved = Decimal("10.01")
    await db.rollback()
    with pytest.raises(IntegrityError):
        async with db.begin():
            row = await db.get(CreditWallet, wallet, with_for_update=True)
            row.balance = Decimal("-0.01")
    await db.rollback()
    assert (
        await db.scalar(select(CreditWallet.balance).where(CreditWallet.id == wallet))
    ) == Decimal("10.00")

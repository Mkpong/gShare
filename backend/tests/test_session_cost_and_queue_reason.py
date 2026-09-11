"""A session row carries what it actually cost and, while it waits, why it is still waiting.

Both figures are reconstructed at read time — the charge from the credit ledger, the reason from
the lifecycle log — so neither can drift away from the record it is derived from."""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.api.deps import Pagination
from app.api.sessions_router import list_sessions
from app.auth.rbac import Principal
from app.core import ids
from app.db.models import CreditTransaction, CreditWallet, Session, SessionEvent

OWNER = "usr_cost01"
P = Principal(user_id=OWNER, global_role="member", global_roles={"member"})


def _session(sid: str, status: str) -> Session:
    return Session(
        id=sid, owner_user_id=OWNER, cluster_id="clu_1", offering_id="off_1", image_id="img_1",
        resource_class="gpu", mode="fractional", gpu_mem_mb=8000, gpu_cores=50, status=status,
    )


async def _rows(db):
    page = await list_sessions(page=Pagination(page=1, size=50), status_filter=None, group_id=None,
                               cluster_id=None, scope="mine", principal=P, db=db)
    return {r.id: r for r in page["data"]}


@pytest.mark.asyncio
async def test_cost_is_the_sum_of_the_consume_rows(db):
    wallet = CreditWallet(id=ids.new("wallet"), owner_type="user", owner_id=OWNER,
                          balance=Decimal("100"), reserved=Decimal("0"))
    db.add_all([wallet, _session("ses_paid", "terminated"), _session("ses_free", "terminated")])
    # two billing ticks on one session, plus a hold and a refund that must NOT count as spend
    for i, (typ, amt) in enumerate(
        [("consume", "-3.50"), ("consume", "-1.25"), ("hold", "-10"), ("refund", "10")]
    ):
        db.add(CreditTransaction(id=ids.new("txn"), wallet_id=wallet.id, type=typ,
                                 amount=Decimal(amt), balance_after=Decimal("0"),
                                 ref="ses_paid", idempotency_key=f"k{i}"))
    await db.commit()

    rows = await _rows(db)
    assert rows["ses_paid"].credit_consumed == 4.75
    # a session that was never charged reports nothing, not a misleading zero
    assert rows["ses_free"].credit_consumed is None


@pytest.mark.asyncio
async def test_a_waiting_session_reports_its_latest_queue_reason(db):
    db.add_all([_session("ses_wait", "pending"), _session("ses_run", "running")])
    for i, (sid, kind, reason) in enumerate([
        ("ses_wait", "queued", "no_gpu_capacity"),
        ("ses_wait", "queued", "host_headroom"),   # the newer refusal wins
        ("ses_run", "queued", "no_gpu_capacity"),  # it got in; the reason is history
    ]):
        db.add(SessionEvent(id=f"sev_{i:03d}", session_id=sid, kind=kind, reason=reason))
    await db.commit()

    rows = await _rows(db)
    assert rows["ses_wait"].queued_reason == "host_headroom"
    assert rows["ses_run"].queued_reason is None


@pytest.mark.asyncio
async def test_the_queue_entry_carries_the_same_reason(db):
    """The queue screen and the dashboard read the reason from one place, so they agree."""
    from app.api.queue_router import _decorate

    db.add_all([
        _session("ses_q1", "pending"),
        SessionEvent(id="sev_q0", session_id="ses_q1", kind="queued", reason="no_gpu_capacity"),
        SessionEvent(id="sev_q1", session_id="ses_q1", kind="queued", reason="host_headroom"),
    ])
    await db.commit()

    out = await _decorate(db, [{"session_id": "ses_q1"}, {"session_id": "ses_none"}])
    assert out[0]["reason"] == "host_headroom"
    assert out[1]["reason"] is None

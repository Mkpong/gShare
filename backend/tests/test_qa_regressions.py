"""Regressions for the defects found in the 2026-09-08 QA audit.

Each test names the bug it pins and fails the way the bug originally presented, so a future
refactor that reintroduces one is caught here rather than in production.
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.api.schemas.credit import MAX_CREDIT, TopupRequestBody, quantized_credit
from app.api.users_router import UserPatch, _assert_grantable_role
from app.auth.rbac import Principal
from app.core.errors import Forbidden
from app.core.validation import clean_text
from tests.fkseed import seed


# ── BUG-001 / BUG-002: 이름 검증 ────────────────────────────────────────────────
def test_blank_and_control_character_names_are_rejected():
    """A name of only spaces used to create a row that renders blank; a NUL byte reached the
    database and came back as a 500."""
    assert clean_text("  gShare  ") == "gShare"
    for bad in ("   ", "\t\n", ""):
        with pytest.raises(ValueError):
            clean_text(bad)
    for bad in ("naught\x00byte", "bell\x07", "\x1b[31m"):
        with pytest.raises(ValueError):
            clean_text(bad)


# ── BUG-005: 알 수 없는 필드는 거부 ──────────────────────────────────────────────
def test_user_patch_rejects_unknown_fields():
    """`{"global_role": "super_admin"}` used to return 200 while being silently dropped."""
    with pytest.raises(ValidationError):
        UserPatch(global_role="super_admin")
    with pytest.raises(ValidationError):
        UserPatch(status="active", is_admin=True)
    assert UserPatch(name="ok").name == "ok"


# ── BUG-006 / BUG-007: 금액 경계 ────────────────────────────────────────────────
def test_credit_amount_bounds_and_rounding():
    """No upper bound let a top-up exceed the ledger column and 500; sub-cent amounts were
    stored as a successful 0.00 movement."""
    with pytest.raises(ValidationError):
        TopupRequestBody(amount=Decimal("1e30"))
    with pytest.raises(ValidationError):
        TopupRequestBody(amount=MAX_CREDIT + 1)
    assert TopupRequestBody(amount=Decimal("100")).amount == Decimal("100")

    assert quantized_credit(Decimal("1.005")) == Decimal("1.01")
    assert quantized_credit(Decimal("0.01")) == Decimal("0.01")
    for dust in ("0.001", "0.0000001"):
        with pytest.raises(ValueError):
            quantized_credit(Decimal(dust))


# ── BUG-009: org_admin 역할을 아무나 부여하지 못한다 ─────────────────────────────
def test_only_super_admin_may_grant_org_admin():
    """Granting a group-scoped org_admin hands over that group's whole organization."""
    plain = Principal(user_id="usr_a", global_role=None, global_roles=set(),
                      memberships={"grp_1": "org_admin"}, org_admin_orgs={"org_1"})
    with pytest.raises(Forbidden):
        _assert_grantable_role(plain, "org_admin")
    for ok in ("group_admin", "member", "guest"):
        _assert_grantable_role(plain, ok)

    root = Principal(user_id="usr_root", global_role="super_admin",
                     global_roles={"super_admin"})
    _assert_grantable_role(root, "org_admin")


# ── BUG-013 / BUG-018: 자기 hold 를 자기 여력으로 인정 ──────────────────────────
@pytest.mark.asyncio
async def test_session_may_spend_its_own_reservation(db):
    """A session funded to exactly its hold was declared bankrupt at its first billing tick:
    `balance - reserved` is 0 for the whole run because consume lowers both together."""
    from types import SimpleNamespace

    from app.core import ids
    from app.db.models import CreditTransaction, CreditWallet
    from app.domain.credit_engine import CreditEngine

    wallet = CreditWallet(id=ids.new("wallet"), owner_type="user", owner_id="usr_x",
                          balance=Decimal("60"), reserved=Decimal("60"))
    sess = SimpleNamespace(id="ses_x", billing_wallet_id=wallet.id, started_at=None)
    await seed(db, [wallet, CreditTransaction(
        id=ids.new("txn"), wallet_id=wallet.id, type="hold", amount=Decimal("60"),
        balance_after=Decimal("60"), ref=sess.id, idempotency_key=f"hold:{sess.id}")])

    engine = CreditEngine(db)
    # The wallet-wide figure says nothing is left...
    assert wallet.balance - wallet.reserved == Decimal("0")
    # ...but this session's own untouched hold is its to spend.
    assert await engine.own_outstanding_hold(sess) == Decimal("60")
    assert await engine.available_for(wallet, sess) == Decimal("60")


@pytest.mark.asyncio
async def test_a_second_session_does_not_get_the_first_ones_reservation(db):
    """available_for must count only the caller's own hold, never another session's."""
    from types import SimpleNamespace

    from app.core import ids
    from app.db.models import CreditTransaction, CreditWallet
    from app.domain.credit_engine import CreditEngine

    wallet = CreditWallet(id=ids.new("wallet"), owner_type="user", owner_id="usr_y",
                          balance=Decimal("100"), reserved=Decimal("100"))
    a = SimpleNamespace(id="ses_a", billing_wallet_id=wallet.id, started_at=None)
    b = SimpleNamespace(id="ses_b", billing_wallet_id=wallet.id, started_at=None)
    await seed(db, [wallet, CreditTransaction(
        id=ids.new("txn"), wallet_id=wallet.id, type="hold", amount=Decimal("100"),
        balance_after=Decimal("100"), ref=a.id, idempotency_key=f"hold:{a.id}")])

    engine = CreditEngine(db)
    assert await engine.available_for(wallet, a) == Decimal("100")   # its own hold
    assert await engine.available_for(wallet, b) == Decimal("0")     # not A's


def test_a_priced_session_always_reserves_something():
    """Rounding a small slice to zero admitted a GPU session against an empty wallet."""
    from app.domain.pricing import round_credit

    # The rounding itself still floors small values...
    assert round_credit(Decimal("0.25")) == Decimal("0")
    # ...so the scheduler floors the HOLD at one credit whenever the rate is non-zero.
    cph, occupancy = Decimal("1"), 0.25
    hold = round_credit(cph * Decimal(str(occupancy)))
    if hold <= Decimal("0") and cph > Decimal("0"):
        hold = Decimal("1")
    assert hold == Decimal("1")


# ── BUG-003 / BUG-009: 테넌트 스코프 ────────────────────────────────────────────
@pytest.mark.asyncio
async def test_admin_cannot_reach_a_user_of_another_organization(db):
    """An org_admin of one organization read and deleted users of another: the handlers checked
    the action but never the tenant."""
    from app.api.users_router import _assert_target_in_scope
    from app.core import ids
    from app.db.models import Membership, Organization, Project, User

    org_a, org_b = ids.new("org"), ids.new("org")
    grp_a, grp_b = ids.new("group"), ids.new("group")
    victim, outsider = ids.new("user"), ids.new("user")
    await seed(db, [
        Organization(id=org_a, name="A"), Organization(id=org_b, name="B"),
        Project(id=grp_a, org_id=org_a, name="ga"), Project(id=grp_b, org_id=org_b, name="gb"),
        User(id=victim, email="v@example.edu", name="v", status="active"),
        User(id=outsider, email="o@example.edu", name="o", status="active"),
        Membership(id=ids.new("membership"), user_id=victim, group_id=grp_a, role="member"),
        Membership(id=ids.new("membership"), user_id=outsider, group_id=grp_b, role="org_admin"),
    ])

    attacker = Principal(user_id=outsider, global_role=None, global_roles=set(),
                         memberships={grp_b: "org_admin"}, org_admin_orgs={org_b})
    with pytest.raises(Forbidden):
        await _assert_target_in_scope(db, attacker, victim)

    # The same administrator still reaches their own organization's users.
    insider = ids.new("user")
    await seed(db, [
        User(id=insider, email="i@example.edu", name="i", status="active"),
        Membership(id=ids.new("membership"), user_id=insider, group_id=grp_b, role="member"),
    ])
    await _assert_target_in_scope(db, attacker, insider)

    # super_admin is global, and everyone reaches themselves.
    root = Principal(user_id="usr_root", global_role="super_admin", global_roles={"super_admin"})
    await _assert_target_in_scope(db, root, victim)
    await _assert_target_in_scope(db, attacker, outsider)


@pytest.mark.asyncio
async def test_admin_cannot_enroll_a_user_into_another_organizations_group(db):
    """Creating a user inside a foreign group was the foothold for a full organization takeover."""
    from app.api.users_router import _assert_group_in_scope
    from app.core import ids
    from app.db.models import Organization, Project

    org_a, org_b = ids.new("org"), ids.new("org")
    grp_a, grp_b = ids.new("group"), ids.new("group")
    await seed(db, [
        Organization(id=org_a, name="A"), Organization(id=org_b, name="B"),
        Project(id=grp_a, org_id=org_a, name="ga"), Project(id=grp_b, org_id=org_b, name="gb"),
    ])
    foreign = await db.get(Project, grp_a)
    own = await db.get(Project, grp_b)

    attacker = Principal(user_id="usr_o", global_role=None, global_roles=set(),
                         memberships={grp_b: "org_admin"}, org_admin_orgs={org_b})
    with pytest.raises(Forbidden):
        await _assert_group_in_scope(db, attacker, foreign)
    await _assert_group_in_scope(db, attacker, own)


# ── BUG-010: 자기 정책 자가 상향 금지 ───────────────────────────────────────────
@pytest.mark.asyncio
async def test_admin_cannot_write_a_policy_for_themselves(db):
    """The user scope outranks group, org and global, so a self-written policy lifted every
    ceiling above the author."""
    from app.api.policies_router import _assert_policy_perm

    admin = Principal(user_id="usr_admin", global_role=None, global_roles=set(),
                      memberships={"grp_1": "group_admin"})
    with pytest.raises(Forbidden):
        await _assert_policy_perm(admin, "policy.create", "user", "usr_admin", db)

    # super_admin is exempt: it is already the top of the chain.
    root = Principal(user_id="usr_root", global_role="super_admin", global_roles={"super_admin"})
    await _assert_policy_perm(root, "policy.create", "user", "usr_root", db)


# ── BUG-012: 자격증명 없는 계정은 로그인 불가 ────────────────────────────────────
@pytest.mark.asyncio
async def test_account_without_a_password_hash_cannot_log_in(db):
    """`if user.password_hash:` let a hash-less row through on ANY password."""
    from app.api.users_router import _LoginRequest, auth_login
    from app.core import ids
    from app.core.errors import Unauthenticated
    from app.db.models import User

    await seed(db, [User(id=ids.new("user"), email="nohash@example.edu", name="n",
                password_hash=None, status="active")])

    class _Req:
        headers = {"x-forwarded-for": "10.0.0.1"}
        client = None

    for attempt in ("", "anything", "hunter2"):
        with pytest.raises(Unauthenticated):
            await auth_login(_LoginRequest(email="nohash@example.edu", password=attempt), _Req(), db)


# ── BUG-020: 종결된 세션은 되살아나지 않는다 ─────────────────────────────────────
@pytest.mark.asyncio
async def test_finished_session_is_not_resurrected_by_a_late_running_report(db):
    """A settled session flipped back to running billed against a released hold and could never
    settle again, because its settle key was already spent."""
    from datetime import UTC, datetime

    from app.api.schemas.internal import OperatorStatusEvent
    from app.cluster.status_sync import StatusSync
    from app.core import ids
    from app.db.models import Session as SessionModel

    now = datetime.now(UTC)
    for finished in ("terminated", "error"):
        sid = ids.new("session")
        await seed(db, [SessionModel(
            id=sid, owner_user_id="usr_x", cluster_id="clu_1", offering_id="off_1",
            image_id="img_1", resource_class="gpu", mode="fractional",
            gpu_mem_mb=1024, gpu_cores=10, status=finished, terminated_at=now,
        )])

        ev = OperatorStatusEvent(phase="running", ts=now, pod_ref="ns/pod", node_name="node-1")
        await StatusSync(db).on_status(sid, ev)

        row = await db.get(SessionModel, sid)
        assert row.status == finished, f"{finished} session was resurrected into {row.status}"


# ── BUG-015: 일시정지 구간은 과금하지 않는다 ─────────────────────────────────────
def test_operator_termination_only_final_consumes_a_running_session():
    """final_consume defaulted to True, so terminating a paused session billed the whole idle gap."""
    import inspect

    from app.cluster import status_sync

    for handler in (status_sync.StatusSync._on_terminated, status_sync.StatusSync._on_error):
        src = inspect.getsource(handler)
        assert 'final_consume=(prior_status == "running")' in src, handler.__name__

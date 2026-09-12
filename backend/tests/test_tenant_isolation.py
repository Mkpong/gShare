"""Regression tests for cross-tenant read isolation on list/get/report endpoints.

These three endpoints previously called the unscoped guard ``principal.require(action=...)``
(group_id=None), which passes for ANY membership of sufficient rank — so a member/admin of one
tenant could enumerate or read every other tenant's resource policies, budgets, and billing
financials. Each test asserts a non-super admin of org/group A sees only A and is denied B.
"""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.api.budgets_router import list_budgets
from app.api.deps import Pagination
from app.api.infra_router import billing_report
from app.api.policies_router import get_policy, list_policies
from app.auth.rbac import Principal
from app.core.errors import Forbidden
from app.db.models import Budget, CreditWallet, ResourcePolicy
from tests.fkseed import add_ordered, seed

pytestmark = pytest.mark.asyncio


def _org_admin(org_id: str, user_id: str = "u_admin") -> Principal:
    return Principal(user_id=user_id, global_roles=set(), org_admin_orgs={org_id})


def _group_admin(group_id: str, user_id: str = "u_gadmin") -> Principal:
    return Principal(user_id=user_id, global_roles=set(), memberships={group_id: "group_admin"})


def _super() -> Principal:
    return Principal(user_id="u_super", global_roles={"super_admin"})


# --------------------------------------------------------------------------- policies

async def _seed_policies(db) -> None:
    await seed(db, [
        ResourcePolicy(id="pol_orgA", scope="org", scope_id="org_A", max_concurrent=1, limits={}),
        ResourcePolicy(id="pol_orgB", scope="org", scope_id="org_B", max_concurrent=1, limits={}),
        ResourcePolicy(id="pol_grpA", scope="group", scope_id="grp_A", max_concurrent=1, limits={}),
        ResourcePolicy(id="pol_grpB", scope="group", scope_id="grp_B", max_concurrent=1, limits={}),
        ResourcePolicy(id="pol_global", scope="global", scope_id="*", max_concurrent=1, limits={}),
        ResourcePolicy(id="pol_user", scope="user", scope_id="u_x", max_concurrent=1, limits={}),
    ])
    await db.flush()


async def test_list_policies_org_admin_scoped(db):
    await _seed_policies(db)
    res = await list_policies(page=Pagination(1, 50), scope=None, scope_id=None, principal=_org_admin("org_A"), db=db)
    ids = {r["id"] for r in res["data"]}
    assert ids == {"pol_orgA"}, ids
    assert res["pagination"]["total"] == 1


async def test_list_policies_group_admin_scoped(db):
    await _seed_policies(db)
    res = await list_policies(page=Pagination(1, 50), scope=None, scope_id=None, principal=_group_admin("grp_A"), db=db)
    ids = {r["id"] for r in res["data"]}
    assert ids == {"pol_grpA"}, ids


async def test_list_policies_super_sees_all(db):
    await _seed_policies(db)
    res = await list_policies(page=Pagination(1, 50), scope=None, scope_id=None, principal=_super(), db=db)
    assert len(res["data"]) == 6


async def test_get_policy_cross_tenant_denied(db):
    await _seed_policies(db)
    # org_A admin may read its own org policy ...
    own = await get_policy("pol_orgA", principal=_org_admin("org_A"), db=db)
    assert own["id"] == "pol_orgA"
    # ... but is forbidden the other tenant's policy (previously leaked).
    with pytest.raises(Forbidden):
        await get_policy("pol_orgB", principal=_org_admin("org_A"), db=db)
    # ... and global/user-scoped policies are super_admin only.
    with pytest.raises(Forbidden):
        await get_policy("pol_global", principal=_org_admin("org_A"), db=db)


# --------------------------------------------------------------------------- budgets

async def _seed_budgets(db) -> None:
    ps = datetime(2026, 6, 1, tzinfo=UTC)
    db.add_all([
        Budget(id="bdg_orgA", scope="org", scope_id="org_A", period_start=ps, limit_credit=Decimal(100)),
        Budget(id="bdg_orgB", scope="org", scope_id="org_B", period_start=ps, limit_credit=Decimal(100)),
        Budget(id="bdg_grpA", scope="group", scope_id="grp_A", period_start=ps, limit_credit=Decimal(100)),
        Budget(id="bdg_grpB", scope="group", scope_id="grp_B", period_start=ps, limit_credit=Decimal(100)),
    ])
    await db.flush()


async def test_list_budgets_org_admin_scoped(db):
    await _seed_budgets(db)
    rows = await list_budgets(page=Pagination(1, 50), scope=None, scope_id=None, action=None, principal=_org_admin("org_A"), db=db)
    assert {r.id for r in rows} == {"bdg_orgA"}


async def test_list_budgets_group_admin_scoped(db):
    await _seed_budgets(db)
    # group_admin of grp_A — list requires group_admin (matrix); sees only grp_A budget.
    rows = await list_budgets(page=Pagination(1, 50), scope=None, scope_id=None, action=None, principal=_group_admin("grp_A"), db=db)
    assert {r.id for r in rows} == {"bdg_grpA"}


async def test_list_budgets_super_sees_all(db):
    await _seed_budgets(db)
    rows = await list_budgets(page=Pagination(1, 50), scope=None, scope_id=None, action=None, principal=_super(), db=db)
    assert len(rows) == 4


# --------------------------------------------------------------------------- billing report

async def _seed_wallets(db) -> None:
    db.add_all([
        CreditWallet(id="wal_orgA", owner_type="org", owner_id="org_A", balance=Decimal(0)),
        CreditWallet(id="wal_orgB", owner_type="org", owner_id="org_B", balance=Decimal(0)),
        CreditWallet(id="wal_grpB", owner_type="group", owner_id="grp_B", balance=Decimal(0)),
    ])
    await db.flush()


def _window():
    frm = datetime(2026, 6, 1, tzinfo=UTC)
    to = datetime(2026, 6, 30, tzinfo=UTC)
    return frm, to


async def _report(db, principal, scope, scope_id):
    frm, to = _window()
    return await billing_report(
        scope=scope, scope_id=scope_id, from_=frm, to=to,
        group_by="group", format="json", principal=principal, db=db,
    )


async def test_billing_report_own_org_allowed(db):
    await _seed_wallets(db)
    rep = await _report(db, _org_admin("org_A"), "org", "org_A")
    assert rep is not None


async def test_billing_report_cross_org_denied(db):
    await _seed_wallets(db)
    with pytest.raises(Forbidden):
        await _report(db, _org_admin("org_A"), "org", "org_B")


async def test_billing_report_cross_group_denied(db):
    await _seed_wallets(db)
    with pytest.raises(Forbidden):
        await _report(db, _group_admin("grp_A"), "group", "grp_B")


async def test_billing_report_wallet_owner_authorized(db):
    await _seed_wallets(db)
    # org_A admin may pull its own org wallet ...
    assert await _report(db, _org_admin("org_A"), "wallet", "wal_orgA") is not None
    # ... but not another tenant's wallet (previously leaked financials).
    with pytest.raises(Forbidden):
        await _report(db, _org_admin("org_A"), "wallet", "wal_grpB")


async def test_billing_report_no_scope_id_super_only(db):
    await _seed_wallets(db)
    # whole-platform aggregate must be super_admin only.
    with pytest.raises(Forbidden):
        await _report(db, _org_admin("org_A"), "org", None)
    # super_admin is unrestricted.
    assert await _report(db, _super(), "org", None) is not None


# --------------------------------------------------------------------------- node pools

async def test_dedicated_pool_cards_invisible_to_other_org_in_placement(db):
    """Org B never places on (or even counts) the cards an admin dedicated to org A."""
    from app.db.models import GpuDevice, GpuNode, NodePool, NodePoolGrant, Project
    from app.domain.node_pools import resolve_pool_access

    cluster_id = "clu_pool"
    pool = NodePool(id="npl_A", cluster_id=cluster_id, name="A-only", kind="dedicated")
    await add_ordered(db, [
        Project(id="grp_A2", org_id="org_A", name="A2"),
        Project(id="grp_B2", org_id="org_B", name="B2"),
        pool,
        NodePoolGrant(id="pgr_A", pool_id=pool.id, scope="org", scope_id="org_A"),
        GpuNode(id="nod_A", cluster_id=cluster_id, hostname="a", status="ready", pool_id=pool.id),
        GpuDevice(id="dev_A", node_id="nod_A", cluster_id=cluster_id, model="A100",
                  gpu_uuid="GPU-A", total_mem_mb=16000, status="ready", mode="fractional"),
    ])
    access_b = await resolve_pool_access(db, cluster_id=cluster_id, user_id="u_b", group_id="grp_B2")
    assert pool.id not in access_b.allowed()
    assert access_b.allowed() == {None}
    access_a = await resolve_pool_access(db, cluster_id=cluster_id, user_id="u_a", group_id="grp_A2")
    assert access_a.tier_of(pool.id) == 0


async def test_list_node_pools_hides_other_tenants_grants(db):
    """A pool granted to both A and B: A's org_admin sees the pool but only A's grants."""
    from app.api.infra_router import list_node_pools
    from app.db.models import Cluster, NodePool, NodePoolGrant, Organization, Project

    db.add_all([
        Cluster(id="clu_share", name="c", api_server="https://x", runtime="k8s", kubeconfig_secret_ref="s"),
        Organization(id="org_A", name="A"),
        Organization(id="org_B", name="B"),
        Project(id="grp_A3", org_id="org_A", name="A3"),
        Project(id="grp_B3", org_id="org_B", name="B3"),
        NodePool(id="npl_S", cluster_id="clu_share", name="shared-by-two", kind="dedicated"),
        NodePoolGrant(id="pgr_oA", pool_id="npl_S", scope="org", scope_id="org_A"),
        NodePoolGrant(id="pgr_oB", pool_id="npl_S", scope="org", scope_id="org_B"),
        NodePoolGrant(id="pgr_gA", pool_id="npl_S", scope="group", scope_id="grp_A3"),
        NodePoolGrant(id="pgr_gB", pool_id="npl_S", scope="group", scope_id="grp_B3"),
    ])
    await db.flush()
    res = await list_node_pools(cluster_id="clu_share", principal=_org_admin("org_A"), db=db)
    assert res["total"] == 1
    seen = {(g["scope"], g["scope_id"]) for g in res["data"][0]["grants"]}
    assert seen == {("org", "org_A"), ("group", "grp_A3")}
    names = {g["name"] for g in res["data"][0]["grants"]}
    assert "B" not in names and "B3" not in names
    # super_admin still sees every grant.
    res = await list_node_pools(cluster_id="clu_share", principal=_super(), db=db)
    assert len(res["data"][0]["grants"]) == 4


async def test_policy_shared_pool_limit_round_trips(db):
    """limits.shared_pool survives create, PATCH and GET (the console's fallback switch)."""
    from app.api.policies_router import PolicyCreate, PolicyUpdate, create_policy, update_policy

    body = PolicyCreate(
        scope="org", scope_id="org_A", max_concurrent=1, max_queued=1, max_runtime_min=60,
        idle_timeout_sec=600, limits={"cpu": 4, "shared_pool": False},
    )
    created = await create_policy(body, principal=_super(), db=db)
    assert created["limits"]["shared_pool"] is False
    got = await get_policy(created["id"], principal=_org_admin("org_A"), db=db)
    assert got["limits"] == {"cpu": 4, "shared_pool": False}
    upd = await update_policy(
        created["id"], PolicyUpdate(limits={"shared_pool": True}), principal=_super(), db=db
    )
    assert upd["limits"] == {"cpu": 4, "shared_pool": True}
    upd = await update_policy(
        created["id"], PolicyUpdate(limits={"shared_pool": False}), principal=_super(), db=db
    )
    assert upd["limits"]["shared_pool"] is False


# --------------------------------------------------------------------------- queue (beta: GS-B01/02)
#
# ``queue.read``/``queue.update`` are rank checks ("are you a group_admin anywhere"); the queue
# handlers must still narrow to the sessions whose OWNER the caller manages, and a session created
# without a group must not fall through the per-group check as if nobody owned it.

def _session_row(owner: str, group_id: str | None = None):
    from app.core import ids
    from app.db.models import Session as SessionRow

    return SessionRow(
        id=ids.new("session"), owner_user_id=owner, group_id=group_id, cluster_id="clu_t",
        offering_id="off_t", image_id="img_t", resource_class="gpu", mode="fractional",
        status="pending", gpu_mem_mb=1024, gpu_cores=10,
    )


async def _seed_queue_world(db):
    from app.core import ids
    from app.db.models import Membership, Organization, Project, QueueEntry, User

    org_a, org_b = "org_QA", "org_QB"
    grp_a, grp_b = "grp_QA", "grp_QB"
    user_a, user_b = "u_qa", "u_qb"
    s_a = _session_row(user_a, grp_a)
    s_b_grouped = _session_row(user_b, grp_b)
    s_b_ungrouped = _session_row(user_b, None)      # the API accepts a session without a group
    # committed, not just flushed: the monitor-SSE test reads this world through a second
    # session, which on Postgres is a different connection.
    await seed(db, [
        Organization(id=org_a, name="A"), Organization(id=org_b, name="B"),
        Project(id=grp_a, org_id=org_a, name="a"), Project(id=grp_b, org_id=org_b, name="b"),
        User(id=user_a, email="qa@x", name="qa"), User(id=user_b, email="qb@x", name="qb"),
        Membership(id=ids.new("membership"), user_id=user_a, group_id=grp_a, role="member"),
        Membership(id=ids.new("membership"), user_id=user_b, group_id=grp_b, role="member"),
        s_a, s_b_grouped, s_b_ungrouped,
    ])
    entries = {}
    for s in (s_a, s_b_grouped, s_b_ungrouped):
        e = QueueEntry(id=ids.new("queue"), session_id=s.id, session_req={"group_id": s.group_id})
        entries[s.id] = e
    await seed(db, list(entries.values()))
    return {"grp_a": grp_a, "grp_b": grp_b, "org_a": org_a, "s_a": s_a,
            "s_b": s_b_grouped, "s_b_ungrouped": s_b_ungrouped, "entries": entries}


async def test_list_queue_group_admin_sees_only_managed_sessions(db):
    from app.api.queue_router import list_queue

    w = await _seed_queue_world(db)
    res = await list_queue(page=Pagination(1, 50), group_id=None, cluster_id=None,
                           principal=_group_admin(w["grp_a"]), db=db)
    sids = {r["session_id"] for r in res["data"]}
    assert sids == {w["s_a"].id}, sids
    assert res["pagination"]["total"] == 1


async def test_list_queue_org_admin_sees_only_own_org(db):
    from app.api.queue_router import list_queue

    w = await _seed_queue_world(db)
    p = Principal(user_id="u_oa", org_admin_orgs={w["org_a"]}, memberships={w["grp_a"]: "org_admin"})
    res = await list_queue(page=Pagination(1, 50), group_id=None, cluster_id=None, principal=p, db=db)
    assert {r["session_id"] for r in res["data"]} == {w["s_a"].id}


async def test_list_queue_super_sees_all(db):
    from app.api.queue_router import list_queue

    await _seed_queue_world(db)
    res = await list_queue(page=Pagination(1, 50), group_id=None, cluster_id=None,
                           principal=_super(), db=db)
    assert len(res["data"]) == 3


async def test_cancel_queue_entry_cross_tenant_denied(db):
    from app.api.queue_router import cancel_queue_entry

    w = await _seed_queue_world(db)
    ga = _group_admin(w["grp_a"])
    # Grouped session of the other tenant: the per-group check already refuses it.
    with pytest.raises(Forbidden):
        await cancel_queue_entry(w["entries"][w["s_b"].id].id, principal=ga, db=db)
    # Ungrouped session of the other tenant: previously slipped through (group_id=None check).
    with pytest.raises(Forbidden):
        await cancel_queue_entry(w["entries"][w["s_b_ungrouped"].id].id, principal=ga, db=db)
    assert w["s_b_ungrouped"].status == "pending"


async def test_update_priority_cross_tenant_denied(db):
    from app.api.queue_router import QueuePriorityPatch, update_priority

    w = await _seed_queue_world(db)
    ga = _group_admin(w["grp_a"])
    with pytest.raises(Forbidden):
        await update_priority(w["entries"][w["s_b_ungrouped"].id].id, QueuePriorityPatch(priority=5),
                              principal=ga, db=db)
    assert w["entries"][w["s_b_ungrouped"].id].priority == 0
    # The administrator's own tenant still works.
    out = await update_priority(w["entries"][w["s_a"].id].id, QueuePriorityPatch(priority=5),
                                principal=ga, db=db)
    assert out["priority"] == 5


# --------------------------------------------------------------------------- memberships (beta: GS-B04)
#
# Adding a user to a group hands the group's administrators authority over that user (password
# reset, suspension, soft delete, wallet grants). A non-super administrator must therefore only be
# able to enroll people who are already in their tenant, or who belong to no tenant yet.

async def _seed_membership_world(db):
    from app.core import ids
    from app.db.models import Membership, Organization, Project, User

    await add_ordered(db, [
        Organization(id="org_MA", name="A"), Organization(id="org_MB", name="B"),
        Project(id="grp_MA", org_id="org_MA", name="a"), Project(id="grp_MB", org_id="org_MB", name="b"),
        User(id="u_victim_b", email="vb@x", name="vb"),
        User(id="u_fresh", email="fresh@x", name="fresh"),
        Membership(id=ids.new("membership"), user_id="u_victim_b", group_id="grp_MB", role="member"),
    ])


async def test_add_membership_cannot_pull_in_foreign_org_user(db):
    from app.api.groups_router import MembershipCreate, add_membership

    await _seed_membership_world(db)
    ga = _group_admin("grp_MA")
    with pytest.raises(Forbidden):
        await add_membership("grp_MA", MembershipCreate(user_id="u_victim_b", role="member"),
                             principal=ga, db=db)
    # An unaffiliated user can still be enrolled by a group_admin.
    out = await add_membership("grp_MA", MembershipCreate(user_id="u_fresh", role="member"),
                               principal=ga, db=db)
    assert out["user_id"] == "u_fresh"


async def test_set_department_cannot_pull_in_foreign_org_user(db):
    from app.api.users_router import UserDepartmentSet, set_user_department
    from app.db.models import Membership

    await _seed_membership_world(db)
    oa = Principal(user_id="u_oa", org_admin_orgs={"org_MA"}, memberships={"grp_MA": "org_admin"})
    with pytest.raises(Forbidden):
        await set_user_department("u_victim_b", UserDepartmentSet(group_id="grp_MA"), principal=oa, db=db)
    rows = (await db.scalars(select(Membership.group_id).where(Membership.user_id == "u_victim_b"))).all()
    assert list(rows) == ["grp_MB"]
    # A super_admin may move anyone; an unaffiliated user may be placed by the org_admin.
    out = await set_user_department("u_fresh", UserDepartmentSet(group_id="grp_MA"), principal=oa, db=db)
    assert out["department_changed"] is True


# --------------------------------------------------------------------------- images (beta: GS-B05)

async def _seed_images(db):
    from app.db.models import Image

    db.add_all([
        Image(id="img_pub", name="pub", registry="r/pub", kind="container", public=True),
        Image(id="img_mine", name="mine", registry="r/mine", kind="container", public=False,
              owner_user_id="u_me"),
        Image(id="img_other", name="other", registry="r/other-secret", kind="container", public=False,
              owner_user_id="u_other"),
        Image(id="img_admin_private", name="retired", registry="r/retired", kind="container",
              public=False),
    ])
    await db.flush()


async def test_list_images_member_never_sees_other_users_private_images(db):
    from app.api.images_router import list_images

    await _seed_images(db)
    me = Principal(user_id="u_me", memberships={"grp_X": "member"})
    for public in (None, False, True):
        res = await list_images(pagination=Pagination(1, 50), kind=None, q=None, tag=None,
                                public=public, mine=False, principal=me, db=db)
        ids_ = {r["id"] for r in res["data"]}
        assert "img_other" not in ids_, (public, ids_)
        assert "img_admin_private" not in ids_, (public, ids_)
    res = await list_images(pagination=Pagination(1, 50), kind=None, q=None, tag=None,
                            public=None, mine=False, principal=me, db=db)
    assert {r["id"] for r in res["data"]} == {"img_pub", "img_mine"}
    # super_admin catalogue view is unchanged.
    res = await list_images(pagination=Pagination(1, 50), kind=None, q=None, tag=None,
                            public=None, mine=False, principal=_super(), db=db)
    assert len(res["data"]) == 4


async def test_get_image_other_users_private_image_denied(db):
    from app.api.images_router import get_image
    from app.core.errors import NotFound

    await _seed_images(db)
    me = Principal(user_id="u_me", memberships={"grp_X": "member"})
    assert (await get_image("img_mine", principal=me, db=db))["id"] == "img_mine"
    assert (await get_image("img_pub", principal=me, db=db))["id"] == "img_pub"
    with pytest.raises((Forbidden, NotFound)):
        await get_image("img_other", principal=me, db=db)
    with pytest.raises((Forbidden, NotFound)):
        await get_image("img_admin_private", principal=me, db=db)
    assert (await get_image("img_other", principal=_super(), db=db))["id"] == "img_other"


# --------------------------------------------------------------------------- storage quota (beta: GS-B06)

async def test_storage_quota_usage_cross_scope_denied(db):
    from app.api.volumes_router import storage_quota_usage
    from app.db.models import StorageVolume

    db.add_all([
        ResourcePolicy(id="pol_u_other", scope="user", scope_id="u_other", max_concurrent=1,
                       limits={"volume_gb": 500}),
        StorageVolume(id="vol_other", scope="user", scope_id="u_other", type="workspace",
                      name="w", access_mode="RWX", owner_id="u_other", quota_gb=123, used_gb=0),
    ])
    await db.flush()
    me = Principal(user_id="u_me", memberships={"grp_A": "member"})
    # Own scope and a group the caller belongs to are fine.
    assert "allocated_gb" in await storage_quota_usage(scope="user", scope_id="u_me", principal=me, db=db)
    assert "allocated_gb" in await storage_quota_usage(scope="group", scope_id="grp_A", principal=me, db=db)
    # Another user's / another group's quota and usage are not.
    with pytest.raises(Forbidden):
        await storage_quota_usage(scope="user", scope_id="u_other", principal=me, db=db)
    with pytest.raises(Forbidden):
        await storage_quota_usage(scope="group", scope_id="grp_B", principal=me, db=db)
    # super_admin is unrestricted.
    out = await storage_quota_usage(scope="user", scope_id="u_other", principal=_super(), db=db)
    assert out["allocated_gb"] == 123


# --------------------------------------------------------------------------- monitor SSE (beta: GS-B03)
#
# The admin monitor stream subscribes to session:events:* for the whole fleet; every event has to
# pass the same owner predicate as the monitoring list before it reaches a non-super administrator.

class _FakeRequest:
    def __init__(self, disconnect_after: int = 3):
        self._n = disconnect_after

    async def is_disconnected(self) -> bool:
        self._n -= 1
        return self._n < 0


async def test_monitor_event_filter_hides_other_tenants_sessions(db, monkeypatch):
    import json

    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.api import sessions_router as sr

    w = await _seed_queue_world(db)
    monkeypatch.setattr(sr, "get_sessionmaker", lambda: async_sessionmaker(db.bind, expire_on_commit=False))

    # super_admin: no gate at all.
    assert sr._monitor_event_filter(_super()) is None

    allow = sr._monitor_event_filter(_group_admin(w["grp_a"]))
    assert allow is not None
    assert await allow({"channel": f"session:events:{w['s_a'].id}", "data": "{}"}) is True
    assert await allow({"channel": f"session:events:{w['s_b'].id}", "data": "{}"}) is False
    assert await allow({"channel": f"session:events:{w['s_b_ungrouped'].id}", "data": "{}"}) is False
    assert await allow({"channel": "queue:events", "data": json.dumps({"kind": "enqueued", "session_id": w["s_a"].id})}) is True
    assert await allow({"channel": "queue:events", "data": json.dumps({"kind": "enqueued", "session_id": w["s_b"].id})}) is False
    assert await allow({"channel": "queue:events", "data": "not json"}) is False


async def test_sse_events_drops_events_the_gate_refuses(fake_redis, monkeypatch):
    from app.api import sessions_router as sr

    monkeypatch.setattr(sr, "_HEARTBEAT_SEC", 0.05)
    seen: list[str] = []

    async def allow(msg: dict) -> bool:
        seen.append(msg["channel"])
        return msg["channel"].endswith(":ok")

    gen = sr._sse_events(["queue:events"], ["session:events:*"], _FakeRequest(disconnect_after=6), allow=allow)
    first = await anext(gen)                      # subscribes, then heartbeats
    assert first["event"] == "heartbeat"
    await fake_redis.publish("session:events:ok", '{"phase":"running"}')
    await fake_redis.publish("session:events:hidden", '{"phase":"running"}')
    await fake_redis.publish("queue:events", '{"kind":"enqueued","session_id":"x"}')
    got = []
    async for ev in gen:
        if ev["event"] != "heartbeat":
            got.append(ev["data"])
    assert got == ['{"phase":"running"}']
    assert set(seen) == {"session:events:ok", "session:events:hidden", "queue:events"}


# --------------------------------------------------------------------------- lead follow-ups
async def test_resource_request_cannot_name_a_group_the_caller_is_not_in(db):
    from app.api.policies_router import ResourceRequestCreate, create_resource_request

    me = Principal(user_id="u_me", memberships={"grp_A": "member"})
    with pytest.raises(Forbidden):
        await create_resource_request(
            ResourceRequestCreate(group_id="grp_B", cpu=8, note="please"), principal=me, db=db)
    ok = await create_resource_request(
        ResourceRequestCreate(group_id="grp_A", cpu=8, note="please"), principal=me, db=db)
    assert ok["group_id"] == "grp_A"


async def test_read_only_grantee_cannot_create_folders(db):
    from app.api.volumes_router import create_folder
    from app.db.models import StorageVolume, User, VolumePermission

    await seed(db, [
        User(id="u_owner", email="o@example.com", name="o"),
        User(id="u_ro", email="r@example.com", name="r"),
        User(id="u_rw", email="w@example.com", name="w"),
        StorageVolume(id="vol_f", scope="user", scope_id="u_owner", type="workspace", name="w",
                      access_mode="RWX", owner_id="u_owner", quota_gb=10, used_gb=0),
        VolumePermission(id="vpm_ro", volume_id="vol_f", user_id="u_ro", role="ro"),
        VolumePermission(id="vpm_rw", volume_id="vol_f", user_id="u_rw", role="rw"),
    ])
    with pytest.raises(Forbidden):
        await create_folder("vol_f", {"path": "/a"}, principal=Principal(user_id="u_ro"), db=db)
    await db.rollback()
    out = await create_folder("vol_f", {"path": "/b"}, principal=Principal(user_id="u_rw"), db=db)
    assert out["path"] == "/b"
    out = await create_folder("vol_f", {"path": "/c"}, principal=Principal(user_id="u_owner"), db=db)
    assert out["path"] == "/c"

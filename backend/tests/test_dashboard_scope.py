"""The administrator dashboard counts the sessions of the people the caller manages — and never more."""
from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.api.dashboard_router import dashboard_summary, managed_owner_filter
from app.auth.rbac import Principal
from app.core import ids
from app.db.models import Membership, Organization, Project
from app.db.models import Session as SessionRow


def _session(owner: str) -> SessionRow:
    return SessionRow(
        id=ids.new("session"), owner_user_id=owner, cluster_id="clu_t", offering_id="off_t",
        image_id="img_t", resource_class="gpu", mode="fractional", status="running",
        gpu_mem_mb=1024, gpu_cores=10,
    )


async def _count(db, pred) -> int:
    stmt = select(func.count()).select_from(SessionRow)
    return int(await db.scalar(stmt if pred is None else stmt.where(pred)) or 0)


@pytest.fixture
async def world(db):
    org_a, org_b = ids.new("org"), ids.new("org")
    g_a1, g_a2, g_b = ids.new("group"), ids.new("group"), ids.new("group")
    admin_a1, member_a1, member_a2, member_b, org_admin_a = (ids.new("user") for _ in range(5))
    async with db.begin():
        db.add_all([
            Organization(id=org_a, name="A"), Organization(id=org_b, name="B"),
            Project(id=g_a1, org_id=org_a, name="a1"), Project(id=g_a2, org_id=org_a, name="a2"),
            Project(id=g_b, org_id=org_b, name="b"),
            Membership(id=ids.new("membership"), user_id=admin_a1, group_id=g_a1, role="group_admin"),
            Membership(id=ids.new("membership"), user_id=member_a1, group_id=g_a1, role="member"),
            Membership(id=ids.new("membership"), user_id=member_a2, group_id=g_a2, role="member"),
            Membership(id=ids.new("membership"), user_id=member_b, group_id=g_b, role="member"),
            _session(admin_a1), _session(member_a1), _session(member_a2), _session(member_b),
            _session(org_admin_a),
        ])
    return {"g_a1": g_a1, "org_a": org_a, "admin_a1": admin_a1, "org_admin_a": org_admin_a,
            "member_a1": member_a1}


@pytest.mark.asyncio
async def test_group_admin_sees_only_their_group(db, world):
    p = Principal(user_id=world["admin_a1"], memberships={world["g_a1"]: "group_admin"})
    assert await _count(db, managed_owner_filter(p, "managed")) == 2   # admin_a1 + member_a1
    assert await _count(db, managed_owner_filter(p, "mine")) == 1


@pytest.mark.asyncio
async def test_org_admin_sees_every_group_of_the_org(db, world):
    p = Principal(user_id=world["org_admin_a"], org_admin_orgs={world["org_a"]})
    # a1 + a2 members (3 users) + the org admin's own session; org B stays invisible.
    assert await _count(db, managed_owner_filter(p, "managed")) == 4


@pytest.mark.asyncio
async def test_member_asking_for_managed_gets_mine(db, world):
    p = Principal(user_id=world["member_a1"], memberships={world["g_a1"]: "member"})
    assert await _count(db, managed_owner_filter(p, "managed")) == 1


@pytest.mark.asyncio
async def test_super_admin_sees_everything(db, world):
    p = Principal(user_id="usr_root", global_role="super_admin")
    assert managed_owner_filter(p, "managed") is None
    assert await _count(db, None) == 5


@pytest.mark.asyncio
async def test_endpoint_runs_end_to_end_for_both_scopes(db, world):
    """The full handler, not just the predicate: the wiring of the owner filter into every query."""
    p = Principal(user_id=world["admin_a1"], memberships={world["g_a1"]: "group_admin"})
    mine = await dashboard_summary(scope="mine", principal=p, db=db)
    managed = await dashboard_summary(scope="managed", principal=p, db=db)
    assert mine["sessions"]["running"] == 1
    assert managed["sessions"]["running"] == 2
    # The managed VRAM figure is what the managed sessions hold.
    assert managed["vram"]["used_mb"] == 2 * 1024

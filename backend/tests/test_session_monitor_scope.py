"""Session monitoring (scope=all) and force-terminate follow the OWNER's tenancy, not Session.group_id.

A session created without a group (the API allows it; the wallet is personal) has group_id NULL.
The monitor used to filter by Session.group_id, so an org_admin or group_admin saw an empty list
while their people's sessions were running — and the per-session role check with group_id=None
passed for any admin membership, so an admin of another organization could force-terminate it.
"""
from __future__ import annotations

import pytest

from app.api.deps import Pagination
from app.api.sessions_router import force_terminate, list_sessions
from app.auth.rbac import Principal
from app.core import ids
from app.core.errors import Forbidden
from app.db.models import Membership, Organization, Project
from app.db.models import Session as SessionRow

pytestmark = pytest.mark.asyncio


def _session(owner: str, name: str) -> SessionRow:
    return SessionRow(
        id=ids.new("session"), name=name, owner_user_id=owner, cluster_id="clu_t",
        offering_id="off_t", image_id="img_t", resource_class="gpu", mode="fractional",
        status="running", gpu_mem_mb=1024, gpu_cores=10,   # no group_id, deliberately
    )


@pytest.fixture
async def world(db):
    org_a, org_b = ids.new("org"), ids.new("org")
    g_a, g_b = ids.new("group"), ids.new("group")
    gadmin_a, member_a, member_b, oadmin_a, oadmin_b = (ids.new("user") for _ in range(5))
    s_a, s_b = _session(member_a, "a-run"), _session(member_b, "b-run")
    async with db.begin():
        db.add_all([
            Organization(id=org_a, name="A"), Organization(id=org_b, name="B"),
            Project(id=g_a, org_id=org_a, name="a"), Project(id=g_b, org_id=org_b, name="b"),
            Membership(id=ids.new("membership"), user_id=gadmin_a, group_id=g_a, role="group_admin"),
            Membership(id=ids.new("membership"), user_id=member_a, group_id=g_a, role="member"),
            Membership(id=ids.new("membership"), user_id=member_b, group_id=g_b, role="member"),
            Membership(id=ids.new("membership"), user_id=oadmin_a, group_id=g_a, role="member"),
            Membership(id=ids.new("membership"), user_id=oadmin_b, group_id=g_b, role="member"),
            s_a, s_b,
        ])
    return {
        "org_a": org_a, "org_b": org_b, "g_a": g_a, "g_b": g_b,
        "gadmin_a": gadmin_a, "oadmin_a": oadmin_a, "oadmin_b": oadmin_b, "member_a": member_a,
        "s_a": s_a.id, "s_b": s_b.id,
    }


async def _names(principal, db, scope="all"):
    res = await list_sessions(
        page=Pagination(1, 50), status_filter=None, group_id=None, cluster_id=None,
        scope=scope, principal=principal, db=db,
    )
    return {r.name for r in res["data"]}


def _org_admin(w, org, uid, group):
    # resolve_principal expands an org_admin across every group of their organization
    return Principal(user_id=uid, org_admin_orgs={org}, memberships={group: "org_admin"})


async def test_org_admin_sees_their_orgs_ungrouped_sessions_only(db, world):
    p = _org_admin(world, world["org_a"], world["oadmin_a"], world["g_a"])
    assert await _names(p, db) == {"a-run"}


async def test_group_admin_sees_members_ungrouped_sessions(db, world):
    p = Principal(user_id=world["gadmin_a"], memberships={world["g_a"]: "group_admin"})
    assert await _names(p, db) == {"a-run"}


async def test_member_scope_all_is_downgraded_to_own(db, world):
    p = Principal(user_id=world["member_a"], memberships={world["g_a"]: "member"})
    assert await _names(p, db) == {"a-run"}
    assert await _names(p, db, scope="mine") == {"a-run"}


async def test_super_admin_sees_everything(db, world):
    assert await _names(Principal(user_id="u_super", global_roles={"super_admin"}), db) == {"a-run", "b-run"}


async def test_force_terminate_refused_outside_owner_tenancy(db, world):
    other = _org_admin(world, world["org_b"], world["oadmin_b"], world["g_b"])
    with pytest.raises(Forbidden):
        await force_terminate(world["s_a"], body=None, principal=other, db=db)

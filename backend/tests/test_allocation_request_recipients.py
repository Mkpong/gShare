"""A credit request must always reach someone who can decide it.

A request is stored as pending and its only route to an administrator is the notification raised
when it is created. Two ways that route was silently empty:

- The organization lookup joined the group table, which only matches the legacy shape of the role
  (org_admin written onto a group membership). Administrators are appointed at the organization
  level, so on a current install the query found nobody at all.
- A tier with no administrator notified nobody rather than passing the request up. The request then
  waited for a decision no one knew to make.
"""
from __future__ import annotations

import pytest

from app.api.credits_router import _fulfiller_user_ids
from app.core import ids
from app.db.models import Membership, Organization, Project, User
from app.domain.notification_service import NotificationService
from tests.fkseed import seed

pytestmark = pytest.mark.asyncio

ORG = "org_recip"
GROUP = "grp_recip"


async def _admin(db, uid: str, *, group: str | None = None, org: str | None = None,
                 role: str = "org_admin", global_role: str | None = None) -> None:
    rows: list = [User(id=uid, email=f"{uid}@example.com", name=uid, status="active",
                       global_role=global_role,
                       global_roles=[global_role] if global_role else [])]
    if group or org:
        rows.append(Membership(id=ids.new("membership"), user_id=uid,
                               group_id=group, org_id=org, role=role))
    await seed(db, rows)


async def _base(db) -> None:
    await seed(db, [
        Organization(id=ORG, name="Org"),
        Project(id=GROUP, org_id=ORG, name="dept", status="active"),
    ])


async def test_an_org_admin_appointed_at_the_org_level_is_found(db):
    """The current shape of the role: org_id set, group_id NULL."""
    await _base(db)
    await _admin(db, "usr_orgadm", org=ORG)
    assert await _fulfiller_user_ids(db, "org", ORG) == ["usr_orgadm"]
    assert await NotificationService(db).org_admins(ORG) == ["usr_orgadm"]


async def test_the_legacy_shape_of_the_role_is_still_found(db):
    """Older rows put org_admin on a group membership; that authority still counts."""
    await _base(db)
    await _admin(db, "usr_legacy", group=GROUP)
    assert await _fulfiller_user_ids(db, "org", ORG) == ["usr_legacy"]


async def test_an_organization_with_no_admin_falls_back_to_the_system_admins(db):
    await _base(db)
    await _admin(db, "usr_root", global_role="super_admin")
    # Nobody administers the organization, so the request goes to the tier above rather than
    # sitting pending with no recipient at all.
    assert await _fulfiller_user_ids(db, "org", ORG) == ["usr_root"]


async def test_a_group_with_no_admin_falls_back_to_its_organization(db):
    await _base(db)
    await _admin(db, "usr_orgadm2", org=ORG)
    await _admin(db, "usr_root2", global_role="super_admin")
    # The organization's administrator answers for a group that has none; the system tier is not
    # bothered while a closer administrator exists.
    assert await _fulfiller_user_ids(db, "group", GROUP) == ["usr_orgadm2"]


async def test_a_group_admin_is_preferred_over_the_tiers_above(db):
    await _base(db)
    await _admin(db, "usr_grpadm", group=GROUP, role="group_admin")
    await _admin(db, "usr_orgadm3", org=ORG)
    await _admin(db, "usr_root3", global_role="super_admin")
    assert await _fulfiller_user_ids(db, "group", GROUP) == ["usr_grpadm"]


async def test_a_group_with_nobody_anywhere_still_reaches_the_system_admins(db):
    await _base(db)
    await _admin(db, "usr_root4", global_role="super_admin")
    assert await _fulfiller_user_ids(db, "group", GROUP) == ["usr_root4"]


# ── the inbox the notification opens ────────────────────────────────────────────────────

async def _pending(db, *, scope: str, fid: str, rid: str) -> None:
    from app.db.models import CreditAllocationRequest, CreditWallet

    wid = ids.new("wallet")
    await seed(db, [
        CreditWallet(id=wid, owner_type="group", owner_id=GROUP),
        CreditAllocationRequest(
            id=rid, requester_id="usr_asker", target_wallet_id=wid, level="group",
            fulfiller_scope=scope, fulfiller_id=fid, amount=10, status="pending",
        ),
    ])


async def _inbox(db, principal) -> list[str]:
    from app.api.credits_router import list_allocation_requests
    from app.api.deps import Pagination

    out = await list_allocation_requests(
        box="incoming", page=Pagination(page=1, size=50), principal=principal, db=db
    )
    return [r["id"] for r in out["data"]]


async def test_a_system_admin_sees_a_request_no_one_else_can_answer(db):
    from app.auth.rbac import Principal

    await _base(db)
    await _admin(db, "usr_root5", global_role="super_admin")
    await _pending(db, scope="org", fid=ORG, rid="areq_orphan")
    root = Principal(user_id="usr_root5", global_role="super_admin", global_roles={"super_admin"})
    # The organization has no administrator, so this landed on the system tier's notification.
    assert "areq_orphan" in await _inbox(db, root)


async def test_a_system_admin_is_not_shown_what_an_org_admin_is_handling(db):
    from app.auth.rbac import Principal

    await _base(db)
    await _admin(db, "usr_root6", global_role="super_admin")
    await _admin(db, "usr_orgadm6", org=ORG)
    await _pending(db, scope="org", fid=ORG, rid="areq_owned")
    root = Principal(user_id="usr_root6", global_role="super_admin", global_roles={"super_admin"})
    assert "areq_owned" not in await _inbox(db, root)


async def test_the_org_admin_still_sees_their_own_inbox(db):
    from app.auth.rbac import Principal

    await _base(db)
    await _admin(db, "usr_orgadm7", org=ORG)
    await _pending(db, scope="org", fid=ORG, rid="areq_theirs")
    oa = Principal(user_id="usr_orgadm7", org_admin_orgs={ORG})
    assert await _inbox(db, oa) == ["areq_theirs"]

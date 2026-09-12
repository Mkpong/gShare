"""Credit requests climb one level at a time: a user asks the group, a group asks the organization
(allocation requests), and only the organization asks the system tier — as a top-up, because that
is the one hop where credits are minted rather than moved."""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.api.credits_router import (
    _Validation,
    create_allocation_request,
    create_topup_request,
    list_topup_requests,
)
from app.api.deps import Pagination
from app.api.schemas.credit import AllocationRequestCreate, TopupRequestBody
from app.auth.rbac import Principal
from app.core import ids
from app.core.errors import Forbidden, TopupRequestOrgOnly
from app.db.models import CreditWallet, Organization, Project, User
from tests.fkseed import seed


async def _tenant(db):
    org = Organization(id=ids.new("org"), name="o1")
    prj = Project(id=ids.new("group"), org_id=org.id, name="cs")
    ow = CreditWallet(id=ids.new("wallet"), owner_type="org", owner_id=org.id,
                      balance=Decimal("0"), reserved=Decimal("0"))
    gw = CreditWallet(id=ids.new("wallet"), owner_type="group", owner_id=prj.id,
                      balance=Decimal("0"), reserved=Decimal("0"))
    oa = User(id=ids.new("user"), email="oa@t.local", name="oa")
    ga = User(id=ids.new("user"), email="ga@t.local", name="ga")
    await seed(db, [org, prj, ow, gw, oa, ga])
    return org, prj, ow, gw, oa.id, ga.id


@pytest.mark.asyncio
async def test_org_admin_asks_the_system_with_a_topup(db):
    org, prj, ow, _gw, oa, _ = await _tenant(db)
    p = Principal(user_id=oa, memberships={prj.id: "org_admin"}, org_admin_orgs={org.id})
    out = await create_topup_request(TopupRequestBody(amount=Decimal("100"), wallet_id=ow.id),
                                     wallet_id=None, principal=p, db=db)
    assert out["wallet_id"] == ow.id and out["status"] == "pending"
    root = Principal(user_id=ids.new("user"), global_role="super_admin",
                     global_roles={"super_admin"}, memberships={})
    lst = await list_topup_requests(page=Pagination(page=1, size=20), status_filter="pending",
                                    wallet_id=None, scope="all", principal=root, db=db)
    row = next(r for r in lst["data"] if r["id"] == out["id"])
    assert row["wallet_owner_type"] == "org" and row["wallet_owner_name"] == "o1"


@pytest.mark.asyncio
async def test_group_and_user_wallets_take_no_topup_requests(db):
    _org, prj, _ow, gw, _oa, ga = await _tenant(db)
    group_admin = Principal(user_id=ga, memberships={prj.id: "group_admin"})
    with pytest.raises(TopupRequestOrgOnly):   # the group asks its organization instead
        await create_topup_request(TopupRequestBody(amount=Decimal("50"), wallet_id=gw.id),
                                   wallet_id=None, principal=group_admin, db=db)
    member = Principal(user_id=ids.new("user"), memberships={prj.id: "member"})
    with pytest.raises(TopupRequestOrgOnly):   # a user asks their group
        await create_topup_request(TopupRequestBody(amount=Decimal("50"), wallet_id=gw.id),
                                   wallet_id=None, principal=member, db=db)


@pytest.mark.asyncio
async def test_only_the_organizations_own_admin_may_ask(db):
    org, prj, ow, _gw, _oa, _ga = await _tenant(db)
    stranger = Principal(user_id=ids.new("user"), memberships={prj.id: "org_admin"},
                         org_admin_orgs={"org_other"})
    with pytest.raises(Forbidden):
        await create_topup_request(TopupRequestBody(amount=Decimal("50"), wallet_id=ow.id),
                                   wallet_id=None, principal=stranger, db=db)


@pytest.mark.asyncio
async def test_group_asks_the_organization_with_an_allocation_request(db):
    org, prj, _ow, gw, oa, ga = await _tenant(db)
    p = Principal(user_id=ga, memberships={prj.id: "group_admin"})
    out = await create_allocation_request(
        AllocationRequestCreate(level="group", group_id=prj.id, amount=Decimal("30"), note="short"),
        principal=p, db=db)
    assert out["target_wallet_id"] == gw.id and out["fulfiller_scope"] == "org"
    assert out["fulfiller_id"] == org.id
    # the organization tier no longer raises allocation requests: that hop is a top-up
    org_admin = Principal(user_id=oa, memberships={prj.id: "org_admin"}, org_admin_orgs={org.id})
    with pytest.raises(_Validation):
        await create_allocation_request(
            AllocationRequestCreate(level="org", org_id=org.id, amount=Decimal("30"), note="x"),
            principal=org_admin, db=db)

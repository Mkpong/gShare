"""Self-service sign-up, governed by the system policy."""
from __future__ import annotations

import pytest

from app.api.system_router import SignupPolicyUpdate, get_signup_policy, set_signup_policy
from app.api.users_router import (
    UserApproveBody,
    _LoginRequest,
    _SignupRequest,
    approve_user,
    auth_login,
    auth_signup,
)
from app.auth.rbac import Principal
from app.core import ids
from app.core.errors import DomainError, Forbidden
from app.db.models import Organization, Project, User


class _Req:
    headers = {"x-forwarded-for": "10.0.0.7"}
    client = None


def _super() -> Principal:
    return Principal(user_id="usr_admin", global_roles={"super_admin"})


async def _group(db) -> Project:
    org = Organization(id=ids.new("org"), name="DKU")
    grp = Project(id=ids.new("project"), org_id=org.id, name="CE")
    async with db.begin():
        db.add_all([org, grp])
    return grp


def _body(email: str = "s1@dankook.ac.kr") -> _SignupRequest:
    return _SignupRequest(email=email, name="Student", password="choose-my-own")


@pytest.mark.asyncio
async def test_closed_is_the_default_and_refuses(db):
    assert (await get_signup_policy(db)).mode == "closed"
    with pytest.raises(Forbidden):
        await auth_signup(_body(), _Req(), db)


@pytest.mark.asyncio
async def test_open_mode_creates_an_active_account_with_no_department(db):
    await set_signup_policy(SignupPolicyUpdate(mode="open"), _super(), db)
    assert (await auth_signup(_body(), _Req(), db))["status"] == "active"
    tok = await auth_login(_LoginRequest(email="s1@dankook.ac.kr", password="choose-my-own"),
                           _Req(), db)
    assert tok["access_token"]

    from sqlalchemy import func
    from sqlalchemy import select as _select

    from app.db.models import Membership
    user = (await db.execute(_select(User).where(User.email == "s1@dankook.ac.kr"))).scalar_one()
    memberships = await db.scalar(
        _select(func.count()).select_from(Membership).where(Membership.user_id == user.id)
    )
    assert memberships == 0


@pytest.mark.asyncio
async def test_approval_mode_parks_the_account_until_an_admin_opens_it(db):
    grp = await _group(db)
    await set_signup_policy(SignupPolicyUpdate(mode="approval"), _super(), db)
    assert (await auth_signup(_body(), _Req(), db))["status"] == "pending"

    with pytest.raises(DomainError) as exc:
        await auth_login(_LoginRequest(email="s1@dankook.ac.kr", password="choose-my-own"),
                         _Req(), db)
    assert exc.value.code == "account_pending"

    # Approval assigns the department and activates in one step.
    from sqlalchemy import select
    row = (await db.execute(select(User).where(User.email == "s1@dankook.ac.kr"))).scalar_one()
    out = await approve_user(row.id, UserApproveBody(group_id=grp.id), _super(), db)
    assert out["status"] == "active"

    from app.db.models import Membership
    m = (await db.execute(select(Membership).where(Membership.user_id == row.id))).scalar_one()
    assert m.group_id == grp.id and m.role == "member"
    assert (await auth_login(_LoginRequest(email="s1@dankook.ac.kr", password="choose-my-own"),
                             _Req(), db))["access_token"]


@pytest.mark.asyncio
async def test_approval_without_a_department_is_allowed(db):
    await set_signup_policy(SignupPolicyUpdate(mode="approval"), _super(), db)
    await auth_signup(_body(), _Req(), db)
    from sqlalchemy import select
    row = (await db.execute(select(User).where(User.email == "s1@dankook.ac.kr"))).scalar_one()
    assert (await approve_user(row.id, UserApproveBody(), _super(), db))["status"] == "active"


@pytest.mark.asyncio
async def test_an_account_that_is_not_pending_cannot_be_approved(db):
    await set_signup_policy(SignupPolicyUpdate(mode="open"), _super(), db)
    await auth_signup(_body(), _Req(), db)
    from sqlalchemy import select
    row = (await db.execute(select(User).where(User.email == "s1@dankook.ac.kr"))).scalar_one()
    with pytest.raises(DomainError):
        await approve_user(row.id, UserApproveBody(), _super(), db)


@pytest.mark.asyncio
async def test_only_the_allowed_domains_may_register(db):
    await set_signup_policy(
        SignupPolicyUpdate(mode="open", allowed_domains=["dankook.ac.kr"]), _super(), db)
    with pytest.raises(DomainError):
        await auth_signup(_body("outsider@gmail.com"), _Req(), db)
    assert (await auth_signup(_body(), _Req(), db))["status"] == "active"


@pytest.mark.asyncio
async def test_a_duplicate_email_conflicts(db):
    await set_signup_policy(SignupPolicyUpdate(mode="open"), _super(), db)
    await auth_signup(_body(), _Req(), db)
    with pytest.raises(DomainError):
        await auth_signup(_body(), _Req(), db)

"""An administrator can put a locked-out user back in, and a group can always be funded.

Two gaps this pins down:

- The console's only password control sent `password`, which the API refuses for anyone but the
  account's own owner, so no administrator could help a user who had forgotten theirs. The reset
  endpoint issues a random one instead of letting the administrator choose it.
- A group created with the wallet box cleared could never be allocated credits, and nothing could
  add the wallet afterwards.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.api.groups_router import ProjectCreate, create_project
from app.api.users_router import UserPatch, reset_user_password, update_user
from app.auth.rbac import Principal
from app.core import ids
from app.core.errors import Forbidden
from app.core.passwords import hash_password, verify_password
from app.db.models import CreditWallet, Membership, Organization, Project, User
from tests.fkseed import seed

pytestmark = pytest.mark.asyncio

ORG = "org_pw"
GROUP = "grp_pw"


def _super() -> Principal:
    # Both fields, the way resolve_principal builds one: groups_router reads the scalar
    # global_role while most handlers read the global_roles set.
    return Principal(user_id="usr_root", global_role="super_admin", global_roles={"super_admin"})


async def _user(db, uid: str, *, password: str = "old-password", group: str | None = GROUP,
                global_roles: list[str] | None = None) -> User:
    u = User(id=uid, email=f"{uid}@example.com", name=uid, status="active",
             password_hash=hash_password(password), must_change_password=False,
             global_roles=global_roles or [],
             global_role=(global_roles or [None])[0] if global_roles else None)
    rows = [u]
    if group:
        rows.append(Membership(id=ids.new("membership"), user_id=uid, group_id=group, role="member"))
    await seed(db, rows)
    return u


# ── the reset ───────────────────────────────────────────────────────────────────────────

async def test_an_administrator_cannot_choose_someone_elses_password(db):
    await _user(db, "usr_a")
    with pytest.raises(Forbidden):
        await update_user("usr_a", UserPatch(password="chosen-by-admin"), principal=_super(), db=db)


async def test_reset_issues_a_working_temporary_password_once(db):
    user = await _user(db, "usr_b", password="forgotten")
    out = await reset_user_password("usr_b", principal=_super(), db=db)

    assert out["temporary_password"] and len(out["temporary_password"]) >= 12
    assert out["email"] == "usr_b@example.com"
    db.expunge_all()
    row = await db.get(User, user.id)
    # The new one works, the forgotten one does not, and the next sign-in has to replace it.
    assert verify_password(out["temporary_password"], row.password_hash)
    assert not verify_password("forgotten", row.password_hash)
    assert row.must_change_password is True
    # Issued once: a second call cannot return the same secret.
    again = await reset_user_password("usr_b", principal=_super(), db=db)
    assert again["temporary_password"] != out["temporary_password"]


async def test_a_group_admin_may_reset_inside_their_group_only(db):
    await _user(db, "usr_mine", group=GROUP)
    await _user(db, "usr_theirs", group="grp_other")
    ga = Principal(user_id="usr_ga", memberships={GROUP: "group_admin"})

    out = await reset_user_password("usr_mine", principal=ga, db=db)
    assert out["temporary_password"]
    with pytest.raises(Forbidden):
        await reset_user_password("usr_theirs", principal=ga, db=db)


async def test_nobody_resets_an_account_that_outranks_them(db):
    await _user(db, "usr_root2", global_roles=["super_admin"])
    ga = Principal(user_id="usr_ga", memberships={GROUP: "group_admin"})
    with pytest.raises(Forbidden):
        await reset_user_password("usr_root2", principal=ga, db=db)
    # A super_admin still can, so a shared bootstrap account is never stuck.
    assert (await reset_user_password("usr_root2", principal=_super(), db=db))["temporary_password"]


# ── the group wallet ────────────────────────────────────────────────────────────────────

async def test_a_new_group_always_gets_a_wallet(db):
    await seed(db, [Organization(id=ORG, name="Org")])
    for flag in (True, False):
        out = await create_project(
            ProjectCreate(org_id=ORG, name=f"dept-{flag}", create_project_wallet=flag),
            principal=_super(), db=db,
        )
        await db.commit()
        wallet = await db.scalar(
            select(CreditWallet.id).where(
                CreditWallet.owner_type == "group", CreditWallet.owner_id == out["id"]
            )
        )
        assert wallet is not None, f"create_project_wallet={flag} left the group unfundable"


async def test_the_startup_seed_fills_in_groups_that_have_no_wallet(db, monkeypatch):
    from app.auth import bootstrap

    await seed(db, [
        Organization(id=ORG, name="Org"),
        Project(id="grp_old", org_id=ORG, name="predates the change", status="active"),
        Project(id="grp_has", org_id=ORG, name="already funded", status="active"),
        CreditWallet(id=ids.new("wallet"), owner_type="group", owner_id="grp_has"),
    ])

    class _SM:
        def __call__(self):
            from contextlib import asynccontextmanager

            @asynccontextmanager
            async def _ctx():
                yield db

            return _ctx()

    monkeypatch.setattr(bootstrap, "get_sessionmaker", lambda: _SM(), raising=False)
    monkeypatch.setattr("app.db.base.get_sessionmaker", lambda: _SM())
    await db.commit()
    await bootstrap.seed_group_wallets()

    owners = set(
        (await db.scalars(
            select(CreditWallet.owner_id).where(CreditWallet.owner_type == "group")
        )).all()
    )
    assert {"grp_old", "grp_has"} <= owners

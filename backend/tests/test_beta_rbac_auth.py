"""Beta authorization sweep (B-authz): token audience/algorithm mixing, account-state gates, the
must_change_password fence, and the operator token's cluster binding.

These are the checks that were verified to HOLD during the sweep; they are kept as a regression
net so a later refactor of jwt_auth / rbac / internal_jwt cannot silently reopen them.
"""
from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import jwt

from app.auth import internal_jwt as ij
from app.auth import rbac
from app.auth.jwt_auth import verify_jwt
from app.auth.rbac import Principal, rbac_allows, resolve_principal
from app.core import ids
from app.core.config import settings
from app.core.errors import Forbidden, Unauthenticated
from app.db.models import Membership, Organization, Project, User
from app.internal.connect_verify_router import _make_cookie, _verify_cookie
from tests.fkseed import add_ordered

pytestmark = pytest.mark.asyncio


def _user_token(**claims) -> str:
    now = int(time.time())
    payload = {"sub": "usr_x", "aud": "gshare-user", "iat": now, "exp": now + 60}
    payload.update(claims)
    return jwt.encode(payload, settings.USER_JWT_SECRET, algorithm="HS256")


# ── token audience / algorithm mixing ──


async def test_connect_cookie_is_not_a_user_bearer():
    """The gshare_session cookie is signed with the same secret as user tokens; it carries no
    gshare-user audience, so it must never authenticate an API call."""
    cookie = _make_cookie("ses_1", "usr_victim")
    with pytest.raises(Unauthenticated):
        await verify_jwt(f"Bearer {cookie}")


async def test_user_bearer_is_not_a_connect_cookie():
    """The reverse direction: a user token presented as the connect cookie yields no session id,
    so forward-auth falls through to the single-use cnx token."""
    assert _verify_cookie(_user_token()) is None
    assert _verify_cookie("garbage") is None
    assert _verify_cookie(None) is None

    assert _verify_cookie(_make_cookie("ses_1", "usr_a")) == "ses_1"


async def test_internal_token_is_not_a_user_bearer(monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    monkeypatch.setattr(settings, "INTERNAL_JWT_PRIVATE_KEY", pem)
    tok = ij.sign_internal_jwt("operator:clu_A")
    with pytest.raises(Unauthenticated):
        await verify_jwt(f"Bearer {tok}")


async def test_user_bearer_is_not_an_internal_token(monkeypatch):
    """HS256 user token against the RS256-only internal verifier (also covers the classic
    alg-confusion attack: an HS256 token signed with the public key is refused because HS256 is
    not in the allowed algorithm list)."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    monkeypatch.setattr(settings, "INTERNAL_JWT_PRIVATE_KEY", pem)
    jwks = await ij.load_internal_jwks()

    async def _fake_jwks():
        return jwks

    monkeypatch.setattr(ij, "_internal_jwks", _fake_jwks)

    good = ij.sign_internal_jwt("operator:clu_A")
    assert (await ij.require_internal_jwt(f"Bearer {good}"))["sub"] == "operator:clu_A"

    with pytest.raises(Unauthenticated):
        await ij.require_internal_jwt(f"Bearer {_user_token(aud='gshare-internal')}")

    pub_pem = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()
    now = int(time.time())

    forged = _hs256_by_hand(
        {"alg": "HS256", "typ": "JWT", "kid": settings.INTERNAL_JWT_KID},
        {"sub": "operator:clu_A", "aud": "gshare-internal", "iat": now, "exp": now + 60},
        pub_pem.encode(),
    )
    with pytest.raises(Unauthenticated):
        await ij.require_internal_jwt(f"Bearer {forged}")


def _hs256_by_hand(header: dict, claims: dict, secret: bytes) -> str:
    import base64
    import hashlib
    import hmac
    import json

    def b64(b: bytes) -> str:
        return base64.urlsafe_b64encode(b).rstrip(b"=").decode()

    signing = f"{b64(json.dumps(header).encode())}.{b64(json.dumps(claims).encode())}"
    sig = hmac.new(secret, signing.encode(), hashlib.sha256).digest()
    return f"{signing}.{b64(sig)}"


# ── operator token cluster binding ──


async def test_operator_token_cluster_binding():
    a = {"sub": "operator:clu_A"}
    ij.require_operator_cluster(a, "clu_A", what="session")
    ij.require_operator_cluster(a, None, what="session")
    ij.require_operator_cluster({"sub": "legacy"}, "clu_B", what="session")
    with pytest.raises(Forbidden):
        ij.require_operator_cluster(a, "clu_B", what="session")


# ── account state gates ──


async def _seed_user(db, *, status="active", deleted=False, memberships=()):
    uid = ids.new("user")
    await add_ordered(db, [
        User(id=uid, email=f"{uid}@x", name=uid, status=status,
             deleted_at=datetime.now(UTC) if deleted else None),
        *(Membership(id=ids.new("membership"), user_id=uid, group_id=gid, role=role,
                     expires_at=exp) for gid, role, exp in memberships),
    ])
    return uid


async def test_expired_guest_membership_is_dropped(db):
    db.add_all([Organization(id="org_G", name="G"), Project(id="grp_G", org_id="org_G", name="g")])
    past = datetime.now(UTC) - timedelta(minutes=1)
    future = datetime.now(UTC) + timedelta(days=1)
    expired = await _seed_user(db, memberships=[("grp_G", "guest", past)])
    live = await _seed_user(db, memberships=[("grp_G", "guest", future)])
    rbac._PRINCIPAL_CACHE.clear()
    p_exp = await resolve_principal(db, {"sub": expired})
    p_live = await resolve_principal(db, {"sub": live})
    assert p_exp.memberships == {}
    assert p_live.memberships == {"grp_G": "guest"}

    for p in (p_exp, p_live):
        assert not rbac_allows(p, "session.create", "grp_G")
        assert not rbac_allows(p, "group.read", "grp_G")
        assert not rbac_allows(p, "volume.create", "grp_G")


async def test_suspended_or_deleted_user_with_valid_token_is_refused(db):
    rbac._PRINCIPAL_CACHE.clear()
    suspended = await _seed_user(db, status="suspended")
    deleted = await _seed_user(db, deleted=True)
    with pytest.raises(Forbidden):
        await resolve_principal(db, {"sub": suspended})
    with pytest.raises(Forbidden):
        await resolve_principal(db, {"sub": deleted})
    with pytest.raises(Forbidden):
        await resolve_principal(db, {"sub": "usr_does_not_exist"})


async def test_suspension_lockout_bounded_by_principal_cache(db, monkeypatch):
    """The 30 s principal cache is the documented window between suspension and lock-out; make the
    bound explicit so nobody grows it without noticing."""
    assert rbac._PRINCIPAL_TTL_SEC <= 30.0
    rbac._PRINCIPAL_CACHE.clear()
    uid = await _seed_user(db)
    await resolve_principal(db, {"sub": uid})
    (await db.get(User, uid)).status = "suspended"
    await db.flush()

    assert (await resolve_principal(db, {"sub": uid})).user_id == uid

    monkeypatch.setattr(rbac, "_PRINCIPAL_TTL_SEC", 0.0)
    with pytest.raises(Forbidden):
        await resolve_principal(db, {"sub": uid})


# ── the must_change_password fence ──


async def test_password_change_fence_blocks_everything_else():
    from types import SimpleNamespace

    from app.api.deps import _PWCHANGE_ALLOWED, get_current_principal
    from app.core.errors import PasswordChangeRequired

    assert set(_PWCHANGE_ALLOWED) == {"/auth/change-password", "/auth/me"}
    token = _user_token(must_change_password=True)
    for path in ("/api/v1/sessions", "/api/v1/notifications", "/api/v1/users/resolve",
                 "/api/v1/credits/wallets/me", "/api/v1/auth/me/../sessions"):
        req = SimpleNamespace(url=SimpleNamespace(path=path), state=SimpleNamespace())
        with pytest.raises(PasswordChangeRequired):
            await get_current_principal(req, authorization=f"Bearer {token}", access_token=None, db=None)

    req = SimpleNamespace(url=SimpleNamespace(path="/api/v1/sessions"), state=SimpleNamespace())
    with pytest.raises(Unauthenticated):
        await get_current_principal(req, authorization=None, access_token=None, db=None)


# ── scoped rank checks ──


async def test_scoped_rank_checks_are_per_group():
    ga = Principal(user_id="u", memberships={"grp_A": "group_admin"})
    assert rbac_allows(ga, "membership.create", "grp_A")
    assert not rbac_allows(ga, "membership.create", "grp_B")
    assert not rbac_allows(ga, "org.read")
    assert not rbac_allows(ga, "cluster.read")
    member = Principal(user_id="u", memberships={"grp_A": "member"})
    for action in ("user.read", "audit.read", "queue.read", "budget.read", "membership.read",
                   "session.monitor", "session.force_terminate", "volume.create"):
        assert not rbac_allows(member, action), action
        assert not rbac_allows(member, action, "grp_A"), action
    nobody = Principal(user_id="u")
    assert not rbac_allows(nobody, "session.create")
    assert not rbac_allows(nobody, "no.such.action")

"""Regression tests for the pre-review hypotheses H-1..H-6 (beta-test pass).

Each test pins one behaviour the review suspected was wrong; every one of them failed on the
code as found and passes with the fix, so a later change that reopens the hole is caught here.
"""
from __future__ import annotations

import time
from contextlib import asynccontextmanager

import pytest
from jose import jwt
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from starlette.requests import Request

from app.api.users_router import _LoginRequest, auth_login
from app.auth.rbac import _resolve_principal_uncached
from app.core import ids
from app.core.config import settings
from app.core.errors import DomainError, Unauthenticated
from app.core.passwords import hash_password
from app.db.models import AuditLog, Cluster, User
from tests.fkseed import seed


def _request(path: str = "/api/v1/auth/login", *, xff: str | None = None,
             query: str = "", peer: str = "9.9.9.9") -> Request:
    headers = [(b"host", b"gshare.test")]
    if xff is not None:
        headers.append((b"x-forwarded-for", xff.encode()))
    return Request({
        "type": "http", "method": "GET", "path": path, "raw_path": path.encode(),
        "root_path": "", "scheme": "http", "server": ("gshare.test", 80),
        "headers": headers, "client": (peer, 1234), "query_string": query.encode(),
    })


def _user_token(uid: str, email: str, **extra) -> str:
    now = int(time.time())
    claims = {
        "sub": uid, "aud": "gshare-user", "email": email,
        "global_role": None, "global_roles": [],
        "must_change_password": False, "iat": now, "exp": now + 60,
    }
    claims.update(extra)
    return jwt.encode(claims, settings.USER_JWT_SECRET, algorithm="HS256")


# ── H-1: a demoted super_admin keeps the role for the life of the token ─────────────────

@pytest.mark.asyncio
async def test_h1_global_roles_come_from_the_database_not_the_token(db):
    uid = ids.new("user")
    await seed(db, [
        User(id=uid, email="h1@example.com", name="H1", status="active",
                global_role="super_admin", global_roles=["super_admin"]),
    ])
    claims = {"sub": uid, "global_roles": ["super_admin"], "global_role": "super_admin"}
    p = await _resolve_principal_uncached(db, claims)
    assert "super_admin" in p.global_roles
    await db.rollback()   # the resolver's SELECT autobegan a transaction
    # Demotion in the database while the 24h token is still valid.
    async with db.begin():
        row = await db.get(User, uid)
        row.global_roles = []
        row.global_role = None
    p = await _resolve_principal_uncached(db, claims)
    assert p.global_roles == set() and p.global_role is None


# ── H-2: the rate limiter trusts whatever the client puts first in X-Forwarded-For ────────

@pytest.mark.asyncio
async def test_h2_client_ip_is_the_hop_the_trusted_proxy_appended(db, monkeypatch):
    from app.api.users_router import _client_ip

    monkeypatch.setattr(settings, "TRUSTED_PROXY_HOPS", 1, raising=False)
    # The proxy appends the real peer last; anything before it is client-controlled.
    assert _client_ip(_request(xff="6.6.6.6, 203.0.113.7")) == "203.0.113.7"
    assert _client_ip(_request(xff="203.0.113.7")) == "203.0.113.7"
    assert _client_ip(_request()) == "9.9.9.9"
    monkeypatch.setattr(settings, "TRUSTED_PROXY_HOPS", 2, raising=False)
    assert _client_ip(_request(xff="6.6.6.6, 203.0.113.7, 10.0.0.2")) == "203.0.113.7"
    # Fewer hops than configured: the leftmost is the best available, never a spoofed extra.
    assert _client_ip(_request(xff="203.0.113.7")) == "203.0.113.7"


@pytest.mark.asyncio
async def test_h2_login_audit_records_the_trusted_hop(db, monkeypatch):
    monkeypatch.setattr(settings, "TRUSTED_PROXY_HOPS", 1, raising=False)
    with pytest.raises(Unauthenticated):
        await auth_login(_LoginRequest(email="ghost@example.com", password="x-y-z-1"),
                         _request(xff="6.6.6.6, 203.0.113.7"), db)
    row = (await db.execute(select(AuditLog).where(AuditLog.action == "auth.login"))).scalars().first()
    assert row is not None
    assert "203.0.113.7" in str(row.detail)
    assert "6.6.6.6" not in str(row.detail)


# ── H-3: "account pending" is disclosed before the password is checked ────────────────────

@pytest.mark.asyncio
async def test_h3_pending_is_only_revealed_to_the_right_password(db):
    user = User(id=ids.new("user"), email="h3@example.com", name="H3", status="pending",
                password_hash=hash_password("correct-horse"))
    await seed(db, [user])
    with pytest.raises(Unauthenticated):
        await auth_login(_LoginRequest(email=user.email, password="wrong-one"), _request(), db)
    with pytest.raises(DomainError) as exc:
        await auth_login(_LoginRequest(email=user.email, password="correct-horse"), _request(), db)
    assert exc.value.code == "account_pending"


# ── H-4: ?access_token= is accepted on every endpoint, not only the SSE streams ───────────

@pytest.mark.asyncio
async def test_h4_query_token_is_limited_to_event_streams(db):
    from app.api.deps import get_current_principal

    uid = ids.new("user")
    await seed(db, [User(id=uid, email="h4@example.com", name="H4", status="active")])
    tok = _user_token(uid, "h4@example.com")
    # An EventSource cannot set headers: the stream endpoints keep the query fallback.
    p = await get_current_principal(_request("/api/v1/notifications/events"), None, tok, db)
    assert p.user_id == uid
    p = await get_current_principal(_request("/api/v1/sessions/ses_x/events"), None, tok, db)
    assert p.user_id == uid
    # Everything else must carry the bearer header; a token in the URL is a token in every log.
    with pytest.raises(Unauthenticated):
        await get_current_principal(_request("/api/v1/sessions"), None, tok, db)
    with pytest.raises(Unauthenticated):
        await get_current_principal(_request("/api/v1/audit-logs/export"), None, tok, db)
    # The header still works everywhere.
    p = await get_current_principal(_request("/api/v1/sessions"), f"Bearer {tok}", None, db)
    assert p.user_id == uid


# ── H-5: the 409 merge-patch leaves cleared fields on the custom resource ─────────────────

class _Conflict(Exception):
    status = 409


class _FakeApi:
    def __init__(self):
        self.patches: list[dict] = []

    async def create_namespaced_custom_object(self, **kw):
        raise _Conflict()

    async def patch_namespaced_custom_object(self, **kw):
        self.patches.append(kw["body"])
        self.content_types = getattr(self, "content_types", []) + [kw.get("_content_type")]
        return kw["body"]


@pytest.mark.asyncio
async def test_h5_reapply_clears_fields_the_new_desired_state_no_longer_carries(db, monkeypatch):
    from app.cluster.crd import GShareSessionCRD

    await seed(db, [
        Cluster(id="clu_h5", name="h5", api_server="https://h5:6443", runtime="k8s",
                   kubeconfig_secret_ref="sec"),
    ])
    api = _FakeApi()

    @asynccontextmanager
    async def _factory(_cluster):
        yield api

    async def _fake_factory(cluster):
        return _factory(cluster)

    crd = GShareSessionCRD(db, client_factory=_fake_factory)

    async def _none(spec_like):
        return None

    monkeypatch.setattr(crd, "_resolve_idle_timeout_sec", _none)
    monkeypatch.setattr(crd, "_resolve_max_runtime_sec", _none)
    # A spec that borrowed a card and excluded a node last time carries neither now.
    spec = {"session_id": "ses_h5", "cluster_id": "clu_h5", "resource_class": "gpu",
            "mode": "fractional", "owner": "usr_h5", "image": "img", "cpu": 2, "mem_gb": 4,
            "gpu_mem_mb": 4096, "gpu_cores": 25}
    await crd.apply("clu_h5", spec)
    assert len(api.patches) == 1
    # Forced merge-patch: the client's default for a dict body is a strategic merge patch, which
    # the API server refuses for custom resources with 415.
    assert api.content_types == ["application/merge-patch+json"]
    patched = api.patches[0]["spec"]
    # Present fields are carried; fields the desired state dropped are explicitly nulled so a
    # JSON merge-patch removes them instead of leaving last run's values behind.
    assert patched["gpuMemMb"] == 4096 and patched["mode"] == "fractional"
    for stale in ("borrowedGpuUuid", "borrowedNode", "pinnedGpuUuid", "excludedNodes",
                  "migProfile", "paused", "fullCard", "volumes"):
        assert stale in patched and patched[stale] is None, stale
    # A lifted lifetime cap must also disappear from the annotations.
    ann = api.patches[0]["metadata"]["annotations"]
    assert "gshare.io/max-runtime-sec" in ann and ann["gshare.io/max-runtime-sec"] is None


# ── H-6: any unique violation is mistaken for an idempotent replay ────────────────────────

@pytest.mark.asyncio
async def test_h6_only_the_idempotency_key_collision_is_swallowed(db):
    from app.domain.credit_engine import CreditEngine

    engine = CreditEngine(db)

    def _err(msg: str) -> IntegrityError:
        return IntegrityError("INSERT", {}, Exception(msg))

    # The replay: swallowed, by design.
    async with engine._keyed_atomic():
        raise _err('duplicate key value violates unique constraint '
                   '"credit_transaction_idempotency_key_key"')
    async with engine._keyed_atomic():
        raise _err("UNIQUE constraint failed: credit_transaction.idempotency_key")
    # Any other unique violation is a real failure and must surface.
    with pytest.raises(IntegrityError):
        async with engine._keyed_atomic():
            raise _err('duplicate key value violates unique constraint "uq_storage_pool_cluster_class"')
    with pytest.raises(IntegrityError):
        async with engine._keyed_atomic():
            raise _err("UNIQUE constraint failed: allocation.session_id")


# ── GS-008: a forced password reset does not reach a token issued before it ──────────────

@pytest.mark.asyncio
async def test_gs008_forced_password_change_is_read_from_the_database(db):
    from app.api.deps import get_current_principal
    from app.core.errors import PasswordChangeRequired

    uid = ids.new("user")
    await seed(db, [
        User(id=uid, email="g8@example.com", name="G8", status="active",
                must_change_password=True),
    ])
    # The token predates the administrator's reset, so its claim still says False.
    tok = _user_token(uid, "g8@example.com", must_change_password=False)
    with pytest.raises(PasswordChangeRequired):
        await get_current_principal(_request("/api/v1/sessions"), f"Bearer {tok}", None, db)
    p = await get_current_principal(_request("/api/v1/auth/me"), f"Bearer {tok}", None, db)
    assert p.user_id == uid

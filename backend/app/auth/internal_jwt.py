"""Plane-to-plane internal JWT — RS256, aud=gshare-internal.

This control plane is the **signer** (private key ``INTERNAL_JWT_PRIVATE_KEY``) and the
**verifier** of operator->control callbacks. Verification uses the internal JWKS published at
``GET /.well-known/gshare-internal-jwks.json``. This is plane-to-plane only — not a user token.
"""
from __future__ import annotations

import time

import httpx
from fastapi import Header
from jose import jwk, jwt
from jose.constants import ALGORITHMS

from app.core.config import settings
from app.core.errors import Forbidden, Unauthenticated

_ijwks_cache: dict = {}
_ijwks_exp: float = 0.0


async def _internal_jwks() -> dict:
    global _ijwks_cache, _ijwks_exp
    if time.time() > _ijwks_exp:
        async with httpx.AsyncClient(timeout=5.0) as c:
            _ijwks_cache = (await c.get(settings.INTERNAL_JWKS_URL)).json()
            _ijwks_exp = time.time() + settings.JWKS_TTL_SEC
    return _ijwks_cache


async def require_internal_jwt(authorization: str = Header(...)) -> dict:
    """FastAPI dependency: verify a short-lived internal RS256 JWT (aud=gshare-internal)."""
    token = authorization.removeprefix("Bearer ").strip()
    try:
        return jwt.decode(
            token, await _internal_jwks(), algorithms=["RS256"],
            audience=settings.INTERNAL_JWT_AUDIENCE,
        )
    except Exception as exc:  # noqa: BLE001
        raise Unauthenticated("invalid internal token") from exc


def sign_internal_jwt(subject: str, ttl: int | None = None, extra: dict | None = None) -> str:
    """Sign a short-lived internal token for an operator.

    The control plane is the signer: it holds the RS256 private key
    (``INTERNAL_JWT_PRIVATE_KEY``, external-secrets injected) and mints short-lived tokens
    (``aud=gshare-internal``) for operator->control callbacks. The ``kid`` header pins the active
    key so verifiers can resolve it from the published JWKS during rotation.
    """
    if not settings.INTERNAL_JWT_PRIVATE_KEY:
        raise RuntimeError("INTERNAL_JWT_PRIVATE_KEY is not configured")
    now = int(time.time())
    ttl = ttl if ttl is not None else settings.INTERNAL_JWT_TTL_SEC
    claims: dict = {
        "sub": subject,
        "aud": settings.INTERNAL_JWT_AUDIENCE,
        "iss": settings.INTERNAL_JWT_AUDIENCE,  # self-issued by the control plane
        "iat": now,
        "nbf": now,
        "exp": now + ttl,
    }
    if extra:
        claims.update(extra)
    return jwt.encode(
        claims,
        settings.INTERNAL_JWT_PRIVATE_KEY,
        algorithm=ALGORITHMS.RS256,
        headers={"kid": settings.INTERNAL_JWT_KID},
    )


def _public_jwk_from_private(pem: str, kid: str) -> dict:
    """Derive a public JWKS entry (RSA n/e) from an RS256 private key PEM (private never
    exposed)."""
    key = jwk.construct(pem, ALGORITHMS.RS256)
    pub = key.public_key().to_dict()  # {kty, n, e, ...} — public material only
    pub.update({"kid": kid, "use": "sig", "alg": ALGORITHMS.RS256})
    return pub


async def load_internal_jwks() -> dict:
    """Return the public JWKS (current + previous kid) for the well-known route.

    Derives the RSA public key (n/e) from the locally held RS256 private key — the private key is
    never published. Supports kid rotation by also publishing a previous key if configured.
    Verifiers trust ONLY this JWKS.
    """
    keys: list[dict] = []
    seen: set[str] = set()
    if settings.INTERNAL_JWT_PRIVATE_KEY:
        keys.append(_public_jwk_from_private(settings.INTERNAL_JWT_PRIVATE_KEY, settings.INTERNAL_JWT_KID))
        seen.add(settings.INTERNAL_JWT_KID)
    # Optional previous key during rotation (external-secrets may inject both).
    prev_pem = getattr(settings, "INTERNAL_JWT_PREVIOUS_PRIVATE_KEY", "")
    prev_kid = getattr(settings, "INTERNAL_JWT_PREVIOUS_KID", "")
    if prev_pem and prev_kid and prev_kid not in seen:
        keys.append(_public_jwk_from_private(prev_pem, prev_kid))
    return {"keys": keys}


def operator_cluster(claims: dict) -> str | None:
    """The cluster an operator token speaks for (``sub=operator:<cluster_id>``), else None."""
    sub = str(claims.get("sub", ""))
    return sub.split(":", 1)[1] if sub.startswith("operator:") else None


def require_operator_cluster(claims: dict, cluster_id: str | None, *, what: str) -> None:
    """Refuse an operator token that names a different cluster than the resource it touches.

    Every attached cluster holds a token signed by the same key; without this check any one of
    them could report status, inventory or samples for sessions and nodes on every other cluster.
    A token without an ``operator:`` subject is not cluster-scoped and passes.
    """
    mine = operator_cluster(claims)
    if mine is not None and cluster_id is not None and mine != cluster_id:
        raise Forbidden(
            f"operator token is not for this {what}'s cluster",
            {"token_cluster": mine, "cluster_id": cluster_id},
        )

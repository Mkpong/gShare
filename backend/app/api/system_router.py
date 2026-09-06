"""Instance-wide system settings.

One section today — branding — but the shape is meant to grow: every section is a key group in
``system_setting``, a read model, and a super-admin write endpoint. Branding is readable without a
token because the sign-in screen has to render the service name before anyone is authenticated.
"""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_principal
from app.auth.rbac import Principal
from app.core.errors import DomainError
from app.db.base import get_db
from app.db.models import SystemSetting
from app.domain.audit_service import AuditService

router = APIRouter(prefix="/system", tags=["system"])

# Setting keys. Grouped by section prefix so a future section is additive.
KEY_SERVICE_NAME = "branding.service_name"
KEY_LOGO = "branding.logo"
KEY_SIGNUP_MODE = "signup.mode"
KEY_SIGNUP_DOMAINS = "signup.allowed_domains"

DEFAULT_SERVICE_NAME = "gShare"

# Sign-up modes. "closed" is the default so an existing install does not start accepting
# strangers on upgrade.
SIGNUP_MODES = ("approval", "open", "closed")
DEFAULT_SIGNUP_MODE = "closed"
# A logo travels inline in the branding payload, which every page load reads, so it is deliberately
# small. 256 KB of base64 is roughly a 190 KB image — ample for a mark.
MAX_LOGO_CHARS = 256 * 1024
_LOGO_RE = re.compile(r"^data:image/(png|jpeg|webp|svg\+xml);base64,[A-Za-z0-9+/=\s]+$")


class _Unprocessable(DomainError):
    code, http = "validation_failed", 422


class BrandingOut(BaseModel):
    service_name: str
    logo: str | None = None      # data: URI, or null for the generated letter mark


class BrandingUpdate(BaseModel):
    # Absent means "leave as is"; for the logo, null means "remove and fall back to the letter mark".
    service_name: str | None = Field(default=None, min_length=1, max_length=40)
    logo: str | None = None
    clear_logo: bool = False


_ALL_KEYS = (KEY_SERVICE_NAME, KEY_LOGO, KEY_SIGNUP_MODE, KEY_SIGNUP_DOMAINS)


async def _read(db: AsyncSession) -> dict[str, str]:
    rows = (await db.execute(
        select(SystemSetting.key, SystemSetting.value).where(
            SystemSetting.key.in_(_ALL_KEYS)
        )
    )).all()
    return {k: v for k, v in rows}


async def _write(db: AsyncSession, key: str, value: str | None) -> None:
    row = await db.get(SystemSetting, key)
    if value is None:
        if row is not None:
            await db.delete(row)
        return
    if row is None:
        db.add(SystemSetting(key=key, value=value))
    else:
        row.value = value


@router.get("/branding", response_model=BrandingOut)
async def get_branding(db: AsyncSession = Depends(get_db)) -> BrandingOut:
    """Public: the sign-in screen renders this before anyone has a token."""
    cur = await _read(db)
    return BrandingOut(
        service_name=cur.get(KEY_SERVICE_NAME) or DEFAULT_SERVICE_NAME,
        logo=cur.get(KEY_LOGO) or None,
    )


@router.put("/branding", response_model=BrandingOut)
async def set_branding(
    body: BrandingUpdate,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> BrandingOut:
    """Set the service name and logo; super_admin only."""
    principal.require(action="system.branding.set")
    changed: dict[str, str] = {}

    if body.service_name is not None:
        name = body.service_name.strip()
        if not name:
            raise _Unprocessable("service name cannot be blank")
        await _write(db, KEY_SERVICE_NAME, name)
        changed["service_name"] = name

    if body.clear_logo:
        await _write(db, KEY_LOGO, None)
        changed["logo"] = "cleared"
    elif body.logo is not None:
        logo = body.logo.strip()
        if len(logo) > MAX_LOGO_CHARS:
            raise _Unprocessable("logo is too large")
        if not _LOGO_RE.match(logo):
            raise _Unprocessable("logo must be a PNG, JPEG, WebP, or SVG data URI")
        await _write(db, KEY_LOGO, logo)
        changed["logo"] = "set"

    if changed:
        await AuditService(db).record(
            actor=principal.user_id, action="system.branding.set", target="branding",
            result="ok", **changed,
        )
    await db.commit()
    return await get_branding(db)


# ── Sign-up policy ──────────────────────────────────────────────────────────────────────────
# Who may create their own account, from which email domains, and whether an administrator has
# to let them in first. The sign-in screen reads the public half to decide whether to offer the
# sign-up tab at all.


class SignupPolicyOut(BaseModel):
    mode: str                              # approval | open | closed
    allowed_domains: list[str] = []


class SignupPolicyUpdate(BaseModel):
    mode: str | None = None
    allowed_domains: list[str] | None = None


def _domains(raw: str | None) -> list[str]:
    return [d.strip().lower().lstrip("@") for d in (raw or "").split(",") if d.strip()]


async def signup_policy(db: AsyncSession) -> tuple[str, list[str]]:
    """(mode, allowed_domains) — the shape the sign-up handler needs."""
    cur = await _read(db)
    mode = cur.get(KEY_SIGNUP_MODE) or DEFAULT_SIGNUP_MODE
    if mode not in SIGNUP_MODES:
        mode = DEFAULT_SIGNUP_MODE
    return mode, _domains(cur.get(KEY_SIGNUP_DOMAINS))


@router.get("/signup", response_model=SignupPolicyOut)
async def get_signup_policy(db: AsyncSession = Depends(get_db)) -> SignupPolicyOut:
    """Public: the sign-in screen shows its sign-up tab only when this is not `closed`."""
    mode, domains = await signup_policy(db)
    return SignupPolicyOut(mode=mode, allowed_domains=domains)


@router.put("/signup", response_model=SignupPolicyOut)
async def set_signup_policy(
    body: SignupPolicyUpdate,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> SignupPolicyOut:
    """Set the sign-up policy; super_admin only."""
    principal.require(action="system.branding.set")
    mode, domains = await signup_policy(db)
    changed: dict[str, str] = {}

    if body.mode is not None:
        if body.mode not in SIGNUP_MODES:
            raise _Unprocessable("unknown sign-up mode")
        mode = body.mode
        changed["mode"] = mode

    if body.allowed_domains is not None:
        domains = _domains(",".join(body.allowed_domains))
        changed["allowed_domains"] = ",".join(domains) or "(any)"

    await _write(db, KEY_SIGNUP_MODE, mode)
    await _write(db, KEY_SIGNUP_DOMAINS, ",".join(domains) or None)
    if changed:
        await AuditService(db).record(
            actor=principal.user_id, action="system.signup.set", target="signup",
            result="ok", **changed,
        )
    await db.commit()
    return SignupPolicyOut(mode=mode, allowed_domains=domains)

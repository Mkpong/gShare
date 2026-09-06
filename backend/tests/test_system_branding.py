"""Branding settings: readable by anyone, writable by a super admin only."""
from __future__ import annotations

import pytest

from app.api.system_router import BrandingUpdate, get_branding, set_branding
from app.auth.rbac import Principal
from app.core.errors import DomainError, Forbidden

_PNG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUg=="


def _super() -> Principal:
    return Principal(user_id="usr_admin", global_roles={"super_admin"})


@pytest.mark.asyncio
async def test_defaults_before_anything_is_set(db):
    out = await get_branding(db)
    assert out.service_name == "gShare" and out.logo is None


@pytest.mark.asyncio
async def test_super_admin_sets_the_name_and_logo(db):
    out = await set_branding(BrandingUpdate(service_name="DKU GPU", logo=_PNG), _super(), db)
    assert out.service_name == "DKU GPU" and out.logo == _PNG
    assert (await get_branding(db)).service_name == "DKU GPU"


@pytest.mark.asyncio
async def test_clearing_the_logo_falls_back_to_the_letter_mark(db):
    await set_branding(BrandingUpdate(logo=_PNG), _super(), db)
    out = await set_branding(BrandingUpdate(clear_logo=True), _super(), db)
    assert out.logo is None


@pytest.mark.asyncio
async def test_a_member_cannot_write(db):
    with pytest.raises(Forbidden):
        await set_branding(BrandingUpdate(service_name="nope"),
                           Principal(user_id="usr_x", memberships={}), db)


@pytest.mark.asyncio
async def test_a_non_image_payload_is_rejected(db):
    with pytest.raises(DomainError):
        await set_branding(BrandingUpdate(logo="data:text/html;base64,PHNjcmlwdD4="), _super(), db)
    with pytest.raises(DomainError):
        await set_branding(BrandingUpdate(logo="data:image/png;base64," + "A" * (256 * 1024)),
                           _super(), db)

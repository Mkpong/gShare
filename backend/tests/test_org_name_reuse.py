"""A deleted organization's name can be used again.

Organizations are soft-deleted; a plain UNIQUE on `name` kept counting the deleted row, so the
name was reserved forever and re-creating it answered 409 against a row nobody could see.
"""
from __future__ import annotations

import pytest

from app.api.groups_router import OrgCreate, create_organization, delete_organization
from app.auth.rbac import Principal


@pytest.mark.asyncio
async def test_an_organization_name_is_free_again_after_deletion(db):
    su = Principal(user_id="usr_su", global_roles={"super_admin"})
    first = await create_organization(OrgCreate(name="Nexus AI Lab"), su, db)
    await delete_organization(first["id"], su, db)
    second = await create_organization(OrgCreate(name="Nexus AI Lab"), su, db)
    assert second["id"] != first["id"]
    assert second["name"] == "Nexus AI Lab"

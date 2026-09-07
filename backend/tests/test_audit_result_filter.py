"""``GET /audit-logs?result=`` narrows the list (and the CSV) to one outcome — "what failed today"."""
from __future__ import annotations

import pytest

from app.api.audit_router import _scoped_query
from app.api.users_router import _LoginRequest, auth_login
from app.auth.rbac import Principal
from app.core import ids
from app.core.errors import Unauthenticated
from app.core.passwords import hash_password
from app.db.models import User

ROOT = Principal(user_id="usr_root", global_role="super_admin", global_roles={"super_admin"})


class _Req:
    headers = {"x-forwarded-for": "10.0.0.9"}
    client = None


@pytest.mark.asyncio
async def test_result_filter_narrows_to_one_outcome(db):
    db.add(User(id=ids.new("user"), email="ce-user01@example.edu", name="u",
                password_hash=hash_password("right-pass-1"), status="active"))
    await db.commit()
    with pytest.raises(Unauthenticated):
        await auth_login(_LoginRequest(email="ce-user01@example.edu", password="wrong-pass-1"), _Req(), db)
    await auth_login(_LoginRequest(email="ce-user01@example.edu", password="right-pass-1"), _Req(), db)

    async def rows(result):
        q = _scoped_query(ROOT, None, None, "auth.login", None, None, None, result)
        return list((await db.scalars(q)).all())

    assert sorted(r.result for r in await rows(None)) == ["failed", "ok"]
    assert [r.result for r in await rows("failed")] == ["failed"]
    assert [r.result for r in await rows("ok")] == ["ok"]
    assert await rows("nonsense") == []

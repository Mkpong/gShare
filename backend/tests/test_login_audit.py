"""Every sign-in attempt lands in the audit log, success and failure alike."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.api.users_router import _LoginRequest, auth_login
from app.core import ids
from app.core.errors import Unauthenticated
from app.db.models import AuditLog, User


class _Req:
    headers = {"x-forwarded-for": "10.0.0.9"}
    client = None


async def _rows(db) -> list[AuditLog]:
    return list((await db.execute(
        select(AuditLog).where(AuditLog.action == "auth.login").order_by(AuditLog.created_at)
    )).scalars())


@pytest.mark.asyncio
async def test_unknown_account_is_recorded_as_failed(db):
    with pytest.raises(Unauthenticated):
        await auth_login(_LoginRequest(email="nobody@dankook.ac.kr", password="whatever1"),
                         _Req(), db)
    rows = await _rows(db)
    assert len(rows) == 1
    assert rows[0].result == "failed"
    assert rows[0].actor == "nobody@dankook.ac.kr"
    assert rows[0].detail["reason"] == "unknown_account"
    assert rows[0].detail["ip"] == "10.0.0.9"


@pytest.mark.asyncio
async def test_wrong_password_and_then_success_are_both_recorded(db):
    from app.core.passwords import hash_password
    user = User(id=ids.new("user"), email="ce-user01@dankook.ac.kr", name="u",
                password_hash=hash_password("correct-horse"), status="active")
    async with db.begin():
        db.add(user)

    with pytest.raises(Unauthenticated):
        await auth_login(_LoginRequest(email=user.email, password="wrong-one"), _Req(), db)
    await auth_login(_LoginRequest(email=user.email, password="correct-horse"), _Req(), db)

    rows = await _rows(db)
    assert [r.result for r in rows] == ["failed", "ok"]
    assert rows[0].detail["reason"] == "bad_password"
    assert all(r.actor == user.id for r in rows)


@pytest.mark.asyncio
async def test_a_suspended_account_is_recorded_as_failed(db):
    from app.core.passwords import hash_password
    user = User(id=ids.new("user"), email="gone@dankook.ac.kr", name="g",
                password_hash=hash_password("correct-horse"), status="suspended")
    async with db.begin():
        db.add(user)
    with pytest.raises(Unauthenticated):
        await auth_login(_LoginRequest(email=user.email, password="correct-horse"), _Req(), db)
    rows = await _rows(db)
    assert rows[0].result == "failed" and rows[0].detail["reason"] == "account_disabled"

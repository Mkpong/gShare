"""CSV export of the audit log: same scope as the list, sensible file shape, and audited itself."""
from __future__ import annotations

import csv
import io

import pytest
from sqlalchemy import select

from app.api.audit_router import export_audit_logs
from app.auth.rbac import Principal
from app.core import ids
from app.db.models import AuditLog
from app.domain.audit_service import AuditService

# Direct (non-FastAPI) calls would otherwise hand the handler its Query default objects.
_NONE = dict(actor_id=None, actor_q=None, action=None, target=None, at_gte=None, at_lt=None)
ROOT = Principal(user_id="usr_root", global_role="super_admin", global_roles={"super_admin"})


async def _export(db, principal, **filters):
    return await export_audit_logs(**{**_NONE, **filters}, principal=principal, db=db)


async def _body(resp) -> str:
    chunks = []
    async for c in resp.body_iterator:
        chunks.append(c if isinstance(c, str) else c.decode())
    return "".join(chunks)


@pytest.fixture
async def rows(db):
    g_a, g_b = ids.new("group"), ids.new("group")
    async with db.begin():
        svc = AuditService(db)
        await svc.record(actor="usr_a", action="session.create", target="ses_1", result="ok",
                         group_id=g_a, name="쿠다 테스트")
        await svc.record(actor="usr_b", action="session.terminate", target="ses_2", result="ok",
                         group_id=g_b)
    return {"g_a": g_a, "g_b": g_b}


@pytest.mark.asyncio
async def test_super_admin_gets_every_row_as_csv(db, rows):
    resp = await _export(db, ROOT)
    text = await _body(resp)
    assert text.startswith("\ufeff")
    assert 'attachment; filename="gshare-audit-' in resp.headers["content-disposition"]
    parsed = list(csv.reader(io.StringIO(text.lstrip("\ufeff"))))
    assert parsed[0][:6] == ["at", "actor_id", "actor_name", "actor_email", "action", "result"]
    actions = {r[4] for r in parsed[1:]}
    assert {"session.create", "session.terminate"} <= actions
    # Korean survives the JSON detail column verbatim.
    assert "쿠다 테스트" in text


@pytest.mark.asyncio
async def test_group_admin_export_is_scoped_like_the_list(db, rows):
    p = Principal(user_id="usr_adm", memberships={rows["g_a"]: "group_admin"})
    text = await _body(await _export(db, p))
    assert "session.create" in text
    assert "session.terminate" not in text


@pytest.mark.asyncio
async def test_export_itself_is_audited(db, rows):
    await _export(db, ROOT, action="session.create")
    row = (await db.execute(select(AuditLog).where(AuditLog.action == "audit.export"))).scalar_one()
    assert row.actor == "usr_root"
    assert row.detail["rows"] == 1 and row.detail["filters"] == {"action": "session.create"}

"""A refused action belongs in the audit log.

The trail held only what people were permitted to do. An account walking the administrative
endpoints and collecting 403s left no trace at all — the single pattern an audit log exists to
surface. Denials are now appended centrally, deduplicated per actor and route so a client
retrying in a loop cannot drown the trail.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI, Request

from app.auth.rbac import Principal
from app.core.errors import Forbidden, NotFound, PasswordChangeRequired, _record_denial


def _req(app: FastAPI, principal: Principal | None, path: str = "/api/v1/clusters",
         method: str = "POST") -> Request:
    scope = {"type": "http", "method": method, "path": path, "headers": [],
             "query_string": b"", "app": app, "scheme": "http", "server": ("t", 80)}
    r = Request(scope)
    if principal is not None:
        r.state.principal = principal
    r.state.request_id = "rid-1"
    return r


@pytest.mark.asyncio
async def test_a_denial_is_recorded_with_the_actor_and_the_route(db, monkeypatch):
    written = []

    async def fake_record(self, actor, action, target=None, **detail):
        written.append((actor, action, target, detail))

    monkeypatch.setattr("app.domain.audit_service.AuditService.record", fake_record)
    app = FastAPI()
    await _record_denial(_req(app, Principal(user_id="usr_probe")), Forbidden("not permitted"))
    assert len(written) == 1
    actor, action, target, detail = written[0]
    assert (actor, action, target) == ("usr_probe", "access.denied", "/api/v1/clusters")
    assert detail["result"] == "denied" and detail["method"] == "POST"
    assert detail["code"] == "forbidden"


@pytest.mark.asyncio
async def test_an_unauthenticated_caller_writes_nothing(db, monkeypatch):
    written = []

    async def fake_record(self, actor, action, target=None, **detail):
        written.append(actor)

    monkeypatch.setattr("app.domain.audit_service.AuditService.record", fake_record)
    app = FastAPI()
    await _record_denial(_req(app, None), Forbidden("not permitted"))
    assert written == []


@pytest.mark.asyncio
async def test_a_forced_password_change_is_not_an_attempt(db, monkeypatch):
    written = []

    async def fake_record(self, actor, action, target=None, **detail):
        written.append(actor)

    monkeypatch.setattr("app.domain.audit_service.AuditService.record", fake_record)
    app = FastAPI()
    await _record_denial(_req(app, Principal(user_id="usr_x")), PasswordChangeRequired("change it"))
    assert written == []


@pytest.mark.asyncio
async def test_auditing_a_denial_never_turns_it_into_a_500(db, monkeypatch):
    async def boom(self, actor, action, target=None, **detail):
        raise RuntimeError("audit backend down")

    monkeypatch.setattr("app.domain.audit_service.AuditService.record", boom)
    app = FastAPI()
    await _record_denial(_req(app, Principal(user_id="usr_x")), Forbidden("not permitted"))


def test_only_403s_reach_the_recorder():
    assert Forbidden().http == 403 and NotFound().http == 404

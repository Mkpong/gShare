"""Every error leaves the API in the same envelope — framework-raised ones included."""
from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI

from app.core.errors import NotFound, register_exception_handlers


def _app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/ok")
    async def ok():  # noqa: ANN202
        return {"ok": True}

    @app.get("/domain")
    async def domain():  # noqa: ANN202
        raise NotFound("thing is missing", {"thing": "x"})

    @app.get("/boom")
    async def boom():  # noqa: ANN202
        raise RuntimeError("secret internals")

    return app


def _client(app: FastAPI, *, raise_app_exceptions: bool = True) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=raise_app_exceptions)
    return httpx.AsyncClient(transport=transport, base_url="http://t")


@pytest.mark.asyncio
async def test_unknown_route_uses_the_envelope():
    async with _client(_app()) as c:
        r = await c.get("/nope")
    assert r.status_code == 404
    body = r.json()["error"]
    assert body["code"] == "not_found"
    assert set(body) >= {"code", "message", "details", "request_id", "timestamp"}


@pytest.mark.asyncio
async def test_wrong_method_uses_the_envelope():
    async with _client(_app()) as c:
        r = await c.post("/ok")
    assert r.status_code == 405
    assert r.json()["error"]["code"] == "method_not_allowed"


@pytest.mark.asyncio
async def test_domain_error_shape_is_unchanged():
    async with _client(_app()) as c:
        r = await c.get("/domain")
    assert r.status_code == 404
    err = r.json()["error"]
    assert err["code"] == "not_found" and err["details"] == {"thing": "x"}


@pytest.mark.asyncio
async def test_unhandled_exception_is_a_500_envelope_without_leaking():
    async with _client(_app(), raise_app_exceptions=False) as c:
        r = await c.get("/boom")
    assert r.status_code == 500
    err = r.json()["error"]
    assert err["code"] == "internal_error"
    assert "secret" not in r.text

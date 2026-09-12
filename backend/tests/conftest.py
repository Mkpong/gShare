"""pytest fixtures.

Testcontainers Postgres/Redis are heavy and unavailable in CI/sandbox. For the domain-logic suite
we bind an in-memory async SQLite engine instead: the CreditEngine / SchedulerService logic under
test is pure SQL + Python (FOR UPDATE serialization is a Postgres runtime concern, not a schema
one), so SQLite is sufficient to exercise idempotency, differencing, and gate ordering.
Postgres-only column types (JSONB) and partial-UNIQUE indexes are adapted/ignored for SQLite below
so ``Base.metadata.create_all`` succeeds.

The cluster handoff is injected as a Fake port so tests can assert the desired payload without a
real K8s cluster. Pod builder/reconcile unit tests live in the operator.
"""
from __future__ import annotations

import os

# Inject a test HS256 signing key before the settings singleton is built, which the app.* imports
# below trigger. Production code has no default (config.USER_JWT_SECRET is ""), so the tests pin one
# here.
os.environ.setdefault("GSHARE_USER_JWT_SECRET", "test-secret-not-for-prod")

import subprocess
import sys
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.pool import StaticPool

from app.db.base import Base

# Opt-in Postgres backend (hypothesis H-7: the SQLite fixture cannot exercise FOR UPDATE, CHECK
# constraints as migrated, enforced foreign keys, or real concurrency). Set
# ``GSHARE_TEST_DATABASE_URL`` to an asyncpg URL and the ``db`` fixture binds to that database
# instead: the schema is created ONCE per session with ``alembic upgrade head`` (the production
# path, not create_all) and every table is truncated after each test. Unset, nothing below
# changes the SQLite behaviour.
PG_TEST_URL = os.environ.get("GSHARE_TEST_DATABASE_URL")


# SQLite has no JSONB; render it as plain JSON (text-backed) so create_all works off the same
# models the production Postgres schema uses. This is a test-only dialect shim.
@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):  # noqa: ANN001, ANN202
    return "JSON"


@pytest.fixture(scope="session")
def pg_schema() -> str | None:
    """Migrate the opt-in Postgres test database to head once per session (``alembic upgrade
    head`` in a subprocess so env.py's own asyncio.run stays out of the test loop), and start
    from empty tables. Returns the URL, or None when the SQLite default is in force."""
    if not PG_TEST_URL:
        return None
    backend_dir = Path(__file__).resolve().parents[1]
    env = {**os.environ, "GSHARE_DATABASE_URL": PG_TEST_URL}
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=backend_dir, env=env, check=True, capture_output=True,
    )
    return PG_TEST_URL


async def _truncate_all(engine) -> None:
    names = ", ".join(f'"{t.name}"' for t in reversed(Base.metadata.sorted_tables))
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE TABLE {names} CASCADE"))


@pytest_asyncio.fixture
async def db_engine(pg_schema):
    """The engine behind ``db``. On Postgres this is a real pool, so a test may open several
    independent sessions on it (concurrency tests); on SQLite it is the single shared in-memory
    connection."""
    if pg_schema:
        engine = create_async_engine(pg_schema, pool_size=20, max_overflow=20)
        await _truncate_all(engine)
        try:
            yield engine
        finally:
            await _truncate_all(engine)
            await engine.dispose()
        return
    # StaticPool shares one connection across every session, so the in-memory database survives
    # between them and the connection stays consistent after an exception inside begin(). With the
    # default pool the async adapter can be left in a broken state.
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def db(db_engine) -> AsyncSession:
    """AsyncSession bound to an in-memory SQLite (default) or the opt-in Postgres (``db_engine``).

    SQLite: a single connection-pooled in-memory engine; schema created via run_sync(create_all).
    Yields one session per test (rolled back / disposed at teardown). Postgres partial-UNIQUE
    indexes carry a ``postgresql_where`` that SQLite simply ignores, which is fine for these logic
    tests.
    """
    sessionmaker = async_sessionmaker(db_engine, expire_on_commit=False)
    session = sessionmaker()
    try:
        yield session
    finally:
        await session.close()


class FakeHandoff:
    """Captures the last desired payload instead of applying a real CR.

    Records the (sess, req) it was handed and the serialized GShareSession spec so scheduler tests
    can assert the desired-state handoff happened with the right shape — without a live cluster.
    """

    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.last_sess = None
        self.last_req = None
        self.last_spec: dict | None = None

    async def apply_desired(self, sess, req) -> None:
        from app.cluster.crd import GShareSessionCRD

        # Pure serialization (no db / no cluster) — mirrors Handoff.apply_desired's spec build.
        self.last_sess = sess
        self.last_req = req
        self.last_spec = GShareSessionCRD().to_session_spec(sess, req)
        self.calls.append((sess, req, self.last_spec))


@pytest.fixture
def fake_handoff() -> FakeHandoff:
    return FakeHandoff()


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    """Replace get_redis's singleton with an in-memory FakeRedis so the tests need no real Redis.

    SchedulerService.create_session uses Redis for the idempotency key (SET NX) and the queue (ZADD
    and ZPOPMAX). Injecting fakeredis instead of a testcontainers Redis keeps the unit tests
    self-contained on a laptop or in a single container.
    """
    from fakeredis.aioredis import FakeRedis

    import app.core.redis as redis_mod

    client = FakeRedis(decode_responses=True)
    monkeypatch.setattr(redis_mod, "_pool", client, raising=False)
    yield client
    monkeypatch.setattr(redis_mod, "_pool", None, raising=False)

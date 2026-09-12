"""Fixture seeding that satisfies the schema's foreign keys.

SQLite does not enforce foreign keys, so a fixture could happily insert a Session whose
``owner_user_id`` points at a user that was never created. Postgres does enforce them, and the
same fixtures then fail with ``ForeignKeyViolationError``. Two distinct problems show up:

1. **Missing parents.** An id was minted with ``ids.new(...)`` and nothing was inserted behind it.
2. **Insert order.** These models deliberately carry no ``relationship()``, so SQLAlchemy's unit of
   work has no dependency graph to sort by: a single ``add_all([device, node, cluster])`` is
   flushed in exactly that order and the child INSERT runs first.

``seed(db, rows)`` fixes both: it orders the INSERTs by table dependency and creates a minimal
parent row for every foreign key that would otherwise dangle (recursively — a placeholder group
gets a placeholder organization). Only rows handed to it are inspected, so production code paths
under test keep hitting the real constraints.

Use the explicit ``*_row`` factories when a test needs a parent with particular contents; use
``seed`` for everything else.
"""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import inspect, select

from app.core import ids
from app.db import models
from app.db.base import Base

__all__ = [
    "seed",
    "add_ordered",
    "cluster_row",
    "user_row",
    "org_row",
    "group_row",
    "wallet_row",
    "node_row",
]


# ── explicit factories ────────────────────────────────────────────────────────────────────────
def cluster_row(cluster_id: str | None = None, **kw: Any) -> models.Cluster:
    cluster_id = cluster_id or ids.new("cluster")
    base = dict(
        id=cluster_id, name=f"c-{cluster_id}", api_server="https://k8s.test", runtime="k8s",
        kubeconfig_secret_ref=f"secret-{cluster_id}", status="ready",
    )
    base.update(kw)
    return models.Cluster(**base)


def user_row(user_id: str | None = None, **kw: Any) -> models.User:
    user_id = user_id or ids.new("user")
    base = dict(id=user_id, email=f"{user_id}@fixture.local", name=user_id)
    base.update(kw)
    return models.User(**base)


def org_row(org_id: str | None = None, **kw: Any) -> models.Organization:
    org_id = org_id or ids.new("org")
    base = dict(id=org_id, name=f"org-{org_id}")
    base.update(kw)
    return models.Organization(**base)


def group_row(group_id: str | None = None, org_id: str | None = None,
              **kw: Any) -> models.Project:
    group_id = group_id or ids.new("group")
    base = dict(id=group_id, org_id=org_id or ids.new("org"), name=f"g-{group_id}")
    base.update(kw)
    return models.Project(**base)


def wallet_row(wallet_id: str | None = None, *, owner_type: str = "user",
               owner_id: str | None = None, **kw: Any) -> models.CreditWallet:
    wallet_id = wallet_id or ids.new("wallet")
    base = dict(id=wallet_id, owner_type=owner_type, owner_id=owner_id or ids.new("user"))
    base.update(kw)
    return models.CreditWallet(**base)


def node_row(node_id: str | None = None, cluster_id: str | None = None,
             **kw: Any) -> models.GpuNode:
    node_id = node_id or ids.new("node")
    base = dict(
        id=node_id, cluster_id=cluster_id or ids.new("cluster"), hostname=f"h-{node_id}",
        status="ready",
    )
    base.update(kw)
    return models.GpuNode(**base)


# ── placeholder parents, one builder per referenced table ─────────────────────────────────────
def _offering(i: str) -> models.Offering:
    # Deliberately minimal: a placeholder must not add a constraint the fixture never asked for
    # (a gpu_model here would make the scheduler's model filter reject the fixture's own cards).
    return models.Offering(id=i, name=f"off-{i}", resource_class="gpu")


def _image(i: str) -> models.Image:
    return models.Image(id=i, name=f"img-{i}")


def _device(i: str) -> models.GpuDevice:
    return models.GpuDevice(id=i, node_id=ids.new("node"), cluster_id=ids.new("cluster"),
                            model="A100", gpu_uuid=f"GPU-{i}", total_mem_mb=16000,
                            status="ready", mode="fractional")


def _session(i: str) -> models.Session:
    return models.Session(id=i, owner_user_id=ids.new("user"), cluster_id=ids.new("cluster"),
                          offering_id=ids.new("offering"), image_id=ids.new("image"),
                          resource_class="gpu", mode="fractional", status="running")


def _volume(i: str) -> models.StorageVolume:
    return models.StorageVolume(id=i, scope="user", scope_id=ids.new("user"), type="home",
                                access_mode="RWO")


def _pool(i: str) -> models.NodePool:
    return models.NodePool(id=i, cluster_id=ids.new("cluster"), name=f"pool-{i}", kind="shared")


def _storage_pool(i: str) -> models.StoragePool:
    return models.StoragePool(id=i, cluster_id=ids.new("cluster"), name=f"sp-{i}")


def _budget(i: str) -> models.Budget:
    return models.Budget(id=i, scope="user", scope_id=ids.new("user"), period="monthly",
                         period_start=datetime.now(UTC), limit_credit=Decimal("0"))


def _webhook(i: str) -> models.WebhookSubscription:
    return models.WebhookSubscription(id=i, scope="global", url="https://hook.test", events=[])


_BUILDERS = {
    "user": user_row,
    "organization": org_row,
    "group": group_row,
    "cluster": cluster_row,
    "gpu_node": node_row,
    "credit_wallet": wallet_row,
    "offering": _offering,
    "image": _image,
    "gpu_device": _device,
    "session": _session,
    "storage_volume": _volume,
    "node_pool": _pool,
    "storage_pool": _storage_pool,
    "budget": _budget,
    "webhook_subscription": _webhook,
}

_TABLE_ORDER = {t.name: n for n, t in enumerate(Base.metadata.sorted_tables)}


def _fk_refs(obj: Any) -> list[tuple[str, str]]:
    """(parent table, parent id) for every non-null foreign key value carried by ``obj``."""
    table = inspect(type(obj)).local_table
    out: list[tuple[str, str]] = []
    for col in table.columns:
        for fk in col.foreign_keys:
            value = getattr(obj, col.name, None)
            if value is not None:
                out.append((fk.column.table.name, value))
    return out


def _pk_of(obj: Any) -> tuple[str, str]:
    table = inspect(type(obj)).local_table
    return table.name, getattr(obj, next(iter(table.primary_key.columns)).name)


def _fk_values(obj: Any) -> dict[str, Any]:
    """{column name: value} for the non-null foreign keys ``obj`` carries."""
    table = inspect(type(obj)).local_table
    return {
        c.name: getattr(obj, c.name, None)
        for c in table.columns
        if c.foreign_keys and getattr(obj, c.name, None) is not None
    }


def _inherit(obj: Any, ctx: dict[str, Any]) -> None:
    """Give a placeholder the same parents as the row that asked for it.

    A placeholder gpu_node conjured for a GpuDevice must sit in the device's cluster, not in a
    cluster of its own, or a scheduler query joining the two stops matching.
    """
    table = inspect(type(obj)).local_table
    for col in table.columns:
        if col.foreign_keys and ctx.get(col.name) is not None:
            setattr(obj, col.name, ctx[col.name])


async def _fill_parents(db, rows: list[Any]) -> list[Any]:
    """Return placeholder parents for the foreign keys ``rows`` reference but nobody provides."""
    have: set[tuple[str, str]] = {_pk_of(r) for r in rows}
    # Rows the caller already put in the session (pending or already persistent) count as provided:
    # conjuring a placeholder for one of those would collide on its primary key.
    for known in list(db.new) + list(db.identity_map.values()):
        try:
            have.add(_pk_of(known))
        except Exception:      # not a mapped row we can key
            pass
    made: list[Any] = []
    pending = list(rows)
    asked: set[tuple[str, str]] = set()
    while pending:
        requests: dict[tuple[str, str], dict[str, Any]] = {}
        for obj in pending:
            ctx = _fk_values(obj)
            for ref in _fk_refs(obj):
                if ref not in have and ref not in asked:
                    requests.setdefault(ref, ctx)
        if not requests:
            break
        asked |= set(requests)
        by_table: dict[str, set[str]] = {}
        for table_name, value in requests:
            by_table.setdefault(table_name, set()).add(value)
        present: set[tuple[str, str]] = set()
        for table_name, values in by_table.items():
            table = Base.metadata.tables[table_name]
            pk = next(iter(table.primary_key.columns))
            for found in (await db.scalars(select(pk).where(pk.in_(values)))).all():
                present.add((table_name, found))
        pending = []
        for (table_name, value), ctx in sorted(requests.items()):
            have.add((table_name, value))
            builder = _BUILDERS.get(table_name)
            if (table_name, value) in present or builder is None:
                continue           # already in the database, or no placeholder shape is known:
            obj = builder(value)   # let the real constraint speak instead of inventing a row
            _inherit(obj, ctx)
            made.append(obj)
            pending.append(obj)
    return made


def _ordered(rows: list[Any]) -> list[list[Any]]:
    """Group rows per table, in the schema's topological table order."""
    by_table: dict[str, list[Any]] = {}
    for obj in rows:
        by_table.setdefault(inspect(type(obj)).local_table.name, []).append(obj)
    return [by_table[name] for name in sorted(by_table, key=lambda n: _TABLE_ORDER[n])]


async def add_ordered(db, rows) -> None:
    """Insert ``rows`` in dependency order inside the caller's transaction — flush, no commit.

    The flushing counterpart of :func:`seed`, for fixtures that deliberately stay in the
    transaction the test goes on to use.
    """
    rows = [r for r in rows if r is not None]
    made = await _fill_parents(db, rows)
    for wave in _ordered(made + rows):
        db.add_all(wave)
        await db.flush()


async def seed(db, rows) -> None:
    """Insert ``rows`` (plus any missing foreign-key parents) and commit.

    Replaces ``async with db.begin(): db.add_all(rows)`` in fixtures whose rows reference ids
    that were never inserted, or that are not already in parent-before-child order.
    """
    rows = [r for r in rows if r is not None]
    made = await _fill_parents(db, rows)
    if db.in_transaction():
        await db.commit()                # close the transaction the lookups above autobegan
    async with db.begin():
        for wave in _ordered(made + rows):
            db.add_all(wave)
            await db.flush()

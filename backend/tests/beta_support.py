"""Shared helpers for the beta-test suites (test_beta_*).

Every referenced row (cluster, node, offering, image, user) is created for real, so the same
tests run unchanged on Postgres, where the foreign keys are enforced, and on the SQLite fixture.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select

from app.core import ids
from app.db.models import (
    Cluster,
    CreditTransaction,
    CreditWallet,
    GpuDevice,
    GpuNode,
    Image,
    Offering,
    Session,
    User,
)

RESERVED_ONLY = ("hold", "refund", "settle")


@dataclass
class Refs:
    cluster_id: str
    node_id: str
    offering_id: str
    image_id: str
    user_id: str


async def make_refs(db, *, rate: str = "60", gpu_mem_mb: int = 16000,
                    total_mem_mb: int = 16000, devices: int = 0) -> Refs:
    """Create one cluster/node/offering/image/user (and ``devices`` ready fractional cards)."""
    cluster = Cluster(id=ids.new("cluster"), name=ids.new("cluster"), api_server="https://k",
                      runtime="k8s", kubeconfig_secret_ref="ref", status="ready")
    node = GpuNode(id=ids.new("node"), cluster_id=cluster.id, hostname=ids.new("node"),
                   status="ready", cpu=64, mem=256, disk=1000)
    offering = Offering(id=ids.new("offering"), name="A100-frac", resource_class="gpu",
                        gpu_model="A100", gpu_mem_mb=gpu_mem_mb, gpu_cores=100,
                        credit_per_hour=Decimal(rate))
    image = Image(id=ids.new("image"), name="pytorch", registry=ids.new("image"))
    user = User(id=ids.new("user"), email=f"{ids.new('user')}@t.local", name="u")
    async with db.begin():
        db.add_all([cluster, node, offering, image, user])
        await db.flush()   # no relationship() on the models: order the FK parents explicitly
        for _ in range(devices):
            db.add(GpuDevice(id=ids.new("device"), node_id=node.id, cluster_id=cluster.id,
                             model="A100", gpu_uuid=ids.new("device"), total_mem_mb=total_mem_mb,
                             status="ready", mode="fractional"))
    return Refs(cluster.id, node.id, offering.id, image.id, user.id)


async def make_user(db) -> str:
    u = User(id=ids.new("user"), email=f"{ids.new('user')}@t.local", name="u")
    async with db.begin():
        db.add(u)
    return u.id


async def make_wallet(db, balance: str, reserved: str = "0", *, owner_type: str = "user",
                      owner_id: str | None = None, grant: str = "0") -> str:
    """Create a wallet and return its id (a plain string survives rollbacks and expiry)."""
    if owner_id is None:
        owner_id = await make_user(db) if owner_type == "user" else ids.new(owner_type)
    w = CreditWallet(
        id=ids.new("wallet"), owner_type=owner_type, owner_id=owner_id,
        balance=Decimal(balance), reserved=Decimal(reserved), monthly_grant=Decimal(grant),
    )
    async with db.begin():
        db.add(w)
    return w.id


async def make_gpu_session(db, refs: Refs, wallet_id: str, rate: str, started: datetime | None,
                           *, status: str = "running", gpu_mem_mb: int = 10000,
                           gpu_cores: int = 100, total_mem_mb: int = 20000,
                           owner_id: str | None = None) -> Session:
    sess = Session(
        id=ids.new("session"), owner_user_id=owner_id or refs.user_id,
        cluster_id=refs.cluster_id, offering_id=refs.offering_id, image_id=refs.image_id,
        resource_class="gpu", mode="fractional", gpu_mem_mb=gpu_mem_mb, gpu_cores=gpu_cores,
        device_total_mem_mb=total_mem_mb, billing_wallet_id=wallet_id, status=status,
        credit_per_hour_snapshot=Decimal(rate), started_at=started,
    )
    async with db.begin():
        db.add(sess)
    return sess


async def wallet_state(db, wallet_id: str) -> tuple[Decimal, Decimal]:
    row = (await db.execute(
        select(CreditWallet.balance, CreditWallet.reserved).where(CreditWallet.id == wallet_id)
    )).one()
    await db.commit()   # close the autobegun read so the next begin() is clean
    return row.balance, row.reserved


async def ledger_rows(db, wallet_id: str, ref: str | None = None) -> list[CreditTransaction]:
    stmt = select(CreditTransaction).where(CreditTransaction.wallet_id == wallet_id)
    if ref is not None:
        stmt = stmt.where(CreditTransaction.ref == ref)
    rows = list((await db.scalars(stmt.order_by(CreditTransaction.created_at,
                                                CreditTransaction.id))).all())
    await db.commit()
    return rows


async def check_ledger(db, wallet_id: str, initial_balance: Decimal) -> None:
    """Ledger sum == balance delta; balance_after snapshot == balance; 0 <= reserved <= balance.

    hold/refund/settle rows move ``reserved`` only, so they are excluded from the balance sum.
    """
    db.expunge_all()
    balance, reserved = await wallet_state(db, wallet_id)
    rows = await ledger_rows(db, wallet_id)
    moved = sum((r.amount for r in rows if r.type not in RESERVED_ONLY), Decimal("0"))
    assert balance == initial_balance + moved, (balance, initial_balance, moved, rows)
    if rows:
        assert rows[-1].balance_after == balance, (rows[-1].type, rows[-1].balance_after, balance)
    assert Decimal("0") <= reserved <= balance, (balance, reserved)

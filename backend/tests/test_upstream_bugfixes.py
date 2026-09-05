"""Regression tests for the field-reported defects (preview denominator, offering alignment, storage panel)."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.api.schemas.internal import OperatorGpuDeviceUpsert
from app.cluster.inventory_sync import align_offering_models
from app.core import ids
from app.db.models import AuditLog, GpuDevice, GpuNode, Offering


def _offering(name, model, mem=98304) -> Offering:
    return Offering(id=ids.new("offering"), name=name, resource_class="gpu", gpu_model=model, gpu_mem_mb=mem,
                    cpu=4, mem_gb=8, disk_gb=50, credit_per_hour=300, status="active")


def _device(node_id, model) -> GpuDevice:
    return GpuDevice(id=ids.new("device"), node_id=node_id, cluster_id="clu_t", model=model,
                     gpu_uuid=ids.new("dev"), total_mem_mb=97887, total_cores=100, status="ready")


@pytest.fixture
async def node(db):
    n = GpuNode(id=ids.new("node"), cluster_id="clu_t", hostname="gpu-a", status="ready")
    async with db.begin():
        db.add(n)
    return n


@pytest.mark.asyncio
async def test_seeded_marketing_name_adopts_the_reported_sku(db, node):
    off = _offering("RTX PRO 6000", "NVIDIA RTX PRO 6000 Blackwell")
    async with db.begin():
        db.add(off)
    async with db.begin():
        await align_offering_models(db, "NVIDIA RTX PRO 6000 Blackwell Max-Q Workstation Edition")
    db.expunge_all()
    assert (await db.get(Offering, off.id)).gpu_model == "NVIDIA RTX PRO 6000 Blackwell Max-Q Workstation Edition"
    audit = (await db.execute(select(AuditLog).where(AuditLog.action == "offering.align_model"))).scalar_one()
    assert audit.detail["previous"] == "NVIDIA RTX PRO 6000 Blackwell"


@pytest.mark.asyncio
@pytest.mark.parametrize("reported", [
    "NVIDIA RTX PRO 6000 Blackwell",                 # already exact: nothing to do
    "NVIDIA RTX PRO 60000 Ultra",                    # not a word-boundary prefix
    "unknown",
])
async def test_alignment_leaves_other_cases_alone(db, node, reported):
    off = _offering("RTX PRO 6000", "NVIDIA RTX PRO 6000 Blackwell")
    async with db.begin():
        db.add(off)
    async with db.begin():
        await align_offering_models(db, reported)
    db.expunge_all()
    assert (await db.get(Offering, off.id)).gpu_model == "NVIDIA RTX PRO 6000 Blackwell"


@pytest.mark.asyncio
async def test_alignment_never_guesses_between_two_candidates(db, node):
    a = _offering("A", "NVIDIA RTX PRO 6000")
    b = _offering("B", "NVIDIA RTX PRO 6000 Blackwell")
    async with db.begin():
        db.add_all([a, b])
    async with db.begin():
        await align_offering_models(db, "NVIDIA RTX PRO 6000 Blackwell Max-Q Workstation Edition")
    db.expunge_all()
    assert (await db.get(Offering, a.id)).gpu_model == "NVIDIA RTX PRO 6000"
    assert (await db.get(Offering, b.id)).gpu_model == "NVIDIA RTX PRO 6000 Blackwell"


@pytest.mark.asyncio
async def test_alignment_keeps_a_name_other_cards_still_report(db, node):
    off = _offering("RTX PRO 6000", "NVIDIA RTX PRO 6000 Blackwell")
    async with db.begin():
        db.add_all([off, _device(node.id, "NVIDIA RTX PRO 6000 Blackwell")])
    async with db.begin():
        await align_offering_models(db, "NVIDIA RTX PRO 6000 Blackwell Max-Q Workstation Edition")
    db.expunge_all()
    assert (await db.get(Offering, off.id)).gpu_model == "NVIDIA RTX PRO 6000 Blackwell"


@pytest.mark.asyncio
async def test_device_report_triggers_alignment(db, node, monkeypatch):
    from app.cluster.inventory_sync import InventorySync
    from app.db.models import Cluster
    off = _offering("RTX PRO 6000", "NVIDIA RTX PRO 6000 Blackwell")
    async with db.begin():
        db.add_all([off, Cluster(id="clu_t", name="t", api_server="https://t:6443", runtime="k8s", kubeconfig_secret_ref="s")])
    await InventorySync(db).upsert_device(OperatorGpuDeviceUpsert(
        node_id="gpu-a", uuid="GPU-1", model="NVIDIA RTX PRO 6000 Blackwell Max-Q Workstation Edition",
        total_mem_mb=97887, total_cores=100, mode="fractional", status="ready", node_ready=True,
    ), "clu_t")
    db.expunge_all()
    assert (await db.get(Offering, off.id)).gpu_model == "NVIDIA RTX PRO 6000 Blackwell Max-Q Workstation Edition"

"""Beta follow-up: the status callback payload contract (GS-C08, GS-C12, GS-C13).

The operator sends more than the control plane used to read. What arrives must either be used
or be documented as unused, and what both sides document about a field must say the same thing.
"""
from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.api.schemas.internal import OperatorStatusEvent
from app.core import ids
from app.core.errors import Forbidden
from app.db.models import Session
from app.internal import status_router
from tests.fkseed import seed

pytestmark = pytest.mark.asyncio

REPO = Path(__file__).resolve().parents[2]
CLUSTER = "clu_a"


async def _seed(db, **kw) -> Session:
    fields = dict(
        id=ids.new("session"), owner_user_id=ids.new("user"), cluster_id=CLUSTER,
        offering_id="off_t", image_id="img_t", resource_class="cpu", status="preparing",
    )
    fields.update(kw)
    sess = Session(**fields)
    await seed(db, [sess])
    return sess


def _ev(**kw) -> OperatorStatusEvent:
    base = dict(phase="preparing", ts=datetime.now(UTC))
    base.update(kw)
    return OperatorStatusEvent(**base)


# ── GS-C08: cluster_id is read, not discarded ──


async def test_the_status_schema_keeps_the_reported_cluster_id(db):
    """The operator stamps cluster_id on every status event; pydantic used to drop it."""
    ev = OperatorStatusEvent(phase="running", ts=datetime.now(UTC), cluster_id=CLUSTER)
    assert ev.cluster_id == CLUSTER


async def test_a_status_report_naming_another_cluster_is_refused(db):
    """Same guard the inventory callback has: the token says who is reporting, and a payload
    that names a different cluster is refused rather than believed."""
    sess = await _seed(db)
    await db.commit()
    with pytest.raises(Forbidden):
        await status_router.report_status(
            sess.id, _ev(cluster_id="clu_b"), {"sub": f"operator:{CLUSTER}"}, db)
    db.expunge_all()
    assert (await db.get(Session, sess.id)).status == "preparing"


async def test_a_status_report_from_the_owning_cluster_is_applied(db):
    sess = await _seed(db)
    await db.commit()
    out = await status_router.report_status(
        sess.id, _ev(cluster_id=CLUSTER), {"sub": f"operator:{CLUSTER}"}, db)
    assert out == {"accepted": True}
    db.expunge_all()
    assert (await db.get(Session, sess.id)).status == "preparing"


async def test_an_older_operator_without_a_cluster_id_still_passes(db):
    sess = await _seed(db)
    await db.commit()
    await status_router.report_status(sess.id, _ev(), {"sub": f"operator:{CLUSTER}"}, db)
    db.expunge_all()
    assert (await db.get(Session, sess.id)).status == "preparing"


async def test_used_mem_mb_is_documented_as_unused(db):
    """It is accepted for wire compatibility and nothing reads it: the device ledger is fed by
    the inventory callback. The comment must not claim a reconciliation that does not exist."""
    src = (REPO / "backend/app/api/schemas/internal.py").read_text()
    line = next(ln for ln in src.splitlines() if ln.strip().startswith("used_mem_mb: int | None"))
    assert "inventory reconciliation" not in line
    assert "unused" in line.lower()
    status_sync = (REPO / "backend/app/cluster/status_sync.py").read_text()
    assert "ev.used_mem_mb" not in status_sync


# ── GS-C12: restart_count 0 is a fact, None is silence ──


async def test_restart_count_zero_is_a_heartbeat_and_none_is_not(db):
    """The backend already tells them apart; the operator now actually sends the 0."""
    reported = await _seed(db)
    silent = await _seed(db)
    from app.cluster.status_sync import StatusSync

    await StatusSync(db).on_status(reported.id, _ev(phase="running", restart_count=0))
    await StatusSync(db).on_status(silent.id, _ev(phase="running"))
    db.expunge_all()
    assert (await db.get(Session, reported.id)).last_reported_at is not None
    assert (await db.get(Session, silent.id)).last_reported_at is None


async def test_the_operator_sends_restart_count_when_it_knows_it():
    """A pointer (not a plain int with omitempty): nil when there is no pod to read it from,
    and an explicit 0 when the kubelet says zero restarts."""
    src = (REPO / "operator/internal/sot/client.go").read_text()
    line = next(ln for ln in src.splitlines() if "json:\"restart_count" in ln)
    assert "*int" in line, line
    ctrl = (REPO / "operator/internal/controller/gsharesession_controller.go").read_text()
    assert "RestartCount: restartCount" in ctrl or "RestartCount:   restartCount" in ctrl


# ── GS-C13: both sides must document the same enum ──


def _go_enum(path: Path, field: str) -> set[str]:
    line = next(ln for ln in path.read_text().splitlines()
                if re.match(rf"^\s*{field}\s+string\s+`json:", ln))
    tail = line.split("//", 1)[1].split("(", 1)[0]
    return {tok.strip() for tok in tail.split("|") if tok.strip()}


def _py_enum(path: Path, field: str) -> set[str]:
    line = next(ln for ln in path.read_text().splitlines()
                if re.match(rf"^\s*{field}: str\s+#", ln))
    tail = line.split("#", 1)[1].split("(", 1)[0]
    return {tok.strip() for tok in tail.split("|") if tok.strip()}


async def test_audit_result_enum_is_documented_identically_on_both_sides():
    go = _go_enum(REPO / "operator/internal/sot/client.go", "Result")
    py = _py_enum(REPO / "backend/app/api/schemas/internal.py", "result")
    assert go == py, f"operator documents {sorted(go)}, backend documents {sorted(py)}"


async def test_the_operator_only_ever_reports_ok():
    """What the comment promises has to match what the code emits."""
    emitted = set()
    for src in (REPO / "operator/internal").rglob("*.go"):
        if src.name.endswith("_test.go"):
            continue
        emitted |= set(re.findall(r'Result:\s*"([a-z_]+)"', src.read_text()))
    assert emitted == {"ok"}, emitted
    assert "ok" in _go_enum(REPO / "operator/internal/sot/client.go", "Result")

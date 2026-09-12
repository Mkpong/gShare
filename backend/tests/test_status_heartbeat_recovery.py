"""A heartbeat rescues a session whose Running report was lost.

The operator persists the CR phase before calling back and discards the callback's error, so a
phase it has already written is never re-sent. When that one call failed — a control-plane
restart, a 500, a network blip — the session sat at `pending` while its pod ran: unbilled,
unreachable, and invisible to the reaper. The 60-second heartbeat carries the same binding facts,
so the transition is applied from there instead.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.api.schemas.internal import OperatorStatusEvent
from app.cluster.status_sync import StatusSync
from app.core import ids
from app.db.models import Session as SessionModel
from tests.fkseed import seed


async def _session(db, status: str) -> SessionModel:
    sess = SessionModel(id=ids.new("session"), owner_user_id="usr_1", cluster_id="clu_a",
                        offering_id="off_1", image_id="img_1", resource_class="cpu",
                        status=status)
    await seed(db, [sess])
    return sess


def _hb() -> OperatorStatusEvent:
    return OperatorStatusEvent(phase="heartbeat", ts=datetime.now(UTC).isoformat(),
                               node_name="cpu0", pod_ref="gshare-sessions/ses-x")


@pytest.mark.parametrize("status", ["pending", "preparing"])
@pytest.mark.asyncio
async def test_heartbeat_applies_a_missed_running_transition(db, status):
    sess = await _session(db, status)
    await StatusSync(db).on_status(sess.id, _hb())
    async with db.begin():
        row = await db.get(SessionModel, sess.id)
        assert row.status == "running"
        assert row.started_at is not None
        assert row.node_hostname == "cpu0"


@pytest.mark.asyncio
async def test_heartbeat_does_not_revive_a_settled_session(db):
    sess = await _session(db, "terminated")
    await StatusSync(db).on_status(sess.id, _hb())
    async with db.begin():
        assert (await db.get(SessionModel, sess.id)).status == "terminated"


@pytest.mark.asyncio
async def test_heartbeat_leaves_a_paused_session_paused(db):
    sess = await _session(db, "paused")
    await StatusSync(db).on_status(sess.id, _hb())
    async with db.begin():
        assert (await db.get(SessionModel, sess.id)).status == "paused"

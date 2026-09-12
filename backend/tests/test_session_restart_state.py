"""Restart is a live-session action: a terminated, pending or errored session cannot be
"restarted", and answering 200 (with a matching audit row) for one was a lie."""
from __future__ import annotations

import pytest

from app.core import ids
from app.core.errors import InvalidStateTransition
from app.db.models import Session as SessionModel
from app.domain.session_service import SessionService
from tests.fkseed import seed


@pytest.mark.parametrize("status", ["terminated", "pending", "preparing", "error", "terminating"])
@pytest.mark.asyncio
async def test_restart_refuses_non_live_states(db, status):
    sess = SessionModel(id=ids.new("session"), owner_user_id="usr_1", cluster_id="clu_a",
                        offering_id="off_1", image_id="img_1", resource_class="gpu",
                        mode="fractional", status=status)
    await seed(db, [sess])
    with pytest.raises(InvalidStateTransition):
        await SessionService(db).restart(sess.id)

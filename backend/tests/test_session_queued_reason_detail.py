"""The list and the detail view must give the same answer for why a session is waiting.

The list joined the `queued` session event and showed the reason; the detail handler never did,
so opening a queued session showed a pending row with no explanation — the one screen a user goes
to when they want exactly that.
"""
from __future__ import annotations

import pytest

from app.api.deps import Pagination
from app.api.sessions_router import get_session, list_sessions
from app.auth.rbac import Principal
from app.core import ids
from app.db.models import Session as SessionModel
from app.db.models import SessionEvent
from tests.fkseed import seed


@pytest.mark.asyncio
async def test_detail_reports_the_same_queued_reason_as_the_list(db):
    sess = SessionModel(id=ids.new("session"), owner_user_id="usr_q", cluster_id="clu_a",
                        offering_id="off_1", image_id="img_1", resource_class="gpu",
                        mode="fractional", status="pending")
    await seed(db, [sess, SessionEvent(id=ids.new("session_event"), session_id=sess.id,
                                       kind="queued", reason="no_vram")])
    p = Principal(user_id="usr_q")
    detail = await get_session(sess.id, p, db)
    assert detail.queued_reason == "no_vram"
    listed = await list_sessions(page=Pagination(page=1, size=50), status_filter=None,
                                 group_id=None, cluster_id=None, scope="mine", principal=p, db=db)
    rows = listed["data"] if isinstance(listed, dict) else listed.data
    row = next(r for r in rows if (r["id"] if isinstance(r, dict) else r.id) == sess.id)
    listed_reason = row["queued_reason"] if isinstance(row, dict) else row.queued_reason
    assert listed_reason == detail.queued_reason

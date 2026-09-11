"""Internal status callback: POST /internal/sessions/{id}/status.

Operator reports phase transitions; StatusSync reflects them into session state + ledger
(running->consume / terminated->settle). Idempotent. RS256 internal JWT required.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.internal import OperatorStatusEvent
from app.auth.internal_jwt import require_internal_jwt, require_operator_cluster
from app.cluster.status_sync import StatusSync
from app.db.base import get_db

router = APIRouter(tags=["internal"])


@router.post("/internal/sessions/{session_id}/status", status_code=status.HTTP_202_ACCEPTED)
async def report_status(
    session_id: str,
    ev: OperatorStatusEvent,
    claims: dict = Depends(require_internal_jwt),    # aud=gshare-internal
    db: AsyncSession = Depends(get_db),
):
    # Only the operator of the session's own cluster may speak for it. The operator addresses the
    # session by its CR name, so the lookup has to be the same one StatusSync uses; an unknown
    # session falls through to StatusSync, which already treats it as a no-op.
    sync = StatusSync(db)
    require_operator_cluster(claims, await sync.cluster_of(session_id), what="session")
    await sync.on_status(session_id, ev)             # idempotent; Python is the only DB writer
    return {"accepted": True}

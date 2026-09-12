"""Internal operator audit callback: POST /internal/audit/operator.

Operator privileged actions (cordon/drain/pod-delete/force) are reported here and written to the
hash-chained audit_log. RS256 internal JWT required; Python is the only DB writer.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.internal import OperatorAuditEvent
from app.auth.internal_jwt import operator_cluster, require_internal_jwt, require_operator_cluster
from app.db.base import get_db
from app.domain.audit_service import AuditService

router = APIRouter(tags=["internal"])


@router.post("/internal/audit/operator", status_code=status.HTTP_202_ACCEPTED)
async def audit_operator(
    ev: OperatorAuditEvent,
    claims: dict = Depends(require_internal_jwt),   # aud=gshare-internal
    db: AsyncSession = Depends(get_db),
):
    # The actor is the token, not the payload: a cluster-scoped operator may not sign the audit
    # trail as another cluster's operator.
    require_operator_cluster(claims, operator_cluster({"sub": ev.actor}), what="audit actor")
    await AuditService(db).record_operator_action(ev)
    # _append only flushes; without an explicit commit the row rolls back when the request
    # session closes — a 202 with nothing persisted.
    await db.commit()
    return {"accepted": True}

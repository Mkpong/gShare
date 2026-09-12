"""Internal volume reconciliation: the operator reports every session-volume PVC it sees and is
told, per claim, the quota to grow to and whether the claim may be reclaimed.

POST /internal/volumes/sync — RS256 internal JWT (aud=gshare-internal). Python stays the only DB
writer; the operator stays the only thing touching PVCs.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.internal import OperatorVolumeSync, VolumeSyncResponse
from app.auth.internal_jwt import operator_cluster, require_internal_jwt, require_operator_cluster
from app.cluster.volume_sync import VolumeSync
from app.db.base import get_db

router = APIRouter(tags=["internal"])


@router.post("/internal/volumes/sync", response_model=VolumeSyncResponse)
async def sync_volumes(
    report: OperatorVolumeSync,
    claims: dict = Depends(require_internal_jwt),   # aud=gshare-internal
    db: AsyncSession = Depends(get_db),
) -> VolumeSyncResponse:
    # The report's cluster pins volume placement and pool capacity, so it has to be the token's
    # cluster: no attached cluster may claim a neighbour's PVCs or rewrite its pool figures. An
    # older operator that sends no cluster lands on the token's.
    require_operator_cluster(claims, report.cluster_id, what="volume report")
    if report.cluster_id is None:
        report.cluster_id = operator_cluster(claims)
    return await VolumeSync(db).sync(report)

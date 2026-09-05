"""One card in or out of service.

A GPU that has faulted (fatal Xid, double-bit ECC, fallen off the bus) cannot carry the sessions
bound to it: their CUDA contexts are gone and a resume would not bring them back. The honest
outcome is to take the card out of placement, end those sessions with a settled bill, and tell
their owners — then let an administrator put the card back once it is repaired. Both the manual
console action and operator health events that name a card land here.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models import Allocation, GpuDevice, Session
from app.domain.audit_service import AuditService

log = get_logger(__name__)

REASON = "gpu_fault"


async def sessions_bound_to(db: AsyncSession, device: GpuDevice) -> list[str]:
    """Live sessions holding a resident allocation on ``device``."""
    return list(
        (
            await db.scalars(
                select(Allocation.session_id)
                .join(Session, Session.id == Allocation.session_id)
                .where(
                    Allocation.device_id == device.id,
                    Allocation.ended_at.is_(None),
                    Session.status.in_(("preparing", "running")),
                )
            )
        ).all()
    )


async def set_device_health(
    db: AsyncSession, device: GpuDevice, status: str, *, actor: str, reason: str | None = None,
) -> list[str]:
    """Move ``device`` to ``ready`` or ``unhealthy``. Returns the ids of sessions ended.

    Ending happens outside this function's transaction scope: terminate() commits per session,
    so the device status is committed first (placement stops immediately) and each session is
    then settled on its own — one failure never leaves the card in service."""
    from app.domain.session_service import SessionService  # lazy: import cycle

    prev = device.status
    device.status = status
    await AuditService(db).record(
        actor=actor, action="gpu_device.set_health", target=device.id, result=status,
        previous=prev, reason=reason, gpu_uuid=device.gpu_uuid, model=device.model,
    )
    await db.commit()
    if status != "unhealthy":
        return []
    ended: list[str] = []
    for sid in await sessions_bound_to(db, device):
        try:
            await SessionService(db).terminate(sid, forced=True, reason=REASON)
            ended.append(sid)
        except Exception:  # noqa: BLE001 — settle the rest; the card is already out of service
            log.exception("device_health: could not end session %s on faulty card %s", sid, device.id)
    log.info("device_health: %s -> %s, ended sessions %s", device.gpu_uuid, status, ended)
    return ended

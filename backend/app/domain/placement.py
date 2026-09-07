"""What makes a card able to take NEW work.

The scheduler's reservation and the availability read model must agree on this, or the console
advertises capacity that admission refuses. They diverged once: a card yielded to the lending pool
was excluded from placement but still counted as free VRAM on the dashboard and in the wizard, so
a session could be told there was room and then queue. Both sides import from here.
"""
from __future__ import annotations

from sqlalchemy import or_

from app.db.models import GpuDevice, GpuNode


def placeable_device_clauses() -> tuple:
    """SQLAlchemy clauses for a card that may receive a new placement.

    - the card is healthy (an administrator's fault marking, or the operator's xid/ECC monitor,
      takes it out),
    - it is not mid-transition between pools (draining/applying),
    - it is not yielded or lent — the resident's pod still holds it and only a spot session may
      use it,
    - and its node is ready: cordon and drain promise "no new scheduling".
    """
    return (
        GpuDevice.status == "ready",
        GpuDevice.mode_state == "ready",
        GpuDevice.lend_state == "",
        or_(GpuNode.id.is_(None), GpuNode.status == "ready"),
    )

"""Per-node agent ingest for sub-second session metrics.

The agent (a DaemonSet) reads cgroup v2 counters on its own node and posts batches here. The
samples live in Redis as a short ring per session — they are a live view, not a record: the durable
history stays in Prometheus, and the permanent average/peak summary is written onto the session row
at termination.
"""
from __future__ import annotations

import json
import time

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.internal_jwt import require_internal_jwt
from app.core.logging import get_logger
from app.core.redis import get_redis
from app.db.base import get_db
from app.db.models import Session as SessionRow

router = APIRouter(tags=["internal"])
log = get_logger(__name__)

# How many samples one session keeps. At the agent's 1 s cadence this is five minutes — enough to
# watch a job start without turning Redis into a time-series database.
RING = 300
# The ring outlives a brief agent gap but not a finished session.
TTL_SEC = 900


def live_key(session_id: str) -> str:
    return f"sess:live:{session_id}"


class AgentSample(BaseModel):
    session: str                       # CR name (gshare.io/session label)
    at: float                          # unix seconds, fractional
    cpu_cores: float = Field(ge=0)
    mem_bytes: int = Field(ge=0)


class AgentReport(BaseModel):
    node: str
    samples: list[AgentSample] = Field(default_factory=list, max_length=500)


@router.post("/internal/metrics/session-samples")
async def ingest_session_samples(
    report: AgentReport,
    _claims: dict = Depends(require_internal_jwt),   # aud=gshare-internal
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Accept one node's batch of session samples.

    The agent knows a session only by its CR name (the pod label), so the ids are resolved here —
    the same lower/underscore mapping the CR builder uses. An unknown name is dropped rather than
    stored under a key nothing will ever read.
    """
    if not report.samples:
        return {"accepted": 0}

    names = {s.session for s in report.samples if s.session}
    rows = (
        await db.scalars(select(SessionRow).where(SessionRow.deleted_at.is_(None)))
    ).all() if names else []
    by_cr = {r.id.lower().replace("_", "-"): r.id for r in rows}

    redis = get_redis()
    pipe = redis.pipeline()
    accepted = 0
    unknown = 0
    for s in report.samples:
        sid = by_cr.get(s.session)
        if sid is None:
            unknown += 1
            continue
        key = live_key(sid)
        pipe.rpush(key, json.dumps({"at": s.at, "cpu_cores": s.cpu_cores, "mem_bytes": s.mem_bytes}))
        pipe.ltrim(key, -RING, -1)
        pipe.expire(key, TTL_SEC)
        accepted += 1
    await pipe.execute()
    if unknown:
        log.debug("agent %s sent %d samples for unknown sessions", report.node, unknown)
    return {"accepted": accepted, "unknown": unknown}


async def live_samples(session_id: str, limit: int = RING) -> list[dict]:
    """The session's live ring, oldest first. Empty when no agent is reporting for it."""
    try:
        raw = await get_redis().lrange(live_key(session_id), -limit, -1)
    except Exception:  # noqa: BLE001 — a live view must not fail the page it decorates
        return []
    out = []
    for item in raw:
        try:
            out.append(json.loads(item))
        except (ValueError, TypeError):
            continue
    return out


def agent_seen_recently(samples: list[dict], within_sec: float = 10.0) -> bool:
    """Whether the stream is actually live, so the console can say so instead of drawing a stale
    line as if it were current."""
    return bool(samples) and (time.time() - float(samples[-1].get("at", 0))) <= within_sec

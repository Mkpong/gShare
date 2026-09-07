"""A finished session's usage: the graphs cover its whole run, and the row keeps average/peak
figures after Prometheus (30-day retention) has forgotten the series."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.api import monitoring_router as mr


def test_session_window_is_the_run_itself_or_nothing():
    t0 = datetime(2026, 9, 7, 10, 0, tzinfo=UTC)
    done = SimpleNamespace(started_at=t0, terminated_at=t0 + timedelta(minutes=42))
    assert mr.session_window(done) == (int(t0.timestamp()), int(t0.timestamp()) + 42 * 60)
    # a run shorter than a minute is widened so the range query still has a few points
    blink = SimpleNamespace(started_at=t0, terminated_at=t0 + timedelta(seconds=5))
    assert mr.session_window(blink) == (int(t0.timestamp()), int(t0.timestamp()) + 60)
    assert mr.session_window(SimpleNamespace(started_at=t0, terminated_at=None)) is None
    assert mr.session_window(SimpleNamespace(started_at=None, terminated_at=t0)) is None


@pytest.mark.asyncio
async def test_series_uses_the_window_and_summary_reads_avg_and_max(monkeypatch):
    calls: list[dict] = []

    async def fake_prom(path, params):
        calls.append({"path": path, **params})
        if path == "/api/v1/query_range":
            return {"result": [{"values": [[params["start"], "1.5"], [params["end"], "NaN"]]}]}
        # query: avg_over_time(...) → 0.5, max_over_time(...) → 2.0
        return {"result": [{"value": [params["time"], "0.5" if params["query"].startswith("avg") else "2.0"]}]}

    monkeypatch.setattr(mr, "_prom", fake_prom)
    out = await mr.session_usage_series("ses_x", "15m", window=(1000, 1000 + 3600))
    assert out["range"] == "session" and out["start"] == 1000 and out["end"] == 4600
    assert out["step"] == 15 and all(c["start"] == 1000 and c["end"] == 4600 for c in calls)
    assert out["metrics"]["cpu_cores"]["points"] == [[1000.0, 1.5], [4600.0, None]]

    calls.clear()
    summary = await mr.session_usage_summary("ses_x", 1000, 4600)
    assert summary["start"] == 1000 and summary["end"] == 4600
    assert summary["cpu_cores"] == {"avg": 0.5, "max": 2.0}
    assert summary["vram_mib"] == {"avg": 0.5, "max": 2.0}
    # every query is a subquery over the whole run, evaluated at its end
    assert all(c["time"] == 4600 and "[3600s:15s]" in c["query"] for c in calls) and len(calls) == 8

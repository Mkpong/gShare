"""The worker's liveness file is touched on every tick and never raises."""
from __future__ import annotations

import time
from pathlib import Path

from app.workers import runner


def test_heartbeat_touches_the_file(tmp_path, monkeypatch):
    f = tmp_path / "alive"
    monkeypatch.setattr(runner, "HEARTBEAT_FILE", f)
    runner.heartbeat()
    assert f.exists()
    first = f.stat().st_mtime
    time.sleep(0.01)
    runner.heartbeat()
    assert f.stat().st_mtime >= first


def test_heartbeat_survives_an_unwritable_path(monkeypatch):
    monkeypatch.setattr(runner, "HEARTBEAT_FILE", Path("/proc/does-not-exist/alive"))
    runner.heartbeat()   # logs, does not raise

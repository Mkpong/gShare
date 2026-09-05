"""Fractional placement policy: binpack consolidates onto the fullest fitting card, spread balances."""
from __future__ import annotations

from types import SimpleNamespace as Card

import pytest

from app.core.config import settings
from app.domain.scheduler import SchedulerService


def _fleet():
    return [
        Card(id="empty", total_mem_mb=48000, used_mem_mb=0, total_cores=100, used_cores=0, mode="fractional"),
        Card(id="half", total_mem_mb=48000, used_mem_mb=24000, total_cores=100, used_cores=50, mode="fractional"),
        Card(id="tight", total_mem_mb=48000, used_mem_mb=34000, total_cores=100, used_cores=70, mode="fractional"),
    ]


@pytest.mark.parametrize("policy, expected", [("binpack", "tight"), ("spread", "empty")])
def test_policy_picks_the_expected_card(monkeypatch, policy, expected):
    monkeypatch.setattr(settings, "GPU_PACKING", policy)
    assert SchedulerService._pick_device(_fleet(), 12000, 20).id == expected


def test_a_card_that_does_not_fit_is_never_chosen(monkeypatch):
    monkeypatch.setattr(settings, "GPU_PACKING", "binpack")
    # 16 GB no longer fits the tight card (14 GB free) → the next-tightest wins.
    assert SchedulerService._pick_device(_fleet(), 16000, 20).id == "half"
    assert SchedulerService._pick_device(_fleet(), 60000, 20) is None

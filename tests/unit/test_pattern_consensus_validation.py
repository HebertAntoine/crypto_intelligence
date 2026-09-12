"""The consensus return audit must count independent opportunities honestly."""

from __future__ import annotations

import pytest

from crypto_intel.pattern_learning.validation import select_non_overlapping


def _event(when: str, asset: str = "BTC", pattern: str = "DOUBLE_TOP"):
    return {"available_at": when, "asset": asset, "pattern": pattern}


def test_overlapping_assets_are_one_forward_window():
    events = [
        _event("2025-01-01T00:00:00+00:00", "BTC"),
        _event("2025-01-01T00:00:00+00:00", "ETH"),
        _event("2025-01-03T23:00:00+00:00", "SOL"),
        _event("2025-01-04T00:00:00+00:00", "ETH"),
    ]

    selected = select_non_overlapping(events, 72)

    assert [(item["asset"], item["available_at"]) for item in selected] == [
        ("BTC", "2025-01-01T00:00:00+00:00"),
        ("ETH", "2025-01-04T00:00:00+00:00"),
    ]


def test_non_positive_horizon_is_rejected():
    with pytest.raises(ValueError, match="positive"):
        select_non_overlapping([], 0)

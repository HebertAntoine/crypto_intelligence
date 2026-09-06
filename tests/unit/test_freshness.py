"""Freshness is the difference between 'a signal' and 'an old number'."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from crypto_intel.core.enums import Freshness
from crypto_intel.core.freshness import (
    compute_freshness,
    freshness_factor,
    metric_class,
    worst_freshness,
)

NOW = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)


class TestMetricClass:
    def test_maps_known_prefixes(self):
        assert metric_class("price.close") == "price"
        assert metric_class("etf.flow") == "etf"
        assert metric_class("funding.rate") == "derivatives"
        assert metric_class("onchain.hashrate") == "onchain"
        assert metric_class("macro.us10y") == "macro"

    def test_unknown_falls_back_to_default(self):
        assert metric_class("something.unknown") == "default"


class TestComputeFreshness:
    def test_missing_timestamp_is_unavailable_not_stale(self):
        """Absent data and old data are different states."""
        assert compute_freshness(None, "price") is Freshness.UNAVAILABLE

    def test_recent_price_is_live(self):
        assert compute_freshness(NOW - timedelta(seconds=60), "price", now=NOW) is Freshness.LIVE

    def test_old_price_is_stale(self):
        assert compute_freshness(NOW - timedelta(days=3), "price", now=NOW) is Freshness.STALE

    def test_etf_thresholds_are_looser_than_price(self):
        """A 30-minute-old ETF flow is fresh; a 30-minute-old price is not."""
        age = NOW - timedelta(minutes=30)
        assert compute_freshness(age, "etf", now=NOW).rank > compute_freshness(age, "price", now=NOW).rank

    def test_interval_scaling_keeps_weekly_bar_current(self):
        """A weekly candle opened 3 days ago is the CURRENT bar, not stale."""
        ts = NOW - timedelta(days=3)
        assert compute_freshness(ts, "price", now=NOW) is Freshness.STALE
        assert compute_freshness(ts, "price", now=NOW, interval_minutes=10080) is Freshness.LIVE

    def test_interval_scaling_still_detects_genuinely_old_data(self):
        ts = NOW - timedelta(days=60)
        assert compute_freshness(ts, "price", now=NOW, interval_minutes=10080) is Freshness.STALE

    def test_small_clock_skew_tolerated(self):
        """Exchange clock skew must not make live data look impossible."""
        assert compute_freshness(NOW + timedelta(seconds=60), "price", now=NOW) is Freshness.LIVE

    def test_far_future_rejected(self):
        assert compute_freshness(NOW + timedelta(hours=5), "price", now=NOW) is Freshness.UNAVAILABLE


class TestAggregation:
    def test_worst_freshness_wins(self):
        assert worst_freshness([Freshness.LIVE, Freshness.STALE, Freshness.HOUR_1]) is Freshness.STALE

    def test_empty_is_unavailable(self):
        assert worst_freshness([]) is Freshness.UNAVAILABLE

    def test_unavailable_contributes_zero_weight(self):
        """Missing data must count for exactly nothing in scoring."""
        assert freshness_factor(Freshness.UNAVAILABLE) == 0.0
        assert freshness_factor(Freshness.LIVE) == 1.0
        assert 0 < freshness_factor(Freshness.STALE) < 1.0

    def test_ordering_is_monotonic(self):
        ranks = [
            Freshness.UNAVAILABLE.rank, Freshness.STALE.rank, Freshness.TODAY.rank,
            Freshness.HOUR_1.rank, Freshness.MIN_15.rank, Freshness.LIVE.rank,
        ]
        assert ranks == sorted(ranks)

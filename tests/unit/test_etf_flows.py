"""ETF flow analysis - the module the brief calls VERY IMPORTANT."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from crypto_intel.core.enums import Asset, Direction, Freshness
from crypto_intel.core.models import Observation, Provenance
from crypto_intel.engines.etf_flows import ETFFlowAnalyzer

PROV = Provenance(source="test", provider="test_etf")


def flows(values: list[float], ticker: str = "IBIT") -> list[Observation]:
    """values[-1] is today."""
    now = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    n = len(values)
    return [
        Observation(
            asset=Asset.BTC, metric="etf.flow", value=v, unit="USD_M",
            timestamp=now - timedelta(days=n - 1 - i), provenance=PROV,
            freshness=Freshness.TODAY, meta={"ticker": ticker},
        )
        for i, v in enumerate(values)
    ]


class TestAvailability:
    def test_no_data_is_unavailable_not_zero(self):
        """The critical rule: absence of data is never a flow of 0."""
        r = ETFFlowAnalyzer().analyze(Asset.BTC, [])
        assert r.available is False
        assert r.latest_total is None
        assert r.freshness is Freshness.UNAVAILABLE
        assert "UNAVAILABLE" in r.unavailable_reason

    def test_explicit_reason_preserved(self):
        r = ETFFlowAnalyzer().analyze(Asset.SOL, [], unavailable_reason="SOL has no US spot ETF")
        assert "SOL has no US spot ETF" in r.unavailable_reason


class TestAggregation:
    def test_sums_funds_per_day(self, etf_observations):
        r = ETFFlowAnalyzer().analyze(Asset.BTC, etf_observations)
        assert r.available
        assert r.latest_total == pytest.approx(500.0)   # 400 IBIT + 100 FBTC
        assert set(r.latest_by_ticker) == {"IBIT", "FBTC"}

    def test_moving_averages(self):
        r = ETFFlowAnalyzer().analyze(Asset.BTC, flows([100, 100, 100, 100, 100]))
        assert r.ma_3d == pytest.approx(100.0)
        assert r.ma_5d == pytest.approx(100.0)

    def test_insufficient_history_gives_none_not_zero(self):
        r = ETFFlowAnalyzer().analyze(Asset.BTC, flows([100, 200]))
        assert r.ma_7d is None
        assert r.ma_3d is None

    def test_cumulative(self):
        r = ETFFlowAnalyzer().analyze(Asset.BTC, flows([10, 20, 30]))
        assert r.cumulative_all == pytest.approx(60.0)


class TestPatterns:
    def test_detects_acceleration(self):
        r = ETFFlowAnalyzer().analyze(Asset.BTC, flows([10, 10, 10, 100, 100, 100]))
        assert r.acceleration_pct is not None and r.acceleration_pct > 100

    def test_detects_positive_reversal(self):
        r = ETFFlowAnalyzer().analyze(Asset.BTC, flows([-50, -50, -50, 50, 50, 50]))
        assert r.reversal == "POSITIVE_REVERSAL"

    def test_detects_negative_reversal(self):
        r = ETFFlowAnalyzer().analyze(Asset.BTC, flows([50, 50, 50, -50, -50, -50]))
        assert r.reversal == "NEGATIVE_REVERSAL"

    def test_counts_inflow_streak(self):
        r = ETFFlowAnalyzer().analyze(Asset.BTC, flows([-10, 20, 30, 40, 50]))
        assert r.streak_days == 4
        assert r.streak_direction == "inflow"

    def test_counts_outflow_streak(self):
        r = ETFFlowAnalyzer().analyze(Asset.BTC, flows([10, -20, -30, -40]))
        assert r.streak_days == 3
        assert r.streak_direction == "outflow"


class TestFlowPriceDivergence:
    def _prices(self, values: list[float]) -> list[tuple[datetime, float]]:
        now = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        n = len(values)
        return [(now - timedelta(days=n - 1 - i), v) for i, v in enumerate(values)]

    def test_accumulation_before_price(self):
        """The headline case: institutions buying while price falls."""
        r = ETFFlowAnalyzer().analyze(
            Asset.BTC, flows([100] * 8), self._prices([100, 99, 98, 97, 96, 95, 94, 93])
        )
        assert r.flow_price_divergence == "ACCUMULATION_BEFORE_PRICE"
        assert "not following price down" in r.divergence_detail

    def test_distribution_into_strength(self):
        r = ETFFlowAnalyzer().analyze(
            Asset.BTC, flows([-100] * 8), self._prices([93, 94, 95, 96, 97, 98, 99, 100])
        )
        assert r.flow_price_divergence == "DISTRIBUTION_INTO_STRENGTH"

    def test_confirmed_uptrend(self):
        r = ETFFlowAnalyzer().analyze(
            Asset.BTC, flows([100] * 8), self._prices([93, 94, 95, 96, 97, 98, 99, 100])
        )
        assert r.flow_price_divergence == "CONFIRMED_UPTREND"


class TestScoring:
    def test_strong_inflows_are_bullish(self):
        r = ETFFlowAnalyzer().analyze(Asset.BTC, flows([400, 450, 500, 550, 600]))
        assert r.direction is Direction.BULLISH
        assert r.strength > 30

    def test_strong_outflows_are_bearish(self):
        r = ETFFlowAnalyzer().analyze(Asset.BTC, flows([-400, -450, -500, -550, -600]))
        assert r.direction is Direction.BEARISH
        assert r.strength < -30

    def test_flat_flows_are_neutral(self):
        r = ETFFlowAnalyzer().analyze(Asset.BTC, flows([1, -1, 2, -2, 1]))
        assert r.direction is Direction.NEUTRAL

    def test_score_bounded(self):
        r = ETFFlowAnalyzer().analyze(Asset.BTC, flows([99999] * 10))
        assert -100 <= r.strength <= 100

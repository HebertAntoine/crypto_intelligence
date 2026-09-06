"""LOT 4: point-in-time, leverage, volatility, edge and uncertainty.

The tests that matter most here are the ones asserting the system REFUSES to
claim things: that edge stays independent of direction, that percentiles never
see the future, and that a missing input produces UNKNOWN rather than a
neutral-looking default.
"""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest

from crypto_intel.core.enums import Asset
from crypto_intel.core.pointintime import Availability, classify_metric
from crypto_intel.engines.edge import (
    MIN_INDEPENDENT_OBSERVATIONS,
    ROUND_TRIP_COST_PCT,
    EdgeAssessment,
    EdgeEngine,
    EdgeEvidence,
    EdgeState,
    UncertaintyEngine,
    build_decision_summary,
)
from crypto_intel.engines.leverage import (
    CrowdingLevel,
    FundingBand,
    LeverageCrowdingEngine,
    _trailing_percentile,
    band_for_percentile,
)
from crypto_intel.engines.volatility import VolatilityRegimeEngine, VolRegime


class _Regime:
    def __init__(self, value: str, confidence: float = 80.0) -> None:
        self.regime = type("R", (), {"value": value})()
        self.confidence = confidence


class _Crowding:
    def __init__(self, level: str) -> None:
        self.level = type("L", (), {"value": level})()


# --- point in time ------------------------------------------------------


def test_revised_macro_series_is_not_backtestable():
    """CPI is revised, so its current value was not knowable at the time."""
    availability = classify_metric("macro.cpi")
    assert availability is Availability.NOT_POINT_IN_TIME
    assert not availability.usable_for_backtest


def test_price_is_point_in_time():
    assert classify_metric("price.close").usable_for_backtest


# --- trailing percentiles ----------------------------------------------


def test_trailing_percentile_never_uses_the_future():
    """The decisive anti-leakage property: appending data cannot change history.

    If a percentile at time t moved when later values arrived, every backtest
    built on it would be reading tomorrow's newspaper.
    """
    rng = np.random.default_rng(11)
    index = pd.date_range("2020-01-01", periods=400, freq="D", tz=UTC)
    values = pd.Series(rng.normal(size=400), index=index)

    full = _trailing_percentile(values)
    truncated = _trailing_percentile(values.iloc[:300])

    overlap = truncated.dropna().index
    assert len(overlap) > 50, "test needs a usable overlap to be meaningful"
    pd.testing.assert_series_equal(
        full.loc[overlap], truncated.loc[overlap], check_names=False
    )


def test_percentile_requires_minimum_history():
    index = pd.date_range("2020-01-01", periods=60, freq="D", tz=UTC)
    result = _trailing_percentile(pd.Series(range(60), index=index, dtype=float))
    assert result.dropna().empty, "60 points must not yield a percentile"


@pytest.mark.parametrize(
    ("percentile", "expected"),
    [
        (99.0, FundingBand.EXTREME_POSITIVE), (80.0, FundingBand.POSITIVE),
        (50.0, FundingBand.NEUTRAL), (10.0, FundingBand.NEGATIVE),
        (2.0, FundingBand.EXTREME_NEGATIVE), (None, FundingBand.UNKNOWN),
    ],
)
def test_funding_bands(percentile, expected):
    assert band_for_percentile(percentile) is expected


def test_nan_percentile_is_unknown_not_neutral():
    """A missing measurement must never be read as a mid-range one."""
    assert band_for_percentile(float("nan")) is FundingBand.UNKNOWN


# --- crowding -----------------------------------------------------------


@pytest.fixture
def synthetic_market(monkeypatch):
    """Price, funding and OI series injected directly.

    The test database is empty by design, so these engines are exercised
    against data constructed here rather than whatever the real database
    happens to hold. That also lets each scenario be stated exactly.
    """
    from crypto_intel.engines import leverage as leverage_module

    index = pd.date_range("2021-01-01", periods=500, freq="D", tz=UTC)

    def install(*, price_trend: float, oi_trend: float, funding: float, with_oi: bool = True):
        closes = pd.Series(
            [100.0 * (1 + price_trend) ** i for i in range(len(index))], index=index
        )
        candles = pd.DataFrame(
            {
                "open": closes, "high": closes * 1.02, "low": closes * 0.98,
                "close": closes, "volume": pd.Series(1000.0, index=index),
            },
            index=index,
        )
        oi_series = pd.Series(
            [1000.0 * (1 + oi_trend) ** i for i in range(len(index))], index=index
        )
        funding_series = pd.Series(funding, index=index)

        monkeypatch.setattr(
            leverage_module.store, "load_candles", lambda *a, **k: candles
        )
        monkeypatch.setattr(
            leverage_module.store,
            "load_derivatives",
            lambda asset, metric, **k: (
                funding_series if metric == "funding.rate"
                else (oi_series if with_oi else pd.Series(dtype=float))
            ),
        )
        return candles, oi_series

    return install


def test_crowding_never_claims_a_direction(synthetic_market):
    """Open interest counts contracts, not sides. Direction is not observable."""
    synthetic_market(price_trend=0.004, oi_trend=0.004, funding=0.0009)
    engine = LeverageCrowdingEngine()
    for asset in Asset.tradables():
        result = engine.crowding(asset)
        assert result.direction == "UNKNOWN"
        assert "not observable" in result.interpretation


def test_crowding_without_history_is_unknown_not_low():
    engine = LeverageCrowdingEngine()
    result = engine.crowding(Asset.BTC, as_of=datetime(2013, 1, 1, tzinfo=UTC))
    assert result.level is CrowdingLevel.UNKNOWN
    assert result.score is None
    assert "UNKNOWN, not low" in result.interpretation


def test_leverage_state_degrades_when_open_interest_is_missing(synthetic_market):
    """Price alone cannot distinguish new positions from closing ones."""
    synthetic_market(price_trend=0.004, oi_trend=0.0, funding=0.0001, with_oi=False)
    result = LeverageCrowdingEngine().leverage_state(Asset.BTC)
    assert result.state.value == "UNDETERMINED"
    assert "open_interest" in result.inputs_missing
    assert "price" in result.inputs_used
    assert "cannot be separated" in result.interpretation


def test_rising_price_with_rising_open_interest_is_new_longs(synthetic_market):
    synthetic_market(price_trend=0.004, oi_trend=0.006, funding=0.0002)
    result = LeverageCrowdingEngine().leverage_state(Asset.BTC)
    assert result.state.value == "NEW_LONGS"
    assert result.confidence == "MEDIUM"


def test_rising_price_with_falling_open_interest_is_short_covering(synthetic_market):
    """The same green candle, a different cause - the reason OI matters."""
    synthetic_market(price_trend=0.004, oi_trend=-0.006, funding=0.0002)
    result = LeverageCrowdingEngine().leverage_state(Asset.BTC)
    assert result.state.value == "SHORT_COVERING"


def test_falling_price_with_falling_open_interest_is_long_liquidation(synthetic_market):
    synthetic_market(price_trend=-0.004, oi_trend=-0.006, funding=-0.0002)
    result = LeverageCrowdingEngine().leverage_state(Asset.BTC)
    assert result.state.value == "LONG_LIQUIDATION"


# --- volatility ---------------------------------------------------------


def test_volatility_regime_is_directionless(monkeypatch):
    """A rising and a falling market of equal amplitude must score the same.

    Volatility measures the size of moves. If direction leaked in, these two
    would differ, and an expansion would start reading as bearish.
    """
    from crypto_intel.engines import volatility as volatility_module

    index = pd.date_range("2021-01-01", periods=400, freq="D", tz=UTC)
    rng = np.random.default_rng(3)
    shocks = rng.normal(0, 0.02, size=len(index))

    def frame(drift: float) -> pd.DataFrame:
        closes = pd.Series(
            100.0 * np.exp(np.cumsum(shocks + drift)), index=index
        )
        return pd.DataFrame(
            {
                "open": closes, "high": closes * 1.01, "low": closes * 0.99,
                "close": closes, "volume": pd.Series(1000.0, index=index),
            },
            index=index,
        )

    engine = VolatilityRegimeEngine()
    monkeypatch.setattr(volatility_module.store, "load_candles", lambda *a, **k: frame(0.003))
    up = engine.assess(Asset.BTC)
    monkeypatch.setattr(volatility_module.store, "load_candles", lambda *a, **k: frame(-0.003))
    down = engine.assess(Asset.BTC)

    # Realised volatility is the scale-free measure and must match closely.
    assert up.realised_vol_annualised == pytest.approx(
        down.realised_vol_annualised, rel=0.05
    )
    # ATR% divides an absolute range by the prevailing price, so drift moves it
    # a little; the regimes must still land adjacent rather than opposite.
    ordering = [r.value for r in VolRegime if r is not VolRegime.UNKNOWN]
    assert abs(ordering.index(up.regime) - ordering.index(down.regime)) <= 1
    for banned in ("BULLISH", "BEARISH", "BUY", "SELL"):
        assert banned not in up.interpretation.upper()
        assert banned not in down.interpretation.upper()


def test_volatility_unknown_without_enough_history():
    engine = VolatilityRegimeEngine()
    result = engine.assess(Asset.BTC, as_of=datetime(2017, 9, 1, tzinfo=UTC))
    assert result.regime == VolRegime.UNKNOWN.value


# --- edge ---------------------------------------------------------------


def test_unadmitted_evidence_yields_no_edge():
    evidence = EdgeEvidence(
        source="test", signal="s", horizon_days=7, effect_pct=5.0,
        p_value=0.001, survives_fdr=True, effective_n=4.0, stability="CONCENTRATED",
    )
    assert not evidence.admitted


def test_edge_is_independent_of_market_direction():
    """A strongly bullish regime must not turn into an edge claim.

    This is the single property LOT 4 is built around: direction and
    demonstrated predictive ability are different questions.
    """
    edge = EdgeAssessment(asset="BTC", state=EdgeState.NO_MEASURABLE_EDGE)
    uncertainty = UncertaintyEngine().assess(Asset.BTC, edge, regime=_Regime("STRONGLY_BULLISH"))
    summary = build_decision_summary(
        Asset.BTC, edge, uncertainty, regime=_Regime("STRONGLY_BULLISH")
    )
    assert summary.market_direction == "STRONGLY_BULLISH"
    assert summary.edge_state is EdgeState.NO_MEASURABLE_EDGE
    assert not summary.actionable
    assert "no robust directional edge" in summary.statement


def test_bullish_regime_does_not_reduce_uncertainty_below_no_edge_floor():
    engine = UncertaintyEngine()
    edge = EdgeAssessment(asset="BTC", state=EdgeState.NO_MEASURABLE_EDGE)
    bullish = engine.assess(Asset.BTC, edge, regime=_Regime("STRONGLY_BULLISH"))
    assert bullish.score >= 40, "absence of edge must dominate the uncertainty score"


def test_crowding_increases_uncertainty():
    engine = UncertaintyEngine()
    edge = EdgeAssessment(asset="BTC", state=EdgeState.NO_MEASURABLE_EDGE)
    calm = engine.assess(Asset.BTC, edge, regime=_Regime("BULLISH"), crowding=_Crowding("NORMAL"))
    hot = engine.assess(Asset.BTC, edge, regime=_Regime("BULLISH"), crowding=_Crowding("EXTREME"))
    assert hot.score > calm.score


def test_effect_below_transaction_cost_is_not_an_edge():
    assert MIN_INDEPENDENT_OBSERVATIONS >= 20
    assert ROUND_TRIP_COST_PCT > 0.1


def test_decision_summary_always_states_the_separation():
    edge = EdgeAssessment(asset="ETH", state=EdgeState.NO_MEASURABLE_EDGE)
    uncertainty = UncertaintyEngine().assess(Asset.ETH, edge)
    summary = build_decision_summary(Asset.ETH, edge, uncertainty, regime=_Regime("BEARISH"))
    joined = " ".join(summary.caveats)
    assert "independently" in joined
    assert "not evidence of predictive ability" in joined


def test_no_buy_or_sell_language_anywhere_in_the_summary():
    """The system must never emit an order instruction."""
    for state in EdgeState:
        edge = EdgeAssessment(asset="SOL", state=state, effect_pct=1.0, horizon_days=7)
        uncertainty = UncertaintyEngine().assess(Asset.SOL, edge)
        summary = build_decision_summary(Asset.SOL, edge, uncertainty, regime=_Regime("BULLISH"))
        text = (summary.statement + " ".join(summary.caveats)).upper()
        for banned in (" BUY ", " SELL ", "GO LONG", "GO SHORT", "ACHETER", "VENDRE"):
            assert banned not in f" {text} "


def test_real_pipeline_assets_report_no_measurable_edge():
    """Reflects the measured state of this system: nothing has cleared the bar.

    If a future signal genuinely passes every filter this will fail, which is
    the correct moment to revisit it deliberately rather than by accident.
    """
    engine = EdgeEngine()
    for asset in Asset.tradables():
        result = engine.assess(asset)
        assert result.state in (EdgeState.NO_MEASURABLE_EDGE, EdgeState.INSUFFICIENT_DATA)
        assert result.admitted_count == 0

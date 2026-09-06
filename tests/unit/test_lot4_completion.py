"""LOT 4 remaining engines: cross-asset, breakout, liquidation, baselines,
feature registry, shadow model and drift.

The causality tests here matter more than the functional ones. A feature that
silently sees the future invalidates every result built on it, and the failure
is invisible in normal use - so it is asserted directly.
"""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest

from crypto_intel.core.enums import Asset, Timeframe
from crypto_intel.engines.breakout import BreakoutQualityEngine, BreakoutState
from crypto_intel.engines.cross_asset import (
    CrossAssetAnalyzer,
    CryptoBreadthEngine,
    LiquidityRegime,
    LiquidityRegimeEngine,
    MarketRatiosEngine,
)
from crypto_intel.engines.liquidation import (
    CascadeRisk,
    LiquidationDataState,
    LiquidationRiskEngine,
)
from crypto_intel.research.baselines import build_baselines, compare_against_baselines, evaluate
from crypto_intel.research.drift import (
    MIN_LIVE_OBSERVATIONS,
    DriftState,
    ShadowModel,
    SignalDriftEngine,
)
from crypto_intel.research.registry import FeatureRegistry, FeatureSpec, get_registry


@pytest.fixture
def synthetic_candles():
    index = pd.date_range("2020-01-01", periods=800, freq="D", tz=UTC)
    rng = np.random.default_rng(7)
    closes = pd.Series(100.0 * np.exp(np.cumsum(rng.normal(0.001, 0.02, len(index)))), index=index)
    return pd.DataFrame(
        {
            "open": closes.shift(1).fillna(closes.iloc[0]),
            "high": closes * 1.02, "low": closes * 0.98,
            "close": closes, "volume": pd.Series(1000.0, index=index),
        },
        index=index,
    )


# --- feature registry: causality ---------------------------------------


def test_registry_features_are_all_declared_point_in_time():
    registry = get_registry()
    for spec in registry.describe():
        assert spec["usable_for_backtest"], f"{spec['name']} is not backtest safe"


def test_dataset_targets_are_separated_from_features(monkeypatch, synthetic_candles):
    """Forward returns must live in clearly named columns, never in features."""
    from crypto_intel.research import registry as registry_module

    monkeypatch.setattr(
        registry_module.store, "load_candles", lambda *a, **k: synthetic_candles
    )
    monkeypatch.setattr(
        registry_module.store, "load_derivatives", lambda *a, **k: pd.Series(dtype=float)
    )
    frame, manifest = FeatureRegistry().build_dataset(Asset.BTC)

    assert manifest["status"] == "OK"
    targets = [c for c in frame.columns if c.startswith("target_")]
    assert targets, "dataset must carry forward-return targets"
    for name in manifest["features_built"]:
        assert not name.startswith("target_")


def test_features_do_not_change_when_the_future_changes(monkeypatch, synthetic_candles):
    """The mutation test: rewrite the future, the past must not move.

    This is the strongest available guarantee against look-ahead. Every feature
    is rebuilt on data whose tail has been replaced with different prices; any
    value at an earlier timestamp that shifts is reading forward.
    """
    from crypto_intel.research import registry as registry_module

    cutoff = 600
    mutated = synthetic_candles.copy()
    # Replace everything after the cutoff with a violent, different path.
    mutated.iloc[cutoff:, mutated.columns.get_loc("close")] *= 3.0
    mutated.iloc[cutoff:, mutated.columns.get_loc("high")] *= 3.0
    mutated.iloc[cutoff:, mutated.columns.get_loc("low")] *= 3.0
    mutated.iloc[cutoff:, mutated.columns.get_loc("volume")] *= 50.0

    monkeypatch.setattr(
        registry_module.store, "load_derivatives", lambda *a, **k: pd.Series(dtype=float)
    )
    registry = FeatureRegistry()

    monkeypatch.setattr(registry_module.store, "load_candles", lambda *a, **k: synthetic_candles)
    original, manifest = registry.build_dataset(Asset.BTC)
    monkeypatch.setattr(registry_module.store, "load_candles", lambda *a, **k: mutated)
    changed, _ = registry.build_dataset(Asset.BTC)

    # Compare only the region before the mutation, and only feature columns.
    features = manifest["features_built"]
    left = original[features].iloc[:cutoff]
    right = changed[features].iloc[:cutoff]
    pd.testing.assert_frame_equal(left, right, check_exact=False, rtol=1e-9)


def test_feature_definition_hash_changes_when_the_builder_changes():
    """Reproducibility depends on the hash tracking the actual code."""
    def builder_a(df, asset):
        return df["close"]

    def builder_b(df, asset):
        return df["close"] * 2   # different source

    spec_a = FeatureSpec("x", "d", builder_a)
    spec_b = FeatureSpec("x", "d", builder_b)
    assert spec_a.definition_hash() != spec_b.definition_hash()


def test_registry_rejects_duplicate_registration():
    registry = FeatureRegistry()
    existing = registry.names()[0]
    with pytest.raises(ValueError):
        registry.register(FeatureSpec(existing, "dup", lambda df, a: df["close"]))


# --- baselines ----------------------------------------------------------


def test_baselines_include_buy_and_hold_and_random():
    signals = build_baselines(Asset.BTC)
    if not signals:
        pytest.skip("no stored candles in the test database")
    assert "always_long" in signals
    assert "random" in signals


def test_random_baseline_is_reproducible():
    """A fixed seed, so the comparison target does not move between runs."""
    first = build_baselines(Asset.BTC).get("random")
    second = build_baselines(Asset.BTC).get("random")
    if first is None:
        pytest.skip("no stored candles in the test database")
    pd.testing.assert_series_equal(first, second)


def test_comparison_names_buy_and_hold_explicitly():
    result = compare_against_baselines(Asset.BTC, 1.0, 7, "test_signal")
    if result.get("status") == "INSUFFICIENT_DATA":
        pytest.skip("no stored candles in the test database")
    assert result["verdict"] in ("BEATS_BUY_AND_HOLD", "DOES_NOT_BEAT_BUY_AND_HOLD")


def test_evaluate_reports_insufficient_data_rather_than_guessing():
    result = evaluate(Asset.BTC)
    assert result["status"] in ("OK", "INSUFFICIENT_DATA")


# --- cross asset --------------------------------------------------------


def test_cross_asset_reports_missing_series_rather_than_zero():
    result = CrossAssetAnalyzer().assess(Asset.BTC)
    for reading in result.correlations:
        # A correlation is either measured or explicitly absent - never 0.0
        # standing in for "we could not compute this".
        if reading.correlation is not None:
            assert -1.0 <= reading.correlation <= 1.0
            assert reading.observations > 0


def test_dominance_is_never_a_fabricated_proxy():
    """The basket-share 'proxy' was removed; only real dominance or UNAVAILABLE."""
    result = MarketRatiosEngine().assess()
    dominance = result["btc_dominance"]
    assert "shares_pct" not in dominance
    if not dominance["available"]:
        assert dominance["status"] == "UNAVAILABLE"
        assert "none is estimated" in dominance["reason"]


def test_breadth_is_unknown_without_history():
    result = CryptoBreadthEngine().assess(as_of=datetime(2010, 1, 1, tzinfo=UTC))
    assert result.state == "UNKNOWN"
    assert result.score is None


def test_liquidity_regime_unknown_is_not_neutral():
    result = LiquidityRegimeEngine().assess(as_of=datetime(2000, 1, 1, tzinfo=UTC))
    assert result.regime is LiquidityRegime.UNKNOWN
    assert "not the same as neutral" in result.interpretation


# --- breakout -----------------------------------------------------------


def test_breakout_quality_carries_no_directional_promise():
    engine = BreakoutQualityEngine()
    result = engine.assess(Asset.BTC, Timeframe.D1)
    assert "NOT a probability" in result.edge_note
    for banned in (" BUY ", " SELL "):
        assert banned not in f" {result.interpretation.upper()} "


def test_breakout_needs_history(monkeypatch):
    from crypto_intel.engines import breakout as breakout_module

    monkeypatch.setattr(
        breakout_module.store, "load_candles", lambda *a, **k: pd.DataFrame()
    )
    result = BreakoutQualityEngine().assess(Asset.BTC)
    assert result.state is BreakoutState.NONE
    assert "price history" in result.missing


# --- liquidations -------------------------------------------------------


@pytest.mark.asyncio
async def test_liquidations_unavailable_without_connector():
    """No connector means UNAVAILABLE, never an estimate."""
    result = await LiquidationRiskEngine().assess(Asset.BTC)
    assert result.data_state is not LiquidationDataState.AVAILABLE
    assert result.liquidations_24h_usd is None
    assert "not estimated" in result.conditions_note


@pytest.mark.asyncio
async def test_cascade_conditions_are_not_a_direction():
    result = await LiquidationRiskEngine().assess(Asset.BTC)
    assert result.cascade_risk in set(CascadeRisk)
    if result.cascade_risk is not CascadeRisk.UNKNOWN:
        assert "no directional information" in result.conditions_note


# --- shadow model and drift --------------------------------------------


def test_shadow_predictions_are_not_scored_before_their_horizon(tmp_path):
    shadow = ShadowModel(tmp_path)
    shadow.record(
        Asset.BTC, "UP", 100.0, "BULLISH", "NO_MEASURABLE_EDGE",
        horizons=[7], made_at=datetime.now(UTC),
    )
    predictions = shadow.load(Asset.BTC)
    assert len(predictions) == 1
    assert not predictions[0].resolved
    assert predictions[0].correct is None


def test_shadow_ignores_duplicate_same_day_records(tmp_path):
    shadow = ShadowModel(tmp_path)
    made_at = datetime.now(UTC)
    first = shadow.record(Asset.BTC, "UP", 100.0, "BULLISH", "X", [7], made_at=made_at)
    second = shadow.record(Asset.BTC, "UP", 100.0, "BULLISH", "X", [7], made_at=made_at)
    assert first == 1
    assert second == 0


def test_neutral_calls_are_never_scored_as_correct(tmp_path, monkeypatch):
    """Counting NEUTRAL as a hit would inflate the live track record."""
    index = pd.date_range("2024-01-01", periods=60, freq="D", tz=UTC)
    prices = pd.DataFrame({"close": np.linspace(100, 130, 60)}, index=index)
    monkeypatch.setattr(
        "crypto_intel.history.store.load_candles", lambda *a, **k: prices
    )

    shadow = ShadowModel(tmp_path)
    shadow.record(
        Asset.BTC, "NEUTRAL", 100.0, "NEUTRAL", "NO_MEASURABLE_EDGE",
        horizons=[7], made_at=index[0].to_pydatetime(),
    )
    shadow.resolve(Asset.BTC, now=index[-1].to_pydatetime())
    predictions = shadow.load(Asset.BTC)
    assert predictions[0].resolved
    assert predictions[0].correct is None


def test_drift_requires_a_minimum_live_sample(tmp_path):
    engine = SignalDriftEngine(ShadowModel(tmp_path))
    result = engine.assess(Asset.BTC)
    assert result["state"] == DriftState.INSUFFICIENT_LIVE_DATA.value
    assert str(MIN_LIVE_OBSERVATIONS) in result["note"]
    assert "not evidence the model is fine" in result["note"]


def test_drift_detects_a_real_gap(tmp_path, monkeypatch):
    """A model promising 70% that delivers 50% must be flagged."""
    index = pd.date_range("2024-01-01", periods=400, freq="D", tz=UTC)
    # Flat-then-noisy prices so roughly half the UP calls are wrong.
    rng = np.random.default_rng(5)
    closes = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.01, len(index)))), index=index)
    monkeypatch.setattr(
        "crypto_intel.history.store.load_candles",
        lambda *a, **k: pd.DataFrame({"close": closes}, index=index),
    )

    shadow = ShadowModel(tmp_path)
    for i in range(0, 300, 3):
        shadow.record(
            Asset.BTC, "UP", float(closes.iloc[i]), "BULLISH", "X",
            horizons=[7], expected_hit_rate=0.95, made_at=index[i].to_pydatetime(),
        )
    shadow.resolve(Asset.BTC, now=index[-1].to_pydatetime())
    result = SignalDriftEngine(shadow).assess(Asset.BTC)

    assert result["predictions_scored"] >= MIN_LIVE_OBSERVATIONS
    assert result["state"] == DriftState.SIGNIFICANT_DRIFT.value
    assert result["by_horizon"]["7d"]["gap_pp"] < 0

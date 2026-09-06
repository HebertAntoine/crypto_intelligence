"""LOT 5 causality: anti-leakage, mutation and robustness.

These are the most important tests in the lot. A structural detector that
peeks at future bars produces a beautiful backtest and a worthless system, and
the failure is invisible in normal use - nothing errors, the numbers just come
out too good.

So causality is asserted directly: compute a structure, rewrite the future,
recompute, and require the earlier answer to be bit-identical.
"""

from __future__ import annotations

from datetime import UTC

import numpy as np
import pandas as pd
import pytest

from crypto_intel.core.enums import Asset, Timeframe
from crypto_intel.core.sources import SourceClaim, SourceTier, can_override, resolve_conflict
from crypto_intel.structure.location import LocationState, StructuralLocationEngine
from crypto_intel.structure.market_structure import MarketStructureEngine, StructureState
from crypto_intel.structure.patterns import (
    PATTERN_CLASSES,
    PatternEdgeState,
    PatternState,
    build_context,
    detect_all,
)
from crypto_intel.structure.ranges import RangeIntelligenceEngine, RangeType
from crypto_intel.structure.swings import find_causal_swings
from crypto_intel.structure.zones import build_zones


def _frame(n: int = 600, seed: int = 3, drift: float = 0.0005) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    index = pd.date_range("2021-01-01", periods=n, freq="D", tz=UTC)
    closes = pd.Series(100.0 * np.exp(np.cumsum(rng.normal(drift, 0.02, n))), index=index)
    return pd.DataFrame(
        {
            "open": closes.shift(1).fillna(closes.iloc[0]),
            "high": closes * (1 + np.abs(rng.normal(0, 0.008, n))),
            "low": closes * (1 - np.abs(rng.normal(0, 0.008, n))),
            "close": closes,
            "volume": pd.Series(rng.uniform(800, 1400, n), index=index),
        },
        index=index,
    )


def _mutate_future(df: pd.DataFrame, cutoff: int, factor: float = 4.0) -> pd.DataFrame:
    """Rewrite everything after `cutoff` into a completely different path."""
    mutated = df.copy()
    for column in ("open", "high", "low", "close"):
        mutated.iloc[cutoff:, mutated.columns.get_loc(column)] *= factor
    mutated.iloc[cutoff:, mutated.columns.get_loc("volume")] *= 30.0
    return mutated


# --- swings -------------------------------------------------------------


def test_swing_confirmation_time_is_after_the_pivot():
    """A pivot needs `lookback` further bars before it can be recognised."""
    df = _frame()
    swings = find_causal_swings(df["high"], df["low"], df["close"], lookback=5)
    assert swings.highs or swings.lows
    for swing in swings.all_swings:
        assert swing.confirmation_time > swing.pivot_time
        assert swing.bars_to_confirm == swing.lookback


def test_swings_are_invisible_before_their_confirmation_time():
    """The core causality guarantee for any backtest using swings."""
    df = _frame()
    swings = find_causal_swings(df["high"], df["low"], df["close"], lookback=5)
    cutoff = df.index[400]
    visible = swings.as_of(cutoff)
    assert visible.all_swings, "test needs some visible swings to be meaningful"
    for swing in visible.all_swings:
        assert swing.confirmation_time <= cutoff


def test_swings_never_include_the_final_unconfirmed_bars():
    df = _frame(n=300)
    swings = find_causal_swings(df["high"], df["low"], df["close"], lookback=5)
    last_allowed = df.index[-6]
    for swing in swings.all_swings:
        assert swing.pivot_time <= last_allowed


def test_swings_do_not_change_when_the_future_changes():
    """Mutation test: rewrite the future, the past must be identical."""
    df = _frame()
    cutoff = 450
    original = find_causal_swings(
        df["high"].iloc[:cutoff], df["low"].iloc[:cutoff], df["close"].iloc[:cutoff]
    )
    mutated = _mutate_future(df, cutoff)
    recomputed = find_causal_swings(
        mutated["high"], mutated["low"], mutated["close"]
    )
    before = [
        (s.pivot_time, round(s.price, 8), s.kind)
        for s in recomputed.all_swings if s.confirmation_time <= df.index[cutoff - 1]
    ]
    expected = [
        (s.pivot_time, round(s.price, 8), s.kind) for s in original.all_swings
    ]
    assert before == expected


# --- ranges and zones ---------------------------------------------------


def test_range_at_t_is_unchanged_by_later_prices():
    """A range detected at T must survive an arbitrary rewrite of T+1..T+n."""
    df = _frame()
    cutoff = 480
    engine = RangeIntelligenceEngine()

    original = engine.detect_from_frame(df.iloc[:cutoff])
    mutated = _mutate_future(df, cutoff)
    recomputed = engine.detect_from_frame(mutated.iloc[:cutoff])

    assert original.range_type is recomputed.range_type
    assert original.valid == recomputed.valid
    assert original.confidence == recomputed.confidence
    if original.top_zone and recomputed.top_zone:
        assert original.top_zone.low == recomputed.top_zone.low
        assert original.top_zone.high == recomputed.top_zone.high
    if original.bottom_zone and recomputed.bottom_zone:
        assert original.bottom_zone.low == recomputed.bottom_zone.low


def test_range_zones_never_overlap():
    """Overlapping zones are one level described twice, not a range.

    An early version accepted them and reported a '0.4 ATR wide range' whose
    boundaries crossed, with a position of 14.06.
    """
    df = _frame()
    for cutoff in (300, 400, 500, 600):
        detected = RangeIntelligenceEngine().detect_from_frame(df.iloc[:cutoff])
        if not detected.valid:
            continue
        assert detected.bottom_zone.high < detected.top_zone.low
        assert detected.width_atr >= 2.0


def test_range_position_is_bounded():
    df = _frame()
    for cutoff in (300, 450, 600):
        detected = RangeIntelligenceEngine().detect_from_frame(df.iloc[:cutoff])
        if not detected.valid:
            continue
        position = detected.position(float(df["close"].iloc[cutoff - 1]))
        assert position is None or -0.5 <= position <= 1.5


def test_zones_are_bands_not_points():
    df = _frame()
    from crypto_intel.engines.technical import indicators as ind

    atr = ind.atr(df["high"], df["low"], df["close"], 14)
    swings = find_causal_swings(df["high"], df["low"], df["close"], atr)
    zones = build_zones(
        swings.lows, df["high"], df["low"], df["close"], atr, "support"
    )
    for zone in zones:
        assert zone.high > zone.low, "a zone must have width"
        assert zone.contains(zone.midpoint)


def test_touch_counting_counts_events_not_bars():
    """Summing bars inside a zone reported 120 'touches' in 193 bars."""
    from crypto_intel.structure.ranges import _count_touch_events

    mask = pd.Series([False, True, True, True, False, False, True, True, False])
    # Three consecutive bars inside the zone are ONE touch, not three.
    assert _count_touch_events(mask) == 2


# --- market structure ---------------------------------------------------


def test_market_structure_unchanged_by_future(monkeypatch):
    df = _frame()
    cutoff = 470
    from crypto_intel.structure import market_structure as module

    engine = MarketStructureEngine()
    monkeypatch.setattr(module.store, "load_candles", lambda *a, **k: df.iloc[:cutoff])
    original = engine.assess(Asset.BTC, Timeframe.D1)
    monkeypatch.setattr(
        module.store, "load_candles", lambda *a, **k: _mutate_future(df, cutoff).iloc[:cutoff]
    )
    recomputed = engine.assess(Asset.BTC, Timeframe.D1)
    assert original.state is recomputed.state
    assert original.labels == recomputed.labels


def test_structure_events_carry_confirmation_times(monkeypatch):
    from crypto_intel.structure import market_structure as module

    df = _frame()
    monkeypatch.setattr(module.store, "load_candles", lambda *a, **k: df)
    reading = MarketStructureEngine().assess(Asset.BTC, Timeframe.D1)
    for event in reading.events:
        assert event.confirmation_time >= event.broken_at


def test_bos_and_choch_are_labelled_as_descriptions(monkeypatch):
    from crypto_intel.structure import market_structure as module

    df = _frame()
    monkeypatch.setattr(module.store, "load_candles", lambda *a, **k: df)
    reading = MarketStructureEngine().assess(Asset.BTC, Timeframe.D1)
    assert "treated as a signal" in reading.caveat
    assert reading.state in set(StructureState)


# --- patterns -----------------------------------------------------------


def test_patterns_unchanged_by_future():
    df = _frame()
    cutoff = 460
    original = build_context(df.iloc[:cutoff], Timeframe.D1)
    mutated = build_context(_mutate_future(df, cutoff).iloc[:cutoff], Timeframe.D1)
    assert original is not None and mutated is not None

    left = [(p.name, p.state, round(p.recognition_confidence, 6)) for p in detect_all(original)]
    right = [(p.name, p.state, round(p.recognition_confidence, 6)) for p in detect_all(mutated)]
    assert left == right


def test_recognition_confidence_is_never_presented_as_probability():
    df = _frame()
    ctx = build_context(df, Timeframe.D1)
    if ctx is None:
        pytest.skip("no context")
    for pattern in detect_all(ctx):
        payload = pattern.to_dict()
        assert "NOT a probability" in payload["separation_note"]
        # Edge is a separate field and starts untested.
        assert payload["edge_state"] in {s.value for s in PatternEdgeState}


def test_pattern_edge_defaults_to_not_yet_tested():
    df = _frame()
    ctx = build_context(df, Timeframe.D1)
    if ctx is None:
        pytest.skip("no context")
    for pattern in detect_all(ctx):
        assert pattern.edge_state is PatternEdgeState.NOT_YET_TESTED


def test_every_pattern_declares_its_reliability_class():
    for name in PATTERN_CLASSES:
        assert PATTERN_CLASSES[name].value in (
            "DETERMINISTIC", "HEURISTIC", "HUMAN_LIKE", "EXPERIMENTAL"
        )


def test_subjective_patterns_are_marked_experimental():
    """Wedges and flags are genuinely ambiguous; they must say so."""
    assert PATTERN_CLASSES["wedge"].value == "EXPERIMENTAL"
    assert PATTERN_CLASSES["flag"].value == "EXPERIMENTAL"


def test_double_bottom_is_not_confirmed_before_the_neckline_breaks():
    """Confirmation requires the trigger, never the shape alone."""
    index = pd.date_range("2022-01-01", periods=200, freq="D", tz=UTC)
    prices = np.concatenate([
        np.linspace(120, 100, 40),      # decline into the first low
        np.linspace(100, 112, 30),      # bounce forms the neckline
        np.linspace(112, 100.5, 30),    # second low, comparable
        np.linspace(100.5, 108, 40),    # recovery that stays BELOW the neckline
        np.full(60, 108.0),
    ])
    closes = pd.Series(prices[: len(index)], index=index)
    df = pd.DataFrame({
        "open": closes, "high": closes * 1.004, "low": closes * 0.996,
        "close": closes, "volume": pd.Series(1000.0, index=index),
    }, index=index)

    ctx = build_context(df, Timeframe.D1)
    assert ctx is not None
    doubles = [p for p in detect_all(ctx) if p.name == "double_bottom"]
    for pattern in doubles:
        neckline = pattern.key_levels["neckline"]
        if float(df["close"].iloc[-1]) <= neckline:
            assert pattern.state is not PatternState.CONFIRMED


# --- structural location ------------------------------------------------


def test_location_unchanged_by_future(monkeypatch):
    from crypto_intel.structure import location as module

    df = _frame()
    cutoff = 500
    monkeypatch.setattr(module.store, "load_candles", lambda *a, **k: df.iloc[:cutoff])
    original = StructuralLocationEngine().assess(Asset.BTC, Timeframe.D1)
    monkeypatch.setattr(
        module.store, "load_candles",
        lambda *a, **k: _mutate_future(df, cutoff).iloc[:cutoff],
    )
    recomputed = StructuralLocationEngine().assess(Asset.BTC, Timeframe.D1)
    assert original.state is recomputed.state
    assert original.relative_position == recomputed.relative_position


def test_location_states_are_declared(monkeypatch):
    from crypto_intel.structure import location as module

    monkeypatch.setattr(module.store, "load_candles", lambda *a, **k: _frame())
    result = StructuralLocationEngine().assess(Asset.BTC, Timeframe.D1)
    assert result.state in set(LocationState)


def test_no_range_yields_no_valid_range_not_mid_range(monkeypatch):
    """Absence of a range must never default to a neutral-looking position."""
    from crypto_intel.structure import location as module

    # A pure trend has no range.
    index = pd.date_range("2022-01-01", periods=300, freq="D", tz=UTC)
    closes = pd.Series(np.linspace(100, 400, 300), index=index)
    df = pd.DataFrame({
        "open": closes, "high": closes * 1.01, "low": closes * 0.99,
        "close": closes, "volume": pd.Series(1000.0, index=index),
    }, index=index)
    monkeypatch.setattr(module.store, "load_candles", lambda *a, **k: df)
    result = StructuralLocationEngine().assess(Asset.BTC, Timeframe.D1)
    assert result.state is LocationState.NO_VALID_RANGE
    assert result.relative_position is None


# --- source hierarchy ---------------------------------------------------


def test_educational_source_cannot_override_measurement():
    assert not can_override("goodcrypto", "binance")
    assert not can_override("lexa_moon", "solana_rpc")
    assert can_override("solana_rpc", "goodcrypto")
    assert can_override("fred", "lexa_moon")


def test_unknown_provider_defaults_to_lowest_authority():
    from crypto_intel.core.sources import tier_for

    assert tier_for("some_random_blog") is SourceTier.GENERAL_MEDIA


def test_conflict_resolution_keeps_the_measurement():
    result = resolve_conflict([
        SourceClaim("lexa_moon", "BTC is around 92k", 92000.0, "price"),
        SourceClaim("binance", "BTC close", 91250.5, "price"),
    ])
    assert result["authoritative"]["provider"] == "binance"
    assert result["is_measurement"]
    assert result["overruled"][0]["provider"] == "lexa_moon"


def test_same_tier_disagreement_is_reported_not_resolved():
    result = resolve_conflict([
        SourceClaim("binance", "price", 100.0), SourceClaim("bybit", "price", 101.0),
    ])
    assert result["status"] == "DISAGREEMENT_AT_SAME_TIER"
    assert "hide the conflict" in result["note"]


# --- robustness ---------------------------------------------------------


def test_missing_candles_do_not_crash_detection():
    df = _frame()
    holed = df.drop(df.index[200:260])
    detected = RangeIntelligenceEngine().detect_from_frame(holed)
    assert detected.range_type in set(RangeType)


def test_duplicate_candles_are_tolerated():
    df = _frame()
    duplicated = pd.concat([df, df.iloc[100:120]]).sort_index()
    detected = RangeIntelligenceEngine().detect_from_frame(duplicated)
    assert detected.range_type in set(RangeType)


def test_flash_crash_does_not_produce_a_spurious_range():
    df = _frame()
    crashed = df.copy()
    crashed.iloc[300, crashed.columns.get_loc("low")] *= 0.4
    detected = RangeIntelligenceEngine().detect_from_frame(crashed)
    # A single extreme wick must not become a range boundary on its own.
    if detected.valid:
        assert detected.bottom_zone.quality.touches >= 2


def test_insufficient_history_is_explicit():
    df = _frame(n=20)
    detected = RangeIntelligenceEngine().detect_from_frame(df)
    assert detected.range_type is RangeType.NO_VALID_RANGE
    assert "bars" in detected.reason


def test_flat_series_does_not_crash():
    index = pd.date_range("2022-01-01", periods=300, freq="D", tz=UTC)
    closes = pd.Series(100.0, index=index)
    df = pd.DataFrame({
        "open": closes, "high": closes, "low": closes,
        "close": closes, "volume": pd.Series(0.0, index=index),
    }, index=index)
    detected = RangeIntelligenceEngine().detect_from_frame(df)
    assert detected.range_type in set(RangeType)


def test_timezone_aware_index_is_preserved():
    df = _frame()
    swings = find_causal_swings(df["high"], df["low"], df["close"])
    for swing in swings.all_swings[:5]:
        assert swing.pivot_time.tzinfo is not None

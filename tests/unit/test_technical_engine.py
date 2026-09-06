"""Technical engine: structure, levels, patterns, multi-timeframe."""

from __future__ import annotations

from crypto_intel.core.enums import (
    Asset,
    ConfirmationState,
    Direction,
    MarketStructure,
    Timeframe,
    TrendDirection,
)
from crypto_intel.engines.mtf import MultiTimeframeEngine
from crypto_intel.engines.technical.engine import TechnicalAnalysisEngine
from crypto_intel.engines.technical.patterns import registered_names
from crypto_intel.engines.technical.structure import classify_structure, find_swings


class TestEngineOutput:
    def test_analyzes_a_clean_uptrend(self, sample_series):
        snap = TechnicalAnalysisEngine().analyze(sample_series)
        assert snap.has_data
        assert snap.trend.direction is TrendDirection.UPTREND
        assert snap.rsi is not None and snap.ema20 is not None
        assert snap.price_vs_ema200_pct is not None and snap.price_vs_ema200_pct > 0

    def test_too_few_candles_is_unavailable(self):
        from datetime import UTC, datetime

        from crypto_intel.core.models import Candle, OHLCVSeries, Provenance

        series = OHLCVSeries(
            asset=Asset.BTC, timeframe=Timeframe.D1,
            candles=[Candle(timestamp=datetime.now(UTC), open=1, high=1, low=1, close=1, volume=1)],
            provenance=Provenance(source="t", provider="t"),
        )
        snap = TechnicalAnalysisEngine().analyze(series)
        assert not snap.has_data
        assert any("UNAVAILABLE" in n for n in snap.notes)

    def test_short_history_reports_missing_ema200(self, sample_series):
        """Never silently compute an EMA200 from 100 bars."""
        truncated = sample_series.model_copy(update={"candles": sample_series.candles[:100]})
        snap = TechnicalAnalysisEngine().analyze(truncated)
        assert snap.ema200 is None
        assert any("EMA200" in n for n in snap.notes)


class TestStructure:
    def test_finds_swings_in_an_oscillating_series(self, ranging_df):
        highs, lows = find_swings(ranging_df["high"], ranging_df["low"], lookback=5)
        assert len(highs) > 3 and len(lows) > 3

    def test_swings_exclude_unconfirmed_recent_bars(self, ranging_df):
        """A pivot needs bars on both sides; the last bars cannot be confirmed."""
        highs, lows = find_swings(ranging_df["high"], ranging_df["low"], lookback=5)
        last_index = len(ranging_df) - 1
        for sp in highs + lows:
            assert sp.index <= last_index - 5

    def test_insufficient_swings_is_undetermined(self):
        structure, labels = classify_structure([], [])
        assert structure is MarketStructure.UNDETERMINED
        assert labels == []

    def test_range_is_not_labelled_a_trend(self, ranging_df):
        from crypto_intel.engines.technical import indicators as ind
        from crypto_intel.engines.technical.structure import determine_trend

        close = ranging_df["close"]
        trend = determine_trend(
            close, ind.ema(close, 20), ind.ema(close, 50), ind.ema(close, 200),
            ind.adx(ranging_df["high"], ranging_df["low"], close, 14),
        )
        assert trend.direction is TrendDirection.RANGE
        assert trend.reason


class TestPatterns:
    def test_expected_detectors_registered(self):
        names = registered_names()
        for expected in ("double_top", "double_bottom", "range", "breakout",
                         "fake_breakout", "head_and_shoulders",
                         "inverse_head_and_shoulders", "triangle"):
            assert expected in names

    def test_patterns_carry_required_fields(self, sample_series):
        snap = TechnicalAnalysisEngine().analyze(sample_series)
        for p in snap.patterns:
            assert p.pattern and 0 <= p.confidence <= 100
            assert isinstance(p.confirmation_state, ConfirmationState)
            assert p.timeframe is Timeframe.D1

    def test_low_confidence_patterns_are_not_reported(self, sample_series):
        """Never announce a shape just because it vaguely resembles a pattern."""
        from crypto_intel.config_loader import threshold

        floor = float(threshold("patterns", "min_confidence", default=55))
        snap = TechnicalAnalysisEngine().analyze(sample_series)
        assert all(p.confidence >= floor for p in snap.patterns)

    def test_flat_line_produces_no_reversal_pattern(self):
        """A featureless series must not yield a double top or H&S."""
        from datetime import UTC, datetime, timedelta

        from crypto_intel.core.models import Candle, OHLCVSeries, Provenance

        start = datetime(2026, 1, 1, tzinfo=UTC)
        candles = [
            Candle(timestamp=start + timedelta(days=i), open=100, high=100,
                   low=100, close=100, volume=10)
            for i in range(120)
        ]
        series = OHLCVSeries(
            asset=Asset.BTC, timeframe=Timeframe.D1, candles=candles,
            provenance=Provenance(source="t", provider="t"),
        )
        snap = TechnicalAnalysisEngine().analyze(series)
        reversal = {"double_top", "double_bottom", "head_and_shoulders",
                    "inverse_head_and_shoulders"}
        assert not [p for p in snap.patterns if p.pattern in reversal]


class TestMultiTimeframe:
    def test_higher_timeframes_weigh_more(self):
        engine = MultiTimeframeEngine()
        assert engine.weight_for(Timeframe.D1) > engine.weight_for(Timeframe.M15)
        assert engine.weight_for(Timeframe.W1) > engine.weight_for(Timeframe.H1)

    def test_no_data_is_inconclusive(self):
        result = MultiTimeframeEngine().analyze(Asset.BTC, {})
        assert result.dominant_direction is Direction.INCONCLUSIVE
        assert result.timeframes_available == 0

    def test_conflicts_are_reported_not_averaged(self, sample_series, ranging_df):
        """Disagreement between timeframes must be named explicitly."""
        from crypto_intel.core.models import Candle, OHLCVSeries, Provenance

        tech = TechnicalAnalysisEngine()
        up = tech.analyze(sample_series)

        down_candles = [
            Candle(timestamp=c.timestamp, open=c.open, high=c.high, low=c.low,
                   close=c.close, volume=c.volume)
            for c in reversed(sample_series.candles)
        ]
        # Rebuild with increasing timestamps so it reads as a genuine downtrend.
        fixed = [
            Candle(timestamp=sample_series.candles[i].timestamp,
                   open=down_candles[i].open, high=down_candles[i].high,
                   low=down_candles[i].low, close=down_candles[i].close,
                   volume=down_candles[i].volume)
            for i in range(len(down_candles))
        ]
        down_series = OHLCVSeries(
            asset=Asset.BTC, timeframe=Timeframe.M15, candles=fixed,
            provenance=Provenance(source="t", provider="t"),
        )
        down = tech.analyze(down_series)

        result = MultiTimeframeEngine().analyze(
            Asset.BTC, {Timeframe.D1: up, Timeframe.M15: down}
        )
        assert result.timeframes_available == 2
        if {v.direction for v in result.verdicts if v.available} >= {
            Direction.BULLISH, Direction.BEARISH
        }:
            assert result.conflicts

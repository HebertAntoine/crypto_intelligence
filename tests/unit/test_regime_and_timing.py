"""MarketRegimeEngine and EntryTimingEngine.

The property that matters most: the two are INDEPENDENT. A bullish regime must
be able to coexist with poor entry timing, because that is the situation the
whole feature exists to expose.
"""

from __future__ import annotations

from typing import ClassVar

import pytest

from crypto_intel.core.enums import Asset, Freshness, Timeframe
from crypto_intel.core.models import Candle, OHLCVSeries, Provenance
from crypto_intel.engines.entry_timing import EntryTiming, EntryTimingEngine
from crypto_intel.engines.regime import MarketCondition, MarketRegime, MarketRegimeEngine
from crypto_intel.engines.technical.engine import TechnicalAnalysisEngine


def make_series(df, asset=Asset.BTC, timeframe=Timeframe.D1) -> OHLCVSeries:
    candles = [
        Candle(timestamp=ts, open=r.open, high=r.high, low=r.low, close=r.close, volume=r.volume)
        for ts, r in df.iterrows()
    ]
    return OHLCVSeries(
        asset=asset, timeframe=timeframe, candles=candles,
        provenance=Provenance(source="test", provider="test"),
        freshness=Freshness.LIVE,
    )


@pytest.fixture
def snapshots(trending_up_df, realistic_history):
    engine = TechnicalAnalysisEngine()
    return {
        Timeframe.D1: engine.analyze(make_series(realistic_history)),
        Timeframe.W1: engine.analyze(make_series(realistic_history.iloc[::7], timeframe=Timeframe.W1)),
        Timeframe.H4: engine.analyze(make_series(trending_up_df, timeframe=Timeframe.H4)),
        Timeframe.H1: engine.analyze(make_series(trending_up_df, timeframe=Timeframe.H1)),
    }


class TestMarketRegime:
    def test_no_data_is_undetermined(self):
        result = MarketRegimeEngine().assess(Asset.BTC, {})
        assert result.regime is MarketRegime.UNDETERMINED
        assert "UNAVAILABLE" in result.summary

    def test_produces_a_regime_with_evidence(self, snapshots):
        result = MarketRegimeEngine().assess(Asset.BTC, {"snapshots": snapshots})
        assert result.regime is not MarketRegime.UNDETERMINED
        assert result.factors, "regime must expose the factors that produced it"
        assert -100 <= result.regime_score <= 100
        assert result.summary

    def test_uptrend_reads_bullish(self, trending_up_df):
        engine = TechnicalAnalysisEngine()
        snaps = {Timeframe.D1: engine.analyze(make_series(trending_up_df))}
        result = MarketRegimeEngine().assess(Asset.BTC, {"snapshots": snaps})
        assert result.regime in (MarketRegime.BULLISH, MarketRegime.STRONGLY_BULLISH)

    def test_missing_domains_are_listed_not_counted_as_neutral(self, snapshots):
        result = MarketRegimeEngine().assess(Asset.BTC, {"snapshots": snapshots})
        assert result.missing, "domains without data must be reported"
        assert all(f.weight >= 0 for f in result.factors)

    def test_conditions_are_separate_from_direction(self, snapshots):
        """A regime is a direction; conditions describe character. A market can
        be bullish AND overheated - these must not collapse into one label."""
        result = MarketRegimeEngine().assess(Asset.BTC, {"snapshots": snapshots})
        assert isinstance(result.conditions, list)
        for condition in result.conditions:
            assert isinstance(condition, MarketCondition)

    def test_extreme_funding_flags_overheated(self, snapshots):
        class FakeDerivatives:
            available = True
            funding_state = "EXTREME_POSITIVE"
            oi_change_24h_pct = 20.0
            evidence_ids: ClassVar[list[str]] = []

        result = MarketRegimeEngine().assess(
            Asset.BTC, {"snapshots": snapshots, "derivatives": FakeDerivatives()}
        )
        assert MarketCondition.OVERHEATED in result.conditions
        assert MarketCondition.LEVERAGE_BUILDUP in result.conditions


class TestEntryTiming:
    def test_no_data_is_undetermined(self):
        result = EntryTimingEngine().assess(Asset.BTC, {})
        assert result.timing is EntryTiming.UNDETERMINED
        assert "UNAVAILABLE" in result.summary

    def test_produces_score_factors_and_explanation(self, snapshots):
        result = EntryTimingEngine().assess(Asset.BTC, {"snapshots": snapshots})
        assert -100 <= result.timing_score <= 100
        assert result.factors
        assert result.explanation, "the WHY panel needs a readable formula"
        assert "weighted" in result.explanation.lower()

    def test_overextended_price_penalises_timing(self, trending_up_df):
        """Buying far above the 20-EMA must score worse than buying near it."""
        engine = TechnicalAnalysisEngine()
        timing_engine = EntryTimingEngine()

        normal = {Timeframe.D1: engine.analyze(make_series(trending_up_df))}
        baseline = timing_engine.assess(Asset.BTC, {"snapshots": normal})

        stretched_df = trending_up_df.copy()
        stretched_df.iloc[-1, stretched_df.columns.get_loc("close")] *= 1.25
        stretched_df.iloc[-1, stretched_df.columns.get_loc("high")] *= 1.25
        stretched = {Timeframe.D1: engine.analyze(make_series(stretched_df))}
        extended = timing_engine.assess(Asset.BTC, {"snapshots": stretched})

        assert extended.timing_score < baseline.timing_score

    def test_imminent_macro_event_penalises_timing(self, snapshots):
        from datetime import UTC, datetime, timedelta

        from crypto_intel.core.models import MacroEvent

        class FakeMacro:
            available = True
            imminent_event = MacroEvent(
                name="US CPI", kind="CPI",
                scheduled_at=datetime.now(UTC) + timedelta(hours=2),
                importance="CRITICAL", hours_until=2.0,
            )
            upcoming_events: ClassVar[list] = [imminent_event]

        without = EntryTimingEngine().assess(Asset.BTC, {"snapshots": snapshots})
        with_event = EntryTimingEngine().assess(
            Asset.BTC, {"snapshots": snapshots, "macro": FakeMacro()}
        )
        assert with_event.timing_score < without.timing_score
        assert any("CPI" in r for r in with_event.risks)

    def test_invalidation_comes_from_a_computed_level(self, snapshots):
        """Never an arbitrary number - it must trace to a support or an EMA."""
        result = EntryTimingEngine().assess(Asset.BTC, {"snapshots": snapshots})
        if result.invalidation_level is not None:
            assert result.invalidation_reason
            assert any(
                word in result.invalidation_reason.lower()
                for word in ("support", "ema", "swing")
            )

    def test_zones_declare_their_basis(self, snapshots):
        result = EntryTimingEngine().assess(Asset.BTC, {"snapshots": snapshots})
        for zone in result.zones_to_watch:
            assert zone.basis, "every zone must state what it derives from"

    def test_partial_bar_excludes_volume_factor(self, snapshots):
        """A forming bar's volume is a partial accumulation - comparing it to
        completed bars would penalise timing every morning."""
        daily = snapshots[Timeframe.D1]
        if daily.last_bar_partial:
            result = EntryTimingEngine().assess(Asset.BTC, {"snapshots": snapshots})
            volume_factors = [f for f in result.factors if f.name == "volume"]
            assert not volume_factors
            assert any("volume" in m for m in result.missing)


class TestIndependence:
    def test_regime_and_timing_can_disagree(self, trending_up_df):
        """The headline feature: a strong uptrend with an overextended price
        should give a favourable regime and an unfavourable entry."""
        engine = TechnicalAnalysisEngine()

        stretched = trending_up_df.copy()
        for column in ("close", "high", "low", "open"):
            stretched.iloc[-1, stretched.columns.get_loc(column)] *= 1.30

        snaps = {Timeframe.D1: engine.analyze(make_series(stretched))}
        regime = MarketRegimeEngine().assess(Asset.BTC, {"snapshots": snaps})
        timing = EntryTimingEngine().assess(Asset.BTC, {"snapshots": snaps})

        assert regime.regime in (MarketRegime.BULLISH, MarketRegime.STRONGLY_BULLISH)
        assert timing.timing in (
            EntryTiming.WAIT, EntryTiming.UNFAVORABLE, EntryTiming.VERY_UNFAVORABLE
        )

    def test_they_are_computed_from_independent_scales(self, snapshots):
        regime = MarketRegimeEngine().assess(Asset.BTC, {"snapshots": snapshots})
        timing = EntryTimingEngine().assess(Asset.BTC, {"snapshots": snapshots})
        regime_factors = {f.name for f in regime.factors}
        timing_factors = {f.name for f in timing.factors}
        # They may share inputs, but must not be the same factor set.
        assert regime_factors != timing_factors

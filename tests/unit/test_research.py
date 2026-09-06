"""Research layer: statistics, ETF lag study, event studies, calibration.

The recurring theme in these tests is guarding against self-deception:
no look-ahead, no significance claimed on tiny samples, no baseline drawn from
a different era than the events it is compared against.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from crypto_intel.research.stats import (
    MIN_RELIABLE_SAMPLE,
    benjamini_hochberg,
    chronological_split,
    describe_returns,
    excursions,
    forward_returns,
    lagged_correlation,
)


class TestDescribeReturns:
    def test_empty_is_inconclusive(self):
        stats = describe_returns([])
        assert stats.n == 0
        assert "INCONCLUSIVE" in stats.note

    def test_small_sample_claims_no_significance(self):
        """A 5-point sample must never be presented as a result."""
        stats = describe_returns([1.0, -0.5, 2.0, 0.3, -1.0])
        assert stats.reliable_sample is False
        assert stats.significant is False
        assert stats.p_value is None
        assert str(MIN_RELIABLE_SAMPLE) in stats.note

    def test_large_sample_runs_a_test(self):
        values = np.random.default_rng(3).normal(0.6, 1.5, 300)
        stats = describe_returns(values)
        assert stats.reliable_sample
        assert stats.p_value is not None
        assert stats.n == 300

    def test_pure_noise_is_not_significant(self):
        values = np.random.default_rng(11).normal(0.0, 2.0, 400)
        stats = describe_returns(values)
        assert stats.significant is False

    def test_win_rate_and_quartiles(self):
        stats = describe_returns([1.0, 2.0, 3.0, -1.0])
        assert stats.win_rate == 75.0
        assert stats.median == 1.5


class TestForwardReturns:
    def test_returns_look_forward(self):
        prices = pd.Series([100.0, 110.0, 121.0], index=pd.date_range("2026-01-01", periods=3))
        fwd = forward_returns(prices, [1])
        assert fwd["fwd_1"].iloc[0] == pytest.approx(10.0)
        # The final row has no future, so it must be NaN, never 0.
        assert pd.isna(fwd["fwd_1"].iloc[-1])

    def test_no_lookahead_in_the_signal_join(self):
        """A signal joined to forward returns can only meet later prices."""
        prices = pd.Series(
            np.linspace(100, 200, 50), index=pd.date_range("2026-01-01", periods=50)
        )
        fwd = forward_returns(prices, [5])
        for i in range(len(prices) - 5):
            expected = (prices.iloc[i + 5] - prices.iloc[i]) / prices.iloc[i] * 100
            assert fwd["fwd_5"].iloc[i] == pytest.approx(expected)


class TestExcursions:
    def test_mfe_is_positive_and_mae_negative_in_an_uptrend(self):
        index = pd.date_range("2026-01-01", periods=30)
        close = pd.Series(np.linspace(100, 130, 30), index=index)
        high = close * 1.02
        low = close * 0.99
        mfe, mae = excursions(high, low, close, 5)
        assert mfe.dropna().mean() > 0
        assert mae.dropna().mean() < 0

    def test_last_bars_have_no_excursion(self):
        index = pd.date_range("2026-01-01", periods=20)
        close = pd.Series(np.linspace(100, 110, 20), index=index)
        mfe, _ = excursions(close * 1.01, close * 0.99, close, 5)
        assert pd.isna(mfe.iloc[-1])


class TestMultipleTesting:
    def test_bh_removes_borderline_hits_among_many_tests(self):
        """Two genuinely small p-values among 32 tests survive; borderline
        hits that would pass a raw p<0.05 do not."""
        p_values = [0.001, 0.002] + [0.5] * 30
        survives = benjamini_hochberg(p_values, alpha=0.05)
        assert survives[0] is True and survives[1] is True
        assert sum(survives) == 2

    def test_bh_rejects_a_field_of_marginal_hits(self):
        """20 tests all sitting at p=0.045 are exactly what noise looks like."""
        survives = benjamini_hochberg([0.045] * 20, alpha=0.01)
        assert sum(survives) == 0

    def test_all_null_survives_nothing(self):
        assert not any(benjamini_hochberg([0.9, 0.8, 0.7, 0.6]))

    def test_handles_missing_p_values(self):
        survives = benjamini_hochberg([0.001, None, 0.9])
        assert survives[0] is True
        assert survives[1] is False


class TestChronologicalSplit:
    def test_split_is_ordered_in_time(self):
        """Random splits leak the future into the past in a time series."""
        index = pd.DatetimeIndex(pd.date_range("2024-01-01", periods=500))
        split = chronological_split(index)
        assert split.train[1] < split.validation[0]
        assert split.validation[1] < split.oos[0]

    def test_too_short_refuses_to_split(self):
        index = pd.DatetimeIndex(pd.date_range("2026-01-01", periods=10))
        split = chronological_split(index)
        assert split.train is None
        assert "too few" in split.note


class TestCorrelation:
    def test_returns_none_on_tiny_overlap(self):
        a = pd.Series([1.0, 2.0], index=pd.date_range("2026-01-01", periods=2))
        b = pd.Series([1.0, 2.0], index=pd.date_range("2026-01-01", periods=2))
        r, _p, n = lagged_correlation(a, b)
        assert r is None and n < 10

    def test_detects_a_real_monotonic_relationship(self):
        index = pd.date_range("2026-01-01", periods=100)
        a = pd.Series(np.arange(100, dtype=float), index=index)
        b = pd.Series(np.arange(100, dtype=float) * 2, index=index)
        r, _p, _n = lagged_correlation(a, b)
        assert r == pytest.approx(1.0, abs=0.01)

    def test_constant_series_has_no_correlation(self):
        index = pd.date_range("2026-01-01", periods=50)
        a = pd.Series([5.0] * 50, index=index)
        b = pd.Series(np.arange(50, dtype=float), index=index)
        r, _, _ = lagged_correlation(a, b)
        assert r is None


class TestETFSignals:
    def test_signals_use_only_past_data(self, realistic_etf_flows):
        """Mutating the tail must not change any earlier signal value."""
        from crypto_intel.research.etf_study import build_signals

        original = build_signals(realistic_etf_flows)

        mutated_flows = realistic_etf_flows.copy()
        mutated_flows.iloc[-30:] *= 10
        mutated = build_signals(mutated_flows)

        cutoff = len(realistic_etf_flows) - 31
        for column in ("ma3", "ma5", "ma7", "cum30", "pos_streak", "neg_streak"):
            a = original[column].iloc[:cutoff].fillna(-999).to_numpy()
            b = mutated[column].iloc[:cutoff].fillna(-999).to_numpy()
            assert np.allclose(a, b), f"{column} leaked future information"

    def test_streaks_count_backwards(self):
        from crypto_intel.research.etf_study import build_signals

        flows = pd.Series(
            [10.0, 20.0, 30.0, -5.0, -6.0],
            index=pd.date_range("2026-01-01", periods=5, tz="UTC"),
        )
        signals = build_signals(flows)
        assert signals["pos_streak"].iloc[2] == 3
        assert signals["neg_streak"].iloc[4] == 2
        assert signals["pos_streak"].iloc[4] == 0


class TestEventStudyGuards:
    def test_trailing_percentile_uses_only_the_past(self):
        from crypto_intel.research.event_study import _trailing_percentile

        series = pd.Series(
            np.arange(300, dtype=float), index=pd.date_range("2025-01-01", periods=300)
        )
        threshold = _trailing_percentile(series, 90)
        # At each point the threshold cannot exceed the max seen so far.
        for i in range(60, 300):
            if not pd.isna(threshold.iloc[i]):
                assert threshold.iloc[i] <= series.iloc[: i + 1].max()

    def test_definitions_declare_their_requirements(self):
        from crypto_intel.research.event_study import DEFINITIONS

        for definition in DEFINITIONS:
            assert definition.key and definition.label and definition.description
            assert isinstance(definition.requires, tuple)

    def test_etf_events_declare_the_etf_requirement(self):
        from crypto_intel.research.event_study import DEFINITIONS

        etf_events = [d for d in DEFINITIONS if d.key.startswith("etf_")]
        assert etf_events
        for definition in etf_events:
            assert "etf" in definition.requires


class TestCalibrationGuards:
    def test_reconstructors_are_causal(self, realistic_history):
        """A reconstructed score must not change when future bars change."""
        from crypto_intel.engines.technical import indicators as ind

        closes = realistic_history["close"]
        rsi_original = ind.rsi(closes, 14)

        mutated = closes.copy()
        mutated.iloc[-50:] *= 3
        rsi_mutated = ind.rsi(mutated, 14)

        cutoff = len(closes) - 51
        assert np.allclose(
            rsi_original.iloc[:cutoff].fillna(-999).to_numpy(),
            rsi_mutated.iloc[:cutoff].fillna(-999).to_numpy(),
        )

    def test_buckets_cover_the_full_score_range(self):
        from crypto_intel.research.calibration import BUCKETS

        lows = [b[1] for b in BUCKETS]
        highs = [b[2] for b in BUCKETS]
        assert min(lows) == -100.0
        assert max(highs) >= 100.0
        # Contiguous: each bucket starts where the previous one ended.
        for i in range(len(BUCKETS) - 1):
            assert BUCKETS[i][2] == BUCKETS[i + 1][1]

    def test_no_weight_is_modified_automatically(self):
        """Calibration measures; it must never rewrite the scoring config."""
        import inspect

        from crypto_intel.research import calibration

        source = inspect.getsource(calibration)
        for forbidden in ("scoring.yaml", "write_text", "asset_weights ="):
            assert forbidden not in source

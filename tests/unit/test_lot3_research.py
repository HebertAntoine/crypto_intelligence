"""LOT 3 research engines: walk-forward, stability, asymmetry, regime, RSI context."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from crypto_intel.core.enums import Asset
from crypto_intel.research.stats import decompose_ic
from crypto_intel.research.walkforward import (
    assess_stability,
    bucket_monotonicity,
    build_windows,
    walk_forward_ic,
)


@pytest.fixture
def long_series() -> tuple[pd.Series, pd.Series]:
    """A signal with a genuine, stable relationship to forward returns."""
    rng = np.random.default_rng(5)
    n = 1500
    index = pd.date_range("2021-01-01", periods=n, freq="D", tz="UTC")
    signal = pd.Series(rng.normal(0, 1, n), index=index)
    # Real but modest relationship, plus a lot of noise - like a real market.
    forward = pd.Series(signal.to_numpy() * 0.8 + rng.normal(0, 4, n), index=index)
    return signal, forward


@pytest.fixture
def noise_series() -> tuple[pd.Series, pd.Series]:
    rng = np.random.default_rng(9)
    n = 1500
    index = pd.date_range("2021-01-01", periods=n, freq="D", tz="UTC")
    return (
        pd.Series(rng.normal(0, 1, n), index=index),
        pd.Series(rng.normal(0, 4, n), index=index),
    )


class TestWalkForward:
    def test_windows_are_chronological_and_disjoint_in_test(self, long_series):
        signal, _ = long_series
        specs = build_windows(pd.DatetimeIndex(signal.index))
        assert specs
        for tr_s, tr_e, va_s, va_e, te_s, te_e in specs:
            assert tr_s < tr_e <= va_s < va_e <= te_s < te_e

    def test_short_history_returns_no_windows(self):
        index = pd.DatetimeIndex(pd.date_range("2026-01-01", periods=60, freq="D"))
        assert build_windows(index) == []

    def test_real_relationship_is_detected(self, long_series):
        signal, forward = long_series
        result = walk_forward_ic(signal, forward)
        assert result["available"]
        stability = result["stability"]
        assert stability["windows_total"] >= 3
        assert stability["sign_consistency"] > 0.5
        assert stability["verdict"] in ("USEFUL", "WEAK")

    def test_pure_noise_is_not_called_useful(self, noise_series):
        signal, forward = noise_series
        result = walk_forward_ic(signal, forward)
        assert result["available"]
        assert result["stability"]["verdict"] in (
            "NO_MEASURABLE_VALUE", "UNSTABLE", "INSUFFICIENT_DATA"
        )

    def test_insufficient_data_is_explicit(self):
        index = pd.date_range("2026-01-01", periods=50, freq="D", tz="UTC")
        signal = pd.Series(range(50), index=index, dtype=float)
        result = walk_forward_ic(signal, signal)
        assert not result["available"]
        assert "INSUFFICIENT_DATA" in result["reason"]


class TestStabilityScore:
    def _window(self, index, train_ic, test_ic, test_p=0.01, n=100):
        from crypto_intel.research.walkforward import WalkForwardWindow

        t = pd.Timestamp("2024-01-01", tz="UTC")
        return WalkForwardWindow(
            index=index, train_start=t, train_end=t, validation_start=t,
            validation_end=t, test_start=t, test_end=t,
            train_ic=train_ic, test_ic=test_ic, test_p=test_p, test_n=n,
        )

    def test_consistent_sign_scores_higher_than_flipping(self):
        consistent = [self._window(i, 0.1, 0.09) for i in range(6)]
        flipping = [
            self._window(i, 0.1, 0.09 if i % 2 == 0 else -0.09) for i in range(6)
        ]
        assert assess_stability(consistent).score > assess_stability(flipping).score

    def test_flipping_sign_is_unstable(self):
        flipping = [
            self._window(i, 0.1, 0.15 if i % 2 == 0 else -0.15) for i in range(6)
        ]
        assert assess_stability(flipping).verdict == "UNSTABLE"

    def test_large_train_test_gap_is_penalised(self):
        """A train IC far above the test IC means fitting, not finding."""
        honest = [self._window(i, 0.08, 0.07) for i in range(6)]
        overfit = [self._window(i, 0.45, 0.05) for i in range(6)]
        assert assess_stability(overfit).score < assess_stability(honest).score
        assert assess_stability(overfit).components["overfit_penalty"] < 0

    def test_tiny_effect_is_no_measurable_value(self):
        tiny = [self._window(i, 0.005, 0.004, test_p=0.9) for i in range(6)]
        assert assess_stability(tiny).verdict == "NO_MEASURABLE_VALUE"

    def test_effect_size_alone_does_not_buy_stability(self):
        """A huge but erratic edge must not outrank a small consistent one."""
        big_erratic = [
            self._window(i, 0.5, 0.6 if i % 2 == 0 else -0.5) for i in range(6)
        ]
        small_steady = [self._window(i, 0.06, 0.05) for i in range(6)]
        assert assess_stability(small_steady).score > assess_stability(big_erratic).score


class TestICDecomposition:
    def test_detects_a_purely_between_period_relationship(self):
        """The exact failure found in this project: a global IC that vanishes
        inside each period."""
        rng = np.random.default_rng(3)
        frames = []
        for year, level in enumerate([-2.0, -1.0, 0.0, 1.0, 2.0]):
            index = pd.date_range(f"{2020 + year}-01-01", periods=250, freq="D", tz="UTC")
            # Signal and return share a per-period LEVEL but are unrelated within it.
            signal = pd.Series(level + rng.normal(0, 0.3, 250), index=index)
            forward = pd.Series(level * 2 + rng.normal(0, 5, 250), index=index)
            frames.append(pd.DataFrame({"s": signal, "f": forward}))
        combined = pd.concat(frames)

        result = decompose_ic(combined["s"], combined["f"])
        assert result["assessable"]
        assert abs(result["global_ic"]) > 0.1
        assert abs(result["mean_within_ic"]) < abs(result["global_ic"]) * 0.5
        assert result["globally_inflated"] is True
        assert "separates eras" in result["interpretation"]

    def test_genuine_within_period_relationship_is_not_flagged(self):
        rng = np.random.default_rng(4)
        n = 1250
        index = pd.date_range("2021-01-01", periods=n, freq="D", tz="UTC")
        signal = pd.Series(rng.normal(0, 1, n), index=index)
        forward = pd.Series(signal.to_numpy() * 1.5 + rng.normal(0, 3, n), index=index)

        result = decompose_ic(signal, forward)
        assert result["assessable"]
        assert result["globally_inflated"] is False
        assert result["periods_positive"] >= result["periods_total"] - 1


class TestMonotonicity:
    def test_monotonic_signal_is_recognised(self):
        rng = np.random.default_rng(7)
        n = 800
        index = pd.date_range("2022-01-01", periods=n, freq="D", tz="UTC")
        signal = pd.Series(np.linspace(-3, 3, n), index=index)
        forward = pd.Series(signal.to_numpy() * 2 + rng.normal(0, 2, n), index=index)
        result = bucket_monotonicity(signal, forward)
        assert result["assessable"]
        assert result["monotonic"] is True

    def test_non_monotonic_signal_is_rejected(self):
        rng = np.random.default_rng(8)
        n = 800
        index = pd.date_range("2022-01-01", periods=n, freq="D", tz="UTC")
        signal = pd.Series(np.linspace(-3, 3, n), index=index)
        # U-shape: both extremes good, middle bad. Correlation ~0, and a higher
        # reading is emphatically not better.
        forward = pd.Series(signal.to_numpy() ** 2 + rng.normal(0, 1, n), index=index)
        result = bucket_monotonicity(signal, forward)
        assert result["assessable"]
        assert result["monotonic"] is False


class TestETFAsymmetry:
    def test_categorisation_is_roughly_decile_shaped(self):
        """The bug that made 388/664 days 'extreme outflow' must not return."""
        from crypto_intel.research.etf_asymmetry import categorise_flows

        rng = np.random.default_rng(11)
        n = 700
        index = pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC")
        flows = pd.Series(rng.normal(50, 200, n), index=index)

        labels = categorise_flows(flows).dropna()
        counts = labels.value_counts()
        assert set(counts.index) >= {"extreme_outflow", "neutral", "extreme_inflow"}
        # No single category may swallow the distribution.
        assert counts.max() / counts.sum() < 0.5
        assert counts.get("extreme_inflow", 0) > 0

    def test_nan_days_do_not_become_a_category(self):
        from crypto_intel.research.etf_asymmetry import categorise_flows

        index = pd.date_range("2024-01-01", periods=400, freq="D", tz="UTC")
        flows = pd.Series(np.nan, index=index)
        flows.iloc[200:] = np.random.default_rng(2).normal(0, 100, 200)
        labels = categorise_flows(flows)
        assert labels.iloc[:150].isna().all()

    def test_no_asymmetry_claimed_without_support(self):
        from crypto_intel.research.etf_asymmetry import compare_tails

        result = compare_tails({
            "extreme_inflow": {
                "available": True,
                "horizons": {
                    f"{h}d": {
                        "edge_vs_baseline": 0.1, "significant_fdr": False,
                        "ci_excludes_zero": False,
                    } for h in (1, 3, 7, 14, 30)
                },
            },
            "extreme_outflow": {
                "available": True,
                "horizons": {
                    f"{h}d": {
                        "edge_vs_baseline": -0.4, "significant_fdr": False,
                        "ci_excludes_zero": False,
                    } for h in (1, 3, 7, 14, 30)
                },
            },
        })
        assert result["verdict"] == "NO_ASYMMETRY_DEMONSTRATED"


class TestDerivativesPercentiles:
    def test_trailing_rank_is_bounded_and_causal(self):
        from crypto_intel.research.derivatives_study import trailing_rank

        rng = np.random.default_rng(13)
        index = pd.date_range("2022-01-01", periods=600, freq="D", tz="UTC")
        series = pd.Series(rng.normal(0, 1, 600), index=index)
        ranks = trailing_rank(series).dropna()
        assert ranks.min() >= 0.0
        assert ranks.max() <= 100.0

    def test_percentile_bands_cover_the_range(self):
        from crypto_intel.research.derivatives_study import PERCENTILE_BANDS

        lows = [b[1] for b in PERCENTILE_BANDS]
        highs = [b[2] for b in PERCENTILE_BANDS]
        assert min(lows) == 0.0
        assert max(highs) >= 100.0
        for i in range(len(PERCENTILE_BANDS) - 1):
            assert PERCENTILE_BANDS[i][2] == PERCENTILE_BANDS[i + 1][1]


class TestRegimeConditioning:
    def test_regime_reconstruction_is_deterministic(self, realistic_history):
        from crypto_intel.research.regime_conditioned import reconstruct_regime

        first = reconstruct_regime(realistic_history)
        second = reconstruct_regime(realistic_history)
        assert (first.fillna("NA") == second.fillna("NA")).all()

    def test_all_regime_labels_are_valid(self, realistic_history):
        from crypto_intel.research.regime_conditioned import REGIME_LABELS, reconstruct_regime

        labels = reconstruct_regime(realistic_history).dropna().unique()
        assert set(labels) <= set(REGIME_LABELS)

    def test_single_regime_signal_is_not_called_insufficient(self):
        """A signal that only fires in one regime is regime-dependent, not
        missing data."""
        from crypto_intel.research.regime_conditioned import _interpret_regime_split

        cells = {
            "STRONGLY_BULLISH": {
                "available": True, "n": 300, "edge_vs_regime": 2.5,
                "significant_fdr": True,
            },
            "BEARISH": {"available": False, "reason": "INSUFFICIENT_DATA - 4 days"},
        }
        result = _interpret_regime_split("rsi_overbought", cells)
        assert result["regime_dependent"] is True
        assert "occurs almost exclusively" in result["conclusion"]

    def test_sign_flip_across_regimes_is_reported(self):
        from crypto_intel.research.regime_conditioned import _interpret_regime_split

        cells = {
            "STRONGLY_BULLISH": {"available": True, "n": 200, "edge_vs_regime": 2.0},
            "STRONGLY_BEARISH": {"available": True, "n": 200, "edge_vs_regime": -2.0},
        }
        result = _interpret_regime_split("rsi_overbought", cells)
        assert result["regime_dependent"] is True
        assert "flips sign" in result["conclusion"]


class TestRSIContext:
    def test_zones(self):
        from crypto_intel.engines.rsi_context import rsi_zone

        assert rsi_zone(85) == "EXTREME_OVERBOUGHT"
        assert rsi_zone(72) == "OVERBOUGHT"
        assert rsi_zone(50) == "NEUTRAL"
        assert rsi_zone(25) == "OVERSOLD"
        assert rsi_zone(15) == "EXTREME_OVERSOLD"

    def test_no_measurement_means_no_claim(self):
        from crypto_intel.engines.rsi_context import RSIContextEngine

        reading = RSIContextEngine().interpret(
            Asset.BTC, 75.0, "A_REGIME_THAT_HAS_NO_STUDY"
        )
        assert reading is not None
        assert "INCONCLUSIVE" in reading.measured_reading
        assert reading.confidence == "NONE"

    def test_middle_range_makes_no_directional_claim(self):
        from crypto_intel.engines.rsi_context import RSIContextEngine

        reading = RSIContextEngine().interpret(Asset.BTC, 52.0, "NEUTRAL")
        assert "no directional reading" in reading.measured_reading

    def test_none_rsi_returns_none(self):
        from crypto_intel.engines.rsi_context import RSIContextEngine

        assert RSIContextEngine().interpret(Asset.BTC, None, "BULLISH") is None


class TestFeatureImportance:
    def test_insufficient_data_features_never_top_the_ranking(self):
        """A -0.78 IC on 17 observations must not outrank a real result."""
        from crypto_intel.research.features import rank_features

        ic_results = {
            "features": {
                "sparse_feature": {
                    "7d": {"ic": -0.78, "p_value": 0.0002, "n": 17, "significant": True},
                },
                "solid_feature": {
                    "7d": {"ic": 0.08, "p_value": 0.0001, "n": 3000, "significant": True},
                },
            }
        }
        detail = {
            "sparse_feature": {"monotonicity_7d": {"monotonic": False}, "walk_forward_7d": {}},
            "solid_feature": {
                "monotonicity_7d": {"monotonic": True},
                "walk_forward_7d": {
                    "available": True,
                    "stability": {"stability_score": 65.0, "verdict": "WEAK"},
                },
            },
        }
        ranking = rank_features(ic_results, detail)
        assert ranking[0]["feature"] == "solid_feature"
        sparse = next(r for r in ranking if r["feature"] == "sparse_feature")
        assert sparse["verdict"] == "INSUFFICIENT_DATA"
        assert sparse["usefulness"] == 0.0

    def test_verdict_vocabulary_is_fixed(self):
        from crypto_intel.research.audit import VERDICTS

        assert set(VERDICTS) == {
            "USEFUL", "WEAK", "UNSTABLE", "NO_MEASURABLE_VALUE", "INSUFFICIENT_DATA",
        }

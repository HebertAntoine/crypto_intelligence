"""Anti look-ahead: the non-negotiable property of the historical engine.

If a feature vector at bar t could see bar t+1, every similarity result would
be worthless and quietly optimistic. These tests prove it cannot.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from crypto_intel.core.enums import Asset, Timeframe
from crypto_intel.engines.historical import FEATURE_NAMES, HistoricalSimilarityEngine


@pytest.fixture
def price_df() -> pd.DataFrame:
    rng = np.random.default_rng(7)
    n = 400
    close = 100 * np.cumprod(1 + rng.normal(0.0008, 0.02, n))
    return pd.DataFrame(
        {
            "open": close, "high": close * 1.012, "low": close * 0.988,
            "close": close, "volume": rng.uniform(800, 1600, n),
        },
        index=pd.date_range("2025-01-01", periods=n, freq="D", tz="UTC"),
    )


class TestNoLookAhead:
    def test_future_bars_do_not_change_past_features(self, price_df):
        """Mutate the last 60 bars; every earlier feature vector must be identical."""
        engine = HistoricalSimilarityEngine()
        original = engine.build_feature_matrix(price_df)

        mutated_df = price_df.copy()
        for col in ("close", "high", "low", "open"):
            mutated_df.iloc[-60:, mutated_df.columns.get_loc(col)] *= 4.0
        mutated = engine.build_feature_matrix(mutated_df)

        cutoff = len(price_df) - 61
        a = original.iloc[:cutoff].fillna(-999).to_numpy()
        b = mutated.iloc[:cutoff].fillna(-999).to_numpy()
        assert np.allclose(a, b), "Past feature vectors changed when future bars changed"

    def test_truncating_the_series_preserves_earlier_features(self, price_df):
        """Features at bar t must be identical whether or not later bars exist."""
        engine = HistoricalSimilarityEngine()
        full = engine.build_feature_matrix(price_df)
        truncated = engine.build_feature_matrix(price_df.iloc[:300])

        a = full.iloc[:300].fillna(-999).to_numpy()
        b = truncated.fillna(-999).to_numpy()
        assert np.allclose(a, b)

    def test_forward_returns_are_separate_from_features(self, price_df):
        """Forward returns must never appear among the similarity features."""
        engine = HistoricalSimilarityEngine()
        features = engine.build_feature_matrix(price_df)
        forward = engine.forward_returns(price_df, Timeframe.D1)
        assert not set(features.columns) & set(forward.columns)
        assert list(features.columns) == FEATURE_NAMES

    def test_forward_returns_look_forward_by_construction(self, price_df):
        """Sanity check that forward returns really are forward-looking - which
        is exactly why they must stay out of the feature matrix."""
        engine = HistoricalSimilarityEngine()
        forward = engine.forward_returns(price_df, Timeframe.D1)
        # The last bars cannot have a 30-day forward return yet.
        assert pd.isna(forward["30d"].iloc[-1])

    def test_recent_bars_excluded_from_matches(self, price_df):
        """Bars without a realised forward return must not be offered as analogues."""
        engine = HistoricalSimilarityEngine()
        result = engine.analyze(Asset.BTC, price_df, Timeframe.D1)
        assert result.available
        max_horizon = max(engine.horizons_days)
        for m in result.matches:
            assert m.index < len(price_df) - max_horizon + 1


class TestHistoricalOutput:
    def test_insufficient_history_is_unavailable(self):
        engine = HistoricalSimilarityEngine()
        small = pd.DataFrame(
            {"open": [1.0] * 50, "high": [1.0] * 50, "low": [1.0] * 50,
             "close": [1.0] * 50, "volume": [1.0] * 50},
            index=pd.date_range("2026-01-01", periods=50, freq="D", tz="UTC"),
        )
        result = engine.analyze(Asset.BTC, small, Timeframe.D1)
        assert result.available is False
        assert "UNAVAILABLE" in result.unavailable_reason

    def test_small_sample_is_flagged_not_hidden(self, price_df):
        engine = HistoricalSimilarityEngine()
        result = engine.analyze(Asset.BTC, price_df, Timeframe.D1)
        assert result.caveat
        assert "not predictive" in result.caveat or "descriptive" in result.caveat

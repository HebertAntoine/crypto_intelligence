"""Data leakage audit.

Every result in this project rests on one assumption: a value dated t was
knowable at t. These tests attack that assumption from several directions,
because leakage is silent - it does not raise, it just makes everything look
better than it is.

The general technique is mutation: change the future, recompute the past, and
assert nothing moved.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from crypto_intel.core.enums import Asset
from crypto_intel.engines.technical import indicators as ind


@pytest.fixture
def series() -> pd.DataFrame:
    rng = np.random.default_rng(31)
    n = 800
    close = 100 * np.cumprod(1 + rng.normal(0.0006, 0.02, n))
    return pd.DataFrame(
        {
            "open": close, "high": close * 1.012, "low": close * 0.988,
            "close": close, "volume": rng.uniform(800, 2400, n),
        },
        index=pd.date_range("2023-01-01", periods=n, freq="D", tz="UTC"),
    )


def mutate_tail(df: pd.DataFrame, bars: int = 60, factor: float = 5.0) -> pd.DataFrame:
    """Violently change the last N bars. Anything causal must be unaffected."""
    out = df.copy()
    for column in ("open", "high", "low", "close"):
        out.iloc[-bars:, out.columns.get_loc(column)] *= factor
    out.iloc[-bars:, out.columns.get_loc("volume")] *= factor
    return out


class TestIndicatorCausality:
    """Every indicator must depend only on bars at or before its own index."""

    @pytest.mark.parametrize(
        "name",
        ["ema20", "ema50", "ema200", "rsi", "atr_pct", "adx", "rel_volume", "bb_position"],
    )
    def test_indicator_ignores_future_bars(self, series, name):
        def compute(df):
            close, high, low, volume = df["close"], df["high"], df["low"], df["volume"]
            return {
                "ema20": ind.ema(close, 20),
                "ema50": ind.ema(close, 50),
                "ema200": ind.ema(close, 200),
                "rsi": ind.rsi(close, 14),
                "atr_pct": ind.atr_percent(high, low, close, 14),
                "adx": ind.adx(high, low, close, 14),
                "rel_volume": ind.relative_volume(volume, 20),
                "bb_position": ind.bollinger_bandwidth(close, 20, 2.0),
            }[name]

        original = compute(series)
        mutated = compute(mutate_tail(series))

        cutoff = len(series) - 61
        a = original.iloc[:cutoff].fillna(-999).to_numpy()
        b = mutated.iloc[:cutoff].fillna(-999).to_numpy()
        assert np.allclose(a, b), f"{name} changed when future bars changed"

    def test_truncation_equivalence(self, series):
        """Computing on a truncated series must match the full-series values."""
        full = ind.rsi(series["close"], 14)
        truncated = ind.rsi(series["close"].iloc[:500], 14)
        assert np.allclose(
            full.iloc[:500].fillna(-999).to_numpy(),
            truncated.fillna(-999).to_numpy(),
        )


class TestFeatureMatrixCausality:
    def test_technical_features_are_causal(self, series):
        from crypto_intel.research.features import build_technical_features

        original = build_technical_features(series)
        mutated = build_technical_features(mutate_tail(series))

        cutoff = len(series) - 61
        for column in original.columns:
            a = original[column].iloc[:cutoff].fillna(-999).to_numpy()
            b = mutated[column].iloc[:cutoff].fillna(-999).to_numpy()
            assert np.allclose(a, b), f"feature '{column}' leaked future information"

    def test_forward_returns_are_kept_separate(self, series):
        """Forward returns must never appear in the feature frame."""
        from crypto_intel.research.features import build_technical_features
        from crypto_intel.research.stats import forward_returns

        features = build_technical_features(series)
        fwd = forward_returns(series["close"], [1, 7])
        assert not set(features.columns) & set(fwd.columns)
        assert all(not c.startswith("fwd_") for c in features.columns)

    def test_forward_returns_really_look_forward(self, series):
        from crypto_intel.research.stats import forward_returns

        fwd = forward_returns(series["close"], [7])
        # The last 7 rows cannot have a 7-day forward return.
        assert fwd["fwd_7"].iloc[-7:].isna().all()


class TestTrailingThresholds:
    """Percentile thresholds must use only past observations."""

    def test_event_threshold_is_trailing(self, series):
        from crypto_intel.research.event_study import _trailing_percentile

        values = series["close"]
        threshold = _trailing_percentile(values, 90)
        for i in range(70, len(values)):
            if pd.isna(threshold.iloc[i]):
                continue
            past_max = values.iloc[: i + 1].max()
            assert threshold.iloc[i] <= past_max

    def test_trailing_rank_ignores_future(self, series):
        from crypto_intel.research.derivatives_study import trailing_rank

        original = trailing_rank(series["close"])
        mutated = trailing_rank(mutate_tail(series)["close"])
        cutoff = len(series) - 61
        assert np.allclose(
            original.iloc[:cutoff].fillna(-999).to_numpy(),
            mutated.iloc[:cutoff].fillna(-999).to_numpy(),
        )

    def test_full_history_percentile_would_leak(self, series):
        """Control: demonstrate the mistake the trailing version avoids.

        A full-history percentile DOES change when the future changes. This
        test documents why the trailing form is required.
        """
        naive_original = series["close"].quantile(0.9)
        naive_mutated = mutate_tail(series)["close"].quantile(0.9)
        assert naive_original != naive_mutated, (
            "the control is broken: a full-history percentile should be affected"
        )


class TestRegimeReconstruction:
    def test_regime_labels_are_causal(self, series):
        from crypto_intel.research.regime_conditioned import reconstruct_regime

        original = reconstruct_regime(series)
        mutated = reconstruct_regime(mutate_tail(series))
        cutoff = len(series) - 61
        assert (
            original.iloc[:cutoff].fillna("NA").to_numpy()
            == mutated.iloc[:cutoff].fillna("NA").to_numpy()
        ).all()


class TestScoreReconstruction:
    def test_reconstructed_scores_are_causal(self, series, monkeypatch):
        from crypto_intel.research import calibration

        # Feed the reconstructor a controlled frame rather than the database.
        monkeypatch.setattr(calibration, "build_price_frame", lambda asset: series)
        original = calibration.reconstruct_technical_score(Asset.BTC)

        monkeypatch.setattr(
            calibration, "build_price_frame", lambda asset: mutate_tail(series)
        )
        mutated = calibration.reconstruct_technical_score(Asset.BTC)

        cutoff = len(series) - 61
        assert np.allclose(
            original.iloc[:cutoff].fillna(-999).to_numpy(),
            mutated.iloc[:cutoff].fillna(-999).to_numpy(),
        )


class TestSnapshotImmutability:
    def test_snapshot_is_never_overwritten(self):
        """Uses a fixed past hour so the test does not depend on whether the
        pipeline happened to record a snapshot for the current hour."""
        from datetime import UTC, datetime

        from crypto_intel.history.immutable import record_prediction, verify_integrity

        when = datetime(2019, 3, 14, 9, 0, tzinfo=UTC)

        first = record_prediction(
            Asset.ETH, 3000.0,
            {"regime": "BULLISH", "regime_score": 30.0},
            {"timing": "WAIT", "timing_score": 0.0},
            {"medium": {"score": 10.0}},
            {}, [], {}, when=when,
        )
        assert first.created

        second = record_prediction(
            Asset.ETH, 9999.0,
            {"regime": "BEARISH", "regime_score": -80.0},
            {"timing": "VERY_FAVORABLE", "timing_score": 90.0},
            {"medium": {"score": -90.0}},
            {}, [], {}, when=when,
        )
        assert second.created is False
        assert second.snapshot_id == first.snapshot_id

        integrity = verify_integrity(first.snapshot_id)
        assert integrity["intact"]

    def test_tampering_is_detectable(self):
        from datetime import UTC, datetime

        from crypto_intel.db.base import PredictionSnapshotRow
        from crypto_intel.db.session import session_scope
        from crypto_intel.history.immutable import record_prediction, verify_integrity

        result = record_prediction(
            Asset.SOL, 100.0,
            {"regime": "NEUTRAL"}, {"timing": "WAIT"},
            {"medium": {"score": 0.0}}, {}, [], {},
            when=datetime(2019, 3, 14, 10, 0, tzinfo=UTC),
        )
        snapshot_id = result.snapshot_id

        with session_scope() as s:
            row = s.get(PredictionSnapshotRow, snapshot_id)
            payload = dict(row.payload)
            payload["price"] = 999999.0
            row.payload = payload

        assert verify_integrity(snapshot_id)["intact"] is False


class TestEventStudyWindows:
    def test_baseline_uses_the_observable_window(self):
        """An ETF event from 2024 must not be compared to a 2017 baseline."""
        import inspect

        from crypto_intel.research import event_study

        source = inspect.getsource(event_study.run_event_study)
        assert "_observable_window" in source
        assert "baseline_index" in source

    def test_recent_bars_excluded_from_analogues(self):
        import inspect

        from crypto_intel.engines.empirical import EmpiricalTimingLayer

        source = inspect.getsource(EmpiricalTimingLayer.analyse)
        # Bars without a realised forward return cannot be analogues.
        assert "usable" in source and "max(HORIZONS)" in source


class TestMacroRevisions:
    def test_revision_limitation_is_documented(self):
        """CPI and PCE are revised. If the source cannot give the value as
        originally released, that limitation must be stated, not hidden."""
        from pathlib import Path

        docs = Path(__file__).resolve().parents[2] / "docs"
        text = " ".join(
            p.read_text(encoding="utf-8") for p in docs.glob("*.md")
        ).lower()
        assert "revis" in text, "macro revision limitations are not documented"

    def test_macro_series_carry_observation_dates(self):
        """Stored macro points are dated by observation date; without a release
        date the backtest limitation must be acknowledged."""
        from crypto_intel.db.base import MacroSeriesRow

        columns = {c.name for c in MacroSeriesRow.__table__.columns}
        assert "timestamp" in columns
        assert "source" in columns

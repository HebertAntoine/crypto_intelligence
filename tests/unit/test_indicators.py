"""Indicator correctness, checked against reference values rather than
against our own output - a self-consistent bug is still a bug."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from crypto_intel.engines.technical import indicators as ind


class TestRSI:
    def test_matches_wilder_reference(self, wilder_closes):
        """First RSI value on Wilder's own dataset is 70.46."""
        result = ind.rsi(pd.Series(wilder_closes), 14).dropna()
        assert not result.empty
        assert result.iloc[0] == pytest.approx(70.46, abs=0.02)
        assert result.iloc[1] == pytest.approx(66.25, abs=0.05)

    def test_bounded_0_100(self, trending_up_df):
        r = ind.rsi(trending_up_df["close"], 14).dropna()
        assert r.min() >= 0.0
        assert r.max() <= 100.0

    def test_warmup_is_nan_not_filled(self, wilder_closes):
        """NaN means 'not computable yet'. Filling it would fabricate a fact."""
        r = ind.rsi(pd.Series(wilder_closes), 14)
        assert r.iloc[:14].isna().all()

    def test_all_gains_gives_100(self):
        s = pd.Series([float(i) for i in range(1, 40)])
        assert ind.rsi(s, 14).dropna().iloc[-1] == pytest.approx(100.0)

    def test_all_losses_gives_0(self):
        s = pd.Series([float(i) for i in range(40, 1, -1)])
        assert ind.rsi(s, 14).dropna().iloc[-1] == pytest.approx(0.0)

    def test_rejects_bad_period(self):
        with pytest.raises(ValueError):
            ind.rsi(pd.Series([1.0, 2.0]), 0)


class TestMovingAverages:
    def test_sma_is_arithmetic_mean(self):
        s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        assert ind.sma(s, 3).iloc[-1] == pytest.approx(4.0)

    def test_ema_warmup_length(self):
        s = pd.Series(range(50), dtype=float)
        assert int(ind.ema(s, 20).isna().sum()) == 19

    def test_ema_reacts_faster_than_sma(self):
        """Just after a step change the EMA must lead the SMA.

        Measured 3 bars in, not 10: once the whole window has moved the SMA
        has fully converged and the comparison stops being meaningful.
        """
        s = pd.Series([10.0] * 30 + [20.0] * 3)
        assert ind.ema(s, 10).iloc[-1] > ind.sma(s, 10).iloc[-1]


class TestMACD:
    def test_histogram_is_macd_minus_signal(self, trending_up_df):
        macd, signal, hist = ind.macd(trending_up_df["close"])
        valid = hist.dropna().index
        assert np.allclose(
            (macd - signal).loc[valid].to_numpy(), hist.loc[valid].to_numpy(), equal_nan=True
        )

    def test_positive_in_uptrend(self, trending_up_df):
        macd, _, _ = ind.macd(trending_up_df["close"])
        assert macd.dropna().iloc[-1] > 0

    def test_rejects_fast_slower_than_slow(self):
        with pytest.raises(ValueError):
            ind.macd(pd.Series([1.0] * 50), fast=26, slow=12)


class TestVolatility:
    def test_bollinger_ordering(self, trending_up_df):
        upper, middle, lower = ind.bollinger_bands(trending_up_df["close"], 20, 2.0)
        valid = middle.dropna().index
        assert (upper.loc[valid] >= middle.loc[valid]).all()
        assert (middle.loc[valid] >= lower.loc[valid]).all()

    def test_atr_positive(self, trending_up_df):
        atr = ind.atr(trending_up_df["high"], trending_up_df["low"], trending_up_df["close"], 14)
        assert (atr.dropna() > 0).all()

    def test_true_range_covers_gaps(self):
        """A gap must widen the true range beyond the bar's own high-low."""
        high = pd.Series([10.0, 20.0])
        low = pd.Series([9.0, 19.0])
        close = pd.Series([9.5, 19.5])
        tr = ind.true_range(high, low, close)
        assert tr.iloc[1] == pytest.approx(10.5)   # 20 - 9.5, not 20 - 19


class TestVolume:
    def test_relative_volume_is_one_when_flat(self):
        v = pd.Series([100.0] * 40)
        assert ind.relative_volume(v, 20).dropna().iloc[-1] == pytest.approx(1.0)

    def test_relative_volume_detects_spike(self):
        v = pd.Series([100.0] * 39 + [300.0])
        assert ind.relative_volume(v, 20).iloc[-1] > 2.0


class TestMissingData:
    def test_percent_change_returns_none_not_zero(self):
        """The distinction that matters: 'no change' vs 'cannot know'."""
        assert ind.percent_change(pd.Series([1.0, 2.0]), 10) is None

    def test_percent_change_computes_when_possible(self):
        assert ind.percent_change(pd.Series([100.0, 110.0]), 1) == pytest.approx(10.0)

    def test_last_valid_on_empty(self):
        assert ind.last_valid(pd.Series([], dtype=float)) is None

    def test_last_valid_skips_trailing_nan(self):
        assert ind.last_valid(pd.Series([1.0, 2.0, np.nan])) == pytest.approx(2.0)

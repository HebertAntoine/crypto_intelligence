"""Windowing and downsampling must never invent a price.

The failure mode this guards against is subtle: a chart that samples every Nth
candle looks fine and shows highs and lows that never occurred, because the
extremes live in the discarded bars. Aggregation preserves them. Each test below
pins one property of that aggregation.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from crypto_intel.core.enums import Timeframe
from crypto_intel.engines.technical.window import (
    MAX_DISPLAY_BARS,
    bars_for,
    build_window,
    downsample_ohlcv,
    downsample_series,
    period_days,
    slice_period,
    slice_with_warmup,
)


def _frame(n: int, freq: str = "D") -> pd.DataFrame:
    index = pd.date_range("2020-01-01", periods=n, freq=freq, tz="UTC")
    rng = np.random.default_rng(7)
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    return pd.DataFrame(
        {
            "open": close - 0.5,
            "high": close + rng.uniform(0.5, 3.0, n),
            "low": close - rng.uniform(0.5, 3.0, n),
            "close": close,
            "volume": rng.uniform(100, 1000, n),
        },
        index=index,
    )


# --- period arithmetic -----------------------------------------------------

def test_unknown_period_is_rejected_with_the_known_list():
    with pytest.raises(ValueError, match="Known periods"):
        period_days("6m")


def test_max_period_means_everything_stored():
    assert period_days("max") is None
    assert bars_for("max", Timeframe.D1) is None


def test_bars_for_scales_with_the_timeframe():
    assert bars_for("30d", Timeframe.D1) == 30
    assert bars_for("30d", Timeframe.H4) == 180
    assert bars_for("30d", Timeframe.M15) == 2880


# --- slicing ---------------------------------------------------------------

def test_period_is_measured_from_the_last_candle_not_the_clock():
    """Collection stopping three days ago must not shrink a 30-day window."""
    df = _frame(400)  # ends in 2021, long past
    window, truncated = slice_period(df, "30d", Timeframe.D1)

    assert len(window) == 31          # 30 days inclusive of both ends
    assert window.index[-1] == df.index[-1]
    assert not truncated


def test_requesting_more_history_than_stored_is_flagged():
    df = _frame(40)
    window, truncated = slice_period(df, "1y", Timeframe.D1)

    assert truncated
    assert len(window) == len(df)


def test_max_returns_everything_and_is_never_truncated():
    df = _frame(400)
    window, truncated = slice_period(df, "max", Timeframe.D1)

    assert len(window) == 400
    assert not truncated


# --- aggregation -----------------------------------------------------------

def test_downsampling_preserves_the_extremes():
    """The whole point: a 3:1 chart must show the same high and low as 1:1."""
    df = _frame(300)
    out = downsample_ohlcv(df, 3)

    assert out["high"].max() == df["high"].max()
    assert out["low"].min() == df["low"].min()


def test_downsampling_preserves_total_volume():
    df = _frame(300)
    out = downsample_ohlcv(df, 4)

    assert out["volume"].sum() == pytest.approx(df["volume"].sum())


def test_last_aggregated_bar_is_the_current_one():
    """Grouping forward would leave a partial group and misreport today's bar."""
    df = _frame(100)
    out = downsample_ohlcv(df, 7)

    assert out.index[-1] == df.index[-1]
    assert out["close"].iloc[-1] == df["close"].iloc[-1]


def test_aggregated_bar_is_stamped_with_its_closing_time():
    """A group stamped with its opening time shifts the whole chart left."""
    df = _frame(10, freq="h")
    out = downsample_ohlcv(df, 3)

    # Groups run backwards from the end: [0], [1,2,3], [4,5,6], [7,8,9].
    assert list(out.index) == [df.index[0], df.index[3], df.index[6], df.index[9]]
    assert out["close"].iloc[1] == df["close"].iloc[3]


def test_aggregated_open_comes_from_the_first_bar_of_its_group():
    df = _frame(10, freq="h")
    out = downsample_ohlcv(df, 3)

    assert out["open"].iloc[1] == df["open"].iloc[1]
    assert out["open"].iloc[-1] == df["open"].iloc[7]


def test_factor_of_one_is_a_passthrough():
    df = _frame(50)
    assert downsample_ohlcv(df, 1).equals(df)


def test_empty_frame_survives_downsampling():
    empty = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    assert downsample_ohlcv(empty, 4).empty


# --- indicators carried through --------------------------------------------

def test_indicator_is_carried_at_each_group_closing_bar():
    """An EMA drawn over aggregated candles must be the real EMA at that bar."""
    df = _frame(10, freq="h")
    carried = downsample_series(df["close"], df, 3)

    assert carried == [
        df["close"].iloc[0], df["close"].iloc[3],
        df["close"].iloc[6], df["close"].iloc[9],
    ]


def test_indicator_length_always_matches_the_candles():
    """A mismatch here silently shifts every overlay against the price."""
    df = _frame(1000)
    for factor in (1, 2, 3, 7, 13):
        candles = downsample_ohlcv(df, factor)
        carried = downsample_series(df["close"], df, factor)
        assert len(carried) == len(candles), f"factor {factor} desynchronised"


# --- warm-up ---------------------------------------------------------------

def test_warmup_prepends_history_so_long_indicators_have_values():
    df = _frame(600)
    warm, warm_bars = slice_with_warmup(df, "30d", Timeframe.D1)

    assert warm_bars > 0
    assert len(warm) == warm_bars + 31
    assert warm.index[-1] == df.index[-1]


def test_warmup_is_capped_by_available_history():
    """Asking for 260 bars of warm-up when 10 exist must not fail."""
    df = _frame(40)
    warm, warm_bars = slice_with_warmup(df, "7d", Timeframe.D1)

    assert warm_bars <= 40 - 8
    assert len(warm) == len(df)


def test_warmup_is_zero_when_the_window_is_everything():
    df = _frame(100)
    _, warm_bars = slice_with_warmup(df, "max", Timeframe.D1)

    assert warm_bars == 0


# --- the assembled window --------------------------------------------------

def test_window_stays_under_the_display_ceiling():
    df = _frame(20000, freq="15min")
    win = build_window(df, "max", Timeframe.M15)

    assert win.displayed_bars <= MAX_DISPLAY_BARS
    assert win.downsampled
    assert win.source_bars == 20000


def test_small_window_is_not_downsampled():
    df = _frame(400)
    win = build_window(df, "30d", Timeframe.D1)

    assert win.downsample_factor == 1
    assert not win.downsampled
    assert win.displayed_bars == 31


def test_summary_reports_real_period_extremes():
    df = _frame(400)
    win = build_window(df, "30d", Timeframe.D1)
    summary = win.summary()

    window, _ = slice_period(df, "30d", Timeframe.D1)
    assert summary["period_high"] == pytest.approx(window["high"].max())
    assert summary["period_low"] == pytest.approx(window["low"].min())
    assert summary["last_price"] == pytest.approx(window["close"].iloc[-1])


def test_summary_states_when_bars_were_aggregated():
    """A user must never be shown aggregated bars without being told."""
    df = _frame(20000, freq="15min")
    summary = build_window(df, "max", Timeframe.M15).summary()

    assert summary["downsampled"] is True
    assert summary["downsample_factor"] > 1
    assert "aggregate" in summary["note"]
    assert summary["effective_interval_minutes"] > Timeframe.M15.minutes


def test_empty_history_yields_an_unavailable_summary():
    empty = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    win = build_window(empty, "30d", Timeframe.D1)

    assert win.summary() == {"available": False}
    assert win.displayed_bars == 0

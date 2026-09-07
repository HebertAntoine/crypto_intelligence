"""Choosing which candles to draw, and how many.

The chart offers a display period (7 days to everything stored) on top of a
timeframe. The two multiply badly: a year of 15-minute candles is 35 000 bars,
which no browser draws usefully and no analyst reads. So a window is selected,
and beyond a ceiling the series is aggregated rather than truncated.

Two rules keep this honest.

**Aggregate, never sample.** Dropping every other candle produces a chart whose
highs and lows never happened - the extremes land in the discarded bars. Each
output bar here is a real OHLCV aggregate of the bars it replaces: first open,
max high, min low, last close, summed volume. Every price shown is a price the
market actually printed.

**Indicators are computed before aggregation, never after.** An EMA200 over
downsampled bars is a different quantity from an EMA200 over the real ones, and
it would silently disagree with the analysis. The caller computes indicators on
the full series and passes them through `downsample_series`, which carries the
value matching each group's closing bar.

The period is measured back from the last stored candle rather than from the
wall clock, so "3 months" means three months of data rather than three months
of calendar during which collection may have stopped.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import pandas as pd

from ...core.enums import Timeframe

#: Display periods offered by the UI, in days. `None` means everything stored.
PERIOD_DAYS: dict[str, int | None] = {
    "7d": 7,
    "30d": 30,
    "3m": 90,
    "1y": 365,
    "max": None,
}

#: Most candles worth sending to a browser. Above this the series is
#: aggregated. Chosen so a 1920px chart still has more bars than pixels-per-bar
#: would resolve, which is the point where more data stops adding information.
MAX_DISPLAY_BARS = 1500


def period_days(period: str) -> int | None:
    """Days covered by a named period, or None for everything available."""
    if period not in PERIOD_DAYS:
        known = ", ".join(PERIOD_DAYS)
        raise ValueError(f"unknown period '{period}'. Known periods: {known}")
    return PERIOD_DAYS[period]


def bars_for(period: str, timeframe: Timeframe) -> int | None:
    """How many bars that period spans on this timeframe."""
    days = period_days(period)
    if days is None:
        return None
    minutes = days * 24 * 60
    return max(1, minutes // timeframe.minutes)


@dataclass(slots=True)
class ChartWindow:
    """The candles to draw, and an honest description of what was done to them."""

    candles: pd.DataFrame
    period: str
    timeframe: Timeframe
    source_bars: int          # bars in the window before any aggregation
    displayed_bars: int
    downsample_factor: int    # 1 when the real bars are shown
    truncated: bool           # the period asked for more history than we hold

    @property
    def downsampled(self) -> bool:
        return self.downsample_factor > 1

    @property
    def effective_timeframe_minutes(self) -> int:
        return self.timeframe.minutes * self.downsample_factor

    def note(self) -> str:
        if self.candles.empty:
            return "no candles stored for this asset and timeframe"
        parts = [f"{self.displayed_bars} bars"]
        if self.downsampled:
            parts.append(
                f"aggregated {self.downsample_factor}:1 from {self.source_bars} real "
                f"{self.timeframe.value} candles - each bar is a true OHLC aggregate, "
                "not a sample"
            )
        if self.truncated:
            parts.append("the period requested exceeds the stored history")
        return "; ".join(parts)

    def summary(self) -> dict[str, Any]:
        """Headline figures for the period - what the UI shows above the chart."""
        if self.candles.empty:
            return {"available": False}
        closes = self.candles["close"]
        first, last = float(closes.iloc[0]), float(closes.iloc[-1])
        return {
            "available": True,
            "last_price": last,
            "first_price": first,
            "change_pct": ((last - first) / first * 100.0) if first else None,
            "period_high": float(self.candles["high"].max()),
            "period_low": float(self.candles["low"].min()),
            "high_time": self.candles["high"].idxmax().isoformat(),
            "low_time": self.candles["low"].idxmin().isoformat(),
            "first_time": self.candles.index[0].isoformat(),
            "last_time": self.candles.index[-1].isoformat(),
            "bars": self.displayed_bars,
            "truncated": self.truncated,
            "downsampled": self.downsampled,
            "downsample_factor": self.downsample_factor,
            "effective_interval_minutes": self.effective_timeframe_minutes,
            "note": self.note(),
        }


def slice_period(
    df: pd.DataFrame, period: str, timeframe: Timeframe
) -> tuple[pd.DataFrame, bool]:
    """Keep the last `period` of candles. Returns the slice and whether it fell short.

    Measured back from the newest stored candle: if collection stopped three days
    ago, "7 days" still yields seven days of candles rather than four.
    """
    days = period_days(period)
    if df.empty or days is None:
        return df, False

    end = df.index[-1]
    start = end - timedelta(days=days)
    window = df.loc[df.index >= start]
    # Falling short means the store begins after the requested start, not that
    # the window happens to hold fewer bars than a perfect market would print.
    truncated = df.index[0] > start
    return window, truncated


#: Bars of history prepended to a window before indicators are computed, so a
#: 200-period EMA is drawn from the first bar of a 7-day view instead of being
#: blank. Slightly above the longest period any overlay uses.
INDICATOR_WARMUP_BARS = 260


def slice_with_warmup(
    df: pd.DataFrame, period: str, timeframe: Timeframe, warmup: int = INDICATOR_WARMUP_BARS
) -> tuple[pd.DataFrame, int]:
    """The window plus preceding bars, and how many of those are warm-up.

    Without this, an EMA200 over a 30-day daily view has no value at all: the
    indicator needs 200 bars and the window holds 30. Computing over the longer
    slice and then discarding the warm-up gives the real indicator value on the
    first drawn bar, which is what any charting tool does.
    """
    window, _ = slice_period(df, period, timeframe)
    if window.empty or len(window) == len(df):
        return window, 0

    start_position = df.index.get_loc(window.index[0])
    if not isinstance(start_position, int):
        return window, 0
    warm_start = max(0, start_position - warmup)
    return df.iloc[warm_start:], start_position - warm_start


def _group_positions(length: int, factor: int) -> Any:
    """Group label per bar, counted back from the newest so the last group is full."""
    offset = (length - 1) % factor
    return ((pd.RangeIndex(length) + (factor - 1 - offset)) // factor).to_numpy()


def _group_last_positions(groups: Any) -> Any:
    """Position of the closing bar of each group, in order."""
    return pd.Series(range(len(groups))).groupby(groups).max().to_numpy()


def downsample_ohlcv(df: pd.DataFrame, factor: int) -> pd.DataFrame:
    """Aggregate every `factor` consecutive bars into one real OHLCV bar.

    Grouping runs from the most recent bar backwards, so the last bar of the
    output is always the current one. Aggregating forward would leave a partial
    group at the end and make the newest bar silently wrong.
    """
    if factor <= 1 or df.empty:
        return df

    # Grouped from the end, so the final group is complete and any remainder
    # lands at the far left where it is oldest and least consequential.
    groups = _group_positions(len(df), factor)

    aggregated = df.groupby(groups).agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    )
    # The timestamp of a group is that of its closing bar, matching `close`.
    # `.max()` over positions, not `idxmax()` over the group labels: every label
    # in a group is identical, so idxmax would return the group's FIRST bar and
    # stamp each aggregate with its opening time.
    aggregated.index = df.index[_group_last_positions(groups)]
    aggregated.index.name = df.index.name
    return aggregated


def downsample_series(values: pd.Series | list, df: pd.DataFrame, factor: int) -> list:
    """Carry an indicator through the same grouping as the candles.

    The value kept for each group is the one on its closing bar, so an EMA drawn
    over aggregated candles is the real EMA at that moment rather than an
    average of averages.
    """
    series = values if isinstance(values, pd.Series) else pd.Series(values, index=df.index)
    if factor <= 1 or df.empty:
        return list(series)

    groups = _group_positions(len(df), factor)
    return [series.iloc[int(p)] for p in _group_last_positions(groups)]


def build_window(
    df: pd.DataFrame,
    period: str,
    timeframe: Timeframe,
    max_bars: int = MAX_DISPLAY_BARS,
) -> ChartWindow:
    """Select the period and aggregate it down to a drawable number of bars."""
    window, truncated = slice_period(df, period, timeframe)
    source_bars = len(window)

    factor = 1
    if source_bars > max_bars:
        # Ceiling division: the smallest factor that fits under the cap.
        factor = -(-source_bars // max_bars)

    candles = downsample_ohlcv(window, factor)
    return ChartWindow(
        candles=candles,
        period=period,
        timeframe=timeframe,
        source_bars=source_bars,
        displayed_bars=len(candles),
        downsample_factor=factor,
        truncated=truncated,
    )

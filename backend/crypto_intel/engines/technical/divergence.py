"""RSI and MACD divergences.

A divergence needs two confirmed pivots that disagree between price and the
oscillator. Requiring a minimum price move and a minimum pivot separation
filters out the noise that makes naive detectors report a divergence on almost
every chart.
"""

from __future__ import annotations

import pandas as pd

from ...core.enums import Timeframe
from ...core.models import Divergence
from .structure import SwingPoint, find_swings


def _indicator_at(indicator: pd.Series, index: int) -> float | None:
    if index < 0 or index >= len(indicator):
        return None
    val = indicator.iloc[index]
    return None if pd.isna(val) else float(val)


def detect_divergences(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    indicator: pd.Series,
    timeframe: Timeframe,
    indicator_name: str = "RSI",
    *,
    lookback_bars: int = 60,
    swing_lookback: int = 5,
    min_pivot_distance: int = 5,
    min_price_move_pct: float = 1.0,
) -> list[Divergence]:
    """Find regular and hidden divergences in the recent window.

    Regular bearish : price higher high, indicator lower high  -> exhaustion up
    Regular bullish : price lower low,  indicator higher low   -> exhaustion down
    Hidden bearish  : price lower high, indicator higher high  -> trend continuation down
    Hidden bullish  : price higher low, indicator lower low    -> trend continuation up
    """
    out: list[Divergence] = []
    if len(close) < swing_lookback * 2 + min_pivot_distance:
        return out

    start = max(0, len(close) - lookback_bars)
    highs, lows = find_swings(high, low, lookback=swing_lookback)
    highs = [s for s in highs if s.index >= start]
    lows = [s for s in lows if s.index >= start]

    out.extend(
        _scan(highs, indicator, timeframe, indicator_name, "high",
              min_pivot_distance, min_price_move_pct)
    )
    out.extend(
        _scan(lows, indicator, timeframe, indicator_name, "low",
              min_pivot_distance, min_price_move_pct)
    )
    # Strongest first: the report should lead with the clearest signal.
    out.sort(key=lambda d: d.strength, reverse=True)
    return out[:4]


def _scan(
    swings: list[SwingPoint],
    indicator: pd.Series,
    timeframe: Timeframe,
    indicator_name: str,
    pivot_kind: str,
    min_pivot_distance: int,
    min_price_move_pct: float,
) -> list[Divergence]:
    found: list[Divergence] = []
    if len(swings) < 2:
        return found

    # Compare the last pivot with each earlier one, most recent pairing first.
    last = swings[-1]
    ind_last = _indicator_at(indicator, last.index)
    if ind_last is None:
        return found

    for prev in reversed(swings[:-1]):
        if last.index - prev.index < min_pivot_distance:
            continue
        ind_prev = _indicator_at(indicator, prev.index)
        if ind_prev is None:
            continue

        price_move_pct = abs(last.price - prev.price) / prev.price * 100.0
        if price_move_pct < min_price_move_pct:
            continue

        kind: str | None = None
        if pivot_kind == "high":
            if last.price > prev.price and ind_last < ind_prev:
                kind = "bearish"
            elif last.price < prev.price and ind_last > ind_prev:
                kind = "hidden_bearish"
        else:
            if last.price < prev.price and ind_last > ind_prev:
                kind = "bullish"
            elif last.price > prev.price and ind_last < ind_prev:
                kind = "hidden_bullish"

        if kind is None:
            continue

        indicator_gap = abs(ind_last - ind_prev)
        # Strength blends how far price moved with how hard the oscillator disagreed.
        strength = min(100.0, price_move_pct * 8.0 + indicator_gap * 2.5)
        if strength < 20.0:
            continue

        found.append(
            Divergence(
                indicator=indicator_name,
                kind=kind,
                timeframe=timeframe,
                strength=round(strength, 1),
                price_points=[round(prev.price, 8), round(last.price, 8)],
                indicator_points=[round(ind_prev, 4), round(ind_last, 4)],
                start_time=prev.timestamp.to_pydatetime() if prev.timestamp is not None else None,
                end_time=last.timestamp.to_pydatetime() if last.timestamp is not None else None,
            )
        )
        break   # one divergence per pivot type is enough; the rest is noise

    return found

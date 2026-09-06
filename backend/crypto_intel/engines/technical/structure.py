"""Market structure: swing points, HH/HL/LH/LL, trend regime.

Structure is computed from confirmed pivots only. A pivot needs `lookback`
bars on BOTH sides to be validated, which means the most recent bars are
deliberately excluded - a high cannot be known to be a swing high until price
has moved away from it. That lag is real information, not a bug to remove.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise

import numpy as np
import pandas as pd

from ...core.enums import MarketStructure, TrendDirection
from ...core.models import TrendState


@dataclass(slots=True)
class SwingPoint:
    index: int
    price: float
    kind: str          # "high" | "low"
    timestamp: pd.Timestamp | None = None


def find_swings(
    high: pd.Series, low: pd.Series, lookback: int = 5
) -> tuple[list[SwingPoint], list[SwingPoint]]:
    """Confirmed swing highs and lows.

    A swing high at i requires high[i] to be the maximum of
    [i-lookback, i+lookback]. Bars within `lookback` of the end cannot be
    confirmed and are excluded.
    """
    highs: list[SwingPoint] = []
    lows: list[SwingPoint] = []
    n = len(high)
    if n < 2 * lookback + 1:
        return highs, lows

    h = high.to_numpy(dtype=float)
    lo = low.to_numpy(dtype=float)
    idx = high.index

    for i in range(lookback, n - lookback):
        window_h = h[i - lookback : i + lookback + 1]
        # Strict on the left avoids logging a flat plateau repeatedly.
        if (
            h[i] == window_h.max()
            and not np.isnan(h[i])
            and (h[i] > h[i - lookback : i].max() or i == lookback)
        ):
            highs.append(SwingPoint(index=i, price=float(h[i]), kind="high",
                                    timestamp=idx[i] if hasattr(idx, "__getitem__") else None))
        window_l = lo[i - lookback : i + lookback + 1]
        if (
            lo[i] == window_l.min()
            and not np.isnan(lo[i])
            and (lo[i] < lo[i - lookback : i].min() or i == lookback)
        ):
            lows.append(SwingPoint(index=i, price=float(lo[i]), kind="low",
                                   timestamp=idx[i] if hasattr(idx, "__getitem__") else None))
    return highs, lows


def classify_structure(
    highs: list[SwingPoint], lows: list[SwingPoint], min_swings: int = 4
) -> tuple[MarketStructure, list[str]]:
    """Label the last swings as HH/HL/LH/LL and derive the structure.

    Returns UNDETERMINED when there are not enough confirmed swings - saying
    "we cannot tell" beats inventing a trend from two points.
    """
    labels: list[str] = []
    if len(highs) + len(lows) < min_swings or len(highs) < 2 or len(lows) < 2:
        return MarketStructure.UNDETERMINED, labels

    recent_highs = highs[-3:]
    recent_lows = lows[-3:]

    for prev, cur in pairwise(recent_highs):
        labels.append("HH" if cur.price > prev.price else "LH")
    for prev, cur in pairwise(recent_lows):
        labels.append("HL" if cur.price > prev.price else "LL")

    bullish = labels.count("HH") + labels.count("HL")
    bearish = labels.count("LH") + labels.count("LL")

    if bullish >= 2 and bearish == 0:
        return MarketStructure.HH_HL, labels
    if bearish >= 2 and bullish == 0:
        return MarketStructure.LH_LL, labels
    if bullish and bearish:
        return MarketStructure.MIXED, labels
    return MarketStructure.RANGE, labels


def determine_trend(
    close: pd.Series,
    ema20: pd.Series,
    ema50: pd.Series,
    ema200: pd.Series,
    adx_series: pd.Series | None = None,
    *,
    ema_separation_min_pct: float = 0.35,
    adx_trending: float = 25.0,
) -> TrendState:
    """Combine EMA alignment with ADX to separate trend from drifting range.

    EMA alignment alone is not enough: in a range the EMAs stay technically
    ordered while price goes nowhere. Requiring both separation and ADX keeps
    the engine from labelling chop as a trend.
    """
    price = _last(close)
    e20, e50, e200 = _last(ema20), _last(ema50), _last(ema200)
    if price is None or e20 is None or e50 is None:
        return TrendState(direction=TrendDirection.UNDETERMINED, strength=0.0,
                          reason="insufficient history for EMA20/EMA50")

    separation_pct = abs(e20 - e50) / price * 100.0 if price else 0.0
    adx_val = _last(adx_series) if adx_series is not None else None
    trending = adx_val is None or adx_val >= adx_trending

    bull_stack = e20 > e50 and price > e20
    bear_stack = e20 < e50 and price < e20
    if e200 is not None:
        bull_stack = bull_stack and price > e200 * 0.97
        bear_stack = bear_stack and price < e200 * 1.03

    if separation_pct < ema_separation_min_pct or not trending:
        reasons = []
        if separation_pct < ema_separation_min_pct:
            reasons.append(f"EMA20/EMA50 separation {separation_pct:.2f}% below {ema_separation_min_pct}%")
        if adx_val is not None and adx_val < adx_trending:
            reasons.append(f"ADX {adx_val:.1f} below trending threshold {adx_trending}")
        return TrendState(direction=TrendDirection.RANGE,
                          strength=min(40.0, separation_pct * 30.0),
                          reason="; ".join(reasons) or "EMAs entangled")

    strength = min(100.0, separation_pct * 18.0 + (adx_val or 20.0))
    if bull_stack:
        return TrendState(direction=TrendDirection.UPTREND, strength=strength,
                          reason=f"price>EMA20>EMA50, separation {separation_pct:.2f}%"
                                 + (f", ADX {adx_val:.1f}" if adx_val is not None else ""))
    if bear_stack:
        return TrendState(direction=TrendDirection.DOWNTREND, strength=strength,
                          reason=f"price<EMA20<EMA50, separation {separation_pct:.2f}%"
                                 + (f", ADX {adx_val:.1f}" if adx_val is not None else ""))
    return TrendState(direction=TrendDirection.RANGE, strength=25.0,
                      reason="EMAs ordered but price not aligned with them")


def _last(series: pd.Series | None) -> float | None:
    if series is None or len(series) == 0:
        return None
    s = series.dropna()
    return float(s.iloc[-1]) if not s.empty else None

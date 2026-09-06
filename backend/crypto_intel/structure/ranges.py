"""Range detection: the structure most traders actually trade.

A range is not "price went sideways". It is a pair of zones that price has
repeatedly respected, with a measurable width, duration and internal
behaviour. Detecting it properly means the difference between "BTC is
consolidating" and "BTC is in a 163.2-185.7 range that has held 4 times at the
bottom and 3 at the top for 41 days".

Widths are normalised by ATR so a "tight" range means the same thing on BTC
and SOL. Nothing here uses a fixed percentage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

import numpy as np
import pandas as pd

from ..core.enums import Asset, Timeframe
from ..engines.technical import indicators as ind
from ..history import store
from ..logging_setup import get_logger
from .swings import SwingSeries, find_causal_swings
from .zones import Zone, build_zones

log = get_logger("structure.ranges")

MIN_BARS_FOR_RANGE = 25
MIN_TOUCHES_PER_SIDE = 2
# Two zones closer than this are one level described twice, not a range.
MIN_RANGE_WIDTH_ATR = 2.0
# A range price left this long ago is history, not current structure.
MAX_BARS_OUTSIDE = 10


def _count_touch_events(mask: pd.Series) -> int:
    """Number of times the series ENTERS the zone, not bars spent in it."""
    if mask.empty:
        return 0
    entries = mask & ~mask.shift(1, fill_value=False)
    return int(entries.sum())


def _trailing_run(mask: pd.Series) -> int:
    """Length of the run of True values at the end of the series."""
    if mask.empty or not bool(mask.iloc[-1]):
        return 0
    reversed_values = mask.to_numpy()[::-1]
    count = 0
    for value in reversed_values:
        if not value:
            break
        count += 1
    return count


class RangeType(StrEnum):
    HORIZONTAL_RANGE = "HORIZONTAL_RANGE"
    TIGHT_RANGE = "TIGHT_RANGE"
    BROAD_RANGE = "BROAD_RANGE"
    RANGE_COMPRESSION = "RANGE_COMPRESSION"
    RANGE_EXPANSION = "RANGE_EXPANSION"
    ASCENDING_STRUCTURE = "ASCENDING_STRUCTURE"
    DESCENDING_STRUCTURE = "DESCENDING_STRUCTURE"
    NO_VALID_RANGE = "NO_VALID_RANGE"


@dataclass(slots=True)
class RangeDeviation:
    """Price left the range, failed to hold, and came back."""

    direction: str                 # "above" | "below"
    started_at: datetime
    ended_at: datetime | None
    max_distance_atr: float
    bars_outside: int
    closed_outside: bool
    reentry_strength_atr: float | None = None
    followed_through: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "direction": self.direction,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "max_distance_atr": self.max_distance_atr,
            "bars_outside": self.bars_outside,
            "closed_outside": self.closed_outside,
            "reentry_strength_atr": self.reentry_strength_atr,
            "followed_through": self.followed_through,
        }


@dataclass(slots=True)
class DetectedRange:
    """A validated range with both zones and its internal behaviour."""

    range_type: RangeType
    top_zone: Zone | None = None
    bottom_zone: Zone | None = None
    started_at: datetime | None = None
    last_bar: datetime | None = None
    duration_bars: int = 0
    width_pct: float | None = None
    width_atr: float | None = None
    top_touches: int = 0
    bottom_touches: int = 0
    wick_penetrations: int = 0
    close_penetrations: int = 0
    false_breakouts: int = 0
    deviations: list[RangeDeviation] = field(default_factory=list)
    reintegrations: int = 0
    volatility_inside: float | None = None
    bars_outside_recent: int = 0
    trend_before: str = "UNKNOWN"
    confidence: float = 0.0
    valid: bool = False
    reason: str = ""

    @property
    def midpoint(self) -> float | None:
        if self.top_zone is None or self.bottom_zone is None:
            return None
        return (self.top_zone.midpoint + self.bottom_zone.midpoint) / 2.0

    def position(self, price: float) -> float | None:
        """Where price sits inside the range, 0 = bottom, 1 = top.

        Values outside [0, 1] are meaningful (price has left the range) but are
        clamped for display to a small margin: a raw 14.06 said nothing useful
        beyond "far above", and reading it as a position was misleading.
        """
        if self.top_zone is None or self.bottom_zone is None:
            return None
        low, high = self.bottom_zone.midpoint, self.top_zone.midpoint
        if high <= low:
            return None
        raw = (price - low) / (high - low)
        return round(float(np.clip(raw, -0.5, 1.5)), 4)

    def to_dict(self) -> dict[str, Any]:
        return {
            "range_type": self.range_type.value,
            "valid": self.valid, "reason": self.reason,
            "top_zone": self.top_zone.to_dict() if self.top_zone else None,
            "bottom_zone": self.bottom_zone.to_dict() if self.bottom_zone else None,
            "midpoint": self.midpoint,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "duration_bars": self.duration_bars,
            "width_pct": self.width_pct, "width_atr": self.width_atr,
            "top_touches": self.top_touches, "bottom_touches": self.bottom_touches,
            "wick_penetrations": self.wick_penetrations,
            "close_penetrations": self.close_penetrations,
            "false_breakouts": self.false_breakouts,
            "deviations": [d.to_dict() for d in self.deviations],
            "reintegrations": self.reintegrations,
            "volatility_inside": self.volatility_inside,
            "bars_outside_recent": self.bars_outside_recent,
            "trend_before": self.trend_before,
            "confidence": self.confidence,
        }

    def describe(self) -> str:
        if not self.valid:
            return f"No valid range: {self.reason}"
        return (
            f"{self.range_type.value} between {self.bottom_zone.low:.2f}-"
            f"{self.bottom_zone.high:.2f} and {self.top_zone.low:.2f}-"
            f"{self.top_zone.high:.2f}, {self.width_atr:.1f} ATR wide, held for "
            f"{self.duration_bars} bars with {self.bottom_touches} bottom and "
            f"{self.top_touches} top touches"
            + (f", {len(self.deviations)} deviation(s)" if self.deviations else "")
            + f". Recognition confidence {self.confidence:.0f}/100."
        )


class RangeIntelligenceEngine:
    """Detect and characterise the current range, causally."""

    def __init__(self, lookback_bars: int = 200, zone_atr: float = 0.5) -> None:
        self.lookback_bars = lookback_bars
        self.zone_atr = zone_atr

    def detect(
        self,
        asset: Asset,
        timeframe: Timeframe = Timeframe.D1,
        as_of: datetime | None = None,
        df: pd.DataFrame | None = None,
    ) -> DetectedRange:
        if df is None:
            df = store.load_candles(asset, timeframe)
        if as_of is not None and not df.empty:
            df = df[df.index <= as_of]
        return self.detect_from_frame(df)

    def detect_from_frame(self, df: pd.DataFrame) -> DetectedRange:
        if df.empty or len(df) < MIN_BARS_FOR_RANGE:
            return DetectedRange(
                range_type=RangeType.NO_VALID_RANGE,
                reason=f"only {len(df)} bars, need {MIN_BARS_FOR_RANGE}",
            )

        window = df.iloc[-self.lookback_bars:]
        high, low, close = window["high"], window["low"], window["close"]
        atr = ind.atr(high, low, close, 14)
        current_atr = float(atr.iloc[-1]) if len(atr.dropna()) else np.nan
        if not np.isfinite(current_atr) or current_atr <= 0:
            return DetectedRange(
                range_type=RangeType.NO_VALID_RANGE, reason="ATR unavailable"
            )

        swings: SwingSeries = find_causal_swings(high, low, close, atr, lookback=5)
        if len(swings.highs) < MIN_TOUCHES_PER_SIDE or len(swings.lows) < MIN_TOUCHES_PER_SIDE:
            return DetectedRange(
                range_type=RangeType.NO_VALID_RANGE,
                reason=(
                    f"only {len(swings.highs)} confirmed highs and "
                    f"{len(swings.lows)} lows; a range needs at least "
                    f"{MIN_TOUCHES_PER_SIDE} of each"
                ),
            )

        top_zones = build_zones(
            swings.highs, high, low, close, atr, "resistance",
            zone_atr=self.zone_atr, min_touches=MIN_TOUCHES_PER_SIDE,
        )
        bottom_zones = build_zones(
            swings.lows, high, low, close, atr, "support",
            zone_atr=self.zone_atr, min_touches=MIN_TOUCHES_PER_SIDE,
        )
        if not top_zones or not bottom_zones:
            return DetectedRange(
                range_type=RangeType.NO_VALID_RANGE,
                reason="no zone reached the minimum number of touches on one side",
            )

        # A range needs two zones that are genuinely SEPARATE. Overlapping or
        # near-touching zones are one level described twice, and treating them
        # as a range produced nonsense like a "0.4 ATR wide range" whose
        # boundaries crossed each other.
        pair = self._select_pair(top_zones, bottom_zones, current_atr)
        if pair is None:
            return DetectedRange(
                range_type=RangeType.NO_VALID_RANGE,
                reason=(
                    "no pair of support and resistance zones is separated by at least "
                    f"{MIN_RANGE_WIDTH_ATR} ATR without overlapping"
                ),
            )
        top, bottom = pair

        detected = self._characterise(window, top, bottom, current_atr, atr)

        # A range price abandoned long ago describes history, not the present.
        if detected.valid and detected.bars_outside_recent > MAX_BARS_OUTSIDE:
            detected.valid = False
            detected.range_type = RangeType.NO_VALID_RANGE
            detected.reason = (
                f"price has been outside this range for {detected.bars_outside_recent} "
                f"consecutive bars (limit {MAX_BARS_OUTSIDE}); the range is stale"
            )
        return detected

    def _select_pair(
        self, top_zones: list[Zone], bottom_zones: list[Zone], current_atr: float
    ) -> tuple[Zone, Zone] | None:
        """Best-quality top/bottom pair that forms a real range."""
        best: tuple[float, Zone, Zone] | None = None
        for top in top_zones:
            for bottom in bottom_zones:
                # Zones must not overlap, and must be far enough apart that
                # calling the gap a "range" means something.
                if bottom.high >= top.low:
                    continue
                separation = (top.midpoint - bottom.midpoint) / current_atr
                if separation < MIN_RANGE_WIDTH_ATR:
                    continue
                score = top.quality.score + bottom.quality.score
                if best is None or score > best[0]:
                    best = (score, top, bottom)
        return (best[1], best[2]) if best else None

    def _characterise(
        self, window: pd.DataFrame, top: Zone, bottom: Zone,
        current_atr: float, atr: pd.Series,
    ) -> DetectedRange:
        close = window["close"]
        detected = DetectedRange(
            range_type=RangeType.HORIZONTAL_RANGE, top_zone=top, bottom_zone=bottom
        )

        width = top.midpoint - bottom.midpoint
        detected.width_pct = round(width / bottom.midpoint * 100, 3)
        detected.width_atr = round(width / current_atr, 2)

        start = min(top.first_touch, bottom.first_touch)
        detected.started_at = start
        detected.last_bar = window.index[-1]
        start_index = close.index.get_indexer([start], method="nearest")[0]
        inside = window.iloc[start_index:]
        detected.duration_bars = len(inside)

        # Count distinct touch EVENTS. Summing bars whose range overlaps the
        # zone reported 120 "top touches" in 193 bars, which simply meant price
        # spent most of its time up there - not that the level was tested 120
        # times. A touch is an entry into the zone after being outside it.
        detected.top_touches = _count_touch_events(inside["high"] >= top.low)
        detected.bottom_touches = _count_touch_events(inside["low"] <= bottom.high)
        detected.wick_penetrations = int(
            (inside["high"] > top.high).sum() + (inside["low"] < bottom.low).sum()
        )
        detected.close_penetrations = int(
            (inside["close"] > top.high).sum() + (inside["close"] < bottom.low).sum()
        )

        outside_now = (inside["close"] > top.high) | (inside["close"] < bottom.low)
        detected.bars_outside_recent = _trailing_run(outside_now)

        returns = inside["close"].pct_change().dropna()
        if len(returns) > 2:
            detected.volatility_inside = round(float(returns.std() * 100), 3)

        detected.deviations = self._find_deviations(inside, top, bottom, atr)
        detected.false_breakouts = sum(1 for d in detected.deviations if d.closed_outside)
        detected.reintegrations = sum(1 for d in detected.deviations if d.ended_at is not None)

        # Trend before the range: context that changes what the range means.
        if start_index >= 20:
            before = window.iloc[max(0, start_index - 40):start_index]["close"]
            if len(before) >= 10:
                change = (before.iloc[-1] / before.iloc[0] - 1) * 100
                detected.trend_before = (
                    "UPTREND" if change > 8 else "DOWNTREND" if change < -8 else "FLAT"
                )

        detected.range_type = self._classify(detected, inside, atr)
        detected.confidence = self._confidence(detected)
        detected.valid = detected.confidence >= 40 and detected.range_type is not RangeType.NO_VALID_RANGE
        if not detected.valid:
            detected.reason = (
                f"recognition confidence {detected.confidence:.0f}/100 is below the "
                "40 threshold for a validated range"
            )
        return detected

    def _find_deviations(
        self, inside: pd.DataFrame, top: Zone, bottom: Zone, atr: pd.Series
    ) -> list[RangeDeviation]:
        """Excursions beyond a zone that returned - the classic deviation."""
        deviations: list[RangeDeviation] = []
        for direction, boundary in (("above", top.high), ("below", bottom.low)):
            outside = (
                inside["high"] > boundary if direction == "above"
                else inside["low"] < boundary
            )
            if not outside.any():
                continue

            runs = (outside != outside.shift()).cumsum()[outside]
            for _, indices in inside[outside].groupby(runs).groups.items():
                chunk = inside.loc[indices]
                start_time = chunk.index[0]
                end_position = inside.index.get_indexer([chunk.index[-1]])[0]
                # Did price come back inside afterwards?
                came_back = end_position < len(inside) - 1
                atr_at = float(atr.reindex(inside.index).loc[chunk.index[0]])
                if not np.isfinite(atr_at) or atr_at <= 0:
                    continue

                distance = (
                    float(chunk["high"].max() - boundary) if direction == "above"
                    else float(boundary - chunk["low"].min())
                )
                closed_outside = bool(
                    (chunk["close"] > boundary).any() if direction == "above"
                    else (chunk["close"] < boundary).any()
                )

                reentry = None
                followed = False
                if came_back:
                    after = inside.iloc[end_position + 1:end_position + 6]
                    if len(after):
                        move = float(after["close"].iloc[-1] - chunk["close"].iloc[-1])
                        reentry = round(abs(move) / atr_at, 3)
                        # A bottom deviation "works" if price rose afterwards.
                        followed = move > 0 if direction == "below" else move < 0

                deviations.append(RangeDeviation(
                    direction=direction, started_at=start_time,
                    ended_at=chunk.index[-1] if came_back else None,
                    max_distance_atr=round(distance / atr_at, 3),
                    bars_outside=len(chunk), closed_outside=closed_outside,
                    reentry_strength_atr=reentry, followed_through=followed,
                ))
        return sorted(deviations, key=lambda d: d.started_at)

    def _classify(
        self, detected: DetectedRange, inside: pd.DataFrame, atr: pd.Series
    ) -> RangeType:
        if detected.width_atr is None:
            return RangeType.NO_VALID_RANGE
        # Width thresholds in ATR, so they mean the same on every asset.
        if detected.width_atr < 2.5:
            base = RangeType.TIGHT_RANGE
        elif detected.width_atr > 8.0:
            base = RangeType.BROAD_RANGE
        else:
            base = RangeType.HORIZONTAL_RANGE

        # Compression or expansion overrides the width label when volatility
        # is clearly trending inside the range.
        window_atr = atr.reindex(inside.index).dropna()
        if len(window_atr) >= 30:
            recent = float(window_atr.iloc[-10:].mean())
            earlier = float(window_atr.iloc[:-10].mean())
            if earlier > 0:
                ratio = recent / earlier
                if ratio < 0.7:
                    return RangeType.RANGE_COMPRESSION
                if ratio > 1.4:
                    return RangeType.RANGE_EXPANSION
        return base

    def _confidence(self, detected: DetectedRange) -> float:
        """How cleanly this matches the definition of a range.

        Recognition only. This number never implies anything about what price
        does next.
        """
        parts: list[float] = []

        touches = detected.top_touches + detected.bottom_touches
        parts.append(float(np.clip((touches - 2) / 8 * 100, 0, 100)))
        # Both sides must be tested; a "range" touched only at the bottom is
        # a support, not a range.
        balance = min(detected.top_touches, detected.bottom_touches)
        parts.append(float(np.clip(balance / 3 * 100, 0, 100)))
        parts.append(float(np.clip(detected.duration_bars / 60 * 100, 0, 100)))

        if detected.close_penetrations and detected.duration_bars:
            breach_rate = detected.close_penetrations / detected.duration_bars
            parts.append(float(np.clip((0.12 - breach_rate) / 0.12 * 100, 0, 100)))
        else:
            parts.append(100.0)

        if detected.top_zone and detected.bottom_zone:
            parts.append((detected.top_zone.quality.score + detected.bottom_zone.quality.score) / 2)

        return round(float(np.mean(parts)), 1)

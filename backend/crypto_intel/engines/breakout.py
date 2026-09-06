"""Breakout quality: how convincing a level break is, not whether to act on it.

A breakout is an observation about price crossing a level. Whether that
observation carries predictive information is a separate question answered by
research, not by this engine. So the score here measures CONVICTION OF THE
BREAK - how far beyond, on what volume, with what follow-through - and never
implies a direction to take.

The distinction matters because "high quality breakout" reads like a
recommendation. It is not one. A 95/100 breakout with NO_MEASURABLE_EDGE means
the break is unambiguous and we still cannot say what follows.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

from ..core.enums import Asset, Timeframe
from ..history import store
from ..logging_setup import get_logger
from .technical import indicators as ind
from .technical.structure import find_swings

log = get_logger("engines.breakout")

MIN_BARS = 120


class BreakoutState(StrEnum):
    NONE = "NONE"
    BREAKOUT_ATTEMPT = "BREAKOUT_ATTEMPT"
    CONFIRMED_BREAKOUT = "CONFIRMED_BREAKOUT"
    FAILED_BREAKOUT = "FAILED_BREAKOUT"
    FAKEOUT = "FAKEOUT"
    BREAKOUT_RETEST = "BREAKOUT_RETEST"
    REINTEGRATION = "REINTEGRATION"


class BreakoutAssessment(BaseModel):
    asset: str
    timeframe: str
    state: BreakoutState = BreakoutState.NONE
    direction: str = "NONE"                # UP / DOWN / NONE
    level: float | None = None
    level_touches: int = 0
    quality_score: float | None = Field(default=None, description="0-100 conviction of the break")
    components: dict[str, Any] = Field(default_factory=dict)
    bars_since_break: int | None = None
    close_beyond_atr: float | None = None
    relative_volume: float | None = None
    follow_through_pct: float | None = None
    retest_occurred: bool = False
    higher_timeframe_aligned: bool | None = None
    interpretation: str = ""
    missing: list[str] = Field(default_factory=list)
    edge_note: str = (
        "Quality measures how convincing the break is. It is NOT a probability that "
        "price continues, and carries no directional recommendation."
    )


class BreakoutQualityEngine:
    """Detect a recent level break and score how convincing it is."""

    def __init__(self, lookback_bars: int = 300) -> None:
        self.lookback_bars = lookback_bars

    def assess(
        self,
        asset: Asset,
        timeframe: Timeframe = Timeframe.D1,
        as_of: datetime | None = None,
    ) -> BreakoutAssessment:
        out = BreakoutAssessment(asset=asset.value, timeframe=timeframe.value)

        df = store.load_candles(asset, timeframe)
        if as_of is not None and not df.empty:
            df = df[df.index <= as_of]
        if df.empty or len(df) < MIN_BARS:
            out.missing.append("price history")
            out.interpretation = (
                f"only {len(df)} bars, below the {MIN_BARS} needed to establish a level"
            )
            return out

        df = df.iloc[-self.lookback_bars:]
        high, low, close, volume = df["high"], df["low"], df["close"], df["volume"]
        atr = ind.atr(high, low, close, 14)
        current_atr = float(atr.iloc[-1])
        if not np.isfinite(current_atr) or current_atr <= 0:
            out.missing.append("ATR")
            out.interpretation = "ATR unavailable, cannot normalise the break distance"
            return out

        # Levels come from confirmed swings only. `find_swings` excludes bars
        # within `lookback` of the end, so a level can never be built from a
        # pivot that is not yet confirmed.
        swing_highs, swing_lows = find_swings(high, low, lookback=5)
        if not swing_highs and not swing_lows:
            out.interpretation = "no confirmed swing points in the window"
            return out

        break_info = self._find_recent_break(df, swing_highs, swing_lows, current_atr)
        if break_info is None:
            out.interpretation = (
                "no level break detected in the recent window; price is inside its "
                "established range"
            )
            return out

        out.direction = break_info["direction"]
        out.level = round(break_info["level"], 6)
        out.level_touches = break_info["touches"]
        out.bars_since_break = break_info["bars_since"]

        self._score(df, out, break_info, current_atr, atr, volume)
        self._classify(df, out, break_info, current_atr)
        self._higher_timeframe(asset, timeframe, out)
        self._interpret(out)
        return out

    def _find_recent_break(
        self, df: pd.DataFrame, swing_highs, swing_lows, current_atr: float
    ) -> dict[str, Any] | None:
        """Most recent close beyond a level built from confirmed swings."""
        close = df["close"]
        n = len(df)
        recent_window = min(30, n - 1)

        candidates: list[dict[str, Any]] = []
        for swings, direction in ((swing_highs, "UP"), (swing_lows, "DOWN")):
            if not swings:
                continue
            # Cluster swing prices that sit within half an ATR of each other.
            prices = sorted(s.price for s in swings)
            clusters: list[list[float]] = []
            for price in prices:
                if clusters and abs(price - np.mean(clusters[-1])) <= current_atr * 0.5:
                    clusters[-1].append(price)
                else:
                    clusters.append([price])

            for cluster in clusters:
                level = float(np.mean(cluster))
                touches = len(cluster)
                if touches < 2:
                    continue
                # Where did price first close beyond this level recently?
                for offset in range(recent_window, 0, -1):
                    index = n - offset
                    if index < 1:
                        continue
                    prior, now = close.iloc[index - 1], close.iloc[index]
                    crossed_up = direction == "UP" and prior <= level < now
                    crossed_down = direction == "DOWN" and prior >= level > now
                    if crossed_up or crossed_down:
                        candidates.append({
                            "direction": direction, "level": level, "touches": touches,
                            "break_index": index, "bars_since": n - 1 - index,
                        })
                        break

        if not candidates:
            return None
        # The most recent break is the relevant one.
        return min(candidates, key=lambda c: c["bars_since"])

    def _score(
        self, df: pd.DataFrame, out: BreakoutAssessment, info: dict[str, Any],
        current_atr: float, atr: pd.Series, volume: pd.Series,
    ) -> None:
        close = df["close"]
        index = info["break_index"]
        level = info["level"]
        up = info["direction"] == "UP"
        components: dict[str, Any] = {}
        parts: list[float] = []

        # 1. How far beyond the level did it close, in ATR?
        distance = (close.iloc[index] - level) if up else (level - close.iloc[index])
        out.close_beyond_atr = round(float(distance / current_atr), 3)
        distance_score = float(np.clip(out.close_beyond_atr / 1.5 * 100, 0, 100))
        parts.append(distance_score)
        components["distance_beyond_level"] = round(distance_score, 1)

        # 2. Volume on the breaking bar against its recent average.
        recent_volume = volume.iloc[max(0, index - 20):index]
        if len(recent_volume) >= 10 and recent_volume.mean() > 0:
            out.relative_volume = round(float(volume.iloc[index] / recent_volume.mean()), 2)
            volume_score = float(np.clip((out.relative_volume - 0.8) / 1.2 * 100, 0, 100))
            parts.append(volume_score)
            components["relative_volume"] = round(volume_score, 1)
        else:
            out.missing.append("volume baseline")

        # 3. Follow-through after the break.
        if out.bars_since_break and out.bars_since_break >= 1:
            move = (close.iloc[-1] - close.iloc[index]) / close.iloc[index] * 100
            out.follow_through_pct = round(float(move if up else -move), 2)
            follow_score = float(np.clip(out.follow_through_pct / 3.0 * 100, 0, 100))
            parts.append(follow_score)
            components["follow_through"] = round(follow_score, 1)
        else:
            components["follow_through"] = "too early to judge"
            out.missing.append("follow-through (break is the latest bar)")

        # 4. Did the level hold on a retest?
        window = df.iloc[index:]
        if up:
            touched = bool((window["low"] <= level * 1.005).any())
            held = touched and bool(close.iloc[-1] > level)
        else:
            touched = bool((window["high"] >= level * 0.995).any())
            held = touched and bool(close.iloc[-1] < level)
        out.retest_occurred = bool(touched)
        if touched:
            retest_score = 85.0 if held else 15.0
            parts.append(retest_score)
            components["retest"] = round(retest_score, 1)

        # 5. Volatility expansion: a break on compressing volatility is weaker.
        if index >= 30:
            before = float(atr.iloc[index - 20:index].mean())
            after = float(atr.iloc[index:].mean())
            if before > 0:
                ratio = after / before
                expansion_score = float(np.clip((ratio - 0.85) / 0.5 * 100, 0, 100))
                parts.append(expansion_score)
                components["volatility_expansion"] = round(expansion_score, 1)

        # 6. Level strength: more touches before the break means more meaning.
        touch_score = float(np.clip((info["touches"] - 1) / 4 * 100, 0, 100))
        parts.append(touch_score)
        components["level_touches"] = round(touch_score, 1)

        out.components = components
        out.quality_score = round(float(np.mean(parts)), 1) if parts else None

    def _classify(
        self, df: pd.DataFrame, out: BreakoutAssessment, info: dict[str, Any], current_atr: float
    ) -> None:
        close = df["close"]
        level = info["level"]
        up = info["direction"] == "UP"
        last = float(close.iloc[-1])
        back_inside = (last < level) if up else (last > level)
        bars_since = out.bars_since_break or 0

        if back_inside:
            # Beyond the level then back within a couple of bars is a fakeout;
            # a longer excursion that fails is a reintegration.
            out.state = BreakoutState.FAKEOUT if bars_since <= 3 else BreakoutState.REINTEGRATION
        elif bars_since == 0:
            out.state = BreakoutState.BREAKOUT_ATTEMPT
        elif out.retest_occurred:
            out.state = BreakoutState.BREAKOUT_RETEST
        elif bars_since >= 3 and (out.close_beyond_atr or 0) >= 0.5:
            out.state = BreakoutState.CONFIRMED_BREAKOUT
        elif (out.follow_through_pct or 0) < 0:
            out.state = BreakoutState.FAILED_BREAKOUT
        else:
            out.state = BreakoutState.BREAKOUT_ATTEMPT

    def _higher_timeframe(
        self, asset: Asset, timeframe: Timeframe, out: BreakoutAssessment
    ) -> None:
        """Does the next timeframe up agree with the break's direction?"""
        higher = {
            Timeframe.M15: Timeframe.H1, Timeframe.H1: Timeframe.H4,
            Timeframe.H4: Timeframe.D1, Timeframe.D1: Timeframe.W1,
        }.get(timeframe)
        if higher is None:
            return
        df = store.load_candles(asset, higher)
        if df.empty or len(df) < 60:
            out.missing.append(f"{higher.value} history for alignment")
            return
        ema50 = df["close"].ewm(span=50, adjust=False).mean()
        higher_bullish = bool(df["close"].iloc[-1] > ema50.iloc[-1])
        out.higher_timeframe_aligned = (
            higher_bullish if out.direction == "UP" else not higher_bullish
        )

    def _interpret(self, out: BreakoutAssessment) -> None:
        if out.quality_score is None:
            out.interpretation = "break detected but not enough inputs to score it"
            return
        alignment = (
            "aligned with the higher timeframe" if out.higher_timeframe_aligned
            else "against the higher timeframe" if out.higher_timeframe_aligned is False
            else "higher-timeframe alignment unknown"
        )
        out.interpretation = (
            f"{out.state.value} to the {out.direction.lower()} through {out.level}, "
            f"{out.bars_since_break} bar(s) ago. Conviction {out.quality_score:.0f}/100 "
            f"(closed {out.close_beyond_atr} ATR beyond"
            + (f", volume {out.relative_volume}x" if out.relative_volume else "")
            + f"), {alignment}. "
            + ("A retest occurred. " if out.retest_occurred else "")
            + "This scores how clean the break is, not what happens next."
        )
        if out.missing:
            out.interpretation += f" Not scored: {'; '.join(out.missing)}."

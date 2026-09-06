"""Concrete chart pattern detectors.

Each one is conservative on purpose: it returns None unless the geometry
genuinely matches. The confidence floor in config/thresholds.yaml then filters
anything marginal, so a report never claims a head-and-shoulders because three
bumps happened to appear.
"""

from __future__ import annotations

import numpy as np

from ....core.enums import ConfirmationState, Direction
from ....core.models import PatternMatch
from .base import PatternContext, PatternDetector, register


def _cfg(ctx: PatternContext, key: str, default: dict) -> dict:
    return {**default, **(ctx.config.get(key) or {})}


class DoubleTopDetector(PatternDetector):
    """Two comparable highs separated by a meaningful valley."""

    name = "double_top"
    min_bars = 30

    def detect(self, ctx: PatternContext) -> PatternMatch | None:
        if not self.enough_data(ctx) or len(ctx.swing_highs) < 2:
            return None
        cfg = _cfg(ctx, "double_top",
                   {"peak_tolerance_pct": 2.0, "min_valley_depth_pct": 3.0, "min_bars_between": 8})

        p2 = ctx.swing_highs[-1]
        p1 = ctx.swing_highs[-2]
        if p2.index - p1.index < cfg["min_bars_between"]:
            return None

        peak_diff_pct = abs(p2.price - p1.price) / p1.price * 100.0
        if peak_diff_pct > cfg["peak_tolerance_pct"]:
            return None

        valley = ctx.low.iloc[p1.index : p2.index + 1].min()
        if np.isnan(valley):
            return None
        depth_pct = (min(p1.price, p2.price) - valley) / min(p1.price, p2.price) * 100.0
        if depth_pct < cfg["min_valley_depth_pct"]:
            return None

        last_close = float(ctx.close.iloc[-1])
        neckline = float(valley)
        confirmed = last_close < neckline
        # Tighter peaks and a deeper valley both make the pattern cleaner.
        confidence = min(
            95.0,
            55.0
            + (cfg["peak_tolerance_pct"] - peak_diff_pct) * 8.0
            + min(depth_pct, 12.0) * 1.6
            + (12.0 if confirmed else 0.0),
        )
        return PatternMatch(
            pattern="double_top",
            confidence=round(confidence, 1),
            timeframe=ctx.timeframe,
            confirmation_state=ConfirmationState.CONFIRMED if confirmed else ConfirmationState.FORMING,
            invalidation_level=round(max(p1.price, p2.price), 8),
            target_level=round(neckline - (max(p1.price, p2.price) - neckline), 8),
            direction=Direction.BEARISH,
            start_index=p1.index,
            end_index=p2.index,
            notes=(
                f"Two highs within {peak_diff_pct:.2f}% ({p1.price:.2f} / {p2.price:.2f}), "
                f"valley {depth_pct:.1f}% below. Neckline {neckline:.2f}."
                + ("" if confirmed else " Not confirmed: neckline not broken.")
            ),
            evidence={"peak1": p1.price, "peak2": p2.price, "neckline": neckline,
                      "peak_diff_pct": round(peak_diff_pct, 2), "valley_depth_pct": round(depth_pct, 2)},
        )


class DoubleBottomDetector(PatternDetector):
    """Two comparable lows separated by a meaningful rally."""

    name = "double_bottom"
    min_bars = 30

    def detect(self, ctx: PatternContext) -> PatternMatch | None:
        if not self.enough_data(ctx) or len(ctx.swing_lows) < 2:
            return None
        cfg = _cfg(ctx, "double_bottom",
                   {"peak_tolerance_pct": 2.0, "min_valley_depth_pct": 3.0, "min_bars_between": 8})

        b2 = ctx.swing_lows[-1]
        b1 = ctx.swing_lows[-2]
        if b2.index - b1.index < cfg["min_bars_between"]:
            return None

        diff_pct = abs(b2.price - b1.price) / b1.price * 100.0
        if diff_pct > cfg["peak_tolerance_pct"]:
            return None

        peak = ctx.high.iloc[b1.index : b2.index + 1].max()
        if np.isnan(peak):
            return None
        height_pct = (peak - max(b1.price, b2.price)) / max(b1.price, b2.price) * 100.0
        if height_pct < cfg["min_valley_depth_pct"]:
            return None

        last_close = float(ctx.close.iloc[-1])
        neckline = float(peak)
        confirmed = last_close > neckline
        confidence = min(
            95.0,
            55.0
            + (cfg["peak_tolerance_pct"] - diff_pct) * 8.0
            + min(height_pct, 12.0) * 1.6
            + (12.0 if confirmed else 0.0),
        )
        return PatternMatch(
            pattern="double_bottom",
            confidence=round(confidence, 1),
            timeframe=ctx.timeframe,
            confirmation_state=ConfirmationState.CONFIRMED if confirmed else ConfirmationState.FORMING,
            invalidation_level=round(min(b1.price, b2.price), 8),
            target_level=round(neckline + (neckline - min(b1.price, b2.price)), 8),
            direction=Direction.BULLISH,
            start_index=b1.index,
            end_index=b2.index,
            notes=(
                f"Two lows within {diff_pct:.2f}% ({b1.price:.2f} / {b2.price:.2f}), "
                f"rally {height_pct:.1f}% between. Neckline {neckline:.2f}."
                + ("" if confirmed else " Not confirmed: neckline not broken.")
            ),
            evidence={"bottom1": b1.price, "bottom2": b2.price, "neckline": neckline,
                      "diff_pct": round(diff_pct, 2), "height_pct": round(height_pct, 2)},
        )


class RangeDetector(PatternDetector):
    """Sideways consolidation with repeated touches of both boundaries."""

    name = "range"
    min_bars = 25

    def detect(self, ctx: PatternContext) -> PatternMatch | None:
        if not self.enough_data(ctx):
            return None
        cfg = _cfg(ctx, "range", {"max_width_pct": 12.0, "min_bars": 20, "min_touches": 4})
        window = int(cfg["min_bars"])
        highs = ctx.high.iloc[-window:]
        lows = ctx.low.iloc[-window:]
        top, bottom = float(highs.max()), float(lows.min())
        if bottom <= 0:
            return None

        width_pct = (top - bottom) / bottom * 100.0
        if width_pct > cfg["max_width_pct"]:
            return None

        # A real range is touched repeatedly, not just bounded once.
        tol = (top - bottom) * 0.12
        touches_top = int((highs >= top - tol).sum())
        touches_bottom = int((lows <= bottom + tol).sum())
        if touches_top + touches_bottom < cfg["min_touches"]:
            return None

        last = float(ctx.close.iloc[-1])
        position = (last - bottom) / (top - bottom) * 100.0 if top > bottom else 50.0
        confidence = min(90.0, 50.0 + (touches_top + touches_bottom) * 4.0
                         + (cfg["max_width_pct"] - width_pct))
        return PatternMatch(
            pattern="range",
            confidence=round(confidence, 1),
            timeframe=ctx.timeframe,
            confirmation_state=ConfirmationState.CONFIRMED,
            invalidation_level=round(top, 8),
            direction=Direction.NEUTRAL,
            start_index=len(ctx.close) - window,
            end_index=len(ctx.close) - 1,
            notes=(
                f"Range {bottom:.2f}-{top:.2f} ({width_pct:.1f}% wide) over {window} bars, "
                f"{touches_top} top / {touches_bottom} bottom touches. "
                f"Price at {position:.0f}% of range."
            ),
            evidence={"top": top, "bottom": bottom, "width_pct": round(width_pct, 2),
                      "position_pct": round(position, 1),
                      "touches_top": touches_top, "touches_bottom": touches_bottom},
        )


class BreakoutDetector(PatternDetector):
    """Close decisively beyond a consolidation, on above-average volume.

    Volume is required: a breakout without participation is exactly the setup
    that turns into a fake breakout, so we refuse to call it one.
    """

    name = "breakout"
    min_bars = 30

    def detect(self, ctx: PatternContext) -> PatternMatch | None:
        if not self.enough_data(ctx):
            return None
        cfg = _cfg(ctx, "breakout", {"min_volume_ratio": 1.4, "min_close_beyond_pct": 0.5})
        lookback = 20
        prior_high = float(ctx.high.iloc[-lookback - 1 : -1].max())
        prior_low = float(ctx.low.iloc[-lookback - 1 : -1].min())
        last = float(ctx.close.iloc[-1])

        avg_vol = float(ctx.volume.iloc[-lookback - 1 : -1].mean())
        cur_vol = float(ctx.volume.iloc[-1])
        vol_ratio = cur_vol / avg_vol if avg_vol > 0 else 0.0
        # A forming bar has only accumulated part of its volume, so a genuine
        # breakout would look unconfirmed. Scale the comparison accordingly.
        completion = ctx.config.get("_bar_completion")
        if completion and 0 < completion < 0.95:
            vol_ratio = vol_ratio / completion

        up_pct = (last - prior_high) / prior_high * 100.0
        down_pct = (prior_low - last) / prior_low * 100.0

        if up_pct >= cfg["min_close_beyond_pct"]:
            direction, beyond, level = Direction.BULLISH, up_pct, prior_high
        elif down_pct >= cfg["min_close_beyond_pct"]:
            direction, beyond, level = Direction.BEARISH, down_pct, prior_low
        else:
            return None

        if vol_ratio < cfg["min_volume_ratio"]:
            # Reported as forming, with reduced confidence - not as a breakout.
            confidence = 45.0 + min(beyond, 5.0) * 2.0
            state = ConfirmationState.FORMING
            note = f"Price beyond level but volume only {vol_ratio:.2f}x average - unconfirmed."
        else:
            confidence = min(92.0, 58.0 + min(beyond, 6.0) * 3.5 + min(vol_ratio, 3.0) * 6.0)
            state = ConfirmationState.CONFIRMED
            note = f"Close {beyond:.2f}% beyond {level:.2f} on {vol_ratio:.2f}x average volume."

        return PatternMatch(
            pattern="breakout",
            confidence=round(confidence, 1),
            timeframe=ctx.timeframe,
            confirmation_state=state,
            invalidation_level=round(level, 8),
            direction=direction,
            start_index=len(ctx.close) - lookback,
            end_index=len(ctx.close) - 1,
            notes=note,
            evidence={"level": level, "beyond_pct": round(beyond, 2),
                      "volume_ratio": round(vol_ratio, 2)},
        )


class FakeBreakoutDetector(PatternDetector):
    """Price broke a level then closed back inside within a few bars.

    Often more informative than the breakout itself: it shows the move was
    rejected.
    """

    name = "fake_breakout"
    min_bars = 30

    def detect(self, ctx: PatternContext) -> PatternMatch | None:
        if not self.enough_data(ctx):
            return None
        cfg = _cfg(ctx, "fake_breakout", {"max_bars_back_inside": 3})
        max_back = int(cfg["max_bars_back_inside"])
        lookback = 20

        for bars_ago in range(1, max_back + 1):
            i = len(ctx.close) - 1 - bars_ago
            if i - lookback < 0:
                continue
            prior_high = float(ctx.high.iloc[i - lookback : i].max())
            prior_low = float(ctx.low.iloc[i - lookback : i].min())
            broke_close = float(ctx.close.iloc[i])
            last = float(ctx.close.iloc[-1])

            if broke_close > prior_high and last < prior_high:
                return self._match(ctx, "bearish", prior_high, bars_ago, broke_close, last)
            if broke_close < prior_low and last > prior_low:
                return self._match(ctx, "bullish", prior_low, bars_ago, broke_close, last)
        return None

    def _match(self, ctx, bias, level, bars_ago, broke, last) -> PatternMatch:
        # A faster rejection is a stronger signal.
        confidence = min(85.0, 58.0 + (4 - bars_ago) * 6.0)
        return PatternMatch(
            pattern="fake_breakout",
            confidence=round(confidence, 1),
            timeframe=ctx.timeframe,
            confirmation_state=ConfirmationState.CONFIRMED,
            invalidation_level=round(float(broke), 8),
            direction=Direction.BEARISH if bias == "bearish" else Direction.BULLISH,
            end_index=len(ctx.close) - 1,
            notes=(
                f"Broke {level:.2f} {bars_ago} bar(s) ago (close {broke:.2f}) "
                f"then returned inside (now {last:.2f}). Breakout rejected."
            ),
            evidence={"level": level, "break_close": broke, "current": last, "bars_ago": bars_ago},
        )


class HeadAndShouldersDetector(PatternDetector):
    """Three peaks, the middle clearly highest, shoulders roughly level."""

    name = "head_and_shoulders"
    min_bars = 40

    def detect(self, ctx: PatternContext) -> PatternMatch | None:
        if not self.enough_data(ctx) or len(ctx.swing_highs) < 3:
            return None
        left, head, right = ctx.swing_highs[-3], ctx.swing_highs[-2], ctx.swing_highs[-1]

        # The head must genuinely dominate both shoulders.
        if not (head.price > left.price * 1.015 and head.price > right.price * 1.015):
            return None
        shoulder_diff = abs(left.price - right.price) / max(left.price, right.price) * 100.0
        if shoulder_diff > 3.5:
            return None

        troughs = [t for t in ctx.swing_lows if left.index < t.index < right.index]
        if len(troughs) < 2:
            return None
        neckline = sum(t.price for t in troughs[-2:]) / 2.0

        last = float(ctx.close.iloc[-1])
        confirmed = last < neckline
        head_prom = (head.price - max(left.price, right.price)) / head.price * 100.0
        confidence = min(90.0, 52.0 + (3.5 - shoulder_diff) * 5.0
                         + min(head_prom, 10.0) * 1.8 + (10.0 if confirmed else 0.0))

        return PatternMatch(
            pattern="head_and_shoulders",
            confidence=round(confidence, 1),
            timeframe=ctx.timeframe,
            confirmation_state=ConfirmationState.CONFIRMED if confirmed else ConfirmationState.FORMING,
            invalidation_level=round(head.price, 8),
            target_level=round(neckline - (head.price - neckline), 8),
            direction=Direction.BEARISH,
            start_index=left.index,
            end_index=right.index,
            notes=(
                f"Shoulders {left.price:.2f}/{right.price:.2f} (diff {shoulder_diff:.2f}%), "
                f"head {head.price:.2f}, neckline {neckline:.2f}."
                + ("" if confirmed else " Not confirmed: neckline intact.")
            ),
            evidence={"left_shoulder": left.price, "head": head.price,
                      "right_shoulder": right.price, "neckline": neckline},
        )


class InverseHeadAndShouldersDetector(PatternDetector):
    """Mirror of head-and-shoulders: three troughs, middle clearly lowest."""

    name = "inverse_head_and_shoulders"
    min_bars = 40

    def detect(self, ctx: PatternContext) -> PatternMatch | None:
        if not self.enough_data(ctx) or len(ctx.swing_lows) < 3:
            return None
        left, head, right = ctx.swing_lows[-3], ctx.swing_lows[-2], ctx.swing_lows[-1]

        if not (head.price < left.price * 0.985 and head.price < right.price * 0.985):
            return None
        shoulder_diff = abs(left.price - right.price) / max(left.price, right.price) * 100.0
        if shoulder_diff > 3.5:
            return None

        peaks = [p for p in ctx.swing_highs if left.index < p.index < right.index]
        if len(peaks) < 2:
            return None
        neckline = sum(p.price for p in peaks[-2:]) / 2.0

        last = float(ctx.close.iloc[-1])
        confirmed = last > neckline
        head_prom = (min(left.price, right.price) - head.price) / head.price * 100.0
        confidence = min(90.0, 52.0 + (3.5 - shoulder_diff) * 5.0
                         + min(head_prom, 10.0) * 1.8 + (10.0 if confirmed else 0.0))

        return PatternMatch(
            pattern="inverse_head_and_shoulders",
            confidence=round(confidence, 1),
            timeframe=ctx.timeframe,
            confirmation_state=ConfirmationState.CONFIRMED if confirmed else ConfirmationState.FORMING,
            invalidation_level=round(head.price, 8),
            target_level=round(neckline + (neckline - head.price), 8),
            direction=Direction.BULLISH,
            start_index=left.index,
            end_index=right.index,
            notes=(
                f"Troughs {left.price:.2f}/{right.price:.2f} (diff {shoulder_diff:.2f}%), "
                f"head {head.price:.2f}, neckline {neckline:.2f}."
                + ("" if confirmed else " Not confirmed: neckline intact.")
            ),
            evidence={"left_shoulder": left.price, "head": head.price,
                      "right_shoulder": right.price, "neckline": neckline},
        )


class TriangleDetector(PatternDetector):
    """Ascending, descending and symmetrical triangles.

    Uses linear regression on the recent swing highs and lows: a flat side plus
    a converging side. Requires real convergence, so a random drift is not
    dressed up as a triangle.
    """

    name = "triangle"
    min_bars = 35

    def detect(self, ctx: PatternContext) -> PatternMatch | None:
        if not self.enough_data(ctx):
            return None
        highs = list(ctx.swing_highs)[-4:]
        lows = list(ctx.swing_lows)[-4:]
        if len(highs) < 3 or len(lows) < 3:
            return None

        last = float(ctx.close.iloc[-1])
        hs, _ = _slope_pct(highs, last)
        ls, _ = _slope_pct(lows, last)
        if hs is None or ls is None:
            return None

        flat = 0.05      # % per bar - below this a side is effectively flat
        top = float(max(s.price for s in highs))
        bottom = float(min(s.price for s in lows))
        start_index = min(highs[0].index, lows[0].index)

        if abs(hs) < flat and ls > flat:
            kind, direction, invalidation = "ascending_triangle", Direction.BULLISH, bottom
        elif abs(ls) < flat and hs < -flat:
            kind, direction, invalidation = "descending_triangle", Direction.BEARISH, top
        elif hs < -flat and ls > flat:
            kind, direction, invalidation = "symmetrical_triangle", Direction.NEUTRAL, bottom
        else:
            return None

        # Convergence must be meaningful, otherwise it is just noise.
        convergence = abs(hs - ls)
        if convergence < 0.04:
            return None

        confidence = min(88.0, 50.0 + min(convergence, 1.0) * 22.0
                         + (len(highs) + len(lows)) * 1.6)
        return PatternMatch(
            pattern=kind,
            confidence=round(confidence, 1),
            timeframe=ctx.timeframe,
            confirmation_state=ConfirmationState.FORMING,
            invalidation_level=round(invalidation, 8),
            direction=direction,
            start_index=start_index,
            end_index=len(ctx.close) - 1,
            notes=(
                f"Upper slope {hs:+.3f}%/bar, lower slope {ls:+.3f}%/bar "
                f"(convergence {convergence:.3f}). Range {bottom:.2f}-{top:.2f}. "
                "Breakout direction not yet decided."
            ),
            evidence={"upper_slope_pct_per_bar": round(hs, 4),
                      "lower_slope_pct_per_bar": round(ls, 4),
                      "top": top, "bottom": bottom},
        )


def _slope_pct(points, reference_price: float) -> tuple[float | None, float | None]:
    """Least-squares slope through swing prices, as % of price per bar."""
    if len(points) < 2 or reference_price <= 0:
        return None, None
    xs = np.array([p.index for p in points], dtype=float)
    ys = np.array([p.price for p in points], dtype=float)
    if xs.max() - xs.min() < 1:
        return None, None
    slope, intercept = np.polyfit(xs, ys, 1)
    return float(slope / reference_price * 100.0), float(intercept)


def register_all() -> None:
    """Register every detector. Called once at import of the package."""
    for detector in (
        DoubleTopDetector(), DoubleBottomDetector(), RangeDetector(),
        BreakoutDetector(), FakeBreakoutDetector(),
        HeadAndShouldersDetector(), InverseHeadAndShouldersDetector(),
        TriangleDetector(),
    ):
        register(detector)

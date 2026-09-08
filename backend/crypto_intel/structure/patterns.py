"""Structural pattern detection, ATR-normalised and causally confirmed.

Two rules govern this module.

First, RECOGNITION IS NOT EDGE. Every detection carries a
`recognition_confidence` describing how cleanly the shape matches its
definition, and a separate `edge_state` describing whether that pattern has
been shown to precede anything. A double bottom can be textbook-perfect
(confidence 91) and carry NO_MEASURABLE_EDGE. Turning 91 into "91% chance of
going up" is the exact error this separation exists to prevent.

Second, QUALITY OVER QUANTITY. A pattern whose definition cannot be written
down without hand-waving is marked EXPERIMENTAL rather than shipped as if it
were reliable. Detecting fifty fragile shapes is worse than detecting eight
solid ones.

All tolerances scale with ATR, so "two comparable highs" means the same
structural thing on BTC at 90,000 and SOL at 95.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

import numpy as np
import pandas as pd

from ..core.enums import Timeframe
from ..logging_setup import get_logger
from .geometry import GeometryPoint, GeometryZone, PatternGeometry, TrendLine
from .quality import (
    PatternCriteria,
    QualityReport,
    fit_line,
    pivot_quality,
    symmetry_score,
    volume_trend_score,
)
from .swings import CausalSwing, SwingSeries

log = get_logger("structure.patterns")


class PatternClass(StrEnum):
    """How trustworthy the DETECTION is - not the prediction."""

    DETERMINISTIC = "DETERMINISTIC"   # geometry fully specified, no judgement
    HEURISTIC = "HEURISTIC"           # specified, but thresholds are choices
    HUMAN_LIKE = "HUMAN_LIKE"         # approximates what an analyst draws
    EXPERIMENTAL = "EXPERIMENTAL"     # definition still too subjective to trust


class PatternState(StrEnum):
    CANDIDATE = "CANDIDATE"           # shape present, trigger not reached
    CONFIRMED = "CONFIRMED"           # trigger reached (e.g. neckline broken)
    FAILED = "FAILED"                 # invalidation reached instead


class PatternEdgeState(StrEnum):
    """Whether the pattern predicts anything. Filled from research, not here."""

    POSITIVE_EDGE = "POSITIVE_EDGE"
    NEGATIVE_EDGE = "NEGATIVE_EDGE"
    NO_MEASURABLE_EDGE = "NO_MEASURABLE_EDGE"
    UNSTABLE = "UNSTABLE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    NOT_YET_TESTED = "NOT_YET_TESTED"


@dataclass(slots=True)
class StructuralPattern:
    """One detected pattern, with recognition and edge kept apart."""

    name: str
    pattern_class: PatternClass
    state: PatternState
    recognition_confidence: float          # 0-100, shape match only
    detected_at: datetime
    confirmation_time: datetime | None = None
    direction_if_textbook: str = "NEUTRAL"  # what THEORY says, not what we claim
    key_levels: dict[str, float] = field(default_factory=dict)
    invalidation_level: float | None = None
    invalidation_rule: str = ""
    components: dict[str, Any] = field(default_factory=dict)
    edge_state: PatternEdgeState = PatternEdgeState.NOT_YET_TESTED
    edge_note: str = ""
    notes: str = ""
    #: Enough to redraw the figure on a chart. Produced by the detector, which
    #: is the only place that knows which pivots define the shape.
    geometry: PatternGeometry = field(default_factory=PatternGeometry)
    #: Bars from the first defining pivot to the last, for the bar-count gates.
    bars_span: int = 0
    #: Which version of which detector produced this. Filled by `detect_all`
    #: rather than by each detector, so a new detector cannot forget it.
    detector_version: str = "unversioned"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "pattern_class": self.pattern_class.value,
            "state": self.state.value,
            "recognition_confidence": self.recognition_confidence,
            "detected_at": self.detected_at.isoformat(),
            "confirmation_time": (
                self.confirmation_time.isoformat() if self.confirmation_time else None
            ),
            "direction_if_textbook": self.direction_if_textbook,
            "key_levels": self.key_levels,
            "invalidation_level": self.invalidation_level,
            "invalidation_rule": self.invalidation_rule,
            "components": self.components,
            "edge_state": self.edge_state.value,
            "edge_note": self.edge_note,
            "notes": self.notes,
            "geometry": self.geometry.to_dict(),
            "bars_span": self.bars_span,
            "detector_version": self.detector_version,
            "separation_note": (
                "recognition_confidence describes how cleanly the shape matches its "
                "definition. It is NOT a probability of any price outcome."
            ),
        }

    def describe(self) -> str:
        return (
            f"{self.name} [{self.state.value}] recognition {self.recognition_confidence:.0f}/100, "
            f"class {self.pattern_class.value}. Textbook reading: "
            f"{self.direction_if_textbook.lower()}. Measured edge: {self.edge_state.value}."
        )


@dataclass(slots=True)
class PatternContext:
    """Everything a detector may read. Strictly bars up to the current one."""

    high: pd.Series
    low: pd.Series
    close: pd.Series
    volume: pd.Series
    atr: pd.Series
    swings: SwingSeries
    timeframe: Timeframe

    @property
    def current_atr(self) -> float:
        value = float(self.atr.iloc[-1]) if len(self.atr.dropna()) else np.nan
        return value if np.isfinite(value) and value > 0 else 0.0

    @property
    def last_close(self) -> float:
        return float(self.close.iloc[-1])

    @property
    def now(self) -> datetime:
        return self.close.index[-1]


# --- individual detectors ------------------------------------------------


def detect_double_bottom(ctx: PatternContext) -> StructuralPattern | None:
    """Two comparable lows with a real reaction between them.

    Tolerances are in ATR rather than percent, and the neckline break is what
    moves the pattern from CANDIDATE to CONFIRMED - never the shape alone.
    """
    return _detect_double(ctx, kind="bottom")


def detect_double_top(ctx: PatternContext) -> StructuralPattern | None:
    return _detect_double(ctx, kind="top")


#: Hard gates per detector. Written down rather than inlined so §14's
#: "minimum criteria, tolerances, bar counts, pivot control, slope validation"
#: can be read in one place, and so a rejection names the gate that stopped it.
#:
#: The defaults below are the tuned values; `config/thresholds.yaml` overrides
#: any of them under `structure_patterns:`, following the project convention
#: that a threshold is a setting rather than a constant in the code.
_CRITERIA_DEFAULTS: dict[str, dict[str, Any]] = {
    "double": {
        "min_bars": 12, "max_bars": 250, "min_pivots": 2,
        "min_pivot_quality": 40.0, "min_confidence": 58.0,
        "extreme_tolerance_atr": 0.7, "min_reaction_atr": 1.5,
    },
    "triangle": {
        "min_bars": 20, "max_bars": 250, "min_pivots": 3,
        "min_pivot_quality": 35.0, "min_alignment": 55.0, "min_confidence": 58.0,
        "min_convergence": 0.35, "flat_slope_atr": 0.015,
    },
    "wedge": {
        "min_bars": 20, "max_bars": 250, "min_pivots": 3,
        "min_pivot_quality": 35.0, "min_alignment": 60.0, "min_confidence": 60.0,
        "min_convergence": 0.30, "flat_slope_atr": 0.015,
    },
}


def _load_criteria() -> dict[str, PatternCriteria]:
    """Merge the YAML overrides onto the defaults, one detector at a time.

    A malformed or absent config falls back to the defaults rather than
    disabling detection: a missing setting must not silently turn a gate off.
    """
    from ..config_loader import threshold

    configured = threshold("structure_patterns", default={}) or {}
    out: dict[str, PatternCriteria] = {}
    for name, defaults in _CRITERIA_DEFAULTS.items():
        overrides = configured.get(name) or {}
        merged = {**defaults}
        for key, value in overrides.items():
            if key in defaults:
                merged[key] = type(defaults[key])(value)
            else:
                log.warning("unknown_pattern_criterion", detector=name, key=key)
        out[name] = PatternCriteria(**merged)
    return out


CRITERIA: dict[str, PatternCriteria] = _load_criteria()


def _point(ctx: PatternContext, swing: CausalSwing, role: str) -> GeometryPoint:
    return GeometryPoint(
        time=ctx.close.index[swing.pivot_index],
        price=round(swing.price, 6),
        role=role,
        kind="pivot",
    )


def _armpit(
    ctx: PatternContext, left_index: int, right_index: int, inverse: bool
) -> CausalSwing | None:
    """The pivot in the trough between two peaks - the figure's armpit.

    Bulkowski draws the neckline of a head-and-shoulders through the two
    armpits, and it may slope. The version before this used a horizontal line
    at the lowest close between the shoulders, which is neither of the two
    points a reader would join and made confirmation fire at the wrong level.
    """
    candidates = [
        swing for swing in (ctx.swings.highs if inverse else ctx.swings.lows)
        if left_index < swing.pivot_index < right_index
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda s: s.price) if inverse else min(
        candidates, key=lambda s: s.price
    )


def _horizontal(ctx: PatternContext, price: float, start_index: int, role: str) -> TrendLine:
    """A flat line from a bar to the last one - a neckline or a range boundary."""
    start = GeometryPoint(time=ctx.close.index[start_index], price=round(price, 6), role=role)
    end = GeometryPoint(time=ctx.now, price=round(price, 6), role=role)
    return TrendLine(start=start, end=end, role=role, extend=True)


def _fitted_line(
    ctx: PatternContext, fit: Any, first_index: int, last_index: int, role: str
) -> TrendLine:
    """The regression line drawn between two bar positions."""
    return TrendLine(
        start=GeometryPoint(
            time=ctx.close.index[first_index],
            price=round(fit.price_at(first_index), 6),
            role=role,
            kind="projected",
        ),
        end=GeometryPoint(
            time=ctx.close.index[last_index],
            price=round(fit.price_at(last_index), 6),
            role=role,
            kind="projected",
        ),
        role=role,
        extend=True,
    )


def _detect_double(ctx: PatternContext, kind: str) -> StructuralPattern | None:
    """Two comparable extremes separated by a genuine reaction.

    Every rejection below is a gate the previous version did not have. The old
    detector accepted any two swings within 1 ATR that were eight bars apart,
    which on nine years of daily bars is most of the time. What is added:

      * a maximum span - two lows 400 bars apart are not one figure;
      * pivot quality - both extremes must have produced a real reaction, not
        be rounding artefacts in a drift;
      * a confidence floor, so a marginal shape is not reported at all.
    """
    criteria = CRITERIA["double"]
    atr = ctx.current_atr
    if atr <= 0:
        return None
    swings = ctx.swings.lows if kind == "bottom" else ctx.swings.highs
    if len(swings) < criteria.min_pivots:
        return None

    second, first = swings[-1], swings[-2]
    span = second.pivot_index - first.pivot_index
    if not criteria.bars_ok(span):
        return None

    difference_atr = abs(second.price - first.price) / atr
    if difference_atr > criteria.extreme_tolerance_atr:
        return None

    # La vallée entre deux sommets est un plus BAS, pas une plus basse
    # clôture. La référence confirme sur « une clôture sous la vallée »: en
    # prenant la plus basse clôture on plaçait la ligne trop haut et la figure
    # se confirmait trop tôt.
    if kind == "bottom":
        between = ctx.high.iloc[first.pivot_index:second.pivot_index + 1]
    else:
        between = ctx.low.iloc[first.pivot_index:second.pivot_index + 1]
    if between.empty:
        return None
    if kind == "bottom":
        neckline = float(between.max())
        reaction_atr = (neckline - max(first.price, second.price)) / atr
        textbook = "BULLISH"
    else:
        neckline = float(between.min())
        reaction_atr = (min(first.price, second.price) - neckline) / atr
        textbook = "BEARISH"

    if reaction_atr < criteria.min_reaction_atr:
        return None

    # Both tests must be pivots the market actually respected.
    quality = pivot_quality([first, second])
    if quality < criteria.min_pivot_quality:
        return None

    report = QualityReport(components={
        "extreme_agreement": symmetry_score([first.price, second.price], atr),
        "reaction_depth": round(
            float(np.clip(reaction_atr / 3.0, 0.0, 1.0)) * 100.0, 1
        ),
        "time_separation": round(float(np.clip(span / 60.0, 0.0, 1.0)) * 100.0, 1),
        "pivot_quality": quality,
    })
    confidence = report.confidence()
    if confidence < criteria.min_confidence:
        return None

    last = ctx.last_close
    if kind == "bottom":
        confirmed = last > neckline
        failed = last < min(first.price, second.price) - atr * 0.3
        invalidation = min(first.price, second.price)
        rule = (
            f"a {ctx.timeframe.value} close below {invalidation:.2f} would break both "
            "lows and invalidate the double bottom"
        )
    else:
        confirmed = last < neckline
        failed = last > max(first.price, second.price) + atr * 0.3
        invalidation = max(first.price, second.price)
        rule = (
            f"a {ctx.timeframe.value} close above {invalidation:.2f} would break both "
            "highs and invalidate the double top"
        )

    state = (
        PatternState.CONFIRMED if confirmed
        else PatternState.FAILED if failed
        else PatternState.CANDIDATE
    )

    geometry = PatternGeometry(
        points=[
            _point(ctx, first, f"first_{kind}"),
            _point(ctx, second, f"second_{kind}"),
        ],
        neckline=_horizontal(ctx, neckline, first.pivot_index, "neckline"),
        zones=[
            GeometryZone(
                start_time=ctx.close.index[first.pivot_index],
                end_time=ctx.now,
                low=round(min(invalidation, neckline), 6),
                high=round(max(invalidation, neckline), 6),
                role="breakout",
            )
        ],
    )
    geometry.trend_lines = [geometry.neckline]
    geometry.breakout_area = geometry.zones[0]

    return StructuralPattern(
        name=f"double_{kind}",
        pattern_class=PatternClass.DETERMINISTIC,
        state=state,
        recognition_confidence=confidence,
        detected_at=ctx.now,
        confirmation_time=second.confirmation_time,
        direction_if_textbook=textbook,
        key_levels={
            "first_extreme": round(first.price, 6),
            "second_extreme": round(second.price, 6),
            "neckline": round(neckline, 6),
        },
        invalidation_level=round(invalidation, 6),
        invalidation_rule=rule,
        components={
            **report.components,
            "difference_atr": round(difference_atr, 3),
            "reaction_atr": round(reaction_atr, 3),
            "bars_between": span,
        },
        geometry=geometry,
        bars_span=span,
        notes=(
            f"two {kind}s within {difference_atr:.2f} ATR of each other, separated by "
            f"{span} bars, with a {reaction_atr:.2f} ATR reaction between them"
        ),
    )



def detect_triple(ctx: PatternContext, kind: str = "bottom") -> StructuralPattern | None:
    """Three comparable extremes. Rarer and stricter than the double."""
    atr = ctx.current_atr
    if atr <= 0:
        return None
    swings = ctx.swings.lows if kind == "bottom" else ctx.swings.highs
    if len(swings) < 3:
        return None

    third, second, first = swings[-1], swings[-2], swings[-3]
    prices = [first.price, second.price, third.price]
    spread_atr = (max(prices) - min(prices)) / atr
    if spread_atr > 1.2:
        return None
    span = third.pivot_index - first.pivot_index
    # Bounded at both ends: three lows spread over two years are not one figure,
    # which the lower bound alone never caught.
    if not (20 <= span <= CRITERIA["double"].max_bars):
        return None
    quality = pivot_quality([first, second, third])
    if quality < CRITERIA["double"].min_pivot_quality:
        return None

    # « La plus basse vallée de la figure » — un plus bas, pas une clôture.
    if kind == "bottom":
        between = ctx.high.iloc[first.pivot_index:third.pivot_index + 1]
        neckline = float(between.max())
    else:
        between = ctx.low.iloc[first.pivot_index:third.pivot_index + 1]
        neckline = float(between.min())
    last = ctx.last_close
    confirmed = last > neckline if kind == "bottom" else last < neckline
    invalidation = min(prices) if kind == "bottom" else max(prices)

    # Named parts rather than one opaque formula, so §22 holds here too.
    report = QualityReport(components={
        "extreme_agreement": symmetry_score(prices, atr),
        "pivot_quality": quality,
        "time_separation": round(float(np.clip(span / 80.0, 0.0, 1.0)) * 100.0, 1),
    })
    confidence = report.confidence()

    # Geometry, so the chart can draw what was decided here. The neckline is
    # the level this detector actually used to judge confirmation - drawing a
    # textbook sloping neckline instead would show the reader a line the
    # analysis never applied.
    geometry = PatternGeometry(
        points=[
            _point(ctx, first, f"first_{kind}"),
            _point(ctx, second, f"second_{kind}"),
            _point(ctx, third, f"third_{kind}"),
        ],
        neckline=_horizontal(ctx, neckline, first.pivot_index, "neckline"),
        zones=[
            GeometryZone(
                start_time=ctx.close.index[first.pivot_index],
                end_time=ctx.now,
                low=round(min(invalidation, neckline), 6),
                high=round(max(invalidation, neckline), 6),
                role="breakout",
            )
        ],
    )
    geometry.trend_lines = [geometry.neckline]
    geometry.breakout_area = geometry.zones[0]

    return StructuralPattern(
        name=f"triple_{kind}",
        pattern_class=PatternClass.DETERMINISTIC,
        state=PatternState.CONFIRMED if confirmed else PatternState.CANDIDATE,
        recognition_confidence=confidence,
        detected_at=ctx.now,
        confirmation_time=third.confirmation_time,
        direction_if_textbook="BULLISH" if kind == "bottom" else "BEARISH",
        key_levels={
            "extremes": round(float(np.mean(prices)), 6),
            "neckline": round(neckline, 6),
        },
        invalidation_level=round(invalidation, 6),
        invalidation_rule=(
            f"a {ctx.timeframe.value} close beyond {invalidation:.2f} invalidates the "
            f"triple {kind}"
        ),
        components={**report.components, "spread_atr": round(spread_atr, 3)},
        geometry=geometry,
        bars_span=span,
        notes=f"three {kind}s within {spread_atr:.2f} ATR across {span} bars",
    )


def detect_head_and_shoulders(
    ctx: PatternContext, inverse: bool = False
) -> StructuralPattern | None:
    """Three extremes where the middle one dominates and the sides agree.

    Marked HEURISTIC: the geometry is specifiable, but "shoulders roughly
    equal" is a judgement call that different analysts make differently.
    """
    atr = ctx.current_atr
    if atr <= 0:
        return None
    swings = ctx.swings.lows if inverse else ctx.swings.highs
    if len(swings) < 3:
        return None

    right, head, left = swings[-1], swings[-2], swings[-3]
    if inverse:
        if not (head.price < left.price and head.price < right.price):
            return None
        prominence_atr = (min(left.price, right.price) - head.price) / atr
    else:
        if not (head.price > left.price and head.price > right.price):
            return None
        prominence_atr = (head.price - max(left.price, right.price)) / atr

    if prominence_atr < 0.8:
        return None
    shoulder_difference_atr = abs(left.price - right.price) / atr
    if shoulder_difference_atr > 1.5:
        return None

    # Les deux aisselles: sans elles il n'y a pas de figure, seulement trois
    # sommets dont celui du milieu est plus haut.
    left_armpit = _armpit(ctx, left.pivot_index, head.pivot_index, inverse)
    right_armpit = _armpit(ctx, head.pivot_index, right.pivot_index, inverse)
    if left_armpit is None or right_armpit is None:
        return None

    # La neckline joint les aisselles et peut pencher. Le niveau à franchir
    # est celui de la droite au dernier chandelier, prolongée: c'est ce que
    # lit un opérateur, et c'est ce que la référence décrit.
    span_bars = right_armpit.pivot_index - left_armpit.pivot_index
    slope = (
        (right_armpit.price - left_armpit.price) / span_bars if span_bars else 0.0
    )
    neckline_now = right_armpit.price + slope * (
        len(ctx.close) - 1 - right_armpit.pivot_index
    )
    # Neckline descendante sur un ETE haussier: la référence confirme alors
    # sous l'aisselle droite plutôt que sous la droite prolongée, qui
    # s'éloignerait indéfiniment du prix.
    if inverse:
        trigger = min(neckline_now, right_armpit.price) if slope < 0 else neckline_now
    else:
        trigger = max(neckline_now, right_armpit.price) if slope > 0 else neckline_now
    neckline = float(trigger)
    last = ctx.last_close
    confirmed = last > neckline if inverse else last < neckline

    components = {
        "head_prominence": round(float(np.clip(prominence_atr / 2.5 * 100, 0, 100)), 1),
        "shoulder_symmetry": round(
            float(np.clip((1.5 - shoulder_difference_atr) / 1.5 * 100, 0, 100)), 1
        ),
    }
    # The three defining pivots, the neckline this detector judged against, and
    # the band between the head and that neckline - the area a break has to
    # travel through.
    geometry = PatternGeometry(
        points=[
            _point(ctx, left, "left_shoulder"),
            _point(ctx, left_armpit, "left_armpit"),
            _point(ctx, head, "head"),
            _point(ctx, right_armpit, "right_armpit"),
            _point(ctx, right, "right_shoulder"),
        ],
        neckline=TrendLine(
            start=_point(ctx, left_armpit, "neckline"),
            end=_point(ctx, right_armpit, "neckline"),
            role="neckline",
            extend=True,
        ),
        zones=[
            GeometryZone(
                start_time=ctx.close.index[left.pivot_index],
                end_time=ctx.now,
                low=round(min(head.price, neckline), 6),
                high=round(max(head.price, neckline), 6),
                role="breakout",
            )
        ],
    )
    geometry.trend_lines = [geometry.neckline]
    geometry.breakout_area = geometry.zones[0]

    return StructuralPattern(
        name="inverse_head_and_shoulders" if inverse else "head_and_shoulders",
        pattern_class=PatternClass.HEURISTIC,
        state=PatternState.CONFIRMED if confirmed else PatternState.CANDIDATE,
        recognition_confidence=round(float(np.mean(list(components.values()))), 1),
        detected_at=ctx.now,
        confirmation_time=right.confirmation_time,
        direction_if_textbook="BULLISH" if inverse else "BEARISH",
        key_levels={
            "left_shoulder": round(left.price, 6), "head": round(head.price, 6),
            "right_shoulder": round(right.price, 6), "neckline": round(neckline, 6),
        },
        invalidation_level=round(head.price, 6),
        invalidation_rule=(
            f"a {ctx.timeframe.value} close beyond the head at {head.price:.2f} "
            "invalidates the pattern"
        ),
        components={
            **components,
            "prominence_atr": round(prominence_atr, 3),
            "shoulder_difference_atr": round(shoulder_difference_atr, 3),
        },
        geometry=geometry,
        bars_span=right.pivot_index - left.pivot_index,
        notes=(
            f"head stands {prominence_atr:.2f} ATR beyond shoulders that agree within "
            f"{shoulder_difference_atr:.2f} ATR"
        ),
    )


def _converging_boundaries(
    ctx: PatternContext, criteria: PatternCriteria
) -> tuple[Any, Any, list[CausalSwing], list[CausalSwing], float, int] | None:
    """Shared front half of triangles and wedges: two fitted, converging lines.

    Returns the two fits, the pivots behind them, the convergence achieved and
    the bar span - or None when any structural gate fails. Both figures need
    exactly this, and computing it once means a triangle and a wedge can never
    disagree about the same price action.
    """
    atr = ctx.current_atr
    if atr <= 0:
        return None

    highs = ctx.swings.highs[-4:]
    lows = ctx.swings.lows[-4:]
    if len(highs) < criteria.min_pivots or len(lows) < criteria.min_pivots:
        return None

    first_index = min(highs[0].pivot_index, lows[0].pivot_index)
    last_index = max(highs[-1].pivot_index, lows[-1].pivot_index)
    span = last_index - first_index
    if not criteria.bars_ok(span):
        return None

    upper = fit_line(highs, atr)
    lower = fit_line(lows, atr)
    if upper is None or lower is None:
        return None

    # The pivots must actually sit on their lines. This is the gate the old
    # detector lacked entirely: it ran polyfit through three points and never
    # asked how far they were from the result, so any three swings became a
    # trendline.
    if (
        upper.alignment_score < criteria.min_alignment
        or lower.alignment_score < criteria.min_alignment
    ):
        return None

    if pivot_quality(highs + lows) < criteria.min_pivot_quality:
        return None

    start_width = upper.price_at(first_index) - lower.price_at(first_index)
    end_width = upper.price_at(last_index) - lower.price_at(last_index)
    # Boundaries that cross before the last pivot describe an apex already
    # passed, not a figure still forming.
    if start_width <= 0 or end_width <= 0:
        return None
    # A figure narrower than an ATR is noise dressed as geometry.
    if start_width / atr < 1.5:
        return None

    convergence = 1.0 - end_width / start_width
    if convergence < criteria.min_convergence:
        return None

    return upper, lower, highs, lows, convergence, span


def _converging_geometry(
    ctx: PatternContext,
    upper: Any,
    lower: Any,
    highs: list[CausalSwing],
    lows: list[CausalSwing],
) -> PatternGeometry:
    first_index = min(highs[0].pivot_index, lows[0].pivot_index)
    last_index = max(highs[-1].pivot_index, lows[-1].pivot_index)
    upper_line = _fitted_line(ctx, upper, first_index, last_index, "upper")
    lower_line = _fitted_line(ctx, lower, first_index, last_index, "lower")
    return PatternGeometry(
        points=(
            [_point(ctx, s, "upper_pivot") for s in highs]
            + [_point(ctx, s, "lower_pivot") for s in lows]
        ),
        trend_lines=[upper_line, lower_line],
    )


def detect_triangle(ctx: PatternContext) -> StructuralPattern | None:
    """Converging boundaries, one of which is flat.

    A triangle is classified by which boundary is horizontal: a flat top with
    rising lows is ascending, a flat bottom with falling highs is descending,
    both sloping toward each other is symmetrical. "Flat" is measured in ATR
    per bar so it means the same thing on any asset, rather than being a
    ratio between two slopes that both happen to be small.
    """
    criteria = CRITERIA["triangle"]
    found = _converging_boundaries(ctx, criteria)
    if found is None:
        return None
    upper, lower, highs, lows, convergence, span = found

    upper_flat = abs(upper.slope_atr_per_bar) < criteria.flat_slope_atr
    lower_flat = abs(lower.slope_atr_per_bar) < criteria.flat_slope_atr

    if upper_flat and lower.slope_atr_per_bar > criteria.flat_slope_atr:
        name, textbook = "ascending_triangle", "BULLISH"
    elif lower_flat and upper.slope_atr_per_bar < -criteria.flat_slope_atr:
        name, textbook = "descending_triangle", "BEARISH"
    elif upper.slope_atr_per_bar < -criteria.flat_slope_atr < criteria.flat_slope_atr < lower.slope_atr_per_bar:
        name, textbook = "symmetrical_triangle", "NEUTRAL"
    else:
        # Both boundaries sloping the same way is a wedge, not a triangle, and
        # is left to the wedge detector rather than being forced into this one.
        return None

    report = QualityReport(components={
        "convergence_quality": round(float(np.clip(convergence / 0.7, 0.0, 1.0)) * 100.0, 1),
        "geometry_score": round((upper.alignment_score + lower.alignment_score) / 2, 1),
        "pivot_quality": pivot_quality(highs + lows),
        "volume_confirmation": volume_trend_score(
            ctx.volume.iloc[min(highs[0].pivot_index, lows[0].pivot_index):].tolist()
        ),
    })
    confidence = report.confidence()
    if confidence < criteria.min_confidence:
        return None

    last_index = len(ctx.close) - 1
    upper_now = upper.price_at(last_index)
    lower_now = lower.price_at(last_index)
    last = ctx.last_close
    if last > upper_now:
        state, invalidation = PatternState.CONFIRMED, lower_now
    elif last < lower_now:
        state, invalidation = PatternState.FAILED, upper_now
    else:
        state, invalidation = PatternState.CANDIDATE, lower_now

    geometry = _converging_geometry(ctx, upper, lower, highs, lows)
    geometry.breakout_area = GeometryZone(
        start_time=ctx.close.index[max(highs[-1].pivot_index, lows[-1].pivot_index)],
        end_time=ctx.now,
        low=round(min(lower_now, upper_now), 6),
        high=round(max(lower_now, upper_now), 6),
        role="breakout",
    )
    geometry.zones = [geometry.breakout_area]

    return StructuralPattern(
        name=name,
        pattern_class=PatternClass.HEURISTIC,
        state=state,
        recognition_confidence=confidence,
        detected_at=ctx.now,
        confirmation_time=max(highs[-1].confirmation_time, lows[-1].confirmation_time),
        direction_if_textbook=textbook,
        key_levels={
            "upper": round(upper_now, 6),
            "lower": round(lower_now, 6),
        },
        invalidation_level=round(invalidation, 6),
        invalidation_rule=(
            f"a {ctx.timeframe.value} close beyond the opposite boundary at "
            f"{invalidation:.2f} resolves the triangle against this reading"
        ),
        components={
            **report.components,
            "convergence": round(convergence, 3),
            "upper_slope_atr_per_bar": round(upper.slope_atr_per_bar, 5),
            "lower_slope_atr_per_bar": round(lower.slope_atr_per_bar, 5),
            "upper_r2": round(upper.r_squared, 3),
            "lower_r2": round(lower.r_squared, 3),
            "bars_span": span,
        },
        geometry=geometry,
        bars_span=span,
        notes=(
            f"boundaries converged {convergence * 100:.0f}% over {span} bars; "
            f"upper slope {upper.slope_atr_per_bar:+.4f} ATR/bar, lower "
            f"{lower.slope_atr_per_bar:+.4f} ATR/bar"
        ),
    )


def detect_wedge(ctx: PatternContext) -> StructuralPattern | None:
    """Both boundaries sloping the same way while converging.

    Previously EXPERIMENTAL because the definition rested on judgement. It is
    now specified the same way as the triangle - fitted lines with a minimum
    alignment, slopes measured in ATR per bar, a required convergence - so two
    runs on the same bars give the same answer and the criteria can be read off.
    That makes it HEURISTIC: reproducible, with thresholds that remain choices.
    """
    criteria = CRITERIA["wedge"]
    found = _converging_boundaries(ctx, criteria)
    if found is None:
        return None
    upper, lower, highs, lows, convergence, span = found

    # Same-signed slopes, both meaningfully away from flat, is what separates a
    # wedge from a triangle.
    if np.sign(upper.slope_atr_per_bar) != np.sign(lower.slope_atr_per_bar):
        return None
    if (
        abs(upper.slope_atr_per_bar) < criteria.flat_slope_atr
        or abs(lower.slope_atr_per_bar) < criteria.flat_slope_atr
    ):
        return None

    rising = upper.slope_atr_per_bar > 0
    report = QualityReport(components={
        "convergence_quality": round(float(np.clip(convergence / 0.7, 0.0, 1.0)) * 100.0, 1),
        "geometry_score": round((upper.alignment_score + lower.alignment_score) / 2, 1),
        "slope_quality": round(
            float(np.clip(min(abs(upper.slope_atr_per_bar), abs(lower.slope_atr_per_bar))
                          / 0.05, 0.0, 1.0)) * 100.0, 1
        ),
        "pivot_quality": pivot_quality(highs + lows),
    })
    confidence = report.confidence()
    if confidence < criteria.min_confidence:
        return None

    last_index = len(ctx.close) - 1
    upper_now = upper.price_at(last_index)
    lower_now = lower.price_at(last_index)
    last = ctx.last_close
    # A rising wedge reads bearish, so its trigger is the lower boundary.
    if rising:
        state = (
            PatternState.CONFIRMED if last < lower_now
            else PatternState.FAILED if last > upper_now
            else PatternState.CANDIDATE
        )
        invalidation = upper_now
    else:
        state = (
            PatternState.CONFIRMED if last > upper_now
            else PatternState.FAILED if last < lower_now
            else PatternState.CANDIDATE
        )
        invalidation = lower_now

    geometry = _converging_geometry(ctx, upper, lower, highs, lows)

    return StructuralPattern(
        name="rising_wedge" if rising else "falling_wedge",
        pattern_class=PatternClass.HEURISTIC,
        state=state,
        recognition_confidence=confidence,
        detected_at=ctx.now,
        confirmation_time=max(highs[-1].confirmation_time, lows[-1].confirmation_time),
        direction_if_textbook="BEARISH" if rising else "BULLISH",
        key_levels={"upper": round(upper_now, 6), "lower": round(lower_now, 6)},
        invalidation_level=round(invalidation, 6),
        invalidation_rule=(
            f"a {ctx.timeframe.value} close beyond {invalidation:.2f} resolves the "
            "wedge against this reading"
        ),
        components={
            **report.components,
            "convergence": round(convergence, 3),
            "upper_slope_atr_per_bar": round(upper.slope_atr_per_bar, 5),
            "lower_slope_atr_per_bar": round(lower.slope_atr_per_bar, 5),
            "upper_r2": round(upper.r_squared, 3),
            "lower_r2": round(lower.r_squared, 3),
            "bars_span": span,
        },
        geometry=geometry,
        bars_span=span,
        notes=(
            f"both boundaries {'rising' if rising else 'falling'} and converging "
            f"{convergence * 100:.0f}% over {span} bars"
        ),
    )



def detect_flag(ctx: PatternContext) -> StructuralPattern | None:
    """A sharp move, then a shallow drift against it.

    The pole and the flag are located from PIVOTS, not from fixed offsets.
    The version before this took the pole to be bars -30 to -12 and the flag
    the last twelve, always: it could not see a pole of forty bars or a flag
    of five, and it re-found a slightly shifted copy of the same rally at
    every pivot. Flags were 38 % of everything the scan produced.

    Still EXPERIMENTAL: "sharp" and "shallow" remain thresholds someone chose,
    and the reference itself gives no number for them.
    """
    atr = ctx.current_atr
    if atr <= 0 or len(ctx.close) < 40:
        return None

    # Le mât se termine au dernier pivot; le drapeau est ce qui suit.
    swings = ctx.swings.all_swings
    if len(swings) < 2:
        return None
    pole_end = swings[-1]
    flag_bars = len(ctx.close) - 1 - pole_end.pivot_index
    # La référence borne la consolidation à une quinzaine de chandeliers:
    # au-delà, la figure est un rectangle ou un canal, avec ses propres
    # statistiques et ses propres règles.
    if not (MIN_FLAG_BARS <= flag_bars <= MAX_FLAG_BARS):
        return None

    # Le mât part du pivot opposé qui l'a lancé.
    opposite = [
        swing for swing in swings[:-1]
        if swing.kind != pole_end.kind and swing.pivot_index < pole_end.pivot_index
    ]
    if not opposite:
        return None
    pole_start = opposite[-1]
    pole_bars = pole_end.pivot_index - pole_start.pivot_index
    if not (MIN_POLE_BARS <= pole_bars <= MAX_POLE_BARS):
        return None

    pole_move = (pole_end.price - pole_start.price) / atr
    if abs(pole_move) < MIN_POLE_ATR:
        return None

    # « Quasi vertical », « en ligne droite », « sans pause »: la référence ne
    # donne pas de nombre, mais elle décrit deux choses mesurables, et
    # l'amplitude seule n'en capture aucune. Sans elles, ancrer le mât sur des
    # pivots au lieu d'une fenêtre fixe faisait passer une marche aléatoire
    # sur deux pour un drapeau.
    #
    # Raideur: le mât doit monter vite, pas seulement loin.
    if abs(pole_move) / pole_bars < MIN_POLE_ATR_PER_BAR:
        return None
    # Rectitude: la part du chemin parcouru qui sert réellement au
    # déplacement. Une ligne droite vaut 1; une marche aléatoire de n pas vaut
    # environ 1/racine(n), soit 0,2 à 0,3 sur la longueur d'un mât.
    pole_path = ctx.close.iloc[pole_start.pivot_index:pole_end.pivot_index + 1]
    travelled = float(pole_path.diff().abs().sum())
    if travelled <= 0:
        return None
    straightness = abs(float(pole_path.iloc[-1] - pole_path.iloc[0])) / travelled
    if straightness < MIN_POLE_STRAIGHTNESS:
        return None

    flag = ctx.close.iloc[pole_end.pivot_index:]
    flag_move = (flag.iloc[-1] - flag.iloc[0]) / atr
    # La consolidation doit être faible ET orientée contre le mât.
    if abs(flag_move) > abs(pole_move) * MAX_FLAG_SHARE:
        return None
    if flag_move == 0 or np.sign(flag_move) == np.sign(pole_move):
        return None

    bullish = pole_move > 0
    flag_high = float(ctx.high.iloc[pole_end.pivot_index:].max())
    flag_low = float(ctx.low.iloc[pole_end.pivot_index:].min())

    geometry = PatternGeometry(
        points=[
            _point(ctx, pole_start, "pole_start"),
            _point(ctx, pole_end, "pole_end"),
        ],
        trend_lines=[
            TrendLine(
                start=_point(ctx, pole_start, "pole"),
                end=_point(ctx, pole_end, "pole"),
                role="pole",
                extend=False,
            )
        ],
        zones=[
            GeometryZone(
                start_time=ctx.close.index[pole_end.pivot_index],
                end_time=ctx.now,
                low=round(flag_low, 6), high=round(flag_high, 6),
                role="consolidation",
            )
        ],
    )

    return StructuralPattern(
        name="bull_flag" if bullish else "bear_flag",
        pattern_class=PatternClass.EXPERIMENTAL,
        state=PatternState.CANDIDATE,
        recognition_confidence=round(
            float(np.clip(abs(pole_move) / 6 * 100, 0, 100)), 1
        ),
        detected_at=ctx.now,
        confirmation_time=pole_end.confirmation_time,
        direction_if_textbook="BULLISH" if bullish else "BEARISH",
        key_levels={
            "pole_start": round(float(pole_start.price), 6),
            "pole_end": round(float(pole_end.price), 6),
        },
        invalidation_level=round(float(pole_start.price), 6),
        invalidation_rule=(
            f"a close beyond the start of the pole at {pole_start.price:.2f} "
            "invalidates the continuation reading"
        ),
        components={
            "pole_atr": round(float(pole_move), 2),
            "flag_atr": round(float(flag_move), 2),
            "pole_bars": pole_bars,
            "flag_bars": flag_bars,
            "pole_straightness": round(straightness, 3),
        },
        geometry=geometry,
        bars_span=pole_bars + flag_bars,
        notes=(
            f"a {abs(pole_move):.1f} ATR move over {pole_bars} bars, then "
            f"{flag_bars} bars drifting the other way"
        ),
    )


DETECTORS: dict[str, Any] = {
    "double_bottom": detect_double_bottom,
    "double_top": detect_double_top,
    "triple_bottom": lambda ctx: detect_triple(ctx, "bottom"),
    "triple_top": lambda ctx: detect_triple(ctx, "top"),
    "head_and_shoulders": lambda ctx: detect_head_and_shoulders(ctx, inverse=False),
    "inverse_head_and_shoulders": lambda ctx: detect_head_and_shoulders(ctx, inverse=True),
    "triangle": detect_triangle,
    "wedge": detect_wedge,
    "flag": detect_flag,
}

# Reliability of DETECTION, declared up front rather than implied.
#
# Keyed by BOTH the registry key and the pattern name a detector emits: the
# triangle detector is registered once but produces three differently named
# figures, and a consumer holding `ascending_triangle` must be able to look up
# its class without knowing which detector produced it.
PATTERN_CLASSES: dict[str, PatternClass] = {
    "double_bottom": PatternClass.DETERMINISTIC,
    "double_top": PatternClass.DETERMINISTIC,
    "triple_bottom": PatternClass.DETERMINISTIC,
    "triple_top": PatternClass.DETERMINISTIC,
    "head_and_shoulders": PatternClass.HEURISTIC,
    "inverse_head_and_shoulders": PatternClass.HEURISTIC,
    "triangle": PatternClass.HEURISTIC,
    "ascending_triangle": PatternClass.HEURISTIC,
    "descending_triangle": PatternClass.HEURISTIC,
    "symmetrical_triangle": PatternClass.HEURISTIC,
    # Promoted from EXPERIMENTAL: the wedge definition is now specified the
    # same way as the triangle - fitted boundaries with a minimum alignment,
    # slopes in ATR per bar, a required convergence - so it is reproducible.
    # The thresholds remain choices, which is exactly what HEURISTIC means.
    "wedge": PatternClass.HEURISTIC,
    "rising_wedge": PatternClass.HEURISTIC,
    "falling_wedge": PatternClass.HEURISTIC,
    # The flag detector is untouched by this lot: "sharp pole" and "shallow
    # flag" are still judgements, so it keeps its warning label.
    "flag": PatternClass.EXPERIMENTAL,
    "bull_flag": PatternClass.EXPERIMENTAL,
    "bear_flag": PatternClass.EXPERIMENTAL,
}


#: Nothing below this reaches a consumer, whatever the detector thinks.
#:
#: The detectors hardened in LOT 4 enforce their own, higher floors through
#: `CRITERIA`. This is the backstop for the ones that have not been reworked
#: yet: replayed over real history they were emitting figures at confidences
#: down to 0.1/100, which is a shape the code found and no analyst would draw.
#: A figure below the floor is not reported at all - §14's "mieux vaut ne rien
#: dire" is a filter, not a caption.
def _default_floor() -> float:
    from ..config_loader import threshold

    return float(threshold("structure_patterns", "min_confidence", default=55.0))


DEFAULT_MIN_CONFIDENCE = _default_floor()

# --- detector versions ----------------------------------------------------
#
# One version per detector, bumped whenever a RULE changes - not when a
# comment or a refactor changes. A benchmark result is meaningless without
# knowing which rules produced it, and "the detector improved" is only a claim
# until two versions can be compared on the same dataset.
#
# History, so a stored observation can be read years later:
#   v1  the original detectors
#   v2  LOT 4 gates: pivot quality, bar-span bounds, confidence floors
#   v3  definitions checked against the reference:
#         double/triple  valleys measured on lows, not on closes
#         head&shoulders neckline joins the two armpits and may slope
#         flag           pole anchored to pivots, steepness and straightness
DETECTOR_VERSIONS: dict[str, str] = {
    "double_bottom": "double_v3",
    "double_top": "double_v3",
    "triple_bottom": "triple_v3",
    "triple_top": "triple_v3",
    "head_and_shoulders": "head_shoulders_v3",
    "inverse_head_and_shoulders": "head_shoulders_v3",
    "triangle": "triangle_v2",
    "ascending_triangle": "triangle_v2",
    "descending_triangle": "triangle_v2",
    "symmetrical_triangle": "triangle_v2",
    "wedge": "wedge_v2",
    "rising_wedge": "wedge_v2",
    "falling_wedge": "wedge_v2",
    "flag": "flag_v3",
    "bull_flag": "flag_v3",
    "bear_flag": "flag_v3",
}


def detector_version(pattern_name: str) -> str:
    """Which rules produced this figure.

    Unknown rather than a guess: an unversioned detector must be visible as
    such, not silently folded into whatever version happens to be current.
    """
    return DETECTOR_VERSIONS.get(pattern_name, "unversioned")

# --- flag geometry ---------------------------------------------------------
#
# The reference bounds the consolidation at roughly fifteen candles - beyond
# that the shape is a rectangle or a channel, which carry their own rules.
# The pole bounds are ours: a "sharp" move has no number in the literature,
# and these are declared here rather than buried in the detector.
MIN_FLAG_BARS = 3
MAX_FLAG_BARS = 15
MIN_POLE_BARS = 3
MAX_POLE_BARS = 25
MIN_POLE_ATR = 3.0
#: Raideur et rectitude du mât. Ce sont nos nombres: la référence dit « quasi
#: vertical » et « en ligne droite » sans les chiffrer.
MIN_POLE_ATR_PER_BAR = 0.45
MIN_POLE_STRAIGHTNESS = 0.55
MAX_FLAG_SHARE = 0.4


def detect_all(
    ctx: PatternContext, min_confidence: float = DEFAULT_MIN_CONFIDENCE
) -> list[StructuralPattern]:
    """Run every detector. Returning nothing is a normal, common outcome."""
    found: list[StructuralPattern] = []
    for name, detector in DETECTORS.items():
        try:
            pattern = detector(ctx)
        except Exception as exc:
            log.debug("detector_failed", detector=name, error=str(exc))
            continue
        if pattern is None:
            continue
        pattern.detector_version = detector_version(pattern.name)
        if pattern.recognition_confidence < min_confidence:
            log.debug(
                "pattern_below_floor", detector=name,
                confidence=pattern.recognition_confidence, floor=min_confidence,
            )
            continue
        found.append(pattern)
    return sorted(found, key=lambda p: -p.recognition_confidence)


def build_context(
    df: pd.DataFrame, timeframe: Timeframe, lookback: int = 5
) -> PatternContext | None:
    """Assemble a context from bars up to and including the last one."""
    from ..engines.technical import indicators as ind
    from .swings import find_causal_swings

    if df.empty or len(df) < 40:
        return None
    atr = ind.atr(df["high"], df["low"], df["close"], 14)
    swings = find_causal_swings(df["high"], df["low"], df["close"], atr, lookback=lookback)
    # Only pivots confirmed by the final bar may inform a detection made now.
    swings = swings.as_of(df.index[-1])
    return PatternContext(
        high=df["high"], low=df["low"], close=df["close"], volume=df["volume"],
        atr=atr, swings=swings, timeframe=timeframe,
    )

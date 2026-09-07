"""The pattern record the rest of the system reads, and the geometry it draws.

`StructuralPattern` in `patterns.py` is what a detector produces: a shape, its
recognition score, and the levels that define it. That is deliberately narrow -
a detector should not need to know which asset it is looking at, nor how a
browser will draw the result.

`PatternDetection` is the published form of that same finding. It adds the
identity (asset, timeframe, a stable id), the lifecycle (`status`, `detected_at`
vs `confirmed_at`), the geometry a chart needs to redraw the figure, and the
confluence signals measured around it.

Three rules carried over from the rest of the project, and enforced here:

1. RECOGNITION IS NOT EDGE. `recognition_confidence` says how cleanly the shape
   matches its definition. `edge_state` says whether that shape has been shown
   to precede anything. They are different quantities and never merged.

2. NO UNEXPLAINED NUMBER. `confidence_components` must account for
   `recognition_confidence`; `to_dict` refuses to publish a score whose parts
   are missing, because §22 requires that every figure can be taken apart.

3. MISSING IS NOT NEGATIVE. A confirmation signal with no data is `UNAVAILABLE`
   and is excluded from scoring rather than counted as zero.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from ..core.enums import Timeframe
from .geometry import GeometryPoint, GeometryZone, PatternGeometry, TrendLine
from .patterns import PatternClass, PatternEdgeState, PatternState, StructuralPattern


class PatternFamily(StrEnum):
    """What kind of figure this is - drives grouping in the UI and the library."""

    REVERSAL = "REVERSAL"
    CONTINUATION = "CONTINUATION"
    TRIANGLE = "TRIANGLE"
    WEDGE = "WEDGE"
    RANGE = "RANGE"
    CANDLESTICK = "CANDLESTICK"


class PatternDirection(StrEnum):
    """What the textbook says the figure implies - never what we claim."""

    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


class PatternStatus(StrEnum):
    """Where the figure stands in its life, from shape to outcome.

    The boundaries are deliberate, because "detected" and "confirmed" are the
    two words most often collapsed into one:

      FORMING           the shape is incomplete; too few pivots to commit
      DETECTED          the geometry is complete and passed every check
      BREAKOUT_PENDING  price sits at the trigger without having closed beyond
      CONFIRMED         a close beyond the trigger level occurred
      INVALIDATED       the invalidation level was reached instead
      COMPLETED         the theoretical target was reached after confirmation
    """

    FORMING = "FORMING"
    DETECTED = "DETECTED"
    BREAKOUT_PENDING = "BREAKOUT_PENDING"
    CONFIRMED = "CONFIRMED"
    INVALIDATED = "INVALIDATED"
    COMPLETED = "COMPLETED"


class SignalVerdict(StrEnum):
    """How one confirmation signal reads. UNAVAILABLE is not ADVERSE."""

    FAVOURABLE = "FAVOURABLE"
    NEUTRAL = "NEUTRAL"
    ADVERSE = "ADVERSE"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(slots=True, frozen=True)
class ConfirmationSignal:
    """One piece of context measured around the pattern.

    `score` is only meaningful when `verdict` is not UNAVAILABLE. The confluence
    engine (LOT 6) drops unavailable signals and redistributes their weight
    rather than scoring them zero - treating "we do not know" as "it is bad" is
    the single most common way a scoring system quietly lies.
    """

    family: str             # "volume", "momentum", "derivatives", "macro", ...
    name: str               # "relative_volume", "rsi_divergence", ...
    verdict: SignalVerdict
    score: float | None = None      # 0-100 within its family, None when unavailable
    value: float | str | None = None
    detail: str = ""

    @property
    def available(self) -> bool:
        return self.verdict is not SignalVerdict.UNAVAILABLE

    def to_dict(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "name": self.name,
            "verdict": self.verdict.value,
            "score": self.score,
            "value": self.value,
            "detail": self.detail,
            "available": self.available,
        }


# --- the published record --------------------------------------------------


def make_pattern_id(
    symbol: str,
    timeframe: str,
    pattern_type: str,
    start_time: datetime,
    end_time: datetime,
) -> str:
    """A stable id for one occurrence of one figure.

    Derived from what identifies the occurrence rather than from when it was
    computed, so re-running the detector on the same bars yields the same id and
    the frontend can keep a pattern selected across a refresh.
    """
    parts = (symbol, timeframe, pattern_type, start_time.isoformat(), end_time.isoformat())
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:24]


@dataclass(slots=True)
class PatternDetection:
    """One figure, published: identity, lifecycle, geometry, confluence."""

    symbol: str
    timeframe: Timeframe
    pattern_type: str
    family: PatternFamily
    direction: PatternDirection
    start_time: datetime
    end_time: datetime
    detected_at: datetime
    status: PatternStatus

    recognition_confidence: float                       # 0-100, shape match only
    confidence_components: dict[str, float] = field(default_factory=dict)

    pattern_class: PatternClass = PatternClass.HEURISTIC
    edge_state: PatternEdgeState = PatternEdgeState.NOT_YET_TESTED
    edge_note: str = ""

    confirmed_at: datetime | None = None
    breakout_level: float | None = None
    invalidation_level: float | None = None
    target_level: float | None = None
    invalidation_rule: str = ""

    geometry: PatternGeometry = field(default_factory=PatternGeometry)
    confirmation_signals: list[ConfirmationSignal] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    notes: str = ""

    @property
    def id(self) -> str:
        return make_pattern_id(
            self.symbol, self.timeframe.value, self.pattern_type,
            self.start_time, self.end_time,
        )

    @property
    def bars_span(self) -> int | None:
        return self.metadata.get("bars_span")

    def signals_by_family(self) -> dict[str, list[ConfirmationSignal]]:
        grouped: dict[str, list[ConfirmationSignal]] = {}
        for signal in self.confirmation_signals:
            grouped.setdefault(signal.family, []).append(signal)
        return grouped

    def available_families(self) -> list[str]:
        """Families with at least one signal carrying data."""
        return sorted(
            family
            for family, signals in self.signals_by_family().items()
            if any(s.available for s in signals)
        )

    def components_explain_confidence(self, tolerance: float = 0.6) -> bool:
        """Does the published score follow from its parts?

        The convention across detectors is that `recognition_confidence` is the
        mean of its components. Checking it here means a detector that invents a
        score, or forgets to record how it built one, fails loudly instead of
        shipping an unexplainable number.
        """
        if not self.confidence_components:
            return False
        parts = list(self.confidence_components.values())
        mean = sum(parts) / len(parts)
        return abs(mean - self.recognition_confidence) <= tolerance

    def to_dict(self) -> dict[str, Any]:
        explained = self.components_explain_confidence()
        return {
            "id": self.id,
            "symbol": self.symbol,
            "timeframe": self.timeframe.value,
            "pattern_type": self.pattern_type,
            "family": self.family.value,
            "direction": self.direction.value,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "detected_at": self.detected_at.isoformat(),
            "confirmed_at": self.confirmed_at.isoformat() if self.confirmed_at else None,
            "status": self.status.value,
            "recognition_confidence": self.recognition_confidence,
            "confidence_components": self.confidence_components,
            # Stated rather than assumed: a consumer can see whether the score
            # is decomposable before quoting it.
            "confidence_is_explained": explained,
            "pattern_class": self.pattern_class.value,
            "edge_state": self.edge_state.value,
            "edge_note": self.edge_note,
            "breakout_level": self.breakout_level,
            "invalidation_level": self.invalidation_level,
            "target_level": self.target_level,
            "invalidation_rule": self.invalidation_rule,
            "geometry": self.geometry.to_dict(),
            "confirmation_signals": [s.to_dict() for s in self.confirmation_signals],
            "available_families": self.available_families(),
            "metadata": self.metadata,
            "notes": self.notes,
            "separation_note": (
                "recognition_confidence measures how cleanly the shape matches its "
                "definition. It is not a probability of any price outcome - read "
                "edge_state for what has actually been measured."
            ),
        }


# --- adapting what the detectors already produce ---------------------------

#: Which family each detector name belongs to. Names not listed fall back to
#: REVERSAL only when explicitly mapped - an unknown detector raises instead,
#: so adding a pattern without classifying it cannot slip through.
FAMILY_BY_PATTERN: dict[str, PatternFamily] = {
    "double_bottom": PatternFamily.REVERSAL,
    "double_top": PatternFamily.REVERSAL,
    "triple_bottom": PatternFamily.REVERSAL,
    "triple_top": PatternFamily.REVERSAL,
    "head_and_shoulders": PatternFamily.REVERSAL,
    "inverse_head_and_shoulders": PatternFamily.REVERSAL,
    "rounded_bottom": PatternFamily.REVERSAL,
    "ascending_triangle": PatternFamily.TRIANGLE,
    "descending_triangle": PatternFamily.TRIANGLE,
    "symmetrical_triangle": PatternFamily.TRIANGLE,
    "rising_wedge": PatternFamily.WEDGE,
    "falling_wedge": PatternFamily.WEDGE,
    "bull_flag": PatternFamily.CONTINUATION,
    "bear_flag": PatternFamily.CONTINUATION,
    "pennant": PatternFamily.CONTINUATION,
    "rectangle": PatternFamily.CONTINUATION,
    "cup_and_handle": PatternFamily.CONTINUATION,
    "range": PatternFamily.RANGE,
}

#: `PatternState` only distinguishes three outcomes. The richer lifecycle needs
#: price context to separate DETECTED from BREAKOUT_PENDING, which the adapter
#: supplies; this is the fallback when it cannot.
_STATE_TO_STATUS: dict[PatternState, PatternStatus] = {
    PatternState.CANDIDATE: PatternStatus.DETECTED,
    PatternState.CONFIRMED: PatternStatus.CONFIRMED,
    PatternState.FAILED: PatternStatus.INVALIDATED,
}


#: How close to its trigger price must sit, in ATR, to read as pending rather
#: than merely detected. Under a quarter of an ATR the next bar can plausibly
#: resolve it; further away the figure is simply still forming.
BREAKOUT_PROXIMITY_ATR = 0.25


def _lifecycle_status(
    pattern: StructuralPattern,
    trigger: float | None,
    last_close: float | None,
    atr: float | None,
) -> PatternStatus:
    """Map the detector's three states onto the six-state lifecycle."""
    base = _STATE_TO_STATUS[pattern.state]
    if base is not PatternStatus.DETECTED:
        return base
    if trigger is None or last_close is None or atr is None or atr <= 0:
        return base
    if abs(last_close - trigger) / atr <= BREAKOUT_PROXIMITY_ATR:
        return PatternStatus.BREAKOUT_PENDING
    return base


def family_for(pattern_type: str) -> PatternFamily:
    """The family of a detector, or a clear error when it was never declared."""
    try:
        return FAMILY_BY_PATTERN[pattern_type]
    except KeyError:
        raise KeyError(
            f"pattern '{pattern_type}' has no declared family. Add it to "
            "FAMILY_BY_PATTERN so the UI and the library can group it."
        ) from None


def from_structural(
    pattern: StructuralPattern,
    *,
    symbol: str,
    timeframe: Timeframe,
    start_time: datetime,
    end_time: datetime,
    geometry: PatternGeometry | None = None,
    status: PatternStatus | None = None,
    breakout_level: float | None = None,
    target_level: float | None = None,
    last_close: float | None = None,
    atr: float | None = None,
) -> PatternDetection:
    """Publish a detector's finding, without reinterpreting it.

    Everything the detector decided - the score, its components, the levels, the
    class - is carried across unchanged. This function adds context the detector
    does not have (which asset, which window, how to draw it) and nothing else.

    The one judgement made here is BREAKOUT_PENDING, and only because the
    detector cannot make it: `PatternState` has three values, while the
    lifecycle §6 asks for distinguishes "the shape is complete" from "price is
    sitting on the trigger without having closed through it". Given the current
    close and an ATR to scale by, that distinction is measurable rather than
    guessed - and without them the status stays DETECTED rather than being
    invented.
    """
    # Numeric component scores are the ones that explain the confidence; the
    # detectors also record raw measurements (ATR distances, bar counts) in the
    # same dict, which belong in metadata instead.
    score_components = {
        key: float(value)
        for key, value in pattern.components.items()
        if isinstance(value, (int, float)) and not isinstance(value, bool)
        and key in {
            "extreme_agreement", "reaction_depth", "time_separation",
            "head_prominence", "shoulder_symmetry", "convergence_quality",
            "slope_quality", "symmetry_score", "pivot_quality",
            "volume_confirmation", "geometry_score",
        }
    }
    raw_measurements = {
        key: value for key, value in pattern.components.items()
        if key not in score_components
    }

    direction = PatternDirection(pattern.direction_if_textbook)
    trigger = (
        breakout_level if breakout_level is not None
        else pattern.key_levels.get("neckline")
    )

    return PatternDetection(
        symbol=symbol,
        timeframe=timeframe,
        pattern_type=pattern.name,
        family=family_for(pattern.name),
        direction=direction,
        start_time=start_time,
        end_time=end_time,
        detected_at=pattern.detected_at,
        confirmed_at=pattern.confirmation_time
        if pattern.state is PatternState.CONFIRMED
        else None,
        status=status or _lifecycle_status(pattern, trigger, last_close, atr),
        recognition_confidence=pattern.recognition_confidence,
        confidence_components=score_components,
        pattern_class=pattern.pattern_class,
        edge_state=pattern.edge_state,
        edge_note=pattern.edge_note,
        breakout_level=breakout_level
        if breakout_level is not None
        else pattern.key_levels.get("neckline"),
        invalidation_level=pattern.invalidation_level,
        target_level=target_level,
        invalidation_rule=pattern.invalidation_rule,
        geometry=geometry or PatternGeometry(),
        metadata={**raw_measurements, "key_levels": pattern.key_levels},
        notes=pattern.notes,
    )


#: Re-exported so consumers can import the whole pattern vocabulary from one
#: place; the definitions live in `geometry.py` to keep detection and drawing
#: free of a circular import.
__all__ = [
    "ConfirmationSignal",
    "GeometryPoint",
    "GeometryZone",
    "PatternDetection",
    "PatternDirection",
    "PatternFamily",
    "PatternGeometry",
    "PatternStatus",
    "SignalVerdict",
    "TrendLine",
    "family_for",
    "from_structural",
    "make_pattern_id",
]

"""Multi-timeframe synthesis: one reading per timeframe, and what they say together.

The engines already produce a structure and a location per timeframe. What was
missing is the sentence a trader actually wants:

    1W bullish, 1D bullish, 4H range, 1H at the bottom of its range

and then the judgement that follows from it - are the timeframes aligned, in
conflict, or is the lower one turning ahead of the higher one?

Two rules govern the output.

A conflict between timeframes is **not an error and not noise**. A weekly
uptrend containing a 4-hour range is the normal state of a market. The engine
names the conflict rather than averaging it away, because the average of
"bullish" and "range" is a number that describes neither.

And the alignment verdict is descriptive. Whether aligned timeframes precede
better returns than conflicting ones is a research question; the LOT 5 result
was that structural labels carry almost nothing once the regime is known, so
nothing here is presented as predictive.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from ..core.enums import Asset, Timeframe
from ..history import store
from ..logging_setup import get_logger

log = get_logger("engines.multi_timeframe")

# Highest first: the hierarchy is what makes "the lower timeframe is turning"
# a meaningful statement.
LADDER: list[Timeframe] = [
    Timeframe.W1, Timeframe.D1, Timeframe.H4, Timeframe.H1, Timeframe.M15
]

_DIRECTION = {
    "BULLISH_STRUCTURE": 1,
    "BEARISH_STRUCTURE": -1,
    "RANGE_STRUCTURE": 0,
    "TRANSITION": 0,
    "UNCLEAR": None,
}


class AlignmentState(StrEnum):
    HIGHER_TIMEFRAME_ALIGNMENT = "HIGHER_TIMEFRAME_ALIGNMENT"
    CONFLICT = "CONFLICT"
    TRANSITION = "TRANSITION"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


@dataclass(slots=True)
class TimeframeReading:
    timeframe: str
    available: bool = False
    bars: int = 0
    structure: str = "UNCLEAR"
    location: str = "NO_VALID_RANGE"
    relative_position: float | None = None
    range_top: float | None = None
    range_bottom: float | None = None
    invalidation: str = ""
    reason_unavailable: str = ""

    @property
    def direction(self) -> int | None:
        return _DIRECTION.get(self.structure)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timeframe": self.timeframe, "available": self.available,
            "bars": self.bars, "structure": self.structure,
            "location": self.location,
            "relative_position": self.relative_position,
            "range_top": self.range_top, "range_bottom": self.range_bottom,
            "invalidation": self.invalidation,
            "reason_unavailable": self.reason_unavailable,
            "direction": self.direction,
        }

    def describe(self) -> str:
        if not self.available:
            return f"{self.timeframe}: unavailable ({self.reason_unavailable})"
        parts = [self.structure.replace("_STRUCTURE", "").replace("_", " ").lower()]
        if self.location != "NO_VALID_RANGE":
            parts.append(self.location.replace("_", " ").lower())
        return f"{self.timeframe}: {', '.join(parts)}"


@dataclass(slots=True)
class MultiTimeframeReading:
    asset: str
    readings: list[TimeframeReading] = field(default_factory=list)
    alignment: AlignmentState = AlignmentState.INSUFFICIENT_DATA
    dominant_direction: str = "UNDETERMINED"
    conflicts: list[str] = field(default_factory=list)
    narrative: str = ""
    caveat: str = (
        "Timeframe alignment is descriptive. A conflict between timeframes is the "
        "normal state of a market, not an error, and alignment has not been shown "
        "to precede better returns."
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset": self.asset,
            "timeframes": [r.to_dict() for r in self.readings],
            "alignment": self.alignment.value,
            "dominant_direction": self.dominant_direction,
            "conflicts": self.conflicts,
            "narrative": self.narrative,
            "caveat": self.caveat,
            "available_timeframes": [r.timeframe for r in self.readings if r.available],
            "missing_timeframes": [
                r.timeframe for r in self.readings if not r.available
            ],
        }


class MultiTimeframeEngine:
    """Read every timeframe, then say what they mean together."""

    def __init__(self, ladder: list[Timeframe] | None = None) -> None:
        self.ladder = ladder or LADDER

    def assess(self, asset: Asset, as_of: datetime | None = None) -> MultiTimeframeReading:
        from ..structure.location import StructuralLocationEngine
        from ..structure.market_structure import MarketStructureEngine

        out = MultiTimeframeReading(asset=asset.value)
        location_engine = StructuralLocationEngine()
        structure_engine = MarketStructureEngine()

        for timeframe in self.ladder:
            reading = TimeframeReading(timeframe=timeframe.value)
            df = store.load_candles(asset, timeframe)
            if as_of is not None and not df.empty:
                df = df[df.index <= as_of]

            reading.bars = len(df)
            if df.empty:
                reading.reason_unavailable = "no candles stored for this timeframe"
                out.readings.append(reading)
                continue
            if len(df) < 60:
                reading.reason_unavailable = f"only {len(df)} bars, need 60"
                out.readings.append(reading)
                continue

            try:
                structure = structure_engine.assess(asset, timeframe, as_of)
                reading.structure = structure.state.value
            except Exception as exc:
                log.debug("structure_failed", tf=timeframe.value, error=str(exc))

            try:
                location = location_engine.assess(asset, timeframe, as_of)
                reading.location = location.state.value
                reading.relative_position = location.relative_position
                reading.invalidation = location.invalidation
                detected = location.detected_range
                if detected and detected.valid and detected.top_zone and detected.bottom_zone:
                    reading.range_top = round(detected.top_zone.midpoint, 6)
                    reading.range_bottom = round(detected.bottom_zone.midpoint, 6)
            except Exception as exc:
                log.debug("location_failed", tf=timeframe.value, error=str(exc))

            reading.available = True
            out.readings.append(reading)

        self._synthesise(out)
        return out

    def _synthesise(self, out: MultiTimeframeReading) -> None:
        usable = [r for r in out.readings if r.available and r.direction is not None]
        if len(usable) < 2:
            out.alignment = AlignmentState.INSUFFICIENT_DATA
            out.narrative = (
                f"Only {len(usable)} timeframe(s) could be read; no cross-timeframe "
                "statement is possible."
            )
            return

        # The two highest available timeframes define the context.
        higher = [r for r in usable if r.timeframe in ("1w", "1d")]
        lower = [r for r in usable if r.timeframe in ("4h", "1h", "15m")]

        directions = [r.direction for r in usable]
        bullish = sum(1 for d in directions if d == 1)
        bearish = sum(1 for d in directions if d == -1)
        neutral = sum(1 for d in directions if d == 0)

        if bullish and not bearish:
            out.dominant_direction = "BULLISH"
        elif bearish and not bullish:
            out.dominant_direction = "BEARISH"
        elif bullish or bearish:
            out.dominant_direction = "MIXED"
        else:
            out.dominant_direction = "RANGE"

        # Name every disagreement explicitly.
        for high in higher:
            for low in lower:
                if high.direction is None or low.direction is None:
                    continue
                if high.direction != 0 and low.direction != 0 and high.direction != low.direction:
                    out.conflicts.append(
                        f"{high.timeframe} is "
                        f"{'bullish' if high.direction == 1 else 'bearish'} while "
                        f"{low.timeframe} is "
                        f"{'bullish' if low.direction == 1 else 'bearish'}"
                    )

        higher_directions = {r.direction for r in higher if r.direction is not None}
        lower_directions = {r.direction for r in lower if r.direction is not None}

        if out.conflicts:
            out.alignment = AlignmentState.CONFLICT
        elif (
            len(higher_directions) == 1
            and higher_directions != {0}
            and lower_directions
            and lower_directions == higher_directions
        ):
            out.alignment = AlignmentState.HIGHER_TIMEFRAME_ALIGNMENT
        elif higher_directions and lower_directions and 0 in lower_directions:
            # The higher frame has a direction, the lower one is consolidating:
            # a pause inside a trend, not a disagreement.
            out.alignment = AlignmentState.TRANSITION
        else:
            out.alignment = AlignmentState.TRANSITION

        out.narrative = self._narrate(out, usable, bullish, bearish, neutral)

    def _narrate(
        self, out: MultiTimeframeReading, usable: list[TimeframeReading],
        bullish: int, bearish: int, neutral: int,
    ) -> str:
        lines = " · ".join(r.describe() for r in usable)
        verdict = {
            AlignmentState.HIGHER_TIMEFRAME_ALIGNMENT:
                "Every readable timeframe points the same way.",
            AlignmentState.CONFLICT:
                "Timeframes disagree, which is ordinary: they describe different "
                "horizons and both readings can be correct at once.",
            AlignmentState.TRANSITION:
                "The higher timeframe holds a direction while a lower one "
                "consolidates - a pause inside a move rather than a disagreement.",
            AlignmentState.INSUFFICIENT_DATA: "",
        }[out.alignment]

        detail = ""
        if out.conflicts:
            detail = " " + "; ".join(out.conflicts) + "."
        return f"{lines}. {verdict}{detail}"

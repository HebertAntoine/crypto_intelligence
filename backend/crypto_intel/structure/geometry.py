"""Geometry a chart needs to redraw a detected figure.

Kept in its own module because both ends need it and neither may import the
other: `patterns.py` produces the geometry as it detects a shape, and
`detection.py` publishes it. Everything here carries real timestamps rather
than bar indices - an index is meaningless to a chart holding a different
window of candles, and it shifts silently the moment the store gains earlier
history.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# --- geometry --------------------------------------------------------------
#
# Everything below carries real timestamps rather than bar indices. An index is
# meaningless to a chart that has loaded a different window of candles, and it
# breaks silently when the store gains earlier history.


@dataclass(slots=True, frozen=True)
class GeometryPoint:
    """One named point of the figure - a peak, a trough, a shoulder."""

    time: datetime
    price: float
    role: str = ""          # "first_top", "head", "left_shoulder", ...
    kind: str = "pivot"     # "pivot" | "close" | "projected"

    def to_dict(self) -> dict[str, Any]:
        return {
            "time": self.time.isoformat(),
            "price": self.price,
            "role": self.role,
            "kind": self.kind,
        }


@dataclass(slots=True, frozen=True)
class TrendLine:
    """A segment between two points, optionally extended to the right.

    `extend` exists because a triangle's boundaries are meaningful ahead of the
    last bar, while a neckline drawn across two completed tops is not.
    """

    start: GeometryPoint
    end: GeometryPoint
    role: str = ""          # "upper", "lower", "neckline", "pole", ...
    extend: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "start": self.start.to_dict(),
            "end": self.end.to_dict(),
            "role": self.role,
            "extend": self.extend,
        }


@dataclass(slots=True, frozen=True)
class GeometryZone:
    """A rectangular area - a breakout band, an invalidation region."""

    start_time: datetime
    end_time: datetime
    low: float
    high: float
    role: str = ""          # "breakout", "invalidation", "target", ...

    def to_dict(self) -> dict[str, Any]:
        return {
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "low": self.low,
            "high": self.high,
            "role": self.role,
        }


@dataclass(slots=True)
class PatternGeometry:
    """Enough to redraw the figure without recomputing it.

    A frontend holding this and the candles can reconstruct exactly what the
    detector saw. It never re-derives geometry of its own, which is what keeps
    the drawing and the analysis from disagreeing.
    """

    points: list[GeometryPoint] = field(default_factory=list)
    trend_lines: list[TrendLine] = field(default_factory=list)
    zones: list[GeometryZone] = field(default_factory=list)
    neckline: TrendLine | None = None
    breakout_area: GeometryZone | None = None

    @property
    def is_empty(self) -> bool:
        return not (self.points or self.trend_lines or self.zones or self.neckline)

    def to_dict(self) -> dict[str, Any]:
        return {
            "points": [p.to_dict() for p in self.points],
            "trend_lines": [line.to_dict() for line in self.trend_lines],
            "zones": [z.to_dict() for z in self.zones],
            "neckline": self.neckline.to_dict() if self.neckline else None,
            "breakout_area": (
                self.breakout_area.to_dict() if self.breakout_area else None
            ),
        }

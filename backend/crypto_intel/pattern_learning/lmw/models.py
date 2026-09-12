"""Public records emitted by the independent LMW-inspired baseline.

The score in this module is deliberately named ``lmw_match_score``.  It is a
geometrical template-match score; it is not a probability and it never reads
future returns.  Keeping a separate record from ``StructuralPattern`` also
prevents the comparator from silently inheriting the production detector's
semantics.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

import numpy as np

from ...structure.geometry import GeometryPoint, PatternGeometry, TrendLine
from ..ontology import MethodFamily, StructuralPatternName


class LMWMode(StrEnum):
    RETROSPECTIVE = "LMW_RETROSPECTIVE"
    CAUSAL = "LMW_CAUSAL"

    @property
    def causal(self) -> bool:
        return self is LMWMode.CAUSAL

    @property
    def detector_version(self) -> str:
        return "lmw_causal_v1" if self.causal else "lmw_retrospective_v1"


class LMWStatus(StrEnum):
    DETECTED = "DETECTED"
    NO_VALID_PATTERN = "NO_VALID_PATTERN"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class PatternOrientation(StrEnum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


@dataclass(slots=True, frozen=True)
class LMWScoreComponents:
    """The four independently inspectable parts of a template match."""

    shape_fit: float
    extrema_fit: float
    symmetry_fit: float
    duration_fit: float

    @property
    def mean(self) -> float:
        return round(float(np.mean(list(self.to_dict().values()))), 1)

    def to_dict(self) -> dict[str, float]:
        return {
            "shape_fit": round(float(self.shape_fit), 1),
            "extrema_fit": round(float(self.extrema_fit), 1),
            "symmetry_fit": round(float(self.symmetry_fit), 1),
            "duration_fit": round(float(self.duration_fit), 1),
        }


@dataclass(slots=True)
class LMWDetection:
    """One LMW template match, with timestamped and drawable geometry."""

    pattern: StructuralPatternName
    start_time: datetime
    end_time: datetime
    available_at: datetime
    geometry: PatternGeometry
    lmw_match_score: float
    score_components: LMWScoreComponents
    mode: LMWMode
    orientation: PatternOrientation
    detection_delay_bars: int
    start_index: int
    end_index: int
    available_index: int
    detector_version: str = ""
    method_family: MethodFamily = MethodFamily.KERNEL_TEMPLATE_MATCHING
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.detector_version:
            self.detector_version = self.mode.detector_version

    @property
    def causal(self) -> bool:
        return self.mode.causal

    @property
    def points(self) -> list[GeometryPoint]:
        return self.geometry.points

    @property
    def lines(self) -> list[TrendLine]:
        return self.geometry.trend_lines

    @property
    def neckline(self) -> TrendLine | None:
        return self.geometry.neckline

    @property
    def id(self) -> str:
        raw = "|".join(
            (
                self.detector_version,
                self.pattern.value,
                self.start_time.isoformat(),
                self.end_time.isoformat(),
            )
        )
        return hashlib.sha256(raw.encode()).hexdigest()[:24]

    def score_is_explained(self, tolerance: float = 0.11) -> bool:
        return abs(float(self.lmw_match_score) - self.score_components.mean) <= tolerance

    def to_dict(self) -> dict[str, Any]:
        geometry = self.geometry.to_dict()
        return {
            "id": self.id,
            "pattern": self.pattern.value,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "points": geometry["points"],
            "lines": geometry["trend_lines"],
            "neckline": geometry["neckline"],
            "geometry": geometry,
            "lmw_match_score": round(float(self.lmw_match_score), 1),
            "score_components": self.score_components.to_dict(),
            "score_is_explained": self.score_is_explained(),
            "causal": self.causal,
            "mode": self.mode.value,
            "available_at": self.available_at.isoformat(),
            "method_family": self.method_family.value,
            "detector_version": self.detector_version,
            "orientation": self.orientation.value,
            "detection_delay_bars": int(self.detection_delay_bars),
            "start_index": int(self.start_index),
            "end_index": int(self.end_index),
            "available_index": int(self.available_index),
            "metadata": self.metadata,
            "score_note": (
                "Template-match quality only; not a probability of success, "
                "a direction forecast, or evidence of edge."
            ),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> LMWDetection:
        geometry_raw = raw.get("geometry") or {}

        def point(item: dict[str, Any]) -> GeometryPoint:
            return GeometryPoint(
                time=datetime.fromisoformat(item["time"]),
                price=float(item["price"]),
                role=str(item.get("role", "")),
                kind=str(item.get("kind", "pivot")),
            )

        def line(item: dict[str, Any]) -> TrendLine:
            return TrendLine(
                start=point(item["start"]),
                end=point(item["end"]),
                role=str(item.get("role", "")),
                extend=bool(item.get("extend", False)),
            )

        lines = [line(item) for item in geometry_raw.get("trend_lines", [])]
        neckline_raw = geometry_raw.get("neckline")
        geometry = PatternGeometry(
            points=[point(item) for item in geometry_raw.get("points", [])],
            trend_lines=lines,
            neckline=line(neckline_raw) if neckline_raw else None,
        )
        components = raw["score_components"]
        return cls(
            pattern=StructuralPatternName(raw["pattern"]),
            start_time=datetime.fromisoformat(raw["start_time"]),
            end_time=datetime.fromisoformat(raw["end_time"]),
            available_at=datetime.fromisoformat(raw["available_at"]),
            geometry=geometry,
            lmw_match_score=float(raw["lmw_match_score"]),
            score_components=LMWScoreComponents(**components),
            mode=LMWMode(raw["mode"]),
            orientation=PatternOrientation(raw["orientation"]),
            detection_delay_bars=int(raw["detection_delay_bars"]),
            start_index=int(raw["start_index"]),
            end_index=int(raw["end_index"]),
            available_index=int(raw["available_index"]),
            detector_version=str(raw["detector_version"]),
            method_family=MethodFamily(raw["method_family"]),
            metadata=dict(raw.get("metadata") or {}),
        )


@dataclass(slots=True)
class LMWResult:
    """The detector must be allowed to say that no template is valid."""

    status: LMWStatus
    detection: LMWDetection | None = None
    candidates_evaluated: int = 0
    rejection_counts: dict[str, int] = field(default_factory=dict)
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "detection": self.detection.to_dict() if self.detection else None,
            "candidates_evaluated": self.candidates_evaluated,
            "rejection_counts": self.rejection_counts,
            "reason": self.reason,
        }


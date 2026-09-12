"""Agreement between the production detector and an independent comparator.

Agreement is a recognition-quality gate, not evidence that price will move in
the textbook direction.  The two questions remain separate by construction.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from ..structure.history_scan import HistoricalPattern
from .lmw.models import LMWDetection
from .lmw.templates import TEMPLATE_BY_PATTERN
from .ontology import METHOD_FAMILIES, MethodFamily, StructuralPatternName, canonical


class ConsensusState(StrEnum):
    INDEPENDENT_AGREEMENT = "INDEPENDENT_AGREEMENT"
    OURS_ONLY = "OURS_ONLY"
    LMW_ONLY = "LMW_ONLY"


@dataclass(slots=True, frozen=True)
class ConsensusItem:
    pattern: StructuralPatternName
    state: ConsensusState
    start_time: datetime
    end_time: datetime
    available_at: datetime
    ours_id: str | None = None
    lmw_id: str | None = None
    temporal_iou: float | None = None
    ours_score: float | None = None
    lmw_score: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "pattern": self.pattern.value,
            "state": self.state.value,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "available_at": self.available_at.isoformat(),
            "ours_id": self.ours_id,
            "lmw_id": self.lmw_id,
            "temporal_iou": self.temporal_iou,
            "ours_score": self.ours_score,
            "lmw_score": self.lmw_score,
            "method_families": {
                "ours": METHOD_FAMILIES["OUR_ENGINE"].value,
                "lmw": METHOD_FAMILIES["LMW"].value,
            },
            "independent_methods": (
                METHOD_FAMILIES["OUR_ENGINE"] is not METHOD_FAMILIES["LMW"]
            ),
            "edge_claim": False,
        }


@dataclass(slots=True)
class ConsensusReport:
    items: list[ConsensusItem] = field(default_factory=list)
    not_comparable_ours: int = 0
    min_temporal_iou: float = 0.35

    @property
    def agreements(self) -> list[ConsensusItem]:
        return [
            item for item in self.items
            if item.state is ConsensusState.INDEPENDENT_AGREEMENT
        ]

    def summary(self) -> dict[str, Any]:
        ours_only = sum(item.state is ConsensusState.OURS_ONLY for item in self.items)
        lmw_only = sum(item.state is ConsensusState.LMW_ONLY for item in self.items)
        comparable_ours = len(self.agreements) + ours_only
        return {
            "independent_agreements": len(self.agreements),
            "ours_only": ours_only,
            "lmw_only": lmw_only,
            "not_comparable_ours": self.not_comparable_ours,
            "comparable_ours": comparable_ours,
            "agreement_rate_pct": (
                round(len(self.agreements) / comparable_ours * 100.0, 1)
                if comparable_ours else None
            ),
            "min_temporal_iou": self.min_temporal_iou,
            "promotion_rule": (
                "Independent agreement promotes recognition quality only; "
                "forward edge still requires a separate out-of-sample test."
            ),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary(),
            "items": [item.to_dict() for item in self.items],
        }


def compare_with_lmw(
    ours: list[HistoricalPattern | dict[str, Any]],
    lmw: list[LMWDetection],
    *,
    min_temporal_iou: float = 0.35,
) -> ConsensusReport:
    """One-to-one matching by canonical name and temporal intersection.

    A broad pattern cannot claim agreement merely by containing a short one:
    intersection-over-union penalises both shifted and differently sized
    windows.  Greedy matching starts from the strongest overlap so one LMW
    reading cannot validate several production detections.
    """
    if not 0 < min_temporal_iou <= 1:
        raise ValueError("min_temporal_iou must be in (0, 1]")

    comparable: list[
        tuple[int, HistoricalPattern | dict[str, Any], StructuralPatternName]
    ] = []
    not_comparable = 0
    for index, item in enumerate(ours):
        name = canonical(_ours_name(item))
        if name is None or name not in TEMPLATE_BY_PATTERN:
            not_comparable += 1
            continue
        comparable.append((index, item, name))

    candidates: list[tuple[float, int, int]] = []
    for ours_index, ours_item, ours_name in comparable:
        for lmw_index, lmw_item in enumerate(lmw):
            if ours_name is not lmw_item.pattern:
                continue
            score = temporal_iou(
                _ours_start(ours_item),
                _ours_end(ours_item),
                lmw_item.start_time,
                lmw_item.end_time,
            )
            if score >= min_temporal_iou:
                candidates.append((score, ours_index, lmw_index))

    matched_ours: set[int] = set()
    matched_lmw: set[int] = set()
    items: list[ConsensusItem] = []
    ours_by_index = {index: (item, name) for index, item, name in comparable}
    for score, ours_index, lmw_index in sorted(candidates, reverse=True):
        if ours_index in matched_ours or lmw_index in matched_lmw:
            continue
        ours_item, name = ours_by_index[ours_index]
        lmw_item = lmw[lmw_index]
        matched_ours.add(ours_index)
        matched_lmw.add(lmw_index)
        items.append(ConsensusItem(
            pattern=name,
            state=ConsensusState.INDEPENDENT_AGREEMENT,
            start_time=max(_ours_start(ours_item), lmw_item.start_time),
            end_time=max(_ours_end(ours_item), lmw_item.end_time),
            available_at=max(_ours_available(ours_item), lmw_item.available_at),
            ours_id=_ours_id(ours_item),
            lmw_id=lmw_item.id,
            temporal_iou=round(score, 3),
            ours_score=round(_ours_score(ours_item), 1),
            lmw_score=round(float(lmw_item.lmw_match_score), 1),
        ))

    for ours_index, ours_item, name in comparable:
        if ours_index in matched_ours:
            continue
        items.append(ConsensusItem(
            pattern=name,
            state=ConsensusState.OURS_ONLY,
            start_time=_ours_start(ours_item),
            end_time=_ours_end(ours_item),
            available_at=_ours_available(ours_item),
            ours_id=_ours_id(ours_item),
            ours_score=round(_ours_score(ours_item), 1),
        ))

    for lmw_index, lmw_item in enumerate(lmw):
        if lmw_index in matched_lmw:
            continue
        items.append(ConsensusItem(
            pattern=lmw_item.pattern,
            state=ConsensusState.LMW_ONLY,
            start_time=lmw_item.start_time,
            end_time=lmw_item.end_time,
            available_at=lmw_item.available_at,
            lmw_id=lmw_item.id,
            lmw_score=round(float(lmw_item.lmw_match_score), 1),
        ))

    items.sort(key=lambda item: (item.end_time, item.pattern.value, item.state.value))
    return ConsensusReport(
        items=items,
        not_comparable_ours=not_comparable,
        min_temporal_iou=min_temporal_iou,
    )


def temporal_iou(
    first_start: datetime,
    first_end: datetime,
    second_start: datetime,
    second_end: datetime,
) -> float:
    """Temporal intersection over union for two closed figure windows."""
    if first_end < first_start or second_end < second_start:
        raise ValueError("pattern end_time cannot precede start_time")
    intersection = max(
        0.0,
        (min(first_end, second_end) - max(first_start, second_start)).total_seconds(),
    )
    union = (max(first_end, second_end) - min(first_start, second_start)).total_seconds()
    if union <= 0:
        return 1.0 if first_start == second_start else 0.0
    return float(intersection / union)


def _ours_name(item: HistoricalPattern | dict[str, Any]) -> str:
    return item.name if isinstance(item, HistoricalPattern) else str(item["name"])


def _ours_start(item: HistoricalPattern | dict[str, Any]) -> datetime:
    if isinstance(item, HistoricalPattern):
        return item.start_time
    return datetime.fromisoformat(str(item["span_start"]))


def _ours_end(item: HistoricalPattern | dict[str, Any]) -> datetime:
    if isinstance(item, HistoricalPattern):
        return item.end_time
    return datetime.fromisoformat(str(item["span_end"]))


def _ours_available(item: HistoricalPattern | dict[str, Any]) -> datetime:
    if isinstance(item, HistoricalPattern):
        return item.first_seen_time
    return datetime.fromisoformat(str(item["first_seen_at"]))


def _ours_score(item: HistoricalPattern | dict[str, Any]) -> float:
    if isinstance(item, HistoricalPattern):
        return float(item.pattern.recognition_confidence)
    return float(item.get("recognition_confidence") or 0.0)


def _ours_id(item: HistoricalPattern | dict[str, Any]) -> str:
    if isinstance(item, dict) and item.get("id"):
        return str(item["id"])
    raw = "|".join(
        (_ours_name(item), _ours_start(item).isoformat(), _ours_end(item).isoformat())
    )
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def production_detection_id(item: HistoricalPattern | dict[str, Any]) -> str:
    """Stable public identity used to join a detection to quality labels."""
    return _ours_id(item)


def methods_are_independent() -> bool:
    """Explicit guard used by reports before calling agreement evidence."""
    ours: MethodFamily = METHOD_FAMILIES["OUR_ENGINE"]
    comparator: MethodFamily = METHOD_FAMILIES["LMW"]
    return ours is not comparator

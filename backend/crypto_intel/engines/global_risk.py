"""Global market-risk diagnosis over three exact, non-overlapping windows.

This layer deliberately reuses the five future families and the event-risk
engine.  It does not compute a directional market score and never publishes a
probability.  A missing horizon model is reported as indeterminate rather than
being filled with a shorter-horizon reading.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, ClassVar

from ..future_events.freshness import EventFreshness, event_freshness
from ..future_events.models import (
    ExpectedMovement,
    FutureEvent,
    FutureEventStatus,
)
from .future_decision import (
    FAMILY_LABELS,
    EventRiskEngine,
    EventRiskLevel,
    FamilyAssessment,
    FiveFamilySnapshot,
    FutureFamily,
)
from .source_hierarchy import may_influence_decision


class GlobalRiskHorizon(StrEnum):
    SHORT = "1-7d"
    MEDIUM = "8-30d"
    LONG = "31-90d"


class GlobalRiskLevel(StrEnum):
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"
    INDETERMINATE = "INDETERMINATE"


class RiskChange(StrEnum):
    INCREASED = "INCREASED"
    DECREASED = "DECREASED"
    UNCHANGED = "UNCHANGED"
    NOT_AVAILABLE = "NOT_AVAILABLE"


@dataclass(frozen=True, slots=True)
class RiskWindow:
    starts_after: timedelta
    ends_at: timedelta
    label: str


RISK_WINDOWS: dict[GlobalRiskHorizon, RiskWindow] = {
    GlobalRiskHorizon.SHORT: RiskWindow(
        starts_after=timedelta(0),
        ends_at=timedelta(days=7),
        label="Court terme (1 à 7 jours)",
    ),
    GlobalRiskHorizon.MEDIUM: RiskWindow(
        starts_after=timedelta(days=7),
        ends_at=timedelta(days=30),
        label="Moyen terme (8 à 30 jours)",
    ),
    GlobalRiskHorizon.LONG: RiskWindow(
        starts_after=timedelta(days=30),
        ends_at=timedelta(days=90),
        label="Plus long terme (31 à 90 jours)",
    ),
}


@dataclass(slots=True)
class RiskDataCoverage:
    available_families: list[str]
    usable_families: list[str]
    unavailable_families: list[str]
    event_count: int
    status: str
    limitations: list[str] = field(default_factory=list)
    total_families: int = 5

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "available_families": self.available_families,
            "available_family_count": len(self.available_families),
            "usable_families": self.usable_families,
            "usable_family_count": len(self.usable_families),
            "unavailable_families": self.unavailable_families,
            "total_families": self.total_families,
            "authorized_event_count": self.event_count,
            "limitations": self.limitations,
        }


@dataclass(slots=True)
class GlobalRiskDiagnosis:
    risk_level: GlobalRiskLevel
    horizon: GlobalRiskHorizon
    assessment_time: datetime
    data_coverage: RiskDataCoverage
    main_drivers: list[str]
    counter_signals: list[str]
    change_since_previous: RiskChange
    evidence_ids: list[str]
    invalidation_conditions: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "risk_level": self.risk_level.value,
            "horizon": self.horizon.value,
            "assessment_time": self.assessment_time.isoformat(),
            "data_coverage": self.data_coverage.to_dict(),
            "main_drivers": self.main_drivers,
            "counter_signals": self.counter_signals,
            "change_since_previous": self.change_since_previous.value,
            "evidence_ids": self.evidence_ids,
            "invalidation_conditions": self.invalidation_conditions,
        }


_EVENT_LEVEL = {
    EventRiskLevel.LOW: GlobalRiskLevel.LOW,
    EventRiskLevel.MODERATE: GlobalRiskLevel.MODERATE,
    EventRiskLevel.HIGH: GlobalRiskLevel.HIGH,
    EventRiskLevel.EXTREME: GlobalRiskLevel.CRITICAL,
    EventRiskLevel.UNKNOWN: GlobalRiskLevel.INDETERMINATE,
}

_MOVEMENT_LEVEL = {
    ExpectedMovement.LOW: GlobalRiskLevel.LOW,
    ExpectedMovement.NORMAL: GlobalRiskLevel.MODERATE,
    ExpectedMovement.HIGH: GlobalRiskLevel.HIGH,
    ExpectedMovement.EXTREME: GlobalRiskLevel.CRITICAL,
}

_LEVEL_RANK = {
    GlobalRiskLevel.LOW: 0,
    GlobalRiskLevel.MODERATE: 1,
    GlobalRiskLevel.HIGH: 2,
    GlobalRiskLevel.CRITICAL: 3,
}


def _reference_time(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def authorized_events_for_window(
    events: Iterable[FutureEvent],
    horizon: GlobalRiskHorizon,
    *,
    as_of: datetime,
) -> list[FutureEvent]:
    """Select authoritative events into exactly one risk window.

    Scheduled events use ``(start, end]`` boundaries.  An unscheduled active
    shock is current risk rather than a dated forecast and therefore belongs
    only to the short window.
    """

    now = _reference_time(as_of)
    window = RISK_WINDOWS[horizon]
    selected: list[FutureEvent] = []
    for event in events:
        if not may_influence_decision(event.source_tier):
            continue
        if event_freshness(event, now).freshness_status not in {
            EventFreshness.LIVE,
            EventFreshness.FRESH,
        }:
            continue
        if event.scheduled_at is not None:
            if event.runtime_status(now) not in {
                FutureEventStatus.SCHEDULED,
                FutureEventStatus.UPCOMING,
            }:
                continue
            distance = event.scheduled_at - now
            if window.starts_after < distance <= window.ends_at:
                selected.append(event)
            continue
        if horizon is not GlobalRiskHorizon.SHORT:
            continue
        origin = event.source_published_at or event.detected_at
        age = now - origin
        if timedelta(0) <= age <= window.ends_at and event.runtime_status(now) in {
            FutureEventStatus.ACTIVE,
            FutureEventStatus.RELEASED,
            FutureEventStatus.SURPRISE,
            FutureEventStatus.DECAYING,
        }:
            selected.append(event)
    return sorted(
        selected,
        key=lambda item: (
            item.scheduled_at or item.source_published_at or item.detected_at,
            -item.importance.rank,
        ),
    )


def _family_level(item: FamilyAssessment) -> GlobalRiskLevel | None:
    if not item.available or item.expected_movement is None:
        return None
    return _MOVEMENT_LEVEL[item.expected_movement]


def _family_is_usable(item: FamilyAssessment) -> bool:
    """Require both an amplitude reading and traceable provenance.

    ``available=True`` alone is not enough to publish an aggregate risk level:
    a family without a movement or a source can be displayed as partial
    coverage, but it cannot count toward the three-family decision floor.
    """

    return (
        item.available
        and item.expected_movement is not None
        and bool(item.sources)
        and item.freshness.upper() not in {"STALE", "UNAVAILABLE"}
    )


def _event_driver(event: FutureEvent) -> str:
    assets = ", ".join(asset.value for asset in event.affected_assets)
    affected = assets or "marché global"
    return (
        f"Événement {event.importance.value}/{event.magnitude_effect.value}: "
        f"{event.title} (actifs affectés: {affected})"
    )


def _evidence_ids(
    families: FiveFamilySnapshot | None,
    events: Iterable[FutureEvent],
) -> list[str]:
    identifiers: list[str] = []
    if families is not None:
        for assessment in families.assessments.values():
            if not assessment.available:
                continue
            for source in assessment.sources:
                values = source.get("evidence_ids") or [
                    source.get("reference"),
                    source.get("id"),
                ]
                identifiers.extend(str(value) for value in values if value)
    for event in events:
        identifiers.extend(str(value) for value in event.evidence_ids if value)
        identifiers.append(event.id)
    return list(dict.fromkeys(identifiers))


def _change(
    current: GlobalRiskLevel,
    previous: GlobalRiskLevel | None,
) -> RiskChange:
    if previous is None or GlobalRiskLevel.INDETERMINATE in {current, previous}:
        return RiskChange.NOT_AVAILABLE
    if _LEVEL_RANK[current] > _LEVEL_RANK[previous]:
        return RiskChange.INCREASED
    if _LEVEL_RANK[current] < _LEVEL_RANK[previous]:
        return RiskChange.DECREASED
    return RiskChange.UNCHANGED


class GlobalRiskEngine:
    """Aggregate risk amplitude, never expected return or market direction."""

    minimum_family_coverage: ClassVar[int] = 3

    def assess(
        self,
        events: Iterable[FutureEvent],
        families_by_horizon: Mapping[GlobalRiskHorizon, FiveFamilySnapshot | None],
        *,
        as_of: datetime,
        previous_levels: Mapping[GlobalRiskHorizon, GlobalRiskLevel] | None = None,
    ) -> list[GlobalRiskDiagnosis]:
        now = _reference_time(as_of)
        event_list = list(events)
        return [
            self._assess_horizon(
                horizon,
                authorized_events_for_window(event_list, horizon, as_of=now),
                families_by_horizon.get(horizon),
                as_of=now,
                previous_level=(previous_levels or {}).get(horizon),
            )
            for horizon in GlobalRiskHorizon
        ]

    def _assess_horizon(
        self,
        horizon: GlobalRiskHorizon,
        events: list[FutureEvent],
        families: FiveFamilySnapshot | None,
        *,
        as_of: datetime,
        previous_level: GlobalRiskLevel | None,
    ) -> GlobalRiskDiagnosis:
        window = RISK_WINDOWS[horizon]
        family_items = (
            [item for item in families.assessments.values() if item.available]
            if families is not None
            else []
        )
        usable_family_items = [item for item in family_items if _family_is_usable(item)]
        available_names = [item.family.value for item in family_items]
        usable_names = [item.family.value for item in usable_family_items]
        unavailable_names = [
            family.value for family in FutureFamily if family.value not in available_names
        ]
        limitations: list[str] = []
        if families is None:
            limitations.append("Aucune lecture des cinq familles n'est validée pour cette fenêtre.")
        elif len(usable_family_items) < self.minimum_family_coverage:
            limitations.append(
                "Moins de trois des cinq familles disposent d'une amplitude sourcée utilisable."
            )
        if horizon is GlobalRiskHorizon.LONG and families is None:
            limitations.append(
                "La lecture 30 jours n'est pas réutilisée sous une étiquette 31-90 jours."
            )

        sufficient = (
            families is not None and len(usable_family_items) >= self.minimum_family_coverage
        )
        coverage = RiskDataCoverage(
            available_families=available_names,
            usable_families=usable_names,
            unavailable_families=unavailable_names,
            event_count=len(events),
            status=(
                "COMPLETE"
                if len(usable_family_items) == 5
                else "SUFFICIENT"
                if sufficient
                else "INSUFFICIENT"
            ),
            limitations=limitations,
        )

        event_risk = EventRiskEngine().assess_future_window(
            events,
            starts_after=window.starts_after,
            ends_at=window.ends_at,
            as_of=as_of,
        )
        family_levels = [
            level for item in usable_family_items if (level := _family_level(item)) is not None
        ]
        candidate_levels = [
            _EVENT_LEVEL[event_risk.level],
            *family_levels,
        ]
        determinate_candidates = [
            level for level in candidate_levels if level is not GlobalRiskLevel.INDETERMINATE
        ]
        measured_level = max(
            determinate_candidates or [GlobalRiskLevel.LOW],
            key=_LEVEL_RANK.__getitem__,
        )
        risk_level = measured_level if sufficient else GlobalRiskLevel.INDETERMINATE

        by_event_id = {event.id: event for event in events}
        ranked_events = [
            by_event_id[item.event_id]
            for item in event_risk.contributions
            if item.event_id in by_event_id
        ]
        main_drivers = [_event_driver(event) for event in ranked_events[:4]]
        for item in usable_family_items:
            if _family_level(item) is measured_level:
                detail = item.summary or "lecture d'amplitude disponible"
                main_drivers.append(f"{FAMILY_LABELS[item.family]}: {detail}")
        if not main_drivers and usable_family_items:
            main_drivers = [
                f"{FAMILY_LABELS[item.family]}: "
                f"{item.summary or 'lecture disponible sans facteur dominant'}"
                for item in usable_family_items[:3]
            ]

        counter_signals = [
            f"{FAMILY_LABELS[item.family]}: "
            f"{item.summary or 'amplitude inférieure au risque dominant'}"
            for item in usable_family_items
            if (level := _family_level(item)) is not None
            and level is not measured_level
            and _LEVEL_RANK[level] < _LEVEL_RANK[measured_level]
        ][:5]

        invalidation_conditions = [
            f"Reclasser après publication ou résolution de « {event.title} »."
            for event in ranked_events[:4]
        ]
        invalidation_conditions.extend(
            f"{FAMILY_LABELS[item.family]}: l'amplitude "
            f"{item.expected_movement.value} n'est plus confirmée par ses sources."
            for item in usable_family_items
            if _family_level(item) is measured_level and item.expected_movement is not None
        )
        if not invalidation_conditions and risk_level is GlobalRiskLevel.INDETERMINATE:
            invalidation_conditions.append(
                "Obtenir au moins trois familles utilisables et propres à cette fenêtre."
            )

        return GlobalRiskDiagnosis(
            risk_level=risk_level,
            horizon=horizon,
            assessment_time=as_of,
            data_coverage=coverage,
            main_drivers=list(dict.fromkeys(main_drivers))[:8],
            counter_signals=list(dict.fromkeys(counter_signals)),
            change_since_previous=_change(risk_level, previous_level),
            evidence_ids=_evidence_ids(families, events),
            invalidation_conditions=list(dict.fromkeys(invalidation_conditions))[:8],
        )

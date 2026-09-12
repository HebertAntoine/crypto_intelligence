"""Future-first scenarios, event-risk gate and final decision.

This module deliberately does not compute a weighted market score.  It applies
the product hierarchy in order: systemic events, expectations/liquidity,
flows, positioning, then technical confirmation.  Missing evidence is a
missing slot, never a neutral vote.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from ..core.enums import Asset
from ..future_events.models import (
    DecisionHorizon,
    DirectionalBias,
    EventImportance,
    ExpectedMovement,
    FutureEvent,
    FutureEventStatus,
)


class DecisionAction(StrEnum):
    BUY = "BUY"
    WAIT = "WAIT"
    SELL = "SELL"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class EventRiskLevel(StrEnum):
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    EXTREME = "EXTREME"
    UNKNOWN = "UNKNOWN"


class FutureFamily(StrEnum):
    MACRO_LIQUIDITY = "macro_liquidity"
    CATALYSTS_REGULATION = "catalysts_regulation"
    FLOWS_WHALES = "flows_whales"
    POSITIONING_DERIVATIVES = "positioning_derivatives"
    TECHNICAL_VOLATILITY = "technical_volatility"


FAMILY_LABELS: dict[FutureFamily, str] = {
    FutureFamily.MACRO_LIQUIDITY: "Macro & liquidité",
    FutureFamily.CATALYSTS_REGULATION: "Catalyseurs & réglementation",
    FutureFamily.FLOWS_WHALES: "Flux institutionnels & baleines",
    FutureFamily.POSITIONING_DERIVATIVES: "Positionnement & dérivés",
    FutureFamily.TECHNICAL_VOLATILITY: "Technique & volatilité",
}

FAMILY_PRIORITY: dict[FutureFamily, int] = {
    FutureFamily.MACRO_LIQUIDITY: 1,
    FutureFamily.CATALYSTS_REGULATION: 1,
    FutureFamily.FLOWS_WHALES: 2,
    FutureFamily.POSITIONING_DERIVATIVES: 3,
    FutureFamily.TECHNICAL_VOLATILITY: 4,
}


@dataclass(slots=True)
class FamilyAssessment:
    family: FutureFamily
    available: bool
    directional_bias: DirectionalBias | None = None
    expected_movement: ExpectedMovement | None = None
    confidence: float = 0.0
    summary: str = ""
    reasons: list[str] = field(default_factory=list)
    sources: list[dict[str, Any]] = field(default_factory=list)
    as_of: str | None = None
    freshness: str = "UNAVAILABLE"
    unavailable_reason: str = ""

    def __post_init__(self) -> None:
        self.confidence = max(0.0, min(1.0, float(self.confidence)))
        if not self.available:
            # Do not serialize a fabricated neutral reading for an absent family.
            self.directional_bias = None
            self.expected_movement = None
            self.confidence = 0.0
            self.freshness = "UNAVAILABLE"
            if not self.unavailable_reason:
                self.unavailable_reason = "Aucune donnée utilisable et sourcée."

    def to_dict(self) -> dict[str, Any]:
        return {
            "family": self.family.value,
            "label": FAMILY_LABELS[self.family],
            "status": "AVAILABLE" if self.available else "UNAVAILABLE",
            "available": self.available,
            "directional_bias": self.directional_bias.value if self.directional_bias else None,
            "expected_movement": self.expected_movement.value if self.expected_movement else None,
            "confidence": round(self.confidence, 3),
            "summary": self.summary,
            "reasons": self.reasons,
            "sources": self.sources,
            "as_of": self.as_of,
            "freshness": self.freshness,
            "unavailable_reason": self.unavailable_reason or None,
        }


@dataclass(slots=True)
class FiveFamilySnapshot:
    assessments: dict[FutureFamily, FamilyAssessment]

    def __post_init__(self) -> None:
        required = set(FutureFamily)
        if set(self.assessments) != required:
            missing = sorted(item.value for item in required - set(self.assessments))
            extra = sorted(str(item) for item in set(self.assessments) - required)
            raise ValueError(f"five family snapshot requires exact slots; missing={missing}, extra={extra}")
        if any(key != value.family for key, value in self.assessments.items()):
            raise ValueError("family assessment keys and values must match")

    @classmethod
    def from_partial(
        cls,
        partial: dict[FutureFamily, FamilyAssessment],
        *,
        unavailable_reason: str = "Famille non propagée par les sources configurées.",
    ) -> FiveFamilySnapshot:
        complete = dict(partial)
        for family in FutureFamily:
            complete.setdefault(
                family,
                FamilyAssessment(
                    family=family,
                    available=False,
                    unavailable_reason=unavailable_reason,
                ),
            )
        return cls(complete)

    @property
    def available_count(self) -> int:
        return sum(item.available for item in self.assessments.values())

    @property
    def coverage_label(self) -> str:
        if self.available_count == 5:
            return "5/5 familles"
        return f"{self.available_count}/5 disponibles"

    def to_dict(self) -> dict[str, Any]:
        unavailable = [
            item.family.value for item in self.assessments.values() if not item.available
        ]
        return {
            "coverage": self.coverage_label,
            "available_count": self.available_count,
            "total_count": 5,
            "unavailable": unavailable,
            "items": {
                family.value: self.assessments[family].to_dict() for family in FutureFamily
            },
        }


@dataclass(slots=True)
class EventRiskGateResult:
    active: bool
    level: EventRiskLevel
    reasons: list[str] = field(default_factory=list)
    event_ids: list[str] = field(default_factory=list)
    bypassed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "active": self.active,
            "level": self.level.value,
            "reasons": self.reasons,
            "event_ids": self.event_ids,
            "bypassed": self.bypassed,
        }


class EventRiskGate:
    """Fail closed before a high-amplitude Tier-1 event inside 48 hours."""

    window = timedelta(hours=48)

    @staticmethod
    def _uncertain(event: FutureEvent, analysis_uncertainty: float | None) -> bool:
        if analysis_uncertainty is None or analysis_uncertainty >= 0.60:
            return True
        probabilities = event.market_probabilities
        if not probabilities:
            return True
        ordered = sorted((item.probability for item in probabilities), reverse=True)
        return len(ordered) > 1 and ordered[0] < 0.75

    def assess(
        self,
        events: Iterable[FutureEvent],
        *,
        as_of: datetime | None = None,
        analysis_uncertainty: float | None = None,
        favorable_in_all_material_scenarios: bool = False,
    ) -> EventRiskGateResult:
        now = as_of or datetime.now(UTC)
        now = now.replace(tzinfo=UTC) if now.tzinfo is None else now.astimezone(UTC)
        material: list[FutureEvent] = []
        for event in events:
            if event.importance is not EventImportance.CRITICAL:
                continue
            status = event.runtime_status(now)
            active_unscheduled = (
                event.scheduled_at is None
                and status in {FutureEventStatus.ACTIVE, FutureEventStatus.SURPRISE}
            )
            imminent = (
                event.scheduled_at is not None
                and timedelta(0) <= event.scheduled_at - now <= self.window
            )
            high_amplitude = event.magnitude_effect in {
                ExpectedMovement.HIGH,
                ExpectedMovement.EXTREME,
            }
            if (active_unscheduled or imminent) and high_amplitude and self._uncertain(
                event, analysis_uncertainty
            ):
                material.append(event)

        if not material:
            return EventRiskGateResult(active=False, level=EventRiskLevel.LOW)

        reasons = [
            (
                f"{event.title}: événement critique à forte amplitude dans moins de 48 h; "
                "distribution incertaine ou non disponible."
            )
            for event in material
        ]
        if favorable_in_all_material_scenarios:
            return EventRiskGateResult(
                active=False,
                level=EventRiskLevel.HIGH,
                reasons=reasons,
                event_ids=[event.id for event in material],
                bypassed=True,
            )
        return EventRiskGateResult(
            active=True,
            level=(
                EventRiskLevel.EXTREME
                if any(event.magnitude_effect is ExpectedMovement.EXTREME for event in material)
                else EventRiskLevel.HIGH
            ),
            reasons=reasons,
            event_ids=[event.id for event in material],
        )


class ScenarioKind(StrEnum):
    BASE_CASE = "base_case"
    BULLISH_CASE = "bullish_case"
    BEARISH_CASE = "bearish_case"
    TAIL_RISK_CASE = "tail_risk_case"


@dataclass(slots=True)
class FutureScenario:
    kind: ScenarioKind
    probability: float | None
    probability_source: str | None
    probability_observed_at: str | None
    event_chain: list[str]
    directional_bias: DirectionalBias
    expected_movement: ExpectedMovement
    confidence: float
    invalidation_conditions: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.kind.value,
            "probability": self.probability,
            "probability_source": self.probability_source,
            "probability_observed_at": self.probability_observed_at,
            "event_chain": self.event_chain,
            "directional_bias": self.directional_bias.value,
            "expected_movement": self.expected_movement.value,
            "confidence": round(max(0.0, min(1.0, self.confidence)), 3),
            "invalidation_conditions": self.invalidation_conditions,
        }


_MOVEMENT_ORDER = {
    ExpectedMovement.LOW: 0,
    ExpectedMovement.NORMAL: 1,
    ExpectedMovement.HIGH: 2,
    ExpectedMovement.EXTREME: 3,
}


def _max_movement(values: Iterable[ExpectedMovement | None]) -> ExpectedMovement:
    present = [item for item in values if item is not None]
    return max(present, key=_MOVEMENT_ORDER.__getitem__) if present else ExpectedMovement.NORMAL


def _dominant_family(families: FiveFamilySnapshot) -> FamilyAssessment | None:
    candidates = [
        assessment
        for assessment in families.assessments.values()
        if assessment.available
        and assessment.directional_bias
        not in {None, DirectionalBias.NEUTRAL}
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda item: (FAMILY_PRIORITY[item.family], -item.confidence))
    first_priority = FAMILY_PRIORITY[candidates[0].family]
    peers = [item for item in candidates if FAMILY_PRIORITY[item.family] == first_priority]
    directions = {
        "bull" if "BULLISH" in item.directional_bias.value else "bear" for item in peers
    }
    if len(directions) > 1:
        return None
    return peers[0]


class FutureScenarioEngine:
    """Build four named scenarios without manufacturing probabilities."""

    def build(
        self,
        events: Iterable[FutureEvent],
        families: FiveFamilySnapshot,
        *,
        horizon: DecisionHorizon = DecisionHorizon.D7,
        as_of: datetime | None = None,
        scenario_probabilities: dict[ScenarioKind, dict[str, Any]] | None = None,
    ) -> list[FutureScenario]:
        now = as_of or datetime.now(UTC)
        horizon_delta = {
            DecisionHorizon.H24: timedelta(hours=24),
            DecisionHorizon.D7: timedelta(days=7),
            DecisionHorizon.D30: timedelta(days=30),
        }[horizon]
        upcoming = sorted(
            (
                event
                for event in events
                if event.scheduled_at is None
                or now <= event.scheduled_at <= now + horizon_delta
            ),
            key=lambda event: (
                -event.importance.rank,
                event.scheduled_at or event.detected_at,
            ),
        )
        chain = []
        for event in upcoming[:3]:
            chain.append(event.title)
            chain.extend(event.causal_chain[:2])
        if not chain:
            chain = ["Aucun catalyseur futur sourcé dans cet horizon."]

        dominant = _dominant_family(families)
        base_direction = dominant.directional_bias if dominant else DirectionalBias.NEUTRAL
        movement = _max_movement(
            [event.magnitude_effect for event in upcoming]
            + [item.expected_movement for item in families.assessments.values()]
        )
        available = [item for item in families.assessments.values() if item.available]
        confidence = (
            sum(item.confidence for item in available) / len(available)
            if available
            else 0.0
        )

        specs = {
            ScenarioKind.BASE_CASE: (
                base_direction,
                movement,
                chain,
                ["Un catalyseur prioritaire change de sens ou d'amplitude."],
            ),
            ScenarioKind.BULLISH_CASE: (
                DirectionalBias.BULLISH,
                movement,
                ["Catalyseurs sourcés résolus favorablement", "Confirmation par les flux"],
                ["Flux institutionnels se retournent durablement à la baisse."],
            ),
            ScenarioKind.BEARISH_CASE: (
                DirectionalBias.BEARISH,
                movement,
                ["Catalyseurs sourcés résolus défavorablement", "Pression confirmée par les flux"],
                ["Le risque événementiel se dissipe et les flux redeviennent positifs."],
            ),
            ScenarioKind.TAIL_RISK_CASE: (
                DirectionalBias.NEUTRAL,
                ExpectedMovement.EXTREME,
                ["Choc systémique non directionnel non inclus dans le scénario de base"],
                ["Absence de choc systémique pendant l'horizon."],
            ),
        }
        if scenario_probabilities:
            if set(scenario_probabilities) != set(ScenarioKind):
                raise ValueError("scenario probabilities must cover all four scenarios")
            probability_sum = sum(
                float(item["probability"]) for item in scenario_probabilities.values()
            )
            if not 0.98 <= probability_sum <= 1.02:
                raise ValueError("scenario probabilities must sum to one")
        output: list[FutureScenario] = []
        for kind in ScenarioKind:
            probability = None
            source = None
            observed_at = None
            raw_probability = (scenario_probabilities or {}).get(kind)
            if raw_probability:
                probability = float(raw_probability["probability"])
                source = str(raw_probability["source"])
                observed_at = str(raw_probability["observed_at"])
                if not 0.0 <= probability <= 1.0 or not source or not observed_at:
                    raise ValueError("scenario probability requires value, source and observed_at")
            direction, amplitude, event_chain, invalidations = specs[kind]
            output.append(
                FutureScenario(
                    kind=kind,
                    probability=probability,
                    probability_source=source,
                    probability_observed_at=observed_at,
                    event_chain=event_chain,
                    directional_bias=direction,
                    expected_movement=amplitude,
                    confidence=confidence if kind is ScenarioKind.BASE_CASE else confidence * 0.75,
                    invalidation_conditions=invalidations,
                )
            )
        return output


@dataclass(slots=True)
class FutureDecision:
    asset: Asset
    as_of: datetime
    horizon: DecisionHorizon
    decision: DecisionAction
    directional_bias: DirectionalBias
    expected_movement: ExpectedMovement
    decision_confidence: float
    event_risk: EventRiskGateResult
    next_major_event: FutureEvent | None
    reasons: list[dict[str, Any]]
    counter_signals: list[dict[str, Any]]
    scenarios: list[FutureScenario]
    what_could_change_decision: list[str]
    families: FiveFamilySnapshot
    provenance: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset": self.asset.value,
            "as_of": self.as_of.isoformat(),
            "horizon": self.horizon.value,
            "decision": self.decision.value,
            "directional_bias": self.directional_bias.value,
            "expected_movement": self.expected_movement.value,
            "decision_confidence": round(self.decision_confidence, 3),
            "event_risk": self.event_risk.to_dict(),
            "next_major_event": (
                self.next_major_event.to_public_dict(self.as_of)
                if self.next_major_event
                else None
            ),
            "reasons": self.reasons[:5],
            "counter_signals": self.counter_signals[:5],
            "scenarios": [item.to_dict() for item in self.scenarios],
            "what_could_change_decision": self.what_could_change_decision[:5],
            "families": self.families.to_dict(),
            "provenance": self.provenance,
            "disclaimer": "Analyse de risque déterministe; aucun ordre n'est exécuté.",
        }


def _is_bullish(direction: DirectionalBias | None) -> bool:
    return direction in {DirectionalBias.BULLISH, DirectionalBias.STRONGLY_BULLISH}


def _is_bearish(direction: DirectionalBias | None) -> bool:
    return direction in {DirectionalBias.BEARISH, DirectionalBias.STRONGLY_BEARISH}


class FutureDecisionEngine:
    """Make an auditable BUY/WAIT/SELL decision in strict priority order."""

    def decide(
        self,
        asset: Asset,
        events: Iterable[FutureEvent],
        families: FiveFamilySnapshot,
        *,
        horizon: DecisionHorizon = DecisionHorizon.D7,
        as_of: datetime | None = None,
        analysis_uncertainty: float | None = None,
    ) -> FutureDecision:
        now = as_of or datetime.now(UTC)
        now = now.replace(tzinfo=UTC) if now.tzinfo is None else now.astimezone(UTC)
        event_list = list(events)
        gate = EventRiskGate().assess(
            event_list,
            as_of=now,
            analysis_uncertainty=analysis_uncertainty,
        )
        scenarios = FutureScenarioEngine().build(
            event_list, families, horizon=horizon, as_of=now
        )
        dominant = _dominant_family(families)
        direction = dominant.directional_bias if dominant else DirectionalBias.NEUTRAL
        expected_movement = _max_movement(
            [item.expected_movement for item in families.assessments.values()]
            + [
                event.magnitude_effect
                for event in event_list
                if event.scheduled_at is None or event.scheduled_at >= now
            ]
        )

        available = [item for item in families.assessments.values() if item.available]
        coverage = len(available) / 5
        confidence = (
            sum(item.confidence for item in available) / len(available) * coverage
            if available
            else 0.0
        )
        if len(available) < 2:
            action = DecisionAction.INSUFFICIENT_DATA
        elif gate.active:
            action = DecisionAction.WAIT
        elif _is_bullish(direction):
            action = DecisionAction.BUY
        elif _is_bearish(direction):
            action = DecisionAction.SELL
        else:
            action = DecisionAction.WAIT

        ordered = sorted(
            available,
            key=lambda item: (FAMILY_PRIORITY[item.family], -item.confidence),
        )
        reasons: list[dict[str, Any]] = []
        if gate.active:
            event_by_id = {event.id: event for event in event_list}
            for event_id, text in zip(gate.event_ids, gate.reasons, strict=False):
                event = event_by_id[event_id]
                reasons.append(
                    {
                        "icon": "calendar-alert",
                        "title": event.title,
                        "date_time": (
                            event.scheduled_at.isoformat()
                            if event.scheduled_at
                            else event.detected_at.isoformat()
                        ),
                        "impact": event.magnitude_effect.value,
                        "explanation": text,
                        "source": event.source,
                        "source_url": event.source_url,
                        "evidence_ids": event.evidence_ids,
                    }
                )
        for item in ordered:
            if len(reasons) >= 5:
                break
            source = item.sources[0] if item.sources else {}
            reasons.append(
                {
                    "icon": "signal",
                    "title": FAMILY_LABELS[item.family],
                    "date_time": item.as_of,
                    "impact": (
                        item.expected_movement.value if item.expected_movement else None
                    ),
                    "explanation": item.summary,
                    "source": source.get("source"),
                    "source_url": source.get("url"),
                    "evidence_ids": source.get("evidence_ids", []),
                }
            )

        counter_signals = []
        for item in ordered:
            if (_is_bullish(direction) and _is_bearish(item.directional_bias)) or (
                _is_bearish(direction) and _is_bullish(item.directional_bias)
            ):
                counter_signals.append(
                    {
                        "family": item.family.value,
                        "directional_bias": item.directional_bias.value,
                        "explanation": item.summary,
                        "sources": item.sources,
                    }
                )

        future_scheduled = [
            event
            for event in event_list
            if event.scheduled_at is not None and event.scheduled_at >= now
        ]
        next_event = min(
            future_scheduled,
            key=lambda event: (event.scheduled_at, -event.importance.rank),
            default=None,
        )
        changes = []
        if gate.active:
            changes.append("Attendre la publication et réévaluer la surprise observée.")
        changes.extend(scenarios[0].invalidation_conditions)
        if families.available_count < 5:
            changes.append("Rétablir les familles indisponibles avec des données actuelles et sourcées.")

        provenance: list[dict[str, Any]] = []
        seen: set[tuple[str | None, str | None]] = set()
        for event in event_list:
            key = (event.source, event.source_url)
            if key not in seen:
                seen.add(key)
                provenance.append(
                    {
                        "source": event.source,
                        "tier": event.source_tier.value,
                        "url": event.source_url,
                        "last_updated": event.last_updated.isoformat(),
                        "evidence_ids": event.evidence_ids,
                    }
                )
        for item in families.assessments.values():
            for source in item.sources:
                key = (source.get("source"), source.get("url"))
                if key not in seen:
                    seen.add(key)
                    provenance.append(source)

        return FutureDecision(
            asset=asset,
            as_of=now,
            horizon=horizon,
            decision=action,
            directional_bias=direction,
            expected_movement=expected_movement,
            decision_confidence=confidence,
            event_risk=gate,
            next_major_event=next_event,
            reasons=reasons,
            counter_signals=counter_signals,
            scenarios=scenarios,
            what_could_change_decision=list(dict.fromkeys(changes)),
            families=families,
            provenance=provenance,
        )


_HORIZON_DAYS = {
    DecisionHorizon.H24: 1,
    DecisionHorizon.D7: 7,
    DecisionHorizon.D30: 30,
}


def horizon_decisions(
    engine: FutureDecisionEngine,
    asset: Asset,
    events: Iterable[FutureEvent],
    families: FiveFamilySnapshot,
    *,
    as_of: datetime,
    analysis_uncertainty: float | None,
) -> dict[str, dict[str, Any]]:
    """Return independent 24h/7d/30d decisions from one timestamp."""
    event_list = list(events)
    output: dict[str, dict[str, Any]] = {}
    for horizon, days in _HORIZON_DAYS.items():
        cutoff = as_of + timedelta(days=days)
        relevant = [
            event
            for event in event_list
            if event.scheduled_at is None or event.scheduled_at <= cutoff
        ]
        result = engine.decide(
            asset,
            relevant,
            families,
            horizon=horizon,
            as_of=as_of,
            analysis_uncertainty=analysis_uncertainty,
        )
        output[horizon.value] = {
            "decision": result.decision.value,
            "directional_bias": result.directional_bias.value,
            "expected_movement": result.expected_movement.value,
            "decision_confidence": round(result.decision_confidence, 3),
            "event_risk": result.event_risk.level.value,
        }
    return output

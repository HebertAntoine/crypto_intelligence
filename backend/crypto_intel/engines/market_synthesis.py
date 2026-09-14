"""Turn family readings into an answer a reader can act on in twenty seconds.

The structure follows one discipline: every claim is paired with what would
contradict it. A market state is never published without the evidence that
argues the other way, because a synthesis that only collects agreeing facts is
how confirmation bias gets encoded into software.

Three ideas are kept strictly apart, and conflating them is the most common way
these systems mislead:

* **risk** - conditions that make a move possible;
* **trigger** - the event that could set it off;
* **confirmation** - proof the move has actually begun.

High risk is not a correction. A correction is confirmed when the confirmation
conditions are met, not when the risk conditions look frightening.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from .factor_semantics import (
    Availability,
    FactorAssessment,
    FactorDirection,
    FactorImpact,
)


class MarketState(StrEnum):
    CALM = "CALM"
    CONSTRUCTIVE = "CONSTRUCTIVE"
    MIXED = "MIXED"
    ELEVATED_RISK = "ELEVATED_RISK"
    CORRECTION_CONFIRMED = "CORRECTION_CONFIRMED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class Uncertainty(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"


#: Qualitative bands, used because no calibrated model backs a percentage.
class Likelihood(StrEnum):
    LOW = "FAIBLE"
    MODERATE = "MODÉRÉ"
    HIGH = "ÉLEVÉ"
    VERY_HIGH = "TRÈS ÉLEVÉ"
    NOT_ASSESSABLE = "NON ÉVALUABLE"


_STATE_LABEL = {
    MarketState.CALM: "🟢 MARCHÉ CALME",
    MarketState.CONSTRUCTIVE: "🟢 CONTEXTE PORTEUR",
    MarketState.MIXED: "🟡 SIGNAUX PARTAGÉS",
    MarketState.ELEVATED_RISK: "🟠 RISQUE ÉLEVÉ",
    MarketState.CORRECTION_CONFIRMED: "🔴 CORRECTION CONFIRMÉE",
    MarketState.INSUFFICIENT_DATA: "⚪ DONNÉES INSUFFISANTES",
}

_IMPACT_WEIGHT = {
    FactorImpact.LOW: 1,
    FactorImpact.MODERATE: 2,
    FactorImpact.HIGH: 3,
    FactorImpact.VERY_HIGH: 4,
}


@dataclass(slots=True, frozen=True)
class Condition:
    """One checkable condition, with the weight it carries.

    Weight exists so that the list is never read as a naive vote: four minor
    conditions do not outweigh one that matters.
    """

    text: str
    met: bool
    weight: int = 1
    evidence: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "met": self.met,
            "weight": self.weight,
            "evidence": self.evidence,
        }


@dataclass(slots=True, frozen=True)
class Scenario:
    name: str
    description: str
    likelihood: Likelihood
    likelihood_basis: str = "HEURISTIC_ASSESSMENT"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "likelihood": self.likelihood.value,
            # Never a percentage: no calibrated model produces one here, and a
            # number would claim a precision that does not exist.
            "likelihood_basis": self.likelihood_basis,
        }


@dataclass(slots=True, frozen=True)
class MarketSynthesis:
    state: MarketState
    headline: str
    summary: str
    why_now: list[dict[str, Any]] = field(default_factory=list)
    counter_evidence: list[dict[str, Any]] = field(default_factory=list)
    confirmation_conditions: list[Condition] = field(default_factory=list)
    invalidation_conditions: list[Condition] = field(default_factory=list)
    main_scenario: Scenario | None = None
    alternative_scenario: Scenario | None = None
    upcoming_events: list[dict[str, Any]] = field(default_factory=list)
    uncertainty: Uncertainty = Uncertainty.MEDIUM
    missing_families: list[str] = field(default_factory=list)
    #: AVAILABLE / PARTIAL_DATA - the screen must be able to say when a family
    #: is missing rather than presenting a degraded reading as a complete one.
    data_status: str = "AVAILABLE"
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def confirmation_met(self) -> tuple[int, int]:
        return (
            sum(1 for item in self.confirmation_conditions if item.met),
            len(self.confirmation_conditions),
        )

    def to_dict(self) -> dict[str, Any]:
        met, total = self.confirmation_met
        return {
            "state": self.state.value,
            "state_label": _STATE_LABEL[self.state],
            "headline": self.headline,
            "summary": self.summary,
            "why_now": self.why_now,
            "counter_evidence": self.counter_evidence,
            "confirmation_conditions": [item.to_dict() for item in self.confirmation_conditions],
            "confirmation_met": f"{met}/{total}",
            "invalidation_conditions": [item.to_dict() for item in self.invalidation_conditions],
            "main_scenario": self.main_scenario.to_dict() if self.main_scenario else None,
            "alternative_scenario": (
                self.alternative_scenario.to_dict() if self.alternative_scenario else None
            ),
            "upcoming_events": self.upcoming_events,
            "uncertainty": self.uncertainty.value,
            "missing_families": self.missing_families,
            "data_status": self.data_status,
            "generated_at": self.generated_at.isoformat(),
            "methodology": (
                "Le risque décrit ce qui rend un mouvement possible; la "
                "confirmation décrit la preuve qu'il a commencé. Un risque élevé "
                "n'est pas une correction."
            ),
        }


class MarketSynthesisEngine:
    """Deterministic synthesis. No language model is involved in the verdict.

    A model may later rephrase the output, but the state, the conditions and the
    scenarios are computed here from measured readings, so the system keeps
    working when no model is reachable.
    """

    #: Below this many usable families, no strong claim is defensible.
    MIN_FAMILIES = 3

    def synthesize(
        self,
        factors: list[FactorAssessment],
        *,
        next_events: list[dict[str, Any]] | None = None,
        upcoming_events: list[dict[str, Any]] | None = None,
        asset: str = "",
        now: datetime | None = None,
    ) -> MarketSynthesis:
        reference = now or datetime.now(UTC)
        usable = [
            item
            for item in factors
            if item.availability in {Availability.AVAILABLE, Availability.STALE}
            and item.direction is not FactorDirection.UNKNOWN
        ]
        missing = [
            item.label
            for item in factors
            if item.availability
            in {Availability.UNAVAILABLE, Availability.NOT_APPLICABLE}
        ]

        if len(usable) < self.MIN_FAMILIES:
            return MarketSynthesis(
                state=MarketState.INSUFFICIENT_DATA,
                headline="Données insuffisantes pour conclure",
                summary=(
                    f"Seule(s) {len(usable)} lecture(s) exploitable(s) sur "
                    f"{len(factors)}. Aucune affirmation forte n'est défendable "
                    "dans cet état."
                ),
                counter_evidence=[],
                upcoming_events=list(upcoming_events or []),
                uncertainty=Uncertainty.VERY_HIGH,
                missing_families=missing,
                data_status="PARTIAL_DATA",
                generated_at=reference,
            )

        negative = [item for item in usable if item.direction is FactorDirection.NEGATIVE]
        positive = [item for item in usable if item.direction is FactorDirection.POSITIVE]
        negative_weight = sum(_IMPACT_WEIGHT[item.impact] for item in negative)
        positive_weight = sum(_IMPACT_WEIGHT[item.impact] for item in positive)

        confirmation = self._confirmation_conditions(usable)
        invalidation = self._invalidation_conditions(usable)
        met_weight = sum(item.weight for item in confirmation if item.met)
        total_weight = sum(item.weight for item in confirmation) or 1

        state = self._state(
            negative_weight=negative_weight,
            positive_weight=positive_weight,
            confirmation_ratio=met_weight / total_weight,
        )

        why_now = [self._evidence_entry(item) for item in self._rank(negative)[:5]]
        # The section that exists to argue against the state. When nothing
        # genuinely argues the other way it must say so: an empty block reads as
        # "not checked", which is the opposite of the point.
        counter = [self._evidence_entry(item) for item in self._rank(positive)[:4]]
        if not counter:
            counter = [
                {
                    "label": "Aucune contre-preuve mesurée",
                    "direction": "NEUTRAL",
                    "impact": "LOW",
                    "observation": (
                        "Aucune des familles disponibles ne va actuellement à "
                        "l'encontre de cette lecture."
                    ),
                    "why_it_matters": (
                        "L'absence de contradiction renforce la lecture, mais "
                        f"{len(missing)} famille(s) restent indisponibles."
                        if missing
                        else "L'absence de contradiction renforce la lecture."
                    ),
                    "reliability": "LOW",
                    "freshness": "",
                    "source": "",
                }
            ]

        return MarketSynthesis(
            state=state,
            headline=self._headline(state, negative, positive),
            summary=self._summary(state, negative, positive, next_events or []),
            why_now=why_now,
            counter_evidence=counter,
            confirmation_conditions=confirmation,
            invalidation_conditions=invalidation,
            main_scenario=self._main_scenario(state),
            alternative_scenario=self._alternative_scenario(state),
            upcoming_events=list(upcoming_events or []),
            uncertainty=self._uncertainty(usable, missing, negative, positive),
            missing_families=missing,
            # Missing families never become a neutral stance: the state is
            # published with the gap declared beside it.
            data_status="PARTIAL_DATA" if missing else "AVAILABLE",
            generated_at=reference,
        )

    # -- internals ----------------------------------------------------------

    @staticmethod
    def _rank(items: list[FactorAssessment]) -> list[FactorAssessment]:
        return sorted(items, key=lambda item: (-_IMPACT_WEIGHT[item.impact], item.label))

    @staticmethod
    def _evidence_entry(item: FactorAssessment) -> dict[str, Any]:
        return {
            "label": item.label,
            "direction": item.direction.value,
            "impact": item.impact.value,
            "observation": item.rationale,
            "why_it_matters": item.causal_chain[-1] if item.causal_chain else "",
            "reliability": item.confidence_band.value,
            "freshness": item.freshness,
            "source": item.provider,
        }

    def _state(
        self, *, negative_weight: int, positive_weight: int, confirmation_ratio: float
    ) -> MarketState:
        """Risk and confirmation are separate axes, deliberately.

        A market can carry heavy negative weight and still not be correcting.
        Only the confirmation conditions promote ELEVATED_RISK into
        CORRECTION_CONFIRMED.
        """

        if negative_weight > positive_weight:
            if confirmation_ratio >= 0.7:
                return MarketState.CORRECTION_CONFIRMED
            # Magnitude matters as much as the gap. Judging on the difference
            # alone rated two high-impact negative forces as merely "mixed"
            # because two moderate positives pushed back - which is exactly the
            # situation the phrase "elevated risk" describes.
            material = negative_weight >= 5
            if material or negative_weight - positive_weight >= 3:
                return MarketState.ELEVATED_RISK
            return MarketState.MIXED
        if positive_weight - negative_weight >= 3:
            return MarketState.CONSTRUCTIVE
        if positive_weight > negative_weight:
            return MarketState.MIXED
        return MarketState.MIXED

    def _confirmation_conditions(self, usable: list[FactorAssessment]) -> list[Condition]:
        """Proof a move has started, one checkable line per family present."""

        by_key = {item.key: item for item in usable}
        conditions: list[Condition] = []

        def add(key: str, text: str, weight: int, met: bool, evidence: str = "") -> None:
            if key in by_key:
                conditions.append(Condition(text=text, met=met, weight=weight, evidence=evidence))

        credit = by_key.get("credit")
        add(
            "credit",
            "Les écarts de crédit se tendent nettement",
            3,
            credit is not None and credit.direction is FactorDirection.NEGATIVE,
            credit.rationale if credit else "",
        )
        flows = by_key.get("flows")
        add(
            "flows",
            "Les sorties des ETF s'accélèrent",
            3,
            flows is not None and flows.direction is FactorDirection.NEGATIVE,
            flows.rationale if flows else "",
        )
        technical = by_key.get("technical")
        add(
            "technical",
            "La structure de prix casse à la baisse",
            2,
            technical is not None and technical.direction is FactorDirection.NEGATIVE,
            technical.rationale if technical else "",
        )
        rates = by_key.get("rates")
        add(
            "rates",
            "Les rendements restent durablement élevés",
            2,
            rates is not None and rates.direction is FactorDirection.NEGATIVE,
            rates.rationale if rates else "",
        )
        energy = by_key.get("energy")
        add(
            "energy",
            "L'énergie continue de progresser",
            1,
            energy is not None and energy.direction is FactorDirection.NEGATIVE,
            energy.rationale if energy else "",
        )
        positioning = by_key.get("positioning")
        add(
            "positioning",
            "Le positionnement à levier se dénoue",
            2,
            positioning is not None and positioning.direction is FactorDirection.NEGATIVE,
            positioning.rationale if positioning else "",
        )
        return conditions

    def _invalidation_conditions(self, usable: list[FactorAssessment]) -> list[Condition]:
        """What would take weight away from the bearish reading."""

        by_key = {item.key: item for item in usable}
        conditions: list[Condition] = []
        specs = [
            ("rates", "Les rendements se détendent", 2),
            ("energy", "Le pétrole reflue", 1),
            ("flows", "Les flux ETF redeviennent positifs", 3),
            ("technical", "Le prix reprend sa résistance", 2),
            ("credit", "Le crédit reste calme", 3),
        ]
        for key, text, weight in specs:
            item = by_key.get(key)
            if item is None:
                continue
            conditions.append(
                Condition(
                    text=text,
                    met=item.direction is FactorDirection.POSITIVE,
                    weight=weight,
                    evidence=item.rationale,
                )
            )
        return conditions

    @staticmethod
    def _headline(
        state: MarketState,
        negative: list[FactorAssessment],
        positive: list[FactorAssessment],
    ) -> str:
        if state is MarketState.CORRECTION_CONFIRMED:
            return "Correction confirmée par plusieurs familles"
        if state is MarketState.ELEVATED_RISK:
            return "Risque de correction élevé, mais baisse majeure non confirmée"
        if state is MarketState.CONSTRUCTIVE:
            return "Contexte porteur, sans excès apparent"
        if state is MarketState.MIXED:
            return "Signaux partagés, aucune direction dominante"
        return "Marché calme"

    @staticmethod
    def _summary(
        state: MarketState,
        negative: list[FactorAssessment],
        positive: list[FactorAssessment],
        next_events: list[dict[str, Any]],
    ) -> str:
        parts: list[str] = []
        if negative:
            names = ", ".join(item.label.lower() for item in negative[:3])
            parts.append(f"Le contexte se dégrade du côté de {names}.")
        if positive:
            names = ", ".join(item.label.lower() for item in positive[:3])
            verb = (
                "ne montrent pas encore de dégradation suffisante pour confirmer"
                if state is MarketState.ELEVATED_RISK
                else "restent favorables"
            )
            parts.append(f"En revanche, {names} {verb}.")
        if next_events:
            # The catalysts are listed in their own section, where the screen
            # renders their French name. Embedding the raw official title here
            # pushed English wording into the summary the reader sees first.
            count = len(next_events)
            parts.append(
                f"{count} catalyseur(s) majeur(s) sont attendus sur cet horizon."
            )
        return " ".join(parts) or "Aucune lecture dominante."

    @staticmethod
    def _main_scenario(state: MarketState) -> Scenario:
        table = {
            MarketState.CORRECTION_CONFIRMED: (
                "Poursuite de la correction",
                "Les familles confirment une dégradation en cours.",
                Likelihood.HIGH,
            ),
            MarketState.ELEVATED_RISK: (
                "Consolidation fragile",
                "Le risque est élevé mais la baisse n'est pas confirmée; le "
                "marché reste suspendu aux prochains catalyseurs.",
                Likelihood.MODERATE,
            ),
            MarketState.CONSTRUCTIVE: (
                "Poursuite du mouvement porteur",
                "Les lectures favorables dominent sans excès mesuré.",
                Likelihood.MODERATE,
            ),
            MarketState.MIXED: (
                "Absence de direction",
                "Les familles se contredisent; aucune tendance ne domine.",
                Likelihood.MODERATE,
            ),
            MarketState.CALM: (
                "Statu quo",
                "Aucune tension mesurée.",
                Likelihood.MODERATE,
            ),
        }
        name, description, likelihood = table[state]
        return Scenario(name=name, description=description, likelihood=likelihood)

    @staticmethod
    def _alternative_scenario(state: MarketState) -> Scenario:
        if state in {MarketState.CORRECTION_CONFIRMED, MarketState.ELEVATED_RISK}:
            return Scenario(
                name="Reprise",
                description=(
                    "Détente des rendements, reflux de l'énergie et retour des "
                    "flux acheteurs suffiraient à retirer du poids au scénario "
                    "baissier."
                ),
                likelihood=Likelihood.LOW,
            )
        return Scenario(
            name="Dégradation",
            description=(
                "Une remontée des rendements ou une tension du crédit "
                "renverserait la lecture actuelle."
            ),
            likelihood=Likelihood.LOW,
        )

    @staticmethod
    def _uncertainty(
        usable: list[FactorAssessment],
        missing: list[str],
        negative: list[FactorAssessment],
        positive: list[FactorAssessment],
    ) -> Uncertainty:
        if len(missing) >= 3:
            return Uncertainty.VERY_HIGH
        if negative and positive and min(len(negative), len(positive)) >= 2:
            return Uncertainty.HIGH
        if missing:
            return Uncertainty.MEDIUM
        return Uncertainty.LOW if len(usable) >= 5 else Uncertainty.MEDIUM

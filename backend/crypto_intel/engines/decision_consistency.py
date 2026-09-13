"""Refuse to publish a decision that contradicts its own evidence.

Every check here answers one question: would a careful reader, shown the
decision next to the evidence beside it, conclude the two disagree? When they
would, the decision is degraded and the reason is recorded. Nothing is ever
hidden: a downgrade always carries the code and the detail that caused it.

The validator never *raises* conviction. It can only move a directional call
towards WAIT, or WAIT towards INSUFFICIENT_DATA. A decision it cannot fault is
returned untouched.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..future_events.models import DirectionalBias, EventImportance, ExpectedMovement
from .future_decision import (
    DecisionAction,
    EventRiskLevel,
    FamilyAssessment,
    FiveFamilySnapshot,
    FutureEvent,
    FutureFamily,
)

#: Below this, the engine is not confident enough to carry a directional call
#: across an unresolved Tier-1 event.
CONFIDENT_ENOUGH = 0.75

_BULLISH = {DirectionalBias.BULLISH, DirectionalBias.STRONGLY_BULLISH}
_BEARISH = {DirectionalBias.BEARISH, DirectionalBias.STRONGLY_BEARISH}
_MATERIAL_IMPORTANCE = {EventImportance.HIGH, EventImportance.CRITICAL}
_MATERIAL_MOVEMENT = {ExpectedMovement.HIGH, ExpectedMovement.EXTREME}


@dataclass(slots=True, frozen=True)
class ConsistencyIssue:
    code: str
    detail: str
    downgraded_to: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "detail": self.detail,
            "downgraded_to": self.downgraded_to,
        }


@dataclass(slots=True)
class ConsistencyReport:
    action: DecisionAction
    issues: list[ConsistencyIssue] = field(default_factory=list)

    @property
    def degraded(self) -> bool:
        return any(issue.downgraded_to for issue in self.issues)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": "DEGRADED" if self.degraded else ("FLAGGED" if self.issues else "OK"),
            "action": self.action.value,
            "issues": [issue.to_dict() for issue in self.issues],
            "methodology": (
                "Chaque contrôle compare la décision aux preuves affichées à côté "
                "d'elle. Un contrôle ne peut que dégrader vers ATTENDRE ou "
                "DONNÉES INSUFFISANTES, jamais renforcer une conviction."
            ),
        }


def _directional_families(families: FiveFamilySnapshot) -> list[FamilyAssessment]:
    return [
        item
        for item in families.assessments.values()
        if item.available
        and item.directional_bias not in {None, DirectionalBias.NEUTRAL}
        and item.confidence > 0
    ]


def blocking_events(events: list[FutureEvent], *, priced: bool) -> list[FutureEvent]:
    """Tier-1 events whose outcome is material and still unknown.

    Direction is deliberately not inferred from the event type, so an event
    with a neutral directional effect and no market pricing is *unknown*, not
    neutral. That is exactly the case a BUY must not be carried across.
    """

    if priced:
        return []
    return [
        event
        for event in events
        if event.importance in _MATERIAL_IMPORTANCE
        and event.magnitude_effect in _MATERIAL_MOVEMENT
        and event.directional_effect is DirectionalBias.NEUTRAL
    ]


class DecisionConsistencyValidator:
    """Run every coherence check and return the decision that survives them."""

    def validate(
        self,
        action: DecisionAction,
        *,
        direction: DirectionalBias,
        confidence: float,
        event_risk_level: EventRiskLevel,
        horizon_events: list[FutureEvent],
        families: FiveFamilySnapshot,
        expectations_available: bool,
        asymmetry_is_favorable: bool = False,
        institutional_flow: Any = None,
    ) -> ConsistencyReport:
        issues: list[ConsistencyIssue] = []
        result = action

        # 1. A directional call carried across an unresolved Tier-1 event.
        #
        # "Fed bientôt" alone never forces WAIT. What forces it is the whole
        # combination: a material event, an outcome nobody has priced, a large
        # potential move, and a confidence that is only middling. BUY stays
        # available if the scenarios demonstrate a robust favourable asymmetry.
        blocking = blocking_events(horizon_events, priced=expectations_available)
        risky = event_risk_level in {EventRiskLevel.HIGH, EventRiskLevel.EXTREME}
        if (
            result in {DecisionAction.BUY, DecisionAction.SELL}
            and blocking
            and risky
            and confidence < CONFIDENT_ENOUGH
            and not asymmetry_is_favorable
        ):
            titles = ", ".join(event.title for event in blocking[:2])
            issues.append(
                ConsistencyIssue(
                    code="UNRESOLVED_TIER1_EVENT",
                    detail=(
                        f"{titles}: impact matériel, issue non valorisée et "
                        f"confiance {confidence:.2f} insuffisante; aucune asymétrie "
                        "favorable robuste n'est démontrée."
                    ),
                    downgraded_to=DecisionAction.WAIT.value,
                )
            )
            result = DecisionAction.WAIT

        # 2. A directional call whose own families mostly point the other way.
        directional = _directional_families(families)
        if result in {DecisionAction.BUY, DecisionAction.SELL} and directional:
            supporting = sum(
                1
                for item in directional
                if (item.directional_bias in _BULLISH) == (result is DecisionAction.BUY)
            )
            if supporting * 2 < len(directional):
                issues.append(
                    ConsistencyIssue(
                        code="MAJORITY_CONTRADICTS_ACTION",
                        detail=(
                            f"{len(directional) - supporting} famille(s) sur "
                            f"{len(directional)} vont contre {result.value}."
                        ),
                        downgraded_to=DecisionAction.WAIT.value,
                    )
                )
                result = DecisionAction.WAIT

        # 3. An institutional-flow direction that its own recent window denies.
        flow = families.assessments.get(FutureFamily.FLOWS_WHALES)
        if flow is not None and flow.available and institutional_flow is not None:
            recent = getattr(institutional_flow, "rolling_5_sessions_musd", None)
            regime = getattr(institutional_flow, "regime_total_musd", None)
            if (
                recent is not None
                and recent < 0
                and flow.directional_bias in _BULLISH
            ):
                justified = regime is not None and regime > 0 and "séances" in flow.summary
                if not justified:
                    issues.append(
                        ConsistencyIssue(
                            code="FLOW_SIGN_UNJUSTIFIED",
                            detail=(
                                f"Flux positifs annoncés alors que le cumul récent "
                                f"vaut {recent:+.1f} M$, sans fenêtre de mesure nommée."
                            ),
                            downgraded_to=DecisionAction.WAIT.value,
                        )
                    )
                    result = DecisionAction.WAIT

        # 4. An amplitude-only family must never carry a direction.
        technical = families.assessments.get(FutureFamily.TECHNICAL_VOLATILITY)
        if (
            technical is not None
            and technical.available
            and technical.confidence == 0
            and technical.directional_bias not in {None, DirectionalBias.NEUTRAL}
        ):
            issues.append(
                ConsistencyIssue(
                    code="AMPLITUDE_USED_AS_DIRECTION",
                    detail=(
                        "La famille technique publie une direction sans confiance "
                        "mesurée; une compression renseigne l'ampleur, pas le sens."
                    ),
                )
            )

        # 5. Nothing left to stand on.
        if result is DecisionAction.WAIT and not directional and not horizon_events:
            issues.append(
                ConsistencyIssue(
                    code="NO_USABLE_EVIDENCE",
                    detail="Aucune famille directionnelle et aucun événement dans l'horizon.",
                    downgraded_to=DecisionAction.INSUFFICIENT_DATA.value,
                )
            )
            result = DecisionAction.INSUFFICIENT_DATA

        return ConsistencyReport(action=result, issues=issues)

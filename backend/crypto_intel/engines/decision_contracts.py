"""Future-first decision contracts: confidence, stability, asymmetry, impact.

These four objects are deliberately **not wired** into the production
BUY/WAIT/SELL path. LOT 2 phase 12 requires them to be computable and tested
first, so every engine here is pure: it reads values another engine already
produced and never performs I/O, never reads a clock it was not given, and
never invents a probability, a percentage or a price target.

Four concepts stay strictly separate, per the LOT 2 central principle:

* ``DecisionAction``      - what to do (owned by the existing decision engine)
* ``DecisionConfidence``  - how well-founded that choice is, given the evidence
* ``ExpectedMovement``    - how much the asset may move, direction-free
* ``DecisionImpactAssessment`` - what follows if the reading proves correct

Confidence is not a probability. HIGH confidence on BUY does not mean "80 %
chance the asset rises"; it means the available evidence converges on BUY and
the inputs behind it are sound.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from ..future_events.models import DecisionHorizon, DirectionalBias, ExpectedMovement
from .contradiction_resolver import ContradictionState
from .future_decision import (
    DecisionAction,
    EventRiskLevel,
    FutureScenario,
    ScenarioKind,
)
from .signal_convergence import SignalConvergence


class ConfidenceLevel(StrEnum):
    VERY_LOW = "VERY_LOW"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"


class StabilityLevel(StrEnum):
    ROBUST = "ROBUST"
    MODERATE = "MODERATE"
    FRAGILE = "FRAGILE"
    UNKNOWN = "UNKNOWN"


class RiskAsymmetry(StrEnum):
    STRONGLY_FAVORABLE = "STRONGLY_FAVORABLE"
    FAVORABLE = "FAVORABLE"
    BALANCED = "BALANCED"
    UNFAVORABLE = "UNFAVORABLE"
    STRONGLY_UNFAVORABLE = "STRONGLY_UNFAVORABLE"
    UNKNOWN = "UNKNOWN"


_CONFIDENCE_ORDER: tuple[ConfidenceLevel, ...] = (
    ConfidenceLevel.VERY_LOW,
    ConfidenceLevel.LOW,
    ConfidenceLevel.MEDIUM,
    ConfidenceLevel.HIGH,
    ConfidenceLevel.VERY_HIGH,
)

_MOVEMENT_ORDER: dict[ExpectedMovement, int] = {
    ExpectedMovement.LOW: 0,
    ExpectedMovement.NORMAL: 1,
    ExpectedMovement.HIGH: 2,
    ExpectedMovement.EXTREME: 3,
}

_BULLISH = {DirectionalBias.BULLISH, DirectionalBias.STRONGLY_BULLISH}
_BEARISH = {DirectionalBias.BEARISH, DirectionalBias.STRONGLY_BEARISH}


def _sign(direction: DirectionalBias | None) -> int:
    if direction in _BULLISH:
        return 1
    if direction in _BEARISH:
        return -1
    return 0


# --------------------------------------------------------------------------
# Confidence
# --------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class ConfidenceFactor:
    """One auditable reason the confidence level moved, and by how many steps."""

    name: str
    steps: int
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "steps": self.steps, "detail": self.detail}


@dataclass(slots=True, frozen=True)
class DecisionConfidence:
    """How well-founded a decision is. Never a probability, never a percentage.

    ``numeric_score`` stays ``None`` until a calibration study exists. A number
    produced by averaging heterogeneous signals would look calibrated without
    being calibrated, which is exactly what LOT 2 forbids displaying.
    """

    level: ConfidenceLevel
    factors: list[ConfidenceFactor] = field(default_factory=list)
    is_calibrated: bool = False
    numeric_score: float | None = None
    methodology: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level.value,
            "factors": [item.to_dict() for item in self.factors],
            "is_calibrated": self.is_calibrated,
            "numeric_score": self.numeric_score,
            "not_a_probability": (
                "La confiance mesure la solidité des informations disponibles, "
                "pas la probabilité que le prix monte ou baisse."
            ),
            "methodology": self.methodology,
        }


class DecisionConfidenceEngine:
    """Derive a confidence level by explicit, auditable steps.

    The baseline comes from how many *independent* confirmations exist, then
    each defect removes steps. A ladder is used rather than a weighted average
    so every movement can be named in the UI and replayed in a test.
    """

    methodology = (
        "Baseline = number of independent confirmations (correlated factors "
        "count once). Deductions: contradictions, stale or missing inputs, "
        "unpriced event uncertainty, fragile decision. No numeric score is "
        "published until a calibration study exists."
    )

    def assess(
        self,
        *,
        convergence: SignalConvergence | None = None,
        contradiction_state: ContradictionState | None = None,
        event_risk_level: EventRiskLevel | None = None,
        gate_active: bool = False,
        expectations_available: bool = True,
        critical_missing_inputs: list[str] | None = None,
        stale_inputs: list[str] | None = None,
        missing_inputs: list[str] | None = None,
        stability: StabilityLevel | None = None,
        calibration: float | None = None,
    ) -> DecisionConfidence:
        critical_missing = list(critical_missing_inputs or [])
        factors: list[ConfidenceFactor] = []

        if critical_missing:
            return DecisionConfidence(
                level=ConfidenceLevel.VERY_LOW,
                factors=[
                    ConfidenceFactor(
                        name="critical_data_missing",
                        steps=-4,
                        detail="Entrées critiques indisponibles: " + ", ".join(critical_missing),
                    )
                ],
                methodology=self.methodology,
            )

        confirmations = convergence.independent_confirmation_count if convergence else 0
        index = min(confirmations, 4)
        factors.append(
            ConfidenceFactor(
                name="independent_confirmations",
                steps=index,
                detail=f"{confirmations} confirmation(s) indépendante(s).",
            )
        )

        if convergence and convergence.correlated_confirmation_reduction > 0:
            index -= 1
            factors.append(
                ConfidenceFactor(
                    name="correlated_signals",
                    steps=-1,
                    detail=(
                        f"{convergence.correlated_confirmation_reduction} signal(aux) "
                        "partagent une même cause et ne comptent pas deux fois."
                    ),
                )
            )

        if contradiction_state is ContradictionState.STRONGLY_MIXED:
            index -= 2
            factors.append(
                ConfidenceFactor(
                    name="contradiction",
                    steps=-2,
                    detail="Preuves fortement contradictoires entre familles.",
                )
            )
        elif contradiction_state is ContradictionState.MIXED:
            index -= 1
            factors.append(
                ConfidenceFactor(
                    name="contradiction",
                    steps=-1,
                    detail="Preuves partiellement contradictoires.",
                )
            )
        elif contradiction_state is ContradictionState.INSUFFICIENT_DATA:
            index -= 2
            factors.append(
                ConfidenceFactor(
                    name="contradiction",
                    steps=-2,
                    detail="Pas assez de signaux directionnels pour trancher.",
                )
            )

        degraded = list(stale_inputs or []) + list(missing_inputs or [])
        if degraded:
            index -= 1
            factors.append(
                ConfidenceFactor(
                    name="input_freshness",
                    steps=-1,
                    detail="Entrées périmées ou absentes: " + ", ".join(sorted(set(degraded))[:4]),
                )
            )

        high_event_risk = event_risk_level in {EventRiskLevel.HIGH, EventRiskLevel.EXTREME}
        if gate_active or (high_event_risk and not expectations_available):
            index -= 1
            factors.append(
                ConfidenceFactor(
                    name="event_uncertainty",
                    steps=-1,
                    detail=(
                        "Événement critique non résolu dans l'horizon, sans "
                        "valorisation de marché disponible."
                    ),
                )
            )

        if stability is StabilityLevel.FRAGILE:
            index -= 2
            factors.append(
                ConfidenceFactor(
                    name="stability",
                    steps=-2,
                    detail="La décision change dès qu'une hypothèse bouge légèrement.",
                )
            )
        elif stability is StabilityLevel.MODERATE:
            index -= 1
            factors.append(
                ConfidenceFactor(
                    name="stability",
                    steps=-1,
                    detail="La décision ne tient pas dans tous les scénarios.",
                )
            )

        index = max(0, min(len(_CONFIDENCE_ORDER) - 1, index))
        return DecisionConfidence(
            level=_CONFIDENCE_ORDER[index],
            factors=factors,
            is_calibrated=calibration is not None,
            numeric_score=calibration,
            methodology=self.methodology,
        )


# --------------------------------------------------------------------------
# Stability
# --------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class DecisionStability:
    """Whether BUY/WAIT/SELL survives small changes in the hypotheses."""

    level: StabilityLevel
    baseline_action: DecisionAction | None
    decision_across_scenarios: dict[str, str] = field(default_factory=dict)
    agreeing_scenarios: int = 0
    total_scenarios: int = 0
    flips_to_opposite: list[str] = field(default_factory=list)
    unknown_reason: str | None = None
    methodology: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level.value,
            "baseline_action": self.baseline_action.value if self.baseline_action else None,
            "decision_across_scenarios": self.decision_across_scenarios,
            "agreeing_scenarios": self.agreeing_scenarios,
            "total_scenarios": self.total_scenarios,
            "flips_to_opposite": self.flips_to_opposite,
            "unknown_reason": self.unknown_reason,
            "methodology": self.methodology,
        }


def action_for_scenario(scenario: FutureScenario, *, gate_active: bool = False) -> DecisionAction:
    """Map one scenario's own bias to the action it would imply, in isolation.

    This mirrors the production rule (gate first, then direction) so that the
    comparison is meaningful. It is a projection of the scenario, never a
    forecast that the scenario will happen.
    """

    if gate_active:
        return DecisionAction.WAIT
    sign = _sign(scenario.directional_bias)
    if sign > 0:
        return DecisionAction.BUY
    if sign < 0:
        return DecisionAction.SELL
    return DecisionAction.WAIT


class DecisionStabilityEngine:
    """Replay the decision rule across scenarios without weighting them.

    Scenario probabilities are not invented, so scenarios are never averaged.
    Stability counts agreement and, separately, flips to the *opposite* action,
    which is what makes a decision fragile rather than merely uncertain.
    """

    methodology = (
        "Chaque scénario est rejoué avec la même règle de décision, sans "
        "pondération: les probabilités de scénario ne sont pas inventées. "
        "ROBUST = aucun basculement vers l'action opposée et accord majoritaire; "
        "FRAGILE = au moins un basculement vers l'action opposée. Aucun niveau "
        "n'est publié si la comparaison est dégénérée (voir unknown_reason)."
    )

    def assess(
        self,
        baseline_action: DecisionAction,
        scenarios: list[FutureScenario],
        *,
        gate_active: bool = False,
        scenarios_are_derived: bool = False,
    ) -> DecisionStability:
        """Measure robustness, or refuse to when the comparison is degenerate.

        Two situations make the comparison meaningless rather than merely
        uncertain, and both are live today:

        * the scenario engine assigns the bullish case a bullish bias and the
          bearish case a bearish bias *by construction*, so any directional
          decision is flipped by one of them whatever the market is doing;
        * an active gate maps every scenario to WAIT, so agreement is total
          whatever the scenarios contain.

        Emitting FRAGILE or ROBUST in those cases would be a metric that is
        true by construction. The level is withheld and the reason is named.
        """

        if not scenarios:
            return DecisionStability(
                level=StabilityLevel.UNKNOWN,
                baseline_action=baseline_action,
                unknown_reason="Aucun scénario disponible.",
                methodology=self.methodology,
            )

        per_scenario_preview = {
            scenario.kind.value: action_for_scenario(
                scenario, gate_active=gate_active
            ).value
            for scenario in scenarios
        }
        if gate_active:
            return DecisionStability(
                level=StabilityLevel.UNKNOWN,
                baseline_action=baseline_action,
                decision_across_scenarios=per_scenario_preview,
                total_scenarios=len(scenarios),
                unknown_reason=(
                    "Décision sous garde-fou: tous les scénarios retombent sur "
                    "ATTENDRE, la comparaison ne discrimine rien."
                ),
                methodology=self.methodology,
            )
        if not scenarios_are_derived:
            return DecisionStability(
                level=StabilityLevel.UNKNOWN,
                baseline_action=baseline_action,
                decision_across_scenarios=per_scenario_preview,
                total_scenarios=len(scenarios),
                unknown_reason=(
                    "Les directions des scénarios sont posées par construction et "
                    "non dérivées des données: un scénario haussier ferait basculer "
                    "tout SELL, un scénario baissier tout BUY."
                ),
                methodology=self.methodology,
            )

        per_scenario: dict[str, str] = {}
        agreeing = 0
        flips: list[str] = []
        opposite = {
            DecisionAction.BUY: DecisionAction.SELL,
            DecisionAction.SELL: DecisionAction.BUY,
        }.get(baseline_action)

        for scenario in scenarios:
            # The tail-risk case is a stress branch: it is allowed to disagree
            # without making an otherwise coherent decision fragile, but a flip
            # to the opposite action is still recorded.
            action = action_for_scenario(scenario, gate_active=gate_active)
            per_scenario[scenario.kind.value] = action.value
            if action is baseline_action:
                agreeing += 1
            elif opposite is not None and action is opposite:
                flips.append(scenario.kind.value)

        non_tail_flips = [item for item in flips if item != ScenarioKind.TAIL_RISK_CASE.value]
        if non_tail_flips:
            level = StabilityLevel.FRAGILE
        elif flips:
            level = StabilityLevel.MODERATE
        elif agreeing >= max(1, len(scenarios) - 1):
            level = StabilityLevel.ROBUST
        else:
            level = StabilityLevel.MODERATE

        return DecisionStability(
            level=level,
            baseline_action=baseline_action,
            decision_across_scenarios=per_scenario,
            agreeing_scenarios=agreeing,
            total_scenarios=len(scenarios),
            flips_to_opposite=flips,
            methodology=self.methodology,
        )


# --------------------------------------------------------------------------
# Asymmetry
# --------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class RiskAsymmetryAssessment:
    """Compare upside and downside amplitude when probabilities are unknown."""

    level: RiskAsymmetry
    upside_movement: ExpectedMovement | None
    downside_movement: ExpectedMovement | None
    tail_movement: ExpectedMovement | None
    explanation: str = ""
    unknown_reason: str | None = None
    methodology: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level.value,
            "upside_movement": self.upside_movement.value if self.upside_movement else None,
            "downside_movement": self.downside_movement.value if self.downside_movement else None,
            "tail_movement": self.tail_movement.value if self.tail_movement else None,
            "explanation": self.explanation,
            "unknown_reason": self.unknown_reason,
            "methodology": self.methodology,
        }


class RiskAsymmetryEngine:
    """Amplitude-based asymmetry. Without probabilities it never claims odds.

    The question answered is "is what I can lose here larger than what I can
    gain", not "which is more likely". Tail risk counts on the downside because
    a liquidity cascade is not symmetric with an equivalent upside move.
    """

    methodology = (
        "Asymétrie d'amplitude: le scénario haussier est comparé au scénario "
        "baissier et au risque extrême. Aucune probabilité n'étant disponible, "
        "il ne s'agit pas d'une espérance mais d'une comparaison d'ampleurs."
    )

    def assess(
        self,
        scenarios: list[FutureScenario],
        *,
        gate_active: bool = False,
        scenarios_are_derived: bool = False,
    ) -> RiskAsymmetryAssessment:
        """Compare amplitudes, or refuse to when they share one source value.

        The current scenario engine computes a single ``expected_movement`` and
        stamps it on both the bullish and the bearish case. Upside can then
        never exceed downside, so the answer would be UNFAVORABLE or BALANCED
        whatever the market is doing. That is a constant, not a measurement.
        """

        by_kind = {scenario.kind: scenario for scenario in scenarios}
        bull = by_kind.get(ScenarioKind.BULLISH_CASE)
        bear = by_kind.get(ScenarioKind.BEARISH_CASE)
        tail = by_kind.get(ScenarioKind.TAIL_RISK_CASE)
        if not scenarios_are_derived:
            return RiskAsymmetryAssessment(
                level=RiskAsymmetry.UNKNOWN,
                upside_movement=bull.expected_movement if bull else None,
                downside_movement=bear.expected_movement if bear else None,
                tail_movement=tail.expected_movement if tail else None,
                unknown_reason=(
                    "Les amplitudes haussière et baissière proviennent d'une seule "
                    "valeur commune: leur comparaison serait constante."
                ),
                methodology=self.methodology,
            )
        if bull is None or bear is None:
            return RiskAsymmetryAssessment(
                level=RiskAsymmetry.UNKNOWN,
                upside_movement=bull.expected_movement if bull else None,
                downside_movement=bear.expected_movement if bear else None,
                tail_movement=tail.expected_movement if tail else None,
                explanation="Scénarios haussier et baissier requis pour comparer les ampleurs.",
                methodology=self.methodology,
            )

        up = _MOVEMENT_ORDER[bull.expected_movement]
        down = _MOVEMENT_ORDER[bear.expected_movement]
        tail_rank = _MOVEMENT_ORDER[tail.expected_movement] if tail else 0
        # An unresolved gating event is downside-weighted: the engine cannot
        # price the outcome, so the loss branch is not offset by the gain branch.
        delta = up - max(down, tail_rank - 1) - (1 if gate_active else 0)

        if delta >= 2:
            level = RiskAsymmetry.STRONGLY_FAVORABLE
        elif delta == 1:
            level = RiskAsymmetry.FAVORABLE
        elif delta == 0:
            level = RiskAsymmetry.BALANCED
        elif delta == -1:
            level = RiskAsymmetry.UNFAVORABLE
        else:
            level = RiskAsymmetry.STRONGLY_UNFAVORABLE

        explanation = (
            f"Potentiel haussier {bull.expected_movement.value}, "
            f"risque baissier {bear.expected_movement.value}"
            + (f", risque extrême {tail.expected_movement.value}" if tail else "")
            + ("; événement non résolu dans l'horizon." if gate_active else ".")
        )
        return RiskAsymmetryAssessment(
            level=level,
            upside_movement=bull.expected_movement,
            downside_movement=bear.expected_movement,
            tail_movement=tail.expected_movement if tail else None,
            explanation=explanation,
            methodology=self.methodology,
        )


# --------------------------------------------------------------------------
# Impact
# --------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class DecisionImpactAssessment:
    """What follows if the reading is correct. Never a price prediction."""

    direction: DirectionalBias
    expected_movement: ExpectedMovement
    time_horizon: DecisionHorizon
    risk_asymmetry: RiskAsymmetry
    primary_driver: str | None
    secondary_drivers: list[str] = field(default_factory=list)
    upside_case: str | None = None
    downside_case: str | None = None
    tail_risk: str | None = None
    invalidation_conditions: list[str] = field(default_factory=list)
    expected_range: dict[str, Any] | None = None
    expected_range_status: str = "UNAVAILABLE"
    methodology: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "direction": self.direction.value,
            "expected_movement": self.expected_movement.value,
            "time_horizon": self.time_horizon.value,
            "risk_asymmetry": self.risk_asymmetry.value,
            "primary_driver": self.primary_driver,
            "secondary_drivers": self.secondary_drivers,
            "upside_case": self.upside_case,
            "downside_case": self.downside_case,
            "tail_risk": self.tail_risk,
            "invalidation_conditions": self.invalidation_conditions,
            "expected_range": self.expected_range,
            "expected_range_status": self.expected_range_status,
            "methodology": self.methodology,
        }


class DecisionImpactEngine:
    """Assemble the consequence view from what other engines already produced.

    ``expected_range`` stays UNAVAILABLE unless a caller supplies a range that
    was derived from implied volatility, realised volatility, ATR or a
    documented historical event distribution. No range is ever synthesised here.
    """

    methodology = (
        "Les conséquences reprennent les scénarios déjà construits. Aucune "
        "cible de prix n'est produite: l'ampleur reste qualitative "
        "(LOW/NORMAL/HIGH/EXTREME) tant qu'aucun intervalle documenté n'est fourni."
    )

    def build(
        self,
        *,
        direction: DirectionalBias,
        expected_movement: ExpectedMovement,
        horizon: DecisionHorizon,
        asymmetry: RiskAsymmetryAssessment,
        scenarios: list[FutureScenario],
        primary_driver: str | None = None,
        secondary_drivers: list[str] | None = None,
        expected_range: dict[str, Any] | None = None,
    ) -> DecisionImpactAssessment:
        by_kind = {scenario.kind: scenario for scenario in scenarios}

        def _describe(kind: ScenarioKind) -> str | None:
            scenario = by_kind.get(kind)
            if scenario is None:
                return None
            chain = "; ".join(scenario.event_chain) if scenario.event_chain else ""
            return (
                f"{scenario.directional_bias.value}, ampleur "
                f"{scenario.expected_movement.value}" + (f" — {chain}" if chain else "")
            )

        invalidations: list[str] = []
        for scenario in scenarios:
            for condition in scenario.invalidation_conditions:
                if condition not in invalidations:
                    invalidations.append(condition)

        if expected_range is not None and not expected_range.get("basis"):
            raise ValueError("expected_range requires a documented volatility basis")

        return DecisionImpactAssessment(
            direction=direction,
            expected_movement=expected_movement,
            time_horizon=horizon,
            risk_asymmetry=asymmetry.level,
            primary_driver=primary_driver,
            secondary_drivers=list(secondary_drivers or []),
            upside_case=_describe(ScenarioKind.BULLISH_CASE),
            downside_case=_describe(ScenarioKind.BEARISH_CASE),
            tail_risk=_describe(ScenarioKind.TAIL_RISK_CASE),
            invalidation_conditions=invalidations,
            expected_range=expected_range,
            expected_range_status="AVAILABLE" if expected_range else "UNAVAILABLE",
            methodology=self.methodology,
        )

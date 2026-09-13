"""LOT 2 phases 5-10: the four contracts must be computable without being wired."""

import pytest

from crypto_intel.engines.contradiction_resolver import ContradictionState
from crypto_intel.engines.decision_contracts import (
    ConfidenceLevel,
    DecisionConfidenceEngine,
    DecisionImpactEngine,
    DecisionStabilityEngine,
    RiskAsymmetry,
    RiskAsymmetryEngine,
    StabilityLevel,
    action_for_scenario,
)
from crypto_intel.engines.future_decision import (
    DecisionAction,
    EventRiskLevel,
    FutureScenario,
    ScenarioKind,
)
from crypto_intel.engines.signal_convergence import SignalConvergence
from crypto_intel.future_events.models import (
    DecisionHorizon,
    DirectionalBias,
    ExpectedMovement,
)


def convergence(
    *, independent: int = 3, correlated: int = 0, mixed: float = 0.0
) -> SignalConvergence:
    return SignalConvergence(
        independent_confirmation_count=independent,
        causal_chain_count=0,
        bullish_independent_count=independent,
        bearish_independent_count=0,
        mixed_signal_strength=mixed,
        correlated_confirmation_reduction=correlated,
        units=[],
        methodology="test",
    )


def scenario(
    kind: ScenarioKind,
    bias: DirectionalBias,
    movement: ExpectedMovement = ExpectedMovement.NORMAL,
) -> FutureScenario:
    return FutureScenario(
        kind=kind,
        probability=None,
        probability_source=None,
        probability_observed_at=None,
        event_chain=["FOMC"],
        directional_bias=bias,
        expected_movement=movement,
        confidence=0.5,
        invalidation_conditions=[f"invalidation-{kind.value}"],
    )


def four_scenarios(
    bear: DirectionalBias = DirectionalBias.BEARISH,
    *,
    bear_movement: ExpectedMovement = ExpectedMovement.NORMAL,
    bull_movement: ExpectedMovement = ExpectedMovement.NORMAL,
    tail_movement: ExpectedMovement = ExpectedMovement.EXTREME,
) -> list[FutureScenario]:
    return [
        scenario(ScenarioKind.BASE_CASE, DirectionalBias.BULLISH),
        scenario(ScenarioKind.BULLISH_CASE, DirectionalBias.BULLISH, bull_movement),
        scenario(ScenarioKind.BEARISH_CASE, bear, bear_movement),
        scenario(ScenarioKind.TAIL_RISK_CASE, DirectionalBias.NEUTRAL, tail_movement),
    ]


# --- DecisionConfidence ----------------------------------------------------


def test_confidence_is_never_published_as_a_calibrated_number() -> None:
    result = DecisionConfidenceEngine().assess(convergence=convergence())
    assert result.numeric_score is None
    assert result.is_calibrated is False
    assert "probabilité" in result.to_dict()["not_a_probability"]


def test_missing_critical_input_collapses_confidence_immediately() -> None:
    result = DecisionConfidenceEngine().assess(
        convergence=convergence(independent=4),
        critical_missing_inputs=["etf_flows"],
    )
    assert result.level is ConfidenceLevel.VERY_LOW


def test_confidence_baseline_follows_independent_confirmations() -> None:
    engine = DecisionConfidenceEngine()
    assert engine.assess(convergence=convergence(independent=0)).level is ConfidenceLevel.VERY_LOW
    assert engine.assess(convergence=convergence(independent=2)).level is ConfidenceLevel.MEDIUM
    assert engine.assess(convergence=convergence(independent=9)).level is ConfidenceLevel.VERY_HIGH


def test_correlated_signals_do_not_count_as_two_confirmations() -> None:
    engine = DecisionConfidenceEngine()
    plain = engine.assess(convergence=convergence(independent=3))
    correlated = engine.assess(convergence=convergence(independent=3, correlated=1))
    assert plain.level is ConfidenceLevel.HIGH
    assert correlated.level is ConfidenceLevel.MEDIUM


def test_unpriced_event_uncertainty_lowers_confidence() -> None:
    result = DecisionConfidenceEngine().assess(
        convergence=convergence(independent=3),
        event_risk_level=EventRiskLevel.HIGH,
        expectations_available=False,
    )
    assert result.level is ConfidenceLevel.MEDIUM
    assert any(item.name == "event_uncertainty" for item in result.factors)


def test_priced_event_does_not_lower_confidence() -> None:
    result = DecisionConfidenceEngine().assess(
        convergence=convergence(independent=3),
        event_risk_level=EventRiskLevel.HIGH,
        expectations_available=True,
    )
    assert result.level is ConfidenceLevel.HIGH


def test_contradiction_and_fragility_stack_as_separate_deductions() -> None:
    result = DecisionConfidenceEngine().assess(
        convergence=convergence(independent=4),
        contradiction_state=ContradictionState.STRONGLY_MIXED,
        stability=StabilityLevel.FRAGILE,
    )
    assert result.level is ConfidenceLevel.VERY_LOW
    names = {item.name for item in result.factors}
    assert {"contradiction", "stability"} <= names


def test_every_confidence_step_is_auditable() -> None:
    result = DecisionConfidenceEngine().assess(
        convergence=convergence(independent=3),
        stale_inputs=["derivatives"],
    )
    assert all(item.detail for item in result.factors)
    assert any(item.name == "input_freshness" for item in result.factors)


# --- DecisionStability -----------------------------------------------------


def test_decision_is_robust_when_every_scenario_agrees() -> None:
    result = DecisionStabilityEngine().assess(
        DecisionAction.BUY,
        four_scenarios(DirectionalBias.BULLISH),
        scenarios_are_derived=True,
    )
    assert result.level is StabilityLevel.ROBUST
    assert result.flips_to_opposite == []


def test_a_bear_case_that_flips_to_the_opposite_action_is_fragile() -> None:
    result = DecisionStabilityEngine().assess(
        DecisionAction.BUY,
        four_scenarios(DirectionalBias.BEARISH),
        scenarios_are_derived=True,
    )
    assert result.level is StabilityLevel.FRAGILE
    assert ScenarioKind.BEARISH_CASE.value in result.flips_to_opposite


def test_tail_risk_alone_does_not_make_a_decision_fragile() -> None:
    scenarios = [
        scenario(ScenarioKind.BASE_CASE, DirectionalBias.BULLISH),
        scenario(ScenarioKind.BULLISH_CASE, DirectionalBias.BULLISH),
        scenario(ScenarioKind.BEARISH_CASE, DirectionalBias.BULLISH),
        scenario(ScenarioKind.TAIL_RISK_CASE, DirectionalBias.BEARISH),
    ]
    result = DecisionStabilityEngine().assess(
        DecisionAction.BUY, scenarios, scenarios_are_derived=True
    )
    assert result.level is StabilityLevel.MODERATE
    assert result.flips_to_opposite == [ScenarioKind.TAIL_RISK_CASE.value]


def test_scenarios_are_never_probability_weighted() -> None:
    result = DecisionStabilityEngine().assess(
        DecisionAction.BUY,
        four_scenarios(DirectionalBias.BEARISH),
        scenarios_are_derived=True,
    )
    assert result.total_scenarios == 4
    assert "probabilités de scénario ne sont pas inventées" in result.methodology


def test_stability_is_unknown_without_scenarios() -> None:
    result = DecisionStabilityEngine().assess(DecisionAction.BUY, [])
    assert result.level is StabilityLevel.UNKNOWN


def test_an_active_gate_makes_every_scenario_read_wait() -> None:
    scen = scenario(ScenarioKind.BULLISH_CASE, DirectionalBias.STRONGLY_BULLISH)
    assert action_for_scenario(scen) is DecisionAction.BUY
    assert action_for_scenario(scen, gate_active=True) is DecisionAction.WAIT


# --- RiskAsymmetry ---------------------------------------------------------


def test_symmetric_amplitudes_are_balanced() -> None:
    result = RiskAsymmetryEngine().assess(
        four_scenarios(
            bull_movement=ExpectedMovement.HIGH,
            bear_movement=ExpectedMovement.HIGH,
            tail_movement=ExpectedMovement.HIGH,
        ),
        scenarios_are_derived=True,
    )
    assert result.level is RiskAsymmetry.BALANCED


def test_a_gating_event_tilts_asymmetry_against_acting_now() -> None:
    scenarios = four_scenarios(
        bull_movement=ExpectedMovement.HIGH,
        bear_movement=ExpectedMovement.HIGH,
        tail_movement=ExpectedMovement.HIGH,
    )
    result = RiskAsymmetryEngine().assess(
        scenarios, gate_active=True, scenarios_are_derived=True
    )
    assert result.level is RiskAsymmetry.UNFAVORABLE
    assert "non résolu" in result.explanation


def test_large_downside_against_small_upside_is_strongly_unfavorable() -> None:
    result = RiskAsymmetryEngine().assess(
        four_scenarios(
            bull_movement=ExpectedMovement.LOW,
            bear_movement=ExpectedMovement.EXTREME,
            tail_movement=ExpectedMovement.EXTREME,
        ),
        scenarios_are_derived=True,
    )
    assert result.level is RiskAsymmetry.STRONGLY_UNFAVORABLE


def test_asymmetry_never_claims_odds() -> None:
    result = RiskAsymmetryEngine().assess(four_scenarios())
    assert "Aucune probabilité" in result.methodology


def test_asymmetry_unknown_without_both_branches() -> None:
    result = RiskAsymmetryEngine().assess(
        [scenario(ScenarioKind.BASE_CASE, DirectionalBias.BULLISH)],
        scenarios_are_derived=True,
    )
    assert result.level is RiskAsymmetry.UNKNOWN


# --- DecisionImpactAssessment ----------------------------------------------


def test_impact_reports_consequences_without_any_price_target() -> None:
    scenarios = four_scenarios()
    asymmetry = RiskAsymmetryEngine().assess(scenarios)
    impact = DecisionImpactEngine().build(
        direction=DirectionalBias.BEARISH,
        expected_movement=ExpectedMovement.HIGH,
        horizon=DecisionHorizon.D7,
        asymmetry=asymmetry,
        scenarios=scenarios,
        primary_driver="FOMC",
        secondary_drivers=["ETF"],
    )
    payload = impact.to_dict()
    assert payload["expected_range"] is None
    assert payload["expected_range_status"] == "UNAVAILABLE"
    assert payload["expected_movement"] == "HIGH"
    assert payload["upside_case"] and payload["downside_case"] and payload["tail_risk"]
    assert len(payload["invalidation_conditions"]) == 4


def test_a_range_without_a_documented_volatility_basis_is_refused() -> None:
    scenarios = four_scenarios()
    with pytest.raises(ValueError, match="documented volatility basis"):
        DecisionImpactEngine().build(
            direction=DirectionalBias.BEARISH,
            expected_movement=ExpectedMovement.HIGH,
            horizon=DecisionHorizon.D7,
            asymmetry=RiskAsymmetryEngine().assess(scenarios),
            scenarios=scenarios,
            expected_range={"low": 60000, "high": 72000},
        )


def test_a_range_with_a_documented_basis_is_accepted() -> None:
    scenarios = four_scenarios()
    impact = DecisionImpactEngine().build(
        direction=DirectionalBias.BEARISH,
        expected_movement=ExpectedMovement.HIGH,
        horizon=DecisionHorizon.D7,
        asymmetry=RiskAsymmetryEngine().assess(scenarios),
        scenarios=scenarios,
        expected_range={"low": 60000, "high": 72000, "basis": "ATR(14) journalier"},
    )
    assert impact.expected_range_status == "AVAILABLE"


def test_contracts_are_not_wired_into_the_production_decision() -> None:
    """Phase 12 requires these objects to stay out of BUY/WAIT/SELL for now."""

    from crypto_intel.engines import future_decision

    source = open(future_decision.__file__, encoding="utf-8").read()
    assert "decision_contracts" not in source


def test_constructed_scenarios_never_yield_a_stability_level() -> None:
    """Today's scenario engine fixes bull/bear bias, so the test is vacuous."""

    result = DecisionStabilityEngine().assess(
        DecisionAction.SELL, four_scenarios(DirectionalBias.BEARISH)
    )
    assert result.level is StabilityLevel.UNKNOWN
    assert "par construction" in (result.unknown_reason or "")
    assert result.decision_across_scenarios


def test_a_gated_decision_never_yields_a_stability_level() -> None:
    """Under an active gate every scenario reads WAIT; agreement proves nothing."""

    result = DecisionStabilityEngine().assess(
        DecisionAction.WAIT,
        four_scenarios(DirectionalBias.BEARISH),
        gate_active=True,
        scenarios_are_derived=True,
    )
    assert result.level is StabilityLevel.UNKNOWN
    assert "garde-fou" in (result.unknown_reason or "")


def test_stamped_scenarios_never_yield_an_asymmetry_level() -> None:
    """Bull and bear share one amplitude today, so the comparison is constant."""

    result = RiskAsymmetryEngine().assess(four_scenarios())
    assert result.level is RiskAsymmetry.UNKNOWN
    assert "valeur commune" in (result.unknown_reason or "")

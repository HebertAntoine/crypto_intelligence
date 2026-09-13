from datetime import UTC, datetime, timedelta

import pytest

from crypto_intel.core.enums import Asset
from crypto_intel.engines.future_decision import (
    DecisionAction,
    EventRiskEngine,
    EventRiskGate,
    FamilyAssessment,
    FiveFamilySnapshot,
    FutureDecisionEngine,
    FutureFamily,
    FutureScenarioEngine,
    ScenarioKind,
    event_proximity,
)
from crypto_intel.future_events.models import (
    DecisionHorizon,
    DirectionalBias,
    EventImportance,
    EventScheduleType,
    ExpectedMovement,
    FutureEvent,
    FutureEventCategory,
    FutureEventSourceTier,
    FutureEventStatus,
)

NOW = datetime(2026, 9, 12, 12, tzinfo=UTC)


def event(*, hours: int = 30, movement: ExpectedMovement = ExpectedMovement.HIGH) -> FutureEvent:
    return FutureEvent(
        event_type="FOMC_DECISION",
        category=FutureEventCategory.MONETARY_POLICY,
        schedule_type=EventScheduleType.SCHEDULED,
        title="Federal Reserve rate decision",
        source="Federal Reserve",
        source_tier=FutureEventSourceTier.A,
        source_url="https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
        scheduled_at=NOW + timedelta(hours=hours),
        affected_assets=[Asset.BTC, Asset.ETH, Asset.SOL],
        importance=EventImportance.CRITICAL,
        magnitude_effect=movement,
        directional_effect=DirectionalBias.NEUTRAL,
        confidence=1.0,
        detected_at=NOW,
        last_updated=NOW,
    )


def assessment(
    family: FutureFamily,
    direction: DirectionalBias = DirectionalBias.NEUTRAL,
) -> FamilyAssessment:
    return FamilyAssessment(
        family=family,
        available=True,
        directional_bias=direction,
        expected_movement=ExpectedMovement.NORMAL,
        confidence=0.8,
        summary=f"Source-backed {family.value} reading",
        sources=[{"source": "test source", "url": "https://example.test/source"}],
        as_of=NOW.isoformat(),
        freshness="RECENT",
    )


def five(*, technical: DirectionalBias = DirectionalBias.BULLISH) -> FiveFamilySnapshot:
    return FiveFamilySnapshot(
        {
            family: assessment(
                family,
                technical
                if family is FutureFamily.TECHNICAL_VOLATILITY
                else DirectionalBias.NEUTRAL,
            )
            for family in FutureFamily
        }
    )


def test_fed_inside_48h_and_unknown_distribution_activates_gate() -> None:
    result = EventRiskGate().assess([event()], as_of=NOW, analysis_uncertainty=None)
    assert result.active is True
    assert result.level.value == "HIGH"


def test_bullish_technical_cannot_override_tier_one_event_gate() -> None:
    result = FutureDecisionEngine().decide(
        Asset.BTC,
        [event()],
        five(technical=DirectionalBias.STRONGLY_BULLISH),
        as_of=NOW,
        analysis_uncertainty=0.8,
    )
    assert result.decision is DecisionAction.WAIT
    assert result.event_risk_gate.active is True
    assert result.reasons[0]["source"] == "Federal Reserve"


def test_exactly_five_slots_and_missing_is_not_neutral() -> None:
    families = FiveFamilySnapshot.from_partial(
        {FutureFamily.TECHNICAL_VOLATILITY: assessment(FutureFamily.TECHNICAL_VOLATILITY)}
    )
    payload = families.to_dict()
    assert len(payload["items"]) == 5
    assert payload["coverage"] == "1/5 disponibles"
    missing = payload["items"][FutureFamily.MACRO_LIQUIDITY.value]
    assert missing["status"] == "UNAVAILABLE"
    assert missing["directional_bias"] is None


def test_five_family_constructor_rejects_missing_slot() -> None:
    with pytest.raises(ValueError, match="exact slots"):
        FiveFamilySnapshot(
            {FutureFamily.TECHNICAL_VOLATILITY: assessment(FutureFamily.TECHNICAL_VOLATILITY)}
        )


def test_scenarios_exist_but_probabilities_are_not_invented() -> None:
    scenarios = FutureScenarioEngine().build([event(hours=72)], five(), as_of=NOW)
    assert [scenario.kind for scenario in scenarios] == list(ScenarioKind)
    assert all(scenario.probability is None for scenario in scenarios)
    assert all(scenario.confidence > 0 for scenario in scenarios)


def test_scenario_probability_requires_source_timestamp_and_full_distribution() -> None:
    probabilities = {
        kind: {
            "probability": 0.25,
            "source": "licensed market feed",
            "observed_at": NOW.isoformat(),
        }
        for kind in ScenarioKind
    }
    scenarios = FutureScenarioEngine().build(
        [], five(), as_of=NOW, scenario_probabilities=probabilities
    )
    assert scenarios[0].probability == pytest.approx(0.25)
    assert scenarios[0].probability_source == "licensed market feed"


def test_event_outside_gate_window_does_not_block() -> None:
    result = EventRiskGate().assess([event(hours=49)], as_of=NOW, analysis_uncertainty=0.9)
    assert result.active is False


def test_critical_event_72h_gate_not_triggered() -> None:
    assert EventRiskGate().assess([event(hours=72)], as_of=NOW).active is False


def test_critical_event_72h_risk_not_low_if_material() -> None:
    result = EventRiskEngine().assess(
        [event(hours=72)], horizon=DecisionHorizon.D7, as_of=NOW
    )
    assert result.level.value in {"MODERATE", "HIGH", "EXTREME"}


def test_critical_event_36h_gate_triggered() -> None:
    assert EventRiskGate().assess([event(hours=36)], as_of=NOW).active is True


def test_low_importance_event_36h_does_not_force_wait() -> None:
    low = event(hours=36).model_copy(update={"importance": EventImportance.LOW})
    assert EventRiskGate().assess([low], as_of=NOW).active is False


def test_event_risk_vs_gate() -> None:
    future_event = event(hours=72)
    gate = EventRiskGate().assess([future_event], as_of=NOW)
    risk = EventRiskEngine().assess(
        [future_event], horizon=DecisionHorizon.D7, as_of=NOW
    )
    assert gate.to_dict()["status"] == "NOT_TRIGGERED"
    assert risk.level.value != "LOW"


def test_event_proximity_decay() -> None:
    close = event(hours=24)
    far = event(hours=72)
    close_weight = event_proximity(close, DecisionHorizon.D7, as_of=NOW)
    far_weight = event_proximity(far, DecisionHorizon.D7, as_of=NOW)
    assert 0.0 < far_weight < close_weight < 1.0


def test_event_risk_horizon_specific() -> None:
    future_event = event(hours=72)
    risk_24h = EventRiskEngine().assess(
        [future_event], horizon=DecisionHorizon.H24, as_of=NOW
    )
    risk_7d = EventRiskEngine().assess(
        [future_event], horizon=DecisionHorizon.D7, as_of=NOW
    )
    risk_30d = EventRiskEngine().assess(
        [future_event], horizon=DecisionHorizon.D30, as_of=NOW
    )
    assert risk_24h.level.value == "LOW"
    assert risk_7d.level.value != "LOW"
    assert risk_7d.materiality != risk_30d.materiality


def test_low_amplitude_event_does_not_block() -> None:
    result = EventRiskGate().assess(
        [event(movement=ExpectedMovement.NORMAL)], as_of=NOW, analysis_uncertainty=0.9
    )
    assert result.active is False


def test_recent_unscheduled_critical_release_activates_gate_then_decays() -> None:
    recent = event().model_copy(
        update={
            "schedule_type": EventScheduleType.UNSCHEDULED,
            "scheduled_at": None,
            "status": FutureEventStatus.RELEASED,
            "source_published_at": NOW - timedelta(hours=2),
        }
    )
    old = recent.model_copy(update={"source_published_at": NOW - timedelta(hours=49)})

    assert EventRiskGate().assess([recent], as_of=NOW).active is True
    assert EventRiskGate().assess([old], as_of=NOW).active is False


def test_default_decision_horizon_is_seven_days() -> None:
    result = FutureDecisionEngine().decide(Asset.ETH, [], five(), as_of=NOW)
    assert result.horizon is DecisionHorizon.D7


def test_available_family_never_keeps_an_unavailable_reason() -> None:
    item = assessment(FutureFamily.MACRO_LIQUIDITY)
    item.unavailable_reason = "should be cleared"
    item.__post_init__()

    assert item.to_dict()["unavailable_reason"] is None


def test_zero_confidence_direction_is_not_a_counter_signal() -> None:
    families = five(technical=DirectionalBias.BULLISH)
    families.assessments[FutureFamily.FLOWS_WHALES].directional_bias = (
        DirectionalBias.BEARISH
    )
    families.assessments[FutureFamily.TECHNICAL_VOLATILITY].confidence = 0.0

    result = FutureDecisionEngine().decide(Asset.BTC, [], families, as_of=NOW)

    assert result.decision is DecisionAction.SELL
    assert result.counter_signals == []


def test_gate_window_follows_the_decision_horizon() -> None:
    """A 74 h event is outside 48 h but inside the 7-day claim it would span."""

    fomc = event(hours=74)
    assert EventRiskGate().assess([fomc], as_of=NOW).active is False
    assert (
        EventRiskGate()
        .assess([fomc], as_of=NOW, horizon=DecisionHorizon.H24)
        .active
        is False
    )
    assert (
        EventRiskGate().assess([fomc], as_of=NOW, horizon=DecisionHorizon.D7).active is True
    )


def test_buy_is_refused_while_an_unpriced_fomc_sits_inside_the_horizon() -> None:
    """The exact 13/09/2026 case: BUY at 7 d with a CRITICAL FOMC at 74 h."""

    result = FutureDecisionEngine().decide(
        Asset.BTC,
        [event(hours=74)],
        five(technical=DirectionalBias.STRONGLY_BULLISH),
        horizon=DecisionHorizon.D7,
        as_of=NOW,
        analysis_uncertainty=0.8,
    )
    assert result.decision is DecisionAction.WAIT
    assert result.event_risk_gate.active is True
    assert "horizon de décision" in result.event_risk_gate.reasons[0]


def test_same_event_still_allows_a_direction_on_the_24h_horizon() -> None:
    """Gating 7 d must not silently gate the shorter horizon too."""

    result = FutureDecisionEngine().decide(
        Asset.BTC,
        [event(hours=74)],
        five(technical=DirectionalBias.STRONGLY_BULLISH),
        horizon=DecisionHorizon.H24,
        as_of=NOW,
        analysis_uncertainty=0.8,
    )
    assert result.event_risk_gate.active is False


def test_gate_reason_carries_a_real_delay_not_a_fixed_48h_string() -> None:
    reason = (
        EventRiskGate()
        .assess([event(hours=74)], as_of=NOW, horizon=DecisionHorizon.D7)
        .reasons[0]
    )
    assert "dans 3,1 j" in reason
    assert "48 h" not in reason

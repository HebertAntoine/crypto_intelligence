from datetime import UTC, datetime, timedelta

import pytest

from crypto_intel.core.enums import Asset
from crypto_intel.engines.future_decision import (
    DecisionAction,
    EventRiskGate,
    FamilyAssessment,
    FiveFamilySnapshot,
    FutureDecisionEngine,
    FutureFamily,
    FutureScenarioEngine,
    ScenarioKind,
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
                technical if family is FutureFamily.TECHNICAL_VOLATILITY else DirectionalBias.NEUTRAL,
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
    assert result.event_risk.active is True
    assert result.reasons[0]["source"] == "Federal Reserve"


def test_exactly_five_slots_and_missing_is_not_neutral() -> None:
    families = FiveFamilySnapshot.from_partial(
        {
            FutureFamily.TECHNICAL_VOLATILITY: assessment(
                FutureFamily.TECHNICAL_VOLATILITY
            )
        }
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
            {
                FutureFamily.TECHNICAL_VOLATILITY: assessment(
                    FutureFamily.TECHNICAL_VOLATILITY
                )
            }
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


def test_low_amplitude_event_does_not_block() -> None:
    result = EventRiskGate().assess(
        [event(movement=ExpectedMovement.NORMAL)], as_of=NOW, analysis_uncertainty=0.9
    )
    assert result.active is False


def test_default_decision_horizon_is_seven_days() -> None:
    result = FutureDecisionEngine().decide(Asset.ETH, [], five(), as_of=NOW)
    assert result.horizon is DecisionHorizon.D7

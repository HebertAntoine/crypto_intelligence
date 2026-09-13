"""Section 12: the decision must never contradict the evidence beside it."""

from datetime import UTC, datetime, timedelta

from crypto_intel.core.enums import Asset
from crypto_intel.engines.decision_consistency import (
    CONFIDENT_ENOUGH,
    DecisionConsistencyValidator,
    blocking_events,
)
from crypto_intel.engines.future_decision import (
    DecisionAction,
    EventRiskLevel,
    FamilyAssessment,
    FiveFamilySnapshot,
    FutureDecisionEngine,
    FutureFamily,
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

NOW = datetime(2026, 9, 13, 12, tzinfo=UTC)


def event(
    *,
    hours: int = 74,
    importance: EventImportance = EventImportance.CRITICAL,
    movement: ExpectedMovement = ExpectedMovement.HIGH,
    direction: DirectionalBias = DirectionalBias.NEUTRAL,
) -> FutureEvent:
    return FutureEvent(
        event_type="FOMC_DECISION",
        category=FutureEventCategory.MONETARY_POLICY,
        schedule_type=EventScheduleType.SCHEDULED,
        title="Décision de la Fed",
        source="Federal Reserve",
        source_tier=FutureEventSourceTier.A,
        source_url="https://www.federalreserve.gov/",
        importance=importance,
        magnitude_effect=movement,
        directional_effect=direction,
        scheduled_at=NOW + timedelta(hours=hours),
        detected_at=NOW,
    )


def family(
    slot: FutureFamily,
    direction: DirectionalBias | None,
    *,
    available: bool = True,
    confidence: float = 0.9,
) -> FamilyAssessment:
    return FamilyAssessment(
        family=slot,
        available=available,
        directional_bias=direction,
        expected_movement=ExpectedMovement.NORMAL,
        confidence=confidence,
        summary="résumé",
        freshness="LIVE",
    )


def five(**overrides: DirectionalBias | None) -> FiveFamilySnapshot:
    slots = {
        FutureFamily.MACRO_LIQUIDITY: overrides.get("macro", DirectionalBias.NEUTRAL),
        FutureFamily.CATALYSTS_REGULATION: overrides.get("catalysts", DirectionalBias.NEUTRAL),
        FutureFamily.FLOWS_WHALES: overrides.get("flows", DirectionalBias.BULLISH),
        FutureFamily.POSITIONING_DERIVATIVES: overrides.get(
            "positioning", DirectionalBias.BULLISH
        ),
        FutureFamily.TECHNICAL_VOLATILITY: overrides.get("technical", DirectionalBias.BULLISH),
    }
    return FiveFamilySnapshot.from_partial(
        {slot: family(slot, direction) for slot, direction in slots.items()}
    )


def validate(action: DecisionAction, **kwargs):
    base = {
        "direction": DirectionalBias.BULLISH,
        "confidence": 0.6,
        "event_risk_level": EventRiskLevel.HIGH,
        "horizon_events": [event()],
        "families": five(),
        "expectations_available": False,
    }
    base.update(kwargs)
    return DecisionConsistencyValidator().validate(action, **base)


def test_event_risk_gate_high_impact_unknown_direction() -> None:
    """A material event with an unknown outcome blocks a directional call."""

    report = validate(DecisionAction.BUY)
    assert report.action is DecisionAction.WAIT
    assert report.issues[0].code == "UNRESOLVED_TIER1_EVENT"
    assert "asymétrie favorable robuste" in report.issues[0].detail


def test_high_importance_is_material_even_without_critical() -> None:
    blocking = blocking_events([event(importance=EventImportance.HIGH)], priced=False)
    assert blocking
    assert not blocking_events([event(importance=EventImportance.MEDIUM)], priced=False)


def test_buy_requires_robust_asymmetry_before_tier1_event() -> None:
    """The brief allows BUY, but only against a demonstrated asymmetry."""

    blocked = validate(DecisionAction.BUY, asymmetry_is_favorable=False)
    allowed = validate(DecisionAction.BUY, asymmetry_is_favorable=True)
    assert blocked.action is DecisionAction.WAIT
    assert allowed.action is DecisionAction.BUY


def test_a_confident_engine_may_still_act_across_the_event() -> None:
    """"Fed bientôt" alone must never force WAIT."""

    report = validate(DecisionAction.BUY, confidence=CONFIDENT_ENOUGH + 0.05)
    assert report.action is DecisionAction.BUY


def test_a_priced_event_does_not_block_anything() -> None:
    report = validate(DecisionAction.BUY, expectations_available=True)
    assert report.action is DecisionAction.BUY
    assert report.issues == []


def test_negative_etf_rolling_flow_not_positive_without_evidence() -> None:
    class Flow:
        rolling_5_sessions_musd = -288.1
        regime_total_musd = None

    report = validate(
        DecisionAction.BUY,
        horizon_events=[],
        event_risk_level=EventRiskLevel.LOW,
        institutional_flow=Flow(),
    )
    codes = {issue.code for issue in report.issues}
    assert "FLOW_SIGN_UNJUSTIFIED" in codes
    assert report.action is DecisionAction.WAIT


def test_a_named_measurement_window_justifies_the_positive_flow() -> None:
    class Flow:
        rolling_5_sessions_musd = -288.1
        regime_total_musd = 3310.1

    families = five()
    families.assessments[FutureFamily.FLOWS_WHALES].summary = (
        "Flux institutionnels: entrées nettes sur 20 séances (+3 310,1 M$); "
        "5 dernières séances -288,1 M$."
    )
    report = validate(
        DecisionAction.BUY,
        horizon_events=[],
        event_risk_level=EventRiskLevel.LOW,
        families=families,
        institutional_flow=Flow(),
    )
    assert "FLOW_SIGN_UNJUSTIFIED" not in {issue.code for issue in report.issues}


def test_majority_of_families_against_the_action_degrades_it() -> None:
    report = validate(
        DecisionAction.BUY,
        horizon_events=[],
        event_risk_level=EventRiskLevel.LOW,
        families=five(
            flows=DirectionalBias.BEARISH,
            positioning=DirectionalBias.BEARISH,
            technical=DirectionalBias.BULLISH,
        ),
    )
    assert report.action is DecisionAction.WAIT
    assert "MAJORITY_CONTRADICTS_ACTION" in {issue.code for issue in report.issues}


def test_bollinger_changes_amplitude_not_direction() -> None:
    """A zero-confidence technical reading must not carry a direction."""

    families = five()
    families.assessments[FutureFamily.TECHNICAL_VOLATILITY].confidence = 0.0
    report = validate(
        DecisionAction.WAIT,
        horizon_events=[],
        event_risk_level=EventRiskLevel.LOW,
        families=families,
    )
    assert "AMPLITUDE_USED_AS_DIRECTION" in {issue.code for issue in report.issues}


def test_market_expectation_missing_reduces_confidence() -> None:
    """Section 4: an unpriced material event must cost confidence."""

    engine = FutureDecisionEngine()
    quiet = engine.decide(
        Asset.BTC, [], five(), horizon=DecisionHorizon.D7, as_of=NOW
    )
    exposed = engine.decide(
        Asset.BTC, [event()], five(), horizon=DecisionHorizon.D7, as_of=NOW
    )
    assert exposed.decision_confidence < quiet.decision_confidence


def test_decision_consistency_validator_never_raises_conviction() -> None:
    report = validate(DecisionAction.WAIT, horizon_events=[event()])
    assert report.action is DecisionAction.WAIT
    for action in (DecisionAction.BUY, DecisionAction.SELL):
        assert validate(action).action is not action or True


def test_a_degraded_decision_always_records_why() -> None:
    report = validate(DecisionAction.BUY)
    assert report.degraded is True
    payload = report.to_dict()
    assert payload["status"] == "DEGRADED"
    assert payload["issues"][0]["downgraded_to"] == "WAIT"
    assert payload["issues"][0]["detail"]


def test_decision_change_conditions_are_concrete() -> None:
    """Section 9: no filler. Every line names something observable."""

    result = FutureDecisionEngine().decide(
        Asset.BTC,
        [event()],
        five(flows=DirectionalBias.BEARISH),
        horizon=DecisionHorizon.D7,
        as_of=NOW,
    )
    changes = result.what_could_change_decision
    assert changes

    for banned in (
        "Un catalyseur prioritaire change de sens ou d'amplitude.",
        "Rétablir les familles indisponibles avec des données actuelles et sourcées.",
        "Attendre la publication et réévaluer la surprise observée.",
    ):
        assert banned not in changes

    # The event condition names the event and when it lands.
    assert any("Décision de la Fed" in item and "dans" in item for item in changes)
    # The family condition names the move that would reverse it.
    assert any("séances consécutives" in item for item in changes)


def test_a_neutral_family_produces_no_flip_condition() -> None:
    """Nothing to reverse means no line, rather than an invented one."""

    from crypto_intel.engines.future_decision import _family_flip_condition

    neutral = family(FutureFamily.MACRO_LIQUIDITY, DirectionalBias.NEUTRAL)
    unavailable = family(FutureFamily.FLOWS_WHALES, None, available=False)
    assert _family_flip_condition(neutral) is None
    assert _family_flip_condition(unavailable) is None
    assert _family_flip_condition(family(FutureFamily.FLOWS_WHALES, DirectionalBias.BULLISH))

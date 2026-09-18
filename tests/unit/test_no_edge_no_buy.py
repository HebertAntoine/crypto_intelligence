"""Sections 25 and 41: clearing a blocker is not evidence of an opportunity.

The decision rule reads "gate active -> WAIT, otherwise bullish -> BUY". The
moment a scheduled event passes, its gate clears and a BUY appears without
anything positive having been demonstrated. This is the real sequence observed
around the September FOMC, replayed here.
"""

from datetime import UTC, datetime, timedelta

from tests.unit.test_decision_consistency import five

from crypto_intel.core.enums import Asset
from crypto_intel.engines.decision_consistency import DecisionConsistencyValidator
from crypto_intel.engines.edge import EdgeState
from crypto_intel.engines.future_decision import (
    DecisionAction,
    EventRiskLevel,
    FutureDecisionEngine,
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

NOW = datetime(2026, 9, 14, 12, tzinfo=UTC)


def fomc(*, hours: int) -> FutureEvent:
    """The event, placed before or after the decision moment."""

    return FutureEvent(
        event_type="FOMC_DECISION",
        category=FutureEventCategory.MONETARY_POLICY,
        schedule_type=EventScheduleType.SCHEDULED,
        title="Décision de la Fed",
        source="Federal Reserve",
        source_tier=FutureEventSourceTier.A,
        source_url="https://www.federalreserve.gov/",
        importance=EventImportance.CRITICAL,
        magnitude_effect=ExpectedMovement.HIGH,
        directional_effect=DirectionalBias.NEUTRAL,
        scheduled_at=NOW + timedelta(hours=hours),
        detected_at=NOW,
        last_updated=NOW,
    )


def decide(events, *, edge_state: str | None, horizon=DecisionHorizon.D7):
    return FutureDecisionEngine().decide(
        Asset.BTC,
        events,
        five(),  # every family bullish by default
        horizon=horizon,
        as_of=NOW,
        analysis_uncertainty=0.8,
        edge_state=edge_state,
    )


# --- the observed sequence --------------------------------------------------


def test_the_gate_holds_the_decision_while_the_event_is_ahead() -> None:
    result = decide([fomc(hours=48)], edge_state=EdgeState.POSITIVE_EDGE.value)
    assert result.decision is DecisionAction.WAIT
    assert result.event_risk_gate.active is True


def test_clearing_the_gate_alone_never_produces_a_buy() -> None:
    """The regression: the event passes, the gate clears, and BUY appears."""

    result = decide(
        [fomc(hours=-6)], edge_state=EdgeState.NO_MEASURABLE_EDGE.value
    )
    assert result.event_risk_gate.active is False
    assert result.decision is DecisionAction.WAIT
    codes = {issue.code for issue in result.consistency.issues}
    assert "NO_MEASURABLE_EDGE" in codes


def test_a_demonstrated_edge_does_allow_the_buy() -> None:
    """The rule blocks an unfounded call; it does not block every call."""

    result = decide([fomc(hours=-6)], edge_state=EdgeState.POSITIVE_EDGE.value)
    assert result.decision is DecisionAction.BUY


def test_insufficient_edge_data_is_not_treated_as_a_green_light() -> None:
    result = decide(
        [fomc(hours=-6)], edge_state=EdgeState.INSUFFICIENT_DATA.value
    )
    assert result.decision is DecisionAction.WAIT


def test_an_unknown_edge_state_does_not_silently_authorise_a_buy() -> None:
    """A missing assessment must not read as a passing one."""

    blocked = DecisionConsistencyValidator().validate(
        DecisionAction.BUY,
        direction=DirectionalBias.BULLISH,
        confidence=0.9,
        event_risk_level=EventRiskLevel.LOW,
        horizon_events=[],
        families=five(),
        expectations_available=True,
        edge_state=EdgeState.NO_MEASURABLE_EDGE.value,
    )
    assert blocked.action is DecisionAction.WAIT


def test_the_rule_applies_to_sell_as_well_as_buy() -> None:
    """A directional call in either direction needs the same footing."""

    report = DecisionConsistencyValidator().validate(
        DecisionAction.SELL,
        direction=DirectionalBias.BEARISH,
        confidence=0.9,
        event_risk_level=EventRiskLevel.LOW,
        horizon_events=[],
        families=five(
            flows=DirectionalBias.BEARISH,
            positioning=DirectionalBias.BEARISH,
            technical=DirectionalBias.BEARISH,
        ),
        expectations_available=True,
        edge_state=EdgeState.NO_MEASURABLE_EDGE.value,
    )
    assert report.action is DecisionAction.WAIT


def test_the_downgrade_states_why_rather_than_hiding_it() -> None:
    result = decide(
        [fomc(hours=-6)], edge_state=EdgeState.NO_MEASURABLE_EDGE.value
    )
    issue = next(
        item for item in result.consistency.issues if item.code == "NO_MEASURABLE_EDGE"
    )
    assert "disparition d'un blocage" in issue.detail
    # Written for a reader, not in the engine's own vocabulary.
    assert "SELL" not in issue.detail and "BUY" not in issue.detail
    assert issue.downgraded_to == DecisionAction.WAIT.value


def test_a_published_event_stops_behaving_like_an_unknown_one() -> None:
    """Section 15: a past event has an outcome, whether or not we read it yet."""

    from crypto_intel.engines.decision_consistency import blocking_events

    ahead = fomc(hours=12)
    behind = fomc(hours=-12)
    assert blocking_events([ahead], priced=False, as_of=NOW) == [ahead]
    assert blocking_events([behind], priced=False, as_of=NOW) == []


def test_a_published_event_no_longer_costs_confidence() -> None:
    """The unpriced haircut applied to an event that had already happened."""

    ahead = decide([fomc(hours=12)], edge_state=EdgeState.POSITIVE_EDGE.value)
    behind = decide([fomc(hours=-12)], edge_state=EdgeState.POSITIVE_EDGE.value)
    assert behind.decision_confidence > ahead.decision_confidence

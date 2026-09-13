from datetime import UTC, datetime, timedelta

from crypto_intel.core.enums import Asset
from crypto_intel.core.usability import FamilyState, Freshness
from crypto_intel.engines.decision_data_quality import (
    DecisionDataQualityEngine,
    DecisionDataQualityStatus,
)
from crypto_intel.engines.future_decision import (
    DecisionAction,
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


def _state(name: str, freshness: Freshness = Freshness.RECENT) -> FamilyState:
    return FamilyState(
        family=name,
        available=True,
        valid=True,
        freshness=freshness,
        observed_at=NOW - timedelta(minutes=5),
        source=f"real {name} provider",
        points=250,
    )


def _bullish_families() -> FiveFamilySnapshot:
    return FiveFamilySnapshot(
        {
            family: FamilyAssessment(
                family=family,
                available=True,
                directional_bias=DirectionalBias.BULLISH,
                expected_movement=ExpectedMovement.NORMAL,
                confidence=0.8,
                freshness="RECENT",
                sources=[
                    {
                        "source": f"real {family.value} provider",
                        "tier": "B",
                        "url": f"https://data.test/{family.value}",
                    }
                ],
            )
            for family in FutureFamily
        }
    )


def test_stale_critical_input_is_present_but_never_usable_coverage() -> None:
    states = {
        "price": _state("price", Freshness.STALE),
        "ohlcv_h1": _state("ohlcv_h1"),
        "ohlcv_4h": _state("ohlcv_4h"),
    }
    quality = DecisionDataQualityEngine().assess(
        Asset.BTC,
        DecisionHorizon.H24,
        states,
        [],
        _bullish_families(),
        as_of=NOW,
    )

    assert quality.status is DecisionDataQualityStatus.INSUFFICIENT
    assert quality.coverage["present_inputs"] == 3
    assert quality.coverage["usable_inputs"] == 2
    assert "price" in quality.stale_inputs
    assert quality.critical_missing_inputs == ["price"]
    assert quality.blocks_directional_decision is True


def test_optional_gaps_are_partial_and_named_without_arbitrary_score() -> None:
    states = {
        "price": _state("price"),
        "ohlcv_h1": _state("ohlcv_h1"),
        "ohlcv_4h": _state("ohlcv_4h"),
    }
    quality = DecisionDataQualityEngine().assess(
        Asset.SOL,
        DecisionHorizon.H24,
        states,
        [],
        _bullish_families(),
        as_of=NOW,
    )
    payload = quality.to_dict()

    assert quality.status is DecisionDataQualityStatus.PARTIAL
    assert quality.blocks_directional_decision is False
    assert "whale_intelligence" in quality.missing_inputs
    assert "market_rate_expectations" in quality.missing_inputs
    assert "dvol" not in payload["freshness"]["inputs"]
    assert "score" not in payload
    assert "score" not in payload["coverage"]
    assert "score" not in payload["source_quality"]


def test_quality_gate_turns_bullish_stale_context_into_insufficient_data() -> None:
    states = {
        "price": _state("price", Freshness.STALE),
        "ohlcv_h1": _state("ohlcv_h1"),
        "ohlcv_4h": _state("ohlcv_4h"),
    }
    families = _bullish_families()
    quality = DecisionDataQualityEngine().assess(
        Asset.BTC,
        DecisionHorizon.H24,
        states,
        [],
        families,
        as_of=NOW,
    )
    decision = FutureDecisionEngine().decide(
        Asset.BTC,
        [],
        families,
        horizon=DecisionHorizon.H24,
        as_of=NOW,
        data_quality=quality,
    )

    assert decision.decision is DecisionAction.INSUFFICIENT_DATA
    assert decision.directional_bias is DirectionalBias.NEUTRAL
    assert decision.decision_confidence == 0.0
    assert decision.reasons[0]["source"] == "DecisionDataQuality"
    assert decision.to_dict()["data_quality"]["status"] == "INSUFFICIENT"


def test_fresh_calendar_is_not_missing_when_no_event_falls_inside_24h() -> None:
    states = {
        "price": _state("price"),
        "ohlcv_h1": _state("ohlcv_h1"),
        "ohlcv_4h": _state("ohlcv_4h"),
    }
    event = FutureEvent(
        event_type="FOMC_DECISION",
        category=FutureEventCategory.MONETARY_POLICY,
        schedule_type=EventScheduleType.SCHEDULED,
        title="Federal Reserve rate decision",
        source="Federal Reserve",
        source_tier=FutureEventSourceTier.A,
        source_url="https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
        scheduled_at=NOW + timedelta(days=3),
        detected_at=NOW,
        last_updated=NOW,
        affected_assets=[Asset.BTC],
        importance=EventImportance.CRITICAL,
    )
    quality = DecisionDataQualityEngine().assess(
        Asset.BTC,
        DecisionHorizon.H24,
        states,
        [],
        _bullish_families(),
        as_of=NOW,
        calendar_events=[event],
    )

    calendar = quality.freshness["inputs"]["event_calendar"]
    assert calendar["usable"] is True
    assert "event_calendar" not in quality.missing_inputs

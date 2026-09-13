from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from crypto_intel.engines.event_surprise import EventSurpriseEngine
from crypto_intel.engines.market_expectation import (
    ExpectedOutcome,
    MarketExpectation,
    MarketExpectationEngine,
    MarketExpectationStatus,
)
from crypto_intel.future_events.deduplication import EventDeduplicator
from crypto_intel.future_events.models import (
    EventImportance,
    EventScheduleType,
    FutureEvent,
    FutureEventCategory,
    FutureEventSourceTier,
)
from crypto_intel.providers.events.cme_fedwatch import parse_fedwatch_payload


def _payload():
    return {
        "asOf": "2028-09-12T14:02:00Z",
        "meetings": [
            {
                "meetingDate": "2028-09-20",
                "currentTargetRange": "4.00-4.25%",
                "probabilities": [
                    {"targetRange": "4.00-4.25%", "probability": 72},
                    {"targetRange": "4.25-4.50%", "probability": 18},
                    {"targetRange": "3.75-4.00%", "probability": 10},
                ],
            }
        ],
    }


def test_fedwatch_parser_requires_and_preserves_measurement_timestamp():
    event = parse_fedwatch_payload(_payload())[0]

    assert event.scheduled_at == datetime(2028, 9, 20, 18, tzinfo=UTC)
    assert event.probability_timestamp == datetime(2028, 9, 12, 14, 2, tzinfo=UTC)
    assert sum(item.probability for item in event.market_probabilities) == 1.0
    assert all(item.observed_at == event.probability_timestamp for item in event.market_probabilities)


def test_partial_or_untimestamped_distribution_is_rejected():
    payload = _payload()
    payload.pop("asOf")
    assert parse_fedwatch_payload(payload) == []

    payload = _payload()
    payload["meetings"][0]["probabilities"] = {"hold": 0.72, "hike": 0.10}
    assert parse_fedwatch_payload(payload) == []


def test_expected_vs_actual_surprise():
    event = parse_fedwatch_payload(_payload())[0]
    analysis = MarketExpectationEngine().analyze(
        event, as_of=datetime(2028, 9, 12, 14, 3, tzinfo=UTC)
    )
    surprise = EventSurpriseEngine().analyze(
        analysis,
        actual_outcome="4.25-4.50%",
        observed_at=datetime(2028, 9, 20, 18, tzinfo=UTC),
    )

    assert analysis.available is True
    assert analysis.expected_outcome.probability == 0.72
    assert analysis.confidence == 1.0
    assert surprise.expected_probability_of_actual == 0.18
    assert surprise.probability_surprise == pytest.approx(0.82)
    assert surprise.numeric_surprise is not None
    assert surprise.numeric_surprise > 0


def test_market_expectation_missing_probability():
    event = FutureEvent(
        event_type="FOMC_DECISION",
        category=FutureEventCategory.MONETARY_POLICY,
        schedule_type=EventScheduleType.SCHEDULED,
        title="FOMC decision",
        source="Federal Reserve",
        source_tier=FutureEventSourceTier.A,
        source_url="https://www.federalreserve.gov/",
        scheduled_at=datetime(2028, 9, 20, 18, tzinfo=UTC),
        importance=EventImportance.CRITICAL,
    )

    analysis = MarketExpectationEngine().analyze(
        event, as_of=datetime(2028, 9, 12, 14, 3, tzinfo=UTC)
    )

    assert analysis.available is False
    assert analysis.distribution == []
    assert analysis.degree_priced is None


def test_market_expectation_requires_timestamp():
    priced = parse_fedwatch_payload(_payload())[0]
    with pytest.raises(ValidationError, match="probability_timestamp"):
        MarketExpectation(
            event_id=priced.id,
            observed_at=datetime(2028, 9, 12, 14, 3, tzinfo=UTC),
            expected_outcome=ExpectedOutcome(outcome="4.00-4.25%", probability=0.72),
            outcome_distribution=priced.market_probabilities,
            market_probability=0.72,
            source="CME FedWatch",
            methodology="test fixture",
            freshness="LIVE",
            status=MarketExpectationStatus.AVAILABLE,
        )


def test_market_expectation_stale_probability():
    priced = parse_fedwatch_payload(_payload())[0]
    analysis = MarketExpectationEngine().analyze(
        priced,
        as_of=priced.probability_timestamp + timedelta(hours=7),
    )

    assert analysis.status is MarketExpectationStatus.STALE
    assert analysis.available is False
    assert analysis.freshness == "STALE"
    assert analysis.outcome_distribution


def test_expected_rate_no_surprise():
    payload = _payload()
    payload["meetings"][0]["probabilities"] = [
        {"targetRange": "4.00-4.25%", "probability": 90},
        {"targetRange": "4.25-4.50%", "probability": 5},
        {"targetRange": "3.75-4.00%", "probability": 5},
    ]
    priced = parse_fedwatch_payload(payload)[0]
    expectation = MarketExpectationEngine().analyze(
        priced, as_of=priced.probability_timestamp + timedelta(minutes=1)
    )
    surprise = EventSurpriseEngine().analyze(
        expectation,
        actual_outcome="4.00-4.25%",
        observed_at=priced.scheduled_at,
    )

    assert surprise.numeric_surprise == pytest.approx(0.0)
    assert surprise.probability_surprise == pytest.approx(0.1)


def test_communication_surprise():
    priced = parse_fedwatch_payload(_payload())[0]
    expectation = MarketExpectationEngine().analyze(
        priced, as_of=priced.probability_timestamp + timedelta(minutes=1)
    )
    surprise = EventSurpriseEngine().analyze(
        expectation,
        actual_outcome="4.00-4.25%",
        observed_at=priced.scheduled_at,
        expected_communication=0.0,
        actual_communication=-0.8,
    )

    assert surprise.numeric_surprise == pytest.approx(0.0)
    assert surprise.communication_surprise == pytest.approx(-0.8)
    assert surprise.overall_direction == "NEGATIVE"


def test_dedup_keeps_official_identity_and_complementary_cme_distribution():
    priced = parse_fedwatch_payload(_payload())[0]
    official = FutureEvent(
        event_type="FOMC_DECISION",
        category=FutureEventCategory.MONETARY_POLICY,
        schedule_type=EventScheduleType.SCHEDULED,
        title="FOMC monetary policy decision",
        source="Federal Reserve",
        source_tier=FutureEventSourceTier.A,
        source_url="https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
        scheduled_at=priced.scheduled_at,
        importance=EventImportance.CRITICAL,
        metadata={
            "entities": ["Federal Reserve", "FOMC"],
            "subject": "monetary policy decision",
            "location": "United States",
        },
    )

    merged = EventDeduplicator().deduplicate([official, priced])[0]

    assert merged.source == "Federal Reserve"
    assert merged.source_tier is FutureEventSourceTier.A
    assert len(merged.market_probabilities) == 3
    assert {reference.source for reference in merged.source_references} == {
        "Federal Reserve",
        "CME FedWatch",
    }

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from crypto_intel.engines.market_expectation import MarketExpectationEngine
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


def test_expectation_and_surprise_are_different_from_analysis_confidence():
    event = parse_fedwatch_payload(_payload())[0]
    analysis = MarketExpectationEngine().analyze(event, actual_outcome="4.25-4.50%")

    assert analysis.available is True
    assert analysis.expected_outcome.probability == 0.72
    assert analysis.confidence == 1.0
    assert analysis.surprise.expected_probability == 0.18
    assert analysis.surprise.surprise_score == pytest.approx(0.82)
    assert analysis.surprise.signed_distance is not None
    assert analysis.surprise.signed_distance > 0


def test_missing_market_pricing_never_becomes_a_default_probability():
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

    analysis = MarketExpectationEngine().analyze(event)

    assert analysis.available is False
    assert analysis.distribution == []
    assert analysis.degree_priced is None


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

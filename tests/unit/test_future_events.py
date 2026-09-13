from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from crypto_intel.core.enums import Asset
from crypto_intel.db import repo
from crypto_intel.future_events import (
    DirectionalBias,
    EventDeduplicator,
    EventFreshness,
    EventImportance,
    EventScheduleType,
    ExpectedMovement,
    FutureEvent,
    FutureEventCategory,
    FutureEventSourceTier,
    FutureEventStatus,
    MarketProbability,
    event_freshness,
)

NOW = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)


def _event(**overrides) -> FutureEvent:
    values = {
        "event_type": "CENTRAL_BANK_DECISION",
        "category": FutureEventCategory.MONETARY_POLICY,
        "schedule_type": EventScheduleType.SCHEDULED,
        "title": "Federal Reserve interest-rate decision",
        "source": "Federal Reserve",
        "source_tier": FutureEventSourceTier.A,
        "source_url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
        "source_published_at": NOW - timedelta(hours=1),
        "detected_at": NOW,
        "scheduled_at": NOW + timedelta(days=4),
        "timezone": "America/New_York",
        "affected_assets": [Asset.BTC, Asset.ETH, Asset.SOL],
        "affected_markets": ["crypto", "rates"],
        "importance": EventImportance.CRITICAL,
        "directional_effect": DirectionalBias.NEUTRAL,
        "magnitude_effect": ExpectedMovement.HIGH,
        "confidence": 0.99,
        "last_updated": NOW,
        "metadata": {
            "entities": ["Federal Reserve"],
            "subject": "interest rate decision",
            "location": "United States",
        },
    }
    values.update(overrides)
    return FutureEvent(**values)


def test_probability_timestamp_is_mandatory() -> None:
    distribution = [
        MarketProbability(
            outcome="hold",
            probability=0.25,
            source="market",
            observed_at=NOW,
            source_url="https://example.test/market",
        ),
        MarketProbability(
            outcome="change",
            probability=0.75,
            source="market",
            observed_at=NOW,
            source_url="https://example.test/market",
        ),
    ]
    with pytest.raises(ValidationError, match="probability_timestamp"):
        _event(market_probabilities=distribution)


def test_market_distribution_must_sum_to_one() -> None:
    distribution = [
        MarketProbability(
            outcome="hold",
            probability=0.25,
            source="market",
            observed_at=NOW,
            source_url="https://example.test/market",
        ),
        MarketProbability(
            outcome="change",
            probability=0.25,
            source="market",
            observed_at=NOW,
            source_url="https://example.test/market",
        ),
    ]
    with pytest.raises(ValidationError, match="sum to one"):
        _event(market_probabilities=distribution, probability_timestamp=NOW)


def test_timezone_is_normalised_to_utc_and_original_zone_is_kept() -> None:
    local = datetime(2026, 9, 16, 14, 0, tzinfo=ZoneInfo("America/New_York"))
    event = _event(scheduled_at=local)

    assert event.scheduled_at == datetime(2026, 9, 16, 18, 0, tzinfo=UTC)
    assert event.timezone == "America/New_York"


def test_freshness_is_recomputed_and_never_stored_in_the_model() -> None:
    event = _event(last_updated=NOW)

    assert "freshness" not in event.model_dump()
    assert "age_seconds" not in event.model_dump()
    assert (
        event_freshness(event, NOW + timedelta(minutes=30)).freshness_status is EventFreshness.LIVE
    )
    assert event_freshness(event, NOW + timedelta(days=3)).freshness_status is EventFreshness.AGING
    assert event_freshness(event, NOW + timedelta(days=8)).freshness_status is EventFreshness.STALE


def test_unscheduled_event_does_not_require_a_fake_schedule() -> None:
    event = _event(
        event_type="STABLECOIN_DEPEG",
        category=FutureEventCategory.SYSTEMIC_RISK,
        schedule_type=EventScheduleType.UNSCHEDULED,
        title="Stablecoin loses its peg",
        scheduled_at=None,
        status=FutureEventStatus.ACTIVE,
    )

    assert event.scheduled_at is None
    assert event.runtime_status(NOW) is FutureEventStatus.ACTIVE


def test_scheduled_event_expires_after_its_explicit_end() -> None:
    event = _event(
        scheduled_at=NOW - timedelta(hours=2),
        expected_end_at=NOW - timedelta(hours=1),
    )

    assert event.runtime_status(NOW - timedelta(hours=1, minutes=30)) is FutureEventStatus.ACTIVE
    assert event.runtime_status(NOW) is FutureEventStatus.EXPIRED


def test_scheduled_event_without_an_end_has_a_bounded_active_window() -> None:
    event = _event(scheduled_at=NOW - timedelta(hours=7))

    assert event.runtime_status(NOW - timedelta(hours=6)) is FutureEventStatus.ACTIVE
    assert event.runtime_status(NOW) is FutureEventStatus.EXPIRED


def test_three_articles_about_one_decision_make_one_canonical_event() -> None:
    shared = {
        "entities": ["Federal Reserve"],
        "subject": "interest rate decision",
        "location": "United States",
    }
    events = [
        _event(title="Federal Reserve interest-rate decision", metadata=shared),
        _event(
            title="Fed announces rate decision",
            source="Reuters",
            source_tier=FutureEventSourceTier.C,
            source_url="https://reuters.example/fed-decision",
            metadata=shared,
        ),
        _event(
            title="FOMC rate decision due Wednesday",
            source="AP",
            source_tier=FutureEventSourceTier.C,
            source_url="https://ap.example/fomc",
            metadata=shared,
        ),
    ]

    result = EventDeduplicator().deduplicate(events)

    assert len(result) == 1
    assert result[0].source == "Federal Reserve"
    assert len(result[0].source_references) == 3
    assert result[0].metadata["corroborating_source_count"] == 3


def test_different_numeric_outcomes_are_not_deduplicated() -> None:
    first = _event(
        title="Inflation actual 2.4%",
        event_type="CPI_RELEASE",
        metadata={"entities": ["BLS"], "subject": "CPI", "numbers": ["2.4%"]},
    )
    second = _event(
        title="Inflation actual 2.8%",
        event_type="CPI_RELEASE",
        metadata={"entities": ["BLS"], "subject": "CPI", "numbers": ["2.8%"]},
    )
    assert len(EventDeduplicator().deduplicate([first, second])) == 2


def test_repository_round_trip_preserves_provenance_and_derives_runtime_fields() -> None:
    event = EventDeduplicator().canonicalise(_event())

    assert repo.save_future_events([event]) == 1
    restored = repo.future_event(event.canonical_event_id)

    assert restored is not None
    assert restored.source_url == event.source_url
    assert restored.source_tier is FutureEventSourceTier.A
    assert restored.evidence_ids == event.evidence_ids
    public = restored.to_public_dict(now=NOW + timedelta(hours=2))
    assert public["freshness_status"] == "FRESH"
    assert public["age_seconds"] == 7200
    assert public["status"] == "UPCOMING"

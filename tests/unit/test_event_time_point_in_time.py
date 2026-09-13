from datetime import UTC, datetime, timedelta

from crypto_intel.db import repo
from crypto_intel.future_events.models import (
    EventImportance,
    EventScheduleType,
    FutureEvent,
    FutureEventCategory,
    FutureEventSourceTier,
)
from crypto_intel.research.event_time import historical_event_times

NOW = datetime.now(UTC)


def _past_event(identifier: str, detected_at: datetime) -> FutureEvent:
    return FutureEvent(
        id=identifier,
        canonical_event_id=identifier,
        event_type="CPI",
        category=FutureEventCategory.MACRO,
        schedule_type=EventScheduleType.SCHEDULED,
        title=f"CPI {identifier}",
        source="Bureau of Labor Statistics",
        source_tier=FutureEventSourceTier.A,
        source_url="https://www.bls.gov/schedule/",
        scheduled_at=NOW - timedelta(days=10),
        detected_at=detected_at,
        last_updated=detected_at,
        importance=EventImportance.CRITICAL,
    )


def test_historical_events_exclude_information_observed_after_event(monkeypatch) -> None:
    safe = _past_event("known_before", NOW - timedelta(days=20))
    lookahead = _past_event("learned_after", NOW - timedelta(days=5))
    monkeypatch.setattr(repo, "list_future_events", lambda **_kwargs: [safe, lookahead])

    events = historical_event_times(["CPI"])

    assert [event["event_id"] for event in events] == ["known_before"]
    assert events[0]["observed_at"] <= events[0]["time"]
    assert events[0]["source_url"] == "https://www.bls.gov/schedule/"

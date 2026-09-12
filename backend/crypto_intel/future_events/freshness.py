"""Runtime freshness for future events."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from .models import EventScheduleType, FutureEvent


class EventFreshness(StrEnum):
    LIVE = "LIVE"
    FRESH = "FRESH"
    AGING = "AGING"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class EventFreshnessReading:
    freshness_status: EventFreshness
    observed_at: datetime | None
    fetched_at: datetime | None
    age_seconds: float | None

    def to_dict(self) -> dict[str, object]:
        return {
            "freshness_status": self.freshness_status.value,
            "observed_at": self.observed_at.isoformat() if self.observed_at else None,
            "fetched_at": self.fetched_at.isoformat() if self.fetched_at else None,
            "age_seconds": self.age_seconds,
        }


def event_freshness(event: FutureEvent, now: datetime | None = None) -> EventFreshnessReading:
    """Recompute freshness; no freshness label is ever persisted."""
    reference = now or datetime.now(UTC)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=UTC)
    else:
        reference = reference.astimezone(UTC)

    fetched = event.last_updated
    observed = event.source_published_at or event.detected_at
    if fetched is None:
        return EventFreshnessReading(EventFreshness.UNAVAILABLE, observed, None, None)

    age = (reference - fetched).total_seconds()
    if age < -300:
        return EventFreshnessReading(EventFreshness.UNAVAILABLE, observed, fetched, age)
    age = max(0.0, age)

    # Official schedules change slowly; unscheduled shocks require a much more
    # recent fetch before they are allowed to influence a current decision.
    if event.schedule_type is EventScheduleType.SCHEDULED:
        live, fresh, aging = 3600, 172800, 604800
    else:
        live, fresh, aging = 300, 1800, 14400

    status = (
        EventFreshness.LIVE
        if age <= live
        else EventFreshness.FRESH
        if age <= fresh
        else EventFreshness.AGING
        if age <= aging
        else EventFreshness.STALE
    )
    return EventFreshnessReading(status, observed, fetched, round(age, 3))

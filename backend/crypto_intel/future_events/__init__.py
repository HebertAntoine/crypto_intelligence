"""Future catalyst domain.

This package is deliberately independent from providers and presentation.  A
provider may discover an event, deterministic engines may enrich it, and both
the API and the clients read the same canonical model.
"""

from .deduplication import EventDeduplicator
from .freshness import EventFreshness, event_freshness
from .models import (
    DecisionHorizon,
    DirectionalBias,
    EventImportance,
    EventScheduleType,
    EventSourceReference,
    ExpectedMovement,
    FutureEvent,
    FutureEventCategory,
    FutureEventSourceTier,
    FutureEventStatus,
    MarketProbability,
)

__all__ = [
    "DecisionHorizon",
    "DirectionalBias",
    "EventDeduplicator",
    "EventFreshness",
    "EventImportance",
    "EventScheduleType",
    "EventSourceReference",
    "ExpectedMovement",
    "FutureEvent",
    "FutureEventCategory",
    "FutureEventSourceTier",
    "FutureEventStatus",
    "MarketProbability",
    "event_freshness",
]

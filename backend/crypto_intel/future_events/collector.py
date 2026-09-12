"""Fetch, deduplicate and persist catalysts without hiding source failures."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..core.enums import FetchStatus
from ..db import repo
from ..providers.base import FetchRequest
from ..providers.registry import ProviderRegistry, get_registry
from .deduplication import EventDeduplicator
from .models import FutureEvent

OFFICIAL_MACRO_CAPABILITIES = (
    "events.macro.fed",
    "events.macro.bls",
    "events.macro.bea",
    "events.macro.treasury",
)
OFFICIAL_REGULATORY_CAPABILITIES = (
    "events.regulation.feeds",
    "events.regulation.cftc",
    "events.regulation.house",
    "events.regulation.senate",
)
MARKET_EXPECTATION_CAPABILITIES = ("events.expectations.fed",)
GEOPOLITICAL_CAPABILITIES = ("events.geopolitical",)
ALL_EVENT_CAPABILITIES = (
    OFFICIAL_MACRO_CAPABILITIES
    + OFFICIAL_REGULATORY_CAPABILITIES
    + MARKET_EXPECTATION_CAPABILITIES
    + GEOPOLITICAL_CAPABILITIES
)


@dataclass(slots=True)
class EventCollectionReport:
    events: list[FutureEvent] = field(default_factory=list)
    saved: int = 0
    statuses: dict[str, FetchStatus] = field(default_factory=dict)
    failures: dict[str, str] = field(default_factory=dict)


class FutureEventCollector:
    def __init__(self, registry: ProviderRegistry | None = None) -> None:
        self.registry = registry or get_registry()
        self.deduplicator = EventDeduplicator()

    async def collect(
        self, capabilities: tuple[str, ...] = ALL_EVENT_CAPABILITIES
    ) -> EventCollectionReport:
        candidates: list[FutureEvent] = []
        statuses: dict[str, FetchStatus] = {}
        failures: dict[str, str] = {}
        for capability in capabilities:
            result = await self.registry.fetch(FetchRequest(capability=capability))
            statuses[capability] = result.status
            if result.ok:
                candidates.extend(result.events)
            else:
                failures[capability] = result.user_message

        events = self.deduplicator.deduplicate(candidates)
        saved = repo.save_future_events(events)
        # Temporary compatibility bridge for reports that still read the
        # legacy, scheduled-only table. The rich table remains authoritative.
        repo.save_events(
            [
                {
                    "id": event.canonical_event_id,
                    "kind": event.event_type,
                    "name": event.title,
                    "institution": event.source,
                    "scheduled_at": event.scheduled_at,
                    "importance": event.importance.value,
                    "summary": "",
                    "source_url": event.source_url,
                    "source_name": event.source,
                    "assets": [asset.value for asset in event.affected_assets],
                    "meta": {"future_event_id": event.canonical_event_id},
                }
                for event in events
                if event.scheduled_at is not None
            ]
        )
        return EventCollectionReport(
            events=events,
            saved=saved,
            statuses=statuses,
            failures=failures,
        )

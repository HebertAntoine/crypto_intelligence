"""Deterministic event identity and multi-source corroboration."""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from datetime import datetime
from typing import Any

from .models import (
    EventImportance,
    EventSourceReference,
    FutureEvent,
    FutureEventStatus,
    normalize_event_text,
)

_NUMERIC = re.compile(r"(?<![a-z])[-+]?\d+(?:[.,]\d+)?(?:\s?(?:%|bp|bps))?", re.I)
_STATUS_ORDER = {
    FutureEventStatus.SCHEDULED: 0,
    FutureEventStatus.UPCOMING: 1,
    FutureEventStatus.ACTIVE: 2,
    FutureEventStatus.RELEASED: 3,
    FutureEventStatus.SURPRISE: 4,
    FutureEventStatus.DECAYING: 5,
    FutureEventStatus.RESOLVED: 6,
    FutureEventStatus.EXPIRED: 7,
}


def _normalised_list(raw: Any) -> list[str]:
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list | tuple | set):
        return []
    return sorted({normalize_event_text(str(item)) for item in raw if str(item).strip()})


class EventDeduplicator:
    """Collapse coverage of the same real-world occurrence into one event.

    Providers should populate ``metadata.entities``, ``metadata.subject`` and
    ``metadata.location`` when the source exposes them.  The title remains a
    fallback only; URLs never participate in identity because syndication gives
    the same event many URLs.
    """

    def signature(self, event: FutureEvent) -> str:
        meta = event.metadata
        entities = _normalised_list(meta.get("entities"))
        subject = normalize_event_text(str(meta.get("subject") or ""))
        location = normalize_event_text(str(meta.get("location") or ""))
        moment = event.scheduled_at or event.source_published_at or event.detected_at
        bucket = self._time_bucket(moment, event.event_type)
        numbers = _normalised_list(meta.get("numbers"))
        if not numbers and not subject:
            numbers = sorted(set(_NUMERIC.findall(event.title)))

        # When structured fields are absent, retain the meaningful title.  It
        # is less powerful than entities+subject, but still avoids URL-based
        # duplication and never merges two different numerical releases.
        fallback_subject = subject or normalize_event_text(event.title)
        parts = [
            ",".join(entities),
            normalize_event_text(event.event_type),
            bucket,
            location,
            fallback_subject,
            ",".join(numbers),
        ]
        return "|".join(parts)

    @staticmethod
    def _time_bucket(moment: datetime, event_type: str) -> str:
        # Releases and scheduled decisions are identified to the hour.  News
        # shocks use the same bucket so syndicated dispatches a few minutes
        # apart collapse without merging separate developments later that day.
        return moment.replace(minute=0, second=0, microsecond=0).isoformat()

    def canonicalise(self, event: FutureEvent) -> FutureEvent:
        signature = self.signature(event)
        canonical_id = "fev_" + hashlib.sha256(signature.encode("utf-8")).hexdigest()[:24]
        return event.model_copy(
            update={
                "id": canonical_id,
                "canonical_event_id": canonical_id,
                "event_signature": signature,
            }
        )

    def deduplicate(self, events: list[FutureEvent]) -> list[FutureEvent]:
        grouped: dict[str, list[FutureEvent]] = defaultdict(list)
        for event in events:
            canonical = self.canonicalise(event)
            grouped[canonical.event_signature].append(canonical)

        merged = [self._merge(group) for group in grouped.values()]
        merged.sort(
            key=lambda event: (
                event.scheduled_at or event.detected_at,
                -event.importance.rank,
            )
        )
        return merged

    def _merge(self, events: list[FutureEvent]) -> FutureEvent:
        best = min(
            events,
            key=lambda event: (
                event.source_tier.rank,
                event.source_published_at or event.detected_at,
            ),
        )

        references: dict[tuple[str, str, str], EventSourceReference] = {}
        for event in events:
            for reference in event.source_references:
                key = (reference.source, reference.url or "", reference.reference or "")
                references[key] = reference

        assets = sorted(
            {asset for event in events for asset in event.affected_assets},
            key=lambda asset: asset.value,
        )
        markets = sorted({market for event in events for market in event.affected_markets})
        evidence = sorted({item for event in events for item in event.evidence_ids})
        importance = max((event.importance for event in events), key=lambda value: value.rank)
        status = max((event.status for event in events), key=lambda value: _STATUS_ORDER[value])

        # Market pricing is complementary evidence, not a claim that competes
        # with the official calendar. Keep the most authoritative, freshest
        # timestamped distribution while retaining the Tier-A event identity.
        priced = [
            event
            for event in events
            if event.market_probabilities and event.probability_timestamp is not None
        ]
        probability_source = min(
            priced,
            key=lambda event: (
                event.source_tier.rank,
                -(event.probability_timestamp or event.detected_at).timestamp(),
            ),
        ) if priced else None

        # Values and market probabilities come only from the most authoritative
        # event.  Corroboration raises neither the probability nor the effect.
        return best.model_copy(
            update={
                "importance": EventImportance(importance),
                "status": status,
                "affected_assets": assets,
                "affected_markets": markets,
                "evidence_ids": evidence,
                "source_references": sorted(
                    references.values(), key=lambda ref: (ref.tier.rank, ref.source)
                ),
                "detected_at": min(event.detected_at for event in events),
                "last_updated": max(event.last_updated for event in events),
                "confidence": max(event.confidence for event in events),
                "consensus": (
                    probability_source.consensus if probability_source else best.consensus
                ),
                "outcome_space": (
                    probability_source.outcome_space if probability_source else best.outcome_space
                ),
                "market_probabilities": (
                    probability_source.market_probabilities
                    if probability_source
                    else best.market_probabilities
                ),
                "probability_timestamp": (
                    probability_source.probability_timestamp
                    if probability_source
                    else best.probability_timestamp
                ),
                "metadata": {
                    **best.metadata,
                    "corroborating_source_count": len(references),
                },
            }
        )

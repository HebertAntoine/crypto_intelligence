"""Concrete-event extraction from configured news feeds.

This is not sentiment analysis. Only explicit actions (closure, strike,
sanction, production decision, reserve release, ceasefire) become events.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any

from bs4 import BeautifulSoup

from ...core.enums import Asset, FetchStatus, ProviderCategory
from ...future_events.deduplication import EventDeduplicator
from ...future_events.models import (
    DirectionalBias,
    EventImportance,
    EventScheduleType,
    ExpectedMovement,
    FutureEvent,
    FutureEventCategory,
    FutureEventSourceTier,
    FutureEventStatus,
)
from ..base import BaseProvider, FetchRequest, FetchResult
from ..news.rss import RSSNewsProvider

_PATTERNS: tuple[
    tuple[re.Pattern[str], str, FutureEventCategory, DirectionalBias, list[str]], ...
] = (
    (
        re.compile(r"\b(?:closed|closes|blocked|shut)\b.{0,60}\b(?:strait|hormuz|suez|chokepoint)\b|\b(?:strait|hormuz|suez)\b.{0,60}\b(?:closed|blocked|shut)\b", re.I),
        "CHOKEPOINT_CLOSURE",
        FutureEventCategory.ENERGY,
        DirectionalBias.BEARISH,
        ["Passage énergétique perturbé", "Risque d’offre pétrolière réduit", "Pétrole potentiellement plus cher", "Inflation anticipée potentiellement plus forte", "Conditions monétaires potentiellement moins favorables", "Pression possible sur les crypto-actifs"],
    ),
    (
        re.compile(r"\b(?:attack|strike|bombing|hit)\b.{0,80}\b(?:oil|refinery|pipeline|terminal|energy infrastructure)\b", re.I),
        "ENERGY_INFRASTRUCTURE_ATTACK",
        FutureEventCategory.ENERGY,
        DirectionalBias.BEARISH,
        ["Infrastructure énergétique attaquée", "Offre potentiellement réduite", "Pétrole potentiellement plus cher", "Risque inflationniste accru", "Pression possible sur les actifs risqués"],
    ),
    (
        re.compile(r"\b(?:pipeline)\b.{0,60}\b(?:halted|stopped|shutdown|disruption|leak)\b", re.I),
        "PIPELINE_DISRUPTION",
        FutureEventCategory.ENERGY,
        DirectionalBias.BEARISH,
        ["Pipeline perturbé", "Offre énergétique réduite", "Pression potentielle sur le pétrole", "Risque inflationniste", "Pression possible sur les crypto-actifs"],
    ),
    (
        re.compile(r"\b(?:imposes?|announces?|expands?)\b.{0,50}\bsanctions?\b", re.I),
        "SANCTIONS",
        FutureEventCategory.GEOPOLITICAL,
        DirectionalBias.BEARISH,
        ["Sanctions annoncées", "Commerce ou financement contraint", "Aversion au risque potentiellement accrue", "Pression possible sur les crypto-actifs"],
    ),
    (
        re.compile(r"\b(?:ceasefire|peace agreement)\b.{0,60}\b(?:agreed|signed|takes effect|begins)\b|\b(?:agreed|signed)\b.{0,60}\bceasefire\b", re.I),
        "CEASEFIRE",
        FutureEventCategory.GEOPOLITICAL,
        DirectionalBias.BULLISH,
        ["Cessez-le-feu confirmé", "Risque géopolitique aigu réduit", "Aversion au risque potentiellement moindre", "Soutien possible aux actifs risqués"],
    ),
    (
        re.compile(r"\bOPEC\+?\b.{0,80}\b(?:cut|raise|increase|reduce|production|output)\b", re.I),
        "OPEC_PRODUCTION_CHANGE",
        FutureEventCategory.ENERGY,
        DirectionalBias.NEUTRAL,
        ["Décision de production OPEP", "Offre pétrolière modifiée", "Effet sur le pétrole à confirmer", "Transmission inflation/taux à surveiller"],
    ),
    (
        re.compile(r"\b(?:strategic petroleum reserve|SPR)\b.{0,50}\b(?:release|sale|drawdown)\b", re.I),
        "STRATEGIC_RESERVE_RELEASE",
        FutureEventCategory.ENERGY,
        DirectionalBias.BULLISH,
        ["Libération de réserves stratégiques", "Offre disponible accrue", "Pression pétrolière potentiellement réduite", "Risque inflationniste potentiellement moindre"],
    ),
)


def geopolitical_items_to_events(
    items: list[dict[str, Any]], *, fetched_at: datetime | None = None
) -> list[FutureEvent]:
    detected = fetched_at or datetime.now(UTC)
    if detected.tzinfo is None:
        detected = detected.replace(tzinfo=UTC)
    events: list[FutureEvent] = []
    tier_map = {1: FutureEventSourceTier.A, 2: FutureEventSourceTier.C, 3: FutureEventSourceTier.D, 4: FutureEventSourceTier.E}
    for item in items:
        title = str(item.get("title") or "").strip()
        summary = BeautifulSoup(str(item.get("summary") or ""), "lxml").get_text(" ", strip=True)
        text = f"{title}. {summary}"
        match = next((rule for rule in _PATTERNS if rule[0].search(text)), None)
        published = item.get("published_at")
        source_url = str(item.get("url") or "").strip()
        if not match or not isinstance(published, datetime) or not source_url:
            continue
        if published.tzinfo is None:
            published = published.replace(tzinfo=UTC)
        pattern, concrete_type, category, direction, chain = match
        del pattern
        source = str(item.get("source") or "News provider")
        tier = tier_map.get(int(item.get("tier", 4)), FutureEventSourceTier.E)
        # Discovery-grade sources may surface an event in the timeline, but
        # confidence stays low and source hierarchy prevents them overriding A-C.
        confidence = {FutureEventSourceTier.A: 1.0, FutureEventSourceTier.C: 0.85, FutureEventSourceTier.D: 0.55, FutureEventSourceTier.E: 0.2}[tier]
        event = FutureEvent(
            event_type=concrete_type,
            category=category,
            schedule_type=EventScheduleType.UNSCHEDULED,
            title=title,
            source=source,
            source_tier=tier,
            source_url=source_url,
            source_published_at=published.astimezone(UTC),
            detected_at=detected,
            status=FutureEventStatus.ACTIVE,
            affected_assets=[Asset.BTC, Asset.ETH, Asset.SOL],
            affected_markets=["crypto", "energy", "risk_assets"],
            importance=EventImportance.HIGH,
            directional_effect=direction,
            magnitude_effect=ExpectedMovement.HIGH,
            confidence=confidence,
            causal_chain=chain,
            last_updated=detected,
            expires_at=published.astimezone(UTC) + timedelta(days=7),
            metadata={
                "entities": item.get("entities") or [],
                "subject": concrete_type,
                "location": item.get("location") or "",
                "concrete_type": concrete_type,
            },
        )
        events.append(EventDeduplicator().canonicalise(event))
    return EventDeduplicator().deduplicate(events)


class GeopoliticalFeedProvider(BaseProvider):
    name = "geopolitical_feeds"
    source = "Configured RSS news feeds"
    category = ProviderCategory.NEWS
    capabilities = ("events.geopolitical",)
    source_url = "multiple"

    async def fetch(self, request: FetchRequest) -> FetchResult:
        raw = await RSSNewsProvider().fetch(FetchRequest(capability="news.feed"))
        if raw.status is not FetchStatus.OK or not raw.raw:
            return FetchResult.failure(raw.status, self.name, raw.user_message)
        events = geopolitical_items_to_events((raw.raw or {}).get("items", []))
        if not events:
            return FetchResult.failure(
                FetchStatus.NO_DATA,
                self.name,
                "No concrete geopolitical event detected in available feeds",
            )
        return FetchResult.success_events(events, self.name, raw={"feed_failures": (raw.raw or {}).get("failures", [])})

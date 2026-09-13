"""Official Ethereum and Solana protocol announcements and incidents.

Only source-owned pages are read.  Blog posts are catalysts for a short,
explicit lifetime; Solana status incidents remain active until the official
status page resolves them.  Direction is always neutral because an upgrade or
outage does not, by itself, establish the market's price direction.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any

import feedparser
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
from ..http import get_http
from ..news.rss import _parse_entry_time

ETHEREUM_FEED_URL = "https://blog.ethereum.org/en/feed.xml"
SOLANA_NEWS_URL = "https://solana.com/news"
SOLANA_STATUS_API_URL = "https://status.solana.com/api/v2/incidents.json"

_PROTOCOL_TERMS = re.compile(
    r"\b(protocol|mainnet|testnet|network|upgrade|hard\s*fork|activation|validator|"
    r"incident|outage|halt|restart|security|slot\s*time)\b",
    re.I,
)
_MAJOR_ETHEREUM_TERMS = re.compile(
    r"\b(mainnet|testnet|network\s+upgrade|hard\s*fork|activation|incident|outage|"
    r"halt|restart|security\s+alert|exploit)\b",
    re.I,
)
_INCIDENT_TERMS = re.compile(r"\b(incident|outage|halt|restart|attack|exploit)\b", re.I)
_MAINNET_TERMS = re.compile(r"\b(mainnet|mainnet-beta|network outage)\b", re.I)
_EXPLICIT_UTC = re.compile(
    r"\b(\w+\s+\d{1,2}(?:st|nd|rd|th)?[,]?\s+20\d{2})"
    r"(?:[,]?|\s+at)\s+(\d{1,2}:\d{2}(?::\d{2})?)\s+UTC\b",
    re.I,
)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    # Both official JSON sources occasionally omit an offset.  Their APIs and
    # status pages are UTC-based; keep that normalization explicit in metadata.
    return _as_utc(parsed)


def _scheduled_utc(text: str) -> datetime | None:
    """Extract a schedule only when the official text states an exact UTC time."""
    match = _EXPLICIT_UTC.search(text)
    if not match:
        return None
    date_text = re.sub(r"(\d)(?:st|nd|rd|th)\b", r"\1", match.group(1), flags=re.I)
    date_text = date_text.replace(",", "")
    for time_format in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(
                f"{date_text} {match.group(2)}", f"%B %d %Y {time_format}"
            ).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def _classification(text: str, chain: str) -> tuple[str, EventImportance, ExpectedMovement]:
    incident = bool(_INCIDENT_TERMS.search(text))
    mainnet = bool(_MAINNET_TERMS.search(text))
    if incident:
        event_type = f"{chain}_NETWORK_INCIDENT"
    elif "testnet" in text.lower():
        event_type = f"{chain}_TESTNET_EVENT"
    else:
        event_type = f"{chain}_PROTOCOL_UPGRADE"
    importance = (
        EventImportance.CRITICAL
        if incident and mainnet
        else EventImportance.HIGH
        if incident or mainnet
        else EventImportance.MEDIUM
    )
    movement = (
        ExpectedMovement.HIGH
        if importance in {EventImportance.CRITICAL, EventImportance.HIGH}
        else ExpectedMovement.NORMAL
    )
    return event_type, importance, movement


def _announcement_event(
    *,
    chain: str,
    asset: Asset,
    title: str,
    body: str,
    source: str,
    source_url: str,
    published_at: datetime,
    detected_at: datetime,
    metadata: dict[str, Any] | None = None,
) -> FutureEvent:
    scheduled = _scheduled_utc(f"{title}. {body}")
    event_type, importance, movement = _classification(f"{title}. {body}", chain)
    causal_chain = (
        [
            "Incident réseau confirmé par la source officielle",
            "Disponibilité ou finalité du réseau potentiellement dégradée",
            "Amplitude de marché potentiellement accrue sans direction certaine",
        ]
        if "INCIDENT" in event_type
        else [
            "Annonce officielle du protocole",
            "Modification ou activation réseau à surveiller",
            "Risque opérationnel et réaction de marché à confirmer",
        ]
    )
    event = FutureEvent(
        event_type=event_type,
        category=FutureEventCategory.PROTOCOL,
        schedule_type=(EventScheduleType.SCHEDULED if scheduled else EventScheduleType.UNSCHEDULED),
        title=title,
        source=source,
        source_tier=FutureEventSourceTier.A,
        source_url=source_url,
        source_published_at=published_at,
        detected_at=detected_at,
        scheduled_at=scheduled,
        timezone="UTC",
        status=(FutureEventStatus.SCHEDULED if scheduled else FutureEventStatus.RELEASED),
        affected_assets=[asset],
        affected_markets=["crypto", chain.lower(), "protocol"],
        importance=importance,
        directional_effect=DirectionalBias.NEUTRAL,
        magnitude_effect=movement,
        confidence=1.0,
        causal_chain=causal_chain,
        last_updated=published_at,
        expires_at=None if scheduled else published_at + timedelta(days=14),
        metadata={
            "entities": [source, chain],
            "subject": event_type,
            "location": f"{chain} network",
            "direction_not_inferred": True,
            **(metadata or {}),
        },
    )
    return EventDeduplicator().canonicalise(event)


def parse_ethereum_protocol_feed(
    xml: str, *, fetched_at: datetime | None = None
) -> list[FutureEvent]:
    detected = _as_utc(fetched_at) or datetime.now(UTC)
    parsed = feedparser.parse(xml)
    events: list[FutureEvent] = []
    for entry in parsed.entries:
        title = str(entry.get("title") or "").strip()
        link = str(entry.get("link") or "").strip()
        published = _as_utc(_parse_entry_time(entry))
        tags = {
            str(item.get("term") or "").strip().lower()
            for item in entry.get("tags", [])
            if isinstance(item, dict)
        }
        content = " ".join(
            str(item.get("value") or "")
            for item in entry.get("content", [])
            if isinstance(item, dict)
        )
        summary = str(entry.get("summary") or "")
        body = BeautifulSoup(f"{summary} {content}", "lxml").get_text(" ", strip=True)
        combined = f"{title}. {body}"
        official_protocol_category = any(tag.startswith("protocol") for tag in tags)
        if (
            not title
            or not link.startswith("https://blog.ethereum.org/")
            or published is None
            or (not official_protocol_category and not _MAJOR_ETHEREUM_TERMS.search(title))
        ):
            continue
        scheduled = _scheduled_utc(combined)
        if published < detected - timedelta(days=45) and (
            scheduled is None or scheduled < detected
        ):
            continue
        events.append(
            _announcement_event(
                chain="ETHEREUM",
                asset=Asset.ETH,
                title=title,
                body=body,
                source="Ethereum Foundation Blog",
                source_url=link,
                published_at=published,
                detected_at=detected,
                metadata={"feed_url": ETHEREUM_FEED_URL, "categories": sorted(tags)},
            )
        )
    return EventDeduplicator().deduplicate(events)


def _walk_json(value: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        if value.get("@type") == "BlogPosting":
            found.append(value)
        for child in value.values():
            found.extend(_walk_json(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(_walk_json(child))
    return found


def parse_solana_news(html: str, *, fetched_at: datetime | None = None) -> list[FutureEvent]:
    detected = _as_utc(fetched_at) or datetime.now(UTC)
    soup = BeautifulSoup(html, "lxml")
    posts: list[dict[str, Any]] = []
    for node in soup.select('script[type="application/ld+json"]'):
        try:
            posts.extend(_walk_json(json.loads(node.get_text())))
        except (json.JSONDecodeError, TypeError):
            continue

    events: list[FutureEvent] = []
    seen_urls: set[str] = set()
    for post in posts:
        title = str(post.get("headline") or post.get("name") or "").strip()
        body = str(post.get("description") or "").strip()
        section = str(post.get("articleSection") or "").strip()
        url = str(post.get("url") or "").strip()
        published = _parse_iso(post.get("datePublished"))
        combined = f"{title}. {body}"
        relevant_section = section.lower() in {"upgrades", "network"}
        if (
            not title
            or url in seen_urls
            or not url.startswith("https://solana.com/news/")
            or published is None
            or (not relevant_section and not _PROTOCOL_TERMS.search(combined))
        ):
            continue
        scheduled = _scheduled_utc(combined)
        if published < detected - timedelta(days=45) and (
            scheduled is None or scheduled < detected
        ):
            continue
        seen_urls.add(url)
        events.append(
            _announcement_event(
                chain="SOLANA",
                asset=Asset.SOL,
                title=title,
                body=body,
                source="Solana Foundation",
                source_url=url,
                published_at=published,
                detected_at=detected,
                metadata={
                    "news_url": SOLANA_NEWS_URL,
                    "article_section": section,
                    "source_timezone_normalization": "UTC when JSON-LD offset is omitted",
                },
            )
        )
    return EventDeduplicator().deduplicate(events)


def parse_solana_incidents(
    payload: Any, *, fetched_at: datetime | None = None
) -> list[FutureEvent]:
    detected = _as_utc(fetched_at) or datetime.now(UTC)
    rows = payload.get("incidents", []) if isinstance(payload, dict) else []
    events: list[FutureEvent] = []
    importance_by_impact = {
        "critical": EventImportance.CRITICAL,
        "major": EventImportance.HIGH,
        "minor": EventImportance.MEDIUM,
        "none": EventImportance.LOW,
    }
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        incident_id = str(row.get("id") or "").strip()
        title = str(row.get("name") or "").strip()
        status = str(row.get("status") or "").lower()
        created = _parse_iso(row.get("created_at"))
        updated = _parse_iso(row.get("updated_at")) or created
        resolved = _parse_iso(row.get("resolved_at"))
        if not incident_id or not title or created is None or updated is None:
            continue
        if status == "resolved" and (resolved is None or resolved < detected - timedelta(days=7)):
            continue
        importance = importance_by_impact.get(
            str(row.get("impact") or "none").lower(), EventImportance.MEDIUM
        )
        updates = row.get("incident_updates") or []
        latest_body = ""
        if isinstance(updates, list) and updates and isinstance(updates[0], dict):
            latest_body = str(updates[0].get("body") or "").strip()
        event = FutureEvent(
            event_type="SOLANA_NETWORK_INCIDENT",
            category=FutureEventCategory.PROTOCOL,
            schedule_type=EventScheduleType.UNSCHEDULED,
            title=title,
            source="Solana Status",
            source_tier=FutureEventSourceTier.A,
            source_url=f"https://status.solana.com/incidents/{incident_id}",
            source_reference=incident_id,
            source_published_at=created,
            detected_at=detected,
            status=(
                FutureEventStatus.DECAYING if status == "resolved" else FutureEventStatus.ACTIVE
            ),
            affected_assets=[Asset.SOL],
            affected_markets=["crypto", "solana", "protocol"],
            importance=importance,
            directional_effect=DirectionalBias.NEUTRAL,
            magnitude_effect=(
                ExpectedMovement.HIGH
                if importance in {EventImportance.CRITICAL, EventImportance.HIGH}
                else ExpectedMovement.NORMAL
            ),
            confidence=1.0,
            causal_chain=[
                "Incident publié par le statut officiel Solana",
                "État du réseau ou d'un composant potentiellement dégradé",
                "Amplitude potentielle accrue; direction de prix non déduite",
            ],
            last_updated=updated,
            expires_at=resolved + timedelta(days=7) if resolved else None,
            metadata={
                "entities": ["Solana", "Solana Status"],
                "subject": "network incident",
                "location": "Solana mainnet",
                "official_status": status,
                "impact": str(row.get("impact") or "none"),
                "latest_update": latest_body,
                "direction_not_inferred": True,
            },
        )
        events.append(EventDeduplicator().canonicalise(event))
    return EventDeduplicator().deduplicate(events)


class EthereumProtocolProvider(BaseProvider):
    name = "ethereum_protocol"
    source = "Ethereum Foundation Blog"
    category = ProviderCategory.NEWS
    capabilities = ("events.protocol.ethereum",)
    source_url = ETHEREUM_FEED_URL
    base_confidence = 100.0

    async def fetch(self, request: FetchRequest) -> FetchResult:
        result = await get_http().get_text(
            self.source_url,
            provider=self.name,
            cache_ttl=10800,
            rate_limit_per_min=4,
            retries=0,
        )
        if not result.ok:
            return FetchResult.failure(result.status, self.name, result.message)
        events = parse_ethereum_protocol_feed(result.data)
        if not events:
            return FetchResult.failure(
                FetchStatus.NO_DATA, self.name, "No recent official Ethereum protocol catalyst"
            )
        return FetchResult.success_events(events, self.name)


class SolanaProtocolProvider(BaseProvider):
    name = "solana_protocol"
    source = "Solana Foundation and Solana Status"
    category = ProviderCategory.NEWS
    capabilities = ("events.protocol.solana",)
    source_url = SOLANA_NEWS_URL
    base_confidence = 100.0

    async def fetch(self, request: FetchRequest) -> FetchResult:
        events: list[FutureEvent] = []
        failures: list[str] = []
        news = await get_http().get_text(
            SOLANA_NEWS_URL,
            provider=self.name,
            cache_ttl=10800,
            rate_limit_per_min=4,
            retries=0,
        )
        if news.ok:
            events.extend(parse_solana_news(news.data))
        else:
            failures.append(f"news: {news.status.value}")
        incidents = await get_http().get_json(
            SOLANA_STATUS_API_URL,
            provider=self.name,
            cache_ttl=300,
            rate_limit_per_min=6,
            retries=0,
        )
        if incidents.ok:
            events.extend(parse_solana_incidents(incidents.data))
        else:
            failures.append(f"status: {incidents.status.value}")
        events = EventDeduplicator().deduplicate(events)
        if not events:
            return FetchResult.failure(
                FetchStatus.NO_DATA,
                self.name,
                "; ".join(failures) if failures else "No recent official Solana catalyst",
            )
        return FetchResult.success_events(events, self.name, raw={"failures": failures})

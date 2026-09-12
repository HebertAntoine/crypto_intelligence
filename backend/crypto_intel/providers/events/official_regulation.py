"""Official regulatory feeds and calendars, with legislative-stage fidelity."""

from __future__ import annotations

from contextlib import suppress
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import feedparser
from bs4 import BeautifulSoup

from ...config_loader import providers_config
from ...core.enums import Asset, FetchStatus, ProviderCategory
from ...engines.regulatory_catalyst import RegulatoryCatalystEngine, RegulatoryStage
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
from ...settings import get_settings
from ..base import BaseProvider, FetchRequest, FetchResult
from ..http import get_http
from ..news.rss import _parse_entry_time

EASTERN = ZoneInfo("America/New_York")
ALL_ASSETS = [Asset.BTC, Asset.ETH, Asset.SOL]
_CRYPTO_TERMS = (
    "crypto", "digital asset", "bitcoin", "ethereum", "solana", "stablecoin",
    "tokenization", "blockchain", "distributed ledger", "clarity act",
)


def _relevant(text: str) -> bool:
    lowered = " ".join(text.lower().split())
    return any(term in lowered for term in _CRYPTO_TERMS)


def _assets(text: str) -> list[Asset]:
    lowered = text.lower()
    selected: list[Asset] = []
    if "bitcoin" in lowered or " btc" in lowered:
        selected.append(Asset.BTC)
    if "ethereum" in lowered or " ether" in lowered or " eth" in lowered:
        selected.append(Asset.ETH)
    if "solana" in lowered or " sol" in lowered:
        selected.append(Asset.SOL)
    return selected or ALL_ASSETS


def _importance(stage: RegulatoryStage) -> EventImportance:
    if stage in {
        RegulatoryStage.CLOTURE,
        RegulatoryStage.PASSED_HOUSE,
        RegulatoryStage.PASSED_SENATE,
        RegulatoryStage.PRESENTED_TO_PRESIDENT,
        RegulatoryStage.SIGNED_INTO_LAW,
        RegulatoryStage.FINAL_RULE,
        RegulatoryStage.EFFECTIVE,
    }:
        return EventImportance.CRITICAL
    if stage in {
        RegulatoryStage.COMMITTEE_MARKUP,
        RegulatoryStage.COMMITTEE_APPROVAL,
        RegulatoryStage.PROPOSED_RULE,
        RegulatoryStage.ENFORCEMENT,
    }:
        return EventImportance.HIGH
    return EventImportance.MEDIUM


def _canonical(event: FutureEvent) -> FutureEvent:
    return EventDeduplicator().canonicalise(event)


def regulatory_feed_items_to_events(
    items: list[dict[str, Any]], *, fetched_at: datetime | None = None
) -> list[FutureEvent]:
    detected = fetched_at or datetime.now(UTC)
    if detected.tzinfo is None:
        detected = detected.replace(tzinfo=UTC)
    events: list[FutureEvent] = []
    classifier = RegulatoryCatalystEngine()
    for item in items:
        title = str(item.get("title") or "").strip()
        summary = BeautifulSoup(str(item.get("summary") or ""), "lxml").get_text(" ", strip=True)
        combined = f"{title} {summary}"
        source_url = str(item.get("url") or "").strip()
        published = item.get("published_at")
        if not _relevant(combined) or not source_url or not isinstance(published, datetime):
            continue
        if published.tzinfo is None:
            published = published.replace(tzinfo=UTC)
        published = published.astimezone(UTC)
        stage = classifier.classify_stage(combined)
        institution = str(item.get("institution") or item.get("source") or "Official source")
        events.append(
            _canonical(
                FutureEvent(
                    event_type=f"{institution.upper()}_REGULATORY_{stage.value}",
                    category=FutureEventCategory.REGULATION,
                    schedule_type=EventScheduleType.UNSCHEDULED,
                    title=title,
                    source=institution,
                    source_tier=FutureEventSourceTier.A,
                    source_url=source_url,
                    source_published_at=published,
                    detected_at=detected,
                    status=FutureEventStatus.RELEASED,
                    affected_assets=_assets(combined),
                    affected_markets=["crypto", "regulation"],
                    importance=_importance(stage),
                    directional_effect=DirectionalBias.NEUTRAL,
                    magnitude_effect=ExpectedMovement.HIGH if _importance(stage) is EventImportance.CRITICAL else ExpectedMovement.NORMAL,
                    confidence=1.0,
                    last_updated=detected,
                    expires_at=published + timedelta(days=14),
                    metadata={
                        "entities": [institution],
                        "subject": title,
                        "location": "United States",
                        "regulatory_stage": stage.value,
                        "stage_is_completed_only": True,
                    },
                )
            )
        )
    return EventDeduplicator().deduplicate(events)


def parse_cftc_calendar(html: str, *, fetched_at: datetime | None = None) -> list[FutureEvent]:
    detected = fetched_at or datetime.now(UTC)
    if detected.tzinfo is None:
        detected = detected.replace(tzinfo=UTC)
    soup = BeautifulSoup(html, "lxml")
    events: list[FutureEvent] = []
    for row in soup.select("table tbody tr"):
        title_node = row.select_one("td.views-field-title a[href]")
        start_node = row.select_one(".field-start-date time[datetime]") or row.select_one("time[datetime]")
        if not title_node or not start_node:
            continue
        text = row.get_text(" ", strip=True)
        if not _relevant(text):
            continue
        try:
            scheduled = datetime.fromisoformat(start_node["datetime"].replace("Z", "+00:00")).astimezone(UTC)
        except (ValueError, KeyError):
            continue
        end_node = row.select_one(".field-end-date time[datetime]")
        expected_end = None
        if end_node:
            with suppress(ValueError, KeyError):
                expected_end = datetime.fromisoformat(end_node["datetime"].replace("Z", "+00:00")).astimezone(UTC)
        title = title_node.get_text(" ", strip=True)
        stage = RegulatoryCatalystEngine.classify_stage(text)
        events.append(
            _canonical(
                FutureEvent(
                    event_type=f"CFTC_{stage.value}",
                    category=FutureEventCategory.REGULATION,
                    schedule_type=EventScheduleType.SCHEDULED,
                    title=title,
                    source="CFTC",
                    source_tier=FutureEventSourceTier.A,
                    source_url=urljoin("https://www.cftc.gov/PressRoom/Events", title_node["href"]),
                    detected_at=detected,
                    scheduled_at=scheduled,
                    timezone="UTC",
                    expected_end_at=expected_end,
                    affected_assets=_assets(text),
                    affected_markets=["crypto", "derivatives", "regulation"],
                    importance=_importance(stage),
                    directional_effect=DirectionalBias.NEUTRAL,
                    magnitude_effect=ExpectedMovement.NORMAL,
                    confidence=1.0,
                    last_updated=detected,
                    metadata={
                        "entities": ["CFTC"],
                        "subject": title,
                        "location": "United States",
                        "regulatory_stage": stage.value,
                        "stage_is_completed_only": True,
                    },
                )
            )
        )
    return EventDeduplicator().deduplicate(events)


def parse_house_calendar(html: str, *, fetched_at: datetime | None = None) -> list[FutureEvent]:
    detected = fetched_at or datetime.now(UTC)
    if detected.tzinfo is None:
        detected = detected.replace(tzinfo=UTC)
    soup = BeautifulSoup(html, "lxml")
    events: list[FutureEvent] = []
    for article in soup.select(".events-future article.card-h-event"):
        title_node = article.select_one("h3 a[href]")
        date_node = article.select_one("time")
        time_node = article.select_one("footer span")
        if not title_node or not date_node or not time_node:
            continue
        text = article.get_text(" ", strip=True)
        if not _relevant(text):
            continue
        date_text = " ".join(span.get_text(" ", strip=True) for span in date_node.find_all("span"))
        try:
            naive = datetime.strptime(
                f"{date_text} {time_node.get_text(' ', strip=True)}", "%b %d %Y %I:%M %p"
            )
        except ValueError:
            continue
        scheduled = naive.replace(tzinfo=EASTERN).astimezone(UTC)
        title = title_node.get_text(" ", strip=True)
        stage = RegulatoryCatalystEngine.classify_stage(text)
        events.append(
            _canonical(
                FutureEvent(
                    event_type=f"HOUSE_{stage.value}",
                    category=FutureEventCategory.REGULATION,
                    schedule_type=EventScheduleType.SCHEDULED,
                    title=title,
                    source="U.S. House Financial Services Committee",
                    source_tier=FutureEventSourceTier.A,
                    source_url=urljoin("https://financialservices.house.gov/calendar/", title_node["href"]),
                    detected_at=detected,
                    scheduled_at=scheduled,
                    timezone="America/New_York",
                    affected_assets=_assets(text),
                    affected_markets=["crypto", "regulation"],
                    importance=_importance(stage),
                    directional_effect=DirectionalBias.NEUTRAL,
                    magnitude_effect=ExpectedMovement.NORMAL,
                    confidence=1.0,
                    last_updated=detected,
                    metadata={
                        "entities": ["U.S. House"],
                        "subject": title,
                        "location": (article.select_one("address").get_text(" ", strip=True) if article.select_one("address") else "United States"),
                        "regulatory_stage": stage.value,
                        "stage_is_completed_only": True,
                    },
                )
            )
        )
    return EventDeduplicator().deduplicate(events)


class OfficialRegulatoryFeedProvider(BaseProvider):
    name = "official_regulatory_feeds"
    source = "Official US regulatory RSS feeds"
    category = ProviderCategory.REGULATION
    capabilities = ("events.regulation.feeds",)
    source_url = "multiple"
    base_confidence = 100.0

    async def fetch(self, request: FetchRequest) -> FetchResult:
        feeds = providers_config().get("feeds", {}).get("regulation", []) or []
        items: list[dict[str, Any]] = []
        failures: list[str] = []
        for feed in feeds:
            url = str(feed.get("url") or "")
            if not url:
                continue
            headers = {"User-Agent": get_settings().sec_user_agent} if "sec.gov" in url else None
            result = await get_http().get_text(
                url, provider=self.name, headers=headers, cache_ttl=900,
                rate_limit_per_min=20, retries=0,
            )
            if not result.ok:
                failures.append(f"{feed.get('name', url)}: {result.status.value}")
                continue
            parsed = feedparser.parse(result.data)
            for entry in parsed.entries[:50]:
                published = _parse_entry_time(entry)
                if published is None:
                    continue
                items.append({
                    "title": entry.get("title") or "",
                    "url": entry.get("link") or "",
                    "summary": entry.get("summary") or entry.get("description") or "",
                    "published_at": published,
                    "source": feed.get("name"),
                    "institution": feed.get("institution"),
                })
        events = regulatory_feed_items_to_events(items)
        if not events:
            return FetchResult.failure(
                FetchStatus.NO_DATA,
                self.name,
                "; ".join(failures) if failures else "No crypto regulatory items in official feeds",
            )
        return FetchResult.success_events(events, self.name, raw={"failures": failures})


class CftcCalendarProvider(BaseProvider):
    name = "cftc_calendar"
    source = "CFTC"
    category = ProviderCategory.REGULATION
    capabilities = ("events.regulation.cftc",)
    source_url = "https://www.cftc.gov/PressRoom/Events"
    base_confidence = 100.0

    async def fetch(self, request: FetchRequest) -> FetchResult:
        result = await get_http().get_text(
            self.source_url, provider=self.name, cache_ttl=10800, rate_limit_per_min=4, retries=0
        )
        if not result.ok:
            return FetchResult.failure(result.status, self.name, result.message)
        return FetchResult.success_events(parse_cftc_calendar(result.data), self.name)


class HouseCalendarProvider(BaseProvider):
    name = "house_financial_services_calendar"
    source = "U.S. House Financial Services Committee"
    category = ProviderCategory.REGULATION
    capabilities = ("events.regulation.house",)
    source_url = "https://financialservices.house.gov/calendar/"
    base_confidence = 100.0

    async def fetch(self, request: FetchRequest) -> FetchResult:
        result = await get_http().get_text(
            self.source_url, provider=self.name, cache_ttl=10800, rate_limit_per_min=4, retries=0
        )
        if not result.ok:
            return FetchResult.failure(result.status, self.name, result.message)
        return FetchResult.success_events(parse_house_calendar(result.data), self.name)


class SenateCalendarProvider(BaseProvider):
    """Official Senate Banking/Agriculture pages; never bypass source blocks."""

    name = "senate_committees_calendar"
    source = "U.S. Senate committees"
    category = ProviderCategory.REGULATION
    capabilities = ("events.regulation.senate",)
    source_url = "https://www.banking.senate.gov/hearings"
    base_confidence = 100.0

    async def fetch(self, request: FetchRequest) -> FetchResult:
        # These official pages currently reject some automated clients. Keep
        # each failure explicit rather than substituting a secondary calendar.
        failures: list[str] = []
        for url in (
            "https://www.banking.senate.gov/hearings",
            "https://www.agriculture.senate.gov/hearings",
        ):
            result = await get_http().get_text(
                url, provider=self.name, cache_ttl=10800, rate_limit_per_min=3, retries=0
            )
            if not result.ok:
                failures.append(f"{url}: {result.status.value}")
                continue
            # Committee templates vary and expose incomplete time metadata.
            # Until a source-backed parser is available, return no event rather
            # than guessing dates from prose.
            failures.append(f"{url}: no verified structured event parser")
        return FetchResult.failure(FetchStatus.NO_DATA, self.name, "; ".join(failures))

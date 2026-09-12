"""Official US macro calendars normalised as :class:`FutureEvent` objects.

No event date lives in this module.  Dates are parsed from primary-source
responses on every refresh (subject to the ordinary HTTP cache).  The only
clock constants below are official publication conventions such as the FOMC's
2 p.m. Eastern statement time.
"""

from __future__ import annotations

import re
from calendar import month_name
from datetime import UTC, datetime, time, timedelta
from typing import Any
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

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
)
from ..base import BaseProvider, FetchRequest, FetchResult
from ..http import get_http

EASTERN = ZoneInfo("America/New_York")
ALL_ASSETS = [Asset.BTC, Asset.ETH, Asset.SOL]


def _now(value: datetime | None = None) -> datetime:
    value = value or datetime.now(UTC)
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _event(
    *,
    event_type: str,
    category: FutureEventCategory,
    title: str,
    source: str,
    source_url: str,
    scheduled_at: datetime,
    detected_at: datetime,
    importance: EventImportance,
    movement: ExpectedMovement,
    metadata: dict[str, Any],
    expected_end_at: datetime | None = None,
) -> FutureEvent:
    event = FutureEvent(
        event_type=event_type,
        category=category,
        schedule_type=EventScheduleType.SCHEDULED,
        title=title,
        source=source,
        source_tier=FutureEventSourceTier.A,
        source_url=source_url,
        detected_at=detected_at,
        scheduled_at=scheduled_at,
        timezone="America/New_York",
        expected_end_at=expected_end_at,
        affected_assets=ALL_ASSETS,
        affected_markets=["crypto", "rates", "risk_assets"],
        importance=importance,
        directional_effect=DirectionalBias.NEUTRAL,
        magnitude_effect=movement,
        confidence=1.0,
        last_updated=detected_at,
        metadata=metadata,
    )
    return EventDeduplicator().canonicalise(event)


def _month_number(label: str, *, last: bool = False) -> int | None:
    names = [part.strip() for part in label.split("/") if part.strip()]
    if not names:
        return None
    wanted = names[-1] if last else names[0]
    for number, name in enumerate(month_name):
        if name and name.lower().startswith(wanted.lower()[:3]):
            return number
    return None


def parse_fomc_calendar(html: str, *, fetched_at: datetime | None = None) -> list[FutureEvent]:
    """Parse current and future FOMC panels from the Fed's own page."""
    detected = _now(fetched_at)
    soup = BeautifulSoup(html, "lxml")
    events: list[FutureEvent] = []

    for panel in soup.select("div.panel"):
        heading = panel.select_one(".panel-heading")
        match = re.search(r"\b(20\d{2})\s+FOMC Meetings\b", heading.get_text(" ", strip=True) if heading else "")
        if not match:
            continue
        year = int(match.group(1))
        for row in panel.select(".fomc-meeting"):
            month_node = row.select_one(".fomc-meeting__month")
            date_node = row.select_one(".fomc-meeting__date")
            if not month_node or not date_node:
                continue
            month_label = month_node.get_text(" ", strip=True)
            raw_days = date_node.get_text(" ", strip=True)
            days = [int(value) for value in re.findall(r"\d+", raw_days)]
            if not days:
                continue
            end_month = _month_number(month_label, last=len(days) > 1 and days[-1] < days[0])
            start_month = _month_number(month_label)
            if end_month is None or start_month is None:
                continue
            end_year = year + (1 if end_month < start_month else 0)
            try:
                decision_local = datetime.combine(
                    datetime(end_year, end_month, days[-1]).date(), time(14, 0), tzinfo=EASTERN
                )
                start_local = datetime.combine(
                    datetime(year, start_month, days[0]).date(), time(0, 0), tzinfo=EASTERN
                )
            except ValueError:
                continue
            has_sep = "*" in raw_days
            events.append(
                _event(
                    event_type="FOMC_DECISION",
                    category=FutureEventCategory.MONETARY_POLICY,
                    title=f"FOMC monetary policy decision ({month_label} {year})",
                    source="Federal Reserve",
                    source_url="https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
                    scheduled_at=decision_local.astimezone(UTC),
                    detected_at=detected,
                    importance=EventImportance.CRITICAL,
                    movement=ExpectedMovement.HIGH,
                    expected_end_at=(decision_local + timedelta(hours=1)).astimezone(UTC),
                    metadata={
                        "entities": ["Federal Reserve", "FOMC"],
                        "subject": "monetary policy decision",
                        "location": "United States",
                        "meeting_starts_at": start_local.astimezone(UTC).isoformat(),
                        "includes_sep": has_sep,
                        "time_basis": "FOMC statements are released at 2:00 p.m. Eastern",
                    },
                )
            )
    return sorted(events, key=lambda item: item.scheduled_at or detected)


def _unfold_ics(text: str) -> list[str]:
    unfolded: list[str] = []
    for line in text.replace("\r\n", "\n").split("\n"):
        if line.startswith((" ", "\t")) and unfolded:
            unfolded[-1] += line[1:]
        else:
            unfolded.append(line)
    return unfolded


def _ics_datetime(key: str, raw: str) -> datetime | None:
    timezone = "America/New_York"
    tz_match = re.search(r"TZID=([^;:]+)", key)
    if tz_match:
        timezone = tz_match.group(1)
    try:
        if raw.endswith("Z"):
            return datetime.strptime(raw, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
        if "T" in raw:
            local = datetime.strptime(raw, "%Y%m%dT%H%M%S")
        else:
            local = datetime.strptime(raw, "%Y%m%d")
        return local.replace(tzinfo=ZoneInfo(timezone)).astimezone(UTC)
    except (ValueError, KeyError):
        return None


_BLS_TYPES: tuple[tuple[str, str, EventImportance, ExpectedMovement], ...] = (
    ("consumer price index", "CPI", EventImportance.CRITICAL, ExpectedMovement.HIGH),
    ("producer price index", "PPI", EventImportance.HIGH, ExpectedMovement.HIGH),
    ("employment situation", "NFP_EMPLOYMENT", EventImportance.CRITICAL, ExpectedMovement.HIGH),
    ("employment cost index", "ECI", EventImportance.HIGH, ExpectedMovement.NORMAL),
    ("real earnings", "REAL_EARNINGS", EventImportance.MEDIUM, ExpectedMovement.NORMAL),
)


def parse_bls_ics(text: str, *, fetched_at: datetime | None = None) -> list[FutureEvent]:
    """Parse the official BLS online calendar without an optional ICS dependency."""
    detected = _now(fetched_at)
    records: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for line in _unfold_ics(text):
        if line == "BEGIN:VEVENT":
            current = {}
        elif line == "END:VEVENT" and current is not None:
            records.append(current)
            current = None
        elif current is not None and ":" in line:
            key, value = line.split(":", 1)
            current[key] = value.replace("\\,", ",").replace("\\n", " ")

    events: list[FutureEvent] = []
    source_url = "https://www.bls.gov/schedule/news_release/bls.ics"
    for record in records:
        summary = next((value for key, value in record.items() if key.startswith("SUMMARY")), "").strip()
        classified = next((item for item in _BLS_TYPES if item[0] in summary.lower()), None)
        start_item = next(((key, value) for key, value in record.items() if key.startswith("DTSTART")), None)
        if not classified or not start_item:
            continue
        scheduled = _ics_datetime(*start_item)
        if scheduled is None:
            continue
        _, event_type, importance, movement = classified
        uid = next((value for key, value in record.items() if key.startswith("UID")), "")
        events.append(
            _event(
                event_type=event_type,
                category=FutureEventCategory.MACRO,
                title=summary,
                source="U.S. Bureau of Labor Statistics",
                source_url=source_url,
                scheduled_at=scheduled,
                detected_at=detected,
                importance=importance,
                movement=movement,
                metadata={
                    "entities": ["BLS"],
                    "subject": event_type,
                    "location": "United States",
                    "source_uid": uid or None,
                },
            )
        )
    return sorted(events, key=lambda item: item.scheduled_at or detected)


_BEA_TYPES: tuple[tuple[str, str, EventImportance], ...] = (
    ("personal income and outlays", "PCE_PERSONAL_INCOME", EventImportance.CRITICAL),
    ("gross domestic product", "GDP", EventImportance.HIGH),
    ("gdp (", "GDP", EventImportance.HIGH),
)


def parse_bea_calendar(html: str, *, fetched_at: datetime | None = None) -> list[FutureEvent]:
    detected = _now(fetched_at)
    soup = BeautifulSoup(html, "lxml")
    page_text = soup.get_text(" ", strip=True)
    year_match = re.search(r"\bYear\s+(20\d{2})\b", page_text)
    if not year_match:
        return []
    year = int(year_match.group(1))
    base_url = "https://www.bea.gov/news/schedule/full"
    events: list[FutureEvent] = []
    for row in soup.select("tr"):
        date_node = row.select_one(".release-date")
        time_node = row.select_one("small")
        title_node = row.select_one(".release-title")
        if not date_node or not time_node or not title_node:
            continue
        title = title_node.get_text(" ", strip=True)
        classified = next((item for item in _BEA_TYPES if item[0] in title.lower()), None)
        if not classified:
            continue
        try:
            naive = datetime.strptime(
                f"{date_node.get_text(' ', strip=True)} {year} {time_node.get_text(' ', strip=True)}",
                "%B %d %Y %I:%M %p",
            )
        except ValueError:
            continue
        scheduled = naive.replace(tzinfo=EASTERN).astimezone(UTC)
        _, event_type, importance = classified
        link = row.find("a", href=True)
        source_url = urljoin(base_url, link["href"]) if link else base_url
        events.append(
            _event(
                event_type=event_type,
                category=FutureEventCategory.MACRO,
                title=title,
                source="U.S. Bureau of Economic Analysis",
                source_url=source_url,
                scheduled_at=scheduled,
                detected_at=detected,
                importance=importance,
                movement=ExpectedMovement.HIGH if importance is EventImportance.CRITICAL else ExpectedMovement.NORMAL,
                metadata={
                    "entities": ["BEA"],
                    "subject": event_type,
                    "location": "United States",
                    "calendar_url": base_url,
                },
            )
        )
    return sorted(events, key=lambda item: item.scheduled_at or detected)


def _parse_iso_date(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _treasury_close(row: dict[str, Any], auction_date: datetime) -> datetime:
    raw = str(row.get("closingTimeCompetitive") or "").strip()
    try:
        clock = datetime.strptime(raw, "%I:%M %p").time()
    except ValueError:
        # An official auction date is still useful when the endpoint omits the
        # tender deadline. Midnight Eastern is explicit, not presented as an
        # exact release time; metadata records that limitation.
        clock = time(0, 0)
    return datetime.combine(auction_date.date(), clock, tzinfo=EASTERN).astimezone(UTC)


def parse_treasury_auctions(
    rows: Any, *, fetched_at: datetime | None = None, lookahead_days: int = 120
) -> list[FutureEvent]:
    detected = _now(fetched_at)
    if not isinstance(rows, list):
        return []
    events: list[FutureEvent] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        auction_date = _parse_iso_date(row.get("auctionDate"))
        if auction_date is None or not (
            detected - timedelta(days=1) <= auction_date <= detected + timedelta(days=lookahead_days)
        ):
            continue
        scheduled = _treasury_close(row, auction_date)
        security_type = str(row.get("securityType") or "Treasury security").strip()
        term = str(row.get("securityTerm") or "").strip()
        cusip = str(row.get("cusip") or "").strip()
        high_impact = security_type.lower() in {"note", "bond", "tips", "frn"}
        title = " ".join(value for value in (term, security_type, "Treasury auction") if value)
        events.append(
            _event(
                event_type="TREASURY_AUCTION",
                category=FutureEventCategory.MACRO,
                title=title,
                source="U.S. Treasury / TreasuryDirect",
                source_url="https://www.treasurydirect.gov/TA_WS/securities/announced?format=json",
                scheduled_at=scheduled,
                detected_at=detected,
                importance=EventImportance.HIGH if high_impact else EventImportance.MEDIUM,
                movement=ExpectedMovement.NORMAL,
                metadata={
                    "entities": ["U.S. Treasury"],
                    "subject": "Treasury auction",
                    "location": "United States",
                    "cusip": cusip or None,
                    "numbers": [value for value in (term, cusip) if value],
                    "announcement_date": row.get("announcementDate"),
                    "issue_date": row.get("issueDate"),
                    "offering_amount": row.get("offeringAmount"),
                    "competitive_close_provided": bool(row.get("closingTimeCompetitive")),
                },
            )
        )
    return EventDeduplicator().deduplicate(events)


class FederalReserveCalendarProvider(BaseProvider):
    name = "fed_calendar"
    source = "Federal Reserve"
    category = ProviderCategory.MACRO
    capabilities = ("events.macro.fed",)
    source_url = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
    base_confidence = 100.0

    async def fetch(self, request: FetchRequest) -> FetchResult:
        result = await get_http().get_text(
            self.source_url, provider=self.name, cache_ttl=21600, rate_limit_per_min=6
        )
        if not result.ok:
            return FetchResult.failure(result.status, self.name, result.message)
        try:
            events = parse_fomc_calendar(result.data)
        except Exception as exc:
            return FetchResult.failure(FetchStatus.PARSE_ERROR, self.name, str(exc))
        return FetchResult.success_events(events, self.name)


class BlsCalendarProvider(BaseProvider):
    name = "bls_calendar"
    source = "U.S. Bureau of Labor Statistics"
    category = ProviderCategory.MACRO
    capabilities = ("events.macro.bls",)
    source_url = "https://www.bls.gov/schedule/news_release/bls.ics"
    base_confidence = 100.0

    async def fetch(self, request: FetchRequest) -> FetchResult:
        result = await get_http().get_text(
            self.source_url, provider=self.name, cache_ttl=21600, rate_limit_per_min=4, retries=0
        )
        if not result.ok:
            return FetchResult.failure(result.status, self.name, result.message)
        try:
            events = parse_bls_ics(result.data)
        except Exception as exc:
            return FetchResult.failure(FetchStatus.PARSE_ERROR, self.name, str(exc))
        return FetchResult.success_events(events, self.name)


class BeaCalendarProvider(BaseProvider):
    name = "bea_calendar"
    source = "U.S. Bureau of Economic Analysis"
    category = ProviderCategory.MACRO
    capabilities = ("events.macro.bea",)
    source_url = "https://www.bea.gov/news/schedule/full"
    base_confidence = 100.0

    async def fetch(self, request: FetchRequest) -> FetchResult:
        result = await get_http().get_text(
            self.source_url, provider=self.name, cache_ttl=21600, rate_limit_per_min=6
        )
        if not result.ok:
            return FetchResult.failure(result.status, self.name, result.message)
        try:
            events = parse_bea_calendar(result.data)
        except Exception as exc:
            return FetchResult.failure(FetchStatus.PARSE_ERROR, self.name, str(exc))
        return FetchResult.success_events(events, self.name)


class TreasuryAuctionProvider(BaseProvider):
    name = "treasury_auctions"
    source = "U.S. Treasury / TreasuryDirect"
    category = ProviderCategory.MACRO
    capabilities = ("events.macro.treasury",)
    source_url = "https://www.treasurydirect.gov/TA_WS/securities/announced?format=json"
    base_confidence = 100.0

    async def fetch(self, request: FetchRequest) -> FetchResult:
        result = await get_http().get_json(
            self.source_url, provider=self.name, cache_ttl=21600, rate_limit_per_min=6
        )
        if not result.ok:
            return FetchResult.failure(result.status, self.name, result.message)
        try:
            events = parse_treasury_auctions(result.data)
        except Exception as exc:
            return FetchResult.failure(FetchStatus.PARSE_ERROR, self.name, str(exc))
        return FetchResult.success_events(events, self.name)

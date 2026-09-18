"""Policy calendars of the central banks outside the Fed.

The Fed is not the only source of global liquidity, and for crypto the Bank of
Japan is arguably the one that moves things hardest: the yen funds a large
carry trade, and when its cost changes, leveraged positions everywhere are
repriced. The ECB and the BoE matter for the same reason at a smaller scale.

Two distinctions this module refuses to blur, because getting them wrong
produces confident nonsense:

* the ECB holds *non*-monetary policy meetings on the same calendar. They set
  no rates and are not decisions;
* an ECB policy meeting spans two days and the decision lands on the second.
  Anchoring on day one puts the event a day early, every time.

As everywhere else in this codebase, no meeting date is written here: they are
parsed from each institution's own published calendar on every refresh.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from ...core.enums import Asset, FetchStatus, ProviderCategory
from ...future_events.models import (
    EventImportance,
    EventScheduleType,
    ExpectedMovement,
    FutureEvent,
    FutureEventCategory,
    FutureEventSourceTier,
)
from ..base import BaseProvider, FetchRequest, FetchResult
from ..http import get_http

FRANKFURT = ZoneInfo("Europe/Berlin")
TOKYO = ZoneInfo("Asia/Tokyo")
ALL_ASSETS = [Asset.BTC, Asset.ETH, Asset.SOL]

#: The ECB has announced its policy decisions at 14:15 CET since 2022, with the
#: press conference at 14:45. This is a published convention, not a guess.
ECB_DECISION_TIME = time(14, 15)

#: The BoJ publishes no fixed announcement time - the statement lands when the
#: meeting ends, usually around midday JST. Events built here are therefore
#: flagged ``time_is_approximate`` so nothing downstream treats the hour as
#: official.
BOJ_APPROXIMATE_TIME = time(12, 0)


def _now(value: datetime | None = None) -> datetime:
    value = value or datetime.now(UTC)
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _event(
    *,
    event_type: str,
    title: str,
    source: str,
    source_url: str,
    scheduled_at: datetime,
    detected_at: datetime,
    importance: EventImportance,
    metadata: dict[str, Any],
) -> FutureEvent:
    event = FutureEvent(
        event_type=event_type,
        category=FutureEventCategory.MONETARY_POLICY,
        schedule_type=EventScheduleType.SCHEDULED,
        title=title,
        source=source,
        source_url=source_url,
        source_tier=FutureEventSourceTier.A,
        scheduled_at=scheduled_at,
        detected_at=detected_at,
        importance=importance,
        # A policy decision reliably moves things - that is amplitude, and it
        # is all a calendar entry can tell us. Which way it moves them is not
        # knowable until the decision is compared with what was priced in, so
        # the bias is deliberately left at its neutral default here.
        magnitude_effect=ExpectedMovement.HIGH,
        affected_assets=list(ALL_ASSETS),
        confidence=1.0,
        # ``directional_effect`` defaults to NEUTRAL on the shared model, which
        # would read as "no effect expected" - the opposite of the truth here.
        # The flag below says what is actually the case, and the radar layer
        # carries it as a genuine UNKNOWN.
        metadata={"direction_known": False, **metadata},
    )
    return event


# ---------------------------------------------------------------------------
# European Central Bank
# ---------------------------------------------------------------------------

_ECB_DATE = re.compile(r"(\d{2})/(\d{2})/(\d{4})")


def parse_ecb_calendar(html: str, *, fetched_at: datetime | None = None) -> list[FutureEvent]:
    """Read the Governing Council calendar, keeping only rate-setting days.

    The page is a definition list: each ``<dt>`` carries a ``DD/MM/YYYY`` date
    and the following ``<dd>`` describes what happens that day.
    """

    detected_at = _now(fetched_at)
    soup = BeautifulSoup(html, "html.parser")
    events: list[FutureEvent] = []
    seen: set[str] = set()

    for term in soup.find_all("dt"):
        match = _ECB_DATE.search(term.get_text(" ", strip=True))
        if match is None:
            continue
        description_tag = term.find_next_sibling("dd")
        if description_tag is None:
            continue
        description = description_tag.get_text(" ", strip=True)
        lowered = description.lower()

        if "monetary policy meeting" not in lowered:
            continue
        if "non-monetary policy" in lowered:
            # Governance and supervision business: no rate is set here.
            continue
        if "(day 1)" in lowered:
            # The decision and the press conference are on day 2.
            continue

        day, month, year = (int(part) for part in match.groups())
        scheduled_at = datetime.combine(
            datetime(year, month, day).date(), ECB_DECISION_TIME, tzinfo=FRANKFURT
        ).astimezone(UTC)

        key = scheduled_at.date().isoformat()
        if key in seen:
            continue
        seen.add(key)

        events.append(
            _event(
                event_type="ECB_RATE_DECISION",
                title="Décision de taux de la BCE",
                source="European Central Bank",
                source_url=ECB_CALENDAR_URL,
                scheduled_at=scheduled_at,
                detected_at=detected_at,
                importance=EventImportance.HIGH,
                metadata={
                    "institution": "ECB",
                    "region": "EUR",
                    "description": description,
                    "press_conference": "press conference" in lowered,
                    "transmission": (
                        "Les taux de la BCE agissent sur la liquidité en euro et "
                        "sur l'euro face au dollar; l'effet sur les actifs "
                        "risqués dépend de l'écart avec ce qui était anticipé."
                    ),
                },
            )
        )

    return events


# ---------------------------------------------------------------------------
# Bank of Japan
# ---------------------------------------------------------------------------

_BOJ_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_BOJ_YEAR = re.compile(r"(20\d{2})")
#: "Jan. 22 (Thurs.), 23 (Fri.)" - a month name then one or more day numbers.
_BOJ_MONTH_TOKEN = re.compile(r"([A-Za-z]{3,9})\.?\s*(\d{1,2})")
_BOJ_EXTRA_DAY = re.compile(r",\s*(\d{1,2})\s*\(")


def parse_boj_calendar(html: str, *, fetched_at: datetime | None = None) -> list[FutureEvent]:
    """Read the Monetary Policy Meeting schedule.

    A BoJ meeting runs over two days and the statement is released when it
    ends, so the event is anchored on the last day listed in the cell.
    """

    detected_at = _now(fetched_at)
    soup = BeautifulSoup(html, "html.parser")
    events: list[FutureEvent] = []
    seen: set[str] = set()

    for table in soup.find_all("table"):
        caption = table.find("caption")
        year_match = _BOJ_YEAR.search(caption.get_text(" ", strip=True)) if caption else None
        if year_match is None:
            continue
        year = int(year_match.group(1))

        for row in table.find_all("tr"):
            cells = row.find_all(["th", "td"])
            if not cells:
                continue
            raw = cells[0].get_text(" ", strip=True)
            token = _BOJ_MONTH_TOKEN.search(raw)
            if token is None:
                continue
            month = _BOJ_MONTHS.get(token.group(1)[:3].lower())
            if month is None:
                continue

            # The meeting ends on the last day named in the cell.
            day = int(token.group(2))
            extra = _BOJ_EXTRA_DAY.findall(raw)
            if extra:
                day = int(extra[-1])

            try:
                scheduled_at = datetime.combine(
                    datetime(year, month, day).date(), BOJ_APPROXIMATE_TIME, tzinfo=TOKYO
                ).astimezone(UTC)
            except ValueError:
                continue

            key = scheduled_at.date().isoformat()
            if key in seen:
                continue
            seen.add(key)

            events.append(
                _event(
                    event_type="BOJ_POLICY_DECISION",
                    title="Décision de politique monétaire de la BoJ",
                    source="Bank of Japan",
                    source_url=BOJ_CALENDAR_URL,
                    scheduled_at=scheduled_at,
                    detected_at=detected_at,
                    importance=EventImportance.HIGH,
                    metadata={
                        "institution": "BOJ",
                        "region": "JPY",
                        "raw_schedule": raw,
                        "time_is_approximate": True,
                        "transmission": (
                            "Le yen finance une large part du portage mondial: "
                            "un changement du coût du yen peut forcer des "
                            "débouclages qui touchent tous les actifs risqués, "
                            "crypto comprise."
                        ),
                    },
                )
            )

    return events


ECB_CALENDAR_URL = "https://www.ecb.europa.eu/press/calendars/mgcgc/html/index.en.html"
BOJ_CALENDAR_URL = "https://www.boj.or.jp/en/mopo/mpmsche_minu/index.htm"


class EcbCalendarProvider(BaseProvider):
    name = "ecb_calendar"
    source = "European Central Bank"
    category = ProviderCategory.MACRO
    capabilities = ("events.macro.ecb",)
    source_url = ECB_CALENDAR_URL
    base_confidence = 100.0

    async def fetch(self, request: FetchRequest) -> FetchResult:
        result = await get_http().get_text(
            self.source_url, provider=self.name, cache_ttl=21600, rate_limit_per_min=6
        )
        if not result.ok:
            return FetchResult.failure(result.status, self.name, result.message)
        try:
            events = parse_ecb_calendar(result.data)
        except Exception as exc:
            return FetchResult.failure(FetchStatus.PARSE_ERROR, self.name, str(exc))
        return FetchResult.success_events(events, self.name)


class BojCalendarProvider(BaseProvider):
    name = "boj_calendar"
    source = "Bank of Japan"
    category = ProviderCategory.MACRO
    capabilities = ("events.macro.boj",)
    source_url = BOJ_CALENDAR_URL
    base_confidence = 100.0

    async def fetch(self, request: FetchRequest) -> FetchResult:
        result = await get_http().get_text(
            self.source_url, provider=self.name, cache_ttl=21600, rate_limit_per_min=6
        )
        if not result.ok:
            return FetchResult.failure(result.status, self.name, result.message)
        try:
            events = parse_boj_calendar(result.data)
        except Exception as exc:
            return FetchResult.failure(FetchStatus.PARSE_ERROR, self.name, str(exc))
        return FetchResult.success_events(events, self.name)

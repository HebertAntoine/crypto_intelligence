"""Licensed CME FedWatch API adapter.

CME advertises an official JSON REST API.  It is a commercial feed, so the
application does not scrape the public visualisation.  Both an entitled API
URL and credential must be configured; otherwise this provider is explicitly
UNAVAILABLE.
"""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

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
    MarketProbability,
)
from ...settings import get_settings
from ..base import BaseProvider, FetchRequest, FetchResult, ProviderStatus
from ..http import get_http

EASTERN = ZoneInfo("America/New_York")
SOURCE_URL = "https://www.cmegroup.com/market-data/market-data-api/fedwatch-api.html"


def _datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
            try:
                parsed = datetime.strptime(raw, fmt)
                break
            except ValueError:
                continue
        else:
            return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _meeting_date(value: Any) -> datetime | None:
    if isinstance(value, str):
        raw_date = value.strip()
        for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
            try:
                local_date = datetime.strptime(raw_date, fmt).date()
                return datetime.combine(local_date, time(14, 0), tzinfo=EASTERN).astimezone(UTC)
            except ValueError:
                continue
    parsed = _datetime(value)
    if parsed is None:
        return None
    local_date = parsed.astimezone(EASTERN).date()
    return datetime.combine(local_date, time(14, 0), tzinfo=EASTERN).astimezone(UTC)


def _probability_rows(raw: Any) -> list[tuple[str, float]]:
    rows: list[tuple[str, float]] = []
    if isinstance(raw, dict):
        iterable = [{"outcome": key, "probability": value} for key, value in raw.items()]
    elif isinstance(raw, list):
        iterable = raw
    else:
        return []
    for item in iterable:
        if not isinstance(item, dict):
            continue
        outcome = str(
            item.get("outcome")
            or item.get("targetRange")
            or item.get("target_rate")
            or item.get("label")
            or ""
        ).strip()
        try:
            probability = float(item.get("probability", item.get("value")))
        except (TypeError, ValueError):
            continue
        if probability > 1.0:
            probability /= 100.0
        if outcome and 0.0 <= probability <= 1.0:
            rows.append((outcome, probability))
    return rows


def parse_fedwatch_payload(payload: Any) -> list[FutureEvent]:
    if not isinstance(payload, dict):
        return []
    data = payload.get("data", payload)
    meetings = data.get("meetings") if isinstance(data, dict) else None
    if not isinstance(meetings, list):
        return []
    top_timestamp = next(
        (payload.get(key) for key in ("observedAt", "asOf", "timestamp") if payload.get(key)),
        None,
    )
    events: list[FutureEvent] = []
    for meeting in meetings:
        if not isinstance(meeting, dict):
            continue
        scheduled = _meeting_date(
            meeting.get("meetingDate") or meeting.get("meeting_date") or meeting.get("date")
        )
        observed = _datetime(
            meeting.get("observedAt")
            or meeting.get("asOf")
            or meeting.get("timestamp")
            or top_timestamp
        )
        rows = _probability_rows(
            meeting.get("probabilities")
            or meeting.get("outcomes")
            or meeting.get("distribution")
        )
        total = sum(probability for _outcome, probability in rows)
        # Do not repair a partial API response into an apparently complete
        # distribution. Small floating-point/rounding drift is acceptable.
        if scheduled is None or observed is None or not rows or not 0.98 <= total <= 1.02:
            continue
        probabilities = [
            MarketProbability(
                outcome=outcome,
                probability=probability,
                source="CME FedWatch",
                observed_at=observed,
                source_url=SOURCE_URL,
            )
            for outcome, probability in rows
        ]
        expected = max(probabilities, key=lambda item: item.probability)
        event = FutureEvent(
            event_type="FOMC_DECISION",
            category=FutureEventCategory.MONETARY_POLICY,
            schedule_type=EventScheduleType.SCHEDULED,
            title=f"CME FedWatch distribution for FOMC {scheduled.date().isoformat()}",
            source="CME FedWatch",
            source_tier=FutureEventSourceTier.B,
            source_url=SOURCE_URL,
            source_published_at=observed,
            detected_at=observed,
            scheduled_at=scheduled,
            timezone="America/New_York",
            expected_end_at=scheduled + timedelta(hours=1),
            affected_assets=[Asset.BTC, Asset.ETH, Asset.SOL],
            affected_markets=["crypto", "rates", "risk_assets"],
            importance=EventImportance.CRITICAL,
            consensus={
                "expected_outcome": expected.outcome,
                "degree_priced": expected.probability,
                "current_target_range": meeting.get("currentTargetRange") or meeting.get("current_target_range"),
            },
            outcome_space=[item.outcome for item in probabilities],
            market_probabilities=probabilities,
            probability_timestamp=observed,
            directional_effect=DirectionalBias.NEUTRAL,
            magnitude_effect=ExpectedMovement.HIGH,
            confidence=1.0,
            last_updated=observed,
            metadata={
                "entities": ["Federal Reserve", "FOMC"],
                "subject": "monetary policy decision",
                "location": "United States",
                "market_data_methodology": "CME FedWatch / 30-Day Fed Funds futures",
            },
        )
        events.append(EventDeduplicator().canonicalise(event))
    return events


class CmeFedWatchProvider(BaseProvider):
    name = "cme_fedwatch"
    source = "CME FedWatch"
    category = ProviderCategory.MACRO
    capabilities = ("events.expectations.fed",)
    requires_key = "CME_FEDWATCH_API_KEY"
    source_url = SOURCE_URL
    base_confidence = 100.0

    async def available(self) -> ProviderStatus:
        settings = get_settings()
        if not settings.cme_fedwatch_api_key.strip() or not settings.cme_fedwatch_api_url.strip():
            return ProviderStatus(
                name=self.name,
                available=False,
                reason="UNAVAILABLE - licensed CME_FEDWATCH_API_URL/API_KEY not configured",
                requires_key=self.requires_key,
                configured=False,
            )
        return ProviderStatus(name=self.name, available=True)

    async def fetch(self, request: FetchRequest) -> FetchResult:
        settings = get_settings()
        if not (await self.available()).available:
            return FetchResult.failure(
                FetchStatus.NOT_CONFIGURED,
                self.name,
                "UNAVAILABLE - licensed CME FedWatch API access is not configured",
            )
        result = await get_http().get_json(
            settings.cme_fedwatch_api_url,
            provider=self.name,
            headers={
                "Authorization": f"Bearer {settings.cme_fedwatch_api_key}",
                "X-API-Key": settings.cme_fedwatch_api_key,
            },
            cache_ttl=60,
            rate_limit_per_min=30,
            retries=1,
        )
        if not result.ok:
            return FetchResult.failure(result.status, self.name, result.message)
        events = parse_fedwatch_payload(result.data)
        if not events:
            return FetchResult.failure(
                FetchStatus.PARSE_ERROR,
                self.name,
                "FedWatch response lacked a complete timestamped probability distribution",
            )
        return FetchResult.success_events(events, self.name)

"""Congress.gov bill actions as stage-faithful regulatory catalysts."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from ...core.enums import FetchStatus, ProviderCategory
from ...engines.regulatory_catalyst import RegulatoryCatalystEngine
from ...future_events.deduplication import EventDeduplicator
from ...future_events.models import (
    DirectionalBias,
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
from .official_regulation import _assets, _importance, _relevant


def _bill_key(bill: dict[str, Any]) -> str:
    return ":".join(
        (
            str(bill.get("congress") or ""),
            str(bill.get("type") or "").lower(),
            str(bill.get("number") or ""),
        )
    )


def _official_date(value: Any) -> datetime | None:
    """Normalize an official date while retaining DATE precision in metadata."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def congress_actions_to_events(
    bills: list[dict[str, Any]],
    actions_by_bill: dict[str, list[dict[str, Any]]],
    *,
    fetched_at: datetime | None = None,
) -> list[FutureEvent]:
    """Convert official actions without promoting a stage beyond its wording."""
    detected = fetched_at or datetime.now(UTC)
    if detected.tzinfo is None:
        detected = detected.replace(tzinfo=UTC)
    detected = detected.astimezone(UTC)
    classifier = RegulatoryCatalystEngine()
    events: list[FutureEvent] = []
    for bill in bills:
        title = str(bill.get("title") or "").strip()
        key = _bill_key(bill)
        source_url = str(bill.get("url") or "").strip()
        if (
            not title
            or not _relevant(title)
            or not source_url.startswith("https://api.congress.gov/")
        ):
            continue
        bill_label = f"{str(bill.get('type') or '').upper()} {bill.get('number') or ''}".strip()
        for action in actions_by_bill.get(key, []):
            action_text = str(action.get("text") or "").strip()
            action_date = _official_date(action.get("actionDate"))
            if not action_text or action_date is None:
                continue
            if action_date < detected - timedelta(days=30):
                continue
            stage = classifier.classify_stage(action_text)
            importance = _importance(stage)
            event = FutureEvent(
                event_type=f"CONGRESS_{stage.value}",
                category=FutureEventCategory.REGULATION,
                schedule_type=EventScheduleType.UNSCHEDULED,
                title=f"{bill_label} — {classifier.stage_label(stage)}: {title}",
                source="Congress.gov API",
                source_tier=FutureEventSourceTier.A,
                source_url=source_url,
                source_reference=key,
                source_published_at=action_date,
                detected_at=detected,
                status=FutureEventStatus.RELEASED,
                affected_assets=_assets(title),
                affected_markets=["crypto", "regulation"],
                importance=importance,
                directional_effect=DirectionalBias.NEUTRAL,
                magnitude_effect=(
                    ExpectedMovement.HIGH
                    if importance.value in {"CRITICAL", "HIGH"}
                    else ExpectedMovement.NORMAL
                ),
                confidence=1.0,
                causal_chain=[
                    f"Étape officielle : {classifier.stage_label(stage)}",
                    "Les étapes législatives suivantes ne sont pas présumées",
                    "Effet de marché à confirmer selon le texte et les anticipations",
                ],
                last_updated=action_date,
                expires_at=action_date + timedelta(days=14),
                metadata={
                    "entities": ["U.S. Congress", bill_label],
                    "subject": f"{key}:{stage.value}",
                    "location": "United States",
                    "bill_title": title,
                    "bill_id": key,
                    "action_text": action_text,
                    "action_code": action.get("actionCode"),
                    "action_time_precision": "DATE",
                    "regulatory_stage": stage.value,
                    "stage_is_completed_only": True,
                },
            )
            events.append(EventDeduplicator().canonicalise(event))
    return EventDeduplicator().deduplicate(events)


class CongressBillActionProvider(BaseProvider):
    name = "congress_bill_actions"
    source = "Congress.gov API"
    category = ProviderCategory.REGULATION
    capabilities = ("events.regulation.congress",)
    requires_key = "CONGRESS_API_KEY"
    source_url = "https://api.congress.gov/v3"
    base_confidence = 100.0

    async def fetch(self, request: FetchRequest) -> FetchResult:
        api_key = get_settings().congress_api_key.strip()
        if not api_key:
            return FetchResult.failure(
                FetchStatus.NOT_CONFIGURED,
                self.name,
                "UNAVAILABLE - CONGRESS_API_KEY not configured",
            )
        base_url = str(self.config.get("base_url") or self.source_url).rstrip("/")
        since = datetime.now(UTC) - timedelta(days=30)
        latest = await get_http().get_json(
            f"{base_url}/bill",
            provider=self.name,
            params={
                "api_key": api_key,
                "format": "json",
                "limit": 250,
                "fromDateTime": since.strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
            cache_ttl=10800,
            rate_limit_per_min=20,
            retries=1,
        )
        if not latest.ok:
            return FetchResult.failure(latest.status, self.name, latest.message)
        raw_bills = latest.data.get("bills", []) if isinstance(latest.data, dict) else []
        bills = [item for item in raw_bills if isinstance(item, dict)]
        relevant = [bill for bill in bills if _relevant(str(bill.get("title") or ""))][:25]
        actions_by_bill: dict[str, list[dict[str, Any]]] = {}
        failures: list[str] = []
        for bill in relevant:
            key = _bill_key(bill)
            congress, bill_type, number = key.split(":", 2)
            result = await get_http().get_json(
                f"{base_url}/bill/{congress}/{bill_type}/{number}/actions",
                provider=self.name,
                params={"api_key": api_key, "format": "json", "limit": 50},
                cache_ttl=10800,
                rate_limit_per_min=20,
                retries=1,
            )
            if not result.ok:
                failures.append(f"{key}: {result.status.value}")
                continue
            rows = result.data.get("actions", []) if isinstance(result.data, dict) else []
            actions_by_bill[key] = [item for item in rows if isinstance(item, dict)]

        events = congress_actions_to_events(relevant, actions_by_bill)
        if not events:
            return FetchResult.failure(
                FetchStatus.NO_DATA,
                self.name,
                "; ".join(failures)
                if failures
                else "No recent official crypto-related bill action",
            )
        return FetchResult.success_events(events, self.name, raw={"failures": failures})

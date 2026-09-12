"""Canonical, source-backed representation of a future catalyst."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..core.enums import Asset


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def normalize_event_text(value: str) -> str:
    """Stable text normalisation used for identity, never for sentiment."""
    ascii_text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return " ".join(re.findall(r"[a-z0-9]+", ascii_text.lower())).strip()


class FutureEventStatus(StrEnum):
    SCHEDULED = "SCHEDULED"
    UPCOMING = "UPCOMING"
    ACTIVE = "ACTIVE"
    RELEASED = "RELEASED"
    SURPRISE = "SURPRISE"
    RESOLVED = "RESOLVED"
    DECAYING = "DECAYING"
    EXPIRED = "EXPIRED"


class EventScheduleType(StrEnum):
    SCHEDULED = "SCHEDULED"
    UNSCHEDULED = "UNSCHEDULED"


class FutureEventCategory(StrEnum):
    MACRO = "MACRO"
    MONETARY_POLICY = "MONETARY_POLICY"
    REGULATION = "REGULATION"
    ETF = "ETF"
    PROTOCOL = "PROTOCOL"
    GEOPOLITICAL = "GEOPOLITICAL"
    ENERGY = "ENERGY"
    INSTITUTIONAL = "INSTITUTIONAL"
    ONCHAIN = "ONCHAIN"
    SYSTEMIC_RISK = "SYSTEMIC_RISK"
    OTHER = "OTHER"


class FutureEventSourceTier(StrEnum):
    """Reliability ladder requested by the product, best source first."""

    A = "A"  # primary official source
    B = "B"  # recognised market-data source
    C = "C"  # major news agency
    D = "D"  # analytics provider
    E = "E"  # social network / influencer / discovery only

    @property
    def rank(self) -> int:
        return {"A": 0, "B": 1, "C": 2, "D": 3, "E": 4}[self.value]


class EventImportance(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

    @property
    def rank(self) -> int:
        return {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}[self.value]


class DirectionalBias(StrEnum):
    STRONGLY_BEARISH = "STRONGLY_BEARISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"
    BULLISH = "BULLISH"
    STRONGLY_BULLISH = "STRONGLY_BULLISH"


class ExpectedMovement(StrEnum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    EXTREME = "EXTREME"


class DecisionHorizon(StrEnum):
    H24 = "24h"
    D7 = "7d"
    D30 = "30d"


class EventSourceReference(BaseModel):
    """One corroborating source for a canonical event."""

    model_config = ConfigDict(frozen=True)

    source: str = Field(min_length=1)
    tier: FutureEventSourceTier
    url: str | None = None
    reference: str | None = None
    published_at: datetime | None = None
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    evidence_ids: list[str] = Field(default_factory=list)

    @field_validator("published_at", "fetched_at")
    @classmethod
    def ensure_utc(cls, value: datetime | None) -> datetime | None:
        return _utc(value)

    @model_validator(mode="after")
    def require_reference(self) -> EventSourceReference:
        if not self.url and not self.reference:
            raise ValueError("an event source requires a URL or a stable source reference")
        return self


class MarketProbability(BaseModel):
    """A market-implied outcome probability, never a system guess."""

    model_config = ConfigDict(frozen=True)

    outcome: str = Field(min_length=1)
    probability: float = Field(ge=0.0, le=1.0)
    source: str = Field(min_length=1)
    observed_at: datetime
    source_url: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)

    @field_validator("observed_at")
    @classmethod
    def ensure_utc(cls, value: datetime) -> datetime:
        return _utc(value)  # type: ignore[return-value]


class FutureEvent(BaseModel):
    """One canonical event, scheduled or discovered as it happens.

    Freshness and ``age_seconds`` are intentionally absent.  They are derived
    at read time from ``last_updated`` so a stored event can never remain
    permanently labelled LIVE.
    """

    model_config = ConfigDict(frozen=True)

    id: str = ""
    canonical_event_id: str = ""
    event_type: str = Field(min_length=1)
    category: FutureEventCategory
    schedule_type: EventScheduleType
    title: str = Field(min_length=1)
    normalized_title: str = ""

    source: str = Field(min_length=1)
    source_tier: FutureEventSourceTier
    source_url: str | None = None
    source_reference: str | None = None
    source_published_at: datetime | None = None
    detected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    scheduled_at: datetime | None = None
    timezone: str = "UTC"
    expected_end_at: datetime | None = None
    status: FutureEventStatus = FutureEventStatus.SCHEDULED

    affected_assets: list[Asset] = Field(default_factory=list)
    affected_markets: list[str] = Field(default_factory=list)
    importance: EventImportance = EventImportance.MEDIUM

    consensus: dict[str, Any] | None = None
    outcome_space: list[str] = Field(default_factory=list)
    market_probabilities: list[MarketProbability] = Field(default_factory=list)
    probability_timestamp: datetime | None = None
    expected_value: Any = None
    previous_value: Any = None
    actual_value: Any = None
    surprise: float | None = None

    directional_effect: DirectionalBias = DirectionalBias.NEUTRAL
    magnitude_effect: ExpectedMovement = ExpectedMovement.NORMAL
    time_horizon: DecisionHorizon = DecisionHorizon.D7
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    causal_chain: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)

    last_updated: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None
    event_signature: str = ""
    source_references: list[EventSourceReference] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "source_published_at",
        "detected_at",
        "scheduled_at",
        "expected_end_at",
        "probability_timestamp",
        "last_updated",
        "expires_at",
    )
    @classmethod
    def ensure_utc(cls, value: datetime | None) -> datetime | None:
        return _utc(value)

    @model_validator(mode="after")
    def validate_source_and_probability(self) -> FutureEvent:
        if not self.source_url and not self.source_reference:
            raise ValueError("a future event requires a source URL or stable reference")
        if self.schedule_type is EventScheduleType.SCHEDULED and self.scheduled_at is None:
            raise ValueError("a scheduled event requires scheduled_at")
        if self.market_probabilities and self.probability_timestamp is None:
            raise ValueError("probability_timestamp is mandatory when probabilities are present")
        if self.market_probabilities:
            total = sum(item.probability for item in self.market_probabilities)
            if not 0.98 <= total <= 1.02:
                raise ValueError("a market probability distribution must sum to one")
        if self.expected_end_at and self.scheduled_at and self.expected_end_at < self.scheduled_at:
            raise ValueError("expected_end_at cannot precede scheduled_at")
        return self

    def model_post_init(self, __context: Any) -> None:
        normalized = self.normalized_title or normalize_event_text(self.title)
        object.__setattr__(self, "normalized_title", normalized)

        signature = self.event_signature or self._fallback_signature()
        object.__setattr__(self, "event_signature", signature)
        canonical = self.canonical_event_id or (
            "fev_" + hashlib.sha256(signature.encode("utf-8")).hexdigest()[:24]
        )
        object.__setattr__(self, "canonical_event_id", canonical)
        if not self.id:
            object.__setattr__(self, "id", canonical)

        if not self.source_references:
            object.__setattr__(
                self,
                "source_references",
                [
                    EventSourceReference(
                        source=self.source,
                        tier=self.source_tier,
                        url=self.source_url,
                        reference=self.source_reference,
                        published_at=self.source_published_at,
                        fetched_at=self.last_updated,
                        evidence_ids=self.evidence_ids,
                    )
                ],
            )

    def _fallback_signature(self) -> str:
        moment = self.scheduled_at or self.detected_at
        bucket = moment.replace(minute=0, second=0, microsecond=0).isoformat()
        return "|".join(
            (
                normalize_event_text(self.event_type),
                bucket,
                self.normalized_title or normalize_event_text(self.title),
            )
        )

    def runtime_status(self, now: datetime | None = None) -> FutureEventStatus:
        reference = _utc(now) or datetime.now(UTC)
        if self.expires_at and reference >= self.expires_at:
            return FutureEventStatus.EXPIRED
        if self.status in {
            FutureEventStatus.RELEASED,
            FutureEventStatus.SURPRISE,
            FutureEventStatus.RESOLVED,
            FutureEventStatus.DECAYING,
            FutureEventStatus.EXPIRED,
        }:
            return self.status
        if self.actual_value is not None:
            return FutureEventStatus.RELEASED
        if self.schedule_type is EventScheduleType.UNSCHEDULED:
            return FutureEventStatus.ACTIVE
        if self.scheduled_at is None:
            return self.status
        if self.expected_end_at and self.scheduled_at <= reference <= self.expected_end_at:
            return FutureEventStatus.ACTIVE
        if reference >= self.scheduled_at:
            return FutureEventStatus.ACTIVE
        if (self.scheduled_at - reference).total_seconds() <= 7 * 86400:
            return FutureEventStatus.UPCOMING
        return FutureEventStatus.SCHEDULED

    def to_public_dict(self, now: datetime | None = None) -> dict[str, Any]:
        """Serialize with runtime-only freshness and lifecycle information."""
        from .freshness import event_freshness

        reference = _utc(now) or datetime.now(UTC)
        payload = self.model_dump(mode="json")
        payload["status"] = self.runtime_status(reference).value
        payload.update(event_freshness(self, reference).to_dict())
        payload["hours_until"] = (
            round((self.scheduled_at - reference).total_seconds() / 3600.0, 3)
            if self.scheduled_at
            else None
        )
        return payload

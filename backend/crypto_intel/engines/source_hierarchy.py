"""Which sources may decide, and which may only suggest what to look at.

A social account can be genuinely useful: it notices a Senate vote, an oil move
or an ETF filing before a calendar does. What it must never become is the source
of the number. The two roles are separated here by type, not by convention, so
that using a social item as a production input is a failure rather than an
oversight.

The rule the rest of the system relies on: a SOCIAL item is a *topic*, and a
topic has to be re-sourced from a primary or specialised provider before it can
influence anything.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import IntEnum, StrEnum
from typing import Any, ClassVar

from ..future_events.models import FutureEventSourceTier


class SourceTier(IntEnum):
    """Lower is more authoritative. Ordering is the point, so IntEnum."""

    PRIMARY = 1       # Federal Reserve, BLS, BEA, Treasury, SEC, CFTC, Congress
    SPECIALIZED = 2   # CME, Farside, DefiLlama, exchange APIs
    PRESS = 3         # Reuters, Bloomberg, FT, WSJ
    SOCIAL = 4        # X, YouTube, Reddit - discovery only


#: The highest tier that may feed a decision. Anything above is discovery.
MAX_PRODUCTION_TIER = SourceTier.PRESS

_EVENT_TIER_MAP = {
    FutureEventSourceTier.A: SourceTier.PRIMARY,
    FutureEventSourceTier.B: SourceTier.SPECIALIZED,
    FutureEventSourceTier.C: SourceTier.PRESS,
    FutureEventSourceTier.D: SourceTier.SPECIALIZED,
    FutureEventSourceTier.E: SourceTier.SOCIAL,
}


def tier_of(event_tier: FutureEventSourceTier | str | None) -> SourceTier:
    if isinstance(event_tier, str):
        try:
            event_tier = FutureEventSourceTier(event_tier)
        except ValueError:
            return SourceTier.SOCIAL
    return _EVENT_TIER_MAP.get(event_tier, SourceTier.SOCIAL)


def may_influence_decision(event_tier: FutureEventSourceTier | str | None) -> bool:
    """True when a source is authoritative enough to move a decision."""

    return tier_of(event_tier) <= MAX_PRODUCTION_TIER


class ProductionSourceError(ValueError):
    """Raised when a discovery-only source is used as a production input."""


def assert_production_source(event_tier: FutureEventSourceTier | str | None, *, what: str) -> None:
    if not may_influence_decision(event_tier):
        raise ProductionSourceError(
            f"{what}: une source sociale ne peut pas alimenter une décision; "
            "elle doit d'abord être confirmée par une source primaire ou spécialisée."
        )


def filter_production_events(events: list[Any]) -> tuple[list[Any], list[Any]]:
    """Split events into those that may decide and those that may only suggest."""

    usable, discovery = [], []
    for event in events:
        target = usable if may_influence_decision(getattr(event, "source_tier", None)) else discovery
        target.append(event)
    return usable, discovery


# ---------------------------------------------------------------------------
# Social discovery
# ---------------------------------------------------------------------------


class VerificationStatus(StrEnum):
    UNVERIFIED = "UNVERIFIED"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"


@dataclass(slots=True, frozen=True)
class DiscoveredTopic:
    """A theme worth checking, never a fact.

    ``claim`` deliberately holds the raw wording as seen, so that it can be
    shown as a quotation and never mistaken for a measurement. No numeric field
    exists on purpose: a figure read in a post is not a figure the system holds.
    """

    topic: str
    category: str
    claim: str
    observed_at: datetime
    handles: list[str] = field(default_factory=list)
    verification: VerificationStatus = VerificationStatus.UNVERIFIED
    verified_source: str | None = None
    verified_url: str | None = None
    status: str = "DISCOVERY_ONLY"

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "category": self.category,
            "claim": self.claim,
            "observed_at": self.observed_at.isoformat(),
            "handles": self.handles,
            "verification": self.verification.value,
            "verified_source": self.verified_source,
            "verified_url": self.verified_url,
            "status": self.status,
            "usage": (
                "DISCOVERY_ONLY: ce sujet indique quoi vérifier, il n'alimente "
                "aucune décision tant qu'une source primaire ne l'a pas confirmé."
            ),
        }

    @property
    def may_become_an_event(self) -> bool:
        return self.verification is VerificationStatus.VERIFIED


class SocialDiscoveryLayer:
    """Turn social chatter into a list of things to verify elsewhere.

    It answers one question: which categories might deserve attention that the
    system is not already watching. It never answers: what is the number.
    """

    status = "DISCOVERY_ONLY"

    #: Themes worth re-sourcing. A mention outside these is noise for our
    #: purposes, whatever its popularity.
    TOPICS: ClassVar[dict[str, tuple[str, ...]]] = {
        "MONETARY": ("fed", "fomc", "powell", "taux", "rate"),
        "MACRO": ("cpi", "inflation", "pce", "ppi", "emploi", "nfp", "pib", "gdp"),
        "REGULATION": ("sec", "cftc", "sénat", "senate", "congress", "vote", "clarity"),
        "ENERGY": ("pétrole", "oil", "brent", "wti", "opep", "opec"),
        "FLOWS": ("etf", "farside", "inflow", "outflow", "flux"),
        "CRYPTO": ("hack", "upgrade", "halving", "stablecoin", "exchange"),
    }

    def discover(
        self,
        mentions: list[dict[str, Any]],
        *,
        now: datetime | None = None,
    ) -> list[DiscoveredTopic]:
        reference = now or datetime.now(UTC)
        found: dict[str, DiscoveredTopic] = {}
        for mention in mentions:
            text = str(mention.get("text") or "").lower()
            handle = str(mention.get("handle") or "")
            for category, keywords in self.TOPICS.items():
                hit = next((word for word in keywords if word in text), None)
                if hit is None:
                    continue
                existing = found.get(category)
                handles = sorted({*(existing.handles if existing else []), handle} - {""})
                found[category] = DiscoveredTopic(
                    topic=hit,
                    category=category,
                    claim=str(mention.get("text") or "")[:200],
                    observed_at=reference,
                    handles=handles,
                )
        return list(found.values())

    def verify(
        self,
        topic: DiscoveredTopic,
        *,
        primary_source: str | None,
        primary_url: str | None = None,
    ) -> DiscoveredTopic:
        """Promote a topic only when a real source backs it."""

        if not primary_source:
            return DiscoveredTopic(
                topic=topic.topic,
                category=topic.category,
                claim=topic.claim,
                observed_at=topic.observed_at,
                handles=topic.handles,
                verification=VerificationStatus.REJECTED,
                status="DISCOVERY_ONLY",
            )
        return DiscoveredTopic(
            topic=topic.topic,
            category=topic.category,
            claim=topic.claim,
            observed_at=topic.observed_at,
            handles=topic.handles,
            verification=VerificationStatus.VERIFIED,
            verified_source=primary_source,
            verified_url=primary_url,
            status="DISCOVERY_ONLY",
        )

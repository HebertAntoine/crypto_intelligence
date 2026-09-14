"""Which events matter, to which asset, and how much.

Two ideas the rest of the system was missing. First, the same event does not hit
three assets equally: a DeFi rule reshapes what can be built on Ethereum and
Solana while barely touching Bitcoin, and an FOMC decision moves all three
through the same channel. Second, a calendar with twenty entries is not an
analysis - something has to decide which three a reader should actually see.

The relevance score exists to **rank**, not to predict. It never becomes a
probability of movement, and nothing here infers a direction: an event's
direction stays whatever the event carries, which before publication is unknown.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from ..core.enums import Asset
from ..future_events.models import EventImportance, FutureEventCategory
from .source_hierarchy import may_influence_decision, tier_of


class AssetImpact(StrEnum):
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"


_IMPACT_SCORE = {
    AssetImpact.NONE: 0.0,
    AssetImpact.LOW: 0.25,
    AssetImpact.MEDIUM: 0.5,
    AssetImpact.HIGH: 0.8,
    AssetImpact.VERY_HIGH: 1.0,
}

#: How a category transmits, per asset. Monetary policy and macro reach every
#: risk asset through the same channel, so they are uniform. Protocol and
#: on-chain events are specific by construction: they concern one network.
_CATEGORY_IMPACT: dict[FutureEventCategory, dict[Asset, AssetImpact]] = {
    FutureEventCategory.MONETARY_POLICY: {
        Asset.BTC: AssetImpact.HIGH,
        Asset.ETH: AssetImpact.HIGH,
        Asset.SOL: AssetImpact.HIGH,
    },
    FutureEventCategory.MACRO: {
        Asset.BTC: AssetImpact.MEDIUM,
        Asset.ETH: AssetImpact.MEDIUM,
        Asset.SOL: AssetImpact.MEDIUM,
    },
    FutureEventCategory.ENERGY: {
        Asset.BTC: AssetImpact.LOW,
        Asset.ETH: AssetImpact.LOW,
        Asset.SOL: AssetImpact.LOW,
    },
    # Regulation lands hardest where the rules govern what can be built and who
    # may hold it. Bitcoin's regulatory question is narrower than Ethereum's.
    FutureEventCategory.REGULATION: {
        Asset.BTC: AssetImpact.MEDIUM,
        Asset.ETH: AssetImpact.HIGH,
        Asset.SOL: AssetImpact.HIGH,
    },
    FutureEventCategory.ETF: {
        Asset.BTC: AssetImpact.HIGH,
        Asset.ETH: AssetImpact.HIGH,
        Asset.SOL: AssetImpact.MEDIUM,
    },
    FutureEventCategory.GEOPOLITICAL: {
        Asset.BTC: AssetImpact.MEDIUM,
        Asset.ETH: AssetImpact.LOW,
        Asset.SOL: AssetImpact.LOW,
    },
    FutureEventCategory.SYSTEMIC_RISK: {
        Asset.BTC: AssetImpact.HIGH,
        Asset.ETH: AssetImpact.HIGH,
        Asset.SOL: AssetImpact.HIGH,
    },
    FutureEventCategory.INSTITUTIONAL: {
        Asset.BTC: AssetImpact.MEDIUM,
        Asset.ETH: AssetImpact.MEDIUM,
        Asset.SOL: AssetImpact.LOW,
    },
}

#: Categories that concern one network only. Their impact comes from the
#: event's own affected_assets rather than from a table.
_ASSET_SPECIFIC = {FutureEventCategory.PROTOCOL, FutureEventCategory.ONCHAIN}

_IMPORTANCE_SCORE = {
    EventImportance.LOW: 0.2,
    EventImportance.MEDIUM: 0.45,
    EventImportance.HIGH: 0.75,
    EventImportance.CRITICAL: 1.0,
}

#: Source credibility, reusing the hierarchy rather than a second scale.
_TIER_SCORE = {1: 1.0, 2: 0.85, 3: 0.6, 4: 0.0}


def asset_impact(event: Any, asset: Asset) -> AssetImpact:
    """How hard one event lands on one asset.

    An event that names its affected assets is trusted on that point: a Solana
    ETF decision says which network it concerns better than any category table.
    """

    category = getattr(event, "category", None)
    affected = list(getattr(event, "affected_assets", []) or [])

    if category in _ASSET_SPECIFIC or (affected and len(affected) < 3):
        if not affected:
            return AssetImpact.LOW
        if asset not in affected:
            return AssetImpact.LOW if category not in _ASSET_SPECIFIC else AssetImpact.NONE
        return AssetImpact.VERY_HIGH if len(affected) == 1 else AssetImpact.HIGH

    table = _CATEGORY_IMPACT.get(category)
    if table is None:
        return AssetImpact.MEDIUM
    return table.get(asset, AssetImpact.MEDIUM)


@dataclass(slots=True, frozen=True)
class EventRelevance:
    event_id: str
    title: str
    asset: Asset
    impact: AssetImpact
    score: int
    reasons: list[str]
    scheduled_at: str | None
    importance: str
    source: str
    source_url: str | None
    may_decide: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "title": self.title,
            "asset": self.asset.value,
            "asset_impact": self.impact.value,
            "relevance_score": self.score,
            "reasons": self.reasons,
            "scheduled_at": self.scheduled_at,
            "importance": self.importance,
            "source": self.source,
            "source_url": self.source_url,
            "may_influence_decision": self.may_decide,
            "usage": (
                "Le score sert à hiérarchiser ce qui est montré. Ce n'est pas "
                "une probabilité de mouvement et il ne porte aucune direction."
            ),
        }


class EventRelevanceEngine:
    """Score events so the screen can show three instead of twenty."""

    #: Below this, an event is real but not worth the reader's attention here.
    DISPLAY_FLOOR = 30

    def score(
        self, event: Any, asset: Asset, *, now: datetime | None = None
    ) -> EventRelevance:
        reference = now or datetime.now(UTC)
        impact = asset_impact(event, asset)
        importance = getattr(event, "importance", EventImportance.MEDIUM)
        tier = tier_of(getattr(event, "source_tier", None))
        may_decide = may_influence_decision(getattr(event, "source_tier", None))

        # Relevance comes from the event itself; credibility then scales it.
        # Adding a source-quality term instead gave every official item a floor
        # of twenty points, so a minor distant release outranked its own
        # irrelevance purely for being officially published.
        components = [
            (_IMPORTANCE_SCORE.get(importance, 0.45), 0.45, f"importance {importance.value}"),
            (_IMPACT_SCORE[impact], 0.40, f"impact sur {asset.value} {impact.value}"),
        ]

        scheduled = getattr(event, "scheduled_at", None)
        if scheduled is not None:
            days = max(0.0, (scheduled - reference).total_seconds() / 86400)
            # Proximity within a month; beyond that an event is context, not a
            # thing to watch this week.
            proximity = max(0.0, 1.0 - days / 30.0)
            components.append((proximity, 0.15, f"échéance dans {days:.1f} j"))
        else:
            components.append((0.3, 0.15, "sans date planifiée"))

        base = sum(value * weight for value, weight, _ in components)
        credibility = _TIER_SCORE.get(int(tier), 0.0)
        reasons = [label for value, _, label in components if value > 0]
        reasons.append(f"source de niveau {int(tier)}")

        # A discovery-only source scores zero: it must never outrank a calendar.
        score = 0 if not may_decide else round(base * credibility * 100)

        return EventRelevance(
            event_id=str(getattr(event, "id", "") or ""),
            title=str(getattr(event, "title", "") or ""),
            asset=asset,
            impact=impact,
            score=score,
            reasons=reasons,
            scheduled_at=scheduled.isoformat() if scheduled else None,
            importance=importance.value,
            source=str(getattr(event, "source", "") or ""),
            source_url=getattr(event, "source_url", None),
            may_decide=may_decide,
        )

    def top(
        self,
        events: list[Any],
        asset: Asset,
        *,
        limit: int = 3,
        now: datetime | None = None,
    ) -> list[EventRelevance]:
        """The few events worth showing, most relevant first."""

        scored = [self.score(event, asset, now=now) for event in events]
        keep = [item for item in scored if item.score >= self.DISPLAY_FLOOR]
        keep.sort(key=lambda item: (-item.score, item.scheduled_at or ""))
        return keep[:limit]

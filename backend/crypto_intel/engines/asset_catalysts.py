"""What is happening to this asset in particular - and whether it is real.

Three families feed the reading, all of them events the system already stores:

    protocol     SIMD, EIP, upgrades, incidents          (primary repositories)
    regulation   EDGAR filings, rule-making, hearings    (official filings)
    market       products launched, listed, withdrawn    (official filings)

Four rules run through it:

*Primary before media.* When a press item and an official document describe
the same thing, the official document is the event and the article becomes one
more reference on it. That is what the deduplicator does, and it is also why a
media-only item is kept apart, marked as a lead to verify.

*A stage is not the next stage.* Every catalyst carries the stage it is
actually at, and the sentence that prevents the usual shortcut ("a filing is
not an approval").

*Economics is not direction.* "Reduces future issuance" is an effect on
supply. Whether the market cares is measured against the price, separately.

*An old catalyst fades.* Freshness is part of the reading: a three-month-old
proposal is history unless its stage moved.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from ..core.enums import Asset
from ..future_events.deduplication import EventDeduplicator
from ..future_events.models import (
    EventImportance,
    FutureEvent,
    FutureEventCategory,
    FutureEventSourceTier,
)
from .catalyst_reaction import Reaction, measure
from .pit_view import PointInTimeView

#: Categories that carry an asset-specific catalyst.
CATALYST_CATEGORIES = {
    FutureEventCategory.PROTOCOL,
    FutureEventCategory.REGULATION,
}
#: Beyond this a catalyst is history unless its stage changed since.
ACTIVE_WINDOW = timedelta(days=90)
#: Tiers allowed to *be* a catalyst. Media and social can only point at one.
PRIMARY_TIERS = {FutureEventSourceTier.A, FutureEventSourceTier.B}

CATEGORY_FR = {
    FutureEventCategory.PROTOCOL: "Protocole",
    FutureEventCategory.REGULATION: "Réglementation",
}
ASSET_EMOJI = {"BTC": "🟠", "ETH": "💎", "SOL": "🟣"}


@dataclass(slots=True)
class Catalyst:
    asset: str
    event_type: str
    title: str
    description: str
    category: str
    stage: str
    stage_label: str
    stage_caveat: str
    source: str
    source_type: str
    source_url: str | None
    published_at: datetime | None
    effective_at: datetime | None
    importance: str
    confidence: str
    direction: str
    economic_effect: dict[str, Any]
    why_it_matters: str
    corroborations: list[str] = field(default_factory=list)
    reaction: Reaction | None = None
    age_days: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset": self.asset,
            "emoji": ASSET_EMOJI.get(self.asset, "🪙"),
            "event_type": self.event_type,
            "title": self.title,
            "description": self.description,
            "category": self.category,
            "stage": self.stage,
            "stage_label": self.stage_label,
            "stage_caveat": self.stage_caveat,
            "source": self.source,
            "source_type": self.source_type,
            "source_url": self.source_url,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "effective_at": self.effective_at.isoformat() if self.effective_at else None,
            "importance": self.importance,
            "confidence": self.confidence,
            "direction": self.direction,
            "economic_effect": self.economic_effect,
            "why_it_matters": self.why_it_matters,
            "corroborations": self.corroborations,
            "age_days": self.age_days,
            "market_reaction": self.reaction.to_dict() if self.reaction else None,
        }


def _confidence_word(event: FutureEvent) -> str:
    """LOW / MODERATE / HIGH - never a probability of a price move."""

    if event.source_tier is FutureEventSourceTier.A and event.confidence >= 0.85:
        return "HIGH"
    if event.source_tier in PRIMARY_TIERS:
        return "MODERATE"
    return "LOW"


def _why_it_matters(event: FutureEvent) -> str:
    """One sentence on the economic mechanism - never on the price."""

    meta = event.metadata or {}
    effect = meta.get("economic_effect") or {}
    supply = effect.get("supply_effect", "UNKNOWN")
    if event.category is FutureEventCategory.PROTOCOL:
        if supply == "ISSUANCE_DOWN":
            return (
                "Réduit la création future de jetons. L'effet sur le marché dépend du prix, "
                "des flux et du positionnement."
            )
        if supply == "ISSUANCE_UP":
            return (
                "Augmente la création future de jetons. L'effet sur le marché reste à mesurer."
            )
        if supply == "BURN":
            return (
                "Modifie la destruction de jetons. L'effet sur l'offre nette dépend de "
                "l'activité du réseau."
            )
        if effect.get("economic"):
            return (
                "Modifie l'économie du protocole (" + ", ".join(effect.get("topics", [])[:3])
                + "). L'effet sur le marché reste à mesurer."
            )
        return "Changement technique : aucun effet économique direct identifié."
    if event.category is FutureEventCategory.REGULATION:
        stage = str(meta.get("stage", ""))
        if stage in {"APPROVED", "EFFECTIVE", "LISTED", "TRADING"}:
            return (
                "Ouvre ou élargit l'accès à un produit régulé. La demande réelle se mesure "
                "ensuite dans les flux."
            )
        return (
            "Fait avancer un dossier réglementaire. Rien n'est acquis tant que l'étape "
            "suivante n'est pas franchie."
        )
    return "Événement suivi pour son contexte."


def _description(event: FutureEvent) -> str:
    meta = event.metadata or {}
    bits = []
    if meta.get("issuer"):
        bits.append(str(meta["issuer"]))
    if meta.get("form"):
        bits.append(f"formulaire {meta['form']}")
    if meta.get("proposal"):
        bits.append(str(meta["proposal"]))
    effect = meta.get("economic_effect") or {}
    if effect.get("evidence"):
        bits.append(str(effect["evidence"])[:160])
    return " · ".join(bits) or event.title


def build_catalyst(event: FutureEvent, asset: Asset, view: PointInTimeView | None,
                   now: datetime) -> Catalyst:
    meta = event.metadata or {}
    published = event.source_published_at or event.detected_at
    age = (now - published).days if published else None
    reaction = None
    if view is not None and published is not None and published <= now:
        reaction = measure(view, asset, published)
    return Catalyst(
        asset=asset.value,
        event_type=event.event_type,
        title=event.title,
        description=_description(event),
        category=CATEGORY_FR.get(event.category, event.category.value),
        stage=str(meta.get("stage", "UNKNOWN")),
        stage_label=str(meta.get("stage_label", "Étape inconnue")),
        stage_caveat=str(meta.get("stage_caveat", "")),
        source=event.source,
        source_type=str(meta.get("source_type", "PRIMARY" if event.source_tier is FutureEventSourceTier.A else "SECONDARY_MEDIA")),
        source_url=event.source_url,
        published_at=published,
        effective_at=event.scheduled_at,
        importance=event.importance.value,
        confidence=_confidence_word(event),
        direction=event.directional_effect.value,
        economic_effect=meta.get("economic_effect") or {"economic": False, "supply_effect": "UNKNOWN"},
        why_it_matters=_why_it_matters(event),
        corroborations=[
            reference.source for reference in event.source_references
            if reference.source != event.source
        ],
        reaction=reaction,
        age_days=age,
    )


@dataclass(slots=True)
class CatalystReading:
    asset: str
    catalysts: list[Catalyst] = field(default_factory=list)
    leads: list[dict[str, Any]] = field(default_factory=list)
    announcements: list[dict[str, Any]] = field(default_factory=list)
    as_of: datetime | None = None

    @property
    def has_catalyst(self) -> bool:
        return bool(self.catalysts)

    def headline(self) -> str:
        if not self.catalysts:
            return "Aucun catalyseur propre à cet actif n'est actif actuellement."
        first = self.catalysts[0]
        return f"{first.title} — {first.stage_label.lower()}."

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset": self.asset,
            "emoji": ASSET_EMOJI.get(self.asset, "🪙"),
            "headline": self.headline(),
            "catalysts": [c.to_dict() for c in self.catalysts],
            "announcements": self.announcements,
            "leads": self.leads,
            "as_of": self.as_of.isoformat() if self.as_of else None,
            "note": (
                "Une source primaire prime sur un article : un média qui rapporte un "
                "document officiel ne crée pas un second événement."
            ),
        }


class AssetCatalystEngine:
    """Per-asset catalysts, deduplicated, staged and confronted with the market."""

    def __init__(self, deduplicator: EventDeduplicator | None = None) -> None:
        self.deduplicator = deduplicator or EventDeduplicator()

    def read(self, events: list[FutureEvent], asset: Asset, *,
             view: PointInTimeView | None = None, now: datetime | None = None,
             limit: int = 6) -> CatalystReading:
        now = now or (view.as_of if view is not None else datetime.now(UTC))
        relevant = [
            event for event in events
            if asset in event.affected_assets and event.category in CATALYST_CATEGORIES
        ]
        # One real-world occurrence, whatever the number of sources covering it.
        merged = self.deduplicator.deduplicate(relevant)

        catalysts: list[Catalyst] = []
        leads: list[dict[str, Any]] = []
        announcements: list[dict[str, Any]] = []
        for event in merged:
            published = event.source_published_at or event.detected_at
            if published and now - published > ACTIVE_WINDOW:
                continue
            meta = event.metadata or {}
            if not (meta.get("catalyst") or meta.get("stage")):
                # An official announcement without an identified stage is
                # context, not a catalyst: a blog post is not a proposal.
                announcements.append({
                    "title": event.title,
                    "source": event.source,
                    "url": event.source_url,
                    "published_at": published.isoformat() if published else None,
                    "category": CATEGORY_FR.get(event.category, event.category.value),
                })
                continue
            if event.source_tier not in PRIMARY_TIERS:
                # A media item stays a lead until a primary source confirms it.
                leads.append({
                    "title": event.title,
                    "source": event.source,
                    "source_type": "SECONDARY_MEDIA",
                    "url": event.source_url,
                    "published_at": published.isoformat() if published else None,
                    "status": "À VÉRIFIER auprès de la source primaire",
                })
                continue
            catalysts.append(build_catalyst(event, asset, view, now))

        catalysts.sort(
            key=lambda c: (
                {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}.get(c.importance, 4),
                # An economic change outranks a purely procedural one.
                0 if c.economic_effect.get("economic") else 1,
                c.age_days if c.age_days is not None else 999,
            )
        )
        return CatalystReading(asset=asset.value, catalysts=catalysts[:limit],
                               leads=leads[:4], announcements=announcements[:4], as_of=now)


def catalysts_for(asset: Asset, *, view: PointInTimeView | None = None,
                  now: datetime | None = None, limit: int = 6) -> CatalystReading:
    """Read the stored events for one asset - the entry point the API uses."""

    from ..db import repo

    moment = now or (view.as_of if view is not None else datetime.now(UTC))
    events = repo.list_future_events(
        asset=asset, start=moment - ACTIVE_WINDOW, end=moment + timedelta(days=30),
        include_expired=False, limit=200,
    )
    return AssetCatalystEngine().read(
        [e for e in events if isinstance(e, FutureEvent)], asset, view=view, now=moment, limit=limit,
    )


def importance_rank(value: str) -> int:
    return {
        EventImportance.CRITICAL.value: 0,
        EventImportance.HIGH.value: 1,
        EventImportance.MEDIUM.value: 2,
        EventImportance.LOW.value: 3,
    }.get(value, 4)

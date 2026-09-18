"""Rank what can move the market, and explain the decision from that ranking.

The screen used to list every reading with the same weight: a short-term
trend line took as much room as a Fed decision fourteen hours away. This module
orders evidence the way it actually transmits to a price:

    1. REGIME       central banks, rates, energy, inflation, liquidity, rules
    2. FLOWS        ETF, spot, whales, stablecoins
    3. FRAGILITY    leverage, funding, implied volatility - amplifiers
    4. CONFIRMATION trend, structure, patterns - timing and invalidation

The tier is only a starting weight. What a reading is worth *now* is

    effective = structural x proximity x magnitude x surprise
                x confidence x freshness x asset relevance x horizon weight

so a Fed meeting forty days away cannot crush an exceptional ETF flow today,
and a small whale transfer barely registers.

Three rules this module never bends:

* attention is not direction - a decision tomorrow is CRITICAL and UNKNOWN,
  and that is a complete answer;
* no event is given a direction because of what it is - a rate cut is not
  bullish by definition; only a stated outcome can carry one;
* the same information seen three times is counted once - Fed, yields and
  credit spreads moving together are one cause and its consequences.

The decision itself is not taken here. The engine decides; this explains.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import IntEnum, StrEnum
from typing import Any

from ..core.enums import Asset
from ..future_events.models import (
    DecisionHorizon,
    EventImportance,
    ExpectedMovement,
    FutureEvent,
    FutureEventCategory,
    FutureEventSourceTier,
)
from .event_relevance import AssetImpact, asset_impact
from .factor_semantics import Availability, FactorAssessment, FactorDirection, FactorImpact
from .market_radar import (
    AttentionLevel,
    RadarCategory,
    RadarItem,
    SourceTrust,
    attention_for,
)


class Tier(IntEnum):
    REGIME = 1
    FLOWS = 2
    FRAGILITY = 3
    CONFIRMATION = 4


class DriverDirection(StrEnum):
    """Which way a driver pushes the analysed asset, when that is known."""

    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    MIXED = "MIXED"
    NEUTRAL = "NEUTRAL"
    UNKNOWN = "UNKNOWN"


class DriverRole(StrEnum):
    PRIMARY = "PRIMARY"
    SECONDARY = "SECONDARY"
    CONFIRMATION = "CONFIRMATION"
    CONTRADICTION = "CONTRADICTION"
    AMPLIFIER = "AMPLIFIER"
    CONSEQUENCE = "CONSEQUENCE"
    INVALIDATION_RISK = "INVALIDATION_RISK"
    CONTEXT = "CONTEXT"


class Reading(StrEnum):
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    MIXED = "MIXED"
    NEUTRAL = "NEUTRAL"
    UNKNOWN = "UNKNOWN"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


# ---------------------------------------------------------------------------
# Weights. Each is a documented judgement, kept in one place so it can be
# argued with. None of them is tuned to make a test pass.
# ---------------------------------------------------------------------------

#: Starting weight of a tier, before anything about the present moment.
TIER_WEIGHT: dict[Tier, float] = {
    Tier.REGIME: 1.0,
    Tier.FLOWS: 0.75,
    Tier.FRAGILITY: 0.55,
    Tier.CONFIRMATION: 0.35,
}

#: How much a *measured state* of each tier matters on each horizon. A level of
#: US yields is a slow regime: it weighs on a month and far less on the next
#: session, where flows and leverage decide. Events are not scaled here - their
#: proximity to the horizon already says how much they matter to it.
HORIZON_TIER_WEIGHT: dict[DecisionHorizon, dict[Tier, float]] = {
    DecisionHorizon.H24: {
        Tier.REGIME: 0.55,
        Tier.FLOWS: 0.9,
        Tier.FRAGILITY: 1.0,
        Tier.CONFIRMATION: 1.0,
    },
    DecisionHorizon.D7: {
        Tier.REGIME: 0.8,
        Tier.FLOWS: 1.0,
        Tier.FRAGILITY: 0.85,
        Tier.CONFIRMATION: 0.8,
    },
    DecisionHorizon.D30: {
        Tier.REGIME: 1.0,
        Tier.FLOWS: 0.9,
        Tier.FRAGILITY: 0.55,
        Tier.CONFIRMATION: 0.5,
    },
}

#: Factor key -> tier. Keys are the engine's normalised factor keys.
FACTOR_TIER: dict[str, Tier] = {
    "rates": Tier.REGIME,
    "energy": Tier.REGIME,
    "credit": Tier.REGIME,
    "flows": Tier.FLOWS,
    "spot": Tier.FLOWS,
    "whales": Tier.FLOWS,
    "stablecoins": Tier.FLOWS,
    "positioning": Tier.FRAGILITY,
    "derivatives": Tier.FRAGILITY,
    "funding": Tier.FRAGILITY,
    "implied_volatility": Tier.FRAGILITY,
    "technical": Tier.CONFIRMATION,
    "volatility": Tier.CONFIRMATION,
}

#: Same information in different forms. Within a cluster only the strongest
#: reading counts in full; the others are its consequences.
FACTOR_CLUSTER: dict[str, str] = {
    "rates": "monetary_conditions",
    "credit": "monetary_conditions",
    "energy": "energy",
    "flows": "capital_demand",
    "spot": "capital_demand",
    "stablecoins": "capital_demand",
    "whales": "whales",
    "positioning": "leverage",
    "derivatives": "leverage",
    "funding": "leverage",
    "implied_volatility": "options",
    "technical": "price_structure",
    "volatility": "price_structure",
}

#: Upstream first. ETF creations drive spot demand, not the reverse; a Fed
#: decision moves yields, which move credit. When members are of comparable
#: weight the cause leads and the rest confirm it.
CAUSAL_ORDER: dict[str, tuple[str, ...]] = {
    "capital_demand": ("flows", "stablecoins", "spot"),
    "monetary_conditions": ("rates", "credit"),
    "leverage": ("funding", "positioning", "derivatives"),
    "price_structure": ("technical", "volatility"),
}

#: A cause leads its cluster as long as it carries at least this share of the
#: strongest member's weight.
CAUSE_LEAD_SHARE = 0.5

#: A follower in a cluster still says something - that the cause is visible
#: elsewhere - but it is not a second cause.
FOLLOWER_WEIGHT = 0.25

_IMPORTANCE = {
    EventImportance.CRITICAL: 1.0,
    EventImportance.HIGH: 0.75,
    EventImportance.MEDIUM: 0.45,
    EventImportance.LOW: 0.2,
}
_MAGNITUDE = {
    ExpectedMovement.LOW: 0.4,
    ExpectedMovement.NORMAL: 0.6,
    ExpectedMovement.HIGH: 0.85,
    ExpectedMovement.EXTREME: 1.0,
}
_FACTOR_MAGNITUDE = {
    FactorImpact.LOW: 0.35,
    FactorImpact.MODERATE: 0.6,
    FactorImpact.HIGH: 0.85,
    FactorImpact.VERY_HIGH: 1.0,
}
_FRESHNESS = {
    Availability.AVAILABLE: 1.0,
    Availability.PARTIAL: 0.7,
    Availability.STALE: 0.4,
    Availability.UNAVAILABLE: 0.0,
    Availability.NOT_APPLICABLE: 0.0,
}
_ASSET = {
    AssetImpact.NONE: 0.0,
    AssetImpact.LOW: 0.4,
    AssetImpact.MEDIUM: 0.7,
    AssetImpact.HIGH: 0.9,
    AssetImpact.VERY_HIGH: 1.0,
}

#: Below this a driver is context, not something the page leads with.
PRINCIPAL_FLOOR = 0.10

#: A routine auction is a macro event in the calendar's sense, and nothing like
#: a CPI print. Weight by what the release actually moves.
_EVENT_STRUCTURAL: tuple[tuple[str, float], ...] = (
    ("FOMC", 1.0),
    ("ECB", 1.0),
    ("BOJ", 1.0),
    ("BOE", 0.9),
    ("CPI", 0.95),
    ("NFP", 0.9),
    ("PCE", 0.9),
    ("PPI", 0.7),
    ("GDP", 0.7),
    ("ECI", 0.55),
    ("TREASURY_AUCTION", 0.35),
    ("REAL_EARNINGS", 0.35),
)
_CATEGORY_STRUCTURAL = {
    FutureEventCategory.MONETARY_POLICY: 0.95,
    FutureEventCategory.MACRO: 0.6,
    FutureEventCategory.ENERGY: 0.85,
    FutureEventCategory.REGULATION: 0.7,
    FutureEventCategory.ETF: 0.6,
    FutureEventCategory.SYSTEMIC_RISK: 0.9,
    FutureEventCategory.GEOPOLITICAL: 0.6,
    FutureEventCategory.PROTOCOL: 0.5,
    FutureEventCategory.INSTITUTIONAL: 0.5,
    FutureEventCategory.ONCHAIN: 0.4,
    FutureEventCategory.OTHER: 0.3,
}
_CATEGORY_TIER = {
    FutureEventCategory.MONETARY_POLICY: Tier.REGIME,
    FutureEventCategory.MACRO: Tier.REGIME,
    FutureEventCategory.ENERGY: Tier.REGIME,
    FutureEventCategory.REGULATION: Tier.REGIME,
    FutureEventCategory.SYSTEMIC_RISK: Tier.REGIME,
    FutureEventCategory.GEOPOLITICAL: Tier.REGIME,
    FutureEventCategory.ETF: Tier.FLOWS,
    FutureEventCategory.INSTITUTIONAL: Tier.FLOWS,
    FutureEventCategory.ONCHAIN: Tier.FLOWS,
    FutureEventCategory.PROTOCOL: Tier.CONFIRMATION,
    FutureEventCategory.OTHER: Tier.CONFIRMATION,
}
_RADAR_CATEGORY = {
    FutureEventCategory.MONETARY_POLICY: RadarCategory.CENTRAL_BANK,
    FutureEventCategory.MACRO: RadarCategory.MACRO,
    FutureEventCategory.ENERGY: RadarCategory.ENERGY,
    FutureEventCategory.REGULATION: RadarCategory.REGULATION,
    FutureEventCategory.SYSTEMIC_RISK: RadarCategory.FINANCIAL_RISK,
    FutureEventCategory.GEOPOLITICAL: RadarCategory.GEOPOLITICS,
    FutureEventCategory.ETF: RadarCategory.ETF,
    FutureEventCategory.INSTITUTIONAL: RadarCategory.ETF,
    FutureEventCategory.PROTOCOL: RadarCategory.CRYPTO_NATIVE,
    FutureEventCategory.ONCHAIN: RadarCategory.CRYPTO_NATIVE,
    FutureEventCategory.OTHER: RadarCategory.OTHER,
}
_TIER_TRUST = {
    FutureEventSourceTier.A: SourceTrust.OFFICIAL,
    FutureEventSourceTier.B: SourceTrust.PRIMARY_DATA,
    FutureEventSourceTier.C: SourceTrust.REPUTABLE_NEWS,
    FutureEventSourceTier.D: SourceTrust.SECONDARY,
    FutureEventSourceTier.E: SourceTrust.SOCIAL,
}


# ---------------------------------------------------------------------------
# Vocabulary: what the reader sees. Built from the event type, never guessed
# from a headline.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _EventProfile:
    emoji: str
    name: str
    why: str
    cluster: str


def _event_profile(event: FutureEvent) -> _EventProfile:
    kind = f"{event.event_type} {event.title}".upper()
    if "FOMC" in kind or "FEDERAL RESERVE" in kind:
        return _EventProfile(
            "🇺🇸",
            "Décision de la Fed",
            "peut modifier rapidement les anticipations de taux et la liquidité "
            "en dollars disponible pour les actifs risqués",
            "fed",
        )
    if "ECB" in kind:
        return _EventProfile(
            "🇪🇺",
            "Décision de la BCE",
            "peut faire bouger l'euro et la liquidité européenne",
            "ecb",
        )
    if "BOJ" in kind:
        return _EventProfile(
            "🇯🇵",
            "Décision de la BoJ",
            "peut faire bouger le yen et forcer des débouclages de portage qui "
            "touchent tous les actifs risqués",
            "boj",
        )
    if "BOE" in kind:
        return _EventProfile(
            "🇬🇧",
            "Décision de la BoE",
            "peut faire bouger la livre et les taux européens",
            "boe",
        )
    if "CPI" in kind:
        return _EventProfile(
            "📈",
            "Inflation US (CPI)",
            "peut déplacer les anticipations sur les prochaines décisions de taux",
            "cpi",
        )
    if "PCE" in kind:
        return _EventProfile(
            "📈",
            "Inflation PCE",
            "est la mesure d'inflation suivie par la Fed et peut déplacer les "
            "anticipations de taux",
            "pce",
        )
    if "NFP" in kind or "EMPLOYMENT SITUATION" in kind:
        return _EventProfile(
            "👷",
            "Emploi US",
            "peut modifier la lecture de la croissance et donc des taux",
            "nfp",
        )
    if "PPI" in kind:
        return _EventProfile(
            "🏭",
            "Prix à la production US",
            "peut annoncer l'inflation des mois suivants",
            "ppi",
        )
    if "GDP" in kind:
        return _EventProfile(
            "🏭",
            "PIB US",
            "peut modifier la lecture de la croissance",
            "gdp",
        )
    if "TREASURY" in kind:
        return _EventProfile(
            "💵",
            "Adjudications du Trésor US",
            "une demande faible pourrait tendre les taux longs",
            "treasury_supply",
        )
    category = event.category
    if category is FutureEventCategory.ENERGY:
        return _EventProfile(
            "🛢️", event.title, "peut raviver les pressions inflationnistes", "energy"
        )
    if category is FutureEventCategory.REGULATION:
        return _EventProfile(
            "🏛️", event.title, "peut changer le cadre réglementaire", "regulation"
        )
    if category in {FutureEventCategory.GEOPOLITICAL, FutureEventCategory.SYSTEMIC_RISK}:
        return _EventProfile(
            "🌍", event.title, "peut provoquer une fuite vers les actifs sûrs", "geopolitics"
        )
    if category in {FutureEventCategory.ETF, FutureEventCategory.INSTITUTIONAL}:
        return _EventProfile(
            "💸", event.title, "peut changer l'accès des institutions", "etf_access"
        )
    return _EventProfile("📅", event.title, "peut provoquer un mouvement marqué", event.id)


_FACTOR_EMOJI = {
    "rates": "💵",
    "energy": "🛢️",
    "credit": "💸",
    "flows": "💸",
    "spot": "🪙",
    "whales": "🐋",
    "stablecoins": "💧",
    "positioning": "⚖️",
    "derivatives": "⚖️",
    "funding": "🔥",
    "implied_volatility": "📊",
    "technical": "📈",
    "volatility": "📊",
}
_FACTOR_NAME = {
    "rates": "Taux US",
    "energy": "Pétrole",
    "credit": "Crédit",
    "flows": "ETF",
    "spot": "Spot",
    "whales": "Baleines",
    "stablecoins": "Stablecoins",
    "positioning": "Levier",
    "derivatives": "Levier",
    "funding": "Funding",
    "implied_volatility": "Options",
    "technical": "Technique",
    "volatility": "Volatilité",
}

#: What happens, then why it matters - one clause each, per direction.
_FACTOR_SENTENCE: dict[tuple[str, DriverDirection], tuple[str, str]] = {
    ("flows", DriverDirection.POSITIVE): (
        "Les ETF enregistrent des entrées nettes",
        "la demande institutionnelle soutient le prix",
    ),
    ("flows", DriverDirection.NEGATIVE): (
        "Les ETF enregistrent des sorties nettes",
        "l'offre institutionnelle pèse sur le prix",
    ),
    ("spot", DriverDirection.POSITIVE): (
        "Les acheteurs dominent au comptant",
        "la demande immédiate est réelle",
    ),
    ("spot", DriverDirection.NEGATIVE): (
        "Les vendeurs dominent au comptant",
        "l'offre immédiate pèse sur le prix",
    ),
    ("rates", DriverDirection.NEGATIVE): (
        "Les taux américains restent élevés",
        "ils rendent les actifs risqués moins attractifs",
    ),
    ("rates", DriverDirection.POSITIVE): (
        "Les taux américains se détendent",
        "les conditions financières s'assouplissent",
    ),
    ("energy", DriverDirection.NEGATIVE): (
        "Le pétrole progresse",
        "il entretient le risque inflationniste et retarde une détente des taux",
    ),
    ("energy", DriverDirection.POSITIVE): (
        "Le pétrole recule",
        "la pression inflationniste s'allège",
    ),
    ("credit", DriverDirection.NEGATIVE): (
        "Les écarts de crédit s'élargissent",
        "le stress financier monte",
    ),
    ("credit", DriverDirection.POSITIVE): (
        "Les écarts de crédit se resserrent",
        "l'appétit pour le risque se maintient",
    ),
    ("technical", DriverDirection.POSITIVE): (
        "La structure technique est haussière",
        "elle confirme le mouvement sans en être la cause",
    ),
    ("technical", DriverDirection.NEGATIVE): (
        "La structure technique est baissière",
        "elle confirme la faiblesse sans en être la cause",
    ),
    ("positioning", DriverDirection.NEGATIVE): (
        "Le levier est chargé",
        "un mouvement pourrait être amplifié par des liquidations",
    ),
    ("positioning", DriverDirection.POSITIVE): (
        "Le levier se reconstruit sainement",
        "il accompagne le mouvement sans excès",
    ),
    ("funding", DriverDirection.NEGATIVE): (
        "Le coût du levier est élevé",
        "beaucoup de positions sont du même côté et peuvent être forcées",
    ),
    ("funding", DriverDirection.POSITIVE): (
        "Le coût du levier reste bas",
        "le marché n'est pas encombré d'un seul côté",
    ),
    ("whales", DriverDirection.POSITIVE): (
        "Les gros portefeuilles retirent leurs jetons des plateformes",
        "l'offre disponible à la vente diminue",
    ),
    ("whales", DriverDirection.NEGATIVE): (
        "Les gros portefeuilles déposent sur les plateformes, ventes confirmées",
        "l'offre disponible à la vente augmente",
    ),
}


# ---------------------------------------------------------------------------
# Drivers
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class Driver:
    id: str
    kind: str  # EVENT | FACTOR
    key: str
    tier: Tier
    cluster: str
    emoji: str
    title: str
    direction: DriverDirection
    attention: AttentionLevel
    structural: float
    proximity: float
    magnitude: float
    surprise: float
    confidence: float
    freshness: float
    asset_relevance: float
    horizon_weight: float
    released: bool = False
    scheduled_at: datetime | None = None
    counted_weight: float = 0.0
    counted_in: str | None = None
    role: DriverRole = DriverRole.CONTEXT
    what: str = ""
    why: str = ""
    expectation: str | None = None
    invalidation: str = ""
    status: str = ""
    tone: str = "WHITE"  # RED | ORANGE | YELLOW | GREEN | WHITE
    source: str = ""
    source_url: str | None = None

    @property
    def effective(self) -> float:
        return (
            self.structural
            * self.proximity
            * self.magnitude
            * self.surprise
            * self.confidence
            * self.freshness
            * self.asset_relevance
            * self.horizon_weight
        )

    @property
    def upcoming(self) -> bool:
        return self.kind == "EVENT" and not self.released

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "key": self.key,
            "tier": self.tier.value,
            "tier_name": self.tier.name,
            "cluster": self.cluster,
            "emoji": self.emoji,
            "title": self.title,
            "direction": self.direction.value,
            "attention": self.attention.value,
            "role": self.role.value,
            "effective_importance": round(self.effective, 4),
            "counted_weight": round(self.counted_weight, 4),
            "counted_in": self.counted_in,
            "weights": {
                "structural": round(self.structural, 3),
                "proximity": round(self.proximity, 3),
                "magnitude": round(self.magnitude, 3),
                "surprise": round(self.surprise, 3),
                "confidence": round(self.confidence, 3),
                "freshness": round(self.freshness, 3),
                "asset_relevance": round(self.asset_relevance, 3),
                "horizon": round(self.horizon_weight, 3),
            },
            "scheduled_at": self.scheduled_at.isoformat() if self.scheduled_at else None,
            "released": self.released,
            "what": self.what,
            "why": self.why,
            "expectation": self.expectation,
            "invalidation": self.invalidation,
            "status": self.status,
            "tone": self.tone,
            "source": self.source,
            "source_url": self.source_url,
        }


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _delay(when: datetime | None, now: datetime) -> str:
    if when is None:
        return "à une date non publiée"
    seconds = (_utc(when) - now).total_seconds()
    if seconds < 0:
        hours = -seconds / 3600
        return f"il y a {hours:.0f} h" if hours < 48 else f"il y a {hours / 24:.0f} j"
    hours = seconds / 3600
    if hours < 1:
        return "dans moins d'une heure"
    if hours < 48:
        return f"dans {hours:.0f} h"
    return f"dans {hours / 24:.0f} j"


def _event_structural(event: FutureEvent) -> float:
    kind = f"{event.event_type} {event.title}".upper()
    for marker, weight in _EVENT_STRUCTURAL:
        if marker in kind:
            return weight
    return _CATEGORY_STRUCTURAL.get(event.category, 0.3)


def _released(event: FutureEvent, now: datetime) -> bool:
    if event.actual_value is not None:
        return True
    if event.scheduled_at is None:
        return True  # unscheduled news: it has already happened
    return _utc(event.scheduled_at) <= now


def _event_direction(event: FutureEvent, released: bool) -> DriverDirection:
    """An event has no direction until an outcome is compared with what was priced.

    The event model's ``directional_effect`` defaults to NEUTRAL on every
    calendar entry, which would read as "no effect". It is ignored on purpose:
    only an outcome stated by a domain adapter in ``metadata`` is trusted.
    """

    if not released:
        return DriverDirection.UNKNOWN
    stated = str((event.metadata or {}).get("overall_direction") or "").upper()
    try:
        return DriverDirection(stated)
    except ValueError:
        return DriverDirection.UNKNOWN


def _surprise_factor(event: FutureEvent, released: bool) -> float:
    if not released:
        # Nothing priced means the outcome can land anywhere.
        if not event.market_probabilities:
            return 1.0
        top = max(item.probability for item in event.market_probabilities)
        return 0.5 + 0.5 * (1.0 - top)
    if event.surprise is None:
        return 0.6
    return 0.4 + 0.6 * min(1.0, abs(float(event.surprise)))


def _expectation(event: FutureEvent) -> str | None:
    """What the market prices, only from a timestamped distribution."""

    if not event.market_probabilities:
        return None
    top = max(event.market_probabilities, key=lambda item: item.probability)
    return f"Le marché valorise « {top.outcome} » à {top.probability * 100:.0f} %."


def _attention_from(value: float) -> AttentionLevel:
    if value >= 0.55:
        return AttentionLevel.CRITICAL
    if value >= 0.35:
        return AttentionLevel.HIGH
    if value >= 0.18:
        return AttentionLevel.MODERATE
    if value >= 0.06:
        return AttentionLevel.LOW
    return AttentionLevel.NONE


def driver_from_event(
    event: FutureEvent,
    *,
    asset: Asset,
    horizon: DecisionHorizon,
    now: datetime,
) -> Driver | None:
    from .future_decision import event_proximity

    proximity = event_proximity(event, horizon, as_of=now)
    if proximity <= 0:
        return None
    relevance = _ASSET[asset_impact(event, asset)]
    if relevance <= 0:
        return None
    if event.source_tier is FutureEventSourceTier.E:
        return None  # a lead, never a driver

    profile = _event_profile(event)
    released = _released(event, now)
    tier = _CATEGORY_TIER.get(event.category, Tier.CONFIRMATION)
    driver = Driver(
        id=event.id,
        kind="EVENT",
        key=event.event_type or event.category.value,
        tier=tier,
        # Released results join their cause's cluster so the rates move they
        # triggered is not counted as a second, independent reason.
        cluster=(
            "monetary_conditions"
            if released and event.category is FutureEventCategory.MONETARY_POLICY
            else profile.cluster
        ),
        emoji=profile.emoji,
        title=profile.name,
        direction=_event_direction(event, released),
        attention=AttentionLevel.NONE,
        structural=_event_structural(event) * _IMPORTANCE.get(event.importance, 0.45),
        proximity=proximity,
        magnitude=_MAGNITUDE.get(event.magnitude_effect, 0.6),
        surprise=_surprise_factor(event, released),
        confidence=max(event.confidence, 0.5),
        freshness=1.0,
        asset_relevance=relevance,
        horizon_weight=1.0,
        released=released,
        scheduled_at=event.scheduled_at,
        source=event.source,
        source_url=event.source_url,
    )
    # Absolute-time attention comes from the radar: a decision tomorrow is
    # CRITICAL whatever the horizon; horizon-relative weight is for ranking.
    radar = RadarItem(
        event_id=event.id,
        title=event.title,
        category=_RADAR_CATEGORY.get(event.category, RadarCategory.OTHER),
        trust=_TIER_TRUST.get(event.source_tier, SourceTrust.SECONDARY),
        source=event.source,
        detected_at=event.detected_at,
        scheduled_at=event.scheduled_at,
        result=None if not released or event.actual_value is None else str(event.actual_value),
    )
    radar_attention = attention_for(
        radar,
        now=now,
        surprise_is_large=released and event.surprise is not None and abs(event.surprise) >= 0.5,
    )
    scaled = _attention_from(driver.effective)
    # A routine auction is not critical because the radar's category says
    # "macro": the structural weight has the last word when it is lower.
    order = list(AttentionLevel)
    ceiling = min(len(order) - 1, order.index(scaled) + 1)
    driver.attention = (
        radar_attention
        if order.index(radar_attention) <= ceiling
        else order[ceiling]
    )

    delay = _delay(event.scheduled_at, now)
    if released:
        if event.surprise is None:
            outcome = "l'écart avec les attentes n'est pas encore mesuré"
        elif abs(event.surprise) >= 0.5:
            outcome = "le résultat s'écarte nettement des attentes"
        else:
            outcome = "le résultat est proche des attentes"
        driver.what = f"{profile.name} publiée {delay} : {outcome}."
    else:
        driver.what = f"{profile.name} {delay}."
    driver.why = f"Elle {profile.why}." if profile.name.startswith(("Décision", "Inflation")) else (
        f"Cet événement {profile.why}."
    )
    driver.expectation = _expectation(event)
    driver.invalidation = (
        "Tant que le résultat et la réaction du marché ne sont pas connus, la "
        "lecture actuelle des autres signaux reste provisoire."
        if not released
        else "Une réaction de marché opposée à l'écart publié invaliderait cette lecture."
    )
    return driver


def driver_from_factor(
    factor: FactorAssessment,
    *,
    asset: Asset,
    horizon: DecisionHorizon,
) -> Driver | None:
    tier = FACTOR_TIER.get(factor.key)
    if tier is None:
        return None
    direction = {
        FactorDirection.POSITIVE: DriverDirection.POSITIVE,
        FactorDirection.NEGATIVE: DriverDirection.NEGATIVE,
        FactorDirection.NEUTRAL: DriverDirection.NEUTRAL,
    }.get(factor.direction, DriverDirection.UNKNOWN)
    # Macro readings land on each asset as their category does.
    category = {
        "rates": FutureEventCategory.MONETARY_POLICY,
        "credit": FutureEventCategory.MACRO,
        "energy": FutureEventCategory.ENERGY,
    }.get(factor.key)
    relevance = 1.0
    if category is not None:
        from types import SimpleNamespace

        relevance = _ASSET[
            asset_impact(SimpleNamespace(category=category, affected_assets=[]), asset)
        ]
    driver = Driver(
        id=f"factor:{factor.key}",
        kind="FACTOR",
        key=factor.key,
        tier=tier,
        cluster=FACTOR_CLUSTER.get(factor.key, factor.key),
        emoji=_FACTOR_EMOJI.get(factor.key, "📊"),
        title=_FACTOR_NAME.get(factor.key, factor.label),
        direction=direction,
        attention=AttentionLevel.NONE,
        structural=TIER_WEIGHT[tier],
        proximity=1.0,
        magnitude=_FACTOR_MAGNITUDE.get(factor.impact, 0.6),
        surprise=1.0,
        confidence=max(0.0, min(1.0, factor.confidence or 0.5)),
        freshness=_FRESHNESS.get(factor.availability, 0.0),
        asset_relevance=relevance,
        horizon_weight=HORIZON_TIER_WEIGHT[horizon][tier],
        source=factor.provider,
        source_url=factor.source_url,
    )
    driver.attention = _attention_from(driver.effective)
    sentence = _FACTOR_SENTENCE.get((factor.key, direction))
    rationale = (factor.rationale or "").strip().rstrip(".")
    if sentence is not None:
        driver.what = sentence[0] + "."
        driver.why = sentence[1][0].upper() + sentence[1][1:] + "."
    else:
        driver.what = (rationale + ".") if rationale else ""
        driver.why = factor.causal_chain[-1] if factor.causal_chain else ""
    driver.expectation = None
    driver.invalidation = (
        factor.missing_requirements[0]
        if factor.missing_requirements
        else "Un retournement durable de cette lecture."
    )
    return driver


# ---------------------------------------------------------------------------
# Hierarchy
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class DecisionHierarchy:
    asset: str
    horizon: str
    action: str
    reading: Reading
    coverage: float
    drivers: list[Driver] = field(default_factory=list)
    data_gaps: list[str] = field(default_factory=list)
    headline: str = ""
    explanation: list[str] = field(default_factory=list)
    whale_status: dict[str, Any] = field(default_factory=dict)

    def by_role(self, role: DriverRole) -> list[Driver]:
        return [item for item in self.drivers if item.role is role]

    @property
    def primary(self) -> Driver | None:
        return next(iter(self.by_role(DriverRole.PRIMARY)), None)

    def home_factors(self, limit: int = 4) -> list[Driver]:
        """The primary cause first, then what else weighs most - once each."""

        ranked = [
            item
            for item in self.drivers
            if item.role
            not in {DriverRole.CONTEXT, DriverRole.CONSEQUENCE}
            and item.counted_weight >= PRINCIPAL_FLOOR
        ]
        ranked.sort(key=lambda item: (item.role is not DriverRole.PRIMARY, -item.counted_weight))
        return ranked[:limit]

    def to_dict(self) -> dict[str, Any]:
        def ids(role: DriverRole) -> list[dict[str, Any]]:
            return [item.to_dict() for item in self.by_role(role)]

        primary = self.primary
        return {
            "asset": self.asset,
            "horizon": self.horizon,
            "action": self.action,
            "reading": self.reading.value,
            "coverage": round(self.coverage, 3),
            "headline": self.headline,
            "explanation": self.explanation,
            "primary_driver": primary.to_dict() if primary else None,
            "secondary_drivers": ids(DriverRole.SECONDARY),
            "confirmations": ids(DriverRole.CONFIRMATION),
            "contradictions": ids(DriverRole.CONTRADICTION),
            "amplifiers": ids(DriverRole.AMPLIFIER),
            "consequences": ids(DriverRole.CONSEQUENCE),
            "upcoming_invalidation_risks": [
                item.to_dict()
                for item in self.drivers
                if item.upcoming and item.counted_weight >= PRINCIPAL_FLOOR
            ],
            "home_factors": [item.to_dict() for item in self.home_factors()],
            "context": ids(DriverRole.CONTEXT)[:8],
            "data_gaps": self.data_gaps,
            "whale_status": self.whale_status,
            "methodology": (
                "importance effective = structurel × proximité × amplitude × "
                "surprise × confiance × fraîcheur × pertinence actif × horizon; "
                "une seule lecture comptée par grappe causale; l'attention ne "
                "porte jamais de direction."
            ),
        }


#: Readings whose absence the page has to admit.
_EXPECTED_KEYS = ("rates", "energy", "credit", "flows", "spot", "whales", "positioning")


def _dedupe(drivers: list[Driver]) -> None:
    """One reading per cluster counts; the rest are its consequences."""

    clusters: dict[str, list[Driver]] = {}
    for item in drivers:
        clusters.setdefault(item.cluster, []).append(item)
    for name, members in clusters.items():
        members.sort(key=lambda item: item.effective, reverse=True)
        strongest = members[0].effective
        leader = members[0]
        # A released decision is the cause of the rates move it triggered.
        events = [m for m in members if m.kind == "EVENT"]
        order = CAUSAL_ORDER.get(name, ())
        upstream = events + sorted(
            (m for m in members if m.key in order),
            key=lambda item: order.index(item.key),
        )
        for candidate in upstream:
            if candidate.effective >= CAUSE_LEAD_SHARE * strongest:
                leader = candidate
                break
        members.remove(leader)
        members.insert(0, leader)
        leader.counted_weight = leader.effective
        for follower in members[1:]:
            follower.counted_weight = follower.effective * FOLLOWER_WEIGHT
            follower.counted_in = leader.id


def _lean(drivers: list[Driver]) -> Reading:
    """Which way the counted, directional evidence leans - fragility excluded.

    Leverage and options speak about how far a move can run, not where it
    goes. Pending events have no direction to add.
    """

    pro = con = 0.0
    for item in drivers:
        if item.counted_in is not None or item.tier is Tier.FRAGILITY:
            continue
        if item.direction is DriverDirection.POSITIVE:
            pro += item.counted_weight
        elif item.direction is DriverDirection.NEGATIVE:
            con += item.counted_weight
    total = pro + con
    if total < 0.05:
        return Reading.UNKNOWN
    if min(pro, con) / total >= 0.3:
        return Reading.MIXED
    if pro > con:
        return Reading.POSITIVE if pro / total >= 0.65 else Reading.NEUTRAL
    return Reading.NEGATIVE if con / total >= 0.65 else Reading.NEUTRAL


def _assign_roles(drivers: list[Driver], reading: Reading) -> None:
    ranked = sorted(drivers, key=lambda item: item.counted_weight, reverse=True)
    lean = {
        Reading.POSITIVE: DriverDirection.POSITIVE,
        Reading.NEGATIVE: DriverDirection.NEGATIVE,
    }.get(reading)
    primary_set = False
    for item in ranked:
        if item.counted_in is not None:
            item.role = DriverRole.CONSEQUENCE
            continue
        if item.counted_weight < PRINCIPAL_FLOOR:
            item.role = DriverRole.CONTEXT
            continue
        calm_fragility = item.tier is Tier.FRAGILITY and not (
            item.direction is DriverDirection.NEGATIVE
            or item.magnitude >= _FACTOR_MAGNITUDE[FactorImpact.HIGH]
        )
        if not primary_set and not calm_fragility:
            item.role = DriverRole.PRIMARY
            primary_set = True
            continue
        if item.upcoming:
            item.role = DriverRole.INVALIDATION_RISK
        elif item.tier is Tier.FRAGILITY:
            # Leverage that is not stretched is reassurance, not a factor the
            # page should lead with; it stays in context.
            fragile = item.direction is DriverDirection.NEGATIVE or item.magnitude >= _FACTOR_MAGNITUDE[FactorImpact.HIGH]
            item.role = DriverRole.AMPLIFIER if fragile else DriverRole.CONTEXT
        elif lean is not None and item.direction not in {lean, DriverDirection.UNKNOWN, DriverDirection.NEUTRAL}:
            item.role = DriverRole.CONTRADICTION
        elif reading is Reading.MIXED and item.direction in {
            DriverDirection.POSITIVE,
            DriverDirection.NEGATIVE,
        }:
            primary = next(d for d in ranked if d.role is DriverRole.PRIMARY)
            item.role = (
                DriverRole.CONTRADICTION
                if primary.direction
                in {DriverDirection.POSITIVE, DriverDirection.NEGATIVE}
                and item.direction is not primary.direction
                else DriverRole.SECONDARY
            )
        elif item.tier is Tier.CONFIRMATION:
            item.role = DriverRole.CONFIRMATION
        else:
            item.role = DriverRole.SECONDARY


def _status(item: Driver, now: datetime, *, gating: bool = False) -> tuple[str, str]:
    """The one line under a factor on the home, and its colour."""

    if gating and item.upcoming:
        return f"Bloque l'entrée • {_delay(item.scheduled_at, now)}", "RED"
    if item.upcoming:
        tone = {
            AttentionLevel.CRITICAL: "RED",
            AttentionLevel.HIGH: "RED",
            AttentionLevel.MODERATE: "ORANGE",
        }.get(item.attention, "YELLOW")
        level = {
            "RED": "Risque élevé",
            "ORANGE": "À surveiller",
            "YELLOW": "À l'agenda",
        }[tone]
        return f"{level} • {_delay(item.scheduled_at, now)}", tone
    if item.freshness <= 0:
        return "Donnée indisponible", "WHITE"
    if item.key == "implied_volatility":
        if item.magnitude >= _FACTOR_MAGNITUDE[FactorImpact.HIGH]:
            return "Les options anticipent un mouvement ample", "ORANGE"
        return "Mouvement ordinaire anticipé", "YELLOW"
    if item.tier is Tier.FRAGILITY:
        if item.direction is DriverDirection.NEGATIVE or item.attention in {
            AttentionLevel.HIGH,
            AttentionLevel.CRITICAL,
        }:
            return "Fragilité : peut amplifier un mouvement", "ORANGE"
        return "Pas d'excès de levier", "GREEN" if item.direction is DriverDirection.POSITIVE else "YELLOW"
    if item.direction is DriverDirection.POSITIVE:
        return {
            "flows": "Flux favorables",
            "spot": "Acheteurs dominants",
            "technical": "Tendance haussière",
            "rates": "Détente des taux",
            "energy": "Pression en baisse",
            "whales": "Retraits des plateformes",
        }.get(item.key, "Favorable"), "GREEN"
    if item.direction is DriverDirection.NEGATIVE:
        tone = "RED" if item.attention in {AttentionLevel.HIGH, AttentionLevel.CRITICAL} else "ORANGE"
        return {
            "flows": "Sorties nettes",
            "spot": "Vendeurs dominants",
            "technical": "Tendance baissière",
            "rates": "Taux qui pèsent",
            "energy": "Pression macro à surveiller",
            "credit": "Stress de crédit",
        }.get(item.key, "Défavorable"), tone
    if item.direction is DriverDirection.MIXED:
        return "Lecture mitigée", "YELLOW"
    if item.direction is DriverDirection.NEUTRAL:
        return "Sans effet net", "YELLOW"
    if item.key == "whales":
        return "Mouvement notable, vente non confirmée", "YELLOW"
    return "Direction inconnue", "WHITE"


#: How a consequence is named inside its cause's sentence.
_CONFIRMED_BY: dict[tuple[str, DriverDirection], str] = {
    ("spot", DriverDirection.POSITIVE): "les achats au comptant",
    ("spot", DriverDirection.NEGATIVE): "les ventes au comptant",
    ("flows", DriverDirection.POSITIVE): "les entrées sur les ETF",
    ("flows", DriverDirection.NEGATIVE): "les sorties des ETF",
    ("credit", DriverDirection.NEGATIVE): "l'élargissement des écarts de crédit",
    ("rates", DriverDirection.NEGATIVE): "des taux américains élevés",
    ("funding", DriverDirection.NEGATIVE): "un coût du levier élevé",
    ("positioning", DriverDirection.NEGATIVE): "un levier chargé",
}


def _line(
    item: Driver,
    now: datetime,
    *,
    opposing: bool = False,
    confirmed_by: list[Driver] | None = None,
) -> str:
    if item.kind == "EVENT":
        if item.upcoming:
            text = (
                f"{item.emoji} {item.title} {_delay(item.scheduled_at, now)} : "
                f"{item.why[0].lower()}{item.why[1:].rstrip('.')}"
            )
            if item.expectation:
                text += f". {item.expectation.rstrip('.')}"
            return text + "."
        return f"{item.emoji} {item.what}"
    cause = item.what.rstrip(".")
    consequence = item.why.rstrip(".")
    if not cause:
        return ""
    if opposing:
        cause = f"En sens inverse, {cause[0].lower()}{cause[1:]}"
    echoes = [
        _CONFIRMED_BY[(other.key, other.direction)]
        for other in confirmed_by or []
        if other.direction is item.direction and (other.key, other.direction) in _CONFIRMED_BY
    ]
    if echoes:
        cause = f"{cause}, ce que confirment {' et '.join(echoes)}"
    if not consequence:
        return f"{item.emoji} {cause}."
    return f"{item.emoji} {cause} : {consequence[0].lower()}{consequence[1:]}."


def _decision_line(
    hierarchy: DecisionHierarchy,
    *,
    gate_active: bool,
    gate_event: Driver | None,
    no_edge: bool,
    conditions_to_buy: list[str],
    conditions_to_sell: list[str],
    now: datetime,
) -> str:
    action = hierarchy.action
    upcoming = [d for d in hierarchy.drivers if d.upcoming and d.counted_weight >= PRINCIPAL_FLOOR]
    next_event = min(
        upcoming,
        key=lambda item: item.scheduled_at or now + timedelta(days=365),
        default=None,
    )
    if action == "INSUFFICIENT_DATA":
        missing = ", ".join(hierarchy.data_gaps) or "plusieurs familles"
        return f"⚪️ Données majeures manquantes ({missing}) : aucune recommandation n'est donnée."
    if action == "WAIT":
        if gate_active and gate_event is not None:
            return (
                f"⏳ L'entrée est différée jusqu'à la publication ({gate_event.title}, "
                f"{_delay(gate_event.scheduled_at, now)}) : l'écart avec les "
                "attentes et la réaction du marché décideront de la suite."
            )
        if no_edge:
            follow = (
                f" Prochain point : {next_event.title} {_delay(next_event.scheduled_at, now)}."
                if next_event is not None
                else ""
            )
            return (
                "⏳ Aucun de ces signaux n'a encore montré d'avantage mesurable sur "
                "l'historique : pas d'entrée tant qu'un avantage ne se confirme pas."
                + follow
            )
        if hierarchy.reading is Reading.MIXED:
            pro = next(
                (d for d in hierarchy.drivers if d.counted_in is None and d.direction is DriverDirection.POSITIVE and d.counted_weight >= PRINCIPAL_FLOOR),
                None,
            )
            con = next(
                (d for d in hierarchy.drivers if d.counted_in is None and d.direction is DriverDirection.NEGATIVE and d.counted_weight >= PRINCIPAL_FLOOR),
                None,
            )
            if pro is not None and con is not None:
                return (
                    f"⏳ Tant que « {pro.title} » et « {con.title} » tirent en sens "
                    "opposé, aucune entrée n'est justifiée."
                )
        if next_event is not None:
            return (
                f"⏳ Aucun facteur ne domine assez pour prendre position ; prochain "
                f"point : {next_event.title} {_delay(next_event.scheduled_at, now)}."
            )
        return "⏳ Aucun facteur ne domine assez pour justifier une position maintenant."
    if action == "BUY":
        invalid = conditions_to_sell[0].rstrip(".") if conditions_to_sell else None
        tail = f" ❌ Invalidation : {invalid[0].lower()}{invalid[1:]}." if invalid else ""
        return "✅ Les facteurs dominants convergent : l'achat est justifié sur cet horizon." + tail
    if action == "SELL":
        back = conditions_to_buy[0].rstrip(".") if conditions_to_buy else None
        tail = f" ✅ Reprise si : {back[0].lower()}{back[1:]}." if back else ""
        return "❌ Les facteurs dominants pèsent : réduire l'exposition est justifié." + tail
    return ""


def build_hierarchy(
    *,
    asset: Asset,
    horizon: DecisionHorizon,
    action: str,
    factors: list[FactorAssessment],
    events: list[FutureEvent],
    now: datetime,
    gate_active: bool = False,
    gate_event_ids: list[str] | None = None,
    no_edge: bool = False,
    conditions_to_buy: list[str] | None = None,
    conditions_to_sell: list[str] | None = None,
) -> DecisionHierarchy:
    now = _utc(now)
    drivers: list[Driver] = []
    for factor in factors:
        driver = driver_from_factor(factor, asset=asset, horizon=horizon)
        if driver is not None:
            drivers.append(driver)
    for event in events:
        driver = driver_from_event(event, asset=asset, horizon=horizon, now=now)
        if driver is not None:
            drivers.append(driver)

    _dedupe(drivers)

    by_key = {factor.key: factor for factor in factors}
    # A reading the engine never published is as missing as one it published
    # as unavailable.
    gaps = [
        _FACTOR_NAME.get(key, key)
        for key in _EXPECTED_KEYS
        if key not in by_key
        or by_key[key].availability in {Availability.UNAVAILABLE, Availability.NOT_APPLICABLE}
    ]
    measured_weight = sum(
        TIER_WEIGHT[FACTOR_TIER[key]]
        for key in _EXPECTED_KEYS
        if key in by_key and _FRESHNESS[by_key[key].availability] > 0
    )
    expected_weight = sum(TIER_WEIGHT[FACTOR_TIER[key]] for key in _EXPECTED_KEYS)
    coverage = measured_weight / expected_weight if expected_weight else 0.0

    reading = _lean(drivers)
    if coverage < 0.4:
        reading = Reading.INSUFFICIENT_DATA
    _assign_roles(drivers, reading)
    gating_ids = set(gate_event_ids or []) if gate_active else set()
    for item in drivers:
        item.status, item.tone = _status(item, now, gating=item.id in gating_ids)
        # The event holding the decision is never demoted to background.
        if item.id in gating_ids and item.role is DriverRole.CONTEXT:
            item.role = DriverRole.INVALIDATION_RISK
            item.counted_weight = max(item.counted_weight, PRINCIPAL_FLOOR)

    drivers.sort(key=lambda item: item.counted_weight, reverse=True)
    hierarchy = DecisionHierarchy(
        asset=asset.value,
        horizon=horizon.value,
        action=action,
        reading=reading,
        coverage=coverage,
        drivers=drivers,
        data_gaps=gaps,
    )

    whale = next((d for d in drivers if d.key == "whales" and d.kind == "FACTOR"), None)
    if whale is None or whale.freshness <= 0:
        hierarchy.whale_status = {
            "status": "Donnée indisponible",
            "tone": "WHITE",
            "detail": (
                by_key["whales"].missing_requirements[0]
                if "whales" in by_key and by_key["whales"].missing_requirements
                else "Aucune source baleines configurée."
            ),
            "principal": False,
        }
    else:
        hierarchy.whale_status = {
            "status": (
                whale.status
                if whale.counted_weight >= PRINCIPAL_FLOOR
                else "Pas de signal majeur confirmé"
            ),
            "tone": whale.tone if whale.counted_weight >= PRINCIPAL_FLOOR else "WHITE",
            "detail": whale.what,
            "principal": whale.counted_weight >= PRINCIPAL_FLOOR,
        }

    # --- Explanation: cause -> consequence -> decision, four or five lines. ---
    lines: list[str] = []
    def followers(leader: Driver) -> list[Driver]:
        return [d for d in drivers if d.counted_in == leader.id]

    primary = hierarchy.primary
    if primary is not None:
        lines.append(_line(primary, now, confirmed_by=followers(primary)))
    for role in (
        DriverRole.SECONDARY,
        DriverRole.CONTRADICTION,
        DriverRole.AMPLIFIER,
        DriverRole.INVALIDATION_RISK,
        DriverRole.CONFIRMATION,
    ):
        for item in hierarchy.by_role(role):
            if len(lines) >= 3:
                break
            text = _line(
                item,
                now,
                opposing=role is DriverRole.CONTRADICTION,
                confirmed_by=followers(item),
            )
            if not text or text in lines:
                continue
            lines.append(text)
    if gaps and len(lines) < 4 and any(g in {"Crédit", "Baleines", "ETF", "Spot", "Taux US"} for g in gaps):
        lines.append(f"⚪️ {', '.join(gaps)} : donnée indisponible, la lecture est moins complète.")
    gate_event = next(
        (d for d in drivers if gate_event_ids and d.id in gate_event_ids),
        None,
    )
    decision = _decision_line(
        hierarchy,
        gate_active=gate_active,
        gate_event=gate_event,
        no_edge=no_edge,
        conditions_to_buy=list(conditions_to_buy or []),
        conditions_to_sell=list(conditions_to_sell or []),
        now=now,
    )
    if decision:
        lines = lines[:4]
        lines.append(decision)
    hierarchy.explanation = [re.sub(r"\s+", " ", line).strip() for line in lines if line]
    hierarchy.headline = hierarchy.explanation[0] if hierarchy.explanation else ""
    return hierarchy

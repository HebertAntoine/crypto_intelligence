"""What deserves attention now, and for how long.

The rule the whole module is built around: noticing something is not the same
as knowing which way it points. "Fed meets tomorrow" is a reason to pay
attention and nothing else - it is neither bullish nor bearish, and a system
that turns every headline into a direction will be wrong roughly half the time
while sounding certain.

So attention and direction are separate fields with separate vocabularies, and
a direction only appears once a result exists to compare against what was
expected. The second concern is the opposite of detection: an item that has
stopped mattering has to leave on its own, because a page that accumulates is a
page nobody can read.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any


class AttentionLevel(StrEnum):
    """How much this deserves being looked at. Never a direction."""

    NONE = "NONE"
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class EventDirection(StrEnum):
    """Which way it points, once that can be said at all."""

    FAVORABLE = "FAVORABLE"
    NEUTRAL = "NEUTRAL"
    UNFAVORABLE = "UNFAVORABLE"
    MIXED = "MIXED"
    UNKNOWN = "UNKNOWN"


class RadarStatus(StrEnum):
    DETECTED = "DETECTED"
    CONFIRMED = "CONFIRMED"
    SCHEDULED = "SCHEDULED"
    UPCOMING = "UPCOMING"
    IMMINENT = "IMMINENT"
    RELEASED = "RELEASED"
    RESULT_AVAILABLE = "RESULT_AVAILABLE"
    INTERPRETED = "INTERPRETED"
    DIGESTING = "DIGESTING"
    SUPERSEDED = "SUPERSEDED"
    EXPIRED = "EXPIRED"


class SourceTrust(StrEnum):
    OFFICIAL = "OFFICIAL"
    PRIMARY_DATA = "PRIMARY_DATA"
    REPUTABLE_NEWS = "REPUTABLE_NEWS"
    SECONDARY = "SECONDARY"
    SOCIAL = "SOCIAL"


#: Only these may carry a decision contribution. Everything below is a lead to
#: be confirmed, never a fact to act on.
DECIDING_TRUST = {SourceTrust.OFFICIAL, SourceTrust.PRIMARY_DATA, SourceTrust.REPUTABLE_NEWS}


class RadarCategory(StrEnum):
    CENTRAL_BANK = "CENTRAL_BANK"
    MACRO = "MACRO"
    RATES = "RATES"
    LIQUIDITY = "LIQUIDITY"
    FX = "FX"
    ETF = "ETF"
    REGULATION = "REGULATION"
    GEOPOLITICS = "GEOPOLITICS"
    ENERGY = "ENERGY"
    FINANCIAL_RISK = "FINANCIAL_RISK"
    CRYPTO_NATIVE = "CRYPTO_NATIVE"
    OTHER = "OTHER"


#: How long an item of each kind stays worth showing once it has been published,
#: absent any further development. A scheduled release is digested within a day;
#: a rule change keeps mattering while the market works out what it means.
#: These are not universal: section 7 explicitly rejects a single blanket value.
DECAY_AFTER_RELEASE: dict[RadarCategory, timedelta] = {
    RadarCategory.CENTRAL_BANK: timedelta(hours=48),
    RadarCategory.MACRO: timedelta(hours=24),
    RadarCategory.RATES: timedelta(hours=12),
    RadarCategory.LIQUIDITY: timedelta(hours=36),
    RadarCategory.FX: timedelta(hours=12),
    RadarCategory.ETF: timedelta(hours=24),
    RadarCategory.REGULATION: timedelta(hours=72),
    RadarCategory.GEOPOLITICS: timedelta(hours=48),
    RadarCategory.ENERGY: timedelta(hours=24),
    RadarCategory.FINANCIAL_RISK: timedelta(hours=72),
    RadarCategory.CRYPTO_NATIVE: timedelta(hours=48),
    RadarCategory.OTHER: timedelta(hours=12),
}

#: Attention a category can reach at most, before proximity and surprise.
BASE_ATTENTION: dict[RadarCategory, AttentionLevel] = {
    RadarCategory.CENTRAL_BANK: AttentionLevel.CRITICAL,
    RadarCategory.MACRO: AttentionLevel.HIGH,
    RadarCategory.REGULATION: AttentionLevel.HIGH,
    RadarCategory.FINANCIAL_RISK: AttentionLevel.HIGH,
    RadarCategory.ETF: AttentionLevel.MODERATE,
    RadarCategory.RATES: AttentionLevel.MODERATE,
    RadarCategory.LIQUIDITY: AttentionLevel.MODERATE,
    RadarCategory.FX: AttentionLevel.MODERATE,
    RadarCategory.ENERGY: AttentionLevel.MODERATE,
    RadarCategory.GEOPOLITICS: AttentionLevel.MODERATE,
    RadarCategory.CRYPTO_NATIVE: AttentionLevel.MODERATE,
    RadarCategory.OTHER: AttentionLevel.LOW,
}

_ATTENTION_ORDER = [
    AttentionLevel.NONE,
    AttentionLevel.LOW,
    AttentionLevel.MODERATE,
    AttentionLevel.HIGH,
    AttentionLevel.CRITICAL,
]


def _shift(level: AttentionLevel, steps: int) -> AttentionLevel:
    index = _ATTENTION_ORDER.index(level) + steps
    return _ATTENTION_ORDER[max(0, min(len(_ATTENTION_ORDER) - 1, index))]


@dataclass(slots=True)
class RadarItem:
    """One thing the radar is watching, with its own clock."""

    event_id: str
    title: str
    category: RadarCategory
    trust: SourceTrust
    source: str
    detected_at: datetime
    scheduled_at: datetime | None = None
    published_at: datetime | None = None
    status: RadarStatus = RadarStatus.DETECTED
    attention: AttentionLevel = AttentionLevel.LOW
    direction: EventDirection = EventDirection.UNKNOWN
    confirmed_by: list[str] = field(default_factory=list)
    cluster_id: str = ""
    result: str | None = None
    consensus: str | None = None
    surprise: str | None = None
    interpretation: str = ""
    affected_assets: list[str] = field(default_factory=list)
    source_url: str | None = None
    #: Why it was kept, or the reason it was turned away.
    rationale: str = ""

    @property
    def is_confirmed(self) -> bool:
        return self.trust in DECIDING_TRUST or bool(self.confirmed_by)

    @property
    def decision_contribution(self) -> float:
        """An unconfirmed item influences nothing, whatever it says."""

        if not self.is_confirmed:
            return 0.0
        if self.direction is EventDirection.UNKNOWN:
            return 0.0
        return 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "title": self.title,
            "category": self.category.value,
            "trust": self.trust.value,
            "source": self.source,
            "source_url": self.source_url,
            "status": self.status.value,
            "attention": self.attention.value,
            "direction": self.direction.value,
            "confirmed": self.is_confirmed,
            "confirmed_by": self.confirmed_by,
            "cluster_id": self.cluster_id,
            "scheduled_at": self.scheduled_at.isoformat() if self.scheduled_at else None,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "result": self.result,
            "consensus": self.consensus,
            "surprise": self.surprise,
            "interpretation": self.interpretation,
            "affected_assets": self.affected_assets,
            "decision_contribution": self.decision_contribution,
            "rationale": self.rationale,
            "usage": (
                "Le niveau d'attention dit à quel point surveiller; il ne dit "
                "jamais dans quel sens le marché ira."
            ),
        }


# ---------------------------------------------------------------------------
# Materiality
# ---------------------------------------------------------------------------

#: Wording that marks an item as opinion rather than news. A piece that only
#: predicts, expects or speculates carries no new fact to react to.
_NOISE_MARKERS = (
    "pourrait", "could", "may ", "analyst", "analyste", "prédit", "predicts",
    "opinion", "selon certains", "rumeur", "rumor", "rumour", "on dit",
    "here's why", "voici pourquoi", "what to expect", "ce qu'il faut attendre",
    "price prediction", "prévision de prix", "top 5", "top 10",
)

#: A fact worth reacting to usually names a change, a decision or a figure.
_MATERIAL_MARKERS = (
    "decision", "décision", "raises", "cuts", "relève", "abaisse", "vote",
    "passed", "adopté", "signed", "promulgué", "announces", "annonce",
    "publishes", "publie", "report", "rapport", "data", "données",
    "approves", "approuve", "rejects", "rejette", "hack", "exploit",
    "halt", "suspend", "sanction", "tariff", "droits de douane",
    "inflation", "unemployment", "chômage", "gdp", "pib", "meeting", "réunion",
)


@dataclass(slots=True, frozen=True)
class MaterialityVerdict:
    material: bool
    reason: str


def is_market_material(
    title: str, category: RadarCategory, trust: SourceTrust
) -> MaterialityVerdict:
    """Whether an item carries a fact the market can react to.

    Mentioning Bitcoin is not a qualification. What matters is whether
    something changed: a decision, a vote, a figure, an incident. Commentary
    about what might happen adds no fact, however many keywords it contains.
    """

    text = title.lower()

    opinion = next((marker for marker in _NOISE_MARKERS if marker in text), None)
    if opinion is not None:
        return MaterialityVerdict(
            False, f"commentaire ou spéculation (« {opinion.strip()} »)"
        )

    fact = next((marker for marker in _MATERIAL_MARKERS if marker in text), None)
    if fact is None:
        return MaterialityVerdict(
            False, "aucun fait nouveau identifiable dans le titre"
        )

    if trust is SourceTrust.SOCIAL:
        # Kept as a lead, never as an entry: it has to be re-sourced first.
        return MaterialityVerdict(
            False, "source sociale: à confirmer auprès d'une source primaire"
        )

    return MaterialityVerdict(True, f"fait identifiable (« {fact.strip()} »)")


# ---------------------------------------------------------------------------
# Attention
# ---------------------------------------------------------------------------


def attention_for(
    item: RadarItem, *, now: datetime, surprise_is_large: bool = False
) -> AttentionLevel:
    """How closely to watch, from the category, the clock and the surprise.

    Nothing here looks at direction, and nothing here produces one.

    Distance dominates. A policy meeting is the most important thing on the
    calendar and still does not deserve attention today if it is five months
    away - otherwise everything is critical at once, which is the same as
    nothing being critical. So proximity sets a ceiling the category cannot
    exceed.
    """

    level = BASE_ATTENTION.get(item.category, AttentionLevel.LOW)

    if item.scheduled_at is not None:
        remaining = item.scheduled_at - now
        if remaining < timedelta(0):
            # Already happened: it stays worth reading while the outcome is
            # unread or fresh, and the lifecycle expires it soon after.
            if item.result is None:
                level = _shift(level, 1)
        elif remaining <= timedelta(hours=12):
            level = _shift(level, 1)
        elif remaining <= timedelta(hours=48):
            pass
        elif remaining <= timedelta(days=7):
            level = _shift(level, -1)
        elif remaining <= timedelta(days=30):
            level = _shift(level, -2)
        else:
            # Beyond a month it is context, not news.
            level = _shift(level, -3)

    if surprise_is_large:
        level = _shift(level, 1)

    # An unconfirmed lead is worth noticing, never worth alarm.
    if not item.is_confirmed:
        level = min(level, AttentionLevel.LOW, key=_ATTENTION_ORDER.index)

    return level


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def advance(item: RadarItem, now: datetime) -> RadarItem:
    """Move an item along its own timeline. No human step anywhere.

    The transition that matters most is the last one: something that has
    stopped mattering leaves by itself, because a page that only accumulates
    stops answering "what counts now".
    """

    if item.status in {RadarStatus.EXPIRED, RadarStatus.SUPERSEDED}:
        item.attention = AttentionLevel.NONE
        return item

    if item.scheduled_at is not None and item.scheduled_at > now:
        remaining = item.scheduled_at - now
        if remaining > timedelta(hours=24):
            item.status = RadarStatus.UPCOMING if item.is_confirmed else RadarStatus.DETECTED
        else:
            item.status = RadarStatus.IMMINENT
    elif item.scheduled_at is not None or item.published_at is not None:
        # Either the scheduled moment has passed, or this is unscheduled news
        # that simply broke. Most news has no calendar entry at all, so it has
        # to reach the same lifecycle - otherwise it would never age out.
        if item.result is None and not item.interpretation:
            item.status = RadarStatus.RELEASED
        elif item.interpretation:
            item.status = RadarStatus.INTERPRETED
        else:
            item.status = RadarStatus.RESULT_AVAILABLE

    reference = item.published_at or item.scheduled_at
    if reference is not None and reference <= now:
        age = now - reference
        window = DECAY_AFTER_RELEASE.get(item.category, timedelta(hours=24))
        if item.status in {RadarStatus.INTERPRETED, RadarStatus.RESULT_AVAILABLE}:
            if age >= window:
                item.status = RadarStatus.EXPIRED
            elif age >= window / 2:
                item.status = RadarStatus.DIGESTING
        elif item.status is RadarStatus.RELEASED and age >= window:
            # The outcome never arrived and the window closed: it stops being
            # something to watch rather than waiting indefinitely.
            item.status = RadarStatus.EXPIRED

    if item.status in {RadarStatus.EXPIRED, RadarStatus.SUPERSEDED}:
        # Whatever it was worth, it is over. Anything else would leave a
        # months-old release sitting at the top of the attention list.
        item.attention = AttentionLevel.NONE
    else:
        item.attention = attention_for(item, now=now)
    return item


def is_on_home(item: RadarItem) -> bool:
    """Only what still counts right now reaches the front page."""

    return item.status in {
        RadarStatus.UPCOMING,
        RadarStatus.IMMINENT,
        RadarStatus.RELEASED,
        RadarStatus.RESULT_AVAILABLE,
        RadarStatus.INTERPRETED,
    } and item.attention in {
        AttentionLevel.MODERATE,
        AttentionLevel.HIGH,
        AttentionLevel.CRITICAL,
    }


# ---------------------------------------------------------------------------
# Interpretation
# ---------------------------------------------------------------------------


def interpret_result(
    item: RadarItem,
    *,
    outcome_vs_consensus: str,
    market_confirms: bool | None = None,
) -> RadarItem:
    """Direction comes from the gap with what was expected, never from the type.

    ``outcome_vs_consensus`` is supplied by whoever read the release: BETTER,
    IN_LINE or WORSE for risk assets. The radar does not decide that a rate cut
    is good news; it records what the comparison said.
    """

    mapping = {
        "BETTER": EventDirection.FAVORABLE,
        "IN_LINE": EventDirection.NEUTRAL,
        "WORSE": EventDirection.UNFAVORABLE,
    }
    direction = mapping.get(outcome_vs_consensus.upper(), EventDirection.UNKNOWN)

    if direction in {EventDirection.FAVORABLE, EventDirection.UNFAVORABLE}:
        if market_confirms is False:
            # The reading stands, but the tape disagrees with it. Saying so is
            # more useful than picking one of the two and hiding the other.
            item.interpretation = (
                f"Résultat {('meilleur' if direction is EventDirection.FAVORABLE else 'moins bon')} "
                "qu'anticipé, mais les flux ne le confirment pas encore."
            )
            item.direction = EventDirection.MIXED
            item.surprise = outcome_vs_consensus.upper()
            return item
        item.interpretation = (
            "Résultat "
            + ("meilleur" if direction is EventDirection.FAVORABLE else "moins bon")
            + " qu'anticipé."
        )
    elif direction is EventDirection.NEUTRAL:
        item.interpretation = "Résultat conforme aux attentes: peu de surprise."
    else:
        item.interpretation = "Résultat non exploitable en l'état."

    item.direction = direction
    item.surprise = outcome_vs_consensus.upper()
    return item


# ---------------------------------------------------------------------------
# Clustering
# ---------------------------------------------------------------------------


def assign_clusters(items: list[RadarItem]) -> list[RadarItem]:
    """Group the pieces of one event so the page shows it once.

    A policy decision arrives as a statement, a press conference and a set of
    projections. They are one thing to a reader.
    """

    for item in items:
        if item.cluster_id:
            continue
        anchor = item.scheduled_at or item.published_at or item.detected_at
        item.cluster_id = f"{item.category.value}_{anchor:%Y%m%d}"
    return items


def confirm(item: RadarItem, *, official_source: str, trust: SourceTrust) -> RadarItem:
    """Promote a detection once an authoritative source carries it too."""

    if official_source and official_source not in item.confirmed_by:
        item.confirmed_by.append(official_source)
    if _trust_rank(trust) < _trust_rank(item.trust):
        item.trust = trust
        item.source = official_source
    if item.status is RadarStatus.DETECTED:
        item.status = RadarStatus.CONFIRMED
    return item


def _trust_rank(trust: SourceTrust) -> int:
    return [
        SourceTrust.OFFICIAL,
        SourceTrust.PRIMARY_DATA,
        SourceTrust.REPUTABLE_NEWS,
        SourceTrust.SECONDARY,
        SourceTrust.SOCIAL,
    ].index(trust)


def home_items(items: list[RadarItem], *, now: datetime, limit: int = 5) -> list[RadarItem]:
    """The few things that count now, most pressing first."""

    live = [advance(item, now) for item in items]
    kept = [item for item in live if is_on_home(item)]
    kept.sort(
        key=lambda item: (
            -_ATTENTION_ORDER.index(item.attention),
            item.scheduled_at or item.published_at or item.detected_at,
        )
    )
    return kept[:limit]


# ---------------------------------------------------------------------------
# Bridge from the stored catalysts
# ---------------------------------------------------------------------------

_CATEGORY_BRIDGE = {
    "MONETARY_POLICY": RadarCategory.CENTRAL_BANK,
    "MACRO": RadarCategory.MACRO,
    "REGULATION": RadarCategory.REGULATION,
    "ETF": RadarCategory.ETF,
    "GEOPOLITICAL": RadarCategory.GEOPOLITICS,
    "ENERGY": RadarCategory.ENERGY,
    "SYSTEMIC_RISK": RadarCategory.FINANCIAL_RISK,
    "PROTOCOL": RadarCategory.CRYPTO_NATIVE,
    "ONCHAIN": RadarCategory.CRYPTO_NATIVE,
    "INSTITUTIONAL": RadarCategory.ETF,
    "OTHER": RadarCategory.OTHER,
}

#: The A-E ladder used by the event store, mapped onto how far a source may be
#: trusted. Tier E stays social: a lead, never an entry.
_TIER_BRIDGE = {
    "A": SourceTrust.OFFICIAL,
    "B": SourceTrust.PRIMARY_DATA,
    "C": SourceTrust.REPUTABLE_NEWS,
    "D": SourceTrust.SECONDARY,
    "E": SourceTrust.SOCIAL,
}


def radar_item_from_event(event: Any) -> RadarItem:
    """Adapt a stored catalyst to the radar without copying the store.

    Accepts anything exposing the catalyst attributes - the ORM row, the
    pydantic model, or a plain object in a test.
    """

    def read(name: str, default: Any = None) -> Any:
        value = getattr(event, name, default)
        return getattr(value, "value", value)

    detected_at = read("detected_at") or datetime.now(UTC)
    return RadarItem(
        event_id=str(read("canonical_event_id") or read("id") or read("event_type")),
        title=str(read("title") or ""),
        category=_CATEGORY_BRIDGE.get(
            str(read("category", "OTHER")), RadarCategory.OTHER
        ),
        trust=_TIER_BRIDGE.get(str(read("source_tier", "D")), SourceTrust.SECONDARY),
        source=str(read("source") or "inconnue"),
        detected_at=detected_at,
        scheduled_at=read("scheduled_at"),
        published_at=read("source_published_at"),
        source_url=read("source_url"),
        affected_assets=list(read("affected_assets") or []),
    )


def radar_summary(items: list[RadarItem], *, now: datetime) -> dict[str, Any]:
    """What the radar is holding, for the health report.

    Counts the one state that rots silently: an event whose moment has passed
    and whose result nobody ever read back.
    """

    live = [advance(item, now) for item in items]
    by_attention: dict[str, int] = {level.value: 0 for level in _ATTENTION_ORDER}
    for item in live:
        by_attention[item.attention.value] += 1

    return {
        "tracked": len(live),
        "on_home": sum(1 for item in live if is_on_home(item)),
        "expired": sum(1 for item in live if item.status is RadarStatus.EXPIRED),
        "unconfirmed": sum(1 for item in live if not item.is_confirmed),
        "awaiting_result": sum(
            1 for item in live if item.status is RadarStatus.RELEASED
        ),
        "by_attention": by_attention,
        "clusters": len({item.cluster_id for item in assign_clusters(live)}),
    }


def radar_fields(event: Any, *, now: datetime) -> dict[str, Any]:
    """The attention view of a catalyst, for payloads that already exist.

    Relevance ranks what to show. This says how closely to watch it and, kept
    strictly apart, whether a direction can be stated at all.
    """

    item = advance(radar_item_from_event(event), now)
    return {
        "attention": item.attention.value,
        "direction": item.direction.value,
        "radar_status": item.status.value,
        "confirmed": item.is_confirmed,
        "attention_note": (
            "Le niveau d'attention dit à quel point surveiller. Il ne dit pas "
            "dans quel sens le marché ira: la direction n'est connue qu'une "
            "fois le résultat comparé aux attentes."
        ),
    }

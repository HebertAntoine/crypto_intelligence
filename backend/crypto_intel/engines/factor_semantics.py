"""What one factor says, how much it can matter, and which way it is moving.

Four properties are computed separately and never collapsed into one another:

* **direction** — which way the factor pushes, if it pushes at all;
* **impact** — how much it could matter on the selected horizon if it plays out;
* **trend** — whether the reading is strengthening, holding or decaying;
* **confidence** — how well the engine could measure it.

The distinction that matters most is ``NEUTRAL`` versus ``UNKNOWN``. NEUTRAL is
a measurement: the data was read and shows no bias. UNKNOWN is an admission: the
outcome has not happened yet, or the instrument cannot speak about direction at
all. A scheduled FOMC is UNKNOWN, not NEUTRAL; funding sitting at its usual
level is NEUTRAL, not UNKNOWN. Collapsing the two lets an unmeasured thing pass
for a balanced one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class FactorDirection(StrEnum):
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    NEUTRAL = "NEUTRAL"
    UNKNOWN = "UNKNOWN"


class FactorTrend(StrEnum):
    IMPROVING = "IMPROVING"
    STABLE = "STABLE"
    DETERIORATING = "DETERIORATING"
    REVERSING = "REVERSING"
    UNKNOWN = "UNKNOWN"


class FactorImpact(StrEnum):
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"


class Availability(StrEnum):
    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"
    STALE = "STALE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class ConfidenceLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


#: Freshness labels the engines already publish, mapped to availability. A stale
#: reading is not an available one: it is data that was true at some point.
_STALE_FRESHNESS = {"STALE", "DELAYED", "AGING"}


def availability_for(freshness: str | None, *, measured: bool) -> Availability:
    if not measured:
        return Availability.UNAVAILABLE
    label = (freshness or "").upper()
    if label in _STALE_FRESHNESS:
        return Availability.STALE
    if label in {"", "UNAVAILABLE"}:
        return Availability.PARTIAL
    return Availability.AVAILABLE


def confidence_level(value: float, availability: Availability) -> ConfidenceLevel:
    """Stale evidence can never be high confidence, whatever the score says."""

    if availability in {Availability.UNAVAILABLE, Availability.NOT_APPLICABLE}:
        return ConfidenceLevel.LOW
    if availability is Availability.STALE:
        return ConfidenceLevel.MEDIUM if value >= 0.6 else ConfidenceLevel.LOW
    if value >= 0.75:
        return ConfidenceLevel.HIGH
    if value >= 0.4:
        return ConfidenceLevel.MEDIUM
    return ConfidenceLevel.LOW


@dataclass(slots=True, frozen=True)
class FactorAssessment:
    key: str
    label: str
    direction: FactorDirection
    impact: FactorImpact
    trend: FactorTrend = FactorTrend.UNKNOWN
    confidence: float = 0.0
    freshness: str = "UNAVAILABLE"
    rationale: str = ""
    evidence_ids: list[str] = field(default_factory=list)

    #: Some instruments speak about amplitude only. Bollinger compression says a
    #: move may be large; it never says which way. Kept separate from ``impact``
    #: so a direction-free reading cannot be read as a directional one.
    impact_on_direction: str = "MEASURED"

    #: Raw data -> observation -> interpretation -> market mechanism. Each link
    #: is a sentence a reader can follow; an empty chain means the factor has no
    #: explanation and must not be presented as a reason.
    causal_chain: list[str] = field(default_factory=list)

    #: What the engine would need to conclude, when it cannot. Never empty on an
    #: UNAVAILABLE or PARTIAL factor: an absence is stated, never left blank.
    missing_requirements: list[str] = field(default_factory=list)

    #: The real upstream provider, not the family label.
    provider: str = ""
    source_url: str | None = None
    availability: Availability = Availability.AVAILABLE

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> FactorAssessment:
        """Rebuild a reading from its published form.

        The synthesis consumes exactly what the API publishes, so a field that
        never reaches the payload cannot silently influence the verdict.
        """

        return cls(
            key=str(payload.get("key") or ""),
            label=str(payload.get("label") or ""),
            direction=FactorDirection(payload.get("direction") or "UNKNOWN"),
            impact=FactorImpact(payload.get("impact") or "MODERATE"),
            trend=FactorTrend(payload.get("trend") or "UNKNOWN"),
            confidence=float(payload.get("confidence") or 0.0),
            freshness=str(payload.get("freshness") or "UNAVAILABLE"),
            rationale=str(payload.get("rationale") or ""),
            evidence_ids=list(payload.get("evidence_ids") or []),
            impact_on_direction=str(payload.get("impact_on_direction") or "MEASURED"),
            causal_chain=list(payload.get("causal_chain") or []),
            missing_requirements=list(payload.get("missing_requirements") or []),
            provider=str(payload.get("provider") or ""),
            source_url=payload.get("source_url"),
            availability=Availability(payload.get("availability") or "AVAILABLE"),
        )

    @property
    def confidence_band(self) -> ConfidenceLevel:
        return confidence_level(self.confidence, self.availability)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "direction": self.direction.value,
            "impact": self.impact.value,
            "trend": self.trend.value,
            "confidence": round(self.confidence, 3),
            "freshness": self.freshness,
            "rationale": self.rationale,
            "evidence_ids": self.evidence_ids,
            "impact_on_direction": self.impact_on_direction,
            "causal_chain": self.causal_chain,
            "missing_requirements": self.missing_requirements,
            "provider": self.provider,
            "source_url": self.source_url,
            "availability": self.availability.value,
            "confidence_band": self.confidence_band.value,
        }


# ---------------------------------------------------------------------------
# Institutional flows
# ---------------------------------------------------------------------------


def flow_assessment(flow: Any, *, label: str = "Flux institutionnels") -> FactorAssessment:
    """Separate where the flows stand from where they are heading.

    A twenty-session regime can be firmly positive while the last sessions have
    already turned. Reporting only the regime published "POSITIF" next to a
    negative recent total; reporting only the recent window would throw away a
    month of steady buying. Both are published: direction from the regime,
    trend from the short window.
    """

    regime = getattr(flow, "regime_total_musd", None)
    recent = getattr(flow, "rolling_5_sessions_musd", None)
    sessions = int(getattr(flow, "regime_sessions", 0) or 0)
    freshness = str(getattr(flow, "freshness", "UNAVAILABLE") or "UNAVAILABLE")

    if regime is None:
        return FactorAssessment(
            key="flows",
            label=label,
            direction=FactorDirection.UNKNOWN,
            impact=FactorImpact.MODERATE,
            trend=FactorTrend.UNKNOWN,
            availability=Availability.UNAVAILABLE,
            freshness=freshness,
            missing_requirements=[
                "Série de flux ETF quotidiens sur au moins trois séances."
            ],
            rationale="Aucune série de flux exploitable.",
        )

    direction = (
        FactorDirection.POSITIVE
        if regime > 0
        else FactorDirection.NEGATIVE
        if regime < 0
        else FactorDirection.NEUTRAL
    )

    reversal = str(getattr(flow, "flow_reversal", "") or "")
    if reversal == "INFLOW_TO_OUTFLOW":
        trend = FactorTrend.DETERIORATING if regime > 0 else FactorTrend.STABLE
    elif reversal == "OUTFLOW_TO_INFLOW":
        trend = FactorTrend.IMPROVING if regime < 0 else FactorTrend.STABLE
    elif recent is None:
        trend = FactorTrend.UNKNOWN
    elif regime > 0 and recent < 0:
        trend = FactorTrend.DETERIORATING
    elif regime < 0 and recent > 0:
        trend = FactorTrend.IMPROVING
    else:
        trend = FactorTrend.STABLE

    # A regime contradicted by its own recent window is not a strong signal.
    impact = (
        FactorImpact.MODERATE
        if trend in {FactorTrend.DETERIORATING, FactorTrend.IMPROVING}
        else FactorImpact.HIGH
        if abs(regime) >= 1000
        else FactorImpact.MODERATE
    )

    parts = [f"{sessions} séances: {regime:+,.1f} M$".replace(",", " ")]
    if recent is not None:
        parts.append(f"5 dernières séances: {recent:+,.1f} M$".replace(",", " "))

    observation = {
        (FactorDirection.POSITIVE, FactorTrend.DETERIORATING): (
            f"Les flux restent positifs sur {sessions} séances, mais la "
            "dynamique récente s'est retournée."
        ),
        (FactorDirection.NEGATIVE, FactorTrend.IMPROVING): (
            f"Les flux restent négatifs sur {sessions} séances, mais les "
            "dernières séances repassent en territoire positif."
        ),
    }.get(
        (direction, trend),
        {
            FactorDirection.POSITIVE: f"Entrées nettes soutenues sur {sessions} séances.",
            FactorDirection.NEGATIVE: f"Sorties nettes soutenues sur {sessions} séances.",
        }.get(direction, f"Flux équilibrés sur {sessions} séances."),
    )

    # Strictly ETF vocabulary: supply and demand through the funds. Transfers to
    # exchanges belong to on-chain whale data and must not appear here.
    mechanism = (
        "Les ETF au comptant constituent une source de demande ou d'offre "
        "nette. Des entrées persistantes apportent du soutien; des sorties "
        "persistantes réduisent ce soutien et peuvent accroître la pression "
        "vendeuse."
    )

    provider = ""
    source_url = None
    for item in getattr(flow, "provenance", []) or []:
        provider = str(item.get("provider") or item.get("source") or "")
        source_url = item.get("source_url")
        if provider:
            break

    return FactorAssessment(
        key="flows",
        label=label,
        direction=direction,
        impact=impact,
        trend=trend,
        confidence=min(0.9, float(getattr(flow, "sessions_available", 0) or 0) / 20),
        availability=availability_for(freshness, measured=True),
        freshness=freshness,
        provider=provider,
        source_url=source_url,
        rationale="; ".join(parts),
        causal_chain=["; ".join(parts) + ".", observation, mechanism],
        evidence_ids=list(getattr(flow, "evidence_ids", []) or [])[:8],
    )


# ---------------------------------------------------------------------------
# Positioning and leverage
# ---------------------------------------------------------------------------

#: Price and open interest read together. Open interest alone cannot say who is
#: leaving: the same fall means longs closing in a downtrend and shorts covering
#: in an uptrend, which are opposite signals.
_POSITIONING_QUADRANTS = {
    (False, False): (
        FactorDirection.NEGATIVE,
        "Le prix recule pendant que les positions à levier se ferment: "
        "des acheteurs abandonnent, ce qui confirme la faiblesse à court terme.",
    ),
    (True, False): (
        FactorDirection.NEUTRAL,
        "Le prix monte pendant que les positions à levier se ferment: "
        "il peut s'agir de vendeurs à découvert qui se rachètent, ce qui "
        "n'indique pas une faiblesse.",
    ),
    (False, True): (
        FactorDirection.NEGATIVE,
        "Le prix recule pendant que les positions à levier augmentent: "
        "de nouvelles positions vendeuses se constituent.",
    ),
    (True, True): (
        FactorDirection.POSITIVE,
        "Le prix monte pendant que les positions à levier augmentent: "
        "de nouveaux acheteurs participent au mouvement.",
    ),
}


def positioning_assessment(
    *,
    price_change_pct: float | None,
    oi_change_pct: float | None,
    funding_state: str | None = None,
    basis_pct: float | None = None,
    freshness: str = "UNAVAILABLE",
    label: str = "Positionnement & dérivés",
) -> FactorAssessment:
    """Read price and open interest together, never open interest alone."""

    if price_change_pct is None or oi_change_pct is None:
        return FactorAssessment(
            key="positioning",
            label=label,
            direction=FactorDirection.UNKNOWN,
            impact=FactorImpact.MODERATE,
            freshness=freshness,
            rationale="Variation de prix ou d'intérêt ouvert indisponible.",
        )

    direction, rationale = _POSITIONING_QUADRANTS[
        (price_change_pct >= 0, oi_change_pct >= 0)
    ]

    state = (funding_state or "").upper()
    if state in {"EXTREME_POSITIVE", "EXTREME_NEGATIVE"}:
        impact = FactorImpact.HIGH
        rationale += " Le coût du levier est extrême, ce qui rend un dénouement plus brutal."
    elif abs(oi_change_pct) >= 5:
        impact = FactorImpact.HIGH
    else:
        impact = FactorImpact.MODERATE

    trend = (
        FactorTrend.DETERIORATING
        if direction is FactorDirection.NEGATIVE and abs(oi_change_pct) >= 2
        else FactorTrend.IMPROVING
        if direction is FactorDirection.POSITIVE and abs(oi_change_pct) >= 2
        else FactorTrend.STABLE
    )
    detail = (
        f"prix {price_change_pct:+.2f}%, intérêt ouvert {oi_change_pct:+.2f}%"
        + (f", écart au comptant {basis_pct:+.2f}%" if basis_pct is not None else "")
    )
    return FactorAssessment(
        key="positioning",
        label=label,
        direction=direction,
        impact=impact,
        trend=trend,
        confidence=0.8,
        freshness=freshness,
        rationale=f"{rationale} ({detail})",
    )


#: The pressure engine already classifies price and open interest jointly. Its
#: labels are reused rather than recomputed, so thresholds stay in one place.
_LEVERAGE_STATES = {
    "NEW_LONGS": (
        FactorDirection.POSITIVE,
        FactorTrend.IMPROVING,
        "Le prix monte pendant que les positions à levier augmentent: "
        "de nouveaux acheteurs participent au mouvement.",
    ),
    "NEW_SHORTS": (
        FactorDirection.NEGATIVE,
        FactorTrend.DETERIORATING,
        "Le prix recule pendant que les positions à levier augmentent: "
        "de nouvelles positions vendeuses se constituent.",
    ),
    "SHORT_COVERING": (
        FactorDirection.NEUTRAL,
        FactorTrend.IMPROVING,
        "Le prix monte pendant que les positions à levier se ferment: "
        "des vendeurs à découvert se rachètent, ce qui ne confirme pas "
        "une tendance acheteuse.",
    ),
    "LONG_LIQUIDATION": (
        FactorDirection.NEGATIVE,
        FactorTrend.DETERIORATING,
        "Le prix recule pendant que les positions à levier se ferment: "
        "des acheteurs abandonnent, ce qui confirme la faiblesse à court terme.",
    ),
    "DELEVERAGING": (
        FactorDirection.NEUTRAL,
        FactorTrend.STABLE,
        "Le levier se réduit sans côté dominant.",
    ),
    "QUIET": (
        FactorDirection.NEUTRAL,
        FactorTrend.STABLE,
        "Aucun changement de positionnement marqué.",
    ),
    "BALANCED": (
        FactorDirection.NEUTRAL,
        FactorTrend.STABLE,
        "Les composantes mesurées se compensent.",
    ),
}


def positioning_from_leverage_state(
    state: str | None,
    *,
    funding_state: str | None = None,
    freshness: str = "UNAVAILABLE",
    confidence: float = 0.8,
    label: str = "Positionnement & dérivés",
    provider: str = "",
    source_url: str | None = None,
) -> FactorAssessment:
    """Normalise the pressure engine's joint price/open-interest label.

    Short covering is deliberately NEUTRAL rather than positive: buyers are not
    stepping in, sellers are stepping out, and reading that as a bullish
    confirmation is the mistake section 7 asks to avoid.
    """

    entry = _LEVERAGE_STATES.get((state or "").upper())
    if entry is None:
        return FactorAssessment(
            key="positioning",
            label=label,
            direction=FactorDirection.UNKNOWN,
            impact=FactorImpact.MODERATE,
            availability=Availability.UNAVAILABLE,
            freshness=freshness,
            provider=provider,
            source_url=source_url,
            missing_requirements=[
                "Variation de prix et d'intérêt ouvert sur la même fenêtre."
            ],
            rationale=f"État de positionnement « {state or 'inconnu'} » non interprétable.",
        )
    direction, trend, rationale = entry
    extreme = (funding_state or "").upper() in {"EXTREME_POSITIVE", "EXTREME_NEGATIVE"}
    if extreme:
        rationale += " Le coût du levier est extrême, ce qui rend un dénouement plus brutal."
    return FactorAssessment(
        key="positioning",
        label=label,
        direction=direction,
        impact=FactorImpact.HIGH if extreme else FactorImpact.MODERATE,
        trend=trend,
        confidence=confidence,
        availability=availability_for(freshness, measured=True),
        freshness=freshness,
        provider=provider,
        source_url=source_url,
        rationale=rationale,
        causal_chain=[
            f"État de positionnement mesuré: {(state or '').upper()}.",
            rationale,
            "Le positionnement à levier amplifie les mouvements: un dénouement "
            "force des ordres dans le sens du mouvement en cours.",
        ],
    )


# ---------------------------------------------------------------------------
# Technical structure
# ---------------------------------------------------------------------------


def technical_assessment(
    *,
    bullish_timeframes: list[str],
    bearish_timeframes: list[str],
    structure_confirmed: bool = False,
    volume_confirms: bool = False,
    breakout_valid: bool = False,
    freshness: str = "UNAVAILABLE",
    label: str = "Technique & volatilité",
) -> FactorAssessment:
    """Impact follows convergent evidence, never the raw count of timeframes.

    Counting units alone rated one agreeing timeframe as high impact, and, when
    no timeframe agreed at all, a regime label still produced a direction with
    zero confidence. Direction now requires at least one timeframe to actually
    point somewhere.
    """

    bullish, bearish = len(bullish_timeframes), len(bearish_timeframes)
    if bullish == 0 and bearish == 0:
        return FactorAssessment(
            key="technical",
            label=label,
            direction=FactorDirection.UNKNOWN,
            impact=FactorImpact.LOW,
            trend=FactorTrend.UNKNOWN,
            confidence=0.0,
            availability=Availability.PARTIAL,
            freshness=freshness,
            provider="Séries de bougies internes",
            missing_requirements=[
                "Au moins une échelle de temps avec une structure exploitable."
            ],
            rationale="Aucune échelle de temps ne donne de direction exploitable.",
            causal_chain=[
                "Aucune échelle de temps ne présente de structure exploitable.",
                "Le sens ne peut pas être déduit d'un simple label de régime.",
                "Sans structure lisible, la technique n'apporte pas de direction.",
            ],
        )

    net = bullish - bearish
    direction = (
        FactorDirection.POSITIVE
        if net > 0
        else FactorDirection.NEGATIVE
        if net < 0
        else FactorDirection.NEUTRAL
    )

    # Independent confirmations: agreeing timeframes beyond the first, plus each
    # qualitative confirmation. One timeframe on its own is a single reading.
    confirmations = max(0, abs(net) - 1)
    confirmations += sum((structure_confirmed, volume_confirms, breakout_valid))
    conflicted = bullish > 0 and bearish > 0

    if direction is FactorDirection.NEUTRAL or (conflicted and confirmations == 0):
        impact = FactorImpact.LOW
    elif confirmations == 0:
        impact = FactorImpact.MODERATE
    elif confirmations >= 3:
        impact = FactorImpact.VERY_HIGH
    else:
        impact = FactorImpact.HIGH

    detail = f"{bullish} échelle(s) haussière(s) contre {bearish}"
    extras = [
        name
        for name, present in (
            ("structure confirmée", structure_confirmed),
            ("volume confirmant", volume_confirms),
            ("cassure valide", breakout_valid),
        )
        if present
    ]
    if extras:
        detail += "; " + ", ".join(extras)
    return FactorAssessment(
        key="technical",
        label=label,
        direction=direction,
        impact=impact,
        trend=FactorTrend.STABLE if not conflicted else FactorTrend.UNKNOWN,
        confidence=min(0.9, (bullish + bearish) / 4),
        availability=availability_for(freshness, measured=True),
        freshness=freshness,
        provider="Séries de bougies internes",
        rationale=detail,
        causal_chain=[
            detail + ".",
            (
                "Les échelles de temps se contredisent."
                if conflicted
                else f"{confirmations + 1} lecture(s) concordante(s)."
            ),
            "Une structure confirmée sur plusieurs échelles rend la lecture "
            "plus fiable qu'une seule unité de temps.",
        ],
    )


# ---------------------------------------------------------------------------
# Volatility compression
# ---------------------------------------------------------------------------


def volatility_assessment(
    *,
    squeeze: bool,
    freshness: str = "UNAVAILABLE",
    label: str = "Volatilité",
) -> FactorAssessment:
    """Compression speaks about size only. It never picks a side."""

    return FactorAssessment(
        key="volatility",
        label=label,
        direction=FactorDirection.UNKNOWN,
        impact=FactorImpact.HIGH if squeeze else FactorImpact.LOW,
        trend=FactorTrend.UNKNOWN,
        confidence=0.6 if squeeze else 0.3,
        freshness=freshness,
        impact_on_direction="NONE",
        availability=availability_for(freshness, measured=True),
        provider="Séries de bougies internes",
        rationale=(
            "Les bandes de Bollinger sont resserrées: un mouvement important "
            "est possible, sans indication de sens."
            if squeeze
            else "Pas de compression marquée."
        ),
        causal_chain=[
            (
                "Largeur des bandes de Bollinger dans le bas de son historique."
                if squeeze
                else "Largeur des bandes dans sa zone habituelle."
            ),
            (
                "Le marché se comprime."
                if squeeze
                else "Aucune compression marquée."
            ),
            "Une phase de faible volatilité précède parfois un mouvement de "
            "forte amplitude, dont le sens n'est pas déterminé par la compression.",
        ],
    )


# ---------------------------------------------------------------------------
# Scheduled events
# ---------------------------------------------------------------------------

_EVENT_IMPACT = {
    "CRITICAL": FactorImpact.VERY_HIGH,
    "HIGH": FactorImpact.HIGH,
    "MEDIUM": FactorImpact.MODERATE,
    "LOW": FactorImpact.LOW,
}


def event_assessment(
    *,
    title: str,
    importance: str,
    priced_direction: FactorDirection | None = None,
    freshness: str = "RECENT",
    evidence_ids: list[str] | None = None,
    provider: str = "",
    source_url: str | None = None,
) -> FactorAssessment:
    """An unpublished event has no direction until the market prices one.

    Deriving direction from the event *type* is what produces "FOMC therefore
    bearish". Until a timestamped market distribution exists, the honest answer
    is UNKNOWN — which is compatible with a very high impact.
    """

    return FactorAssessment(
        key="event",
        label=title,
        direction=priced_direction or FactorDirection.UNKNOWN,
        impact=_EVENT_IMPACT.get(importance.upper(), FactorImpact.MODERATE),
        trend=FactorTrend.UNKNOWN,
        confidence=0.0 if priced_direction is None else 0.6,
        freshness=freshness,
        rationale=(
            "Issue non publiée et non valorisée par le marché."
            if priced_direction is None
            else "Direction déduite d'une distribution de marché horodatée."
        ),
        provider=provider,
        source_url=source_url,
        availability=(
            Availability.PARTIAL if priced_direction is None else Availability.AVAILABLE
        ),
        missing_requirements=(
            ["Distribution de probabilités de marché horodatée pour cet événement."]
            if priced_direction is None
            else []
        ),
        causal_chain=[
            f"Événement programmé: {title} (importance {importance.upper()}).",
            (
                "Son issue n'est pas connue et aucune valorisation de marché "
                "n'est disponible."
                if priced_direction is None
                else "Le marché valorise une issue dominante."
            ),
            "Ce qui déplace le prix est l'écart entre l'issue et ce qui était "
            "déjà valorisé, pas l'événement lui-même.",
        ],
        evidence_ids=list(evidence_ids or []),
    )


# ---------------------------------------------------------------------------
# Funding
# ---------------------------------------------------------------------------


def funding_assessment(
    *,
    percentile: float | None,
    freshness: str = "UNAVAILABLE",
    label: str = "Coût du levier",
    provider: str = "",
    source_url: str | None = None,
) -> FactorAssessment:
    """Read funding against its own history, never as a raw number.

    Crowding is the measurement; direction is an inference on top of it, and a
    contrarian one. Very negative funding means shorts are paying, which is a
    setup, not a buy signal: it usually accompanies a weak market. The two are
    reported separately rather than collapsed into "cheap therefore bullish".
    """

    availability = availability_for(freshness, measured=percentile is not None)
    if percentile is None:
        return FactorAssessment(
            key="funding",
            label=label,
            direction=FactorDirection.UNKNOWN,
            impact=FactorImpact.LOW,
            availability=availability,
            freshness=freshness,
            provider=provider,
            source_url=source_url,
            missing_requirements=["Série de funding et son historique glissant."],
            rationale="Coût du levier indisponible.",
        )

    if percentile >= 95:
        direction, impact = FactorDirection.NEGATIVE, FactorImpact.HIGH
        observation = "Le coût pour rester acheteur est parmi les plus élevés de son historique."
        mechanism = (
            "Beaucoup d'acheteurs à levier paient cher: un repli peut les "
            "contraindre à sortir et amplifier la baisse."
        )
    elif percentile <= 5:
        direction, impact = FactorDirection.NEUTRAL, FactorImpact.MODERATE
        observation = "Le coût pour rester acheteur est parmi les plus bas de son historique."
        mechanism = (
            "Ce sont les vendeurs qui paient. Cela accompagne le plus souvent "
            "un marché faible, et ne constitue pas en soi un signal d'achat."
        )
    else:
        direction, impact = FactorDirection.NEUTRAL, FactorImpact.LOW
        observation = "Le coût du levier est proche de sa normale historique."
        mechanism = "Aucun déséquilibre de positionnement n'est mesuré."

    return FactorAssessment(
        key="funding",
        label=label,
        direction=direction,
        impact=impact,
        trend=FactorTrend.UNKNOWN,
        confidence=0.7,
        availability=availability,
        freshness=freshness,
        provider=provider,
        source_url=source_url,
        rationale=observation,
        causal_chain=[
            f"Funding au niveau {percentile:.0f} sur 100 de son historique.",
            observation,
            mechanism,
        ],
    )


# ---------------------------------------------------------------------------
# Basis
# ---------------------------------------------------------------------------


def basis_assessment(
    *,
    basis_pct: float | None,
    percentile: float | None = None,
    freshness: str = "UNAVAILABLE",
    label: str = "Écart contrats / comptant",
    provider: str = "",
    source_url: str | None = None,
) -> FactorAssessment:
    """A positive basis is normal, not bullish.

    Contracts trading above spot is the ordinary state of a carry market. Only
    an unusual level relative to its own history carries information, and even
    then it describes appetite for leverage rather than a direction.
    """

    availability = availability_for(freshness, measured=basis_pct is not None)
    if basis_pct is None:
        return FactorAssessment(
            key="basis",
            label=label,
            direction=FactorDirection.UNKNOWN,
            impact=FactorImpact.LOW,
            availability=availability,
            freshness=freshness,
            provider=provider,
            source_url=source_url,
            missing_requirements=["Écart contrats/comptant et son historique."],
            rationale="Écart contrats/comptant indisponible.",
        )

    if percentile is None:
        return FactorAssessment(
            key="basis",
            label=label,
            direction=FactorDirection.NEUTRAL,
            impact=FactorImpact.LOW,
            confidence=0.35,
            availability=Availability.PARTIAL,
            freshness=freshness,
            provider=provider,
            source_url=source_url,
            missing_requirements=["Historique de l'écart, pour situer le niveau actuel."],
            rationale=(
                f"Écart de {basis_pct:+.2f}%, sans historique pour dire si ce "
                "niveau est inhabituel."
            ),
            causal_chain=[
                f"Écart contrats/comptant: {basis_pct:+.2f}%.",
                "Un écart positif est l'état normal d'un marché à terme.",
                "Sans historique, aucun déséquilibre ne peut être affirmé.",
            ],
        )

    if percentile >= 90:
        direction, impact = FactorDirection.NEGATIVE, FactorImpact.MODERATE
        mechanism = (
            "Payer très cher pour être exposé à terme signale un excès "
            "d'appétit pour le levier, vulnérable à un dénouement."
        )
    elif percentile <= 10:
        direction, impact = FactorDirection.NEUTRAL, FactorImpact.LOW
        mechanism = "L'appétit pour le levier est inhabituellement faible."
    else:
        direction, impact = FactorDirection.NEUTRAL, FactorImpact.LOW
        mechanism = "L'écart se situe dans sa zone habituelle."

    return FactorAssessment(
        key="basis",
        label=label,
        direction=direction,
        impact=impact,
        confidence=0.6,
        availability=availability,
        freshness=freshness,
        provider=provider,
        source_url=source_url,
        rationale=f"Écart de {basis_pct:+.2f}%, niveau {percentile:.0f} sur 100.",
        causal_chain=[
            f"Écart contrats/comptant: {basis_pct:+.2f}% (niveau {percentile:.0f}/100).",
            "Un écart positif est l'état normal d'un marché à terme.",
            mechanism,
        ],
    )


# ---------------------------------------------------------------------------
# Implied volatility
# ---------------------------------------------------------------------------


def implied_volatility_assessment(
    *,
    available: bool,
    percentile: float | None = None,
    skew: float | None = None,
    freshness: str = "UNAVAILABLE",
    label: str = "Volatilité implicite",
    provider: str = "",
    source_url: str | None = None,
) -> FactorAssessment:
    """Implied volatility sizes the move; only skew can lean a direction.

    Keeping them apart is the whole point: a high implied volatility says the
    options market expects a large move, and says nothing about which way.
    """

    availability = availability_for(freshness, measured=available)
    if not available:
        return FactorAssessment(
            key="implied_volatility",
            label=label,
            direction=FactorDirection.UNKNOWN,
            impact=FactorImpact.LOW,
            availability=availability,
            freshness=freshness,
            provider=provider,
            source_url=source_url,
            missing_requirements=["Série de volatilité implicite pour cet actif."],
            rationale="Lecture des options indisponible pour cet actif.",
            impact_on_direction="NONE",
        )

    impact = (
        FactorImpact.HIGH
        if percentile is not None and percentile >= 70
        else FactorImpact.MODERATE
    )
    if skew is None:
        direction = FactorDirection.UNKNOWN
        directional = "NONE"
        mechanism = (
            "La volatilité implicite mesure l'ampleur attendue, jamais le sens. "
            "Sans asymétrie d'options disponible, aucune direction ne peut être lue."
        )
    else:
        direction = (
            FactorDirection.NEGATIVE
            if skew < -0.02
            else FactorDirection.POSITIVE
            if skew > 0.02
            else FactorDirection.NEUTRAL
        )
        directional = "MEASURED"
        mechanism = (
            "L'asymétrie des options indique de quel côté la protection est la "
            "plus demandée, ce qui porte une information de sens."
        )

    return FactorAssessment(
        key="implied_volatility",
        label=label,
        direction=direction,
        impact=impact,
        confidence=0.6,
        availability=availability,
        freshness=freshness,
        provider=provider,
        source_url=source_url,
        impact_on_direction=directional,
        rationale=(
            "Le marché des options anticipe un mouvement "
            + ("important." if impact is FactorImpact.HIGH else "ordinaire.")
        ),
        causal_chain=[
            (
                f"Volatilité implicite au niveau {percentile:.0f} sur 100."
                if percentile is not None
                else "Volatilité implicite mesurée."
            ),
            "Elle décrit l'ampleur attendue du mouvement.",
            mechanism,
        ],
    )


# ---------------------------------------------------------------------------
# Whales / on-chain
# ---------------------------------------------------------------------------


def whale_assessment(
    *,
    available: bool,
    transfers_to_exchange: int | None = None,
    corroborating_signals: list[str] | None = None,
    freshness: str = "UNAVAILABLE",
    label: str = "Mouvements de baleines",
    provider: str = "",
    source_url: str | None = None,
) -> FactorAssessment:
    """A transfer is a movement, not a sale.

    Coins reaching an exchange only *can* be sold. Reading the transfer itself
    as selling pressure is the inference this refuses to make: a direction
    requires corroboration, and without it the honest answer is UNKNOWN.
    """

    availability = availability_for(freshness, measured=available)
    if not available:
        return FactorAssessment(
            key="whales",
            label=label,
            direction=FactorDirection.UNKNOWN,
            impact=FactorImpact.LOW,
            availability=Availability.UNAVAILABLE,
            freshness=freshness,
            provider=provider,
            source_url=source_url,
            missing_requirements=[
                "Flux de transferts attribués depuis un fournisseur on-chain."
            ],
            rationale="Données baleines indisponibles.",
        )

    corroboration = list(corroborating_signals or [])
    if not corroboration:
        return FactorAssessment(
            key="whales",
            label=label,
            direction=FactorDirection.UNKNOWN,
            impact=FactorImpact.MODERATE,
            confidence=0.3,
            availability=Availability.PARTIAL,
            freshness=freshness,
            provider=provider,
            source_url=source_url,
            missing_requirements=[
                "Un signal corroborant: entrées nettes sur les plateformes, "
                "prime Coinbase, ou réaction du prix."
            ],
            rationale=(
                f"{transfers_to_exchange or 0} transfert(s) vers des plateformes "
                "d'échange, sans confirmation d'une vente."
            ),
            causal_chain=[
                f"{transfers_to_exchange or 0} transfert(s) vers des plateformes.",
                "Des jetons déposés sur une plateforme peuvent être vendus.",
                "Un transfert ne signifie pas qu'une vente a lieu: sans signal "
                "corroborant, le sens reste inconnu.",
            ],
        )

    return FactorAssessment(
        key="whales",
        label=label,
        direction=FactorDirection.NEGATIVE,
        impact=FactorImpact.MODERATE,
        confidence=0.55,
        availability=availability,
        freshness=freshness,
        provider=provider,
        source_url=source_url,
        rationale=(
            f"{transfers_to_exchange or 0} transfert(s) vers des plateformes, "
            f"corroborés par: {', '.join(corroboration)}."
        ),
        causal_chain=[
            f"{transfers_to_exchange or 0} transfert(s) vers des plateformes.",
            f"Confirmé par: {', '.join(corroboration)}.",
            "L'offre disponible à la vente augmente, ce qui peut peser sur le prix.",
        ],
    )


# ---------------------------------------------------------------------------
# Existing pressure components
# ---------------------------------------------------------------------------

_COMPONENT_MECHANISM = {
    "funding": (
        "Le coût pour rester positionné révèle quel côté du marché paie. Un "
        "déséquilibre marqué rend un dénouement plus probable, sans dire "
        "quand il aura lieu."
    ),
    "derivatives": (
        "Le positionnement à levier amplifie les mouvements: un dénouement "
        "force des ordres dans le sens du mouvement en cours."
    ),
    "spot": (
        "Le déséquilibre entre acheteurs et vendeurs au comptant décrit qui "
        "accepte de payer le prix demandé maintenant."
    ),
    "whales": (
        "Des mouvements de gros portefeuilles modifient l'offre disponible, "
        "sans qu'un transfert constitue à lui seul une vente."
    ),
}

#: The pressure engine names its directions from the trader's side (BUY/SELL);
#: the interpretation layer names them from the asset's (POSITIVE/NEGATIVE).
#: Mapping only the bias vocabulary left every pressure component UNKNOWN while
#: it was in fact measured, which hid the very reading a decision rested on.
_COMPONENT_DIRECTION = {
    "STRONG_BUY": FactorDirection.POSITIVE,
    "BUY": FactorDirection.POSITIVE,
    "SLIGHT_BUY": FactorDirection.POSITIVE,
    "NEUTRAL": FactorDirection.NEUTRAL,
    "SLIGHT_SELL": FactorDirection.NEGATIVE,
    "SELL": FactorDirection.NEGATIVE,
    "STRONG_SELL": FactorDirection.NEGATIVE,
    # Bias vocabulary, for components that publish it instead.
    "BULLISH": FactorDirection.POSITIVE,
    "STRONGLY_BULLISH": FactorDirection.POSITIVE,
    "BEARISH": FactorDirection.NEGATIVE,
    "STRONGLY_BEARISH": FactorDirection.NEGATIVE,
}


def pressure_component_assessment(component: Any) -> FactorAssessment:
    """Normalise a measurement an engine already made, without redoing it.

    The interpretation layer exists to give every reading the same shape, not to
    recompute it with a second set of thresholds. Direction and score are taken
    as the pressure engine produced them; what is added here is availability,
    the provider, and a causal chain the reader can follow.
    """

    key = str(getattr(component, "family", "") or "unknown")
    raw_direction = str(getattr(component, "direction", "") or "").upper()
    available = bool(getattr(component, "available", False))
    freshness = str(getattr(component, "freshness", "UNAVAILABLE") or "UNAVAILABLE")
    availability = availability_for(freshness, measured=available)
    detail = str(getattr(component, "detail", "") or getattr(component, "reason", "") or "")
    explanation = str(getattr(component, "explanation", "") or "")
    score = getattr(component, "normalized_score", None)

    if not available or raw_direction in {"", "UNAVAILABLE"}:
        return FactorAssessment(
            key=key,
            label=str(getattr(component, "label", key) or key),
            direction=FactorDirection.UNKNOWN,
            impact=FactorImpact.LOW,
            availability=Availability.UNAVAILABLE,
            freshness=freshness,
            provider=str(getattr(component, "source", "") or ""),
            missing_requirements=[
                detail or "Mesure indisponible pour cette composante."
            ],
            rationale=detail or "Composante indisponible.",
        )

    direction = _COMPONENT_DIRECTION.get(raw_direction, FactorDirection.UNKNOWN)
    magnitude = abs(float(score)) if score is not None else 0.0
    impact = (
        FactorImpact.HIGH
        if magnitude >= 55
        else FactorImpact.MODERATE
        if magnitude >= 12
        else FactorImpact.LOW
    )
    return FactorAssessment(
        key=key,
        label=str(getattr(component, "label", key) or key),
        direction=direction,
        impact=impact,
        trend=FactorTrend.UNKNOWN,
        confidence=float(getattr(component, "confidence", 0.5) or 0.5),
        availability=availability,
        freshness=freshness,
        provider=str(getattr(component, "source", "") or ""),
        rationale=detail or explanation,
        causal_chain=[
            (
                f"Mesure normalisée: {score:+.0f} sur 100."
                if score is not None
                else "Mesure disponible."
            ),
            detail or explanation or "Lecture mesurée.",
            _COMPONENT_MECHANISM.get(key, "Cette composante pèse sur l'équilibre du marché."),
        ],
    )


def whale_flow_assessment(analysis: Any) -> FactorAssessment:
    """Publish the whale analyser's own reading, or say plainly it has none.

    Net withdrawals from exchanges are not a purchase and net deposits are
    not a sale. The analyser's own direction reads a deposit as bearish as soon
    as its score crosses a threshold; that shortcut is not taken here - a
    direction needs the exchange-held supply to move the same way.
    """

    available = bool(getattr(analysis, "available", False))
    freshness = str(getattr(getattr(analysis, "freshness", None), "value", "UNAVAILABLE"))
    providers = ", ".join(getattr(analysis, "configured_providers", None) or [])
    if not available:
        reason = getattr(analysis, "unavailable_reason", None)
        assessment = whale_assessment(available=False, provider=providers)
        if reason:
            from dataclasses import replace

            assessment = replace(assessment, missing_requirements=[str(reason)])
        return assessment

    behaviour = str(getattr(analysis, "behaviour", "") or "neutral")
    findings = [str(item) for item in getattr(analysis, "findings", []) or []]
    # A net flow is one measurement. It only earns a direction when the
    # exchange-held supply moves the same way - a second, independent view of
    # the same coins. Deposits alone are not a sale; withdrawals alone are
    # not a purchase.
    supply_down = any("supply down" in item for item in findings)
    supply_up = any("supply up" in item for item in findings)
    if behaviour == "from_exchange" and supply_down:
        direction = FactorDirection.POSITIVE
    elif behaviour == "to_exchange" and supply_up:
        direction = FactorDirection.NEGATIVE
    elif behaviour == "neutral":
        direction = FactorDirection.NEUTRAL
    else:
        direction = FactorDirection.UNKNOWN
    # How large the move is decides how much it can matter. A small transfer
    # must barely register; the analyser's score runs from -100 to 100.
    size = abs(float(getattr(analysis, "strength", 0.0) or 0.0))
    impact = (
        FactorImpact.HIGH
        if size >= 40
        else FactorImpact.MODERATE
        if size >= 20
        else FactorImpact.LOW
    )
    confidence = float(getattr(analysis, "confidence", 0.0) or 0.0)
    if confidence > 1.0:  # the analyser reports a percentage
        confidence /= 100.0
    rationale = {
        "from_exchange": "Retraits nets des plateformes : les gros portefeuilles "
        "sortent leurs jetons.",
        "to_exchange": "Dépôts nets vers les plateformes : des ventes sont "
        "possibles, sans être confirmées.",
    }.get(behaviour, "Flux des gros portefeuilles équilibrés.")
    return FactorAssessment(
        key="whales",
        label="Mouvements de baleines",
        direction=direction,
        impact=impact,
        confidence=max(0.0, min(1.0, confidence)),
        availability=availability_for(freshness, measured=True),
        freshness=freshness,
        provider=providers,
        rationale=rationale,
        causal_chain=[str(item) for item in getattr(analysis, "findings", [])[:3]],
    )

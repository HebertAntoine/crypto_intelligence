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
            freshness=freshness,
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
    return FactorAssessment(
        key="flows",
        label=label,
        direction=direction,
        impact=impact,
        trend=trend,
        confidence=min(0.9, float(getattr(flow, "sessions_available", 0) or 0) / 20),
        freshness=freshness,
        rationale="; ".join(parts),
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
            freshness=freshness,
            rationale="Aucune échelle de temps ne donne de direction exploitable.",
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
        freshness=freshness,
        rationale=detail,
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
        rationale=(
            "Les bandes de Bollinger sont resserrées: un mouvement important "
            "est possible, sans indication de sens."
            if squeeze
            else "Pas de compression marquée."
        ),
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
        evidence_ids=list(evidence_ids or []),
    )

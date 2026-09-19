"""How a macro variable reaches a crypto price, link by link.

Nothing here turns a level into a verdict. Brent at 108 dollars is not a sell
signal; it is an inflation input whose effect depends on what the bond market
and the dollar are doing at the same time. Every function below therefore
returns a reading plus the chain that produced it, and the confrontation step
refuses to conclude when the links disagree.

The three variables modelled here - energy, the Treasury curve and credit - were
absent from the analysis entirely. Credit in particular is what separates an
equity drawdown from systemic stress, and without it the difference cannot be
measured at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from .factor_semantics import (
    Availability,
    FactorAssessment,
    FactorDirection,
    FactorImpact,
    FactorTrend,
    availability_for,
    fr_number,
)

#: A move of this size over a month is a shock rather than a level. Energy
#: shocks transmit through expectations, and expectations move on change, not
#: on the absolute price.
OIL_SHOCK_30D_PCT = 15.0
OIL_FAST_7D_PCT = 8.0

#: High-yield spread levels. Below the calm floor, credit is not corroborating
#: any stress; above the stress floor, it is.
HY_CALM_PCT = 4.0
HY_STRESS_PCT = 6.0
HY_WIDENING_PCT = 0.5


class MacroRegime(StrEnum):
    """What the macro links say together, once confronted."""

    SUPPORTIVE = "SUPPORTIVE"
    NEUTRAL = "NEUTRAL"
    RESTRICTIVE = "RESTRICTIVE"
    STRONGLY_RESTRICTIVE = "STRONGLY_RESTRICTIVE"
    CONFLICTING = "CONFLICTING"
    UNKNOWN = "UNKNOWN"


@dataclass(slots=True, frozen=True)
class MacroReading:
    """One macro variable, its reading, and the chain that justifies it."""

    assessment: FactorAssessment
    chain: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = self.assessment.to_dict()
        payload["transmission_chain"] = self.chain
        return payload


# ---------------------------------------------------------------------------
# Energy
# ---------------------------------------------------------------------------


def oil_assessment(
    *,
    brent: float | None = None,
    wti: float | None = None,
    change_7d_pct: float | None = None,
    change_30d_pct: float | None = None,
    freshness: str = "UNAVAILABLE",
    provider: str = "FRED",
    source_url: str | None = None,
) -> MacroReading:
    """Read energy as a change, not as a level.

    "Brent is high" and "Brent rose twenty per cent in a fortnight" are not the
    same signal: the first is already in prices and in expectations, the second
    is not. A high but stable level is therefore read as a standing condition,
    while a fast move is read as a fresh inflation impulse.
    """

    # Either benchmark answers the question. WTI already flows in from Yahoo and
    # Stooq without an API key, while the FRED Brent series needs one, so
    # requiring Brent would have made this unusable on the data that exists.
    price = brent if brent is not None else wti
    benchmark = "Brent" if brent is not None else "WTI"
    available = price is not None
    availability = availability_for(freshness, measured=available)
    if not available:
        return MacroReading(
            FactorAssessment(
                key="energy",
                label="Énergie",
                direction=FactorDirection.UNKNOWN,
                impact=FactorImpact.LOW,
                availability=Availability.UNAVAILABLE,
                freshness=freshness,
                provider=provider,
                source_url=source_url,
                missing_requirements=["Série de prix du pétrole (Brent ou WTI)."],
                rationale="Prix du pétrole indisponible.",
            )
        )

    fast = (change_7d_pct is not None and abs(change_7d_pct) >= OIL_FAST_7D_PCT) or (
        change_30d_pct is not None and abs(change_30d_pct) >= OIL_SHOCK_30D_PCT
    )
    rising = (change_30d_pct or change_7d_pct or 0.0) > 0

    if fast and rising:
        direction, impact = FactorDirection.NEGATIVE, FactorImpact.HIGH
        observation = f"Le pétrole progresse rapidement ({benchmark} {price:.0f} $)."
        trend = FactorTrend.DETERIORATING
    elif fast and not rising:
        direction, impact = FactorDirection.POSITIVE, FactorImpact.MODERATE
        observation = f"Le pétrole recule rapidement ({benchmark} {price:.0f} $)."
        trend = FactorTrend.IMPROVING
    else:
        direction, impact = FactorDirection.NEUTRAL, FactorImpact.LOW
        observation = f"Le pétrole reste stable ({benchmark} {price:.0f} $)."
        trend = FactorTrend.STABLE

    chain = [
        observation,
        (
            "Une hausse rapide de l'énergie alimente l'inflation anticipée."
            if fast and rising
            else "Une baisse rapide de l'énergie détend l'inflation anticipée."
            if fast
            else "Un niveau stable est déjà intégré dans les anticipations."
        ),
    ]
    if fast:
        chain.extend(
            [
                "Une inflation anticipée plus "
                + ("forte" if rising else "faible")
                + " rend une détente monétaire "
                + ("moins" if rising else "plus")
                + " probable.",
                "Des rendements obligataires potentiellement "
                + ("plus élevés" if rising else "plus bas")
                + " resserrent ou détendent les conditions financières.",
                "Un contexte "
                + ("moins" if rising else "plus")
                + " favorable aux actifs risqués en découle — sans que ce lien "
                "soit automatique: il doit être confronté aux taux et au dollar.",
            ]
        )
    else:
        chain.append(
            "Sans mouvement marqué, l'énergie ne modifie pas les anticipations "
            "de politique monétaire."
        )

    detail = [f"{benchmark} {price:.1f} $"]
    if change_7d_pct is not None:
        detail.append(f"7 j {change_7d_pct:+.1f} %")
    if change_30d_pct is not None:
        detail.append(f"30 j {change_30d_pct:+.1f} %")

    return MacroReading(
        FactorAssessment(
            key="energy",
            value=f"{benchmark} {fr_number(price, 1)} $",
            label="Énergie",
            direction=direction,
            impact=impact,
            trend=trend,
            confidence=0.7,
            availability=availability,
            freshness=freshness,
            provider=provider,
            source_url=source_url,
            rationale=" · ".join(detail),
            causal_chain=chain,
        ),
        chain=chain,
    )


# ---------------------------------------------------------------------------
# Credit
# ---------------------------------------------------------------------------


def credit_assessment(
    *,
    hy_spread_pct: float | None,
    hy_change_30d_pct: float | None = None,
    ig_spread_pct: float | None = None,
    freshness: str = "UNAVAILABLE",
    provider: str = "FRED / ICE BofA",
    source_url: str | None = None,
) -> MacroReading:
    """Credit is the confirmation step, not a leading signal.

    Risk assets can fall a long way while credit stays calm; that is a drawdown.
    When spreads widen at the same time, the same fall means something else.
    Reading equity weakness without looking at credit cannot tell the two apart.
    """

    available = hy_spread_pct is not None
    availability = availability_for(freshness, measured=available)
    if not available:
        return MacroReading(
            FactorAssessment(
                key="credit",
                label="Crédit",
                direction=FactorDirection.UNKNOWN,
                impact=FactorImpact.LOW,
                availability=Availability.UNAVAILABLE,
                freshness=freshness,
                provider=provider,
                source_url=source_url,
                missing_requirements=["Série d'écarts de crédit à haut rendement."],
                rationale="Écarts de crédit indisponibles.",
            )
        )

    widening = hy_change_30d_pct is not None and hy_change_30d_pct >= HY_WIDENING_PCT
    stressed = hy_spread_pct >= HY_STRESS_PCT
    calm = hy_spread_pct <= HY_CALM_PCT and not widening

    if stressed and widening:
        direction, impact, trend = (
            FactorDirection.NEGATIVE,
            FactorImpact.VERY_HIGH,
            FactorTrend.DETERIORATING,
        )
        observation = "Les écarts de crédit sont élevés et continuent de s'écarter."
        mechanism = (
            "Le financement des entreprises se tend: c'est la signature d'un "
            "stress qui dépasse une simple correction de marché."
        )
    elif widening:
        direction, impact, trend = (
            FactorDirection.NEGATIVE,
            FactorImpact.HIGH,
            FactorTrend.DETERIORATING,
        )
        observation = "Les écarts de crédit s'écartent."
        mechanism = (
            "Le marché commence à exiger davantage pour prêter aux entreprises, "
            "ce qui accompagne généralement une aversion au risque plus large."
        )
    elif calm:
        direction, impact, trend = (
            FactorDirection.POSITIVE,
            FactorImpact.MODERATE,
            FactorTrend.STABLE,
        )
        observation = "Les écarts de crédit restent contenus."
        mechanism = (
            "Tant que le crédit reste calme, une baisse des actifs risqués reste "
            "une correction et non un stress systémique confirmé."
        )
    else:
        direction, impact, trend = (
            FactorDirection.NEUTRAL,
            FactorImpact.MODERATE,
            FactorTrend.STABLE,
        )
        observation = "Les écarts de crédit sont dans leur zone intermédiaire."
        mechanism = "Le crédit ne confirme ni ne dément une dégradation du risque."

    detail = [f"haut rendement {hy_spread_pct:.2f} %"]
    if ig_spread_pct is not None:
        detail.append(f"qualité investissement {ig_spread_pct:.2f} %")
    if hy_change_30d_pct is not None:
        detail.append(f"30 j {hy_change_30d_pct:+.2f} pt")

    chain = [observation, mechanism]
    return MacroReading(
        FactorAssessment(
            key="credit",
            value=f"haut rendement {fr_number(hy_spread_pct, 2)} %",
            label="Crédit",
            direction=direction,
            impact=impact,
            trend=trend,
            confidence=0.8,
            availability=availability,
            freshness=freshness,
            provider=provider,
            source_url=source_url,
            rationale=" · ".join(detail),
            causal_chain=chain,
        ),
        chain=chain,
    )


# ---------------------------------------------------------------------------
# Treasury curve
# ---------------------------------------------------------------------------


def rates_assessment(
    *,
    us2y: float | None,
    us10y: float | None,
    us30y: float | None = None,
    us10y_change_30d_pct: float | None = None,
    freshness: str = "UNAVAILABLE",
    provider: str = "FRED",
    source_url: str | None = None,
) -> MacroReading:
    """Each maturity answers a different question, so all three are read.

    The 2Y prices what the central bank is expected to do, the 10Y prices
    financial conditions and valuations, the 30Y carries long-run inflation and
    fiscal risk. Watching only the 10Y conflates the three.
    """

    available = us10y is not None
    availability = availability_for(freshness, measured=available)
    if not available:
        return MacroReading(
            FactorAssessment(
                key="rates",
                label="Taux",
                direction=FactorDirection.UNKNOWN,
                impact=FactorImpact.LOW,
                availability=Availability.UNAVAILABLE,
                freshness=freshness,
                provider=provider,
                source_url=source_url,
                missing_requirements=["Courbe des taux du Trésor américain."],
                rationale="Courbe des taux indisponible.",
            )
        )

    rising = us10y_change_30d_pct is not None and us10y_change_30d_pct > 0.25
    falling = us10y_change_30d_pct is not None and us10y_change_30d_pct < -0.25

    if rising:
        direction, impact, trend = (
            FactorDirection.NEGATIVE,
            FactorImpact.HIGH,
            FactorTrend.DETERIORATING,
        )
        mechanism = (
            "Des rendements qui montent resserrent les conditions financières et "
            "pèsent sur les valorisations des actifs risqués."
        )
    elif falling:
        direction, impact, trend = (
            FactorDirection.POSITIVE,
            FactorImpact.HIGH,
            FactorTrend.IMPROVING,
        )
        mechanism = (
            "Des rendements qui baissent détendent les conditions financières et "
            "soutiennent les valorisations."
        )
    else:
        direction, impact, trend = (
            FactorDirection.NEUTRAL,
            FactorImpact.MODERATE,
            FactorTrend.STABLE,
        )
        mechanism = "Les conditions financières ne se modifient pas nettement."

    detail = [f"10 ans {us10y:.2f} %"]
    parts = ["Le 10 ans décrit les conditions financières."]
    if us2y is not None:
        detail.insert(0, f"2 ans {us2y:.2f} %")
        parts.insert(0, "Le 2 ans reflète les attentes de politique monétaire.")
    if us30y is not None:
        detail.append(f"30 ans {us30y:.2f} %")
        parts.append("Le 30 ans porte l'inflation longue et le risque budgétaire.")
    if us2y is not None and us10y is not None:
        curve = us10y - us2y
        detail.append(f"pente 10-2 {curve:+.2f} pt")

    chain = [" ".join(detail) + ".", *parts, mechanism]
    return MacroReading(
        FactorAssessment(
            key="rates",
            value=f"10 ans {fr_number(us10y, 2)} %",
            label="Taux",
            direction=direction,
            impact=impact,
            trend=trend,
            confidence=0.85,
            availability=availability,
            freshness=freshness,
            provider=provider,
            source_url=source_url,
            rationale=" · ".join(detail),
            causal_chain=chain,
        ),
        chain=chain,
    )


# ---------------------------------------------------------------------------
# Confrontation
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class MacroConfrontation:
    """What the macro links say once compared with each other."""

    regime: MacroRegime
    rationale: str
    agreeing: list[str] = field(default_factory=list)
    disagreeing: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "regime": self.regime.value,
            "rationale": self.rationale,
            "agreeing": self.agreeing,
            "disagreeing": self.disagreeing,
            "missing": self.missing,
            "methodology": (
                "Le sens d'une variable macro n'est jamais conclu seul: il est "
                "confronté aux autres liens de la chaîne. Des liens qui se "
                "contredisent produisent CONFLICTING, pas une moyenne."
            ),
        }


def confront(readings: list[MacroReading]) -> MacroConfrontation:
    """Compare the macro links instead of averaging them.

    The case this exists for: oil rising while yields fall. Averaging would
    produce a mild reading and hide that the transmission chain is broken. What
    the data actually says is that the usual mechanism is not operating, and the
    honest output is CONFLICTING rather than a number.
    """

    # A measured variable counts even when its freshness label is imperfect.
    # Restricting this to AVAILABLE made a real reading vanish and the verdict
    # fall back to UNKNOWN, which is worse than reporting it as degraded.
    usable = {Availability.AVAILABLE, Availability.PARTIAL, Availability.STALE}
    available = [
        item
        for item in readings
        if item.assessment.availability in usable
        and item.assessment.direction is not FactorDirection.UNKNOWN
    ]
    degraded = [
        item.assessment.label
        for item in available
        if item.assessment.availability is not Availability.AVAILABLE
    ]
    missing = [
        item.assessment.label
        for item in readings
        if item.assessment.availability
        in {Availability.UNAVAILABLE, Availability.NOT_APPLICABLE}
    ]
    if not available:
        return MacroConfrontation(
            regime=MacroRegime.UNKNOWN,
            rationale="Aucune variable macro exploitable.",
            missing=missing,
        )
    degraded_note = (
        f" Lecture(s) dégradée(s): {', '.join(degraded)}." if degraded else ""
    )

    negative = [
        item.assessment for item in available
        if item.assessment.direction is FactorDirection.NEGATIVE
    ]
    positive = [
        item.assessment for item in available
        if item.assessment.direction is FactorDirection.POSITIVE
    ]

    def weight(items: list[FactorAssessment]) -> int:
        order = {
            FactorImpact.LOW: 1,
            FactorImpact.MODERATE: 2,
            FactorImpact.HIGH: 3,
            FactorImpact.VERY_HIGH: 4,
        }
        return sum(order[item.impact] for item in items)

    negative_weight, positive_weight = weight(negative), weight(positive)
    agreeing = [item.label for item in (negative if negative_weight >= positive_weight else positive)]
    disagreeing = [item.label for item in (positive if negative_weight >= positive_weight else negative)]

    # Both sides carrying real weight means the chain is not operating as
    # usual. Averaging that away would hide the most informative fact available.
    if negative and positive and min(negative_weight, positive_weight) >= 3:
        return MacroConfrontation(
            regime=MacroRegime.CONFLICTING,
            rationale=(
                "Les liens macro se contredisent: "
                + ", ".join(item.label for item in negative)
                + " pèsent tandis que "
                + ", ".join(item.label for item in positive)
                + " soutiennent. Aucune conclusion directionnelle n'est défendable."
                + degraded_note
            ),
            agreeing=agreeing,
            disagreeing=disagreeing,
            missing=missing,
        )

    if negative_weight >= 6 and not positive:
        regime = MacroRegime.STRONGLY_RESTRICTIVE
    elif negative_weight > positive_weight:
        regime = MacroRegime.RESTRICTIVE
    elif positive_weight > negative_weight:
        regime = MacroRegime.SUPPORTIVE
    else:
        regime = MacroRegime.NEUTRAL

    return MacroConfrontation(
        regime=regime,
        rationale=(
            f"{len(negative)} lien(s) défavorable(s) contre {len(positive)} "
            f"favorable(s), pondérés par leur importance." + degraded_note
        ),
        agreeing=agreeing,
        disagreeing=disagreeing,
        missing=missing,
    )


# ---------------------------------------------------------------------------
# Adapter: real observations -> readings
# ---------------------------------------------------------------------------

#: Metric names as the observation store already publishes them. Nothing new is
#: collected here: the same list the macro analyser receives is reused.
_METRIC_OIL_BRENT = "macro.brent"
_METRIC_OIL_WTI = ("macro.wti", "macro.oil_wti")
_METRIC_US2Y = "macro.us2y"
_METRIC_US10Y = ("macro.us10y", "macro.us10y_yahoo")
_METRIC_US30Y = "macro.us30y"
_METRIC_HY = "macro.hy_spread"
_METRIC_IG = "macro.ig_spread"


def _is_production(observation: Any) -> bool:
    """Reuse the project's own production-label rule, row by row."""

    from ..core.data_integrity import is_production_label

    provenance = getattr(observation, "provenance", None)
    return is_production_label(
        getattr(provenance, "source", "")
    ) and is_production_label(getattr(provenance, "provider", ""))


def _series(observations: list[Any], names: str | tuple[str, ...]) -> list[Any]:
    """Build one series, fixtures excluded.

    Mock rows sit interleaved with real ones in the live database: a constant
    71.8 appeared between genuine 92-93 dollar prints on the same day. Picked up
    as a reference point it produced a 43 per cent "oil shock" that never
    happened. The guard belongs here rather than at the call site, so it cannot
    be forgotten by a future caller.
    """

    wanted = (names,) if isinstance(names, str) else names
    items = [
        item
        for item in observations
        if item.metric in wanted
        and isinstance(item.value, int | float)
        and _is_production(item)
    ]
    return sorted(items, key=lambda item: item.timestamp)


def _latest(series: list[Any]) -> Any | None:
    return series[-1] if series else None


def _change_pct(series: list[Any], days: int, *, now: datetime) -> float | None:
    """Percentage change against the closest observation `days` ago.

    Returns None rather than a guess when no observation is old enough: a
    change computed against the only point available would be zero, which reads
    as "stable" and is a fabrication.
    """

    if len(series) < 2:
        return None
    current = series[-1]
    cutoff = now - timedelta(days=days)
    earlier = [item for item in series[:-1] if item.timestamp <= cutoff]
    if not earlier:
        return None
    reference = earlier[-1]
    if not reference.value:
        return None
    return (float(current.value) - float(reference.value)) / abs(float(reference.value)) * 100.0


def _freshness_of(item: Any) -> str:
    return str(getattr(getattr(item, "freshness", None), "value", "") or "UNAVAILABLE")


def _provider_of(item: Any, fallback: str) -> tuple[str, str | None]:
    prov = getattr(item, "provenance", None)
    provider = str(getattr(prov, "provider", "") or getattr(prov, "source", "") or fallback)
    return provider, getattr(prov, "source_url", None)


def readings_from_observations(
    observations: list[Any], *, now: datetime | None = None
) -> list[MacroReading]:
    """Build the energy, rates and credit readings from stored observations.

    Every variable is read from the series that actually exists. A missing one
    produces an UNAVAILABLE reading that states what it needs, so the absence
    travels to the screen instead of quietly becoming a neutral stance.
    """

    reference = now or datetime.now(UTC)

    brent_series = _series(observations, _METRIC_OIL_BRENT)
    wti_series = _series(observations, _METRIC_OIL_WTI)
    oil_series = brent_series or wti_series
    oil_latest = _latest(oil_series)
    oil_provider, oil_url = (
        _provider_of(oil_latest, "FRED") if oil_latest else ("", None)
    )
    oil = oil_assessment(
        brent=float(_latest(brent_series).value) if brent_series else None,
        wti=float(_latest(wti_series).value) if wti_series else None,
        change_7d_pct=_change_pct(oil_series, 7, now=reference),
        change_30d_pct=_change_pct(oil_series, 30, now=reference),
        freshness=_freshness_of(oil_latest) if oil_latest else "UNAVAILABLE",
        provider=oil_provider,
        source_url=oil_url,
    )

    us2y, us10y, us30y = (
        _latest(_series(observations, _METRIC_US2Y)),
        _latest(_series(observations, _METRIC_US10Y)),
        _latest(_series(observations, _METRIC_US30Y)),
    )
    ten_year_series = _series(observations, _METRIC_US10Y)
    rates_provider, rates_url = _provider_of(us10y, "FRED") if us10y else ("", None)
    rates = rates_assessment(
        us2y=float(us2y.value) if us2y else None,
        us10y=float(us10y.value) if us10y else None,
        us30y=float(us30y.value) if us30y else None,
        # Yields are already percentages: the meaningful move is in points.
        us10y_change_30d_pct=(
            (float(us10y.value) - float(ten_year_series[0].value))
            if us10y and len(ten_year_series) > 1
            else None
        ),
        freshness=_freshness_of(us10y) if us10y else "UNAVAILABLE",
        provider=rates_provider,
        source_url=rates_url,
    )

    hy_series = _series(observations, _METRIC_HY)
    hy_latest = _latest(hy_series)
    ig_latest = _latest(_series(observations, _METRIC_IG))
    credit_provider, credit_url = (
        _provider_of(hy_latest, "FRED / ICE BofA") if hy_latest else ("", None)
    )
    credit = credit_assessment(
        hy_spread_pct=float(hy_latest.value) if hy_latest else None,
        hy_change_30d_pct=(
            float(hy_latest.value) - float(hy_series[0].value)
            if hy_latest and len(hy_series) > 1
            else None
        ),
        ig_spread_pct=float(ig_latest.value) if ig_latest else None,
        freshness=_freshness_of(hy_latest) if hy_latest else "UNAVAILABLE",
        provider=credit_provider,
        source_url=credit_url,
    )
    return [oil, rates, credit]

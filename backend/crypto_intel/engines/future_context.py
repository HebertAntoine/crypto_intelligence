"""Adapt the existing analysis snapshot into the five future-first families."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from ..future_events.freshness import EventFreshness, event_freshness
from ..future_events.models import (
    DecisionHorizon,
    DirectionalBias,
    ExpectedMovement,
    FutureEvent,
    FutureEventCategory,
)
from .future_decision import FamilyAssessment, FiveFamilySnapshot, FutureFamily

_HORIZON_DELTA = {
    DecisionHorizon.H24: timedelta(hours=24),
    DecisionHorizon.D7: timedelta(days=7),
    DecisionHorizon.D30: timedelta(days=30),
}

_HORIZON_TECHNICAL_STATES = {
    DecisionHorizon.H24: ("ohlcv_h1", "ohlcv_4h"),
    DecisionHorizon.D7: ("ohlcv_4h", "ohlcv_daily"),
    DecisionHorizon.D30: ("ohlcv_daily", "ohlcv_weekly"),
}


def events_for_horizon(
    events: list[FutureEvent], horizon: DecisionHorizon, as_of: datetime
) -> list[FutureEvent]:
    """Select future and still-active recent events for one real horizon."""
    delta = _HORIZON_DELTA[horizon]
    cutoff = as_of + delta
    lower = as_of - delta
    selected: list[FutureEvent] = []
    for event in events:
        moment = event.scheduled_at or event.source_published_at or event.detected_at
        if (event.scheduled_at is not None and as_of <= event.scheduled_at <= cutoff) or (event.scheduled_at is None and lower <= moment <= as_of):
            selected.append(event)
        elif event.scheduled_at is not None and lower <= event.scheduled_at < as_of:
            # ``analysis_context`` has already lifecycle-filtered these rows;
            # retaining them only inside the horizon-specific lookback lets a
            # just-released result decay instead of leaking forever.
            selected.append(event)
    return selected


def usable_events_for_horizon(
    events: list[FutureEvent], horizon: DecisionHorizon, as_of: datetime
) -> list[FutureEvent]:
    """Return horizon-relevant events fresh and authoritative enough to decide.

    Social-tier items were being assigned tier E and then flowing on unchecked:
    a post could reach the decision without ever being re-sourced. They are now
    dropped here, which is the single point every horizon passes through.
    """

    from .source_hierarchy import may_influence_decision

    return [
        event
        for event in events_for_horizon(events, horizon, as_of)
        if event_freshness(event, as_of).freshness_status
        in {EventFreshness.LIVE, EventFreshness.FRESH}
        and may_influence_decision(event.source_tier)
    ]


def structure_for_horizon(
    structure: dict[str, Any], horizon: DecisionHorizon
) -> dict[str, Any]:
    """Project the MTF structure onto the units relevant to one horizon."""
    units = {
        DecisionHorizon.H24: ("1h", "4h"),
        DecisionHorizon.D7: ("4h", "1d"),
        DecisionHorizon.D30: ("1d", "1w"),
    }[horizon]
    readings = structure.get("timeframes") or {}
    selected = {name: readings[name] for name in units if name in readings}
    bullish = [
        name for name, value in selected.items() if value.get("state") == "BULLISH_STRUCTURE"
    ]
    bearish = [
        name for name, value in selected.items() if value.get("state") == "BEARISH_STRUCTURE"
    ]
    return {
        "timeframes": selected,
        "bullish_timeframes": bullish,
        "bearish_timeframes": bearish,
        "conflict": bool(bullish and bearish),
    }


def _value(value: Any, default: str = "") -> str:
    result = getattr(value, "value", value)
    return str(result) if result is not None else default


def _isoformat(value: Any) -> str | None:
    return value.isoformat() if isinstance(value, datetime) else None


def _direction(value: float | None) -> DirectionalBias:
    if value is None:
        return DirectionalBias.NEUTRAL
    if value >= 60:
        return DirectionalBias.STRONGLY_BULLISH
    if value > 12:
        return DirectionalBias.BULLISH
    if value <= -60:
        return DirectionalBias.STRONGLY_BEARISH
    if value < -12:
        return DirectionalBias.BEARISH
    return DirectionalBias.NEUTRAL


_INSTITUTIONAL_STATE_FR = {
    "STRONG_INFLOW": "fortes entrées nettes",
    "INFLOW": "entrées nettes",
    "NEUTRAL": "sans direction nette",
    "OUTFLOW": "sorties nettes",
    "STRONG_OUTFLOW": "fortes sorties nettes",
}


def _musd(value: Any) -> str:
    """Format a millions-of-dollars figure for display, signed, one decimal."""

    if value is None:
        return "n/d"
    return f"{float(value):+,.1f} M$".replace(",", " ").replace(".", ",")


def _institutional_summary(institutional_flow: Any, state: str) -> str:
    """Describe the flow regime and the recent window without mixing them.

    The regime is measured over its own number of sessions; quoting a
    five-session cumulative next to it made a positive regime read as if it
    were negative. Each figure now carries the window it was measured on.
    """

    sessions = int(getattr(institutional_flow, "regime_sessions", 0) or 0)
    regime_total = getattr(institutional_flow, "regime_total_musd", None)
    label = _INSTITUTIONAL_STATE_FR.get(state, state.lower())
    head = (
        f"Flux institutionnels: {label} sur {sessions} séances "
        f"({_musd(regime_total)})"
        if sessions
        else f"Flux institutionnels: {label}"
    )
    # A regime measured over twenty sessions can stay positive while the most
    # recent sessions have already turned. The engine detects that reversal and
    # used to drop it, so the summary announced net inflows next to a negative
    # five-session figure. The reversal is now stated instead of discarded.
    reversal = _value(getattr(institutional_flow, "flow_reversal", None), "UNAVAILABLE")
    streak = int(getattr(institutional_flow, "persistence_sessions", 0) or 0)
    streak_side = _value(getattr(institutional_flow, "persistence_direction", None), "")
    if reversal == "INFLOW_TO_OUTFLOW" and streak:
        head += (
            f", mais le sens s'est inversé: {streak} séance(s) consécutives "
            "de sorties"
        )
    elif reversal == "OUTFLOW_TO_INFLOW" and streak:
        head += (
            f", mais le sens s'est inversé: {streak} séance(s) consécutives "
            "d'entrées"
        )
    elif streak >= 3 and streak_side in {"INFLOW", "OUTFLOW"}:
        side = "entrées" if streak_side == "INFLOW" else "sorties"
        head += f", dont {streak} séance(s) consécutives de {side}"

    recent = getattr(institutional_flow, "rolling_5_sessions_musd", None)
    if recent is None or sessions == 5:
        return head + "."
    return f"{head}; 5 dernières séances {_musd(recent)}."


_VOLATILITY_FR = {
    "VERY_LOW": "très faible",
    "LOW": "faible",
    "NORMAL": "normale",
    "HIGH": "forte",
    "VERY_HIGH": "très forte",
}


def _technical_summary(
    *,
    horizon: DecisionHorizon,
    bullish: list[str],
    bearish: list[str],
    volatility_regime: str,
    squeeze: bool | None,
) -> str:
    """Describe the technical reading in words a non-specialist can act on."""

    window = {
        DecisionHorizon.H24: "sur 24 heures",
        DecisionHorizon.D7: "sur 7 jours",
        DecisionHorizon.D30: "sur 30 jours",
    }[horizon]
    if not bullish and not bearish:
        head = f"Aucune échelle de temps ne donne de direction claire {window}"
    elif bullish and not bearish:
        head = f"{len(bullish)} échelle(s) de temps orientée(s) à la hausse {window}"
    elif bearish and not bullish:
        head = f"{len(bearish)} échelle(s) de temps orientée(s) à la baisse {window}"
    else:
        head = (
            f"Échelles de temps partagées {window}: {len(bullish)} à la hausse "
            f"contre {len(bearish)} à la baisse"
        )
    volatility = _VOLATILITY_FR.get(volatility_regime.upper(), volatility_regime.lower())
    parts = [f"{head}; volatilité {volatility}."]
    if squeeze is True:
        parts.append(
            "Les bandes de Bollinger sont resserrées: un mouvement de forte "
            "amplitude est possible, sans indication de sens."
        )
    elif squeeze is False:
        parts.append("Pas de compression des bandes de Bollinger.")
    return " ".join(parts)


def _event_direction(events: list[FutureEvent]) -> DirectionalBias | None:
    directed = [
        event for event in events if event.directional_effect is not DirectionalBias.NEUTRAL
    ]
    if not directed:
        return None
    directed.sort(key=lambda event: (-event.importance.rank, -event.confidence))
    top_rank = directed[0].importance.rank
    top = [event for event in directed if event.importance.rank == top_rank]
    sides = {"bull" if "BULLISH" in event.directional_effect.value else "bear" for event in top}
    return directed[0].directional_effect if len(sides) == 1 else DirectionalBias.NEUTRAL


def _movement(events: list[FutureEvent], fallback: ExpectedMovement) -> ExpectedMovement:
    rank = {
        ExpectedMovement.LOW: 0,
        ExpectedMovement.NORMAL: 1,
        ExpectedMovement.HIGH: 2,
        ExpectedMovement.EXTREME: 3,
    }
    return max([fallback, *(event.magnitude_effect for event in events)], key=rank.__getitem__)


def _event_sources(events: list[FutureEvent]) -> list[dict[str, Any]]:
    result = []
    seen: set[tuple[str, str | None]] = set()
    for event in events:
        key = (event.source, event.source_url)
        if key in seen:
            continue
        seen.add(key)
        result.append(
            {
                "source": event.source,
                "tier": event.source_tier.value,
                "url": event.source_url,
                "reference": event.source_reference,
                "as_of": event.last_updated.isoformat(),
                "evidence_ids": event.evidence_ids,
            }
        )
    return result


def _derived_source(name: str, analysis_id: str, as_of: datetime) -> dict[str, Any]:
    return {
        "source": name,
        "tier": "DERIVED",
        "reference": analysis_id,
        "as_of": as_of.isoformat(),
        "evidence_ids": [],
    }


def _freshness(states: dict[str, Any], names: tuple[str, ...]) -> str:
    order = {
        "UNAVAILABLE": 0,
        "STALE": 1,
        "TODAY": 2,
        "HOUR_1": 3,
        "MIN_15": 4,
        "LIVE": 5,
    }
    values = [
        _value(getattr(states.get(name), "freshness", None), "UNAVAILABLE")
        for name in names
        if states.get(name) is not None and bool(getattr(states[name], "usable", False))
    ]
    return min(values, key=lambda value: order.get(value, 0)) if values else "UNAVAILABLE"


def _usable(states: dict[str, Any], *names: str) -> bool:
    return any(bool(getattr(states.get(name), "usable", False)) for name in names)


def _pressure_components(pressure: Any, names: set[str]) -> list[Any]:
    return [
        component
        for component in getattr(pressure, "components", []) or []
        if getattr(component, "name", getattr(component, "family", "")) in names
        and bool(getattr(component, "available", False))
        and getattr(component, "score", None) is not None
    ]


def build_five_family_snapshot(
    *,
    analysis_id: str,
    as_of: datetime,
    states: dict[str, Any],
    events: list[FutureEvent],
    macro_context: dict[str, Any],
    liquidity: dict[str, Any],
    pressure: Any,
    institutional_flow: Any,
    structure: dict[str, Any],
    regime: Any,
    volatility: Any,
    implied_volatility: Any,
    expected_volatility: Any = None,
    leverage_state: str | None = None,
    funding_state: str | None = None,
    macro_observations: list[Any] | None = None,
    horizon: DecisionHorizon = DecisionHorizon.D7,
) -> FiveFamilySnapshot:
    """Create all five slots from one immutable analysis context."""
    events = usable_events_for_horizon(events, horizon, as_of)
    structure = structure_for_horizon(structure, horizon)
    macro_events = [
        event
        for event in events
        if event.category
        in {
            FutureEventCategory.MACRO,
            FutureEventCategory.MONETARY_POLICY,
            FutureEventCategory.ENERGY,
        }
    ]
    catalyst_events = [
        event
        for event in events
        if event.category
        in {
            FutureEventCategory.REGULATION,
            FutureEventCategory.ETF,
            FutureEventCategory.PROTOCOL,
            FutureEventCategory.GEOPOLITICAL,
            FutureEventCategory.SYSTEMIC_RISK,
            FutureEventCategory.OTHER,
        }
    ]

    # Stablecoin liquidity is a slow input and cannot drive the 24-hour
    # family. It becomes relevant at 7d/30d without being duplicated.
    liquidity_available = (
        bool(liquidity.get("available"))
        and _usable(states, "liquidity")
        and horizon is not DecisionHorizon.H24
    )
    macro_context_available = bool(macro_context.get("available")) and _usable(
        states, "macro"
    )
    macro_available = (
        bool(macro_events)
        or macro_context_available
        or liquidity_available
    )
    macro_strengths = [
        float(item)
        for item in (
            macro_context.get("strength"),
            liquidity.get("strength") if liquidity_available else None,
        )
        if item is not None
    ]
    macro_strength = max(macro_strengths, key=abs) if macro_strengths else None
    macro_direction = _event_direction(macro_events) or _direction(macro_strength)
    macro_summary = (
        f"{len(macro_events)} événement(s) macro/monétaire sourcé(s) dans la fenêtre."
        if macro_events
        else "; ".join((macro_context.get("findings") or liquidity.get("findings") or [])[:2])
    )
    macro_sources = _event_sources(macro_events)
    if macro_context_available:
        macro_sources.append(_derived_source("MacroAnalyzer", analysis_id, as_of))
    if liquidity_available:
        macro_sources.append(_derived_source("StablecoinLiquidityAnalyzer", analysis_id, as_of))

    from .geopolitics import GeopoliticalRiskEngine

    geopolitical = GeopoliticalRiskEngine().analyze(catalyst_events)
    catalyst_available = bool(catalyst_events)
    catalyst_direction = (
        geopolitical.directional_bias
        if geopolitical.available
        else _event_direction(catalyst_events) or DirectionalBias.NEUTRAL
    )
    catalyst_sources = _event_sources(catalyst_events)
    if geopolitical.available:
        catalyst_sources.append(_derived_source("GeopoliticalRiskEngine", analysis_id, as_of))

    institutional_usable = (
        horizon is not DecisionHorizon.H24
        and bool(getattr(institutional_flow, "available", False))
        and _value(
            getattr(institutional_flow, "freshness", None), "UNAVAILABLE"
        ) not in {"STALE", "UNAVAILABLE"}
    )
    flow_components = _pressure_components(pressure, {"spot", "whales"})
    flow_order = {"whales": 1, "spot": 2}
    flow_components.sort(
        key=lambda item: (
            flow_order.get(getattr(item, "name", getattr(item, "family", "")), 9),
            -abs(float(getattr(item, "score", 0) or 0)),
        )
    )
    institutional_state = _value(getattr(institutional_flow, "state", None))
    institutional_directions = {
        "STRONG_INFLOW": DirectionalBias.STRONGLY_BULLISH,
        "INFLOW": DirectionalBias.BULLISH,
        "NEUTRAL": DirectionalBias.NEUTRAL,
        "OUTFLOW": DirectionalBias.BEARISH,
        "STRONG_OUTFLOW": DirectionalBias.STRONGLY_BEARISH,
    }
    flow_direction = (
        institutional_directions.get(institutional_state)
        if institutional_usable
        else _direction(float(flow_components[0].score))
        if flow_components
        else None
    )
    flow_sources = [
        {
            "source": item.get("source"),
            "tier": "MEASURED",
            "url": item.get("source_url"),
            "reference": item.get("provider"),
            "as_of": _isoformat(getattr(institutional_flow, "observed_at", None)),
            "evidence_ids": list(getattr(institutional_flow, "evidence_ids", [])),
        }
        for item in getattr(institutional_flow, "provenance", [])
    ] + [
        {
            "source": getattr(item, "source", ""),
            "tier": "MEASURED",
            "reference": analysis_id,
            "as_of": getattr(item, "as_of", None),
            "evidence_ids": [],
        }
        for item in flow_components
    ]

    positioning_components = _pressure_components(pressure, {"derivatives", "funding"})
    positioning_components.sort(key=lambda item: -abs(float(getattr(item, "score", 0) or 0)))
    positioning_direction = (
        _direction(float(positioning_components[0].score)) if positioning_components else None
    )
    volatility_regime = _value(getattr(volatility, "regime", None), "UNKNOWN")
    dvol_available = bool(getattr(implied_volatility, "available", False))
    dvol_usable = dvol_available and bool(
        getattr(implied_volatility, "usable_for_decision", False)
    )
    positioning_available = (
        bool(positioning_components)
        or dvol_usable
        or _usable(states, "funding", "open_interest", "dvol")
    )
    positioning_movement = (
        ExpectedMovement.HIGH
        if volatility_regime in {"HIGH", "VERY_HIGH"}
        or _value(getattr(volatility, "direction", None)) == "EXPANDING"
        else ExpectedMovement.NORMAL
    )
    positioning_sources: list[dict[str, Any]] = [
        {
            "source": getattr(item, "source", ""),
            "tier": "MEASURED",
            "reference": analysis_id,
            "as_of": getattr(item, "as_of", None),
            "evidence_ids": [],
        }
        for item in positioning_components
    ]
    if dvol_usable:
        dvol_source = _derived_source("ImpliedVolatilityEngine (Deribit)", analysis_id, as_of)
        dvol_source["as_of"] = _isoformat(getattr(implied_volatility, "observed_at", None))
        positioning_sources.append(dvol_source)

    bullish = list(structure.get("bullish_timeframes") or [])
    bearish = list(structure.get("bearish_timeframes") or [])
    technical_state_names = _HORIZON_TECHNICAL_STATES[horizon]
    technical_available = _usable(states, *technical_state_names)
    technical_score = (len(bullish) - len(bearish)) * 25 if bullish or bearish else None
    if technical_score is None:
        regime_label = _value(getattr(regime, "regime", None), "UNDETERMINED")
        technical_score = (
            40
            if "BULL" in regime_label or "UP" in regime_label
            else -40
            if "BEAR" in regime_label or "DOWN" in regime_label
            else None
        )
    technical_direction = _direction(technical_score) if technical_available else None
    technical_movement = (
        ExpectedMovement.HIGH
        if volatility_regime in {"HIGH", "VERY_HIGH"}
        or _value(getattr(volatility, "direction", None)) == "EXPANDING"
        or (
            bool(getattr(expected_volatility, "available", False))
            and _value(getattr(expected_volatility, "expected_movement", None)) == "HIGH"
        )
        else ExpectedMovement.NORMAL
    )

    partial = {
        FutureFamily.MACRO_LIQUIDITY: FamilyAssessment(
            family=FutureFamily.MACRO_LIQUIDITY,
            available=macro_available,
            directional_bias=macro_direction if macro_available else None,
            expected_movement=_movement(macro_events, ExpectedMovement.NORMAL),
            confidence=(
                max([event.confidence for event in macro_events], default=0.65)
                if macro_available
                else 0.0
            ),
            summary=macro_summary or "Contexte macro mesuré, sans direction forte.",
            reasons=[event.title for event in macro_events[:3]],
            sources=macro_sources,
            as_of=as_of.isoformat(),
            freshness=("RECENT" if macro_events else _freshness(states, ("macro", "onchain"))),
            unavailable_reason="Calendrier et séries macro/liquidité indisponibles.",
        ),
        FutureFamily.CATALYSTS_REGULATION: FamilyAssessment(
            family=FutureFamily.CATALYSTS_REGULATION,
            available=catalyst_available,
            directional_bias=catalyst_direction if catalyst_available else None,
            expected_movement=(
                geopolitical.expected_movement
                if geopolitical.available
                else _movement(catalyst_events, ExpectedMovement.NORMAL)
            ),
            confidence=max([event.confidence for event in catalyst_events], default=0.0),
            summary=(
                geopolitical.explanation
                if geopolitical.available
                else (
                    f"{len(catalyst_events)} catalyseur(s) réglementaire(s), protocolaire(s) "
                    "ou géopolitique(s) sourcé(s)."
                    if catalyst_events
                    else ""
                )
            ),
            reasons=[event.title for event in catalyst_events[:3]],
            sources=catalyst_sources,
            as_of=as_of.isoformat(),
            freshness="RECENT" if catalyst_events else "UNAVAILABLE",
            unavailable_reason="Aucun catalyseur pertinent remonté par les sources configurées.",
        ),
        FutureFamily.FLOWS_WHALES: FamilyAssessment(
            family=FutureFamily.FLOWS_WHALES,
            available=institutional_usable or bool(flow_components),
            directional_bias=flow_direction,
            expected_movement=ExpectedMovement.NORMAL,
            confidence=(
                min(0.9, float(getattr(institutional_flow, "sessions_available", 0)) / 20)
                if institutional_usable
                else float(getattr(flow_components[0], "confidence", 0.0))
                if flow_components
                else 0.0
            ),
            summary=(
                (
                    _institutional_summary(institutional_flow, institutional_state)
                    if institutional_usable
                    else "; ".join(str(getattr(item, "detail", "")) for item in flow_components[:2])
                )
                if institutional_usable or flow_components
                else ""
            ),
            reasons=(
                [f"Régime institutionnel {institutional_state}"] if institutional_usable else []
            )
            + [str(getattr(item, "label", "")) for item in flow_components[:3]],
            sources=flow_sources,
            as_of=(
                _isoformat(getattr(institutional_flow, "observed_at", None))
                if institutional_usable and getattr(institutional_flow, "observed_at", None)
                else getattr(flow_components[0], "as_of", None)
                if flow_components
                else None
            ),
            freshness=(
                _value(getattr(institutional_flow, "freshness", None), "UNAVAILABLE")
                if institutional_usable
                else _value(getattr(flow_components[0], "freshness", None), "UNAVAILABLE")
                if flow_components
                else "UNAVAILABLE"
            ),
            unavailable_reason="Flux institutionnels, spot et baleines indisponibles.",
        ),
        FutureFamily.POSITIONING_DERIVATIVES: FamilyAssessment(
            family=FutureFamily.POSITIONING_DERIVATIVES,
            available=positioning_available,
            directional_bias=(positioning_direction if positioning_available else None),
            expected_movement=positioning_movement,
            confidence=(
                max(
                    [float(getattr(item, "confidence", 0.0)) for item in positioning_components]
                    + ([0.75] if dvol_usable else [0.0])
                )
                if positioning_available
                else 0.0
            ),
            summary=(
                "; ".join(str(getattr(item, "detail", "")) for item in positioning_components[:2])
                or (
                    str(getattr(implied_volatility, "interpretation", ""))
                    if dvol_usable
                    else "Positionnement disponible sans signal directionnel défendable."
                )
            ),
            reasons=[str(getattr(item, "label", "")) for item in positioning_components[:3]],
            sources=positioning_sources,
            as_of=as_of.isoformat(),
            freshness=_freshness(states, ("funding", "open_interest", "dvol")),
            unavailable_reason="Funding, OI, options et DVOL indisponibles.",
        ),
        FutureFamily.TECHNICAL_VOLATILITY: FamilyAssessment(
            family=FutureFamily.TECHNICAL_VOLATILITY,
            available=technical_available,
            directional_bias=technical_direction,
            expected_movement=technical_movement,
            confidence=(
                min(0.9, (len(bullish) + len(bearish)) / 4) if technical_available else 0.0
            ),
            # Plain French at the source. Translating "squeeze=False" in the UI
            # meant the screen was interpreting an engine flag, which is exactly
            # what the interpretation layer exists to prevent.
            summary=(
                _technical_summary(
                    horizon=horizon,
                    bullish=bullish,
                    bearish=bearish,
                    volatility_regime=volatility_regime,
                    squeeze=(
                        bool(getattr(expected_volatility, "squeeze", False))
                        if bool(getattr(expected_volatility, "available", False))
                        else None
                    ),
                )
                if technical_available
                else ""
            ),
            reasons=[
                *(f"Structure haussière {item}" for item in bullish[:2]),
                *(f"Structure baissière {item}" for item in bearish[:2]),
            ],
            sources=[
                _derived_source("MarketStructureEngine", analysis_id, as_of),
                _derived_source("VolatilityRegimeEngine", analysis_id, as_of),
                *(
                    [_derived_source("ExpectedVolatilityEngine", analysis_id, as_of)]
                    if bool(getattr(expected_volatility, "available", False))
                    else []
                ),
            ],
            as_of=as_of.isoformat(),
            freshness=_freshness(states, technical_state_names),
            unavailable_reason="Historique OHLCV insuffisant pour structure et volatilité.",
        ),
    }
    # Normalised semantics, published alongside the families. Direction, impact,
    # trend and confidence are kept apart here so the UI never has to infer one
    # from another - and so UNKNOWN stays distinct from NEUTRAL.
    from .factor_semantics import (
        flow_assessment,
        implied_volatility_assessment,
        positioning_from_leverage_state,
        pressure_component_assessment,
        technical_assessment,
        volatility_assessment,
    )

    normalised: list[dict[str, Any]] = []
    if institutional_usable:
        normalised.append(
            flow_assessment(
                institutional_flow, label="Flux institutionnels & baleines"
            ).to_dict()
        )
    if positioning_available:
        normalised.append(
            positioning_from_leverage_state(
                leverage_state,
                funding_state=funding_state,
                freshness=_freshness(states, ("open_interest", "funding")),
                provider="Open interest multi-exchange, comptes Binance",
            ).to_dict()
        )
    # Every component the families actually weighed must have a traceable
    # reading. Funding drove a family's direction while having no interpretation
    # of its own, which left a decision resting on something the screen could
    # not explain.
    # The pressure engine's "derivatives" component measures the same thing as
    # the leverage-state reading published above. Adding both counted one
    # measurement twice and inflated its weight in the synthesis.
    same_as = {"derivatives": "positioning"}
    covered = {item["key"] for item in normalised}
    for component in flow_components + positioning_components:
        reading = pressure_component_assessment(component)
        key = same_as.get(reading.key, reading.key)
        if key in covered:
            continue
        covered.add(key)
        normalised.append(reading.to_dict())
    if technical_available:
        normalised.append(
            technical_assessment(
                bullish_timeframes=bullish,
                bearish_timeframes=bearish,
                freshness=_freshness(states, technical_state_names),
            ).to_dict()
        )
    if getattr(expected_volatility, "available", False):
        normalised.append(
            volatility_assessment(
                squeeze=bool(getattr(expected_volatility, "squeeze", False)),
                freshness=_freshness(states, technical_state_names),
            ).to_dict()
        )
    # Energy, the Treasury curve and credit join the macro family as readings of
    # their own. They were collected and never interpreted; a missing series
    # publishes what it needs rather than a neutral stance.
    if macro_observations:
        from .macro_transmission import readings_from_observations

        for reading in readings_from_observations(macro_observations, now=as_of):
            normalised.append(reading.to_dict())

    normalised.append(
        implied_volatility_assessment(
            available=dvol_usable,
            percentile=getattr(implied_volatility, "dvol_percentile", None),
            freshness=_value(getattr(implied_volatility, "freshness", None), "UNAVAILABLE"),
            provider="Deribit" if dvol_available else "",
        ).to_dict()
    )

    snapshot = FiveFamilySnapshot.from_partial(partial)
    snapshot.normalised_factors = normalised
    return snapshot

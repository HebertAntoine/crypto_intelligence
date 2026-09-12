"""Adapt the existing analysis snapshot into the five future-first families."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ..future_events.models import (
    DirectionalBias,
    ExpectedMovement,
    FutureEvent,
    FutureEventCategory,
)
from .future_decision import FamilyAssessment, FiveFamilySnapshot, FutureFamily


def _value(value: Any, default: str = "") -> str:
    result = getattr(value, "value", value)
    return str(result) if result is not None else default


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


def _event_direction(events: list[FutureEvent]) -> DirectionalBias | None:
    directed = [
        event
        for event in events
        if event.directional_effect is not DirectionalBias.NEUTRAL
    ]
    if not directed:
        return None
    directed.sort(key=lambda event: (-event.importance.rank, -event.confidence))
    top_rank = directed[0].importance.rank
    top = [event for event in directed if event.importance.rank == top_rank]
    sides = {
        "bull" if "BULLISH" in event.directional_effect.value else "bear"
        for event in top
    }
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
    structure: dict[str, Any],
    regime: Any,
    volatility: Any,
    implied_volatility: Any,
) -> FiveFamilySnapshot:
    """Create all five slots from one immutable analysis context."""
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

    macro_available = bool(macro_events) or bool(macro_context.get("available")) or bool(
        liquidity.get("available")
    )
    macro_strengths = [
        float(item)
        for item in (macro_context.get("strength"), liquidity.get("strength"))
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
    if macro_context.get("available"):
        macro_sources.append(_derived_source("MacroAnalyzer", analysis_id, as_of))
    if liquidity.get("available"):
        macro_sources.append(_derived_source("StablecoinLiquidityAnalyzer", analysis_id, as_of))

    catalyst_available = bool(catalyst_events)
    catalyst_direction = _event_direction(catalyst_events) or DirectionalBias.NEUTRAL

    flow_components = _pressure_components(pressure, {"institutions", "spot", "whales"})
    flow_order = {"institutions": 0, "whales": 1, "spot": 2}
    flow_components.sort(
        key=lambda item: (
            flow_order.get(getattr(item, "name", getattr(item, "family", "")), 9),
            -abs(float(getattr(item, "score", 0) or 0)),
        )
    )
    flow_direction = _direction(float(flow_components[0].score)) if flow_components else None
    flow_sources = [
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
        _direction(float(positioning_components[0].score))
        if positioning_components
        else None
    )
    volatility_regime = _value(getattr(volatility, "regime", None), "UNKNOWN")
    dvol_available = bool(getattr(implied_volatility, "available", False))
    positioning_available = bool(positioning_components) or dvol_available or _usable(
        states, "funding", "open_interest", "dvol"
    )
    positioning_movement = (
        ExpectedMovement.HIGH
        if volatility_regime in {"HIGH", "VERY_HIGH"}
        or _value(getattr(volatility, "direction", None)) == "EXPANDING"
        else ExpectedMovement.NORMAL
    )
    positioning_sources = [
        {
            "source": getattr(item, "source", ""),
            "tier": "MEASURED",
            "reference": analysis_id,
            "as_of": getattr(item, "as_of", None),
            "evidence_ids": [],
        }
        for item in positioning_components
    ]
    if dvol_available:
        positioning_sources.append(_derived_source("ImpliedVolatilityEngine (Deribit)", analysis_id, as_of))

    bullish = list(structure.get("bullish_timeframes") or [])
    bearish = list(structure.get("bearish_timeframes") or [])
    technical_available = _usable(states, "structure", "volatility")
    technical_score = (len(bullish) - len(bearish)) * 25 if bullish or bearish else None
    if technical_score is None:
        regime_label = _value(getattr(regime, "regime", None), "UNDETERMINED")
        technical_score = (
            40 if "BULL" in regime_label or "UP" in regime_label
            else -40 if "BEAR" in regime_label or "DOWN" in regime_label
            else None
        )
    technical_direction = _direction(technical_score) if technical_available else None
    technical_movement = (
        ExpectedMovement.HIGH
        if volatility_regime in {"HIGH", "VERY_HIGH"}
        or _value(getattr(volatility, "direction", None)) == "EXPANDING"
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
            freshness=(
                "RECENT" if macro_events else _freshness(states, ("macro", "onchain"))
            ),
            unavailable_reason="Calendrier et séries macro/liquidité indisponibles.",
        ),
        FutureFamily.CATALYSTS_REGULATION: FamilyAssessment(
            family=FutureFamily.CATALYSTS_REGULATION,
            available=catalyst_available,
            directional_bias=catalyst_direction if catalyst_available else None,
            expected_movement=_movement(catalyst_events, ExpectedMovement.NORMAL),
            confidence=max([event.confidence for event in catalyst_events], default=0.0),
            summary=(
                f"{len(catalyst_events)} catalyseur(s) réglementaire(s), protocolaire(s) "
                "ou géopolitique(s) sourcé(s)."
                if catalyst_events
                else ""
            ),
            reasons=[event.title for event in catalyst_events[:3]],
            sources=_event_sources(catalyst_events),
            as_of=as_of.isoformat(),
            freshness="RECENT" if catalyst_events else "UNAVAILABLE",
            unavailable_reason="Aucun catalyseur pertinent remonté par les sources configurées.",
        ),
        FutureFamily.FLOWS_WHALES: FamilyAssessment(
            family=FutureFamily.FLOWS_WHALES,
            available=bool(flow_components),
            directional_bias=flow_direction,
            expected_movement=ExpectedMovement.NORMAL,
            confidence=(
                float(getattr(flow_components[0], "confidence", 0.0))
                if flow_components
                else 0.0
            ),
            summary=(
                "; ".join(str(getattr(item, "detail", "")) for item in flow_components[:2])
                if flow_components
                else ""
            ),
            reasons=[str(getattr(item, "label", "")) for item in flow_components[:3]],
            sources=flow_sources,
            as_of=getattr(flow_components[0], "as_of", None) if flow_components else None,
            freshness=(
                _value(getattr(flow_components[0], "freshness", None), "UNAVAILABLE")
                if flow_components
                else "UNAVAILABLE"
            ),
            unavailable_reason="Flux institutionnels, spot et baleines indisponibles.",
        ),
        FutureFamily.POSITIONING_DERIVATIVES: FamilyAssessment(
            family=FutureFamily.POSITIONING_DERIVATIVES,
            available=positioning_available,
            directional_bias=(
                positioning_direction if positioning_available else None
            ),
            expected_movement=positioning_movement,
            confidence=(
                max(
                    [float(getattr(item, "confidence", 0.0)) for item in positioning_components]
                    + ([0.75] if dvol_available else [0.0])
                )
                if positioning_available
                else 0.0
            ),
            summary=(
                "; ".join(str(getattr(item, "detail", "")) for item in positioning_components[:2])
                or (
                    str(getattr(implied_volatility, "interpretation", ""))
                    if dvol_available
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
                min(0.9, (len(bullish) + len(bearish)) / 4)
                if technical_available
                else 0.0
            ),
            summary=(
                f"Structure haussière sur {len(bullish)} unité(s), baissière sur "
                f"{len(bearish)}; volatilité {volatility_regime.lower()}."
                if technical_available
                else ""
            ),
            reasons=[*(f"Structure haussière {item}" for item in bullish[:2]),
                     *(f"Structure baissière {item}" for item in bearish[:2])],
            sources=[_derived_source("MarketStructureEngine + VolatilityRegimeEngine", analysis_id, as_of)],
            as_of=as_of.isoformat(),
            freshness=_freshness(states, ("structure", "volatility")),
            unavailable_reason="Historique OHLCV insuffisant pour structure et volatilité.",
        ),
    }
    return FiveFamilySnapshot.from_partial(partial)

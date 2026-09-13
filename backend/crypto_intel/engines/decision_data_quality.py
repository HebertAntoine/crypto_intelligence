"""Decision-scoped input quality, with no synthetic quality score.

The four components answer different questions and deliberately remain
separate:

* coverage: how many horizon-relevant inputs are actually usable;
* freshness: the runtime state of every relevant input;
* source quality: whether the evidence is named, traceable and how it is tiered;
* critical missing inputs: the minimum market inputs without which a current
  directional decision is not defensible.

No component is collapsed into an arbitrary ``x/100`` number.  In particular,
an input that merely exists but is stale is counted as present and stale, never
as usable coverage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from ..core.data_integrity import is_production_label
from ..core.enums import Asset
from ..core.usability import freshness_for
from ..future_events.freshness import EventFreshness, event_freshness
from ..future_events.models import DecisionHorizon, FutureEvent
from .future_decision import FiveFamilySnapshot


class DecisionDataQualityStatus(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    INSUFFICIENT = "INSUFFICIENT"


@dataclass(frozen=True, slots=True)
class DecisionInputSpec:
    name: str
    critical: bool = False
    applicable_assets: frozenset[Asset] | None = None

    def applies_to(self, asset: Asset) -> bool:
        return self.applicable_assets is None or asset in self.applicable_assets


_ETF_ASSETS = frozenset({Asset.BTC, Asset.ETH})

# Requirements follow the units each horizon actually consumes.  Only price
# and the horizon's structural candle inputs are critical.  Missing context
# such as whales or expectations makes quality PARTIAL but does not pretend
# that no market reading at all can be made.
_INPUTS_BY_HORIZON: dict[DecisionHorizon, tuple[DecisionInputSpec, ...]] = {
    DecisionHorizon.H24: (
        DecisionInputSpec("price", critical=True),
        DecisionInputSpec("ohlcv_h1", critical=True),
        DecisionInputSpec("ohlcv_4h", critical=True),
        DecisionInputSpec("funding"),
        DecisionInputSpec("open_interest"),
        DecisionInputSpec("spot"),
        DecisionInputSpec("dvol", applicable_assets=_ETF_ASSETS),
        DecisionInputSpec("event_calendar"),
        DecisionInputSpec("market_rate_expectations"),
        DecisionInputSpec("whale_intelligence"),
    ),
    DecisionHorizon.D7: (
        DecisionInputSpec("price", critical=True),
        DecisionInputSpec("ohlcv_4h", critical=True),
        DecisionInputSpec("ohlcv_daily", critical=True),
        DecisionInputSpec("funding"),
        DecisionInputSpec("open_interest"),
        DecisionInputSpec("spot"),
        DecisionInputSpec("dvol", applicable_assets=_ETF_ASSETS),
        DecisionInputSpec("etf", applicable_assets=_ETF_ASSETS),
        DecisionInputSpec("macro"),
        DecisionInputSpec("onchain"),
        DecisionInputSpec("liquidity"),
        DecisionInputSpec("event_calendar"),
        DecisionInputSpec("market_rate_expectations"),
        DecisionInputSpec("whale_intelligence"),
    ),
    DecisionHorizon.D30: (
        DecisionInputSpec("price", critical=True),
        DecisionInputSpec("ohlcv_daily", critical=True),
        DecisionInputSpec("ohlcv_weekly", critical=True),
        DecisionInputSpec("macro"),
        DecisionInputSpec("cross_asset"),
        DecisionInputSpec("onchain"),
        DecisionInputSpec("liquidity"),
        DecisionInputSpec("etf", applicable_assets=_ETF_ASSETS),
        DecisionInputSpec("event_calendar"),
        DecisionInputSpec("market_rate_expectations"),
        DecisionInputSpec("whale_intelligence"),
    ),
}


@dataclass(slots=True)
class DecisionDataQuality:
    horizon: DecisionHorizon
    status: DecisionDataQualityStatus
    coverage: dict[str, Any]
    freshness: dict[str, Any]
    source_quality: dict[str, Any]
    critical_missing_inputs: list[str] = field(default_factory=list)
    missing_inputs: list[str] = field(default_factory=list)
    stale_inputs: list[str] = field(default_factory=list)

    @property
    def blocks_directional_decision(self) -> bool:
        return bool(self.critical_missing_inputs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "horizon": self.horizon.value,
            "coverage": self.coverage,
            "freshness": self.freshness,
            "source_quality": self.source_quality,
            "critical_missing_inputs": self.critical_missing_inputs,
            "missing_inputs": self.missing_inputs,
            "stale_inputs": self.stale_inputs,
            "blocks_directional_decision": self.blocks_directional_decision,
            "methodology": {
                "coverage": (
                    "Nombre d'entrées applicables présentes, valides et fraîches; "
                    "une entrée stale n'est jamais comptée comme utilisable."
                ),
                "freshness": (
                    "État runtime de chaque entrée selon la cadence propre à sa source."
                ),
                "source_quality": (
                    "Inventaire de provenance par tiers; aucun score numérique composite."
                ),
                "critical_missing_inputs": (
                    "Prix et bougies structurelles minimales propres à l'horizon."
                ),
            },
        }


def _state_reading(name: str, state: Any, critical: bool) -> dict[str, Any]:
    freshness = getattr(getattr(state, "freshness", None), "value", None)
    if freshness is None:
        freshness = str(getattr(state, "freshness", "UNAVAILABLE"))
    observed = getattr(state, "observed_at", None)
    return {
        "input": name,
        "critical": critical,
        "available": bool(getattr(state, "available", False)),
        "valid": bool(getattr(state, "valid", False)),
        "freshness": freshness,
        "usable": bool(getattr(state, "usable", False)),
        "observed_at": observed.isoformat() if isinstance(observed, datetime) else None,
        "source": str(getattr(state, "source", "") or "") or None,
        "reason": str(getattr(state, "reason", "") or "") or None,
    }


def _event_calendar_reading(
    events: list[FutureEvent], as_of: datetime, critical: bool
) -> dict[str, Any]:
    readings = [event_freshness(event, as_of) for event in events]
    usable = [
        item
        for item in readings
        if item.freshness_status in {EventFreshness.LIVE, EventFreshness.FRESH}
    ]
    newest = max((item.fetched_at for item in readings if item.fetched_at), default=None)
    status = (
        "LIVE"
        if any(item.freshness_status is EventFreshness.LIVE for item in usable)
        else "RECENT"
        if usable
        else "STALE"
        if readings
        else "UNAVAILABLE"
    )
    return {
        "input": "event_calendar",
        "critical": critical,
        "available": bool(readings),
        "valid": bool(readings),
        "freshness": status,
        "usable": bool(usable),
        "observed_at": newest.isoformat() if newest else None,
        "source": "sources officielles des événements" if events else None,
        "reason": None if usable else "aucun événement frais dans cette fenêtre",
    }


def _expectation_reading(
    events: list[FutureEvent], as_of: datetime, critical: bool
) -> dict[str, Any]:
    candidates = [
        event
        for event in events
        if event.market_probabilities and event.probability_timestamp is not None
    ]
    # Phase 4 only inventories an already sourced distribution.  It does not
    # create, fetch or infer FedWatch expectations.
    newest = max((event.probability_timestamp for event in candidates), default=None)
    expectation_freshness = freshness_for("market_expectations", newest, as_of)
    fresh = bool(newest and expectation_freshness.is_fresh)
    return {
        "input": "market_rate_expectations",
        "critical": critical,
        "available": bool(candidates),
        "valid": bool(candidates),
        "freshness": expectation_freshness.value,
        "usable": fresh,
        "observed_at": newest.isoformat() if newest else None,
        "source": candidates[0].market_probabilities[0].source if candidates else None,
        "reason": (
            None
            if fresh
            else "aucune distribution de marché horodatée et récente disponible"
        ),
    }


def _source_quality(
    readings: list[dict[str, Any]],
    events: list[FutureEvent],
    families: FiveFamilySnapshot,
) -> dict[str, Any]:
    sources: dict[tuple[str, str | None], dict[str, Any]] = {}

    def add(source: Any, tier: Any, url: Any = None) -> None:
        label = str(source or "").strip()
        if not label or not is_production_label(label):
            return
        normalized_tier = str(getattr(tier, "value", tier) or "UNKNOWN").upper()
        key = (label, str(url) if url else None)
        sources[key] = {"source": label, "tier": normalized_tier, "url": key[1]}

    for reading in readings:
        if reading["usable"]:
            add(reading.get("source"), "MEASURED")
    for event in events:
        add(event.source, event.source_tier, event.source_url)
    for assessment in families.assessments.values():
        if not assessment.available:
            continue
        for source in assessment.sources:
            add(source.get("source"), source.get("tier"), source.get("url"))

    values = list(sources.values())
    counts = {
        tier: sum(item["tier"] == tier for item in values)
        for tier in ("A", "B", "C", "D", "E", "MEASURED", "DERIVED", "UNKNOWN")
    }
    named = len(values)
    with_url = sum(bool(item["url"]) for item in values)
    lower_or_unknown = counts["D"] + counts["E"] + counts["UNKNOWN"]
    status = (
        "UNAVAILABLE"
        if not values
        else "PARTIAL"
        if lower_or_unknown or with_url < named
        else "TRACEABLE"
    )
    return {
        "status": status,
        "named_sources": named,
        "sources_with_url": with_url,
        "tiers": counts,
        "sources": values,
    }


class DecisionDataQualityEngine:
    """Assess the exact inputs used by one asset/horizon decision."""

    def assess(
        self,
        asset: Asset,
        horizon: DecisionHorizon,
        states: dict[str, Any],
        events: list[FutureEvent],
        families: FiveFamilySnapshot,
        *,
        as_of: datetime | None = None,
        calendar_events: list[FutureEvent] | None = None,
    ) -> DecisionDataQuality:
        reference = as_of or datetime.now(UTC)
        reference = (
            reference.replace(tzinfo=UTC)
            if reference.tzinfo is None
            else reference.astimezone(UTC)
        )
        specs = [spec for spec in _INPUTS_BY_HORIZON[horizon] if spec.applies_to(asset)]
        readings: list[dict[str, Any]] = []
        for spec in specs:
            if spec.name == "event_calendar":
                reading = _event_calendar_reading(
                    calendar_events if calendar_events is not None else events,
                    reference,
                    spec.critical,
                )
            elif spec.name == "market_rate_expectations":
                reading = _expectation_reading(events, reference, spec.critical)
            elif spec.name == "whale_intelligence":
                reading = _state_reading(spec.name, states.get("whales"), spec.critical)
            else:
                reading = _state_reading(spec.name, states.get(spec.name), spec.critical)
            readings.append(reading)

        usable = [item for item in readings if item["usable"]]
        present = [item for item in readings if item["available"]]
        stale = [
            item["input"]
            for item in readings
            if item["available"] and not item["usable"]
        ]
        missing = [item["input"] for item in readings if not item["available"]]
        critical_missing = [
            item["input"]
            for item in readings
            if item["critical"] and not item["usable"]
        ]
        if critical_missing:
            status = DecisionDataQualityStatus.INSUFFICIENT
        elif len(usable) < len(readings):
            status = DecisionDataQualityStatus.PARTIAL
        else:
            status = DecisionDataQualityStatus.COMPLETE

        freshness_status = (
            "FRESH"
            if len(usable) == len(readings)
            else "CRITICAL_INPUT_STALE"
            if critical_missing and any(name in stale for name in critical_missing)
            else "PARTIAL"
            if usable
            else "UNAVAILABLE"
        )
        return DecisionDataQuality(
            horizon=horizon,
            status=status,
            coverage={
                "usable_inputs": len(usable),
                "present_inputs": len(present),
                "applicable_inputs": len(readings),
                "label": f"{len(usable)}/{len(readings)} utilisables",
            },
            freshness={
                "status": freshness_status,
                "fresh_inputs": len(usable),
                "stale_inputs": len(stale),
                "unavailable_inputs": len(missing),
                "inputs": {item["input"]: item for item in readings},
            },
            source_quality=_source_quality(readings, events, families),
            critical_missing_inputs=critical_missing,
            missing_inputs=missing,
            stale_inputs=stale,
        )

"""Deterministic answer to “who buys, who sells?”.

Every available component is normalised to -100 (selling) .. +100 (buying),
then combined with an explicit weight and confidence. Missing data is removed
from the denominator and listed; it is never converted to a neutral zero.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from ..core.enums import Asset

ETF_ASSETS = (Asset.BTC, Asset.ETH)
STRONG_FLOW_MUSD = 1000.0


@dataclass(slots=True)
class PressureComponent:
    name: str
    label: str
    available: bool = False
    normalized_pressure: float | None = None
    raw_value: Any = None
    weight: float = 1.0
    confidence: float = 0.5
    detail: str = ""
    source: str = ""
    as_of: str | None = None
    freshness: str = "UNAVAILABLE"
    reason: str = ""

    @property
    def score(self) -> float | None:
        return self.normalized_pressure

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "label": self.label,
            "available": self.available,
            "normalized_pressure": self.normalized_pressure,
            "score": self.normalized_pressure,
            "raw_value": self.raw_value, "weight": self.weight,
            "confidence": self.confidence, "detail": self.detail,
            "source": self.source, "as_of": self.as_of,
            "freshness": self.freshness, "reason": self.reason,
        }


@dataclass(slots=True)
class MarketPressureExplanation:
    state: str = "INSUFFICIENT_DATA"
    pressure_score: float | None = None
    components: list[PressureComponent] = field(default_factory=list)
    contradictions: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    summary: str = ""
    as_of: str = ""
    asset: str = ""

    @property
    def balance(self) -> float | None:
        return None if self.pressure_score is None else (self.pressure_score + 100) / 2

    @property
    def label(self) -> str:
        return _label_fr(self.state)

    @property
    def measured(self) -> int:
        return sum(c.available and c.normalized_pressure is not None for c in self.components)

    @property
    def note(self) -> str:
        return self.summary

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state, "pressure_score": self.pressure_score,
            "components": [c.to_dict() for c in self.components],
            "contradictions": self.contradictions, "missing": self.missing,
            "summary": self.summary, "as_of": self.as_of, "asset": self.asset,
            # Backwards-compatible fields for an older Flutter client.
            "balance": round(self.balance, 1) if self.balance is not None else None,
            "label": self.label, "components_measured": self.measured,
            "components_missing": self.missing, "note": self.summary,
        }


MarketPressure = MarketPressureExplanation


def _source_state(family_states: dict[str, Any] | None, family: str) -> tuple[str | None, str]:
    state = (family_states or {}).get(family)
    if state is None:
        return None, "RECENT"
    observed = getattr(state, "observed_at", None)
    observed_at = observed.isoformat() if observed is not None else None
    freshness = getattr(getattr(state, "freshness", None), "value", "UNAVAILABLE")
    return observed_at, str(freshness)


def _institutional(asset: Asset) -> PressureComponent:
    component = PressureComponent(
        name="institutions", label="Institutions (ETF spot)", weight=.35,
        confidence=.95, source="Farside Investors, flux par émetteur",
    )
    if asset not in ETF_ASSETS:
        component.reason = f"aucun flux ETF spot {asset.value} suivi par cette source"
        return component

    from ..db import repo

    rows = repo.get_etf_flows(asset, days=45)
    if not rows:
        component.reason = "aucun flux ETF stocké"
        return component
    by_day: dict[str, float] = {}
    for row in rows:
        day = str(row["date"])[:10]
        by_day[day] = by_day.get(day, 0) + float(row["flow_musd"] or 0)
    days = sorted(by_day)
    recent_5 = days[-5:]
    recent_20 = days[-20:]
    net_5 = sum(by_day[day] for day in recent_5)
    net_20 = sum(by_day[day] for day in recent_20)
    latest = by_day[days[-1]]
    streak_direction = 1 if latest > 0 else -1 if latest < 0 else 0
    streak = 0
    for day in reversed(days):
        direction = 1 if by_day[day] > 0 else -1 if by_day[day] < 0 else 0
        if direction != streak_direction or direction == 0:
            break
        streak += 1
    age = (datetime.now(UTC).date() - datetime.fromisoformat(days[-1]).date()).days
    component.as_of = datetime.fromisoformat(days[-1]).replace(tzinfo=UTC).isoformat()
    component.freshness = "RECENT" if age <= 4 else "DELAYED" if age <= 7 else "STALE"
    component.raw_value = {
        "latest_musd": round(latest, 2), "net_5d_musd": round(net_5, 2),
        "net_20d_musd": round(net_20, 2), "streak_sessions": streak,
        "extreme": abs(latest) >= STRONG_FLOW_MUSD,
    }
    component.detail = (
        f"{latest:+,.0f} M$ dernière séance; {net_5:+,.0f} M$ sur 5 et "
        f"{net_20:+,.0f} M$ sur 20; série {streak} séance(s). "
        "Flux observés; leur avantage causal n’est pas supposé."
    )
    if age > 7:
        component.reason = f"dernière publication il y a {age} jours, trop ancienne"
        return component
    component.available = True
    component.normalized_pressure = max(-100, min(100, net_5 / STRONG_FLOW_MUSD * 100))
    return component


def _funding(asset: Asset, percentile: float | None, usable: bool,
             family_states: dict[str, Any] | None) -> PressureComponent:
    as_of, freshness = _source_state(family_states, "funding")
    component = PressureComponent(
        name="levier", label="Funding perpétuel", weight=.20,
        confidence=.7, source="funding.rate, percentile trailing par actif",
        as_of=as_of, freshness=freshness,
    )
    if percentile is None:
        component.reason = "historique insuffisant pour calculer le percentile"
        return component
    from ..history import store

    series = store.load_derivatives(asset, "funding.rate")
    current = float(series.iloc[-1]) if not series.empty else None
    change_24h = (
        float(current - series.iloc[-4])
        if current is not None and len(series) >= 4 else None
    )
    component.raw_value = {
        "value": current, "percentile": percentile,
        "change_24h": change_24h,
    }
    if not usable:
        component.reason = "dernière observation trop ancienne"
        return component
    component.available = True
    component.normalized_pressure = max(-100, min(100, (percentile - 50) * 2))
    # Le percentile et la variation brute restent dans raw_value, donc dans
    # les preuves. « variation 24 h -0.000006 » ne dit rien en première lecture.
    niveau = (
        "nettement au-dessus de sa normale" if percentile >= 75
        else "au-dessus de sa normale" if percentile >= 60
        else "nettement en dessous de sa normale" if percentile <= 25
        else "en dessous de sa normale" if percentile <= 40
        else "dans sa normale"
    )
    qui = (
        "les positions longues paient les shorts" if percentile >= 60
        else "les positions courtes paient les longs" if percentile <= 40
        else "aucun côté ne paie franchement"
    )
    component.detail = (
        f"Coût de portage {niveau} : {qui}. Un extrême signale surtout un coût "
        "et un encombrement, pas la suite du prix."
    )
    return component


def _positioning(asset: Asset, state: str, usable: bool,
                 family_states: dict[str, Any] | None) -> PressureComponent:
    as_of, freshness = _source_state(family_states, "open_interest")
    component = PressureComponent(
        name="positionnement", label="Prix + open interest", weight=.30,
        confidence=.75, source="OHLCV et open interest multi-exchange",
        as_of=as_of, freshness=freshness, raw_value={"state": state},
    )
    if not usable:
        component.reason = "open interest ou prix trop ancien"
        return component
    from ..history import store

    oi = store.load_derivatives(asset, "oi.contracts_bybit")
    if oi.empty:
        oi = store.load_derivatives(asset, "oi.value")
    daily = oi.resample("1D").last().dropna() if not oi.empty else oi
    latest_oi = float(daily.iloc[-1]) if not daily.empty else None
    change_7d = (
        float((daily.iloc[-1] / daily.iloc[-8] - 1) * 100)
        if len(daily) >= 8 and daily.iloc[-8] else None
    )
    acceleration = None
    if len(daily) >= 7:
        recent_change = float(daily.iloc[-1] / daily.iloc[-4] - 1)
        prior_change = float(daily.iloc[-4] / daily.iloc[-7] - 1)
        acceleration = (recent_change - prior_change) * 100
    component.raw_value = {
        "state": state, "open_interest": latest_oi,
        "change_7d_pct": change_7d, "acceleration_pct": acceleration,
    }
    score, detail = {
        "NEW_LONGS": (70, "prix et OI montent: nouvelles positions dans la hausse"),
        "NEW_SHORTS": (-70, "prix baisse et OI monte: nouvelles positions vendeuses"),
        "SHORT_COVERING": (30, "hausse avec OI en baisse: rachats de shorts"),
        "LONG_LIQUIDATION": (-30, "baisse avec OI en baisse: sorties de longs"),
        "DELEVERAGING": (0, "réduction du levier sans côté dominant"),
        "QUIET": (0, "aucun changement de positionnement marqué"),
        "BALANCED": (0, "les composantes mesurées se compensent"),
    }.get(state.upper(), (None, ""))
    if score is None:
        component.reason = f"état {state or 'inconnu'} non interprétable"
        return component
    component.available = True
    component.normalized_pressure = float(score)
    component.detail = detail + (
        f"; OI {change_7d:+.1f}% sur 7 j"
        if change_7d is not None else ""
    )
    return component


def _whales(analysis: Any | None) -> PressureComponent:
    component = PressureComponent(
        name="baleines", label="Baleines", weight=.25,
        source="fournisseur on-chain vérifié",
    )
    if analysis is None or not bool(getattr(analysis, "available", False)):
        component.reason = str(
            getattr(analysis, "unavailable_reason", "")
            or "aucun fournisseur fiable configuré; aucune direction n’est estimée"
        )
        return component
    reliability = str(getattr(getattr(analysis, "reliability", None), "value", "UNVERIFIED"))
    if reliability not in ("HIGH", "MEDIUM"):
        component.reason = f"source {reliability.lower()}, insuffisante pour affirmer une direction"
        return component
    component.available = True
    component.normalized_pressure = float(getattr(analysis, "strength", 0) or 0)
    component.confidence = float(getattr(analysis, "confidence", 0) or 0) / 100
    component.raw_value = {
        "exchange_netflow": getattr(analysis, "exchange_netflow", None),
        "reliability": reliability,
    }
    component.detail = "; ".join(getattr(analysis, "findings", [])[:2])
    component.freshness = str(getattr(getattr(analysis, "freshness", None),
                                      "value", "UNAVAILABLE"))
    return component


def _spot_flow() -> PressureComponent:
    return PressureComponent(
        name="flux_spot", label="Flux spot / exchanges", weight=.15,
        source="connecteur de flux spot/exchange",
        reason="aucune série fiable de flux net spot/exchange n’est configurée",
    )


def _state(score: float) -> str:
    if score >= 45:
        return "STRONG_BUYING"
    if score >= 15:
        return "BUYING"
    if score > -15:
        return "BALANCED"
    if score > -45:
        return "SELLING"
    return "STRONG_SELLING"


def _label_fr(state: str) -> str:
    return {
        "STRONG_BUYING": "ACHAT DOMINANT", "BUYING": "ACHAT LÉGER",
        "BALANCED": "ÉQUILIBRÉ", "SELLING": "VENTE LÉGÈRE",
        "STRONG_SELLING": "VENTE DOMINANTE",
        "INSUFFICIENT_DATA": "INDÉTERMINÉ",
    }.get(state, "INDÉTERMINÉ")


def assess_pressure(
    asset: Asset, *, funding_percentile: float | None, funding_usable: bool,
    leverage_state: str, positioning_usable: bool,
    whale_analysis: Any | None = None,
    family_states: dict[str, Any] | None = None,
) -> MarketPressureExplanation:
    components = [
        _institutional(asset),
        _funding(asset, funding_percentile, funding_usable, family_states),
        _positioning(asset, leverage_state, positioning_usable, family_states),
        _whales(whale_analysis),
        _spot_flow(),
    ]
    usable = [c for c in components
              if c.available and c.normalized_pressure is not None]
    now = datetime.now(UTC).isoformat()
    missing = [c.label for c in components if not c.available]
    if not usable:
        return MarketPressureExplanation(
            asset=asset.value, components=components, missing=missing, as_of=now,
            summary="Aucune composante actuelle et fiable ne permet d’établir la pression.",
        )

    denominator = sum(c.weight * c.confidence for c in usable)
    score = sum(
        float(c.normalized_pressure) * c.weight * c.confidence
        for c in usable if c.normalized_pressure is not None
    ) / denominator
    score = round(max(-100, min(100, score)), 1)
    contradictions: list[str] = []
    positive = [c for c in usable if float(c.normalized_pressure or 0) >= 20]
    negative = [c for c in usable if float(c.normalized_pressure or 0) <= -20]
    if positive and negative:
        contradictions.append(
            f"{positive[0].label} indique une pression acheteuse tandis que "
            f"{negative[0].label} indique une pression vendeuse."
        )
    state = _state(score)
    summary = (
        f"{_label_fr(state)} ({score:+.0f}/100), mesuré par {len(usable)} "
        f"composante(s) sur {len(components)}."
    )
    if contradictions:
        summary += " Les sources ne concordent pas entièrement."
    return MarketPressureExplanation(
        state=state, pressure_score=score, components=components,
        contradictions=contradictions, missing=missing, summary=summary,
        as_of=now, asset=asset.value,
    )

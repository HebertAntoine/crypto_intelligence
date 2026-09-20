"""Who is buying through regulated products - and whether the two sources agree.

Two independent measurements of institutional demand:

    Farside      daily net flow of the US spot ETFs, asset by asset
    CoinShares   weekly flows across every listed crypto product, worldwide

They answer different questions, so they can disagree, and a disagreement is
information. US ETFs taking money in while global products bleed says
something neither number says alone, so the reading keeps a DIVERGENCE state
instead of averaging the two into a comfortable middle.

A flow is never read as a verdict. "+2 bn this week" means nothing without the
size of the assets it lands on, the history it sits in and how long it has
lasted, so each source is expressed against its own past: a percentile, a
streak, an acceleration and, where the issuer publishes it, the share of
assets under management.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from ..core.enums import Asset
from .factor_semantics import fr_number
from .pit_view import PointInTimeView


class DemandState(StrEnum):
    STRONG_INFLOW = "STRONG_INFLOW"
    INFLOW = "INFLOW"
    NEUTRAL = "NEUTRAL"
    OUTFLOW = "OUTFLOW"
    STRONG_OUTFLOW = "STRONG_OUTFLOW"
    DIVERGENCE = "DIVERGENCE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


STATE_FR = {
    DemandState.STRONG_INFLOW: "Entrées fortes",
    DemandState.INFLOW: "Entrées",
    DemandState.NEUTRAL: "Flux neutres",
    DemandState.OUTFLOW: "Sorties",
    DemandState.STRONG_OUTFLOW: "Sorties fortes",
    DemandState.DIVERGENCE: "Divergence entre les sources",
    DemandState.INSUFFICIENT_DATA: "Données insuffisantes",
}
STATE_EMOJI = {
    DemandState.STRONG_INFLOW: "🟢",
    DemandState.INFLOW: "🟢",
    DemandState.NEUTRAL: "🟡",
    DemandState.OUTFLOW: "🔴",
    DemandState.STRONG_OUTFLOW: "🔴",
    DemandState.DIVERGENCE: "🟠",
    DemandState.INSUFFICIENT_DATA: "⚪",
}

#: A weekly report older than this describes a market that has moved on.
COINSHARES_MAX_AGE = timedelta(days=14)
#: A daily ETF file older than this (weekends included) is not current.
ETF_MAX_AGE = timedelta(days=4)


@dataclass(slots=True)
class SourceReading:
    name: str
    available: bool
    stale: bool = False
    latest_at: datetime | None = None
    windows: dict[str, float] = field(default_factory=dict)
    streak: int = 0
    percentile: float | None = None
    share_of_aum_pct: float | None = None
    acceleration: float | None = None
    note: str = ""

    @property
    def direction(self) -> int:
        """+1, -1 or 0 - from the window this source actually measures."""

        if not self.available or self.stale or not self.windows:
            return 0
        reference = self.windows.get("7d", next(iter(self.windows.values())))
        return 1 if reference > 0 else -1 if reference < 0 else 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "available": self.available,
            "stale": self.stale,
            "latest_at": self.latest_at.isoformat() if self.latest_at else None,
            "windows": {k: round(v, 1) for k, v in self.windows.items()},
            "streak": self.streak,
            "percentile": round(self.percentile, 0) if self.percentile is not None else None,
            "share_of_aum_pct": (
                round(self.share_of_aum_pct, 2) if self.share_of_aum_pct is not None else None
            ),
            "acceleration": round(self.acceleration, 1) if self.acceleration is not None else None,
            "direction": self.direction,
            "note": self.note,
        }


@dataclass(slots=True)
class InstitutionalDemand:
    asset: str
    state: DemandState
    etf: SourceReading
    coinshares: SourceReading
    sentences: list[str] = field(default_factory=list)
    as_of: datetime | None = None

    @property
    def label(self) -> str:
        return STATE_FR[self.state]

    @property
    def emoji(self) -> str:
        return STATE_EMOJI[self.state]

    @property
    def divergent(self) -> bool:
        return self.state is DemandState.DIVERGENCE

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset": self.asset,
            "state": self.state.value,
            "label": self.label,
            "emoji": self.emoji,
            "divergence": self.divergent,
            "etf": self.etf.to_dict(),
            "coinshares": self.coinshares.to_dict(),
            "sentences": self.sentences,
            "explanation": " ".join(self.sentences),
            "as_of": self.as_of.isoformat() if self.as_of else None,
            "note": (
                "Un flux ne vaut pas un signal d'achat : il est lu par rapport à son "
                "historique, à sa durée et à la taille des encours."
            ),
        }


def _percentile(value: float, history: list[float]) -> float | None:
    if len(history) < 20:
        return None
    below = sum(1 for h in history if h < value)
    equal = sum(1 for h in history if h == value)
    return 100 * (below + 0.5 * equal) / len(history)


def _etf_reading(view: PointInTimeView, asset: Asset) -> SourceReading:
    points = view.points("etf.net_flow", asset.value)
    if not points:
        return SourceReading("ETF au comptant (États-Unis)", available=False,
                             note="Aucun ETF au comptant vérifié pour cet actif.")
    last = points[-1]
    stale = view.as_of - last.available_at > ETF_MAX_AGE
    values = [p.value for p in points]
    windows = {
        "1d": values[-1],
        "7d": sum(values[-5:]),
        "30d": sum(values[-20:]),
    }
    streak = 0
    for value in reversed(values):
        if value == 0 or (streak and (value > 0) != (streak > 0)):
            break
        streak += 1 if value > 0 else -1
    history = [sum(values[i - 5:i]) for i in range(5, len(values))][-250:]
    five = sum(values[-5:]) / 5
    twenty = sum(values[-20:]) / 20 if len(values) >= 20 else None
    return SourceReading(
        name="ETF au comptant (États-Unis)",
        available=True,
        stale=stale,
        latest_at=last.timestamp,
        windows=windows,
        streak=streak,
        percentile=_percentile(windows["7d"], history),
        acceleration=(five - twenty) if twenty is not None else None,
        note="Flux quotidiens publiés le lendemain." + (" Fichier périmé." if stale else ""),
    )


def _coinshares_reading(view: PointInTimeView, asset: Asset) -> SourceReading:
    per_asset = view.points("flows.coinshares.asset", asset.value)
    global_points = view.points("flows.coinshares.global")
    aum_points = view.points("flows.coinshares.aum")
    if not per_asset and not global_points:
        return SourceReading("Produits d'investissement (monde)", available=False,
                             note="Rapport hebdomadaire non disponible.")
    source = per_asset or global_points
    last = source[-1]
    stale = view.as_of - last.timestamp > COINSHARES_MAX_AGE
    values = [p.value / 1e6 for p in source]  # en M$, comme les flux ETF
    windows = {"7d": values[-1], "4w": sum(values[-4:])}
    streak = 0
    for value in reversed(values):
        if value == 0 or (streak and (value > 0) != (streak > 0)):
            break
        streak += 1 if value > 0 else -1
    share = None
    if aum_points and per_asset:
        aum = aum_points[-1].value
        if aum:
            share = 100 * (last.value / aum)
    return SourceReading(
        name="Produits d'investissement (monde)",
        available=True,
        stale=stale,
        latest_at=last.timestamp,
        windows=windows,
        streak=streak,
        percentile=_percentile(values[-1], values[:-1]),
        share_of_aum_pct=share,
        note=(
            f"Rapport hebdomadaire du {last.timestamp:%d/%m}."
            + (" Plus ancien que sa propre cadence : lu comme périmé." if stale else "")
        ),
    )


def _strength(reading: SourceReading) -> str:
    """STRONG / NORMAL, from the reading's own history rather than a round number."""

    if reading.percentile is None:
        return "NORMAL"
    if reading.percentile >= 90 or reading.percentile <= 10:
        return "STRONG"
    return "NORMAL"


def read_demand(view: PointInTimeView, asset: Asset) -> InstitutionalDemand:
    etf = _etf_reading(view, asset)
    coinshares = _coinshares_reading(view, asset)
    usable = [r for r in (etf, coinshares) if r.available and not r.stale and r.windows]
    demand = InstitutionalDemand(asset=asset.value, state=DemandState.INSUFFICIENT_DATA,
                                 etf=etf, coinshares=coinshares, as_of=view.as_of)
    if not usable:
        demand.sentences = [
            "Aucune source institutionnelle exploitable : "
            + " ".join(r.note for r in (etf, coinshares) if r.note)
        ]
        return demand

    directions = {r.name: r.direction for r in usable}
    signs = {d for d in directions.values() if d != 0}
    if len(signs) > 1:
        # Both measured, and they disagree: say so rather than blend it.
        demand.state = DemandState.DIVERGENCE
    else:
        direction = next(iter(signs), 0)
        strong = any(_strength(r) == "STRONG" for r in usable if r.direction == direction)
        demand.state = {
            1: DemandState.STRONG_INFLOW if strong else DemandState.INFLOW,
            -1: DemandState.STRONG_OUTFLOW if strong else DemandState.OUTFLOW,
            0: DemandState.NEUTRAL,
        }[direction]
    demand.sentences = _explain(demand, usable)
    return demand


def _explain(demand: InstitutionalDemand, usable: list[SourceReading]) -> list[str]:
    out: list[str] = []
    etf, coinshares = demand.etf, demand.coinshares
    if etf.available and not etf.stale:
        week = etf.windows.get("7d", 0.0)
        out.append(
            f"💵 ETF au comptant : {fr_number(week, 0, signed=True)} M$ sur cinq séances"
            + (f", {abs(etf.streak)} séances d'affilée" if abs(etf.streak) >= 3 else "")
            + "."
        )
    if coinshares.available:
        week = coinshares.windows.get("7d", 0.0)
        out.append(
            f"🌍 Produits d'investissement dans le monde : {fr_number(week, 0, signed=True)} M$ "
            f"sur la semaine publiée"
            + (" (rapport plus ancien que sa cadence)." if coinshares.stale else ".")
        )
    if demand.divergent:
        out.append(
            "⚠️ Les deux sources ne disent pas la même chose : la demande américaine et la "
            "demande mondiale divergent. Aucune des deux n'est masquée."
        )
    elif demand.state in {DemandState.STRONG_INFLOW, DemandState.STRONG_OUTFLOW}:
        source = next((r for r in usable if _strength(r) == "STRONG"), None)
        if source is not None and source.percentile is not None:
            out.append(
                f"L'ampleur est inhabituelle pour cette source ({fr_number(source.percentile, 0)}e "
                "centile de son propre historique)."
            )
    if coinshares.share_of_aum_pct is not None:
        out.append(
            f"Cela représente {fr_number(abs(coinshares.share_of_aum_pct), 2)} % des encours."
        )
    return out[:4]

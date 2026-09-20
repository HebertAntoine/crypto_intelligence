"""Is the market rising, or are a few assets rising?

A price going up explains nothing on its own. This engine answers a narrower
question: *who* is taking part. It reads several independent measures and
returns one regime.

    participation   how many of the top 100 beat Bitcoin, how many simply rose
    concentration   BTC dominance and its trend, share of volume outside BTC
    rotation        ETH/BTC, TOTAL2 and TOTAL3 against TOTAL
    dispersion      how far apart the performances are

Two rules matter more than the thresholds:

*No single measure decides.* An "altcoin season" reading in particular needs
four independent confirmations; a high participation number on its own gives
at most ALTSEASON_EARLY.

*The published 90-day index is not reproduced.* CoinMarketCap's altcoin season
index uses a 90-day window and a licensed API. The free market data exposes
24 h, 7 d and 30 d, so the reading is computed on those and says so. Nothing
here claims to be that index.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from ..core.enums import Asset, Timeframe
from .factor_semantics import fr_number
from .pit_view import PointInTimeView


class BreadthRegime(StrEnum):
    BTC_LED_RALLY = "BTC_LED_RALLY"
    ETH_LED_RALLY = "ETH_LED_RALLY"
    BROAD_CRYPTO_RALLY = "BROAD_CRYPTO_RALLY"
    SELECTIVE_ALT_RALLY = "SELECTIVE_ALT_RALLY"
    ALTSEASON_EARLY = "ALTSEASON_EARLY"
    ALTSEASON_CONFIRMED = "ALTSEASON_CONFIRMED"
    RISK_OFF = "RISK_OFF"
    MIXED = "MIXED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


REGIME_FR = {
    BreadthRegime.BTC_LED_RALLY: "Hausse menée par Bitcoin",
    BreadthRegime.ETH_LED_RALLY: "Hausse menée par Ethereum",
    BreadthRegime.BROAD_CRYPTO_RALLY: "Hausse large du marché",
    BreadthRegime.SELECTIVE_ALT_RALLY: "Hausse sélective sur quelques altcoins",
    BreadthRegime.ALTSEASON_EARLY: "Début de rotation vers les altcoins",
    BreadthRegime.ALTSEASON_CONFIRMED: "Rotation altcoins confirmée",
    BreadthRegime.RISK_OFF: "Aversion au risque",
    BreadthRegime.MIXED: "Participation mitigée",
    BreadthRegime.INSUFFICIENT_DATA: "Données insuffisantes",
}
REGIME_EMOJI = {
    BreadthRegime.BTC_LED_RALLY: "🟠",
    BreadthRegime.ETH_LED_RALLY: "🟠",
    BreadthRegime.BROAD_CRYPTO_RALLY: "🟢",
    BreadthRegime.SELECTIVE_ALT_RALLY: "🟠",
    BreadthRegime.ALTSEASON_EARLY: "🔵",
    BreadthRegime.ALTSEASON_CONFIRMED: "🟢",
    BreadthRegime.RISK_OFF: "🔴",
    BreadthRegime.MIXED: "🟡",
    BreadthRegime.INSUFFICIENT_DATA: "⚪",
}

#: Every condition an "altcoin season" claim must satisfy, each independent.
ALTSEASON_CONDITIONS = (
    ("outperform_30d", 65.0, "Une majorité nette du top 100 surperforme BTC sur 30 jours"),
    ("outperform_7d", 60.0, "La surperformance se prolonge sur 7 jours"),
    ("positive_30d", 60.0, "La majorité du marché progresse réellement"),
    ("alt_volume_share", 55.0, "Les volumes se déplacent hors de Bitcoin"),
)
#: Freshness: participation is a market reading, worthless when old.
MAX_AGE = timedelta(hours=12)


@dataclass(slots=True)
class BreadthReading:
    regime: BreadthRegime
    measures: dict[str, float] = field(default_factory=dict)
    ages: dict[str, float] = field(default_factory=dict)
    confirmations: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    sentences: list[str] = field(default_factory=list)
    as_of: datetime | None = None

    @property
    def label(self) -> str:
        return REGIME_FR[self.regime]

    @property
    def emoji(self) -> str:
        return REGIME_EMOJI[self.regime]

    @property
    def altseason_confirmed(self) -> bool:
        return self.regime is BreadthRegime.ALTSEASON_CONFIRMED

    def to_dict(self) -> dict[str, Any]:
        return {
            "regime": self.regime.value,
            "label": self.label,
            "emoji": self.emoji,
            "measures": {k: round(v, 2) for k, v in self.measures.items()},
            "confirmations": self.confirmations,
            "altseason_conditions": [
                {"key": key, "threshold": threshold, "text": text,
                 "met": self.measures.get(key) is not None and self.measures[key] >= threshold}
                for key, threshold, text in ALTSEASON_CONDITIONS
            ],
            "missing": self.missing,
            "sentences": self.sentences,
            "explanation": " ".join(self.sentences),
            "as_of": self.as_of.isoformat() if self.as_of else None,
            "window_note": (
                "Participation mesurée sur 24 h, 7 j et 30 j. La fenêtre de 90 jours de "
                "l'indice publié demande une clé sous licence : elle n'est pas reproduite ici."
            ),
        }


def _measure(view: PointInTimeView, metric: str, key: str,
             measures: dict[str, float], ages: dict[str, float], missing: list[str],
             label: str) -> None:
    point = view.latest(metric)
    if point is None:
        missing.append(label)
        return
    age = (view.as_of - point.timestamp).total_seconds() / 3600
    if age > MAX_AGE.total_seconds() / 3600:
        missing.append(f"{label} (périmée, {fr_number(age, 0)} h)")
        return
    measures[key] = float(point.value)
    ages[key] = age


def _change_pct(view: PointInTimeView, metric: str, days: int, asset: str | None = None) -> float | None:
    points = view.points(metric, asset)
    if len(points) < 2:
        return None
    last = points[-1]
    before = next((p for p in reversed(points) if p.timestamp <= last.timestamp - timedelta(days=days)), None)
    if before is None or not before.value:
        return None
    return (last.value / before.value - 1) * 100


def _ratio_change(view: PointInTimeView, numerator: str, denominator: str, days: int) -> float | None:
    own = view.candles(numerator, Timeframe.D1)
    base = view.candles(denominator, Timeframe.D1)
    if len(own) <= days or len(base) <= days:
        return None
    now = float(own["close"].iloc[-1]) / float(base["close"].iloc[-1])
    then = float(own["close"].iloc[-days - 1]) / float(base["close"].iloc[-days - 1])
    return (now / then - 1) * 100 if then else None


def read_breadth(view: PointInTimeView) -> BreadthReading:
    measures: dict[str, float] = {}
    ages: dict[str, float] = {}
    missing: list[str] = []

    _measure(view, "breadth.outperform_btc_30d_pct", "outperform_30d", measures, ages, missing,
             "Surperformance vs BTC (30 j)")
    _measure(view, "breadth.outperform_btc_7d_pct", "outperform_7d", measures, ages, missing,
             "Surperformance vs BTC (7 j)")
    _measure(view, "breadth.outperform_btc_24h_pct", "outperform_24h", measures, ages, missing,
             "Surperformance vs BTC (24 h)")
    _measure(view, "breadth.positive_30d_pct", "positive_30d", measures, ages, missing,
             "Part en hausse (30 j)")
    _measure(view, "breadth.positive_7d_pct", "positive_7d", measures, ages, missing,
             "Part en hausse (7 j)")
    _measure(view, "breadth.alt_volume_share_pct", "alt_volume_share", measures, ages, missing,
             "Part des volumes hors BTC")
    _measure(view, "breadth.dispersion_30d", "dispersion_30d", measures, ages, missing,
             "Dispersion des performances")

    dominance = view.latest("market.dominance", "BTC")
    if dominance is not None:
        measures["btc_dominance"] = float(dominance.value)
        change = _change_pct(view, "market.dominance", 30, "BTC")
        if change is not None:
            measures["btc_dominance_change_30d"] = change
    else:
        missing.append("Dominance BTC")

    eth_btc = _ratio_change(view, "ETH", "BTC", 30)
    if eth_btc is not None:
        measures["eth_btc_change_30d"] = eth_btc
    total2 = _change_pct(view, "market.total2", 30)
    if total2 is not None:
        measures["total2_change_30d"] = total2
    total3 = _change_pct(view, "market.total3", 30)
    if total3 is not None:
        measures["total3_change_30d"] = total3
    btc_daily = view.candles("BTC", Timeframe.D1)
    if len(btc_daily) > 31:
        measures["btc_change_30d"] = (
            float(btc_daily["close"].iloc[-1]) / float(btc_daily["close"].iloc[-31]) - 1
        ) * 100
    stable = _change_pct(view, "stablecoin.supply.total", 30)
    if stable is not None:
        measures["stablecoin_change_30d"] = stable

    reading = BreadthReading(regime=BreadthRegime.INSUFFICIENT_DATA, measures=measures,
                             ages=ages, missing=missing, as_of=view.as_of)
    if "outperform_30d" not in measures or "positive_30d" not in measures:
        reading.sentences = [
            "La participation du marché n'est pas mesurable : "
            + (", ".join(missing[:3]) or "données absentes") + "."
        ]
        return reading

    reading.regime = _classify(measures)
    reading.confirmations = [
        text for key, threshold, text in ALTSEASON_CONDITIONS
        if measures.get(key) is not None and measures[key] >= threshold
    ]
    reading.sentences = _explain(reading.regime, measures)
    return reading


def _classify(m: dict[str, float]) -> BreadthRegime:
    outperform_30 = m.get("outperform_30d", 0.0)
    outperform_7 = m.get("outperform_7d", outperform_30)
    positive_30 = m.get("positive_30d", 0.0)
    positive_7 = m.get("positive_7d", positive_30)
    btc_30 = m.get("btc_change_30d")
    dominance_change = m.get("btc_dominance_change_30d")
    eth_btc = m.get("eth_btc_change_30d")
    dispersion = m.get("dispersion_30d")

    met = sum(
        1 for key, threshold, _ in ALTSEASON_CONDITIONS
        if m.get(key) is not None and m[key] >= threshold
    )
    # Four independent confirmations, and a dominance that actually falls.
    if met == len(ALTSEASON_CONDITIONS) and (dominance_change is not None and dominance_change < 0):
        return BreadthRegime.ALTSEASON_CONFIRMED
    if positive_30 <= 30 and (btc_30 is None or btc_30 < 0):
        return BreadthRegime.RISK_OFF
    if outperform_30 >= 55 and positive_7 >= 55 and (
        (dominance_change is not None and dominance_change < 0)
        or (eth_btc is not None and eth_btc > 0)
    ):
        return BreadthRegime.ALTSEASON_EARLY
    if btc_30 is not None and btc_30 > 0:
        if positive_30 >= 70 and 40 <= outperform_30 < 65:
            return BreadthRegime.BROAD_CRYPTO_RALLY
        if eth_btc is not None and eth_btc >= 5 and outperform_30 < 55:
            return BreadthRegime.ETH_LED_RALLY
        if outperform_30 < 40 and (dominance_change is None or dominance_change >= 0):
            return BreadthRegime.BTC_LED_RALLY
        if dispersion is not None and dispersion >= 40 and positive_30 < 60:
            return BreadthRegime.SELECTIVE_ALT_RALLY
    if outperform_7 >= 55 and positive_7 >= 55 and (btc_30 is not None and btc_30 <= 0):
        return BreadthRegime.SELECTIVE_ALT_RALLY
    return BreadthRegime.MIXED


def _explain(regime: BreadthRegime, m: dict[str, float]) -> list[str]:
    """Three or four plain sentences - never a certainty the data cannot carry."""

    out: list[str] = []
    outperform_30 = m.get("outperform_30d")
    positive_30 = m.get("positive_30d")
    dominance = m.get("btc_dominance")
    dominance_change = m.get("btc_dominance_change_30d")

    lead = {
        BreadthRegime.ALTSEASON_CONFIRMED: "La participation s'est élargie.",
        BreadthRegime.ALTSEASON_EARLY: "La participation s'élargit.",
        BreadthRegime.BROAD_CRYPTO_RALLY: "La hausse est large : la majorité du marché progresse.",
        BreadthRegime.BTC_LED_RALLY: "La hausse reste menée par Bitcoin.",
        BreadthRegime.ETH_LED_RALLY: "La hausse est menée par Ethereum.",
        BreadthRegime.SELECTIVE_ALT_RALLY: "La hausse reste concentrée sur quelques actifs.",
        BreadthRegime.RISK_OFF: "Le marché recule de façon généralisée.",
        BreadthRegime.MIXED: "La participation est mitigée.",
        BreadthRegime.INSUFFICIENT_DATA: "La participation n'est pas mesurable.",
    }[regime]
    out.append(lead)
    if outperform_30 is not None:
        out.append(
            f"{fr_number(outperform_30, 0)} % du top 100 surperforme Bitcoin sur 30 jours"
            + (f", {fr_number(positive_30, 0)} % progressent réellement." if positive_30 is not None else ".")
        )
    if dominance is not None:
        trend = (
            "recule" if dominance_change is not None and dominance_change < -0.5
            else "progresse" if dominance_change is not None and dominance_change > 0.5
            else "reste stable"
        )
        out.append(f"La dominance de Bitcoin {trend} ({fr_number(dominance, 1)} %).")
    if regime in {BreadthRegime.BTC_LED_RALLY, BreadthRegime.SELECTIVE_ALT_RALLY, BreadthRegime.MIXED}:
        out.append(
            "Il est donc prématuré de parler d'une rotation généralisée vers les altcoins."
        )
    elif regime is BreadthRegime.ALTSEASON_EARLY:
        out.append(
            "Les conditions deviennent compatibles avec une rotation, sans être toutes réunies."
        )
    elif regime is BreadthRegime.ALTSEASON_CONFIRMED:
        out.append("Les quatre conditions indépendantes suivies ici sont réunies.")
    return out


def breadth_for(view: PointInTimeView, asset: Asset | None = None) -> BreadthReading:
    """Entry point used by the analysts and the API."""

    return read_breadth(view)

"""Qui achète, qui vend — et à quel point nous avons le droit de l'affirmer.

Deux mesures distinctes sortent d'ici, et les confondre était le défaut.

  PRESSION    dans quel sens penchent les familles qui ont répondu
  COUVERTURE  combien de familles pertinentes ont réellement répondu

Un score de +61 calculé sur une seule famille sur cinq n'est pas un « achat
dominant » : c'est une lecture indicative appuyée sur presque rien. Le
vocabulaire est donc verrouillé par la couverture, et le mot « dominant » ne
peut sortir qu'au-dessus d'un seuil des deux.

Trois règles gouvernent le calcul :

  * une source absente sort du dénominateur, elle ne devient jamais un zéro —
    « pas de donnée » et « pas de pression » sont deux affirmations
    différentes, et confondre la première avec la seconde tire silencieusement
    chaque score vers le neutre ;
  * une famille qui n'a structurellement aucun sens pour un actif est
    NON APPLICABLE et ne compte pas non plus dans le dénominateur : il n'existe
    pas d'ETF spot SOL, et le compter comme un trou signalerait un défaut de
    données là où il y a un fait de marché ;
  * une hausse d'open interest n'est pas un achat. Un future a un long ET un
    short pour chaque contrat. La direction se lit sur le prix, l'OI, la
    répartition des comptes et le funding ensemble, jamais sur l'OI seul.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from ..core.enums import Asset

ETF_ASSETS = (Asset.BTC, Asset.ETH)

# Un flux ETF d'un milliard sur cinq séances est un mouvement franc; c'est
# l'échelle qui sature la normalisation, pas un seuil de décision.
STRONG_FLOW_MUSD = 1000.0

# Part du volume spot exécutée à l'achat agressif. 0,5 est l'équilibre exact;
# l'échelle est resserrée parce que le ratio quotidien sort rarement de
# [0,45 ; 0,55] et qu'une normalisation large écraserait tout vers zéro.
TAKER_NEUTRAL = 0.5
TAKER_FULL_SCALE = 0.04


class Direction(StrEnum):
    """Le sens d'une famille, nommé plutôt que laissé à un nombre."""

    STRONG_SELL = "STRONG_SELL"
    SELL = "SELL"
    SLIGHT_SELL = "SLIGHT_SELL"
    NEUTRAL = "NEUTRAL"
    SLIGHT_BUY = "SLIGHT_BUY"
    BUY = "BUY"
    STRONG_BUY = "STRONG_BUY"
    UNAVAILABLE = "UNAVAILABLE"

    @classmethod
    def of(cls, score: float | None) -> Direction:
        if score is None:
            return cls.UNAVAILABLE
        if score >= 60:
            return cls.STRONG_BUY
        if score >= 25:
            return cls.BUY
        if score > 8:
            return cls.SLIGHT_BUY
        if score >= -8:
            return cls.NEUTRAL
        if score > -25:
            return cls.SLIGHT_SELL
        if score > -60:
            return cls.SELL
        return cls.STRONG_SELL


DIRECTION_FR: dict[str, str] = {
    "STRONG_BUY": "Acheteur marqué", "BUY": "Acheteur",
    "SLIGHT_BUY": "Acheteur léger", "NEUTRAL": "Neutre",
    "SLIGHT_SELL": "Vendeur léger", "SELL": "Vendeur",
    "STRONG_SELL": "Vendeur marqué", "UNAVAILABLE": "Indisponible",
}

DIRECTION_DOT: dict[str, str] = {
    "STRONG_BUY": "🟢", "BUY": "🟢", "SLIGHT_BUY": "🟢", "NEUTRAL": "⚪",
    "SLIGHT_SELL": "🟠", "SELL": "🔴", "STRONG_SELL": "🔴", "UNAVAILABLE": "⚪",
}


@dataclass(slots=True)
class PressureFamilyContribution:
    """Une famille, avec tout ce qu'il faut pour refaire le calcul à la main."""

    family: str
    label: str
    asset: str = ""
    applicable: bool = True
    available: bool = False
    direction: Direction = Direction.UNAVAILABLE
    raw_value: Any = None
    normalized_score: float | None = None
    weight: float = 0.0
    # Poids théorique renormalisé sur les familles qui ont répondu. C'est lui
    # qui multiplie le score, donc c'est lui qu'il faut montrer à côté de la
    # contribution: afficher le poids théorique laissait croire à deux
    # arithmétiques différentes.
    effective_weight: float | None = None
    weighted_contribution: float | None = None
    source: str = ""
    # L'heure de l'événement décrit, celle de l'observation, et celle de son
    # arrivée chez nous: trois moments différents qu'un seul horodatage
    # confondait.
    event_time: str | None = None
    observation_time: str | None = None
    ingested_at: str | None = None
    freshness: str = "UNAVAILABLE"
    data_quality: str = "UNAVAILABLE"
    explanation: str = ""
    reason: str = ""

    # --- compatibilité avec le client déployé -----------------------------
    @property
    def name(self) -> str:
        return self.family

    @property
    def score(self) -> float | None:
        return self.normalized_score

    @property
    def normalized_pressure(self) -> float | None:
        return self.normalized_score

    @property
    def confidence(self) -> float:
        return {"MEASURED": 0.9, "DERIVED": 0.75, "PARTIAL": 0.5}.get(
            self.data_quality, 0.0
        )

    @property
    def detail(self) -> str:
        return self.explanation

    @property
    def as_of(self) -> str | None:
        return self.observation_time

    @property
    def direction_label(self) -> str:
        return DIRECTION_FR[self.direction.value]

    def to_dict(self) -> dict[str, Any]:
        return {
            "family": self.family, "name": self.family, "label": self.label,
            "asset": self.asset,
            "applicable": self.applicable, "available": self.available,
            "direction": self.direction.value,
            "direction_label": self.direction_label,
            "dot": DIRECTION_DOT[self.direction.value],
            "raw_value": self.raw_value,
            "normalized_score": self.normalized_score,
            "score": self.normalized_score,
            "normalized_pressure": self.normalized_score,
            "weight": self.weight,
            "effective_weight": self.effective_weight,
            "weighted_contribution": self.weighted_contribution,
            "source": self.source,
            "event_time": self.event_time,
            "observation_time": self.observation_time,
            "ingested_at": self.ingested_at,
            "as_of": self.observation_time,
            "freshness": self.freshness,
            "data_quality": self.data_quality,
            "confidence": self.confidence,
            "explanation": self.explanation,
            "detail": self.explanation,
            "reason": self.reason,
        }


# Poids, documentés et fixes. Ils disent l'importance relative d'une famille
# quand elle répond, pas une probabilité. Ils somment à 1 sur les cinq, mais le
# dénominateur réel est la somme des poids des familles réellement disponibles.
WEIGHTS: dict[str, float] = {
    "institutions": 0.30,   # de l'argent réel, mais publié une fois par séance
    "spot": 0.25,           # le côté agresseur de transactions réellement passées
    "derivatives": 0.20,    # positionnement, ambigu pris isolément
    "funding": 0.15,        # coût de portage; un extrême dit l'encombrement
    "whales": 0.10,         # quand une source vérifiée existe
}

# Intensité et couverture répondent à deux questions et se lisaient comme une
# seule. « +30/100 · 4/5 familles · Forte » laissait entendre que la pression
# était forte, alors que « Forte » qualifiait la couverture et que +30 est une
# pression modérée. Les deux échelles sont désormais séparées, et leurs bornes
# vivent dans `config/thresholds.yaml` — un seuil dupliqué dans un widget est
# un seuil qui finira par contredire le moteur.
def _intensity_thresholds() -> dict[str, float]:
    from ..config_loader import threshold

    raw = threshold("pressure", "intensity", default={}) or {}
    return {
        "strong_buy": float(raw.get("strong_buy", 60)),
        "buy": float(raw.get("buy", 25)),
        "neutral_band": float(raw.get("neutral_band", 24)),
        "sell": float(raw.get("sell", -25)),
        "strong_sell": float(raw.get("strong_sell", -60)),
    }


def _coverage_thresholds() -> dict[str, int]:
    from ..config_loader import threshold

    raw = threshold("pressure", "coverage", default={}) or {}
    return {
        "excellent": int(raw.get("excellent", 5)),
        "good": int(raw.get("good", 4)),
        "partial": int(raw.get("partial", 3)),
    }


def minimum_families() -> int:
    """En dessous, aucune conclusion de pression n'est produite.

    Deux familles sur cinq ne disent pas « marché équilibré » : elles disent
    que nous ne savons pas. Afficher 0/100 dans ce cas serait une conclusion
    tirée d'une absence.
    """
    from ..config_loader import threshold

    return int(threshold("pressure", "minimum_families", default=3) or 3)


class Intensity(StrEnum):
    """Ce que dit le score, indépendamment de sa couverture."""

    STRONG_BUYING = "STRONG_BUYING"
    BUYING = "BUYING"
    BALANCED = "BALANCED"
    SELLING = "SELLING"
    STRONG_SELLING = "STRONG_SELLING"
    INSUFFICIENT = "INSUFFICIENT"

    @classmethod
    def of(cls, score: float | None) -> Intensity:
        if score is None:
            return cls.INSUFFICIENT
        limits = _intensity_thresholds()
        if score >= limits["strong_buy"]:
            return cls.STRONG_BUYING
        if score >= limits["buy"]:
            return cls.BUYING
        if score <= limits["strong_sell"]:
            return cls.STRONG_SELLING
        if score <= limits["sell"]:
            return cls.SELLING
        return cls.BALANCED


INTENSITY_FR: dict[str, str] = {
    "STRONG_BUYING": "FORTE PRESSION ACHETEUSE",
    "BUYING": "PRESSION ACHETEUSE",
    "BALANCED": "ÉQUILIBRÉE",
    "SELLING": "PRESSION VENDEUSE",
    "STRONG_SELLING": "FORTE PRESSION VENDEUSE",
    "INSUFFICIENT": "DONNÉES INSUFFISANTES",
}


class CoverageLevel(StrEnum):
    """Combien de familles applicables ont répondu — jamais une intensité."""

    NONE = "NONE"
    LOW = "LOW"
    PARTIAL = "PARTIAL"
    GOOD = "GOOD"
    EXCELLENT = "EXCELLENT"


COVERAGE_FR: dict[str, str] = {
    "NONE": "Aucune", "LOW": "Faible", "PARTIAL": "Partielle",
    "GOOD": "Bonne", "EXCELLENT": "Excellente",
}


@dataclass(slots=True)
class MarketPressureExplanation:
    """La pression, sa couverture, et le vocabulaire que les deux autorisent."""

    asset: str = ""
    state: str = "INSUFFICIENT_DATA"
    pressure_score: float | None = None
    families: list[PressureFamilyContribution] = field(default_factory=list)
    contradictions: list[str] = field(default_factory=list)
    summary: str = ""
    as_of: str = ""
    denominator: float = 0.0

    # --- couverture -------------------------------------------------------
    @property
    def applicable(self) -> list[PressureFamilyContribution]:
        return [item for item in self.families if item.applicable]

    @property
    def measured(self) -> list[PressureFamilyContribution]:
        return [
            item for item in self.applicable
            if item.available and item.normalized_score is not None
        ]

    @property
    def coverage_ratio(self) -> float:
        """Part du poids applicable qui a effectivement répondu."""
        total = sum(WEIGHTS[item.family] for item in self.applicable)
        if total <= 0:
            return 0.0
        return sum(WEIGHTS[item.family] for item in self.measured) / total

    @property
    def coverage_level(self) -> CoverageLevel:
        """Classée sur le nombre de familles, pas sur leur poids.

        La ligne affichée compte des familles (« 4/5 ») ; classer sur le poids
        produisait des paires contradictoires — SOL affichait « 3/4 » avec un
        niveau calculé à 86 %, deux mesures différentes présentées comme une.
        """
        count = len(self.measured)
        if count == 0:
            return CoverageLevel.NONE
        limits = _coverage_thresholds()
        if count >= limits["excellent"]:
            return CoverageLevel.EXCELLENT
        if count >= limits["good"]:
            return CoverageLevel.GOOD
        if count >= limits["partial"]:
            return CoverageLevel.PARTIAL
        return CoverageLevel.LOW

    @property
    def has_enough_families(self) -> bool:
        return len(self.measured) >= minimum_families()

    @property
    def intensity(self) -> Intensity:
        """L'intensité ne se prononce pas sans un minimum de familles."""
        if not self.has_enough_families:
            return Intensity.INSUFFICIENT
        return Intensity.of(self.pressure_score)

    @property
    def coverage_line(self) -> str:
        return f"{len(self.measured)}/{len(self.applicable)} familles"

    @property
    def breakdown_line(self) -> str:
        """« 2 acheteuses · 1 vendeuse · 1 neutre · 1 indisponible »."""
        buying = sum(
            1 for item in self.measured
            if item.direction in (Direction.STRONG_BUY, Direction.BUY,
                                  Direction.SLIGHT_BUY)
        )
        selling = sum(
            1 for item in self.measured
            if item.direction in (Direction.STRONG_SELL, Direction.SELL,
                                  Direction.SLIGHT_SELL)
        )
        neutral = sum(
            1 for item in self.measured if item.direction is Direction.NEUTRAL
        )
        unavailable = len(self.applicable) - len(self.measured)
        parts = []
        if buying:
            parts.append(f"{buying} acheteuse{'s' if buying > 1 else ''}")
        if selling:
            parts.append(f"{selling} vendeuse{'s' if selling > 1 else ''}")
        if neutral:
            parts.append(f"{neutral} neutre{'s' if neutral > 1 else ''}")
        if unavailable:
            parts.append(
                f"{unavailable} indisponible{'s' if unavailable > 1 else ''}"
            )
        return " · ".join(parts)

    @property
    def label(self) -> str:
        """Le titre affiché : l'intensité seule, jamais la couverture.

        L'ancien titre fusionnait les deux — « PRESSION ACHETEUSE PARTIELLE »
        décrivait un score par un adjectif de couverture, et « 4/5 · Forte »
        juste en dessous laissait lire « forte pression ». Le titre dit
        maintenant ce que vaut le score ; la couverture se lit à côté, avec
        ses propres mots.
        """
        if not self.has_enough_families:
            return INTENSITY_FR["INSUFFICIENT"]
        return INTENSITY_FR[self.intensity.value]

    @property
    def coverage_label(self) -> str:
        return COVERAGE_FR[self.coverage_level.value]

    # --- compatibilité ----------------------------------------------------
    @property
    def components(self) -> list[PressureFamilyContribution]:
        return self.families

    @property
    def missing(self) -> list[str]:
        return [
            item.label for item in self.applicable
            if not item.available
        ]

    @property
    def balance(self) -> float | None:
        return None if self.pressure_score is None else (self.pressure_score + 100) / 2

    @property
    def note(self) -> str:
        return self.summary

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset": self.asset,
            "state": self.state,
            "pressure_score": self.pressure_score,
            "label": self.label,
            "families": [item.to_dict() for item in self.families],
            "components": [item.to_dict() for item in self.families],
            "intensity": self.intensity.value,
            "intensity_label": INTENSITY_FR[self.intensity.value],
            "coverage": {
                "measured": len(self.measured),
                "applicable": len(self.applicable),
                "line": self.coverage_line,
                "breakdown": self.breakdown_line,
                "ratio": round(self.coverage_ratio, 3),
                "level": self.coverage_level.value,
                "label": self.coverage_label,
                "sufficient": self.has_enough_families,
                "minimum": minimum_families(),
            },
            "contradictions": self.contradictions,
            "missing": self.missing,
            "components_missing": self.missing,
            "components_measured": len(self.measured),
            "summary": self.summary,
            "note": self.summary,
            "as_of": self.as_of,
            "balance": round(self.balance, 1) if self.balance is not None else None,
            "method": {
                "formula": (
                    "score = Σ(score_normalisé × poids) / Σ(poids des familles "
                    "disponibles)"
                ),
                "denominator": round(self.denominator, 4),
                "weights": WEIGHTS,
                "bounds": [-100, 100],
                "missing_data": (
                    "retirée du dénominateur, jamais convertie en zéro"
                ),
                "not_applicable": (
                    "retirée du dénominateur et du décompte de couverture"
                ),
                "intensity_scale": _intensity_thresholds(),
                "coverage_scale": _coverage_thresholds(),
                "insufficient_below": (
                    f"moins de {minimum_families()} familles disponibles : "
                    "aucune intensité n'est annoncée"
                ),
            },
            "caveat": (
                "Cette lecture décrit la pression relative des familles "
                "disponibles. Elle n'est ni une probabilité de hausse ni un "
                "avantage statistique démontré."
            ),
        }


MarketPressure = MarketPressureExplanation
PressureComponent = PressureFamilyContribution


# --- les cinq familles ----------------------------------------------------

def _freshness_of(observed: datetime | None, live_s: int, recent_s: int) -> tuple[str, bool]:
    """Fraîcheur mesurée contre la cadence de publication de la source.

    Une valeur de funding vieille de dix heures n'est pas périmée : c'est la
    valeur courante, parce que le funding ne se règle que toutes les huit
    heures. Juger chaque famille contre une horloge unique rendait la moitié
    d'entre elles inutilisables alors qu'elles étaient à jour.
    """
    if observed is None:
        return "UNAVAILABLE", False
    age = (datetime.now(UTC) - observed).total_seconds()
    if age < -300:
        return "UNAVAILABLE", False
    if age <= live_s:
        return "LIVE", True
    if age <= recent_s:
        return "RECENT", True
    if age <= recent_s * 3:
        return "DELAYED", False
    return "STALE", False


def _institutions(asset: Asset) -> PressureFamilyContribution:
    """Flux ETF spot, l'argent institutionnel réellement entré ou sorti."""
    item = PressureFamilyContribution(
        family="institutions", label="ETF / Institutions", asset=asset.value,
        weight=WEIGHTS["institutions"],
        source="Farside Investors, flux quotidiens par émetteur",
    )
    if asset not in ETF_ASSETS:
        item.applicable = False
        item.reason = (
            f"aucun ETF spot {asset.value} n'existe sur les marchés suivis; "
            "ce n'est pas une donnée manquante"
        )
        return item

    from ..db import repo

    rows = repo.get_etf_flows(asset, days=45)
    if not rows:
        item.reason = "aucun flux ETF stocké"
        return item

    by_day: dict[str, float] = {}
    for row in rows:
        by_day[str(row["date"])[:10]] = by_day.get(str(row["date"])[:10], 0) + float(
            row["flow_musd"] or 0
        )
    days = sorted(by_day)
    latest_day = datetime.fromisoformat(days[-1]).replace(tzinfo=UTC)
    net_5 = sum(by_day[day] for day in days[-5:])
    net_20 = sum(by_day[day] for day in days[-20:])
    latest = by_day[days[-1]]

    # Publié une fois par séance, et pas le week-end: quatre jours restent la
    # dernière publication disponible, pas une donnée périmée.
    item.freshness, fresh = _freshness_of(latest_day, 172800, 432000)
    item.event_time = latest_day.isoformat()
    item.observation_time = latest_day.isoformat()
    item.raw_value = {
        "latest_musd": round(latest, 2), "net_5d_musd": round(net_5, 2),
        "net_20d_musd": round(net_20, 2), "sessions": len(days),
    }
    if not fresh:
        item.reason = (
            f"dernière publication le {days[-1]}, au-delà de la cadence de "
            "publication de cette source"
        )
        return item

    item.available = True
    item.data_quality = "MEASURED"
    item.normalized_score = max(-100, min(100, net_5 / STRONG_FLOW_MUSD * 100))
    item.direction = Direction.of(item.normalized_score)
    item.explanation = (
        "Les flux récents sont positifs." if net_5 > 0
        else "Les flux récents sont négatifs." if net_5 < 0
        else "Les flux récents s'annulent."
    )
    return item


def _spot(asset: Asset) -> PressureFamilyContribution:
    """Part du volume spot exécutée par des acheteurs agressifs.

    Chaque transaction a un acheteur et un vendeur, donc le volume seul ne dit
    rien. Ce que dit ce ratio est qui a traversé le spread — la comptabilité de
    l'exchange, pas une déduction.
    """
    from ..history import store

    item = PressureFamilyContribution(
        family="spot", label="Spot / agressivité", asset=asset.value,
        weight=WEIGHTS["spot"],
        source="Binance klines, taker buy base volume / volume total",
    )
    series = store.load_derivatives(asset, "spot.taker_buy_ratio")
    if series.empty:
        item.reason = "aucune série d'agressivité spot stockée"
        return item

    observed = series.index[-1].to_pydatetime()
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=UTC)
    item.event_time = observed.isoformat()
    item.observation_time = observed.isoformat()
    # Bougies journalières: la barre du jour est la plus récente qui existe.
    item.freshness, fresh = _freshness_of(observed, 93600, 172800)

    latest = float(series.iloc[-1])
    window = series.iloc[-5:]
    mean_5 = float(window.mean())
    baseline = series.iloc[-90:] if len(series) >= 90 else series
    typical = float(baseline.mean())
    item.raw_value = {
        "taker_buy_ratio": round(latest, 4),
        "mean_5d": round(mean_5, 4),
        "baseline_90d": round(typical, 4),
        "sessions": len(series),
    }
    if not fresh:
        item.reason = "dernière bougie spot trop ancienne"
        return item

    item.available = True
    item.data_quality = "MEASURED"
    # Mesuré contre la normale propre à l'actif plutôt que contre 0,5: certaines
    # paires tournent structurellement un peu au-dessus ou au-dessous.
    centre = typical if len(baseline) >= 30 else TAKER_NEUTRAL
    item.normalized_score = max(
        -100, min(100, (mean_5 - centre) / TAKER_FULL_SCALE * 100)
    )
    item.direction = Direction.of(item.normalized_score)
    item.explanation = (
        "Les acheteurs traversent le spread plus souvent que d'habitude."
        if item.normalized_score > 8
        else "Les vendeurs traversent le spread plus souvent que d'habitude."
        if item.normalized_score < -8
        else "Acheteurs et vendeurs se croisent à leur rythme habituel."
    )
    return item


def _derivatives(asset: Asset, leverage_state: str) -> PressureFamilyContribution:
    """Positionnement à terme: prix, open interest et répartition des comptes.

    Une hausse d'open interest n'est pas un achat — il y a un short en face de
    chaque long. Le sens vient de la combinaison : l'OI monte-t-il pendant que
    le prix monte, et les comptes basculent-ils du côté long ?
    """
    from ..history import store

    item = PressureFamilyContribution(
        family="derivatives", label="Dérivés / positionnement", asset=asset.value,
        weight=WEIGHTS["derivatives"],
        source="open interest multi-exchange et répartition des comptes Binance",
    )
    oi = store.load_derivatives(asset, "oi.contracts_bybit")
    if oi.empty:
        oi = store.load_derivatives(asset, "oi.value")
    accounts = store.load_derivatives(asset, "derivatives.long_account_share")
    if oi.empty and accounts.empty:
        item.reason = "ni open interest ni répartition des comptes stockés"
        return item

    observed = None
    for series in (oi, accounts):
        if series.empty:
            continue
        last = series.index[-1].to_pydatetime()
        if last.tzinfo is None:
            last = last.replace(tzinfo=UTC)
        observed = last if observed is None else max(observed, last)
    item.event_time = observed.isoformat() if observed else None
    item.observation_time = item.event_time
    item.freshness, fresh = _freshness_of(observed, 43200, 129600)

    daily = oi.resample("1D").last().dropna() if not oi.empty else oi
    change_7d = (
        float((daily.iloc[-1] / daily.iloc[-8] - 1) * 100)
        if len(daily) >= 8 and daily.iloc[-8] else None
    )
    long_share = float(accounts.iloc[-1]) if not accounts.empty else None
    long_share_change = (
        float(accounts.iloc[-1] - accounts.iloc[-7])
        if len(accounts) >= 7 else None
    )
    item.raw_value = {
        "state": leverage_state or None,
        "oi_change_7d_pct": change_7d,
        "long_account_share": long_share,
        "long_share_change": long_share_change,
    }
    if not fresh:
        item.reason = "open interest et répartition des comptes trop anciens"
        return item

    # L'état joint prix/OI donne le sens; la bascule des comptes le confirme ou
    # le tempère. Aucun des deux n'est lu seul.
    base, sentence = {
        "NEW_LONGS": (55, "Le prix monte avec l'open interest : de nouveaux longs entrent."),
        "NEW_SHORTS": (-55, "Le prix baisse avec l'open interest : de nouveaux shorts entrent."),
        "SHORT_COVERING": (25, "L'open interest recule dans la hausse : des shorts se rachètent."),
        "LONG_LIQUIDATION": (-25, "L'open interest recule dans la baisse : des longs sortent."),
        "DELEVERAGING": (0, "Le levier se réduit sans côté dominant."),
        "QUIET": (0, "Aucun changement de positionnement marqué."),
        "BALANCED": (0, "Les composantes mesurées se compensent."),
    }.get((leverage_state or "").upper(), (None, ""))

    if base is None and long_share_change is None:
        item.reason = f"état {leverage_state or 'inconnu'} non interprétable"
        return item

    score = float(base or 0)
    if long_share_change is not None:
        # Un basculement d'un point de pourcentage des comptes vers le long est
        # un mouvement net à cette échelle.
        score += max(-30, min(30, long_share_change * 100 * 3))
        if base is None:
            sentence = (
                "Les comptes basculent vers le long."
                if long_share_change > 0
                else "Les comptes basculent vers le short."
            )
    item.available = True
    item.data_quality = "MEASURED" if not accounts.empty else "PARTIAL"
    item.normalized_score = max(-100, min(100, score))
    item.direction = Direction.of(item.normalized_score)
    item.explanation = sentence or "Positionnement sans direction nette."
    return item


def _funding(
    asset: Asset, percentile: float | None
) -> PressureFamilyContribution:
    """Coût de portage des perpétuels, situé dans son propre historique."""
    from ..history import store

    item = PressureFamilyContribution(
        family="funding", label="Funding / levier", asset=asset.value,
        weight=WEIGHTS["funding"],
        source="funding.rate Binance, percentile glissant par actif",
    )
    series = store.load_derivatives(asset, "funding.rate")
    if series.empty:
        item.reason = "aucune série de funding stockée"
        return item

    observed = series.index[-1].to_pydatetime()
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=UTC)
    item.event_time = observed.isoformat()
    item.observation_time = observed.isoformat()
    # Le funding se règle toutes les huit heures: dix heures est la valeur
    # courante, pas une valeur périmée.
    item.freshness, fresh = _freshness_of(observed, 32400, 46800)

    current = float(series.iloc[-1])
    item.raw_value = {"value": current, "percentile": percentile}
    if percentile is None:
        item.reason = "historique insuffisant pour situer le niveau actuel"
        return item
    if not fresh:
        item.reason = "dernier règlement de funding trop ancien"
        return item

    item.available = True
    item.data_quality = "MEASURED"
    # Le funding dit surtout le coût et l'encombrement; son signe directionnel
    # est réel mais faible, d'où une échelle volontairement compressée.
    item.normalized_score = max(-100, min(100, (percentile - 50) * 1.4))
    item.direction = Direction.of(item.normalized_score)
    item.explanation = (
        "Les longs paient nettement pour rester en position."
        if percentile >= 75
        else "Les shorts paient nettement pour rester en position."
        if percentile <= 25
        else "Le coût du levier reste proche de sa normale."
    )
    return item


def _whales(analysis: Any | None) -> PressureFamilyContribution:
    """Flux des gros portefeuilles vers et depuis les exchanges.

    Aucune source gratuite ne fournit l'attribution d'adresses aux exchanges,
    qui est précisément ce qui coûte de l'argent chez Glassnode, CryptoQuant ou
    Nansen. Rien n'est estimé à la place : un signal baleine fabriqué est l'une
    des sorties les plus dangereuses que cet outil puisse produire.
    """
    item = PressureFamilyContribution(
        family="whales", label="Baleines / flux exchanges",
        weight=WEIGHTS["whales"],
        source="fournisseur on-chain avec attribution d'adresses",
        # Le nom de la variable d'environnement est un détail de configuration
        # et reste dans la documentation: il n'a rien à faire sous les yeux
        # d'un lecteur de la page.
        reason=(
            "aucun fournisseur configuré : l'attribution des adresses aux "
            "exchanges demande un abonnement payant (Glassnode, CryptoQuant, "
            "Nansen)."
        ),
    )
    if analysis is None or not bool(getattr(analysis, "available", False)):
        return item
    reliability = str(getattr(getattr(analysis, "reliability", None), "value", "UNVERIFIED"))
    if reliability not in ("HIGH", "MEDIUM"):
        item.reason = f"source {reliability.lower()}, insuffisante pour affirmer une direction"
        return item
    item.available = True
    item.data_quality = "MEASURED"
    item.normalized_score = float(getattr(analysis, "strength", 0) or 0)
    item.direction = Direction.of(item.normalized_score)
    item.freshness = str(getattr(getattr(analysis, "freshness", None), "value", "RECENT"))
    item.observation_time = item.event_time
    item.raw_value = {"exchange_netflow": getattr(analysis, "exchange_netflow", None)}
    item.explanation = "; ".join(getattr(analysis, "findings", [])[:1])
    return item


def assess_pressure(
    asset: Asset, *, funding_percentile: float | None = None,
    funding_usable: bool = True, leverage_state: str = "",
    positioning_usable: bool = True,
    whale_analysis: Any | None = None,
    family_states: dict[str, Any] | None = None,
) -> MarketPressureExplanation:
    """Assemble les cinq familles, puis un score et une couverture séparés.

    `funding_usable` et `positioning_usable` restent acceptés pour les appelants
    existants mais ne gouvernent plus la disponibilité : chaque famille juge sa
    propre fraîcheur contre la cadence de sa source, ce qu'une horloge unique
    ne pouvait pas faire correctement.
    """
    families = [
        _institutions(asset),
        _spot(asset),
        _derivatives(asset, leverage_state),
        _funding(asset, funding_percentile),
        _whales(whale_analysis),
    ]
    now = datetime.now(UTC).isoformat()
    out = MarketPressureExplanation(asset=asset.value, families=families, as_of=now)

    measured = out.measured
    if not measured:
        out.summary = (
            "Aucune famille actuelle et fiable ne permet d'établir la pression."
        )
        return out

    # Une seule formule, documentée et reproductible:
    #   poids effectif = poids / somme des poids disponibles
    #   score          = Σ(score famille × poids effectif),  borné à [-100, 100]
    # Une famille absente sort du dénominateur; elle ne vaut ni 0 ni neutre.
    denominator = sum(item.weight for item in measured)
    out.denominator = denominator
    exact = 0.0
    for item in measured:
        effective = item.weight / denominator
        item.effective_weight = round(effective, 4)
        contribution = float(item.normalized_score or 0) * effective
        exact += contribution
        item.weighted_contribution = round(contribution, 2)
    out.pressure_score = round(max(-100.0, min(100.0, exact)), 1)
    out.state = Direction.of(out.pressure_score).value

    positive = [item for item in measured if (item.normalized_score or 0) >= 20]
    negative = [item for item in measured if (item.normalized_score or 0) <= -20]
    if positive and negative:
        out.contradictions.append(
            f"{positive[0].label} penche à l'achat pendant que "
            f"{negative[0].label} penche à la vente."
        )

    if not out.has_enough_families:
        # Deux familles sur cinq ne disent pas « marché équilibré »: elles
        # disent que nous ne savons pas. Le score reste calculé et auditable,
        # mais aucune intensité n'est annoncée.
        out.summary = (
            f"Données insuffisantes pour déterminer la pression : "
            f"{out.coverage_line} disponibles, {minimum_families()} au minimum."
        )
        return out

    out.summary = (
        f"{out.label} ({out.pressure_score:+.0f}/100), sur "
        f"{out.coverage_line} applicables."
    )
    if out.contradictions:
        out.summary += " Les familles ne concordent pas entièrement."
    return out

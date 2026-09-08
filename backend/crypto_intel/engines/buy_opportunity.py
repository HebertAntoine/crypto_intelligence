"""Deterministic, source-backed explanation of a buy opportunity.

This is the last analytical layer. It normalises existing engine outputs,
ranks the evidence, applies explicit guard rails and returns a complete UI
payload. It never calls an LLM and never invents a missing measurement.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, ClassVar

from ..core import labels_fr
from ..core.enums import Asset

# Le régime en français. L'enum reste la vérité interne; il ne doit pas
# traverser jusqu'à l'écran, où « Régime strongly bullish » était lisible.
# La table est partagée: cf. `core/labels_fr.py`.
_REGIME_FR = labels_fr.REGIME_FR


class BuyOpportunityState(StrEnum):
    """Les six états, et rien d'autre.

    Une version précédente gardait VERY_FAVORABLE / FAVORABLE avec des alias
    pointant dessus. Les alias ne changent pas la valeur sérialisée: le payload
    d'ETH sortait « FAVORABLE », un état que l'interface ne sait pas nommer.
    """

    STRONG_OPPORTUNITY = "STRONG_OPPORTUNITY"
    OPPORTUNITY = "OPPORTUNITY"
    WATCH = "WATCH"
    WAIT = "WAIT"
    UNFAVORABLE = "UNFAVORABLE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class Polarity(StrEnum):
    POSITIVE = "POSITIVE"
    WAIT = "WAIT"
    NEGATIVE = "NEGATIVE"
    NEUTRAL = "NEUTRAL"
    MISSING = "MISSING"

    SUPPORTS = "POSITIVE"
    OPPOSES = "NEGATIVE"


class Category(StrEnum):
    REGIME = "REGIME"
    STRUCTURE = "STRUCTURE"
    LOCATION = "LOCATION"
    ENTRY_TIMING = "ENTRY_TIMING"
    MEASURED_EDGE = "MEASURED_EDGE"
    FUNDING = "FUNDING"
    OPEN_INTEREST = "OPEN_INTEREST"
    CROWDING = "CROWDING"
    POSITIONING = "POSITIONING"
    VOLATILITY = "VOLATILITY"
    DVOL = "DVOL"
    ETF = "ETF"
    LIQUIDITY = "LIQUIDITY"
    ONCHAIN = "ONCHAIN"
    CROSS_ASSET = "CROSS_ASSET"
    MACRO = "MACRO"
    NEWS = "NEWS"
    WHALES = "WHALES"
    HISTORICAL_ANALOGS = "HISTORICAL_ANALOGS"
    LIVE_TRACK_RECORD = "LIVE_TRACK_RECORD"
    UNCERTAINTY = "UNCERTAINTY"
    DATA_QUALITY = "DATA_QUALITY"

    TREND = "REGIME"
    DERIVATIVES = "POSITIONING"


@dataclass(slots=True)
class DecisionFactor:
    """One auditable decision input; normalised values use -100..+100."""

    id: str
    category: Category
    title: str
    short_text: str
    raw_value: Any = None
    normalized_value: float | None = None
    polarity: Polarity = Polarity.NEUTRAL
    importance: int = 50
    confidence: float = 0.5
    evidence_level: str = "COMPUTATION"
    timeframe: str = "NOW"
    source: str = ""
    as_of: str | None = None
    freshness: str = "UNAVAILABLE"
    available: bool = True

    @property
    def explanation(self) -> str:
        return self.short_text

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "category": self.category.value,
            "title": self.title, "short_text": self.short_text,
            "explanation": self.short_text, "raw_value": self.raw_value,
            "normalized_value": self.normalized_value,
            "polarity": self.polarity.value, "importance": self.importance,
            "confidence": round(max(0.0, min(1.0, self.confidence)), 3),
            "evidence_level": self.evidence_level, "timeframe": self.timeframe,
            "source": self.source, "as_of": self.as_of,
            "freshness": self.freshness, "available": self.available,
        }


Factor = DecisionFactor


class DecisionFactorRanker:
    """Rank importance, abnormality, change, event proximity and evidence."""

    evidence: ClassVar[dict[str, float]] = {"FACT": 1.0, "COMPUTATION": .9, "INTERPRETATION": .65,
                "HYPOTHESIS": .25, "MISSING": 0.0}
    freshness: ClassVar[dict[str, float]] = {"LIVE": 1.0, "RECENT": .9, "MIN_15": .9, "HOUR_1": .8,
                 "TODAY": .7, "DELAYED": .4, "STALE": .15,
                 "UNAVAILABLE": 0.0}

    @staticmethod
    def _hint(factor: DecisionFactor, key: str) -> float:
        if not isinstance(factor.raw_value, dict):
            return 0.0
        try:
            return max(0.0, min(1.0, float(factor.raw_value.get(key, 0))))
        except (TypeError, ValueError):
            return 0.0

    def score(self, factor: DecisionFactor) -> float:
        return (
            factor.importance * .34
            + abs(factor.normalized_value or 0) * .18
            + factor.confidence * 14
            + self.evidence.get(factor.evidence_level.upper(), .4) * 11
            + self.freshness.get(factor.freshness.upper(), .35) * 9
            + self._hint(factor, "recent_change") * 5
            + self._hint(factor, "event_proximity") * 5
            + self._hint(factor, "contradiction") * 2
            + self._hint(factor, "historical_evidence") * 1.5
            + self._hint(factor, "data_quality") * .5
        )

    def rank(self, factors: Iterable[DecisionFactor], polarity: Polarity,
             limit: int = 5) -> list[DecisionFactor]:
        selected = [factor for factor in factors if factor.polarity is polarity]
        # Dédoublonner sur le texte affiché: deux moteurs peuvent signaler la
        # même lacune, et la voir écrite deux fois de suite donne l'impression
        # de deux problèmes distincts.
        seen: set[tuple[str, str]] = set()
        unique: list[DecisionFactor] = []
        for factor in sorted(selected, key=lambda f: (-self.score(f), f.id)):
            key = (factor.title, factor.short_text)
            if key in seen:
                continue
            seen.add(key)
            unique.append(factor)
        return unique[:limit]


@dataclass(slots=True)
class BuyOpportunityExplanation:
    state: BuyOpportunityState
    summary: str
    positives: list[DecisionFactor] = field(default_factory=list)
    waits: list[DecisionFactor] = field(default_factory=list)
    negatives: list[DecisionFactor] = field(default_factory=list)
    missing: list[DecisionFactor] = field(default_factory=list)
    improvement_conditions: list[ChangeCondition] = field(default_factory=list)
    deterioration_conditions: list[ChangeCondition] = field(default_factory=list)

    # Troisième catégorie, distincte des deux autres: un changement de
    # structure n'a pas de signe. Une cassure du haut de range invalide le
    # range sans dégrader le marché.
    structure_change_conditions: list[ChangeCondition] = field(default_factory=list)
    as_of: str = ""
    provenance: dict[str, Any] = field(default_factory=dict)
    score: float | None = None
    factors: list[DecisionFactor] = field(default_factory=list)
    guard_rails_applied: list[str] = field(default_factory=list)
    measured_edge_state: str = "NO_MEASURABLE_EDGE"

    @property
    def headline(self) -> str:
        return HEADLINES[self.state]

    @property
    def short_summary(self) -> str:
        return self.summary

    @property
    def what_would_improve(self) -> list[str]:
        return self.improvement_conditions

    @property
    def what_would_deteriorate(self) -> list[str]:
        return self.deterioration_conditions

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value, "headline": self.headline,
            "summary": self.summary, "short_summary": self.summary,
            "positives": [f.to_dict() for f in self.positives],
            "waits": [f.to_dict() for f in self.waits],
            "negatives": [f.to_dict() for f in self.negatives],
            "missing": [f.to_dict() for f in self.missing],
            # Structuré pour la page, en phrases pour les clients plus
            # anciens qui n'attendaient qu'une liste de textes.
            "improvement_conditions": [
                item.to_dict() for item in self.improvement_conditions
            ],
            "deterioration_conditions": [
                item.to_dict() for item in self.deterioration_conditions
            ],
            "structure_change_conditions": [
                item.to_dict() for item in self.structure_change_conditions
            ],
            "what_would_improve": [
                item.sentence for item in self.improvement_conditions
            ],
            "what_would_deteriorate": [
                item.sentence for item in self.deterioration_conditions
            ],
            "what_would_change_structure": [
                item.sentence for item in self.structure_change_conditions
            ],
            "guard_rails_applied": self.guard_rails_applied,
            "measured_edge_state": self.measured_edge_state,
            "score": self.score, "as_of": self.as_of,
            "provenance": self.provenance,
            "disclaimer": (
                "Évaluation déterministe du contexte, pas une garantie de "
                "performance ni un conseil. L’application ne passe aucun ordre."
            ),
        }


HEADLINES = {
    BuyOpportunityState.STRONG_OPPORTUNITY: "OPPORTUNITÉ FORTE",
    BuyOpportunityState.OPPORTUNITY: "OUI, CONTEXTE FAVORABLE",
    BuyOpportunityState.WATCH: "À SURVEILLER",
    BuyOpportunityState.WAIT: "ATTENDRE",
    BuyOpportunityState.UNFAVORABLE: "NON, CONTEXTE DÉFAVORABLE",
    BuyOpportunityState.INSUFFICIENT_DATA: "DONNÉES INSUFFISANTES",
}
BASE_MAPPING = {
    "VERY_FAVORABLE": BuyOpportunityState.STRONG_OPPORTUNITY,
    "FAVORABLE": BuyOpportunityState.OPPORTUNITY,
    "NEUTRAL": BuyOpportunityState.WAIT,
    "UNFAVORABLE": BuyOpportunityState.UNFAVORABLE,
    "VERY_UNFAVORABLE": BuyOpportunityState.UNFAVORABLE,
    "INSUFFICIENT_DATA": BuyOpportunityState.INSUFFICIENT_DATA,
}
SEVERITY = [BuyOpportunityState.STRONG_OPPORTUNITY, BuyOpportunityState.OPPORTUNITY,
            BuyOpportunityState.WATCH, BuyOpportunityState.WAIT,
            BuyOpportunityState.UNFAVORABLE]
MACRO_RISK_HOURS = 24.0
HIGH_UNCERTAINTY = 60.0


def _value(value: Any, default: str = "UNKNOWN") -> str:
    result = getattr(value, "value", value)
    return str(result) if result is not None else default


def _cap(state: BuyOpportunityState, ceiling: BuyOpportunityState) -> BuyOpportunityState:
    if state is BuyOpportunityState.INSUFFICIENT_DATA:
        return state
    return state if SEVERITY.index(state) >= SEVERITY.index(ceiling) else ceiling


def _entry_factors(entry: Any, as_of: str) -> list[DecisionFactor]:
    out: list[DecisionFactor] = []
    for raw in getattr(entry, "factors", []) or []:
        contribution = float(getattr(raw, "contribution", 0) or 0)
        name = str(getattr(raw, "name", "structure"))
        lower = name.lower()
        category = (Category.LOCATION if "location" in lower else
                    Category.VOLATILITY if "volatil" in lower else
                    Category.FUNDING if "funding" in lower else
                    Category.CROWDING if "crowd" in lower else Category.STRUCTURE)
        out.append(DecisionFactor(
            id=f"entry.{name.replace(' ', '_')}", category=category,
            title=name.capitalize(), short_text=str(getattr(raw, "detail", "")),
            raw_value=contribution, normalized_value=contribution,
            polarity=(Polarity.POSITIVE if contribution >= 10 else
                      Polarity.NEGATIVE if contribution <= -20 else
                      Polarity.WAIT if contribution < 0 else Polarity.NEUTRAL),
            importance=min(90, max(35, int(abs(contribution) * 2))),
            confidence=.72, timeframe="4H/1D",
            source=str(getattr(raw, "source", "EntryOpportunityEngine")),
            as_of=as_of, freshness="RECENT",
        ))
    for index, note in enumerate(getattr(entry, "missing", []) or []):
        out.append(DecisionFactor(
            id=f"entry.missing.{index}", category=Category.DATA_QUALITY,
            title="Lecture structurelle incomplète", short_text=str(note),
            polarity=Polarity.MISSING, importance=45, confidence=1,
            evidence_level="MISSING", timeframe="4H/1D",
            source="EntryOpportunityEngine", as_of=as_of,
            freshness="UNAVAILABLE", available=False,
        ))
    return out


def _pressure_factors(pressure: Any, as_of: str) -> list[DecisionFactor]:
    out: list[DecisionFactor] = []
    categories = {"institutions": Category.ETF, "levier": Category.FUNDING,
                  "positionnement": Category.POSITIONING,
                  "baleines": Category.WHALES, "flux_spot": Category.LIQUIDITY}
    for component in getattr(pressure, "components", []) or []:
        name = str(getattr(component, "name", "pressure"))
        available = bool(getattr(component, "available", False))
        score = getattr(component, "score", None)
        common = {
            "id": f"pressure.{name}",
            "category": categories.get(name, Category.POSITIONING),
            "title": str(getattr(component, "label", name)),
            "source": str(getattr(component, "source", "")),
            "as_of": getattr(component, "as_of", None) or as_of,
        }
        if not available or score is None:
            out.append(DecisionFactor(
                **common, short_text=str(getattr(component, "reason", "donnée indisponible")),
                polarity=Polarity.MISSING, importance=35, confidence=1,
                evidence_level="MISSING", freshness="UNAVAILABLE", available=False,
            ))
            continue
        number = float(score)
        out.append(DecisionFactor(
            **common, short_text=str(getattr(component, "detail", "")),
            raw_value=number, normalized_value=number,
            polarity=(Polarity.POSITIVE if number > 15 else
                      Polarity.NEGATIVE if number < -15 else Polarity.NEUTRAL),
            importance=min(80, max(30, int(abs(number)))),
            confidence=float(getattr(component, "confidence", .65) or .65),
            evidence_level="FACT", timeframe="NOW/5D",
            freshness=str(getattr(component, "freshness", "RECENT")),
        ))
    return out


def decide(
    asset: Asset, *, entry: Any, edge: Any, uncertainty: Any,
    macro_events: list[dict[str, Any]], crowding: Any, pressure: Any,
    unusable_families: list[str], regime: Any | None = None,
    timing: Any | None = None, volatility: Any | None = None,
    implied_volatility: Any | None = None,
    historical_analogs: dict[str, Any] | None = None,
    live_track_record: dict[str, Any] | None = None,
    extra_factors: list[DecisionFactor] | None = None,
    critical_missing_families: list[str] | None = None,
    location: Any = None,
) -> BuyOpportunityExplanation:
    """Assemble the state and explanation exclusively from structured inputs."""
    now = datetime.now(UTC).isoformat()
    state = BASE_MAPPING.get(_value(getattr(entry, "state", None),
                                   "INSUFFICIENT_DATA"),
                             BuyOpportunityState.INSUFFICIENT_DATA)
    factors = _entry_factors(entry, now)
    guards: list[str] = []

    if regime is not None:
        label = _value(getattr(regime, "regime", None), "UNDETERMINED")
        confidence = float(getattr(regime, "confidence", 0) or 0)
        direction = (55 if "BULL" in label or "UP" in label else
                     -55 if "BEAR" in label or "DOWN" in label else 0)
        factors.append(DecisionFactor(
            id="regime.market", category=Category.REGIME,
            title=f"Régime {_REGIME_FR.get(label, label.replace('_', ' ').lower())}",
            short_text=f"Tendance, structure et momentum concordent à {confidence:.0f}%.",
            raw_value={"regime": label, "confidence": confidence},
            normalized_value=direction,
            polarity=(Polarity.POSITIVE if direction > 0 else
                      Polarity.NEGATIVE if direction < 0 else Polarity.NEUTRAL),
            importance=78, confidence=confidence / 100, timeframe="1D",
            source="MarketRegimeEngine", as_of=now, freshness="RECENT",
        ))

    edge_state = _value(getattr(edge, "state", None), "NO_MEASURABLE_EDGE")
    admitted = int(getattr(edge, "admitted_count", 0) or 0)
    rejected = int(getattr(edge, "rejected_count", 0) or 0)
    if edge_state == "POSITIVE_EDGE":
        factors.append(DecisionFactor(
            id="edge.positive", category=Category.MEASURED_EDGE,
            title=f"{admitted} relation(s) validée(s)",
            short_text=f"{admitted} sur {admitted + rejected} ont franchi les baselines et contrôles.",
            raw_value={"admitted": admitted, "rejected": rejected,
                       "historical_evidence": 1}, normalized_value=70,
            polarity=Polarity.POSITIVE, importance=95, confidence=.8,
            timeframe="HISTORIQUE", source="EdgeEngine", as_of=now,
            freshness="RECENT",
        ))
    else:
        factors.append(DecisionFactor(
            id="edge.none", category=Category.MEASURED_EDGE,
            title="Aucun avantage statistique démontré",
            short_text=(f"{admitted} validée(s), {rejected} rejetée(s). Cela ne dit pas "
                        "que le prix va baisser; aucun avantage n’a été démontré."),
            raw_value={"admitted": admitted, "rejected": rejected},
            normalized_value=0, polarity=Polarity.WAIT, importance=88,
            confidence=1, timeframe="HISTORIQUE", source="EdgeEngine",
            as_of=now, freshness="RECENT",
        ))
        if state is BuyOpportunityState.STRONG_OPPORTUNITY:
            state = BuyOpportunityState.WATCH
            guards.append("Aucun avantage statistique démontré: plafond « à surveiller ».")

    for index, event in enumerate(macro_events):
        hours = float(event.get("hours_until") or 0)
        if hours <= 0:
            continue
        critical = str(event.get("importance", "")).upper() == "CRITICAL"
        imminent = critical and hours <= MACRO_RISK_HOURS
        name = str(event.get("name") or event.get("kind") or "Événement macro")
        proximity = max(0, min(1, (MACRO_RISK_HOURS - hours) / MACRO_RISK_HOURS))
        factors.append(DecisionFactor(
            id=f"macro.{event.get('kind', index)}.{index}", category=Category.MACRO,
            title=f"{name} dans {hours:.0f} h" if hours <= 36 else f"{name} dans {hours / 24:.0f} j",
            short_text=("Échéance majeure imminente: le sens n’est pas prédit, mais le risque de mouvement augmente."
                        if imminent else "Échéance réelle programmée; aucune direction de taux n’est supposée."),
            raw_value={"hours_until": hours, "event_proximity": proximity},
            normalized_value=0, polarity=Polarity.WAIT if imminent else Polarity.NEUTRAL,
            importance=92 if imminent else 42, confidence=1,
            evidence_level="FACT", timeframe="ÉVÉNEMENT",
            source=str(event.get("source") or "calendrier macro officiel"),
            as_of=str(event.get("scheduled_at") or now), freshness="RECENT",
        ))
        if imminent:
            capped = _cap(state, BuyOpportunityState.WAIT)
            if capped is not state:
                state = capped
                guards.append(f"{name} dans {hours:.0f} h: risque événementiel majeur.")

    uncertainty_score = float(getattr(uncertainty, "score", 0) or 0)
    factors.append(DecisionFactor(
        id="uncertainty.score", category=Category.UNCERTAINTY,
        title=f"Incertitude {uncertainty_score:.0f}/100",
        short_text="Contradictions, qualité et absences agrégées par le moteur d’incertitude.",
        raw_value=uncertainty_score, normalized_value=uncertainty_score,
        polarity=(Polarity.NEGATIVE if uncertainty_score >= 75 else
                  Polarity.WAIT if uncertainty_score >= HIGH_UNCERTAINTY else
                  Polarity.POSITIVE if uncertainty_score <= 25 else Polarity.NEUTRAL),
        importance=82 if uncertainty_score >= HIGH_UNCERTAINTY else 45,
        confidence=.8, timeframe="NOW", source="UncertaintyEngine",
        as_of=now, freshness="RECENT",
    ))
    if uncertainty_score >= HIGH_UNCERTAINTY:
        capped = _cap(state, BuyOpportunityState.WAIT)
        if capped is not state:
            state = capped
            guards.append(f"Incertitude {uncertainty_score:.0f}/100: plafond « attendre ».")

    crowding_level = _value(getattr(crowding, "level", None), "UNKNOWN")
    crowding_score = getattr(crowding, "score", None)
    if crowding_level in ("ELEVATED", "EXTREME"):
        factors.append(DecisionFactor(
            id="crowding.level", category=Category.CROWDING,
            title=f"Encombrement {crowding_level.lower()}",
            short_text="Le positionnement est chargé; risque de liquidation accru, sans direction prédite.",
            raw_value={"level": crowding_level, "score": crowding_score},
            normalized_value=float(crowding_score or 0),
            polarity=Polarity.NEGATIVE if crowding_level == "EXTREME" else Polarity.WAIT,
            importance=90 if crowding_level == "EXTREME" else 68,
            confidence=.72, timeframe="7D", source="LeverageCrowdingEngine",
            as_of=now, freshness="RECENT",
        ))
    if crowding_level == "EXTREME":
        state = _cap(state, BuyOpportunityState.UNFAVORABLE)
        guards.append("Encombrement dérivé extrême: configuration défavorable.")

    if timing is not None and getattr(timing, "timing_score", None) is not None:
        number = float(timing.timing_score)
        factors.append(DecisionFactor(
            id="entry.timing", category=Category.ENTRY_TIMING,
            title="Timing d’entrée", short_text=str(getattr(timing, "summary", "")),
            raw_value=number, normalized_value=number,
            polarity=(Polarity.POSITIVE if number >= 20 else
                      Polarity.WAIT if number <= -10 else Polarity.NEUTRAL),
            importance=72, confidence=.7, timeframe="1H/4H/1D",
            source="EntryTimingEngine", as_of=now, freshness="RECENT",
        ))

    if volatility is not None:
        regime_label = str(getattr(volatility, "regime", "UNKNOWN"))
        direction = str(getattr(volatility, "direction", "STABLE"))
        percentile = getattr(volatility, "atr_percentile", None)
        risky = regime_label in ("HIGH", "VERY_HIGH") or direction == "EXPANDING"
        state_label = (
            "EXTREME" if regime_label == "VERY_HIGH" else
            "EXPANSION" if direction == "EXPANDING" or regime_label == "HIGH" else
            "COMPRESSION" if regime_label in ("LOW", "VERY_LOW") or
            direction == "CONTRACTING" else "NORMAL"
        )
        factors.append(DecisionFactor(
            id="volatility.realised", category=Category.VOLATILITY,
            title=f"Volatilité {state_label.lower()}",
            short_text=(f"État normalisé {state_label}; volatilité réalisée "
                        f"{direction.lower()}. Cela mesure l’amplitude, pas le sens."),
            raw_value={"state": state_label, "regime": regime_label, "direction": direction,
                       "percentile": percentile},
            normalized_value=float(percentile or 0),
            polarity=Polarity.WAIT if risky else Polarity.NEUTRAL,
            importance=66 if risky else 36, confidence=.78, timeframe="30D",
            source="VolatilityRegimeEngine", as_of=now, freshness="RECENT",
        ))

    if implied_volatility is not None:
        available = bool(getattr(implied_volatility, "available", False))
        factors.append(DecisionFactor(
            id="volatility.dvol", category=Category.DVOL,
            title="Volatilité implicite (DVOL)",
            short_text=(str(getattr(implied_volatility, "interpretation", "")) if available
                        else str(getattr(implied_volatility, "unavailable_reason", "DVOL indisponible"))),
            raw_value=getattr(implied_volatility, "dvol", None),
            normalized_value=getattr(implied_volatility, "dvol_percentile", None),
            polarity=Polarity.NEUTRAL if available else Polarity.MISSING,
            importance=40 if available else 25, confidence=.75 if available else 1,
            evidence_level="COMPUTATION" if available else "MISSING",
            timeframe="NOW/30D", source="Deribit DVOL via ImpliedVolatilityEngine",
            as_of=now, freshness="RECENT" if available else "UNAVAILABLE",
            available=available,
        ))

    if historical_analogs:
        raw_n = int(historical_analogs.get("raw_n", 0) or 0)
        effective_n = float(historical_analogs.get("effective_n", 0) or 0)
        factors.append(DecisionFactor(
            id="history.analogs", category=Category.HISTORICAL_ANALOGS,
            # MFE, MAE et n effectif restent dans raw_value, donc dans les
            # preuves. En première lecture ils ne disent rien à personne.
            title=(
                "Historique comparable trop limité" if effective_n < 20
                else "Situations comparables disponibles"
            ),
            short_text=(
                f"Seulement {raw_n} situation{'s' if raw_n > 1 else ''} "
                f"suffisamment indépendante{'s' if raw_n > 1 else ''} ont été "
                "trouvées. L'échantillon est trop faible pour en tirer une "
                "conclusion solide."
                if effective_n < 20 else
                f"{raw_n} situations comparables trouvées, dont "
                f"{effective_n:.0f} réellement indépendantes. La preuve reste "
                "modérée et ne garantit rien."
            ),
            raw_value={**historical_analogs,
                       "historical_evidence": min(1, effective_n / 30)},
            polarity=Polarity.WAIT if effective_n < 20 else Polarity.NEUTRAL,
            importance=62, confidence=min(.8, effective_n / 30), timeframe="HISTORIQUE",
            source="HistoricalSimilarityEngine", as_of=now, freshness="RECENT",
        ))

    if live_track_record:
        matured = int(live_track_record.get("matured_predictions", 0) or 0)
        status = str(live_track_record.get("status") or live_track_record.get("verdict"))
        too_early = status == "TOO_EARLY"
        factors.append(DecisionFactor(
            id="track.live", category=Category.LIVE_TRACK_RECORD,
            title="Suivi live encore trop jeune" if too_early else "Suivi live disponible",
            short_text=f"{matured} prédiction(s) arrivée(s) à maturité.",
            raw_value=live_track_record,
            polarity=Polarity.WAIT if too_early else Polarity.NEUTRAL,
            importance=60 if too_early else 45, confidence=1,
            evidence_level="FACT", timeframe="LIVE", source="LiveTrackRecord",
            as_of=now, freshness="RECENT",
        ))

    factors.extend(_pressure_factors(pressure, now))
    factors.extend(extra_factors or [])
    critical = list(critical_missing_families or [])
    for name in (family for family in unusable_families if family not in critical):
        factors.append(DecisionFactor(
            id=f"data.missing.{name}", category=Category.DATA_QUALITY,
            title=f"{name.replace('_', ' ').capitalize()} indisponible ou périmé",
            short_text="Famille exclue plutôt que remplacée par une estimation.",
            polarity=Polarity.MISSING, importance=35, confidence=1,
            evidence_level="MISSING", source="DataUsability", as_of=now,
            freshness="UNAVAILABLE", available=False,
        ))
    stale_decision_inputs = {
        name for name in unusable_families if name in {"funding", "open_interest"}
    }
    if stale_decision_inputs:
        capped = _cap(state, BuyOpportunityState.WAIT)
        if capped is not state:
            state = capped
            guards.append(
                "Funding ou open interest non actuel: plafond « attendre »."
            )
    if critical:
        factors.append(DecisionFactor(
            id="data.critical_missing", category=Category.DATA_QUALITY,
            title="Données majeures insuffisantes",
            short_text=", ".join(critical) + " ne permet pas une décision actuelle.",
            raw_value=critical, polarity=Polarity.MISSING, importance=100,
            confidence=1, evidence_level="MISSING", source="DataUsability",
            as_of=now, freshness="UNAVAILABLE", available=False,
        ))
        state = BuyOpportunityState.INSUFFICIENT_DATA
        guards.append("Au moins une famille indispensable (prix ou structure) manque.")

    ranker = DecisionFactorRanker()
    positives = ranker.rank(factors, Polarity.POSITIVE)
    waits = ranker.rank(factors, Polarity.WAIT)
    negatives = ranker.rank(factors, Polarity.NEGATIVE)
    missing = ranker.rank(factors, Polarity.MISSING)
    improve, deteriorate, structure_change = _changes(
        entry, edge_state, state, macro_events, crowding_level,
        # The caller usually already holds the structural reading the entry
        # was assessed against; recomputing it would risk answering about a
        # different bar than the one this decision was built on.
        location=location or getattr(entry, "location", None) or _location_for(entry),
    )
    selected = [f.id for group in (positives, waits, negatives, missing)
                for f in group]
    return BuyOpportunityExplanation(
        state=state,
        summary=_summary(state, positives, waits, negatives, missing),
        positives=positives, waits=waits, negatives=negatives, missing=missing,
        improvement_conditions=improve,
        deterioration_conditions=deteriorate,
        structure_change_conditions=structure_change, as_of=now,
        provenance={"decision_engine": "BuyOpportunityDecisionEngine/v2",
                    "factor_ranker": "DecisionFactorRanker/v1",
                    "llm_used": False, "factors_considered": len(factors),
                    "selected_factor_ids": selected},
        score=getattr(entry, "score", None), factors=factors,
        guard_rails_applied=guards, measured_edge_state=edge_state,
    )


def _summary(state: BuyOpportunityState, positives: list[DecisionFactor],
             waits: list[DecisionFactor], negatives: list[DecisionFactor],
             missing: list[DecisionFactor]) -> str:
    base = {
        BuyOpportunityState.STRONG_OPPORTUNITY: "Les facteurs majeurs concordent dans un contexte nettement favorable.",
        BuyOpportunityState.OPPORTUNITY: "La configuration est plus favorable que la normale, sans garantie de performance.",
        BuyOpportunityState.WATCH: "La configuration mérite d’être suivie, mais ne justifie pas encore d’agir.",
        BuyOpportunityState.WAIT: "Un facteur de risque ou de timing majeur justifie d’attendre.",
        BuyOpportunityState.UNFAVORABLE: "La structure ou le risque rend l’entrée moins favorable que la normale.",
        BuyOpportunityState.INSUFFICIENT_DATA: "Les données majeures ne permettent pas une évaluation fiable.",
    }[state]
    decisive = (negatives or waits or positives or missing)[:1]
    return base + (f" Facteur principal: {decisive[0].title}." if decisive else "")


def _location_for(entry: Any) -> Any:
    """La lecture structurelle qui a servi à l'évaluation.

    `EntryOpportunityAssessment` ne conserve pas l'objet de localisation, mais
    la direction de l'invalidation en dépend. On la relit sur le même actif et
    le même timeframe plutôt que d'analyser la phrase anglaise du moteur.
    """
    from ..core.enums import Asset, Timeframe
    from ..structure.location import StructuralLocationEngine

    try:
        asset = Asset(str(getattr(entry, "asset", "")))
        timeframe = Timeframe(str(getattr(entry, "timeframe", "4h")))
    except ValueError:
        return None
    try:
        return StructuralLocationEngine().assess(asset, timeframe)
    except (ValueError, KeyError):
        return None


@dataclass(slots=True)
class ChangeCondition:
    """Un titre court, puis une ligne d'explication.

    Une phrase de trente mots dit la même chose mais ne se lit pas: sur la
    page, « Retour vers le support » se comprend avant qu'on ait fini de lire,
    et le détail répond ensuite à « pourquoi ça compterait ».

    `direction` porte le sens propre de la condition, pas celui de son groupe:
    dans « changement à surveiller », une cassure du haut du range monte et un
    retour vers le bas descend. Une flèche unique par groupe donnait la même
    au deux.
    """

    title: str
    detail: str
    direction: str = "NEUTRAL"   # UP / DOWN / NEUTRAL

    def to_dict(self) -> dict[str, str]:
        return {
            "title": self.title,
            "detail": self.detail,
            "direction": self.direction,
        }

    @property
    def sentence(self) -> str:
        return f"{self.title} — {self.detail}"


def _changes(
    entry: Any,
    edge_state: str,
    state: BuyOpportunityState,
    macro_events: list[dict[str, Any]],
    crowding_level: str,
    location: Any = None,
) -> tuple[list[ChangeCondition], list[ChangeCondition], list[ChangeCondition]]:
    """Trois catégories, pas deux.

    « La structure actuelle n'est plus valide » n'est pas « la situation
    devient mauvaise ». L'invalidation du range était versée telle quelle dans
    « ce qui dégraderait », si bien qu'une clôture 4H *au-dessus* du haut de
    range - une cassure haussière - s'affichait comme une dégradation. Une
    cassure change la structure; elle peut l'améliorer après confirmation.
    """
    improve: list[ChangeCondition] = []
    degrade: list[ChangeCondition] = []
    change: list[ChangeCondition] = []

    for raw in getattr(entry, "factors", []) or []:
        contribution = float(getattr(raw, "contribution", 0) or 0)
        name = str(getattr(raw, "name", "")).lower()
        if contribution < 0 and "location" in name:
            improve.append(ChangeCondition(
                "Retour vers le support",
                "Meilleur emplacement si le support tient.",
                direction="DOWN",
            ))
        if contribution > 0 and "structure" in name:
            degrade.append(ChangeCondition(
                "Perte de la structure",
                "La structure haussière actuelle ne tiendrait plus.",
                direction="DOWN",
            ))

    if edge_state != "POSITIVE_EDGE":
        improve.append(ChangeCondition(
            "Avantage confirmé",
            "Un signal avec un avantage statistique validé.",
            direction="UP",
        ))
    if crowding_level in ("ELEVATED", "EXTREME"):
        improve.append(ChangeCondition(
            "Levier qui se dégonfle",
            "Un encombrement dérivé revenu vers sa normale.",
            direction="DOWN",
        ))
    else:
        degrade.append(ChangeCondition(
            "Levier trop chargé",
            "Un encombrement dérivé extrême dégraderait le timing.",
            direction="UP",
        ))

    if any(
        0 < float(event.get("hours_until") or 0) <= MACRO_RISK_HOURS
        for event in macro_events
    ):
        improve.append(ChangeCondition(
            "Échéance macro passée",
            "L'échéance franchie sans rupture de structure.",
        ))

    # L'invalidation du range est un changement de structure, et sa direction
    # décide de ce qu'elle vaut. Elle est lue depuis l'état structurel, jamais
    # depuis le texte anglais du moteur.
    location_state = str(getattr(getattr(location, "state", None), "value",
                                 getattr(location, "state", "")) or "")
    if location_state:
        if "TOP" in location_state:
            change.append(ChangeCondition(
                "Cassure du haut du range",
                "Une clôture 4H au-dessus changerait la structure. "
                "À confirmer par un retest.",
                direction="UP",
            ))
            change.append(ChangeCondition(
                "Retour vers le bas du range",
                "La structure actuelle redeviendrait plus lisible.",
                direction="DOWN",
            ))
        elif "BOTTOM" in location_state:
            change.append(ChangeCondition(
                "Cassure du bas du range",
                "Une clôture 4H en dessous changerait la structure.",
                direction="DOWN",
            ))
            degrade.append(ChangeCondition(
                "Perte du bas de range",
                "Le support qui cède confirmerait une lecture plus faible.",
                direction="DOWN",
            ))
        else:
            change.append(ChangeCondition(
                "Sortie du range",
                "Une clôture confirmée hors du range, dans un sens ou l'autre.",
            ))

    if state in (BuyOpportunityState.OPPORTUNITY,
                 BuyOpportunityState.STRONG_OPPORTUNITY):
        degrade.append(ChangeCondition(
            "Volatilité en expansion",
            "Des mouvements plus amples à la baisse.",
            direction="DOWN",
        ))
    if not degrade:
        degrade.append(ChangeCondition(
            "Régime journalier retourné",
            "La tendance de fond qui bascule.",
            direction="DOWN",
        ))

    def unique(
        items: list[ChangeCondition], limit: int = 3
    ) -> list[ChangeCondition]:
        seen: set[str] = set()
        out: list[ChangeCondition] = []
        for item in items:
            if item.title in seen:
                continue
            seen.add(item.title)
            out.append(item)
        return out[:limit]

    return unique(improve), unique(degrade), unique(change)

"""Traduire les moteurs existants en une décision lisible, sans en refaire un.

Ce module ne calcule aucun indicateur. Il consomme ce que les moteurs
produisent déjà - EntryOpportunity, EdgeEngine, UncertaintyEngine, le
calendrier macro, le crowding, la fraîcheur des familles - et en tire un état
et son explication.

Le point important, et la raison d'être du module: « aucun avantage mesurable »
ne veut pas dire « non ». NO_MEASURABLE_EDGE signifie que rien n'a été démontré,
pas que le prix va baisser. Un marché fortement haussier sans edge validé et
sans configuration d'entrée favorable appelle ATTENDRE, pas NON. L'écran disait
NON, ce qui laissait croire à une lecture baissière alors que le système ne
dit rien de tel.

La décision est déterministe et entièrement dérivée des états structurés. Un
modèle de langage peut reformuler les phrases; il ne peut pas changer l'état,
créer un facteur, inventer un événement macro ni transformer une absence de
preuve en preuve d'absence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from ..core.enums import Asset
from ..logging_setup import get_logger

log = get_logger("engines.buy_opportunity")


class BuyOpportunityState(StrEnum):
    STRONG_OPPORTUNITY = "STRONG_OPPORTUNITY"
    OPPORTUNITY = "OPPORTUNITY"
    WATCH = "WATCH"
    WAIT = "WAIT"
    UNFAVORABLE = "UNFAVORABLE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class Polarity(StrEnum):
    SUPPORTS = "SUPPORTS"
    OPPOSES = "OPPOSES"
    WAIT = "WAIT"
    NEUTRAL = "NEUTRAL"
    MISSING = "MISSING"


class Category(StrEnum):
    TREND = "TREND"
    STRUCTURE = "STRUCTURE"
    LOCATION = "LOCATION"
    ENTRY_TIMING = "ENTRY_TIMING"
    MEASURED_EDGE = "MEASURED_EDGE"
    DERIVATIVES = "DERIVATIVES"
    VOLATILITY = "VOLATILITY"
    ETF = "ETF"
    MACRO = "MACRO"
    WHALES = "WHALES"
    UNCERTAINTY = "UNCERTAINTY"
    DATA_QUALITY = "DATA_QUALITY"


@dataclass(slots=True)
class Factor:
    """Un élément qui pèse, avec sa provenance et son poids."""

    id: str
    category: Category
    title: str
    explanation: str
    polarity: Polarity
    importance: int = 50            # 0-100
    raw_value: Any = None
    source: str = ""
    as_of: str | None = None
    available: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "category": self.category.value, "title": self.title,
            "explanation": self.explanation, "polarity": self.polarity.value,
            "importance": self.importance, "raw_value": self.raw_value,
            "source": self.source, "as_of": self.as_of,
            "available": self.available,
        }


@dataclass(slots=True)
class BuyOpportunityExplanation:
    state: BuyOpportunityState
    headline: str
    short_summary: str
    score: float | None = None
    factors: list[Factor] = field(default_factory=list)
    what_would_improve: list[str] = field(default_factory=list)
    what_would_deteriorate: list[str] = field(default_factory=list)
    guard_rails_applied: list[str] = field(default_factory=list)
    measured_edge_state: str = "NO_MEASURABLE_EDGE"
    as_of: str = ""

    def _by(self, polarity: Polarity) -> list[dict[str, Any]]:
        return [
            f.to_dict() for f in sorted(
                (x for x in self.factors if x.polarity is polarity),
                key=lambda x: -x.importance,
            )
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "headline": self.headline,
            "short_summary": self.short_summary,
            "score": self.score,
            "positives": self._by(Polarity.SUPPORTS),
            "waits": self._by(Polarity.WAIT),
            "negatives": self._by(Polarity.OPPOSES),
            "neutrals": self._by(Polarity.NEUTRAL),
            "missing": self._by(Polarity.MISSING),
            "what_would_improve": self.what_would_improve,
            "what_would_deteriorate": self.what_would_deteriorate,
            "guard_rails_applied": self.guard_rails_applied,
            "measured_edge_state": self.measured_edge_state,
            "as_of": self.as_of,
            "disclaimer": (
                "Évaluation du contexte de marché, pas une garantie de "
                "performance ni un conseil. Cette application ne passe jamais "
                "d'ordre."
            ),
        }


HEADLINES: dict[BuyOpportunityState, str] = {
    BuyOpportunityState.STRONG_OPPORTUNITY: "OPPORTUNITÉ FORTE",
    BuyOpportunityState.OPPORTUNITY: "OUI, CONTEXTE FAVORABLE",
    BuyOpportunityState.WATCH: "À SURVEILLER",
    BuyOpportunityState.WAIT: "ATTENDRE",
    BuyOpportunityState.UNFAVORABLE: "NON, CONTEXTE DÉFAVORABLE",
    BuyOpportunityState.INSUFFICIENT_DATA: "DONNÉES INSUFFISANTES",
}

# EntryOpportunity -> état de départ, avant garde-fous.
BASE_MAPPING = {
    "VERY_FAVORABLE": BuyOpportunityState.STRONG_OPPORTUNITY,
    "FAVORABLE": BuyOpportunityState.OPPORTUNITY,
    "NEUTRAL": BuyOpportunityState.WAIT,
    "UNFAVORABLE": BuyOpportunityState.UNFAVORABLE,
    "VERY_UNFAVORABLE": BuyOpportunityState.UNFAVORABLE,
    "INSUFFICIENT_DATA": BuyOpportunityState.INSUFFICIENT_DATA,
}

# Ordre du plus favorable au moins favorable: un garde-fou ne fait que
# descendre dans cette liste, jamais monter.
SEVERITY = [
    BuyOpportunityState.STRONG_OPPORTUNITY,
    BuyOpportunityState.OPPORTUNITY,
    BuyOpportunityState.WATCH,
    BuyOpportunityState.WAIT,
    BuyOpportunityState.UNFAVORABLE,
]

MACRO_RISK_HOURS = 24.0
HIGH_UNCERTAINTY = 60.0


def _cap(state: BuyOpportunityState, ceiling: BuyOpportunityState) -> BuyOpportunityState:
    """Empêche un état d'être plus favorable que le plafond."""
    if state is BuyOpportunityState.INSUFFICIENT_DATA:
        return state
    if state not in SEVERITY or ceiling not in SEVERITY:
        return state
    return state if SEVERITY.index(state) >= SEVERITY.index(ceiling) else ceiling


def _entry_factors(entry: Any) -> list[Factor]:
    """Les facteurs d'EntryOpportunity, retranscrits avec une polarité."""
    factors: list[Factor] = []
    for raw in getattr(entry, "factors", []) or []:
        contribution = float(getattr(raw, "contribution", 0.0))
        name = str(getattr(raw, "name", ""))
        detail = str(getattr(raw, "detail", ""))
        category = (
            Category.LOCATION if "location" in name
            else Category.VOLATILITY if "volatil" in name
            else Category.DERIVATIVES if "funding" in name or "crowd" in name
            else Category.STRUCTURE
        )
        polarity = (
            Polarity.SUPPORTS if contribution >= 15
            else Polarity.OPPOSES if contribution <= -25
            else Polarity.WAIT if contribution <= -10
            else Polarity.NEUTRAL
        )
        factors.append(Factor(
            id=f"entry.{name.replace(' ', '_')}",
            category=category, title=name.capitalize(), explanation=detail,
            polarity=polarity, importance=min(100, int(abs(contribution) * 2)),
            raw_value=contribution, source="EntryOpportunityEngine",
        ))
    for note in getattr(entry, "missing", []) or []:
        factors.append(Factor(
            id=f"entry.missing.{abs(hash(note)) % 10000}",
            category=Category.DATA_QUALITY, title="Donnée absente",
            explanation=str(note), polarity=Polarity.MISSING, importance=30,
            source="EntryOpportunityEngine", available=False,
        ))
    return factors


def decide(
    asset: Asset,
    *,
    entry: Any,
    edge: Any,
    uncertainty: Any,
    macro_events: list[dict[str, Any]],
    crowding: Any,
    pressure: Any,
    unusable_families: list[str],
) -> BuyOpportunityExplanation:
    """Assemble l'état et son explication à partir des sorties existantes."""
    entry_state = str(getattr(getattr(entry, "state", None), "value", "INSUFFICIENT_DATA"))
    state = BASE_MAPPING.get(entry_state, BuyOpportunityState.INSUFFICIENT_DATA)
    factors = _entry_factors(entry)
    guards: list[str] = []

    # --- avantage mesuré: séparé, et jamais transformé en verdict baissier ---
    edge_state = str(getattr(getattr(edge, "state", None), "value", "NO_MEASURABLE_EDGE"))
    admitted = int(getattr(edge, "admitted_count", 0) or 0)
    rejected = int(getattr(edge, "rejected_count", 0) or 0)
    if edge_state == "POSITIVE_EDGE":
        factors.append(Factor(
            id="edge.positive", category=Category.MEASURED_EDGE,
            title=f"{admitted} relation validée",
            explanation=f"sur {admitted + rejected} testées, après contrôle des "
                        "baselines et de la stabilité.",
            polarity=Polarity.SUPPORTS, importance=90,
            raw_value=admitted, source="EdgeEngine",
        ))
    else:
        factors.append(Factor(
            id="edge.none", category=Category.MEASURED_EDGE,
            title="Aucun avantage statistique démontré",
            explanation=(
                f"{admitted} validée, {rejected} rejetée"
                f"{'s' if rejected > 1 else ''}. Cela ne dit pas que le prix "
                "va baisser: seulement qu'aucun avantage n'a été démontré."
            ),
            polarity=Polarity.WAIT, importance=85,
            raw_value={"admitted": admitted, "rejected": rejected},
            source="EdgeEngine",
        ))
        # Sans edge démontré, rien ne peut se présenter comme une opportunité
        # forte: le plafond est la surveillance.
        capped = _cap(state, BuyOpportunityState.WATCH)
        if capped is not state:
            guards.append(
                "Aucun avantage statistique démontré: l'état ne peut pas "
                "dépasser « à surveiller »."
            )
            state = capped

    # --- macro réellement programmée -------------------------------------
    for event in macro_events:
        hours = float(event.get("hours_until") or 0.0)
        if hours <= 0:
            continue
        critical = str(event.get("importance", "")).upper() == "CRITICAL"
        imminent = hours <= MACRO_RISK_HOURS
        factors.append(Factor(
            id=f"macro.{event.get('kind', 'event')}",
            category=Category.MACRO,
            title=f"{event.get('name')} dans {hours / 24:.0f} j"
                  if hours > 36 else f"{event.get('name')} dans {hours:.0f} h",
            explanation=(
                "Échéance majeure: la volatilité augmente souvent autour de "
                "l'annonce." if critical else "Échéance programmée à connaître."
            ),
            polarity=Polarity.WAIT if (critical and imminent) else Polarity.NEUTRAL,
            importance=80 if (critical and imminent) else 40,
            raw_value={"hours_until": hours},
            source="calendrier macro", as_of=str(event.get("scheduled_at")),
        ))
        if critical and imminent:
            capped = _cap(state, BuyOpportunityState.WAIT)
            if capped is not state:
                guards.append(
                    f"{event.get('name')} dans {hours:.0f} h: échéance majeure "
                    "imminente."
                )
                state = capped

    # --- incertitude, décomposée ------------------------------------------
    score = float(getattr(uncertainty, "score", 0.0) or 0.0)
    drivers = getattr(uncertainty, "drivers", []) or []
    factors.append(Factor(
        id="uncertainty.score", category=Category.UNCERTAINTY,
        title=f"Incertitude {score:.0f}/100",
        explanation="; ".join(
            f"+{d.get('contribution')} {d.get('driver')}" for d in drivers
        ) or "aucun facteur nommé",
        polarity=(
            Polarity.OPPOSES if score >= HIGH_UNCERTAINTY
            else Polarity.SUPPORTS if score <= 25 else Polarity.NEUTRAL
        ),
        importance=70 if score >= HIGH_UNCERTAINTY else 40,
        raw_value=score, source="UncertaintyEngine",
    ))
    if score >= HIGH_UNCERTAINTY:
        capped = _cap(state, BuyOpportunityState.WAIT)
        if capped is not state:
            guards.append(f"Incertitude {score:.0f}/100: trop élevée pour agir.")
            state = capped

    # --- crowding extrême --------------------------------------------------
    level = str(getattr(getattr(crowding, "level", None), "value", "UNKNOWN"))
    if level == "EXTREME":
        factors.append(Factor(
            id="crowding.extreme", category=Category.DERIVATIVES,
            title="Encombrement extrême",
            explanation="Le positionnement dérivé est saturé d'un côté, ce qui "
                        "augmente le coût d'une erreur.",
            polarity=Polarity.OPPOSES, importance=85,
            raw_value=level, source="LeverageCrowdingEngine",
        ))
        capped = _cap(state, BuyOpportunityState.UNFAVORABLE)
        if capped is not state:
            guards.append("Encombrement extrême: entrée déconseillée.")
            state = capped

    # --- pression du marché, reprise telle quelle --------------------------
    for component in getattr(pressure, "components", []) or []:
        if not component.available:
            factors.append(Factor(
                id=f"pressure.{component.name}",
                category=Category.WHALES if component.name == "baleines"
                else Category.ETF if component.name == "institutions"
                else Category.DERIVATIVES,
                title=component.label, explanation=component.reason,
                polarity=Polarity.MISSING, importance=35,
                source=component.source, available=False,
            ))
            continue
        value = float(component.score or 0.0)
        factors.append(Factor(
            id=f"pressure.{component.name}",
            category=Category.ETF if component.name == "institutions"
            else Category.DERIVATIVES,
            title=component.label, explanation=component.detail,
            polarity=(
                Polarity.SUPPORTS if value > 15
                else Polarity.OPPOSES if value < -15 else Polarity.NEUTRAL
            ),
            importance=min(100, int(abs(value))), raw_value=value,
            source=component.source,
        ))

    # --- données périmées ---------------------------------------------------
    if unusable_families:
        factors.append(Factor(
            id="data.stale", category=Category.DATA_QUALITY,
            title=f"{len(unusable_families)} donnée(s) trop ancienne(s)",
            explanation=", ".join(unusable_families) +
                        " ne décrivent plus le marché actuel.",
            polarity=Polarity.MISSING, importance=60,
            raw_value=unusable_families, source="usability", available=False,
        ))
        capped = _cap(state, BuyOpportunityState.WAIT)
        if capped is not state:
            guards.append("Entrées critiques périmées: lecture non actuelle.")
            state = capped

    explanation = BuyOpportunityExplanation(
        state=state,
        headline=HEADLINES[state],
        short_summary=_summary(state, factors, entry),
        score=getattr(entry, "score", None),
        factors=factors,
        guard_rails_applied=guards,
        measured_edge_state=edge_state,
        as_of=datetime.now(UTC).isoformat(),
    )
    explanation.what_would_improve, explanation.what_would_deteriorate = _changes(
        entry, edge_state, state
    )
    return explanation


def _summary(state: BuyOpportunityState, factors: list[Factor], entry: Any) -> str:
    """Deux phrases, construites depuis les états, jamais depuis un texte libre."""
    tops = sorted(
        (f for f in factors if f.polarity in (Polarity.SUPPORTS, Polarity.WAIT,
                                              Polarity.OPPOSES)),
        key=lambda f: -f.importance,
    )[:2]
    raisons = " ".join(f"{f.title}." for f in tops)

    contexte = {
        BuyOpportunityState.STRONG_OPPORTUNITY:
            "Plusieurs facteurs concordent et la configuration est nettement "
            "plus favorable que la normale.",
        BuyOpportunityState.OPPORTUNITY:
            "La configuration est plus favorable que la normale, sans être "
            "exceptionnelle.",
        BuyOpportunityState.WATCH:
            "La configuration mérite d'être suivie, sans appeler à agir.",
        BuyOpportunityState.WAIT:
            "Le contexte de fond n'est pas défavorable, mais aucune "
            "configuration d'entrée suffisamment favorable n'est validée.",
        BuyOpportunityState.UNFAVORABLE:
            "La configuration actuelle est moins favorable que la normale.",
        BuyOpportunityState.INSUFFICIENT_DATA:
            "Les données disponibles ne permettent pas d'évaluer la "
            "configuration.",
    }[state]
    return f"{contexte} {raisons}".strip()


def _changes(entry: Any, edge_state: str, state: BuyOpportunityState) -> tuple[list[str], list[str]]:
    """Ce qui ferait bouger la lecture, tiré des moteurs et non imaginé."""
    improve: list[str] = []
    deteriorate: list[str] = []

    for raw in getattr(entry, "factors", []) or []:
        contribution = float(getattr(raw, "contribution", 0.0))
        name = str(getattr(raw, "name", ""))
        if contribution < 0 and "location" in name:
            improve.append(
                "un retour du prix vers le bas de la structure plutôt que vers "
                "son haut"
            )
        if contribution > 0 and "volatilit" in name:
            deteriorate.append("une expansion de la volatilité à la baisse")

    if edge_state != "POSITIVE_EDGE":
        improve.append(
            "une relation qui franchisse enfin l'ensemble des filtres "
            "statistiques"
        )
    invalidation = str(getattr(entry, "invalidation", "") or "")
    if invalidation and "no validated range" not in invalidation:
        deteriorate.append(invalidation)

    if state in (BuyOpportunityState.WAIT, BuyOpportunityState.WATCH):
        improve.append("un encombrement dérivé qui redescende vers la normale")
    return improve[:4], deteriorate[:4]

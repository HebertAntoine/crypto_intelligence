"""Qui achète, qui vend, et avec quoi on le mesure.

La question posée est simple: est-ce que les gros acteurs accumulent ou
distribuent. La réponse honnête l'est moins, parce que les sources ne sont pas
toutes disponibles.

Ce qui est mesurable ici:

  institutions   les flux nets des ETF spot, publiés par émetteur et par jour.
                 C'est de l'argent institutionnel réel, pas une estimation.
                 BTC et ETH uniquement: il n'existe pas d'ETF spot SOL.
  levier         le funding perpétuel. Positif, les longs paient les shorts:
                 la pression est acheteuse et elle a un coût.
  positionnement le couple prix / open interest, qui distingue de l'argent
                 neuf d'un simple débouclage.

Ce qui ne l'est pas:

  baleines       les mouvements de gros portefeuilles exigent un fournisseur
                 on-chain payant qui n'est pas configuré. Aucune estimation
                 n'est fabriquée pour combler le trou: l'absence est déclarée.

Chaque composante porte sa source et son état. Une composante absente ne vaut
pas zéro - elle est retirée du calcul et signalée, parce qu'un zéro se lirait
comme un équilibre alors qu'il s'agit d'une ignorance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from ..core.enums import Asset
from ..logging_setup import get_logger

log = get_logger("engines.pressure")

# Les ETF spot n'existent que pour ces deux actifs.
ETF_ASSETS = (Asset.BTC, Asset.ETH)

# Au-delà, un flux net sur cinq jours est considéré comme franc plutôt que
# comme du bruit. Calibré sur l'ordre de grandeur observé depuis 2024.
STRONG_FLOW_MUSD = 1000.0


@dataclass(slots=True)
class PressureComponent:
    name: str
    label: str
    available: bool = False
    score: float | None = None      # -100 vente franche .. +100 achat franc
    detail: str = ""
    source: str = ""
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "label": self.label,
            "available": self.available, "score": self.score,
            "detail": self.detail, "source": self.source, "reason": self.reason,
        }


@dataclass(slots=True)
class MarketPressure:
    asset: str
    balance: float | None = None    # 0 = vente totale, 50 = neutre, 100 = achat
    label: str = "INDÉTERMINÉ"
    components: list[PressureComponent] = field(default_factory=list)
    measured: int = 0
    missing: list[str] = field(default_factory=list)
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset": self.asset,
            "balance": self.balance,
            "label": self.label,
            "components": [c.to_dict() for c in self.components],
            "components_measured": self.measured,
            "components_missing": self.missing,
            "note": self.note,
        }


def _institutional(asset: Asset) -> PressureComponent:
    """Flux nets des ETF spot sur cinq séances."""
    component = PressureComponent(
        name="institutions", label="Institutions (ETF spot)",
        source="farside, flux publiés par émetteur",
    )
    if asset not in ETF_ASSETS:
        component.reason = (
            f"aucun ETF spot {asset.value} n'existe, donc aucun flux à mesurer"
        )
        return component

    from ..db import repo

    rows = repo.get_etf_flows(asset, days=30)
    if not rows:
        component.reason = "aucun flux ETF stocké"
        return component

    by_day: dict[str, float] = {}
    for row in rows:
        day = str(row["date"])[:10]
        by_day[day] = by_day.get(day, 0.0) + float(row["flow_musd"] or 0.0)
    if not by_day:
        component.reason = "flux illisibles"
        return component

    days = sorted(by_day)
    recent = days[-5:]
    net = sum(by_day[d] for d in recent)
    last_day = days[-1]

    # Fraîcheur: les ETF ne publient que les jours de bourse, mais une semaine
    # de retard reste une semaine de retard.
    age_days = (datetime.now(UTC).date() - datetime.fromisoformat(last_day).date()).days
    if age_days > 7:
        component.reason = (
            f"dernière publication il y a {age_days} jours, trop ancienne"
        )
        component.detail = f"net 5 séances {net:+,.0f} M$ (périmé)"
        return component

    component.available = True
    # Saturé à STRONG_FLOW_MUSD pour qu'une journée exceptionnelle ne domine
    # pas tout le reste.
    component.score = max(-100.0, min(100.0, net / STRONG_FLOW_MUSD * 100.0))
    sens = "achat net" if net > 0 else "vente nette" if net < 0 else "équilibre"
    component.detail = f"{net:+,.0f} M$ sur 5 séances — {sens}"
    component.reason = f"dernière publication {last_day}"
    return component


def _leverage(funding_percentile: float | None, usable: bool) -> PressureComponent:
    """Le funding perpétuel comme mesure du côté qui paie pour être positionné."""
    component = PressureComponent(
        name="levier", label="Levier (funding perpétuel)",
        source="funding.rate, percentile sur l'historique de l'actif",
    )
    if funding_percentile is None:
        component.reason = "pas de percentile: historique insuffisant"
        return component
    if not usable:
        component.reason = "dernière observation trop ancienne"
        return component

    component.available = True
    # 50e percentile = neutre. Au-dessus, les longs paient: pression acheteuse.
    component.score = (funding_percentile - 50.0) * 2.0
    if funding_percentile >= 70:
        sens = "les longs paient nettement — pression acheteuse"
    elif funding_percentile <= 30:
        sens = "les shorts paient — pression vendeuse"
    else:
        sens = "aucun côté ne paie franchement"
    component.detail = f"{funding_percentile:.0f}e percentile — {sens}"
    return component


def _positioning(state: str, usable: bool) -> PressureComponent:
    """Prix et open interest: de l'argent neuf, ou un simple débouclage."""
    component = PressureComponent(
        name="positionnement", label="Positionnement (prix + open interest)",
        source="bougies journalières et open interest",
    )
    if not usable:
        component.reason = "open interest ou prix trop ancien"
        return component

    score, detail = {
        "NEW_LONGS": (70.0, "positions acheteuses ouvertes dans la hausse"),
        "NEW_SHORTS": (-70.0, "positions vendeuses ouvertes dans la baisse"),
        "SHORT_COVERING": (30.0, "rachat de shorts, pas de l'argent neuf"),
        "LONG_LIQUIDATION": (-30.0, "sortie de longs, pas de vente agressive"),
        "DELEVERAGING": (0.0, "réduction du levier des deux côtés"),
        "QUIET": (0.0, "aucun mouvement de positionnement marqué"),
        "BALANCED": (0.0, "les deux côtés se compensent"),
    }.get(state.upper(), (None, ""))

    if score is None:
        component.reason = f"état {state} non interprétable"
        return component
    component.available = True
    component.score = score
    component.detail = detail
    return component


def _whales() -> PressureComponent:
    """Déclarée absente plutôt que devinée."""
    return PressureComponent(
        name="baleines", label="Baleines (gros portefeuilles)",
        source="fournisseur on-chain",
        reason=(
            "aucun fournisseur on-chain n'est configuré. Suivre les gros "
            "portefeuilles demande un service payant; rien n'est estimé à la "
            "place."
        ),
    )


def _label(balance: float) -> str:
    if balance >= 70:
        return "ACHAT DOMINANT"
    if balance >= 58:
        return "ACHAT LÉGER"
    if balance > 42:
        return "ÉQUILIBRÉ"
    if balance > 30:
        return "VENTE LÉGÈRE"
    return "VENTE DOMINANTE"


def assess_pressure(
    asset: Asset,
    *,
    funding_percentile: float | None,
    funding_usable: bool,
    leverage_state: str,
    positioning_usable: bool,
) -> MarketPressure:
    """Combine uniquement ce qui est mesurable et à jour."""
    components = [
        _institutional(asset),
        _leverage(funding_percentile, funding_usable),
        _positioning(leverage_state, positioning_usable),
        _whales(),
    ]
    usable = [c for c in components if c.available and c.score is not None]
    pressure = MarketPressure(
        asset=asset.value,
        components=components,
        measured=len(usable),
        missing=[c.label for c in components if not c.available],
    )

    if not usable:
        pressure.note = (
            "Aucune composante mesurable n'est disponible: la pression du "
            "marché ne peut pas être établie."
        )
        return pressure

    average = sum(c.score for c in usable if c.score is not None) / len(usable)
    pressure.balance = round((average + 100.0) / 2.0, 1)
    pressure.label = _label(pressure.balance)
    pressure.note = (
        f"{len(usable)} composante(s) mesurée(s) sur {len(components)}. "
        "Une composante absente est retirée du calcul, jamais comptée comme "
        "neutre: ignorer n'est pas équilibrer."
    )
    return pressure

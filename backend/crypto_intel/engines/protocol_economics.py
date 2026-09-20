"""The economics of each protocol: what changes the supply, what changes the demand.

A generic frame, filled only where a measurement exists:

    supply    issuance, burn, circulating supply, scheduled changes
    demand    regulated products, spot pressure

Two states are returned separately - supply and demand - because they move for
different reasons, and neither is a recommendation. A protocol that will issue
fewer tokens has a NEGATIVE_SUPPLY_CHANGE; whether that matters to the price
is decided by the market, and measured elsewhere.

Where no source is connected the answer is UNKNOWN with the reason, never an
estimate. Ethereum's burn and Solana's issuance schedule need an indexer this
system does not have; they say so.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from enum import StrEnum
from typing import Any

from ..core.enums import Asset
from .factor_semantics import fr_number
from .pit_view import PointInTimeView


class EconomicState(StrEnum):
    POSITIVE_SUPPLY_CHANGE = "POSITIVE_SUPPLY_CHANGE"
    NEGATIVE_SUPPLY_CHANGE = "NEGATIVE_SUPPLY_CHANGE"
    POSITIVE_DEMAND_CHANGE = "POSITIVE_DEMAND_CHANGE"
    NEGATIVE_DEMAND_CHANGE = "NEGATIVE_DEMAND_CHANGE"
    MIXED = "MIXED"
    UNKNOWN = "UNKNOWN"


STATE_FR = {
    EconomicState.POSITIVE_SUPPLY_CHANGE: "Offre future en hausse",
    EconomicState.NEGATIVE_SUPPLY_CHANGE: "Offre future en baisse",
    EconomicState.POSITIVE_DEMAND_CHANGE: "Demande en hausse",
    EconomicState.NEGATIVE_DEMAND_CHANGE: "Demande en baisse",
    EconomicState.MIXED: "Signaux économiques mitigés",
    EconomicState.UNKNOWN: "Non mesuré",
}

#: What each asset's supply reading needs, and what is missing without a key.
SUPPLY_SOURCES = {
    Asset.BTC: ("onchain.circulating_supply", "Offre en circulation (chaîne Bitcoin)"),
    Asset.ETH: ("onchain.circulating_supply", "Offre en circulation"),
    Asset.SOL: ("onchain.total_supply", "Offre totale"),
}
MISSING_REASON = {
    Asset.BTC: "",
    Asset.ETH: (
        "L'émission nette et la destruction de frais d'Ethereum demandent un indexeur "
        "(clé requise) : elles ne sont pas estimées ici."
    ),
    Asset.SOL: (
        "La trajectoire d'émission de Solana dépend des propositions en cours : seule "
        "l'offre mesurée sur la chaîne est utilisée."
    ),
}


@dataclass(slots=True)
class ProtocolEconomics:
    asset: str
    supply_state: EconomicState = EconomicState.UNKNOWN
    demand_state: EconomicState = EconomicState.UNKNOWN
    supply_growth_annual_pct: float | None = None
    scheduled_changes: list[dict[str, Any]] = field(default_factory=list)
    demand_evidence: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    sentences: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset": self.asset,
            "supply_state": self.supply_state.value,
            "supply_label": STATE_FR[self.supply_state],
            "demand_state": self.demand_state.value,
            "demand_label": STATE_FR[self.demand_state],
            "supply_growth_annual_pct": (
                round(self.supply_growth_annual_pct, 2)
                if self.supply_growth_annual_pct is not None else None
            ),
            "scheduled_changes": self.scheduled_changes,
            "demand_evidence": self.demand_evidence,
            "missing": self.missing,
            "sentences": self.sentences,
            "note": (
                "Aucun changement d'économie du protocole n'est traduit automatiquement "
                "en achat ou en vente."
            ),
        }


def read_economics(view: PointInTimeView, asset: Asset, *,
                   catalysts: Any = None, demand: Any = None) -> ProtocolEconomics:
    out = ProtocolEconomics(asset=asset.value)
    metric, label = SUPPLY_SOURCES[asset]
    points = view.points(metric, asset.value)
    if len(points) >= 2:
        last = points[-1]
        # Thirty days when the history allows it, seven otherwise: the rate is
        # annualised from the window actually measured.
        window_days, earlier = next(
            (
                (days, point)
                for days in (30, 7)
                for point in [next(
                    (p for p in reversed(points) if p.timestamp <= last.timestamp - timedelta(days=days)),
                    None,
                )]
                if point is not None and point.value
            ),
            (0, None),
        )
        if earlier is not None and earlier.value:
            change = (last.value / earlier.value - 1) * 100
            monthly = change * (30 / window_days)
            out.supply_growth_annual_pct = monthly * 12
            # An issuance that slows is a supply change, not a price forecast.
            out.supply_state = (
                EconomicState.POSITIVE_SUPPLY_CHANGE if monthly > 0.05
                else EconomicState.NEGATIVE_SUPPLY_CHANGE if monthly < -0.05
                else EconomicState.MIXED
            )
            out.sentences.append(
                f"{label} : {fr_number(out.supply_growth_annual_pct, 1, signed=True)} % par an "
                f"au rythme des {window_days} derniers jours."
            )
    else:
        out.missing.append(label)
    if MISSING_REASON[asset]:
        out.missing.append(MISSING_REASON[asset])

    # A proposal that changes issuance is a scheduled supply change - with its
    # stage, so "proposed" is never read as "in force".
    for catalyst in getattr(catalysts, "catalysts", []) or []:
        effect = catalyst.economic_effect or {}
        if effect.get("supply_effect") in {"ISSUANCE_DOWN", "ISSUANCE_UP", "BURN"}:
            out.scheduled_changes.append({
                "title": catalyst.title,
                "stage": catalyst.stage,
                "stage_label": catalyst.stage_label,
                "effect": effect["supply_effect"],
                "caveat": catalyst.stage_caveat,
            })
    if out.scheduled_changes:
        pending = out.scheduled_changes[0]
        out.sentences.append(
            f"Changement d'émission en cours de processus ({pending['stage_label'].lower()}) : "
            f"{pending['caveat']}"
        )

    if demand is not None:
        state = getattr(demand, "state", None)
        value = getattr(state, "value", "")
        if value in {"STRONG_INFLOW", "INFLOW"}:
            out.demand_state = EconomicState.POSITIVE_DEMAND_CHANGE
        elif value in {"STRONG_OUTFLOW", "OUTFLOW"}:
            out.demand_state = EconomicState.NEGATIVE_DEMAND_CHANGE
        elif value == "DIVERGENCE":
            out.demand_state = EconomicState.MIXED
        out.demand_evidence = list(getattr(demand, "sentences", []))[:2]
    if out.demand_state is EconomicState.UNKNOWN:
        out.missing.append("Demande institutionnelle non mesurable")
    if not out.sentences:
        out.sentences.append("Économie du protocole non mesurée avec les sources connectées.")
    return out

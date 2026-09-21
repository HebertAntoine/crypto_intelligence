"""What would have happened if the scenario had been followed to the letter.

A simulation of the extracted scenario, never a recommendation. It is pure
arithmetic over two inputs: the levels the video announced, and the prices
that actually printed after the video was published.

    entries        BUY_ZONE, REINFORCEMENT - bought when the price trades at
                   or below the level, with the allocation the video gave
    take-profits   TARGET, TAKE_PROFIT - a share of the position sold when the
                   price trades at or above the level, after it was bought
    invalidation   flagged when reached; nothing is sold on it unless the
                   video said so, because inventing a stop would change the
                   scenario

Money is in euros, levels in the quote the video used (dollars). The exchange
rate between the two is held constant: the performance in percent is exact,
the euro value ignores the €/$ move, and the result says so.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd

ENTRY_KINDS = {"BUY_ZONE", "REINFORCEMENT"}
EXIT_KINDS = {"TARGET", "TAKE_PROFIT"}


@dataclass(slots=True)
class SimLevel:
    id: int
    kind: str
    value: float
    allocation_pct: float | None = None
    label: str = ""


@dataclass(slots=True)
class Fill:
    level_id: int
    kind: str
    price: float
    at: datetime
    amount_eur: float
    quantity: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "level_id": self.level_id,
            "kind": self.kind,
            "price": self.price,
            "at": self.at.isoformat(),
            "amount_eur": round(self.amount_eur, 2),
            "quantity": self.quantity,
        }


@dataclass(slots=True)
class SimulationResult:
    capital_eur: float
    allocations_eur: dict[int, float]
    fills: list[Fill] = field(default_factory=list)
    exits: list[Fill] = field(default_factory=list)
    executed_eur: float = 0.0
    remaining_eur: float = 0.0
    quantity_held: float = 0.0
    average_price: float | None = None
    realised_eur: float = 0.0
    current_price: float | None = None
    current_value_eur: float = 0.0
    performance_pct: float | None = None
    targets_hit: list[int] = field(default_factory=list)
    invalidation_reached: bool = False
    assumptions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "capital_eur": round(self.capital_eur, 2),
            "allocations_eur": {str(k): round(v, 2) for k, v in self.allocations_eur.items()},
            "fills": [f.to_dict() for f in self.fills],
            "exits": [f.to_dict() for f in self.exits],
            "executed_eur": round(self.executed_eur, 2),
            "remaining_eur": round(self.remaining_eur, 2),
            "quantity_held": self.quantity_held,
            "average_price": self.average_price,
            "realised_eur": round(self.realised_eur, 2),
            "current_price": self.current_price,
            "current_value_eur": round(self.current_value_eur, 2),
            "performance_pct": (
                round(self.performance_pct, 2) if self.performance_pct is not None else None
            ),
            "targets_hit": self.targets_hit,
            "invalidation_reached": self.invalidation_reached,
            "assumptions": self.assumptions,
            "disclaimer": (
                "Simulation du scénario extrait de la vidéo, pas une recommandation. "
                "Le change €/$ est supposé constant."
            ),
        }


def align_stamp(moment: datetime, index: pd.DatetimeIndex) -> pd.Timestamp:
    """The video time on the same clock as the candles (SQLite returns naive UTC)."""

    stamp = pd.Timestamp(moment)
    if index.tz is None:
        return stamp.tz_convert(None) if stamp.tzinfo is not None else stamp
    return stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp


def allocate(capital_eur: float, levels: list[SimLevel]) -> tuple[dict[int, float], list[str]]:
    """Euros per entry level. Proportional: doubling the capital doubles each line."""

    entries = [lv for lv in levels if lv.kind in ENTRY_KINDS]
    notes: list[str] = []
    if not entries:
        return {}, notes
    given = [lv for lv in entries if lv.allocation_pct is not None]
    if len(given) == len(entries):
        total = sum(lv.allocation_pct or 0 for lv in entries)
        if total > 100.0001:
            notes.append(
                f"Les allocations annoncées totalisent {total:.0f} % : elles sont ramenées à 100 %."
            )
            return {lv.id: capital_eur * (lv.allocation_pct or 0) / total for lv in entries}, notes
        if total < 99.999:
            notes.append(f"{100 - total:.0f} % du capital n'est affecté à aucune entrée.")
        return {lv.id: capital_eur * (lv.allocation_pct or 0) / 100 for lv in entries}, notes
    # Some or all allocations missing: the rest is split equally, and said so.
    announced = sum(lv.allocation_pct or 0 for lv in given)
    remaining = max(0.0, 100.0 - announced)
    missing = [lv for lv in entries if lv.allocation_pct is None]
    share = remaining / len(missing)
    notes.append(
        "Répartition non précisée dans la vidéo pour "
        + ", ".join(lv.label or lv.kind for lv in missing)
        + f" : {share:.0f} % chacune par hypothèse."
    )
    out = {lv.id: capital_eur * (lv.allocation_pct or 0) / 100 for lv in given}
    out.update({lv.id: capital_eur * share / 100 for lv in missing})
    return out, notes


def simulate(
    levels: list[SimLevel],
    candles: pd.DataFrame,
    *,
    capital_eur: float = 100.0,
    published_at: datetime,
    invalidation: float | None = None,
) -> SimulationResult:
    """Walk the closed candles after the video, bar by bar, and apply the scenario."""

    allocations, notes = allocate(capital_eur, levels)
    result = SimulationResult(capital_eur=capital_eur, allocations_eur=allocations,
                              assumptions=notes)
    frame = candles
    if frame is not None and not frame.empty:
        stamp = align_stamp(published_at, frame.index)
        frame = frame.loc[frame.index >= stamp]
    pending_entries = sorted(
        (lv for lv in levels if lv.kind in ENTRY_KINDS and lv.id in allocations),
        key=lambda lv: -lv.value,
    )
    exits = sorted((lv for lv in levels if lv.kind in EXIT_KINDS), key=lambda lv: lv.value)
    exit_given = [lv for lv in exits if lv.allocation_pct is not None]
    if exits and len(exit_given) < len(exits):
        result.assumptions.append(
            "Part vendue à chaque objectif non précisée : parts égales par hypothèse."
        )
    quantity = 0.0
    bought_quantity = 0.0
    realised = 0.0
    done_exits: set[int] = set()

    if frame is not None and not frame.empty:
        for stamp, bar in frame.iterrows():
            moment = pd.Timestamp(stamp).to_pydatetime()
            low, high = float(bar["low"]), float(bar["high"])
            for level in list(pending_entries):
                if low <= level.value:
                    amount = allocations[level.id]
                    qty = amount / level.value
                    quantity += qty
                    bought_quantity += qty
                    result.fills.append(Fill(level.id, level.kind, level.value, moment, amount, qty))
                    pending_entries.remove(level)
            if bought_quantity > 0:
                for level in exits:
                    if level.id in done_exits or high < level.value:
                        continue
                    share = (
                        (level.allocation_pct or 0) / 100 if level.allocation_pct is not None
                        else 1 / len(exits)
                    )
                    qty = min(quantity, bought_quantity * share)
                    if qty <= 0:
                        continue
                    quantity -= qty
                    realised += qty * level.value
                    done_exits.add(level.id)
                    result.targets_hit.append(level.id)
                    result.exits.append(Fill(level.id, level.kind, level.value, moment,
                                             qty * level.value, qty))
            if invalidation is not None and bought_quantity > 0 and low <= invalidation:
                result.invalidation_reached = True

    result.executed_eur = sum(fill.amount_eur for fill in result.fills)
    result.remaining_eur = capital_eur - result.executed_eur
    result.quantity_held = quantity
    result.realised_eur = realised
    if bought_quantity > 0:
        result.average_price = result.executed_eur / bought_quantity
    if frame is not None and not frame.empty:
        result.current_price = float(frame["close"].iloc[-1])
    if result.current_price is not None:
        result.current_value_eur = quantity * result.current_price + realised + result.remaining_eur
        if result.executed_eur > 0:
            invested_now = quantity * result.current_price + realised
            result.performance_pct = (invested_now / result.executed_eur - 1) * 100
    else:
        result.current_value_eur = capital_eur
    if result.invalidation_reached:
        result.assumptions.append(
            "Niveau d'invalidation atteint : la simulation ne vend pas, faute de consigne "
            "de sortie dans la vidéo."
        )
    return result

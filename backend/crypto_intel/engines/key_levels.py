"""The nearest support and the next resistance, drawn from market structure.

A level is a cluster of confirmed swing pivots within a tolerance of each other
(half an ATR, never under 0.4 % of price). Its strength is how often the market
turned there. The next resistance is the nearest cluster above the price; the
nearest support the nearest one below. A former top the price has since cleared
becomes a support and says so ("ancienne résistance").

Pivots come from ``find_causal_swings``: each one is only used once it was
confirmed, so a backtest never sees a level before it existed. Nothing is picked
arbitrarily - when no cluster lies above the price, there is no resistance to
name, and the engine says the price trades above every tested level.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd

from .factor_semantics import fr_number


@dataclass(slots=True)
class KeyLevel:
    price: float
    kind: str  # SUPPORT | RESISTANCE
    origin: str  # SWING_HIGH | SWING_LOW | FORMER_RESISTANCE | FORMER_SUPPORT
    touches: int
    anchor_time: datetime
    last_time: datetime
    timeframe: str
    pivots: list[float] = field(default_factory=list)

    @property
    def explanation(self) -> str:
        day = f"{self.anchor_time:%d/%m/%Y}"
        count = f"{self.touches} fois" if self.touches > 1 else "une fois"
        return {
            "SWING_HIGH": f"Résistance issue du sommet du {day}, testée {count}.",
            "SWING_LOW": f"Support issu du creux du {day}, testé {count}.",
            "FORMER_RESISTANCE": (
                f"Ancienne résistance (sommet du {day}) devenue support, testée {count}."
            ),
            "FORMER_SUPPORT": (
                f"Ancien support (creux du {day}) devenu résistance, testé {count}."
            ),
        }[self.origin]

    def to_dict(self) -> dict[str, Any]:
        return {
            "price": round(self.price, 2),
            "kind": self.kind,
            "origin": self.origin,
            "touches": self.touches,
            "anchor_time": self.anchor_time.isoformat(),
            "last_time": self.last_time.isoformat(),
            "timeframe": self.timeframe,
            "explanation": self.explanation,
            "label": f"{fr_number(self.price, 0)} $",
        }


def _clusters(pivots: list[tuple[datetime, float, str]], tolerance: float) -> list[list[tuple[datetime, float, str]]]:
    ordered = sorted(pivots, key=lambda p: p[1])
    groups: list[list[tuple[datetime, float, str]]] = []
    for pivot in ordered:
        # Neighbours within the tolerance, and a zone never wider than two
        # tolerances: a slow staircase of pivots is not one level.
        if (groups and pivot[1] - groups[-1][-1][1] <= tolerance
                and pivot[1] - groups[-1][0][1] <= 2 * tolerance):
            groups[-1].append(pivot)
        else:
            groups.append([pivot])
    return groups


def find_key_levels(
    frame: pd.DataFrame, timeframe: str, *, lookback: int = 5, bars: int = 500
) -> tuple[KeyLevel | None, KeyLevel | None, list[KeyLevel]]:
    """(nearest support, next resistance, every level) from closed bars."""

    from ..structure.swings import find_causal_swings
    from .technical import indicators as ind

    if len(frame) < 60:
        return None, None, []
    window = frame.iloc[-bars:]
    atr = ind.atr(window["high"], window["low"], window["close"], 14)
    swings = find_causal_swings(window["high"], window["low"], window["close"], atr, lookback=lookback)
    swings = swings.as_of(window.index[-1])
    price = float(window["close"].iloc[-1])
    atr_now = float(atr.iloc[-1]) if pd.notna(atr.iloc[-1]) else price * 0.01
    tolerance = max(0.5 * atr_now, price * 0.004)

    pivots = [(s.pivot_time, float(s.price), s.kind) for s in swings.all_swings]
    levels: list[KeyLevel] = []
    for group in _clusters(pivots, tolerance):
        level_price = sorted(p[1] for p in group)[len(group) // 2]
        highs = [p for p in group if p[2] == "high"]
        lows = [p for p in group if p[2] == "low"]
        dominant = "high" if len(highs) >= len(lows) else "low"
        anchor = max(highs or lows, key=lambda p: p[1]) if dominant == "high" else min(lows or highs, key=lambda p: p[1])
        above = level_price > price
        if above:
            kind = "RESISTANCE"
            origin = "SWING_HIGH" if dominant == "high" else "FORMER_SUPPORT"
        else:
            kind = "SUPPORT"
            origin = "SWING_LOW" if dominant == "low" else "FORMER_RESISTANCE"
        stamp = anchor[0] if isinstance(anchor[0], datetime) else pd.Timestamp(anchor[0]).to_pydatetime()
        last = max(p[0] for p in group)
        last = last if isinstance(last, datetime) else pd.Timestamp(last).to_pydatetime()
        levels.append(KeyLevel(
            price=level_price, kind=kind, origin=origin, touches=len(group),
            anchor_time=stamp, last_time=last, timeframe=timeframe,
            pivots=[p[1] for p in group],
        ))

    # A level within a hair of the price is being tested, not ahead of it.
    margin = price * 0.001
    resistances = [lv for lv in levels if lv.price > price + margin]
    supports = [lv for lv in levels if lv.price < price - margin]
    # "Important": a level the market turned at more than once wins over a
    # single pivot; a lone pivot is named only when nothing stronger exists.
    strong_r = [lv for lv in resistances if lv.touches >= 2]
    strong_s = [lv for lv in supports if lv.touches >= 2]
    resistance = min(strong_r or resistances, key=lambda lv: lv.price) if resistances else None
    support = max(strong_s or supports, key=lambda lv: lv.price) if supports else None
    return support, resistance, levels

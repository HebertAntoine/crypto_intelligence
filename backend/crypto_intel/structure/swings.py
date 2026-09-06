"""Causal swing detection with explicit confirmation times.

A swing high at bar i is only knowable once `lookback` further bars have
printed without exceeding it. The existing `find_swings` already refuses to
emit unconfirmed pivots, but it does not record WHEN each pivot became
knowable - and that distinction decides whether a backtest is honest.

Every swing here carries two timestamps:

  pivot_time         when the extreme actually occurred
  confirmation_time  when it could first have been recognised

A backtest asking "what did we know at T" must filter on confirmation_time.
Filtering on pivot_time silently imports `lookback` bars of future knowledge,
which is one of the easiest look-ahead bugs to introduce and one of the
hardest to notice.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd


@dataclass(slots=True, frozen=True)
class CausalSwing:
    """One pivot, with the moment it became knowable."""

    pivot_time: datetime
    confirmation_time: datetime
    price: float
    kind: str                    # "high" | "low"
    pivot_index: int
    confirmation_index: int
    lookback: int
    # Reaction depth measures how meaningful the pivot was: a swing low that
    # produced a 3-ATR bounce matters more than one that produced a wobble.
    reaction_atr: float | None = None

    @property
    def bars_to_confirm(self) -> int:
        return self.confirmation_index - self.pivot_index

    def known_at(self, when: datetime) -> bool:
        return self.confirmation_time <= when

    def to_dict(self) -> dict[str, Any]:
        return {
            "pivot_time": self.pivot_time.isoformat(),
            "confirmation_time": self.confirmation_time.isoformat(),
            "price": self.price, "kind": self.kind,
            "bars_to_confirm": self.bars_to_confirm,
            "reaction_atr": self.reaction_atr,
        }


@dataclass(slots=True)
class SwingSeries:
    """All swings for one series, queryable as of any point in time."""

    highs: list[CausalSwing] = field(default_factory=list)
    lows: list[CausalSwing] = field(default_factory=list)
    lookback: int = 5

    def as_of(self, when: datetime) -> SwingSeries:
        """Only what was confirmed by `when` - the causal view."""
        return SwingSeries(
            highs=[s for s in self.highs if s.known_at(when)],
            lows=[s for s in self.lows if s.known_at(when)],
            lookback=self.lookback,
        )

    @property
    def all_swings(self) -> list[CausalSwing]:
        return sorted(self.highs + self.lows, key=lambda s: s.pivot_time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "lookback": self.lookback,
            "highs": [s.to_dict() for s in self.highs],
            "lows": [s.to_dict() for s in self.lows],
            "counts": {"highs": len(self.highs), "lows": len(self.lows)},
        }


def find_causal_swings(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series | None = None,
    atr: pd.Series | None = None,
    lookback: int = 5,
) -> SwingSeries:
    """Confirmed pivots, each tagged with when it became knowable.

    A pivot at index i is confirmed at index i+lookback, because that is the
    first bar at which the full window [i-lookback, i+lookback] exists. Bars
    within `lookback` of the end are therefore not yet confirmed and are
    excluded entirely.
    """
    series = SwingSeries(lookback=lookback)
    n = len(high)
    if n < 2 * lookback + 1:
        return series

    highs = high.to_numpy(dtype=float)
    lows = low.to_numpy(dtype=float)
    index = high.index
    atr_values = atr.to_numpy(dtype=float) if atr is not None else None

    for i in range(lookback, n - lookback):
        confirmation_index = i + lookback
        window_high = highs[i - lookback:i + lookback + 1]
        window_low = lows[i - lookback:i + lookback + 1]

        # Strict on the left so a flat plateau is not logged repeatedly.
        is_high = (
            highs[i] == np.nanmax(window_high)
            and not np.isnan(highs[i])
            and (highs[i] > np.nanmax(highs[i - lookback:i]) or i == lookback)
        )
        if is_high:
            series.highs.append(CausalSwing(
                pivot_time=index[i], confirmation_time=index[confirmation_index],
                price=float(highs[i]), kind="high",
                pivot_index=i, confirmation_index=confirmation_index,
                lookback=lookback,
                reaction_atr=_reaction(
                    lows, i, confirmation_index, atr_values, downward=True
                ),
            ))

        is_low = (
            lows[i] == np.nanmin(window_low)
            and not np.isnan(lows[i])
            and (lows[i] < np.nanmin(lows[i - lookback:i]) or i == lookback)
        )
        if is_low:
            series.lows.append(CausalSwing(
                pivot_time=index[i], confirmation_time=index[confirmation_index],
                price=float(lows[i]), kind="low",
                pivot_index=i, confirmation_index=confirmation_index,
                lookback=lookback,
                reaction_atr=_reaction(
                    highs, i, confirmation_index, atr_values, downward=False
                ),
            ))

    return series


def _reaction(
    prices: np.ndarray, pivot: int, confirmation: int,
    atr_values: np.ndarray | None, downward: bool,
) -> float | None:
    """Move away from the pivot, in ATR, measured only up to confirmation.

    Bounded by the confirmation bar on purpose: measuring the full subsequent
    move would import information the pivot itself could not have carried.
    """
    if atr_values is None or pivot >= len(atr_values):
        return None
    atr_at_pivot = atr_values[pivot]
    if not np.isfinite(atr_at_pivot) or atr_at_pivot <= 0:
        return None
    window = prices[pivot:confirmation + 1]
    if len(window) < 2:
        return None
    move = (window[0] - np.nanmin(window)) if downward else (np.nanmax(window) - window[0])
    if not np.isfinite(move):
        return None
    return round(float(abs(move) / atr_at_pivot), 3)

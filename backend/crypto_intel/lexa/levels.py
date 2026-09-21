"""Where each announced level stands, read on the prices that followed.

    ⚪ NOT_WATCHED     no price source for this asset
    ⏳ WAITING         the price has not reached the level
    🟢 TOUCHED         the price reached it
    🚀 CONFIRMED       the confirmation the video stated is satisfied
    ⚠️ TESTED_LOST     a confirmation level reached, then lost again
    ⚠️ INVALIDATED     an invalidation met under the stated condition
    🔴 TARGET_REACHED  an objective reached

A price passing through a level is a touch, nothing more. "Confirmed" needs the
condition the video gave - a close above on a given timeframe - and a level
whose video gave no condition stays at TOUCHED: the condition is UNKNOWN, and
it is not invented here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pandas as pd

from .simulation import align_stamp

#: Conditions the member can record, exactly as the video phrased them.
CONDITIONS = {
    "UNKNOWN": ("", None, None),
    "CLOSE_1H_ABOVE": ("Clôture 1 h au-dessus", "1h", "above"),
    "CLOSE_4H_ABOVE": ("Clôture 4 h au-dessus", "4h", "above"),
    "CLOSE_1D_ABOVE": ("Clôture journalière au-dessus", "1d", "above"),
    "CLOSE_1H_BELOW": ("Clôture 1 h en dessous", "1h", "below"),
    "CLOSE_4H_BELOW": ("Clôture 4 h en dessous", "4h", "below"),
    "CLOSE_1D_BELOW": ("Clôture journalière en dessous", "1d", "below"),
}

STATE_FR = {
    "NOT_WATCHED": ("⚪", "Non surveillé"),
    "WAITING": ("⏳", "Non atteint"),
    "TOUCHED": ("🟢", "Touché"),
    "CONFIRMED": ("🚀", "Confirmé"),
    "TESTED_LOST": ("⚠️", "Niveau testé puis reperdu"),
    "INVALIDATED": ("⚠️", "Invalidé"),
    "TARGET_REACHED": ("🔴", "Objectif atteint"),
}

#: Levels reached from above (the price has to come down to them).
FROM_ABOVE = {"BUY_ZONE", "REINFORCEMENT", "SUPPORT", "INVALIDATION"}
#: Levels reached from below.
FROM_BELOW = {"RESISTANCE", "CONFIRMATION", "TARGET", "TAKE_PROFIT"}


@dataclass(slots=True)
class LevelState:
    state: str
    first_touched_at: datetime | None = None
    last_touched_at: datetime | None = None
    confirmed_at: datetime | None = None
    invalidated_at: datetime | None = None
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        emoji, label = STATE_FR[self.state]
        return {
            "state": self.state,
            "emoji": emoji,
            "label": label,
            "first_touched_at": self.first_touched_at.isoformat() if self.first_touched_at else None,
            "last_touched_at": self.last_touched_at.isoformat() if self.last_touched_at else None,
            "confirmed_at": self.confirmed_at.isoformat() if self.confirmed_at else None,
            "invalidated_at": self.invalidated_at.isoformat() if self.invalidated_at else None,
            "note": self.note,
        }


def _resample(hourly: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    if timeframe == "1h" or hourly.empty:
        return hourly
    rule = {"4h": "4h", "1d": "1D"}[timeframe]
    return hourly.resample(rule, label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}
    ).dropna()


def track(kind: str, value: float, condition: str, hourly: pd.DataFrame | None,
          published_at: datetime) -> LevelState:
    """The state of one level, from the closed hourly bars after the video."""

    if hourly is None or hourly.empty:
        return LevelState("NOT_WATCHED", note="Aucun prix disponible pour cet actif.")
    stamp = align_stamp(published_at, hourly.index)
    frame = hourly.loc[hourly.index >= stamp]
    if frame.empty:
        return LevelState("WAITING", note="Aucune bougie close depuis la vidéo.")

    # Entries and supports are reached from above, targets from below.
    touched = frame[frame["low"] <= value] if kind in FROM_ABOVE else frame[frame["high"] >= value]
    if touched.empty:
        return LevelState("WAITING")

    first = pd.Timestamp(touched.index[0]).to_pydatetime()
    last = pd.Timestamp(touched.index[-1]).to_pydatetime()
    state = LevelState("TOUCHED", first_touched_at=first, last_touched_at=last)

    if kind in {"TARGET", "TAKE_PROFIT"}:
        state.state = "TARGET_REACHED"
        return state

    label, timeframe, side = CONDITIONS.get(condition, CONDITIONS["UNKNOWN"])
    if timeframe is not None:
        bars = _resample(frame, timeframe)
        bars = bars.loc[bars.index >= pd.Timestamp(touched.index[0]).floor("h")]
        closes = bars[bars["close"] > value] if side == "above" else bars[bars["close"] < value]
        if not closes.empty:
            moment = pd.Timestamp(closes.index[0]).to_pydatetime()
            if kind == "INVALIDATION":
                state.state = "INVALIDATED"
                state.invalidated_at = moment
            else:
                state.state = "CONFIRMED"
                state.confirmed_at = moment
            state.note = f"{label} constatée."
            return state
        state.note = f"Touché, mais la condition « {label.lower()} » n'est pas remplie."
    else:
        state.note = "Aucune condition de confirmation donnée dans la vidéo : touché seulement."

    # A confirmation level reached, then lost again on the latest close.
    if kind == "CONFIRMATION" and float(frame["close"].iloc[-1]) < value:
        state.state = "TESTED_LOST"
    return state

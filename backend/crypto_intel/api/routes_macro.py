"""« 🌍 Pourquoi le marché bouge ? » - the macro radar, served to the page.

Fifteen drivers are watched; five reach the home. The route reads the current
cycle, compares it with the previous recorded one, and carries the recorded
history so the page can show how the regime moved through the day.

The reading is computed here from measured series, never from a stored
narrative: the snapshots are used to say what *changed*, not to serve a stale
state as if it were current.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException

from ..engines.macro_drivers import BY_KEY, DIRECTION_FR, build
from ..engines.pit_view import DataCache, PointInTimeView
from ..history.macro_cycles import cycle_history, previous_cycle

router = APIRouter(tags=["macro"])


def _radar(now: datetime) -> dict[str, Any]:
    view = PointInTimeView(DataCache(), now)
    return build(view, now=now, previous=previous_cycle(now))


@router.get("/macro/drivers")
def macro_drivers(history_hours: int = 24) -> dict[str, Any]:
    """The five drivers that explain the current regime, and the ten behind them."""

    now = datetime.now(UTC)
    radar = _radar(now)
    radar["history"] = cycle_history(now, hours=max(3, min(history_hours, 168)))
    # The page needs a word for each direction; the engine keeps the enum.
    radar["direction_labels"] = {
        key: {"emoji": emoji, "label": label} for key, (emoji, label) in DIRECTION_FR.items()
    }
    return radar


@router.get("/macro/drivers/{key}")
def macro_driver(key: str) -> dict[str, Any]:
    """One driver in full: its values, why it matters, and what comes next."""

    driver = BY_KEY.get(key)
    if driver is None:
        raise HTTPException(404, f"Moteur macro inconnu : '{key}'.")
    now = datetime.now(UTC)
    radar = _radar(now)
    reading = next((d for d in radar["drivers"] if d["key"] == key), None)
    if reading is None:  # pragma: no cover - every driver is read every cycle
        raise HTTPException(503, f"Le moteur '{key}' n'a pas pu être lu.")
    emoji, label = DIRECTION_FR[reading["direction"]]
    return {
        **reading,
        "direction_emoji": emoji,
        "direction_label": label,
        "as_of": radar["as_of"],
        "next_check": radar["next_check"],
        "rank": [d["key"] for d in radar["drivers"]].index(key) + 1,
        "watched": radar["watched"],
    }

"""Did the market actually confirm the catalyst?

A protocol change, an approved filing or a fund-flow report is a fact about
the world. Whether it mattered is a separate question, and it is answered by
measuring the market around the moment the news became public:

    before   the days leading in - was it already being priced?
    at       the hours around it - did anything move at all?
    after    1 h, 4 h, 24 h, 3 d, 7 d, 30 d - what stuck?

Prices, volume, open interest and funding are read over the same windows, so a
move can be told apart from a shrug. A good announcement followed by a fall is
reported as such: CATALYST_REJECTED_BY_MARKET. Nothing here converts a
reaction into a recommendation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

import pandas as pd

from ..core.enums import Asset, Timeframe
from .factor_semantics import fr_number
from .pit_view import PointInTimeView


class ReactionState(StrEnum):
    CONFIRMED_BY_MARKET = "CATALYST_CONFIRMED_BY_MARKET"
    NOT_PRICED = "CATALYST_NOT_PRICED"
    ALREADY_PRICED = "CATALYST_ALREADY_PRICED"
    REJECTED_BY_MARKET = "CATALYST_REJECTED_BY_MARKET"
    MIXED_REACTION = "CATALYST_MIXED_REACTION"
    UNKNOWN = "UNKNOWN"


STATE_FR = {
    ReactionState.CONFIRMED_BY_MARKET: "Confirmé par le marché",
    ReactionState.NOT_PRICED: "Pas encore intégré par le marché",
    ReactionState.ALREADY_PRICED: "Déjà intégré avant l'annonce",
    ReactionState.REJECTED_BY_MARKET: "Rejeté par le marché",
    ReactionState.MIXED_REACTION: "Réaction mitigée",
    ReactionState.UNKNOWN: "Réaction non mesurable",
}
STATE_EMOJI = {
    ReactionState.CONFIRMED_BY_MARKET: "🟢",
    ReactionState.NOT_PRICED: "⚪",
    ReactionState.ALREADY_PRICED: "🟡",
    ReactionState.REJECTED_BY_MARKET: "🔴",
    ReactionState.MIXED_REACTION: "🟠",
    ReactionState.UNKNOWN: "⚪",
}

#: Windows measured after the moment, and the one measured before it.
AFTER_WINDOWS = (
    ("1h", timedelta(hours=1)),
    ("4h", timedelta(hours=4)),
    ("24h", timedelta(hours=24)),
    ("3j", timedelta(days=3)),
    ("7j", timedelta(days=7)),
    ("30j", timedelta(days=30)),
)
BEFORE_WINDOW = timedelta(days=7)
#: A move smaller than this is noise, whatever its sign.
NOISE_PCT = 1.0
#: A move this size is a real reaction.
MEANINGFUL_PCT = 3.0


@dataclass(slots=True)
class Reaction:
    asset: str
    at: datetime
    state: ReactionState = ReactionState.UNKNOWN
    before_pct: float | None = None
    after: dict[str, float] = field(default_factory=dict)
    volume_ratio: float | None = None
    oi_change_pct: float | None = None
    funding_change: float | None = None
    measurable_windows: list[str] = field(default_factory=list)
    sentence: str = ""

    @property
    def label(self) -> str:
        return STATE_FR[self.state]

    @property
    def emoji(self) -> str:
        return STATE_EMOJI[self.state]

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset": self.asset,
            "at": self.at.isoformat(),
            "state": self.state.value,
            "label": self.label,
            "emoji": self.emoji,
            "before_pct": round(self.before_pct, 2) if self.before_pct is not None else None,
            "after": {k: round(v, 2) for k, v in self.after.items()},
            "volume_ratio": round(self.volume_ratio, 2) if self.volume_ratio is not None else None,
            "oi_change_pct": round(self.oi_change_pct, 2) if self.oi_change_pct is not None else None,
            "funding_change": (
                round(self.funding_change, 5) if self.funding_change is not None else None
            ),
            "measured_windows": self.measurable_windows,
            "sentence": self.sentence,
        }


def _price_at(frame: pd.DataFrame, when: datetime) -> float | None:
    if frame is None or frame.empty:
        return None
    stamp = pd.Timestamp(when)
    if frame.index.tz is None:
        stamp = stamp.tz_localize(None)
    window = frame.loc[:stamp]
    return float(window["close"].iloc[-1]) if len(window) else None


def _change(frame: pd.DataFrame, start: datetime, end: datetime) -> float | None:
    first, last = _price_at(frame, start), _price_at(frame, end)
    if first is None or last is None or not first:
        return None
    return (last / first - 1) * 100


def _volume_ratio(frame: pd.DataFrame, when: datetime) -> float | None:
    """Volume of the day after, against the twenty days before."""

    if frame is None or frame.empty:
        return None
    stamp = pd.Timestamp(when)
    if frame.index.tz is None:
        stamp = stamp.tz_localize(None)
    before = frame.loc[:stamp]["volume"].tail(20)
    after = frame.loc[stamp:]["volume"].head(1)
    if len(before) < 5 or after.empty or not float(before.mean()):
        return None
    return float(after.iloc[0]) / float(before.mean())


def measure(view: PointInTimeView, asset: Asset, at: datetime) -> Reaction:
    """The market around one moment, on every window the data can cover."""

    reaction = Reaction(asset=asset.value, at=at)
    hourly = view.candles(asset.value, Timeframe.H1)
    daily = view.candles(asset.value, Timeframe.D1)
    if (hourly is None or hourly.empty) and (daily is None or daily.empty):
        reaction.sentence = "Aucune bougie disponible autour de cette date."
        return reaction

    reaction.before_pct = _change(daily, at - BEFORE_WINDOW, at)
    for label, span in AFTER_WINDOWS:
        frame = hourly if span <= timedelta(hours=24) else daily
        # Only windows the clock has actually passed are measured.
        if at + span > view.as_of:
            continue
        change = _change(frame, at, at + span)
        if change is not None:
            reaction.after[label] = change
            reaction.measurable_windows.append(label)
    reaction.volume_ratio = _volume_ratio(daily, at)

    oi_points = list(view.points("oi.contracts_bybit", asset.value))
    if oi_points:
        before = next((p.value for p in reversed(oi_points) if p.timestamp <= at), None)
        after = next((p.value for p in oi_points if p.timestamp >= at + timedelta(days=1)), None)
        if before and after:
            reaction.oi_change_pct = (after / before - 1) * 100
    funding_points = view.points("funding.rate", asset.value)
    if funding_points:
        before = next((p.value for p in reversed(funding_points) if p.timestamp <= at), None)
        after = next((p.value for p in funding_points if p.timestamp >= at + timedelta(days=1)), None)
        if before is not None and after is not None:
            reaction.funding_change = (after - before) * 100

    reaction.state = _classify(reaction)
    reaction.sentence = _explain(reaction)
    return reaction


def _classify(reaction: Reaction) -> ReactionState:
    """The reading follows the market, never the hoped-for direction."""

    after = reaction.after
    if not after:
        return ReactionState.UNKNOWN
    horizon = after.get("24h", after.get("4h", after.get("1h")))
    if horizon is None:
        return ReactionState.UNKNOWN
    later = after.get("7j", after.get("3j"))
    before = reaction.before_pct

    strong_up = horizon >= MEANINGFUL_PCT
    strong_down = horizon <= -MEANINGFUL_PCT
    flat = abs(horizon) < NOISE_PCT

    if strong_down:
        return ReactionState.REJECTED_BY_MARKET
    if strong_up:
        # A rise that gives everything back within the week is not a confirmation.
        if later is not None and later <= 0:
            return ReactionState.MIXED_REACTION
        return ReactionState.CONFIRMED_BY_MARKET
    if flat:
        # Nothing moved: either the market had already priced the run-up, or
        # it has not taken the news on board at all.
        if before is not None and before >= MEANINGFUL_PCT:
            return ReactionState.ALREADY_PRICED
        return ReactionState.NOT_PRICED
    return ReactionState.MIXED_REACTION


def _explain(reaction: Reaction) -> str:
    after = reaction.after
    horizon_key = "24h" if "24h" in after else next(iter(after), None)
    if horizon_key is None:
        return "Fenêtres de mesure non encore écoulées."
    move = after[horizon_key]
    parts = [
        f"{fr_number(move, 1, signed=True)} % sur {horizon_key} après la publication"
    ]
    if reaction.before_pct is not None:
        parts.append(f"{fr_number(reaction.before_pct, 1, signed=True)} % la semaine précédente")
    if reaction.volume_ratio is not None:
        parts.append(f"volume ×{fr_number(reaction.volume_ratio, 1)} par rapport à sa moyenne")
    if reaction.oi_change_pct is not None:
        parts.append(f"open interest {fr_number(reaction.oi_change_pct, 1, signed=True)} %")
    return " · ".join(parts) + "."

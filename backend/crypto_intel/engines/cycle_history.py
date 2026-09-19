"""Past cycles, measured - shown as history, never as a schedule.

For each halving the engine measures what actually happened: how long the
market took to reach a new high, how far it went, how deep the fall that
followed was, how long the bear lasted and how long the recovery took. The
same figures are computed for the cycle under way, with its measures marked
as still open.

A normalised comparison (100 at each halving) lets the current cycle be put
beside the previous ones. It is a resemblance, never a forecast: nothing here
converts "the last cycles did X" into "the next top is in N days".

Bottoms are only named once a later high confirms them. In real time the
engine says "plus bas local actuel" - never "this is the bottom".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pandas as pd

#: Beyond this, a cycle is compared to the next halving instead.
MAX_CYCLE_DAYS = 1500
#: A cycle's own peak is looked for in its first two years: without this, the
#: next cycle's higher high would be credited to the previous one.
ATH_WINDOW_DAYS = 730
#: A drop of this size over 30 days is an exceptional market shock.
SHOCK_30D_PCT = -35.0


def _utc(value: Any) -> datetime:
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is None:
        stamp = stamp.tz_localize("UTC")
    return stamp.to_pydatetime().astimezone(UTC)


@dataclass(slots=True)
class CycleStats:
    index: int
    halving: datetime
    halving_price: float
    ath: float | None
    ath_date: datetime | None
    days_to_ath: int | None
    gain_from_halving_pct: float | None
    drawdown_after_ath_pct: float | None
    bottom: float | None
    bottom_date: datetime | None
    bear_days: int | None
    recovery_days: int | None
    ongoing: bool

    @property
    def name(self) -> str:
        return f"Cycle {self.halving.year}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "name": self.name,
            "halving": self.halving.isoformat(),
            "halving_price": round(self.halving_price, 2),
            "ath": round(self.ath, 2) if self.ath else None,
            "ath_date": self.ath_date.isoformat() if self.ath_date else None,
            "days_to_ath": self.days_to_ath,
            "gain_from_halving_pct": (
                round(self.gain_from_halving_pct, 0) if self.gain_from_halving_pct is not None else None
            ),
            "drawdown_after_ath_pct": (
                round(self.drawdown_after_ath_pct, 1)
                if self.drawdown_after_ath_pct is not None else None
            ),
            "bottom": round(self.bottom, 2) if self.bottom else None,
            "bottom_date": self.bottom_date.isoformat() if self.bottom_date else None,
            "bottom_confirmed": self.bottom_date is not None and not self.ongoing,
            "bear_days": self.bear_days,
            "recovery_days": self.recovery_days,
            "ongoing": self.ongoing,
        }


def cycle_stats(daily: pd.DataFrame, halvings: list[datetime],
                as_of: datetime | None = None) -> list[CycleStats]:
    """One row per halving, measured on the bars we actually have."""

    if daily is None or daily.empty or not halvings:
        return []
    as_of = as_of or _utc(daily.index[-1])
    ordered = sorted(h for h in halvings if h <= as_of)
    out: list[CycleStats] = []
    for position, halving in enumerate(ordered):
        following = ordered[position + 1] if position + 1 < len(ordered) else None
        end = min(following or as_of, halving + timedelta(days=MAX_CYCLE_DAYS), as_of)
        window = daily.loc[str(halving.date()): str(end.date())]
        if window.empty:
            continue
        halving_price = float(window["close"].iloc[0])
        peak_end = min(end, halving + timedelta(days=ATH_WINDOW_DAYS))
        peak_window = daily.loc[str(halving.date()): str(peak_end.date())]
        highs = peak_window["high"]
        ath_idx = highs.idxmax()
        ath = float(highs.loc[ath_idx])
        ath_date = _utc(ath_idx)
        # A cycle whose high is its last bar has not peaked: it is open.
        peaked = ath_date < as_of - timedelta(days=30)
        after = window.loc[ath_idx:]
        bottom = bottom_date = drawdown = bear_days = recovery_days = None
        if peaked and len(after) > 1:
            lows = after["low"]
            bottom_idx = lows.idxmin()
            bottom = float(lows.loc[bottom_idx])
            bottom_date = _utc(bottom_idx)
            drawdown = (bottom / ath - 1) * 100
            bear_days = max(0, (bottom_date - ath_date).days)
            # Recovery may well happen after the next halving: it is counted
            # wherever it happens, or left open.
            back = daily.loc[bottom_idx:]
            regained = back[back["close"] >= ath]
            recovery_days = (
                max(0, (_utc(regained.index[0]) - bottom_date).days) if len(regained) else None
            )
        out.append(CycleStats(
            index=position + 1,
            halving=halving,
            halving_price=halving_price,
            ath=ath,
            ath_date=ath_date,
            days_to_ath=max(0, (ath_date - halving).days),
            gain_from_halving_pct=(ath / halving_price - 1) * 100 if halving_price else None,
            drawdown_after_ath_pct=drawdown,
            bottom=bottom,
            bottom_date=bottom_date,
            bear_days=bear_days,
            recovery_days=recovery_days,
            ongoing=following is None,
        ))
    return out


def normalised_cycles(daily: pd.DataFrame, halvings: list[datetime], *,
                      step_days: int = 7, as_of: datetime | None = None) -> list[dict[str, Any]]:
    """Each cycle rebased to 100 on its halving - a comparison, not a model."""

    if daily is None or daily.empty or not halvings:
        return []
    as_of = as_of or _utc(daily.index[-1])
    ordered = sorted(h for h in halvings if h <= as_of)
    out: list[dict[str, Any]] = []
    for position, halving in enumerate(ordered):
        following = ordered[position + 1] if position + 1 < len(ordered) else None
        end = min(following or as_of, halving + timedelta(days=MAX_CYCLE_DAYS), as_of)
        window = daily.loc[str(halving.date()): str(end.date())]
        if len(window) < 30:
            continue
        base = float(window["close"].iloc[0])
        points = [
            {"day": (_utc(stamp) - halving).days, "index": round(float(close) / base * 100, 1)}
            for stamp, close in window["close"].iloc[::step_days].items()
        ]
        out.append({
            "name": f"Cycle {halving.year}",
            "halving": halving.isoformat(),
            "ongoing": following is None,
            "points": points,
        })
    return out


def price_series(daily: pd.DataFrame, *, step_days: int = 7) -> list[dict[str, Any]]:
    """The chart's own series: weekly closes, plus the very last daily bar."""

    if daily is None or daily.empty:
        return []
    sampled = daily["close"].iloc[::step_days]
    points = [{"t": _utc(stamp).date().isoformat(), "c": round(float(value), 2)}
              for stamp, value in sampled.items()]
    last_stamp, last_close = daily.index[-1], float(daily["close"].iloc[-1])
    if points and points[-1]["t"] != _utc(last_stamp).date().isoformat():
        points.append({"t": _utc(last_stamp).date().isoformat(), "c": round(last_close, 2)})
    return points


def annotations(daily: pd.DataFrame, halvings: list[datetime],
                stats: list[CycleStats], as_of: datetime | None = None) -> list[dict[str, Any]]:
    """A few markers per cycle: halvings, new highs, confirmed bottoms, shocks."""

    if daily is None or daily.empty:
        return []
    as_of = as_of or _utc(daily.index[-1])
    out: list[dict[str, Any]] = [
        {"kind": "HALVING", "emoji": "⚡", "label": f"Halving {h.year}",
         "date": h.date().isoformat(), "price": None}
        for h in sorted(halvings) if h <= as_of
    ]
    for cycle in stats:
        if cycle.ath_date is not None and not (cycle.ongoing and cycle.ath_date > as_of - timedelta(days=30)):
            out.append({"kind": "ATH", "emoji": "🏆", "label": f"Sommet {cycle.ath_date.year}",
                        "date": cycle.ath_date.date().isoformat(), "price": round(cycle.ath or 0, 2)})
        if cycle.bottom_date is not None and not cycle.ongoing:
            out.append({"kind": "BOTTOM", "emoji": "🔻",
                        "label": f"Creux majeur {cycle.bottom_date.year} (confirmé a posteriori)",
                        "date": cycle.bottom_date.date().isoformat(),
                        "price": round(cycle.bottom or 0, 2)})
    # Exceptional shocks: measured, one per event, not per day.
    closes = daily["close"]
    change = closes / closes.shift(30) - 1
    shocks = change[change <= SHOCK_30D_PCT / 100]
    last_date: datetime | None = None
    for stamp, value in shocks.items():
        day = _utc(stamp)
        if last_date is not None and (day - last_date).days < 180:
            continue
        last_date = day
        out.append({"kind": "SHOCK", "emoji": "🌍",
                    "label": f"Choc de marché ({value * 100:.0f} % en 30 j)",
                    "date": day.date().isoformat(), "price": round(float(closes.loc[stamp]), 2)})
    return sorted(out, key=lambda item: item["date"])


def current_low(daily: pd.DataFrame, since: datetime) -> dict[str, Any] | None:
    """The lowest price since a date - called a local low, never "the bottom"."""

    if daily is None or daily.empty:
        return None
    window = daily.loc[str(since.date()):]
    if window.empty:
        return None
    idx = window["low"].idxmin()
    return {
        "price": round(float(window["low"].loc[idx]), 2),
        "date": _utc(idx).date().isoformat(),
        "label": "Plus bas local actuel",
    }

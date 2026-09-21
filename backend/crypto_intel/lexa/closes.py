"""TOUCH ≠ CLOSE ≠ CONFIRMATION.

A CloseCondition says: `required_closes` consecutive CLOSED candles on
`timeframe` beyond `level` (ABOVE or BELOW); with `confirmation_window`, the
breakout must then hold that many more closed candles.

    WAITING              never reached since the video
    TOUCHED_NOT_CLOSED   the price is beyond the level now, the candle is still open
    CLOSED_ABOVE/BELOW   closed beyond, but not yet the number of closes required,
                         or the confirmation window is still running
    CONFIRMED            the stated closes happened (and held through the window)
    FAILED               reached, but the candle closed back on the wrong side
                         (or the breakout was lost inside the window)
    INVALIDATED          the scenario itself was invalidated

The forming candle is never counted as a close. The close time is Binance's.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .market import TIMEFRAME_FR, Bar, countdown, next_close, paris

STATUS_FR = {
    "WAITING": ("⏳", "Pas encore atteint"),
    "TOUCHED_NOT_CLOSED": ("⏳", "Attente clôture"),
    "CLOSED_ABOVE": ("🕯️", "Clôturé au-dessus — confirmation en cours"),
    "CLOSED_BELOW": ("🕯️", "Clôturé en dessous — confirmation en cours"),
    "CONFIRMED": ("🚀", "Confirmé"),
    "FAILED": ("❌", "Clôture non confirmée"),
    "INVALIDATED": ("⚠️", "Scénario invalidé"),
}


@dataclass(slots=True)
class CloseCondition:
    level: float
    operator: str = "ABOVE"  # ABOVE | BELOW
    timeframe: str = "1D"
    required_closes: int = 1
    confirmation_window: int | None = None

    def beyond(self, value: float) -> bool:
        return value > self.level if self.operator == "ABOVE" else value < self.level

    def reached(self, bar: Bar) -> bool:
        return bar.high >= self.level if self.operator == "ABOVE" else bar.low <= self.level

    def describe(self) -> str:
        side = "au-dessus" if self.operator == "ABOVE" else "en dessous"
        closes = ("une clôture" if self.required_closes == 1
                  else f"{self.required_closes} clôtures consécutives")
        text = f"{closes} {TIMEFRAME_FR.get(self.timeframe, self.timeframe)} {side} du niveau"
        if self.confirmation_window:
            text += f", puis le maintien pendant {self.confirmation_window} bougie(s)"
        return text[0].upper() + text[1:]


@dataclass(slots=True)
class CloseEvaluation:
    status: str
    closes_beyond: int = 0
    first_touch_at: datetime | None = None
    closed_beyond_at: datetime | None = None
    confirmed_at: datetime | None = None
    failed_at: datetime | None = None
    next_close_at: datetime | None = None
    seconds_to_close: float | None = None
    message: str = ""
    history: list[tuple[datetime, str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        emoji, label = STATUS_FR[self.status]
        iso = lambda d: d.isoformat() if d else None  # noqa: E731
        return {
            "status": self.status, "emoji": emoji, "label": label,
            "closes_beyond": self.closes_beyond,
            "first_touch_at": iso(self.first_touch_at),
            "closed_beyond_at": iso(self.closed_beyond_at),
            "confirmed_at": iso(self.confirmed_at), "failed_at": iso(self.failed_at),
            "next_close_at": iso(self.next_close_at),
            "next_close_paris": paris(self.next_close_at) if self.next_close_at else None,
            "countdown": countdown(self.seconds_to_close) if self.seconds_to_close is not None else None,
            "message": self.message,
            "history": [{"at": at.isoformat(), "event": kind, "text": text}
                        for at, kind, text in self.history],
        }


def evaluate(cond: CloseCondition, bars: list[Bar], *, since: datetime, now: datetime,
             price: float | None, invalidated: bool = False) -> CloseEvaluation:
    """Walk the candles that CLOSED after the video, then look at the open one."""

    closed = [b for b in bars if b.closed and b.close_time > since]
    forming = next((b for b in bars if not b.closed), None)
    ev = CloseEvaluation(status="WAITING", next_close_at=next_close(now, cond.timeframe))
    ev.seconds_to_close = (ev.next_close_at - now).total_seconds()
    side = "au-dessus" if cond.operator == "ABOVE" else "en dessous"
    tf = TIMEFRAME_FR.get(cond.timeframe, cond.timeframe)

    streak = 0
    confirmed_at: datetime | None = None
    held = 0
    for bar in closed:
        if ev.first_touch_at is None and cond.reached(bar):
            ev.first_touch_at = max(bar.open_time, since)
            ev.history.append((ev.first_touch_at, "TOUCHED", f"Niveau touché ({tf})"))
        if cond.beyond(bar.close):
            streak += 1
            ev.closed_beyond_at = bar.close_time
            ev.history.append((bar.close_time, "CLOSED_BEYOND", f"Clôture {tf} {side} du niveau"))
            if confirmed_at is None and streak >= cond.required_closes:
                if not cond.confirmation_window:
                    confirmed_at = bar.close_time
                    ev.history.append((bar.close_time, "CONFIRMED", "Condition de clôture remplie"))
                else:
                    held += 1
                    if held > cond.confirmation_window:
                        confirmed_at = bar.close_time
                        ev.history.append((bar.close_time, "CONFIRMED",
                                           "Cassure maintenue sur la fenêtre de confirmation"))
        elif confirmed_at is not None:
            if streak:
                ev.history.append((bar.close_time, "RETURNED",
                                   f"Clôture {tf} revenue de l'autre côté après la confirmation"))
            streak = 0
        else:
            if cond.reached(bar):
                ev.failed_at = bar.close_time
                ev.history.append((bar.close_time, "FAILED",
                                   f"Touché mais clôture {tf} revenue de l'autre côté"))
            elif streak and confirmed_at is None:
                ev.failed_at = bar.close_time
                ev.history.append((bar.close_time, "FAILED", "Cassure perdue avant confirmation"))
            streak, held = 0, 0

    ev.closes_beyond = streak
    ev.confirmed_at = confirmed_at
    beyond_now = price is not None and cond.beyond(price)
    if forming is not None and ev.first_touch_at is None and cond.reached(forming):
        ev.first_touch_at = max(forming.open_time, since)

    if invalidated:
        ev.status, ev.message = "INVALIDATED", "Le scénario a été invalidé : la condition n'est plus suivie."
    elif confirmed_at is not None:
        ev.status = "CONFIRMED"
        ev.message = f"Condition remplie : {cond.describe().lower()}."
    elif streak:
        ev.status = "CLOSED_ABOVE" if cond.operator == "ABOVE" else "CLOSED_BELOW"
        left = max(cond.required_closes - streak, 0)
        ev.message = (f"{streak} clôture(s) {tf} {side} sur {cond.required_closes} requise(s)"
                      + (f" ; encore {left}." if left else
                         f" ; maintien à vérifier sur {cond.confirmation_window} bougie(s)."))
    elif beyond_now:
        ev.status = "TOUCHED_NOT_CLOSED"
        ev.message = (f"Le prix est actuellement {side} du niveau, mais la bougie {tf} "
                      "n'est pas encore clôturée : ce n'est pas une confirmation.")
    elif ev.failed_at is not None:
        ev.status = "FAILED"
        ev.message = f"Le niveau a été atteint, mais la bougie {tf} n'a pas clôturé {side}."
    else:
        ev.message = "Niveau pas encore atteint depuis la vidéo."
    # A countdown only means something while a close is awaited.
    if ev.status not in ("TOUCHED_NOT_CLOSED", "CLOSED_ABOVE", "CLOSED_BELOW"):
        ev.seconds_to_close = None
    return ev

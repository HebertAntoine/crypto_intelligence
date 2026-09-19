"""Where Bitcoin stands in its cycle - described, never predicted.

Inputs, all read as of the moment of the reading:
    - the last halving (its block timestamp, from the chain) and the days since;
    - the next halving, estimated from the observed block pace (display only);
    - the all-time high of the daily closes and highs, its date, the drawdown;
    - the long-term trend: price against its 200-day average and that average's
      slope over 30 days;
    - the rebound from the lowest price since the high.

The phase comes from several of these together. Days since the halving alone
never decide it, and no phase carries a date for a future top or bottom: no
such model has been validated. The cycle is context. Its signal is capped and
it can never, alone, turn a decision into BUY or SELL.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import pandas as pd

from .factor_semantics import fr_number


class CyclePhase(StrEnum):
    EARLY_POST_HALVING = "EARLY_POST_HALVING"
    EXPANSION = "EXPANSION"
    PRICE_DISCOVERY = "PRICE_DISCOVERY"
    POST_ATH_DRAWDOWN = "POST_ATH_DRAWDOWN"
    RECOVERY = "RECOVERY"
    MATURE_RANGE = "MATURE_RANGE"
    DEEP_DRAWDOWN = "DEEP_DRAWDOWN"
    UNKNOWN = "UNKNOWN"


PHASE_FR = {
    CyclePhase.EARLY_POST_HALVING: "Début de cycle post-halving",
    CyclePhase.EXPANSION: "Expansion",
    CyclePhase.PRICE_DISCOVERY: "Découverte de prix (proche du record)",
    CyclePhase.POST_ATH_DRAWDOWN: "Repli après le sommet",
    CyclePhase.RECOVERY: "Post-ATH / récupération",
    CyclePhase.MATURE_RANGE: "Cycle mature, sans tendance nette",
    CyclePhase.DEEP_DRAWDOWN: "Repli profond",
    CyclePhase.UNKNOWN: "Indéterminé",
}

#: The contextual lean of each phase - small, and capped again by the family.
PHASE_LEAN = {
    CyclePhase.EARLY_POST_HALVING: 0.1,
    CyclePhase.EXPANSION: 0.2,
    CyclePhase.PRICE_DISCOVERY: 0.1,
    CyclePhase.POST_ATH_DRAWDOWN: -0.2,
    CyclePhase.RECOVERY: 0.1,
    CyclePhase.MATURE_RANGE: 0.0,
    CyclePhase.DEEP_DRAWDOWN: -0.1,
    CyclePhase.UNKNOWN: 0.0,
}

#: A phase that raises structural risk without saying anything about timing.
ELEVATED_RISK_PHASES = {CyclePhase.POST_ATH_DRAWDOWN, CyclePhase.MATURE_RANGE, CyclePhase.PRICE_DISCOVERY}


@dataclass(slots=True)
class CycleReading:
    phase: CyclePhase
    price: float
    ath: float
    ath_date: datetime
    drawdown_pct: float
    days_since_ath: int
    last_halving: datetime | None
    days_since_halving: int | None
    next_halving_estimate: datetime | None
    sma200: float | None
    sma200_slope_pct: float | None
    rebound_from_low_pct: float | None
    lean: float
    sentence: str

    @property
    def label(self) -> str:
        return PHASE_FR[self.phase]

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase.value,
            "phase_label": self.label,
            "price_usd": round(self.price, 2),
            "ath_usd": round(self.ath, 2),
            "ath_date": self.ath_date.isoformat(),
            "drawdown_pct": round(self.drawdown_pct, 1),
            "days_since_ath": self.days_since_ath,
            "last_halving": self.last_halving.isoformat() if self.last_halving else None,
            "days_since_halving": self.days_since_halving,
            "next_halving_estimate": (
                self.next_halving_estimate.isoformat() if self.next_halving_estimate else None
            ),
            "next_halving_is_estimate": True,
            "sma200_usd": round(self.sma200, 2) if self.sma200 else None,
            "sma200_slope_pct": round(self.sma200_slope_pct, 2) if self.sma200_slope_pct is not None else None,
            "rebound_from_low_pct": (
                round(self.rebound_from_low_pct, 1) if self.rebound_from_low_pct is not None else None
            ),
            "lean": round(self.lean, 3),
            "sentence": self.sentence,
            "elevated_structural_risk": self.phase in ELEVATED_RISK_PHASES,
        }


def classify(
    *,
    drawdown_pct: float,
    days_since_ath: int,
    above_sma200: bool | None,
    sma200_rising: bool | None,
    rebound_from_low_pct: float | None,
    days_since_halving: int | None,
) -> CyclePhase:
    """Several conditions together; the halving clock is only one of them."""

    if drawdown_pct <= -50:
        return CyclePhase.DEEP_DRAWDOWN
    if drawdown_pct > -5 and days_since_ath <= 30:
        return CyclePhase.PRICE_DISCOVERY
    if drawdown_pct <= -20:
        improving = bool(above_sma200) and (
            bool(sma200_rising) or (rebound_from_low_pct is not None and rebound_from_low_pct >= 30)
        )
        return CyclePhase.RECOVERY if improving else CyclePhase.POST_ATH_DRAWDOWN
    if above_sma200 and sma200_rising:
        if days_since_halving is not None and days_since_halving < 180:
            return CyclePhase.EARLY_POST_HALVING
        return CyclePhase.EXPANSION
    return CyclePhase.MATURE_RANGE


def read_cycle(
    daily: pd.DataFrame,
    *,
    halvings: list[datetime],
    next_halving: datetime | None,
    as_of: datetime,
) -> CycleReading | None:
    """``daily`` holds closed daily bars known at ``as_of``; ``halvings`` the
    halving block times known then."""

    if daily is None or len(daily) < 220:
        return None
    highs = daily["high"]
    closes = daily["close"]
    price = float(closes.iloc[-1])
    ath_idx = highs.idxmax()
    ath = float(highs.loc[ath_idx])
    ath_date = pd.Timestamp(ath_idx).to_pydatetime()
    if ath_date.tzinfo is None:
        ath_date = ath_date.replace(tzinfo=UTC)
    drawdown = (price / ath - 1) * 100
    days_since_ath = max(0, (as_of - ath_date).days)
    sma = closes.rolling(200).mean()
    sma_now = float(sma.iloc[-1]) if pd.notna(sma.iloc[-1]) else None
    sma_past = float(sma.iloc[-31]) if len(sma) > 31 and pd.notna(sma.iloc[-31]) else None
    slope = (sma_now / sma_past - 1) * 100 if sma_now and sma_past else None
    since_ath = daily.loc[ath_idx:]
    low_since = float(since_ath["low"].min()) if len(since_ath) else None
    rebound = (price / low_since - 1) * 100 if low_since else None
    past = [h for h in halvings if h <= as_of]
    last_halving = max(past) if past else None
    days_halving = (as_of - last_halving).days if last_halving else None

    phase = classify(
        drawdown_pct=drawdown,
        days_since_ath=days_since_ath,
        above_sma200=(price > sma_now) if sma_now else None,
        sma200_rising=(slope > 0) if slope is not None else None,
        rebound_from_low_pct=rebound,
        days_since_halving=days_halving,
    )
    sentence = _sentence(phase, drawdown, rebound)
    return CycleReading(
        phase=phase, price=price, ath=ath, ath_date=ath_date, drawdown_pct=drawdown,
        days_since_ath=days_since_ath, last_halving=last_halving,
        days_since_halving=days_halving,
        next_halving_estimate=next_halving if next_halving and next_halving > as_of else None,
        sma200=sma_now, sma200_slope_pct=slope, rebound_from_low_pct=rebound,
        lean=PHASE_LEAN[phase], sentence=sentence,
    )


def _sentence(phase: CyclePhase, drawdown: float, rebound: float | None) -> str:
    below = f"{fr_number(abs(drawdown), 0)} %"
    return {
        CyclePhase.DEEP_DRAWDOWN: f"Bitcoin reste {below} sous son record : le marché est en repli profond.",
        CyclePhase.PRICE_DISCOVERY: "Bitcoin évolue près de son record : aucun niveau historique au-dessus.",
        CyclePhase.RECOVERY: (
            f"Bitcoin reste {below} sous son sommet de cycle malgré un rebond"
            + (f" de {fr_number(rebound, 0)} % depuis son plus bas." if rebound else ".")
        ),
        CyclePhase.POST_ATH_DRAWDOWN: (
            f"Bitcoin est {below} sous son sommet et sa tendance longue ne s'est pas encore redressée."
        ),
        CyclePhase.EARLY_POST_HALVING: "Début de cycle après le halving, avec une tendance longue haussière.",
        CyclePhase.EXPANSION: f"Tendance longue haussière, {below} sous le record.",
        CyclePhase.MATURE_RANGE: f"Bitcoin est {below} sous son record, sans tendance longue nette.",
        CyclePhase.UNKNOWN: "Historique insuffisant pour situer le cycle.",
    }[phase]

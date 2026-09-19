"""Where Bitcoin stands in its cycle, read from the market - not from a clock.

The halving is a landmark, never a rule: the phase comes from several
dimensions read together on daily closes.

    A. position against the all-time high  - new high, distance, depth, age
    B. long-term structure                 - higher/lower highs and lows, 200 d
    C. long-term momentum                  - accelerating, slowing, reversing
    D. halving                             - days since, limited weight
    E. volatility regime                   - expansion, contraction, stress
    F. flows                               - when a measured source exists

Two properties matter as much as the rules themselves:

*Hysteresis.* A phase does not change because the price fell 5 % in two days.
A new phase is proposed as a *candidate* and becomes current only once it has
held for ``CONFIRMATION_DAYS`` daily closes. The reading therefore carries a
current phase, a candidate, and how far that candidate is confirmed.

*No hindsight.* The timeline is computed forward, each day from the data
known that day, so the history of the classification is what it was - never
what it would be with today's knowledge.

Nothing here forecasts. A phase describes the present; the comparison with
past cycles is shown as history, never as a schedule.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

import numpy as np
import pandas as pd

ENGINE_VERSION = "cycle-regime-1"

#: Daily closes a new phase must hold before it replaces the current one.
CONFIRMATION_DAYS = 15
#: Window used to say whether the regime improves or degrades.
DIRECTION_WINDOW_DAYS = 30
DIRECTION_EPSILON = 0.06


class Phase(StrEnum):
    ACCUMULATION = "ACCUMULATION"
    RECOVERY = "RECOVERY"
    EXPANSION = "EXPANSION"
    PRICE_DISCOVERY = "PRICE_DISCOVERY"
    TRANSITION = "TRANSITION"
    DISTRIBUTION_POSSIBLE = "DISTRIBUTION_POSSIBLE"
    BEAR_MARKET = "BEAR_MARKET"
    DEEP_DRAWDOWN = "DEEP_DRAWDOWN"
    UNDETERMINED = "UNDETERMINED"


PHASE_FR = {
    Phase.ACCUMULATION: "Accumulation",
    Phase.RECOVERY: "Récupération",
    Phase.EXPANSION: "Expansion haussière",
    Phase.PRICE_DISCOVERY: "Découverte de prix",
    Phase.TRANSITION: "Transition",
    Phase.DISTRIBUTION_POSSIBLE: "Distribution possible",
    Phase.BEAR_MARKET: "Bear market",
    Phase.DEEP_DRAWDOWN: "Drawdown profond",
    Phase.UNDETERMINED: "Régime indéterminé",
}
PHASE_EMOJI = {
    Phase.ACCUMULATION: "🔵",
    Phase.RECOVERY: "🟢",
    Phase.EXPANSION: "🟢",
    Phase.PRICE_DISCOVERY: "🔥",
    Phase.TRANSITION: "🟠",
    Phase.DISTRIBUTION_POSSIBLE: "🟠",
    Phase.BEAR_MARKET: "🔴",
    Phase.DEEP_DRAWDOWN: "🔴",
    Phase.UNDETERMINED: "⚪",
}
#: One colour per concept, the same everywhere in the application.
PHASE_TONE = {
    Phase.ACCUMULATION: "BLUE",
    Phase.RECOVERY: "GREEN",
    Phase.EXPANSION: "GREEN",
    Phase.PRICE_DISCOVERY: "FIRE",
    Phase.TRANSITION: "ORANGE",
    Phase.DISTRIBUTION_POSSIBLE: "ORANGE",
    Phase.BEAR_MARKET: "RED",
    Phase.DEEP_DRAWDOWN: "RED",
    Phase.UNDETERMINED: "WHITE",
}
#: What each phase leans, as context only. The decision engine caps it again.
PHASE_LEAN = {
    Phase.ACCUMULATION: 0.05,
    Phase.RECOVERY: 0.1,
    Phase.EXPANSION: 0.2,
    Phase.PRICE_DISCOVERY: 0.1,
    Phase.TRANSITION: 0.0,
    Phase.DISTRIBUTION_POSSIBLE: -0.1,
    Phase.BEAR_MARKET: -0.2,
    Phase.DEEP_DRAWDOWN: -0.1,
    Phase.UNDETERMINED: 0.0,
}
ELEVATED_RISK_PHASES = {
    Phase.DISTRIBUTION_POSSIBLE, Phase.TRANSITION, Phase.PRICE_DISCOVERY,
    Phase.BEAR_MARKET, Phase.DEEP_DRAWDOWN,
}


@dataclass(slots=True, frozen=True)
class Dimensions:
    """Everything the classification reads, on one day."""

    price: float
    ath: float
    ath_date: datetime
    drawdown_pct: float
    days_since_ath: int
    new_high: bool
    structure: str            # HIGHER | LOWER | MIXED | UNCLEAR
    sma200: float | None
    sma200_slope_pct: float | None
    above_sma200: bool | None
    momentum: str             # ACCELERATING | SLOWING | REVERSING | STEADY
    volatility: str           # EXPANSION | CONTRACTION | STRESS | NORMAL
    rebound_from_low_pct: float | None
    days_since_halving: int | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "price": round(self.price, 2),
            "ath": round(self.ath, 2),
            "ath_date": self.ath_date.isoformat(),
            "drawdown_pct": round(self.drawdown_pct, 1),
            "days_since_ath": self.days_since_ath,
            "new_high": self.new_high,
            "structure": self.structure,
            "sma200": round(self.sma200, 2) if self.sma200 else None,
            "sma200_slope_pct": (
                round(self.sma200_slope_pct, 2) if self.sma200_slope_pct is not None else None
            ),
            "momentum": self.momentum,
            "volatility": self.volatility,
            "rebound_from_low_pct": (
                round(self.rebound_from_low_pct, 1) if self.rebound_from_low_pct is not None else None
            ),
            "days_since_halving": self.days_since_halving,
        }


def _structure_state(highs: pd.Series, lows: pd.Series) -> str:
    """Long-term structure from two successive quarters of highs and lows."""

    if len(highs) < 240:
        return "UNCLEAR"
    recent_high, past_high = highs.iloc[-120:].max(), highs.iloc[-240:-120].max()
    recent_low, past_low = lows.iloc[-120:].min(), lows.iloc[-240:-120].min()
    higher = recent_high > past_high * 1.02 and recent_low > past_low * 1.02
    lower = recent_high < past_high * 0.98 and recent_low < past_low * 0.98
    if higher:
        return "HIGHER"
    if lower:
        return "LOWER"
    return "MIXED"


def _momentum_state(closes: pd.Series) -> str:
    """Compared with itself: is the trend gaining or losing pace?"""

    if len(closes) < 200:
        return "STEADY"
    now = closes.iloc[-1] / closes.iloc[-91] - 1
    before = closes.iloc[-91] / closes.iloc[-181] - 1
    if now > 0 and before > 0:
        return "ACCELERATING" if now > before * 1.2 else "SLOWING" if now < before * 0.8 else "STEADY"
    if now <= 0 < before:
        return "REVERSING"
    if now < 0 and before < 0:
        return "SLOWING" if now > before else "ACCELERATING"
    return "STEADY"


def _volatility_state(closes: pd.Series) -> str:
    if len(closes) < 400:
        return "NORMAL"
    returns = np.log(closes / closes.shift(1)).dropna()
    recent = float(returns.iloc[-30:].std() * np.sqrt(365))
    base = returns.iloc[-365:].std() * np.sqrt(365)
    if not base or np.isnan(base):
        return "NORMAL"
    ratio = recent / float(base)
    if ratio >= 1.6:
        return "STRESS"
    if ratio >= 1.2:
        return "EXPANSION"
    if ratio <= 0.7:
        return "CONTRACTION"
    return "NORMAL"


def read_dimensions(daily: pd.DataFrame, as_of: datetime,
                    halvings: list[datetime]) -> Dimensions | None:
    """Every dimension, from the bars known at ``as_of`` - nothing later."""

    if daily is None or len(daily) < 260:
        return None
    closes, highs, lows = daily["close"], daily["high"], daily["low"]
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
    days_halving = (as_of - max(past)).days if past else None
    return Dimensions(
        price=price, ath=ath, ath_date=ath_date, drawdown_pct=drawdown,
        days_since_ath=days_since_ath, new_high=days_since_ath <= 30,
        structure=_structure_state(highs, lows), sma200=sma_now, sma200_slope_pct=slope,
        above_sma200=(price > sma_now) if sma_now else None,
        momentum=_momentum_state(closes), volatility=_volatility_state(closes),
        rebound_from_low_pct=rebound, days_since_halving=days_halving,
    )


def dimension_frame(daily: pd.DataFrame, halvings: list[datetime]) -> pd.DataFrame:
    """Every dimension for every day at once - same maths, one pass.

    Reading day by day recomputed 200-day means thousands of times; the
    vectorised form lets the whole timeline be built on each refresh.
    """

    closes, highs, lows = daily["close"], daily["high"], daily["low"]
    frame = pd.DataFrame(index=daily.index)
    frame["price"] = closes
    frame["ath"] = highs.cummax()
    high_values = highs.to_numpy()
    ath_idx = pd.Series(
        np.maximum.accumulate(
            np.where(high_values >= np.maximum.accumulate(high_values), np.arange(len(high_values)), 0)
        ).astype(float),
        index=daily.index,
    )
    frame["drawdown_pct"] = (closes / frame["ath"] - 1) * 100
    positions = np.arange(len(daily), dtype=float)
    frame["ath_position"] = ath_idx
    frame["days_since_ath"] = (positions - ath_idx).clip(lower=0)
    frame["new_high"] = frame["days_since_ath"] <= 30
    sma = closes.rolling(200).mean()
    frame["sma200"] = sma
    frame["sma200_slope_pct"] = (sma / sma.shift(30) - 1) * 100
    frame["above_sma200"] = closes > sma
    # Structure: two successive quarters of highs and lows.
    recent_high, past_high = highs.rolling(120).max(), highs.rolling(120).max().shift(120)
    recent_low, past_low = lows.rolling(120).min(), lows.rolling(120).min().shift(120)
    frame["structure"] = np.where(
        (recent_high > past_high * 1.02) & (recent_low > past_low * 1.02), "HIGHER",
        np.where((recent_high < past_high * 0.98) & (recent_low < past_low * 0.98), "LOWER", "MIXED"),
    )
    frame.loc[past_high.isna(), "structure"] = "UNCLEAR"
    # Momentum: this quarter's move against the previous one.
    now = closes / closes.shift(90) - 1
    before = closes.shift(90) / closes.shift(180) - 1
    momentum = np.where(
        (now > 0) & (before > 0),
        np.where(now > before * 1.2, "ACCELERATING", np.where(now < before * 0.8, "SLOWING", "STEADY")),
        np.where((now <= 0) & (before > 0), "REVERSING",
                 np.where((now < 0) & (before < 0),
                          np.where(now > before, "SLOWING", "ACCELERATING"), "STEADY")),
    )
    frame["momentum"] = momentum
    frame.loc[before.isna(), "momentum"] = "STEADY"
    returns = np.log(closes / closes.shift(1))
    ratio = returns.rolling(30).std() / returns.rolling(365).std()
    frame["volatility"] = np.where(
        ratio >= 1.6, "STRESS",
        np.where(ratio >= 1.2, "EXPANSION", np.where(ratio <= 0.7, "CONTRACTION", "NORMAL")),
    )
    frame.loc[ratio.isna(), "volatility"] = "NORMAL"
    # Lowest low since the running high, for the rebound.
    low_since_ath = np.empty(len(daily))
    running_low = np.inf
    last_ath_position = -1
    low_values = lows.to_numpy()
    ath_positions = frame["ath_position"].to_numpy()
    for i in range(len(daily)):
        if ath_positions[i] != last_ath_position:
            last_ath_position = ath_positions[i]
            running_low = low_values[i]
        running_low = min(running_low, low_values[i])
        low_since_ath[i] = running_low
    frame["rebound_from_low_pct"] = (closes.to_numpy() / low_since_ath - 1) * 100
    stamps = frame.index.to_pydatetime()
    ordered = sorted(halvings)
    days_since = []
    for stamp in stamps:
        day = stamp if stamp.tzinfo else stamp.replace(tzinfo=UTC)
        past = [h for h in ordered if h <= day]
        days_since.append((day - max(past)).days if past else None)
    frame["days_since_halving"] = days_since
    return frame


def _dimensions_from_row(row: Any, stamp: datetime, daily_index: Any) -> Dimensions | None:
    if pd.isna(row.sma200) or row.structure == "UNCLEAR":
        return None
    ath_stamp = pd.Timestamp(daily_index[int(row.ath_position)]).to_pydatetime()
    if ath_stamp.tzinfo is None:
        ath_stamp = ath_stamp.replace(tzinfo=UTC)
    return Dimensions(
        price=float(row.price),
        ath=float(row.ath),
        ath_date=ath_stamp,
        drawdown_pct=float(row.drawdown_pct),
        days_since_ath=int(row.days_since_ath),
        new_high=bool(row.new_high),
        structure=str(row.structure),
        sma200=float(row.sma200),
        sma200_slope_pct=None if pd.isna(row.sma200_slope_pct) else float(row.sma200_slope_pct),
        above_sma200=bool(row.above_sma200),
        momentum=str(row.momentum),
        volatility=str(row.volatility),
        rebound_from_low_pct=(
            None if pd.isna(row.rebound_from_low_pct) else float(row.rebound_from_low_pct)
        ),
        days_since_halving=None if row.days_since_halving is None else int(row.days_since_halving),
    )


@dataclass(slots=True)
class Classification:
    phase: Phase
    confidence: int
    evidence: list[str] = field(default_factory=list)


def classify(dims: Dimensions) -> Classification:
    """The phase of one day, from several dimensions - never the clock alone."""

    evidence: list[str] = []
    rising = bool(dims.sma200_slope_pct is not None and dims.sma200_slope_pct > 0.5)
    falling = bool(dims.sma200_slope_pct is not None and dims.sma200_slope_pct < -0.5)
    above = bool(dims.above_sma200)
    deteriorating = dims.momentum in {"SLOWING", "REVERSING"}

    def note(text: str) -> None:
        evidence.append(text)

    # Price discovery: at the high, with nothing tested above.
    if dims.drawdown_pct > -3 and dims.new_high and dims.structure != "LOWER":
        note("Le prix évolue à moins de 3 % de son record, atteint il y a moins d'un mois.")
        note("Aucune résistance historique au-dessus.")
        return Classification(Phase.PRICE_DISCOVERY, 80, evidence)

    # Expansion: structure, long trend and momentum, together.
    if all([dims.drawdown_pct > -20, dims.structure == "HIGHER", above and rising,
            dims.momentum != "REVERSING"]):
        note("Sommets et creux ascendants.")
        note("Prix au-dessus d'une moyenne 200 jours qui monte.")
        note(f"Record approché à {abs(dims.drawdown_pct):.0f} %.")
        return Classification(Phase.EXPANSION, 80, evidence)

    # Recovery: climbing back from a major low, still under the old high. It is
    # read before any drawdown label: a market up 40 % from its low is
    # recovering, however far the old record still is.
    rebound = dims.rebound_from_low_pct or 0.0
    if dims.drawdown_pct <= -10 and rebound >= 25 and (above or rising):
        note(f"Le prix remonte de {rebound:.0f} % depuis son dernier creux majeur.")
        note("La structure de moyen terme s'améliore.")
        note(f"L'ancien record n'est pas repris ({abs(dims.drawdown_pct):.0f} % en dessous).")
        return Classification(Phase.RECOVERY, 70, evidence)

    # Distribution possible: near the highs, but the advance loses pace. The
    # word "possible" stays: it is not directly observable.
    if dims.drawdown_pct > -25 and deteriorating and dims.structure in {"MIXED", "LOWER"}:
        note(f"Le marché reste proche de ses sommets ({abs(dims.drawdown_pct):.0f} % sous le record).")
        note("La progression s'essouffle et les sommets cessent de monter.")
        note("Preuves insuffisantes pour l'affirmer : distribution possible, non démontrée.")
        return Classification(Phase.DISTRIBUTION_POSSIBLE, 55, evidence)

    # Bear market: depth, a broken structure and a falling long trend, in time.
    if all([dims.drawdown_pct <= -30, dims.structure == "LOWER", falling or not above,
            dims.days_since_ath >= 90]):
        note(f"Repli durable de {abs(dims.drawdown_pct):.0f} % depuis {dims.days_since_ath} jours.")
        note("Sommets et creux descendants.")
        note("Tendance longue orientée à la baisse.")
        return Classification(Phase.BEAR_MARKET, 80, evidence)

    # Deep drawdown: a violent fall the bear reading cannot yet claim, and no
    # rebound worth the name.
    if dims.drawdown_pct <= -45 and rebound < 25:
        note(f"Repli de {abs(dims.drawdown_pct):.0f} % sous le record.")
        note("La dégradation est brutale mais pas encore installée dans la durée.")
        return Classification(Phase.DEEP_DRAWDOWN, 65, evidence)

    # Accumulation: still low, volatility compressing, lows no longer falling.
    if dims.drawdown_pct <= -35 and dims.volatility in {"CONTRACTION", "NORMAL"} and dims.structure != "LOWER":
        note(f"Le prix reste {abs(dims.drawdown_pct):.0f} % sous son record.")
        note("La volatilité se comprime et les creux cessent de baisser.")
        return Classification(Phase.ACCUMULATION, 60, evidence)

    if dims.structure == "UNCLEAR" and dims.sma200 is None:
        return Classification(Phase.UNDETERMINED, 30, ["Historique insuffisant."])
    note("Signaux contradictoires : structure et momentum ne pointent pas dans le même sens.")
    note(f"Écart au record : {abs(dims.drawdown_pct):.0f} %.")
    return Classification(Phase.TRANSITION, 50, evidence)


def health_score(dims: Dimensions) -> float:
    """A single number for "is this improving?", in [-1, 1]."""

    score = 0.0
    score += max(-0.4, min(0.4, dims.drawdown_pct / 100))
    score += {"HIGHER": 0.3, "MIXED": 0.0, "LOWER": -0.3, "UNCLEAR": 0.0}[dims.structure]
    if dims.sma200_slope_pct is not None:
        score += max(-0.2, min(0.2, dims.sma200_slope_pct / 20))
    if dims.above_sma200 is not None:
        score += 0.1 if dims.above_sma200 else -0.1
    score += {"ACCELERATING": 0.15, "STEADY": 0.0, "SLOWING": -0.1, "REVERSING": -0.2}[dims.momentum]
    return max(-1.0, min(1.0, score))


@dataclass(slots=True)
class PhaseRun:
    phase: Phase
    start: datetime
    end: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase.value,
            "label": PHASE_FR[self.phase],
            "tone": PHASE_TONE[self.phase],
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "days": max(1, (self.end - self.start).days),
        }


@dataclass(slots=True)
class CycleRegime:
    phase: Phase
    previous_phase: Phase | None
    candidate_phase: Phase | None
    candidate_days: int
    confidence: int
    phase_since: datetime
    days_in_phase: int
    direction: str            # IMPROVING | STABLE | DEGRADING
    dimensions: Dimensions
    evidence: list[str]
    runs: list[PhaseRun]
    calculated_at: datetime
    data_cutoff: datetime
    health: float
    health_change: float

    @property
    def label(self) -> str:
        return PHASE_FR[self.phase]

    @property
    def emoji(self) -> str:
        return PHASE_EMOJI[self.phase]

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase.value,
            "phase_label": self.label,
            "phase_emoji": self.emoji,
            "tone": PHASE_TONE[self.phase],
            "previous_phase": self.previous_phase.value if self.previous_phase else None,
            "candidate_phase": self.candidate_phase.value if self.candidate_phase else None,
            "candidate_label": PHASE_FR[self.candidate_phase] if self.candidate_phase else None,
            "candidate_days": self.candidate_days,
            "confirmation_days": CONFIRMATION_DAYS,
            "confidence": self.confidence,
            "phase_since": self.phase_since.isoformat(),
            "days_in_phase": self.days_in_phase,
            "direction": self.direction,
            "direction_label": {
                "IMPROVING": "Amélioration", "STABLE": "Stable", "DEGRADING": "Dégradation",
            }[self.direction],
            "direction_emoji": {"IMPROVING": "↗️", "STABLE": "➡️", "DEGRADING": "↘️"}[self.direction],
            "elevated_structural_risk": self.phase in ELEVATED_RISK_PHASES,
            "lean": PHASE_LEAN[self.phase],
            "evidence": self.evidence,
            "dimensions": self.dimensions.to_dict(),
            "health": round(self.health, 3),
            "health_change": round(self.health_change, 3),
            "runs": [r.to_dict() for r in self.runs],
            "calculated_at": self.calculated_at.isoformat(),
            "data_cutoff": self.data_cutoff.isoformat(),
            "engine_version": ENGINE_VERSION,
        }


class BitcoinCycleRegimeEngine:
    """The phase timeline, computed forward, with hysteresis on changes."""

    version = ENGINE_VERSION

    def __init__(self, confirmation_days: int = CONFIRMATION_DAYS) -> None:
        self.confirmation_days = confirmation_days

    def timeline(self, daily: pd.DataFrame, halvings: list[datetime], *,
                 step_days: int = 1, start_after: int = 260) -> list[tuple[datetime, Classification, Dimensions]]:
        """One classification per step, each from the data known that day."""

        out: list[tuple[datetime, Classification, Dimensions]] = []
        if daily is None or len(daily) <= start_after:
            return out
        frame = dimension_frame(daily, halvings)
        index = daily.index
        for position in range(start_after, len(daily), step_days):
            row = frame.iloc[position]
            day = pd.Timestamp(index[position]).to_pydatetime()
            if day.tzinfo is None:
                day = day.replace(tzinfo=UTC)
            dims = _dimensions_from_row(row, day, index)
            if dims is None:
                continue
            out.append((day, classify(dims), dims))
        return out

    def confirmed_runs(
        self, timeline: list[tuple[datetime, Classification, Dimensions]]
    ) -> tuple[list[PhaseRun], Phase | None, int]:
        """Apply hysteresis: a new phase needs ``confirmation_days`` closes.

        Returns the confirmed runs, the pending candidate and how many
        observations it already holds.
        """

        runs: list[PhaseRun] = []
        current: Phase | None = None
        candidate: Phase | None = None
        candidate_count = 0
        for day, classification, _ in timeline:
            raw = classification.phase
            if current is None:
                current = raw
                runs.append(PhaseRun(raw, day, day))
                continue
            if raw == current:
                candidate, candidate_count = None, 0
            elif raw == candidate:
                candidate_count += 1
            else:
                candidate, candidate_count = raw, 1
            if candidate is not None and candidate_count >= self.confirmation_days:
                # The change is dated to the first close of the new phase.
                start = day - timedelta(days=candidate_count - 1)
                runs[-1].end = start
                runs.append(PhaseRun(candidate, start, day))
                current, candidate, candidate_count = candidate, None, 0
            else:
                runs[-1].end = day
        return runs, candidate, candidate_count

    def read(self, daily: pd.DataFrame, halvings: list[datetime], *,
             as_of: datetime | None = None, step_days: int = 1) -> CycleRegime | None:
        timeline = self.timeline(daily, halvings, step_days=step_days)
        if not timeline:
            return None
        runs, candidate, candidate_count = self.confirmed_runs(timeline)
        day, classification, dims = timeline[-1]
        current = runs[-1].phase
        previous = runs[-2].phase if len(runs) > 1 else None
        health = health_score(dims)
        past = next(
            (d for d in reversed(timeline) if d[0] <= day - timedelta(days=DIRECTION_WINDOW_DAYS)),
            None,
        )
        change = health - health_score(past[2]) if past else 0.0
        direction = (
            "IMPROVING" if change > DIRECTION_EPSILON
            else "DEGRADING" if change < -DIRECTION_EPSILON else "STABLE"
        )
        evidence = classification.evidence if classification.phase == current else [
            f"Phase confirmée : {PHASE_FR[current].lower()}.",
            *classification.evidence,
        ]
        return CycleRegime(
            phase=current,
            previous_phase=previous,
            candidate_phase=candidate,
            candidate_days=candidate_count,
            confidence=classification.confidence if classification.phase == current else 55,
            phase_since=runs[-1].start,
            days_in_phase=max(1, (day - runs[-1].start).days),
            direction=direction,
            dimensions=dims,
            evidence=evidence[:3],
            runs=runs,
            calculated_at=as_of or datetime.now(UTC),
            data_cutoff=day,
            health=health,
            health_change=change,
        )


# ---------------------------------------------------------------------------
# What would move the reading on - and what would invalidate it
# ---------------------------------------------------------------------------

#: For each phase, the phase it usually steps into, and what that would take.
NEXT_STEP: dict[Phase, tuple[Phase, list[str]]] = {
    Phase.ACCUMULATION: (Phase.RECOVERY, [
        "📈 Une remontée d'au moins 25 % depuis le dernier creux majeur.",
        "🧱 Des creux qui cessent de baisser sur deux trimestres.",
    ]),
    Phase.RECOVERY: (Phase.EXPANSION, [
        "🧱 Confirmer une structure haussière long terme (sommets et creux ascendants).",
        "🏆 Revenir à moins de 20 % du record historique.",
        "🪙 Conserver une demande au comptant suffisamment saine.",
    ]),
    Phase.EXPANSION: (Phase.PRICE_DISCOVERY, [
        "🏆 Dépasser le record historique et s'y maintenir.",
    ]),
    Phase.PRICE_DISCOVERY: (Phase.EXPANSION, [
        "📉 Un repli sous l'ancien record ramènerait le marché en expansion.",
    ]),
    Phase.TRANSITION: (Phase.EXPANSION, [
        "🧱 Une structure de nouveau ascendante.",
        "📈 Un momentum long terme qui réaccélère.",
    ]),
    Phase.DISTRIBUTION_POSSIBLE: (Phase.EXPANSION, [
        "📈 Un momentum qui réaccélère avec de nouveaux sommets.",
    ]),
    Phase.BEAR_MARKET: (Phase.ACCUMULATION, [
        "🌪️ Une volatilité qui se comprime durablement.",
        "🧱 Des creux qui cessent de baisser.",
    ]),
    Phase.DEEP_DRAWDOWN: (Phase.ACCUMULATION, [
        "🌪️ Une stabilisation de la volatilité.",
        "🧱 Une structure qui cesse de se dégrader.",
    ]),
    Phase.UNDETERMINED: (Phase.TRANSITION, ["📈 Assez d'historique pour lire la structure."]),
}

#: What would send each phase backwards.
INVALIDATION: dict[Phase, tuple[Phase, str]] = {
    Phase.ACCUMULATION: (Phase.BEAR_MARKET, "De nouveaux creux plus bas avec une tendance longue qui repart à la baisse."),
    Phase.RECOVERY: (Phase.DEEP_DRAWDOWN, "Une cassure structurelle importante et un retour sous la moyenne 200 jours."),
    Phase.EXPANSION: (Phase.TRANSITION, "Une perte de momentum avec des sommets qui cessent de monter."),
    Phase.PRICE_DISCOVERY: (Phase.TRANSITION, "Un décrochage net sous le record accompagné d'un momentum qui se retourne."),
    Phase.TRANSITION: (Phase.BEAR_MARKET, "Un repli de plus de 30 % avec une structure descendante installée."),
    Phase.DISTRIBUTION_POSSIBLE: (Phase.BEAR_MARKET, "Un repli durable de plus de 30 % avec des creux descendants."),
    Phase.BEAR_MARKET: (Phase.DEEP_DRAWDOWN, "Une accélération de la baisse au-delà de 45 % sous le record."),
    Phase.DEEP_DRAWDOWN: (Phase.BEAR_MARKET, "Une dégradation qui s'installe au-delà de trois mois."),
    Phase.UNDETERMINED: (Phase.UNDETERMINED, "Aucune bascule identifiée."),
}


def next_step(regime: CycleRegime) -> dict[str, Any]:
    target, conditions = NEXT_STEP[regime.phase]
    back, reason = INVALIDATION[regime.phase]
    return {
        "from_phase": regime.phase.value,
        "from_label": regime.label,
        "to_phase": target.value,
        "to_label": PHASE_FR[target],
        "to_emoji": PHASE_EMOJI[target],
        "conditions": conditions,
        "invalidation_phase": back.value,
        "invalidation_label": PHASE_FR[back],
        "invalidation_emoji": PHASE_EMOJI[back],
        "invalidation": reason,
        "candidate_phase": regime.candidate_phase.value if regime.candidate_phase else None,
        "candidate_label": PHASE_FR[regime.candidate_phase] if regime.candidate_phase else None,
        "candidate_progress": f"{regime.candidate_days}/{CONFIRMATION_DAYS}",
    }

"""Multi-timeframe engine.

An asset is never judged on a single timeframe. Each timeframe is analysed
independently, then combined with weights that grow toward the higher
timeframes - a 15-minute trend must not carry the same authority as a weekly
one.

Disagreement between timeframes is reported, not averaged away: "15m bullish,
daily bearish" is a genuinely different situation from "everything neutral",
and flattening the two into one number destroys the distinction.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..config_loader import assets_config
from ..core.enums import Asset, Direction, Freshness, Timeframe, TrendDirection
from ..core.freshness import worst_freshness
from .technical.engine import TechnicalAnalysisEngine, TechnicalSnapshot


class TimeframeVerdict(BaseModel):
    timeframe: Timeframe
    direction: Direction
    trend: TrendDirection
    weight: float
    rsi: float | None = None
    available: bool = True
    note: str = ""


class MTFResult(BaseModel):
    asset: Asset
    verdicts: list[TimeframeVerdict] = Field(default_factory=list)
    alignment_score: float = 0.0          # -100 .. +100
    coherence: float = 0.0                # 0..100, how much the timeframes agree
    dominant_direction: Direction = Direction.INCONCLUSIVE
    conflicts: list[str] = Field(default_factory=list)
    freshness: Freshness = Freshness.UNAVAILABLE
    timeframes_available: int = 0

    @property
    def is_aligned(self) -> bool:
        return self.coherence >= 70.0


class MultiTimeframeEngine:
    name = "mtf_engine"

    def __init__(self) -> None:
        self.tech = TechnicalAnalysisEngine()
        self.weights: dict[str, float] = {
            tf["code"]: float(tf.get("mtf_weight", 0.2))
            for tf in assets_config().get("timeframes", [])
        }

    def weight_for(self, tf: Timeframe) -> float:
        return self.weights.get(tf.value, 0.2)

    def analyze(
        self, asset: Asset, snapshots: dict[Timeframe, TechnicalSnapshot]
    ) -> MTFResult:
        verdicts: list[TimeframeVerdict] = []
        weighted_sum = 0.0
        total_weight = 0.0
        freshness_list: list[Freshness] = []

        for tf in (Timeframe.M15, Timeframe.H1, Timeframe.H4, Timeframe.D1, Timeframe.W1):
            snap = snapshots.get(tf)
            weight = self.weight_for(tf)
            if snap is None or not snap.has_data:
                verdicts.append(TimeframeVerdict(
                    timeframe=tf, direction=Direction.INCONCLUSIVE,
                    trend=TrendDirection.UNDETERMINED, weight=weight,
                    available=False, note="UNAVAILABLE - no data for this timeframe",
                ))
                continue

            direction = self.tech.technical_direction(snap)
            verdicts.append(TimeframeVerdict(
                timeframe=tf, direction=direction, trend=snap.trend.direction,
                weight=weight, rsi=snap.rsi, available=True,
                note=snap.trend.reason,
            ))
            freshness_list.append(snap.freshness)

            value = {
                Direction.BULLISH: 1.0, Direction.BEARISH: -1.0,
                Direction.NEUTRAL: 0.0, Direction.INCONCLUSIVE: 0.0,
            }[direction]
            # Trend strength modulates how much a directional call counts.
            value *= 0.5 + min(snap.trend.strength, 100.0) / 200.0
            weighted_sum += value * weight
            total_weight += weight

        available = [v for v in verdicts if v.available]
        if not available or total_weight == 0:
            return MTFResult(
                asset=asset, verdicts=verdicts, freshness=Freshness.UNAVAILABLE,
                dominant_direction=Direction.INCONCLUSIVE,
                conflicts=["UNAVAILABLE - no timeframe could be analysed"],
            )

        alignment = max(-100.0, min(100.0, weighted_sum / total_weight * 100.0))

        bulls = sum(1 for v in available if v.direction is Direction.BULLISH)
        bears = sum(1 for v in available if v.direction is Direction.BEARISH)
        n = len(available)
        # Coherence: how one-sided the timeframes are, ignoring neutrals.
        coherence = (abs(bulls - bears) / n * 100.0) if n else 0.0

        conflicts: list[str] = []
        if bulls and bears:
            bull_tfs = [v.timeframe.value for v in available if v.direction is Direction.BULLISH]
            bear_tfs = [v.timeframe.value for v in available if v.direction is Direction.BEARISH]
            conflicts.append(
                f"Timeframes disagree: bullish on {', '.join(bull_tfs)} "
                f"but bearish on {', '.join(bear_tfs)}"
            )
            # A short-term move against the higher timeframes is worth naming.
            high_tf = {Timeframe.D1.value, Timeframe.W1.value}
            if set(bear_tfs) & high_tf and set(bull_tfs) <= {Timeframe.M15.value, Timeframe.H1.value}:
                conflicts.append(
                    "Short-term strength against a bearish higher timeframe - "
                    "typically a counter-trend bounce rather than a reversal"
                )
            elif set(bull_tfs) & high_tf and set(bear_tfs) <= {Timeframe.M15.value, Timeframe.H1.value}:
                conflicts.append(
                    "Short-term weakness inside a bullish higher timeframe - "
                    "typically a pullback rather than a top"
                )

        if alignment > 20:
            dominant = Direction.BULLISH
        elif alignment < -20:
            dominant = Direction.BEARISH
        elif n >= 2:
            dominant = Direction.NEUTRAL
        else:
            dominant = Direction.INCONCLUSIVE

        return MTFResult(
            asset=asset,
            verdicts=verdicts,
            alignment_score=round(alignment, 1),
            coherence=round(coherence, 1),
            dominant_direction=dominant,
            conflicts=conflicts,
            freshness=worst_freshness(freshness_list),
            timeframes_available=n,
        )

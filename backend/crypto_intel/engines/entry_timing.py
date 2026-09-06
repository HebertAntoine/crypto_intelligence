"""EntryTimingEngine - "is this a good moment?", asked separately from
"is the trend favourable?".

This is the distinction the LOT 2 brief is built around. A market can be
STRONGLY_BULLISH while the immediate entry is poor: stretched from its moving
averages, hourly RSI overbought, funding crowded, resistance overhead, a CPI
print in six hours. Blending those into one number destroys the information.

The engine is fully deterministic and runs before any LLM. It produces a
timing score, the factors that moved it, the risks, a zone to watch derived
from *computed* levels, and an invalidation level.

It never invents a price target. Every level it quotes comes from swing
clustering or from an indicator value.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from ..config_loader import threshold
from ..core.enums import Asset, Freshness, TrendDirection


class EntryTiming(StrEnum):
    VERY_UNFAVORABLE = "VERY_UNFAVORABLE"
    UNFAVORABLE = "UNFAVORABLE"
    WAIT = "WAIT"
    FAVORABLE = "FAVORABLE"
    VERY_FAVORABLE = "VERY_FAVORABLE"
    UNDETERMINED = "UNDETERMINED"


class TimingFactor(BaseModel):
    name: str
    value: str
    contribution: float = Field(..., ge=-100.0, le=100.0)
    weight: float = Field(default=1.0, ge=0.0)
    detail: str = ""
    favourable: bool = True


class TimingZone(BaseModel):
    """A price area worth watching, always derived from computed levels."""

    label: str
    low: float | None = None
    high: float | None = None
    basis: str = ""


class EntryTimingAssessment(BaseModel):
    asset: Asset
    timing: EntryTiming = EntryTiming.UNDETERMINED
    timing_score: float = Field(default=0.0, ge=-100.0, le=100.0)
    confidence: float = Field(default=0.0, ge=0.0, le=100.0)
    factors: list[TimingFactor] = Field(default_factory=list)
    positives: list[str] = Field(default_factory=list)
    negatives: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    zones_to_watch: list[TimingZone] = Field(default_factory=list)
    invalidation_level: float | None = None
    invalidation_reason: str = ""
    freshness: Freshness = Freshness.UNAVAILABLE
    evidence_ids: list[str] = Field(default_factory=list)
    summary: str = ""
    missing: list[str] = Field(default_factory=list)
    explanation: str = ""


class EntryTimingEngine:
    name = "entry_timing_engine"

    def __init__(self) -> None:
        self.t_rsi = threshold("technical", "rsi", default={}) or {}
        self.t_vol = threshold("technical", "volume", default={}) or {}
        self.t_atr = threshold("technical", "atr_pct", default={}) or {}
        self.t_funding = threshold("derivatives", "funding", default={}) or {}
        self.t_oi = threshold("derivatives", "open_interest", default={}) or {}
        self.t_event = threshold("macro", "event_proximity", default={}) or {}

    def assess(self, asset: Asset, context: dict[str, Any]) -> EntryTimingAssessment:
        snapshots = context.get("snapshots") or {}
        daily = self._snap(snapshots, "1d")
        h4 = self._snap(snapshots, "4h")
        h1 = self._snap(snapshots, "1h")

        if daily is None or not daily.has_data:
            return EntryTimingAssessment(
                asset=asset, timing=EntryTiming.UNDETERMINED,
                summary="UNAVAILABLE - no daily candles, entry timing cannot be assessed",
                missing=["daily OHLCV"],
            )

        factors: list[TimingFactor] = []
        risks: list[str] = []
        missing: list[str] = []
        evidence_ids: list[str] = []
        price = daily.price or 0.0

        # --- 1. Short-term momentum: the classic "chasing" check -------------
        short = h1 if (h1 and h1.has_data) else h4
        short_label = "1h" if (h1 and h1.has_data) else "4h"
        if short and short.has_data and short.rsi is not None:
            factors.append(self._rsi_factor(short.rsi, short_label, weight=2.0))
        else:
            missing.append("intraday RSI (1h/4h)")

        if daily.rsi is not None:
            factors.append(self._rsi_factor(daily.rsi, "daily", weight=1.2))

        # --- 2. Distance from moving averages --------------------------------
        if daily.ema20 and price:
            stretch = (price - daily.ema20) / daily.ema20 * 100.0
            # Buying far above the 20-EMA is statistically a worse entry than
            # buying near it, regardless of how good the trend is.
            contribution = max(-100.0, min(100.0, -stretch * 6.0))
            factors.append(TimingFactor(
                name="distance to EMA20", value=f"{stretch:+.2f}%",
                contribution=contribution, weight=1.8,
                detail=f"Price {price:,.2f} vs EMA20 {daily.ema20:,.2f}",
                favourable=contribution >= 0,
            ))
            if stretch > 12:
                risks.append(
                    f"Price is {stretch:.1f}% above its 20-day EMA - entries this "
                    "extended are exposed to mean reversion"
                )

        # --- 3. Position inside the Bollinger band ---------------------------
        if daily.bb_position is not None:
            # 0 = lower band, 100 = upper band. Near the top is a poor entry.
            contribution = max(-100.0, min(100.0, (50.0 - daily.bb_position) * 1.6))
            factors.append(TimingFactor(
                name="Bollinger position", value=f"{daily.bb_position:.0f}% of band",
                contribution=contribution, weight=1.2,
                detail="0% = lower band, 100% = upper band",
                favourable=contribution >= 0,
            ))

        # --- 4. Proximity to resistance / support ----------------------------
        zones: list[TimingZone] = []
        nearest_resistance = daily.levels_resistance[0] if daily.levels_resistance else None
        nearest_support = daily.levels_support[0] if daily.levels_support else None

        if nearest_resistance and price:
            distance = (nearest_resistance.price - price) / price * 100.0
            if distance < 3.0:
                factors.append(TimingFactor(
                    name="resistance proximity", value=f"{distance:.2f}% away",
                    contribution=-55.0, weight=1.6,
                    detail=f"Resistance {nearest_resistance.price:,.2f} "
                           f"({nearest_resistance.touches} touches)",
                    favourable=False,
                ))
                risks.append(
                    f"Resistance at {nearest_resistance.price:,.2f} is only "
                    f"{distance:.1f}% away ({nearest_resistance.touches} touches)"
                )
            elif distance > 8.0:
                factors.append(TimingFactor(
                    name="resistance proximity", value=f"{distance:.1f}% away",
                    contribution=25.0, weight=1.0,
                    detail="Room before the next resistance", favourable=True,
                ))
            zones.append(TimingZone(
                label="Nearest resistance",
                low=nearest_resistance.price * 0.995, high=nearest_resistance.price * 1.005,
                basis=f"swing cluster, {nearest_resistance.touches} touches",
            ))

        if nearest_support and price:
            distance = (price - nearest_support.price) / price * 100.0
            if distance < 2.5:
                # Close to support is a better entry, but only if it holds.
                factors.append(TimingFactor(
                    name="support proximity", value=f"{distance:.2f}% away",
                    contribution=40.0, weight=1.4,
                    detail=f"Support {nearest_support.price:,.2f} "
                           f"({nearest_support.touches} touches) - better risk/reward, "
                           "conditional on it holding",
                    favourable=True,
                ))
            zones.append(TimingZone(
                label="Nearest support",
                low=nearest_support.price * 0.995, high=nearest_support.price * 1.005,
                basis=f"swing cluster, {nearest_support.touches} touches",
            ))

        # A pullback zone between price and the 20-EMA, when price is extended.
        if daily.ema20 and price and price > daily.ema20 * 1.03:
            zones.append(TimingZone(
                label="Pullback zone (EMA20 area)",
                low=min(daily.ema20, price) * 0.99, high=daily.ema20 * 1.01,
                basis="20-day EMA, computed from candles",
            ))

        # --- 5. Volume confirmation -------------------------------------------
        # Skipped while the current bar is still forming: a partial volume
        # reading would show as "LOW" every morning and wrongly penalise timing.
        if daily.relative_volume is not None and not daily.last_bar_partial:
            if daily.volume_state == "LOW":
                factors.append(TimingFactor(
                    name="volume", value=f"{daily.relative_volume:.2f}x average",
                    contribution=-20.0, weight=1.0,
                    detail="Thin participation - moves made on low volume are less reliable",
                    favourable=False,
                ))
            elif daily.volume_state in ("HIGH", "SPIKE"):
                factors.append(TimingFactor(
                    name="volume", value=f"{daily.relative_volume:.2f}x average",
                    contribution=15.0, weight=0.8,
                    detail="Participation confirms the current move", favourable=True,
                ))
        elif daily.relative_volume is not None and daily.last_bar_partial:
            missing.append(
                f"volume confirmation (current daily bar only "
                f"{daily.last_bar_completion_pct:.0f}% elapsed)"
            )

        # --- 6. Volatility ----------------------------------------------------
        if daily.atr_pct is not None and daily.atr_pct >= float(self.t_atr.get("high", 5.0)):
            factors.append(TimingFactor(
                name="volatility", value=f"ATR {daily.atr_pct:.2f}%",
                contribution=-25.0, weight=1.0,
                detail="High volatility widens any stop and worsens entry precision",
                favourable=False,
            ))
            risks.append(f"Elevated volatility (ATR {daily.atr_pct:.2f}% of price)")

        # --- 7. Divergences ---------------------------------------------------
        for source in (short, daily):
            if not source or not source.has_data:
                continue
            for div in source.divergences[:1]:
                bullish = "bull" in div.kind
                factors.append(TimingFactor(
                    name=f"{div.indicator} divergence ({source.timeframe.value})",
                    value=div.kind.replace("_", " "),
                    contribution=(35.0 if bullish else -35.0) * (div.strength / 100.0),
                    weight=1.3,
                    detail=f"strength {div.strength:.0f}/100",
                    favourable=bullish,
                ))
                if not bullish:
                    risks.append(
                        f"Bearish {div.indicator} divergence on {source.timeframe.value} "
                        f"(strength {div.strength:.0f})"
                    )

        # --- 8. Derivatives: crowding is a timing signal ---------------------
        deriv = context.get("derivatives")
        if deriv is not None and getattr(deriv, "available", False):
            state = deriv.funding_state
            contribution = {
                "EXTREME_POSITIVE": -60.0, "ELEVATED_POSITIVE": -25.0,
                "MILD_POSITIVE": -5.0, "NEUTRAL": 5.0, "MILD_NEGATIVE": 5.0,
                "ELEVATED_NEGATIVE": 20.0, "EXTREME_NEGATIVE": 40.0,
            }.get(state, 0.0)
            if state != "UNAVAILABLE":
                factors.append(TimingFactor(
                    name="funding", value=state,
                    contribution=contribution, weight=1.7,
                    detail=(
                        f"{deriv.funding_rate:.6f} per 8h"
                        if deriv.funding_rate is not None else ""
                    ),
                    favourable=contribution >= 0,
                ))
            if state == "EXTREME_POSITIVE":
                risks.append(
                    "Funding is extreme: longs are crowded and paying to hold, "
                    "which raises long-squeeze risk on any dip"
                )
            oi_change = deriv.oi_change_24h_pct
            if oi_change is not None and oi_change >= float(self.t_oi.get("spike_pct_24h", 12)):
                factors.append(TimingFactor(
                    name="open interest", value=f"{oi_change:+.1f}% 24h",
                    contribution=-20.0, weight=1.0,
                    detail="Rapid leverage build-up precedes violent unwinds",
                    favourable=False,
                ))
            if deriv.liquidations_available and deriv.liquidation_imbalance:
                factors.append(TimingFactor(
                    name="liquidations", value=deriv.liquidation_imbalance,
                    contribution=15.0 if deriv.liquidation_imbalance == "LONGS_LIQUIDATED" else -5.0,
                    weight=0.8,
                    detail="Forced selling can create better entries",
                    favourable=deriv.liquidation_imbalance == "LONGS_LIQUIDATED",
                ))
            evidence_ids.extend(getattr(deriv, "evidence_ids", [])[:5])
        else:
            missing.append("derivatives (funding / open interest)")

        # --- 9. ETF flows -----------------------------------------------------
        etf = context.get("etf")
        if etf is not None and getattr(etf, "available", False):
            # Flows are a demand signal; for timing they matter mostly through
            # their direction of change, not their absolute level.
            contribution = max(-45.0, min(45.0, etf.strength * 0.45))
            factors.append(TimingFactor(
                name="ETF flows", value=f"{etf.strength:+.0f}",
                contribution=contribution, weight=1.2,
                detail=(
                    f"5-day average {etf.ma_5d:+.1f}M USD"
                    if etf.ma_5d is not None else ""
                ),
                favourable=contribution >= 0,
            ))
            if etf.flow_price_divergence == "DISTRIBUTION_INTO_STRENGTH":
                risks.append(
                    "Price is rising while ETF flows are negative - the move lacks "
                    "institutional support"
                )
            evidence_ids.extend(getattr(etf, "evidence_ids", [])[:5])
        elif asset in (Asset.BTC, Asset.ETH):
            missing.append("ETF flows")

        # --- 10. Imminent macro events ---------------------------------------
        # Handled as a CAP applied after the weighted average, not as a term
        # inside it. Inside the average, a -45 factor can pull an already-worse
        # score upward, which would mean an imminent CPI *improved* the timing -
        # the opposite of what it should do.
        imminent_penalty: float | None = None
        macro = context.get("macro")
        if macro is not None and getattr(macro, "imminent_event", None):
            event = macro.imminent_event
            imminent_penalty = -45.0
            factors.append(TimingFactor(
                name="imminent macro event", value=event.name,
                contribution=-45.0,
                # weight 0: reported as evidence, applied as a cap below.
                weight=0.0,
                detail=f"in {event.hours_until:.1f}h ({event.importance}) - applied as a cap",
                favourable=False,
            ))
            risks.append(
                f"{event.name} lands in {event.hours_until:.1f}h - entering just before "
                "a scheduled release is a coin flip, not an edge"
            )
        elif macro is not None and getattr(macro, "upcoming_events", None):
            nxt = macro.upcoming_events[0]
            near = float(self.t_event.get("near_hours", 48))
            if nxt.hours_until is not None and nxt.hours_until <= near:
                factors.append(TimingFactor(
                    name="upcoming macro event", value=nxt.name,
                    contribution=-15.0, weight=1.0,
                    detail=f"in {nxt.hours_until:.0f}h ({nxt.importance})",
                    favourable=False,
                ))

        # --- 11. Structure alignment -----------------------------------------
        if daily.trend.direction is TrendDirection.RANGE and daily.bb_position is not None:
            # Inside a range, position within the range IS the timing.
            if daily.bb_position < 25:
                factors.append(TimingFactor(
                    name="range position", value="lower part of the range",
                    contribution=30.0, weight=1.2,
                    detail="Buying the lower half of a range is a better entry than the top",
                    favourable=True,
                ))
            elif daily.bb_position > 75:
                factors.append(TimingFactor(
                    name="range position", value="upper part of the range",
                    contribution=-30.0, weight=1.2,
                    detail="Buying the top of a range offers poor risk/reward",
                    favourable=False,
                ))

        # --- aggregate --------------------------------------------------------
        weighted = [f for f in factors if f.weight > 0]
        total_weight = sum(f.weight for f in weighted)
        score = (
            sum(f.contribution * f.weight for f in weighted) / total_weight
            if total_weight else 0.0
        )

        # An imminent scheduled release can only ever make the moment worse.
        if imminent_penalty is not None:
            score = min(score, imminent_penalty) - 5.0

        score = max(-100.0, min(100.0, score))

        timing = self._label(score)
        coverage = min(1.0, len(weighted) / 9.0)
        confidence = min(100.0, 30.0 + coverage * 60.0 - len(missing) * 4.0)
        if daily.freshness is Freshness.STALE:
            confidence *= 0.6

        positives = [
            f"{f.name}: {f.value}" + (f" — {f.detail}" if f.detail else "")
            for f in sorted(weighted, key=lambda x: -x.contribution * x.weight)
            if f.contribution > 5
        ][:5]
        negatives = [
            f"{f.name}: {f.value}" + (f" — {f.detail}" if f.detail else "")
            for f in sorted(weighted, key=lambda x: x.contribution * x.weight)
            if f.contribution < -5
        ][:5]

        invalidation, invalidation_reason = self._invalidation(daily, nearest_support)

        return EntryTimingAssessment(
            asset=asset, timing=timing, timing_score=round(score, 1),
            confidence=round(max(0.0, confidence), 1),
            factors=factors, positives=positives, negatives=negatives, risks=risks,
            zones_to_watch=zones, invalidation_level=invalidation,
            invalidation_reason=invalidation_reason,
            freshness=daily.freshness, evidence_ids=evidence_ids[:20],
            summary=self._summary(asset, timing, score, positives, negatives),
            missing=missing,
            explanation=self._explanation(weighted, score, timing),
        )

    # --- helpers -----------------------------------------------------------

    @staticmethod
    def _snap(snapshots: dict, code: str):
        for tf, snap in snapshots.items():
            if getattr(tf, "value", str(tf)) == code:
                return snap
        return None

    def _rsi_factor(self, rsi: float, label: str, weight: float) -> TimingFactor:
        overbought = float(self.t_rsi.get("overbought", 70))
        oversold = float(self.t_rsi.get("oversold", 30))
        extreme_high = float(self.t_rsi.get("extreme_high", 80))
        extreme_low = float(self.t_rsi.get("extreme_low", 20))

        if rsi >= extreme_high:
            contribution, detail = -70.0, "Extremely overbought - a poor moment to add"
        elif rsi >= overbought:
            contribution, detail = -40.0, "Overbought - entries here chase the move"
        elif rsi <= extreme_low:
            contribution, detail = 55.0, "Extremely oversold - potential exhaustion"
        elif rsi <= oversold:
            contribution, detail = 35.0, "Oversold - better risk/reward than chasing"
        else:
            # Mid-range: mildly better the lower it is.
            contribution = (55.0 - rsi) * 1.2
            detail = "Neutral momentum zone"
        return TimingFactor(
            name=f"RSI {label}", value=f"{rsi:.1f}",
            contribution=max(-100.0, min(100.0, contribution)),
            weight=weight, detail=detail, favourable=contribution >= 0,
        )

    @staticmethod
    def _invalidation(daily, nearest_support) -> tuple[float | None, str]:
        """The level that would falsify a constructive read. Always computed."""
        if nearest_support is not None:
            return (
                round(nearest_support.price, 8),
                f"Daily close below the nearest support ({nearest_support.touches} "
                "touches from swing clustering) invalidates the constructive case",
            )
        if daily.ema50 is not None:
            return (
                round(daily.ema50, 8),
                "Daily close below the 50-day EMA invalidates the constructive case",
            )
        return None, "No computed level available for invalidation"

    @staticmethod
    def _label(score: float) -> EntryTiming:
        if score >= 45:
            return EntryTiming.VERY_FAVORABLE
        if score >= 15:
            return EntryTiming.FAVORABLE
        if score <= -45:
            return EntryTiming.VERY_UNFAVORABLE
        if score <= -15:
            return EntryTiming.UNFAVORABLE
        return EntryTiming.WAIT

    @staticmethod
    def _summary(asset, timing, score, positives, negatives) -> str:
        base = f"{asset.value} entry timing {timing.value} (score {score:+.0f})."
        if negatives:
            base += f" Main obstacle: {negatives[0]}."
        elif positives:
            base += f" Main support: {positives[0]}."
        return base

    @staticmethod
    def _explanation(factors, score, timing) -> str:
        """Human-readable account of the arithmetic, for the WHY? panel."""
        lines = [
            "Entry timing is a weighted average of independent factors, each "
            "scored from -100 (poor moment) to +100 (good moment):",
            "",
        ]
        for f in sorted(factors, key=lambda x: -abs(x.contribution) * x.weight):
            sign = "+" if f.contribution >= 0 else ""
            lines.append(
                f"  {f.name} = {f.value} -> {sign}{f.contribution:.0f} "
                f"(weight {f.weight:.1f}){' - ' + f.detail if f.detail else ''}"
            )
        total_weight = sum(f.weight for f in factors)
        lines.append("")
        lines.append(
            f"  weighted sum / total weight ({total_weight:.1f}) = {score:+.1f} -> {timing.value}"
        )
        lines.append(
            "  Note: an imminent scheduled macro release is applied as a CAP on the "
            "score (weight 0 above), never averaged in - it can only worsen the moment."
        )
        lines.append("")
        lines.append(
            "Thresholds: >= +45 VERY_FAVORABLE, >= +15 FAVORABLE, "
            "-15..+15 WAIT, <= -15 UNFAVORABLE, <= -45 VERY_UNFAVORABLE."
        )
        return "\n".join(lines)

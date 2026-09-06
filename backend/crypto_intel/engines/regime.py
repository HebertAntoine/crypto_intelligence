"""MarketRegimeEngine - what kind of market are we in?

Deliberately multi-factor. "Price above EMA200" is not a regime: it says
nothing about volatility, leverage, participation or macro backdrop, and it
labels a grinding range as a bull market.

Two independent axes are produced:

  * `regime`     - the directional state (STRONGLY_BEARISH … STRONGLY_BULLISH)
  * `conditions` - the *character* of the market (volatility expansion,
                   deleveraging, overheated, capitulation, risk-on/off …)

A market can be BULLISH and OVERHEATED at the same time; collapsing those into
one label is exactly what hides the "good trend, bad entry" situation.

Every regime carries its evidence: which factors voted, and how strongly.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from ..config_loader import threshold
from ..core.enums import Asset, Freshness, MarketStructure, TrendDirection


class MarketRegime(StrEnum):
    STRONGLY_BEARISH = "STRONGLY_BEARISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"
    BULLISH = "BULLISH"
    STRONGLY_BULLISH = "STRONGLY_BULLISH"
    UNDETERMINED = "UNDETERMINED"


class MarketCondition(StrEnum):
    """Character of the market, independent of direction."""

    VOLATILITY_EXPANSION = "VOLATILITY_EXPANSION"
    VOLATILITY_COMPRESSION = "VOLATILITY_COMPRESSION"
    RANGE = "RANGE"
    RISK_ON = "RISK_ON"
    RISK_OFF = "RISK_OFF"
    DELEVERAGING = "DELEVERAGING"
    LEVERAGE_BUILDUP = "LEVERAGE_BUILDUP"
    OVERHEATED = "OVERHEATED"
    CAPITULATION = "CAPITULATION"
    LIQUIDITY_EXPANSION = "LIQUIDITY_EXPANSION"
    LIQUIDITY_CONTRACTION = "LIQUIDITY_CONTRACTION"


class RegimeFactor(BaseModel):
    """One piece of evidence for the regime call."""

    name: str
    value: str
    contribution: float = Field(..., ge=-100.0, le=100.0)
    weight: float = Field(default=1.0, ge=0.0)
    detail: str = ""


class RegimeAssessment(BaseModel):
    asset: Asset
    regime: MarketRegime = MarketRegime.UNDETERMINED
    regime_score: float = Field(default=0.0, ge=-100.0, le=100.0)
    confidence: float = Field(default=0.0, ge=0.0, le=100.0)
    conditions: list[MarketCondition] = Field(default_factory=list)
    factors: list[RegimeFactor] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    freshness: Freshness = Freshness.UNAVAILABLE
    summary: str = ""
    missing: list[str] = Field(default_factory=list)

    @property
    def is_bullish(self) -> bool:
        return self.regime in (MarketRegime.BULLISH, MarketRegime.STRONGLY_BULLISH)

    @property
    def is_bearish(self) -> bool:
        return self.regime in (MarketRegime.BEARISH, MarketRegime.STRONGLY_BEARISH)

    def label(self) -> str:
        if not self.conditions:
            return self.regime.value
        return f"{self.regime.value} / {' + '.join(c.value for c in self.conditions[:2])}"


class MarketRegimeEngine:
    name = "market_regime_engine"

    def __init__(self) -> None:
        self.t_atr = threshold("technical", "atr_pct", default={}) or {}
        self.t_funding = threshold("derivatives", "funding", default={}) or {}
        self.t_rsi = threshold("technical", "rsi", default={}) or {}

    def assess(self, asset: Asset, context: dict[str, Any]) -> RegimeAssessment:
        """Build the regime from every domain that has data.

        Domains without data simply do not vote - they are recorded in
        `missing` rather than counted as neutral, which would drag every regime
        toward NEUTRAL as sources drop out.
        """
        snapshots = context.get("snapshots") or {}
        daily = self._snap(snapshots, "1d")
        weekly = self._snap(snapshots, "1w")

        factors: list[RegimeFactor] = []
        conditions: list[MarketCondition] = []
        missing: list[str] = []
        evidence_ids: list[str] = []

        if daily is None or not daily.has_data:
            return RegimeAssessment(
                asset=asset, regime=MarketRegime.UNDETERMINED,
                summary="UNAVAILABLE - no daily candles, regime cannot be determined",
                missing=["daily OHLCV"],
            )

        # --- 1. Higher-timeframe trend (the backbone, but not the whole story)
        factors.append(self._trend_factor(daily, "daily trend", weight=2.0))
        if weekly and weekly.has_data:
            factors.append(self._trend_factor(weekly, "weekly trend", weight=2.5))
        else:
            missing.append("weekly OHLCV")

        # --- 2. Market structure
        factors.append(self._structure_factor(daily))

        # --- 3. Position relative to the long moving average
        if daily.ema200 is not None and daily.price:
            dist = (daily.price - daily.ema200) / daily.ema200 * 100.0
            contribution = max(-100.0, min(100.0, dist * 3.0))
            factors.append(RegimeFactor(
                name="price vs EMA200", value=f"{dist:+.1f}%",
                contribution=contribution, weight=1.5,
                detail=f"Price {daily.price:,.2f} vs EMA200 {daily.ema200:,.2f}",
            ))
            # Being far above the long MA is a stretch condition, not bullishness.
            if dist > 35:
                conditions.append(MarketCondition.OVERHEATED)
        else:
            missing.append("EMA200 (needs 200 daily bars)")

        # --- 4. Momentum
        if daily.rsi is not None:
            rsi_contribution = (daily.rsi - 50.0) * 1.6
            factors.append(RegimeFactor(
                name="daily RSI", value=f"{daily.rsi:.1f}",
                contribution=max(-100.0, min(100.0, rsi_contribution)), weight=1.0,
                detail=daily.rsi_state,
            ))
            if daily.rsi >= float(self.t_rsi.get("extreme_high", 80)):
                conditions.append(MarketCondition.OVERHEATED)
            elif daily.rsi <= float(self.t_rsi.get("extreme_low", 20)):
                conditions.append(MarketCondition.CAPITULATION)

        # --- 5. Volatility character
        if daily.atr_pct is not None:
            high = float(self.t_atr.get("high", 5.0))
            low = float(self.t_atr.get("low", 1.0))
            if daily.atr_pct >= high:
                conditions.append(MarketCondition.VOLATILITY_EXPANSION)
            elif daily.atr_pct <= low:
                conditions.append(MarketCondition.VOLATILITY_COMPRESSION)
            factors.append(RegimeFactor(
                name="volatility", value=f"ATR {daily.atr_pct:.2f}%",
                contribution=0.0, weight=0.0,   # character, not direction
                detail=daily.volatility_state,
            ))

        if daily.trend.direction is TrendDirection.RANGE:
            conditions.append(MarketCondition.RANGE)

        # --- 6. Derivatives: leverage state
        deriv = context.get("derivatives")
        if deriv is not None and getattr(deriv, "available", False):
            funding_state = deriv.funding_state
            if funding_state == "EXTREME_POSITIVE":
                conditions.append(MarketCondition.OVERHEATED)
                conditions.append(MarketCondition.LEVERAGE_BUILDUP)
                factors.append(RegimeFactor(
                    name="funding", value=funding_state, contribution=-25.0, weight=1.0,
                    detail="Crowded long positioning is a late-cycle characteristic",
                ))
            elif funding_state == "EXTREME_NEGATIVE":
                conditions.append(MarketCondition.CAPITULATION)
                factors.append(RegimeFactor(
                    name="funding", value=funding_state, contribution=20.0, weight=1.0,
                    detail="Crowded short positioning often marks exhaustion",
                ))
            oi_change = getattr(deriv, "oi_change_24h_pct", None)
            if oi_change is not None:
                if oi_change <= -8:
                    conditions.append(MarketCondition.DELEVERAGING)
                elif oi_change >= 12:
                    conditions.append(MarketCondition.LEVERAGE_BUILDUP)
            evidence_ids.extend(getattr(deriv, "evidence_ids", [])[:5])
        else:
            missing.append("derivatives")

        # --- 7. ETF demand (structural for BTC/ETH)
        etf = context.get("etf")
        if etf is not None and getattr(etf, "available", False):
            factors.append(RegimeFactor(
                name="ETF flows", value=f"{etf.strength:+.0f}",
                contribution=max(-100.0, min(100.0, etf.strength)), weight=1.8,
                detail=(
                    f"5-day average {etf.ma_5d:+.1f}M USD" if etf.ma_5d is not None
                    else "flows available"
                ),
            ))
            evidence_ids.extend(getattr(etf, "evidence_ids", [])[:5])
        elif asset in (Asset.BTC, Asset.ETH):
            missing.append("ETF flows")

        # --- 8. Liquidity backdrop
        liq = context.get("liquidity")
        if liq is not None and getattr(liq, "available", False):
            if liq.regime in ("EXPANSION", "STRONG_EXPANSION"):
                conditions.append(MarketCondition.LIQUIDITY_EXPANSION)
            elif liq.regime in ("CONTRACTION", "STRONG_CONTRACTION"):
                conditions.append(MarketCondition.LIQUIDITY_CONTRACTION)
            factors.append(RegimeFactor(
                name="stablecoin liquidity", value=liq.regime,
                contribution=max(-100.0, min(100.0, liq.strength)), weight=1.0,
                detail=(
                    f"7-day change {liq.change_7d_pct:+.2f}%"
                    if liq.change_7d_pct is not None else ""
                ),
            ))
        else:
            missing.append("stablecoin liquidity")

        # --- 9. Macro risk appetite
        macro = context.get("macro")
        if macro is not None and getattr(macro, "available", False):
            appetite = macro.risk_appetite
            if appetite == "RISK_ON":
                conditions.append(MarketCondition.RISK_ON)
            elif appetite == "RISK_OFF":
                conditions.append(MarketCondition.RISK_OFF)
            factors.append(RegimeFactor(
                name="macro risk appetite", value=appetite,
                contribution=max(-100.0, min(100.0, macro.strength)), weight=1.2,
                detail=f"dollar {macro.dollar_trend}, rates {macro.rates_trend}",
            ))
        else:
            missing.append("macro")

        # --- aggregate ------------------------------------------------------
        directional = [f for f in factors if f.weight > 0]
        total_weight = sum(f.weight for f in directional)
        score = (
            sum(f.contribution * f.weight for f in directional) / total_weight
            if total_weight else 0.0
        )

        regime = self._label(score)
        # Confidence reflects how much evidence actually voted, not how extreme
        # the resulting number happens to be.
        coverage = len(directional) / 8.0
        confidence = min(100.0, 35.0 + coverage * 55.0 - len(missing) * 3.0)
        if daily.freshness is Freshness.STALE:
            confidence *= 0.6

        deduped: list[MarketCondition] = []
        for c in conditions:
            if c not in deduped:
                deduped.append(c)

        return RegimeAssessment(
            asset=asset, regime=regime, regime_score=round(score, 1),
            confidence=round(max(0.0, confidence), 1),
            conditions=deduped, factors=factors,
            evidence_ids=evidence_ids[:20], freshness=daily.freshness,
            summary=self._summary(asset, regime, score, deduped, factors),
            missing=missing,
        )

    # --- helpers ------------------------------------------------------------

    @staticmethod
    def _snap(snapshots: dict, code: str):
        for tf, snap in snapshots.items():
            if getattr(tf, "value", str(tf)) == code:
                return snap
        return None

    @staticmethod
    def _trend_factor(snap, name: str, weight: float) -> RegimeFactor:
        direction = snap.trend.direction
        contribution = {
            TrendDirection.UPTREND: 1.0, TrendDirection.DOWNTREND: -1.0,
            TrendDirection.RANGE: 0.0, TrendDirection.UNDETERMINED: 0.0,
        }[direction] * min(snap.trend.strength, 100.0)
        return RegimeFactor(
            name=name, value=direction.value, contribution=contribution,
            weight=weight, detail=snap.trend.reason,
        )

    @staticmethod
    def _structure_factor(snap) -> RegimeFactor:
        contribution = {
            MarketStructure.HH_HL: 70.0, MarketStructure.LH_LL: -70.0,
            MarketStructure.MIXED: 0.0, MarketStructure.RANGE: 0.0,
            MarketStructure.UNDETERMINED: 0.0,
        }[snap.structure]
        return RegimeFactor(
            name="market structure", value=snap.structure.value,
            contribution=contribution,
            weight=1.5 if snap.structure not in (
                MarketStructure.UNDETERMINED, MarketStructure.MIXED
            ) else 0.5,
            detail=" ".join(snap.structure_labels) if snap.structure_labels else "",
        )

    @staticmethod
    def _label(score: float) -> MarketRegime:
        if score >= 55:
            return MarketRegime.STRONGLY_BULLISH
        if score >= 20:
            return MarketRegime.BULLISH
        if score <= -55:
            return MarketRegime.STRONGLY_BEARISH
        if score <= -20:
            return MarketRegime.BEARISH
        return MarketRegime.NEUTRAL

    @staticmethod
    def _summary(asset, regime, score, conditions, factors) -> str:
        top = sorted(
            [f for f in factors if f.weight > 0],
            key=lambda f: abs(f.contribution) * f.weight, reverse=True,
        )[:3]
        drivers = ", ".join(f"{f.name} ({f.value})" for f in top)
        condition_text = (
            f" Character: {', '.join(c.value.replace('_', ' ').lower() for c in conditions[:3])}."
            if conditions else ""
        )
        return (
            f"{asset.value} regime {regime.value} (score {score:+.0f}). "
            f"Main drivers: {drivers}.{condition_text}"
        )

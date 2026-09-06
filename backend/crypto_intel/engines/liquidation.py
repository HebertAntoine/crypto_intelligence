"""Liquidation risk, and an honest UNAVAILABLE when the data is not there.

Binance closed its public aggregated liquidation stream. Without a Coinglass
subscription there is no legitimate source of aggregated liquidation data, so
this engine reports UNAVAILABLE rather than estimating it. Estimating
liquidations from open interest and price is possible in principle and
worthless in practice: the leverage distribution is not observable, so any
"liquidation level" would be an assumption presented as a measurement.

What CAN be measured without that feed is the conditions under which
liquidation cascades have historically occurred - high open interest, extreme
funding, compressed volatility. That is offered as CONTEXT and labelled as
such, never as a liquidation figure.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from ..core.enums import Asset
from ..logging_setup import get_logger

log = get_logger("engines.liquidation")


class LiquidationDataState(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE_NO_CONNECTOR = "UNAVAILABLE_NO_CONNECTOR"
    UNAVAILABLE_PROVIDER_ERROR = "UNAVAILABLE_PROVIDER_ERROR"


class CascadeRisk(StrEnum):
    LOW = "LOW"
    MODERATE = "MODERATE"
    ELEVATED = "ELEVATED"
    HIGH = "HIGH"
    UNKNOWN = "UNKNOWN"


class LiquidationAssessment(BaseModel):
    asset: str
    data_state: LiquidationDataState = LiquidationDataState.UNAVAILABLE_NO_CONNECTOR
    liquidations_24h_usd: float | None = None
    long_liquidations_usd: float | None = None
    short_liquidations_usd: float | None = None

    # Conditions, not liquidations. Measurable without the feed.
    cascade_risk: CascadeRisk = CascadeRisk.UNKNOWN
    risk_factors: list[dict[str, Any]] = Field(default_factory=list)
    conditions_note: str = ""
    reason: str = ""
    assessed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class LiquidationRiskEngine:
    """Report liquidation data when a connector exists; otherwise say so."""

    async def assess(self, asset: Asset) -> LiquidationAssessment:
        out = LiquidationAssessment(asset=asset.value)
        await self._try_fetch(asset, out)
        self._assess_conditions(asset, out)
        return out

    async def _try_fetch(self, asset: Asset, out: LiquidationAssessment) -> None:
        from ..providers.base import FetchRequest
        from ..providers.registry import get_registry

        try:
            result = await get_registry().fetch(
                FetchRequest(capability="derivatives.liquidations", asset=asset)
            )
        except Exception as exc:
            out.data_state = LiquidationDataState.UNAVAILABLE_PROVIDER_ERROR
            out.reason = f"provider error: {exc}"[:160]
            return

        if not result.ok or not result.data:
            out.data_state = LiquidationDataState.UNAVAILABLE_NO_CONNECTOR
            out.reason = (
                (result.message or "")[:160]
                or "no liquidation connector configured; Binance's public aggregated "
                "stream was withdrawn and no free replacement exists"
            )
            return

        out.data_state = LiquidationDataState.AVAILABLE
        for observation in result.data:
            metric = getattr(observation, "metric", "")
            value = getattr(observation, "value", None)
            if value is None:
                continue
            if metric.endswith("total") or metric.endswith("liquidations"):
                out.liquidations_24h_usd = float(value)
            elif "long" in metric:
                out.long_liquidations_usd = float(value)
            elif "short" in metric:
                out.short_liquidations_usd = float(value)

    def _assess_conditions(self, asset: Asset, out: LiquidationAssessment) -> None:
        """Conditions historically associated with cascades - not a forecast."""
        from .leverage import CrowdingLevel, FundingBand, LeverageCrowdingEngine
        from .volatility import VolatilityRegimeEngine

        engine = LeverageCrowdingEngine()
        crowding = engine.crowding(asset)
        funding = engine.funding_context(asset)
        volatility = VolatilityRegimeEngine().assess(asset)

        factors: list[dict[str, Any]] = []
        score = 0.0

        if crowding.level is CrowdingLevel.EXTREME:
            score += 40
            factors.append({"factor": "crowding EXTREME", "weight": 40})
        elif crowding.level is CrowdingLevel.ELEVATED:
            score += 25
            factors.append({"factor": "crowding ELEVATED", "weight": 25})

        if funding.band in (FundingBand.EXTREME_POSITIVE, FundingBand.EXTREME_NEGATIVE):
            score += 30
            factors.append({
                "factor": f"funding at {funding.band.value}",
                "weight": 30,
                "detail": "one side is paying heavily to hold its position",
            })

        # Compressed volatility after a leverage build-up is the classic
        # precondition; it says nothing about which direction resolves.
        if volatility.regime in ("VERY_LOW", "LOW") and crowding.score and crowding.score > 55:
            score += 20
            factors.append({
                "factor": "leverage built up during volatility compression",
                "weight": 20,
            })

        if crowding.oi_percentile is not None and crowding.oi_percentile >= 85:
            score += 15
            factors.append({
                "factor": f"open interest at the {crowding.oi_percentile:.0f}th percentile",
                "weight": 15,
            })

        out.risk_factors = factors
        if crowding.level is CrowdingLevel.UNKNOWN and funding.band is FundingBand.UNKNOWN:
            out.cascade_risk = CascadeRisk.UNKNOWN
            out.conditions_note = (
                "neither crowding nor funding could be measured, so cascade conditions "
                "are UNKNOWN rather than low"
            )
            if out.data_state is not LiquidationDataState.AVAILABLE:
                out.conditions_note += (
                    " Actual liquidation volumes are UNAVAILABLE and are not estimated."
                )
            return

        out.cascade_risk = (
            CascadeRisk.HIGH if score >= 70 else
            CascadeRisk.ELEVATED if score >= 45 else
            CascadeRisk.MODERATE if score >= 20 else CascadeRisk.LOW
        )
        out.conditions_note = (
            f"Cascade CONDITIONS are {out.cascade_risk.value}"
            + (f" ({', '.join(f['factor'] for f in factors)})" if factors else "")
            + ". This describes how fragile positioning looks, not a liquidation forecast, "
            "and gives no directional information: a cascade can resolve either way."
        )
        if out.data_state is not LiquidationDataState.AVAILABLE:
            out.conditions_note += (
                " Actual liquidation volumes are UNAVAILABLE and are not estimated."
            )

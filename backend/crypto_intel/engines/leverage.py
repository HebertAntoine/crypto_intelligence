"""Funding percentiles, the OI/funding/price state machine, and crowding.

LOT 3 found the fixed funding threshold (0.0025) was crossed on 0.04-0.09% of
days, so 97-99% of history scored neutral - the threshold described almost
nothing. Percentiles fix that by asking "how does today compare to this
asset's own history" instead of comparing against a constant nobody derived.

Every percentile here is TRAILING: rank at time t uses only data strictly
before t. That is what makes these values usable in a backtest, and it is the
same anti-leakage rule the LOT 3 audit enforced elsewhere.

Crowding deliberately reports no direction. Open interest counts contracts,
not sides - every long has a short. Funding tells us who pays whom, which is
suggestive but not a position census. Claiming "the crowd is long" would be an
inference dressed as a measurement.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

from ..core.enums import Asset, Timeframe
from ..history import store
from ..logging_setup import get_logger

log = get_logger("engines.leverage")

MIN_HISTORY_FOR_PERCENTILE = 180   # days before a trailing rank means anything
LOOKBACK_DAYS = 365 * 2


class FundingBand(StrEnum):
    """Where funding sits in its own history, not against a fixed number."""

    EXTREME_NEGATIVE = "EXTREME_NEGATIVE"   # p0-p5
    NEGATIVE = "NEGATIVE"                   # p5-p25
    NEUTRAL = "NEUTRAL"                     # p25-p75
    POSITIVE = "POSITIVE"                   # p75-p95
    EXTREME_POSITIVE = "EXTREME_POSITIVE"   # p95-p100
    UNKNOWN = "UNKNOWN"


class CrowdingLevel(StrEnum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    ELEVATED = "ELEVATED"
    EXTREME = "EXTREME"
    UNKNOWN = "UNKNOWN"


class LeverageState(StrEnum):
    """Joint OI / funding / price state.

    The classic reading: rising price with rising OI is new money; rising price
    with falling OI is shorts covering. Both can precede the same candle and
    mean different things.
    """

    NEW_LONGS = "NEW_LONGS"
    NEW_SHORTS = "NEW_SHORTS"
    SHORT_COVERING = "SHORT_COVERING"
    LONG_LIQUIDATION = "LONG_LIQUIDATION"
    DELEVERAGING = "DELEVERAGING"
    QUIET = "QUIET"
    UNDETERMINED = "UNDETERMINED"


def _trailing_percentile(series: pd.Series, window: int | None = None) -> pd.Series:
    """Rank of each value against everything strictly before it.

    A full-sample `rank(pct=True)` would let the future set today's percentile;
    that is exactly the leak the LOT 3 audit was built to catch.
    """
    clean = series.dropna()
    if clean.empty:
        return pd.Series(dtype=float)
    if window:
        return clean.rolling(window, min_periods=MIN_HISTORY_FOR_PERCENTILE).apply(
            lambda w: (w[:-1] < w[-1]).mean() * 100.0 if len(w) > 1 else np.nan, raw=True
        )
    ranks = [np.nan] * len(clean)
    values = clean.to_numpy()
    for i in range(MIN_HISTORY_FOR_PERCENTILE, len(values)):
        ranks[i] = float((values[:i] < values[i]).mean() * 100.0)
    return pd.Series(ranks, index=clean.index)


def band_for_percentile(pct: float | None) -> FundingBand:
    if pct is None or not np.isfinite(pct):
        return FundingBand.UNKNOWN
    if pct >= 95:
        return FundingBand.EXTREME_POSITIVE
    if pct >= 75:
        return FundingBand.POSITIVE
    if pct > 25:
        return FundingBand.NEUTRAL
    if pct > 5:
        return FundingBand.NEGATIVE
    return FundingBand.EXTREME_NEGATIVE


class FundingContext(BaseModel):
    asset: str
    value: float | None = None
    percentile: float | None = None
    band: FundingBand = FundingBand.UNKNOWN
    annualised_pct: float | None = None
    history_days: int = 0
    sufficient_history: bool = False
    note: str = ""


class CrowdingAssessment(BaseModel):
    asset: str
    level: CrowdingLevel = CrowdingLevel.UNKNOWN
    score: float | None = Field(default=None, description="0-100, higher = more crowded")
    direction: str = Field(
        default="UNKNOWN",
        description="Always UNKNOWN: open interest has two sides and we cannot see them.",
    )
    oi_percentile: float | None = None
    funding_percentile: float | None = None
    oi_change_7d_pct: float | None = None
    components: dict[str, Any] = Field(default_factory=dict)
    interpretation: str = ""
    missing: list[str] = Field(default_factory=list)


class LeverageStateAssessment(BaseModel):
    asset: str
    state: LeverageState = LeverageState.UNDETERMINED
    price_change_pct: float | None = None
    oi_change_pct: float | None = None
    funding_band: FundingBand = FundingBand.UNKNOWN
    confidence: str = "LOW"
    inputs_used: list[str] = Field(default_factory=list)
    inputs_missing: list[str] = Field(default_factory=list)
    interpretation: str = ""


class LeverageCrowdingEngine:
    """Percentile funding, joint OI/price state, and a crowding read."""

    def __init__(self, lookback_days: int = LOOKBACK_DAYS) -> None:
        self.lookback_days = lookback_days

    # -- funding ---------------------------------------------------------
    def funding_context(self, asset: Asset, as_of: datetime | None = None) -> FundingContext:
        funding = store.load_derivatives(asset, "funding.rate")
        ctx = FundingContext(asset=asset.value)
        if funding.empty:
            ctx.note = "no funding history stored"
            return ctx

        if as_of is not None:
            funding = funding[funding.index <= as_of]
        if funding.empty:
            ctx.note = "no funding observation at or before the requested time"
            return ctx

        daily = funding.resample("1D").mean().dropna()
        ctx.history_days = len(daily)
        ctx.value = float(funding.iloc[-1])
        # Binance settles every 8h, so a period rate compounds 3x daily.
        ctx.annualised_pct = round(ctx.value * 3 * 365 * 100, 2)

        if ctx.history_days < MIN_HISTORY_FOR_PERCENTILE:
            ctx.note = (
                f"{ctx.history_days} days of history, below the {MIN_HISTORY_FOR_PERCENTILE}-day "
                "minimum for a trailing percentile"
            )
            return ctx

        ctx.sufficient_history = True
        prior = daily.iloc[:-1].to_numpy()
        ctx.percentile = round(float((prior < daily.iloc[-1]).mean() * 100.0), 1)
        ctx.band = band_for_percentile(ctx.percentile)
        ctx.note = (
            f"funding {ctx.value:.6f} sits at the {ctx.percentile:.0f}th percentile of "
            f"{ctx.history_days} days of this asset's own history"
        )
        return ctx

    def funding_percentile_series(self, asset: Asset) -> pd.Series:
        """Trailing funding percentiles, for research and backtests."""
        funding = store.load_derivatives(asset, "funding.rate")
        if funding.empty:
            return pd.Series(dtype=float)
        return _trailing_percentile(funding.resample("1D").mean().dropna())

    # -- OI / funding / price state machine --------------------------------
    def leverage_state(
        self, asset: Asset, as_of: datetime | None = None, window_days: int = 7
    ) -> LeverageStateAssessment:
        """Read price and OI together, degrading explicitly when OI is missing.

        The hierarchy: with price + OI + funding we name a state; with price and
        funding only we say so and stay coarse; with price alone we return
        UNDETERMINED rather than guessing.
        """
        out = LeverageStateAssessment(asset=asset.value)

        candles = store.load_candles(asset, Timeframe.D1)
        oi = self._best_oi_series(asset)
        funding_ctx = self.funding_context(asset, as_of=as_of)
        out.funding_band = funding_ctx.band

        if as_of is not None:
            if not candles.empty:
                candles = candles[candles.index <= as_of]
            if not oi.empty:
                oi = oi[oi.index <= as_of]

        if candles.empty or len(candles) < window_days + 1:
            out.inputs_missing.append("price")
            out.interpretation = "no usable price history"
            return out

        closes = candles["close"]
        out.price_change_pct = round(
            float((closes.iloc[-1] / closes.iloc[-1 - window_days] - 1) * 100), 2
        )
        out.inputs_used.append("price")

        if funding_ctx.band is not FundingBand.UNKNOWN:
            out.inputs_used.append("funding")
        else:
            out.inputs_missing.append("funding")

        if oi.empty or len(oi) < window_days + 1:
            out.inputs_missing.append("open_interest")
            out.confidence = "LOW"
            out.interpretation = (
                "open interest unavailable over the window, so new positioning cannot be "
                "separated from position closing; state left UNDETERMINED"
            )
            return out

        out.inputs_used.append("open_interest")
        out.oi_change_pct = round(
            float((oi.iloc[-1] / oi.iloc[-1 - window_days] - 1) * 100), 2
        )

        price_up = out.price_change_pct > 1.0
        price_down = out.price_change_pct < -1.0
        oi_up = out.oi_change_pct > 2.0
        oi_down = out.oi_change_pct < -2.0

        if price_up and oi_up:
            out.state = LeverageState.NEW_LONGS
            out.interpretation = (
                "price and open interest both rose: new positions are being opened into "
                "the move rather than old ones closing"
            )
        elif price_down and oi_up:
            out.state = LeverageState.NEW_SHORTS
            out.interpretation = "price fell while open interest rose: new short exposure"
        elif price_up and oi_down:
            out.state = LeverageState.SHORT_COVERING
            out.interpretation = (
                "price rose while open interest fell: the move looks like existing shorts "
                "closing, not fresh buying"
            )
        elif price_down and oi_down:
            out.state = LeverageState.LONG_LIQUIDATION
            out.interpretation = (
                "price and open interest both fell: existing longs are being closed out"
            )
        elif oi_down:
            out.state = LeverageState.DELEVERAGING
            out.interpretation = "open interest falling without a decisive price move"
        else:
            out.state = LeverageState.QUIET
            out.interpretation = "neither price nor open interest moved decisively"

        out.confidence = "MEDIUM" if len(out.inputs_used) == 3 else "LOW"
        return out

    def _best_oi_series(self, asset: Asset) -> pd.Series:
        """Prefer the deeper Bybit series; fall back to the shallow Binance one."""
        for metric in ("oi.contracts_bybit", "oi.value", "oi.contracts"):
            series = store.load_derivatives(asset, metric)
            if not series.empty:
                return series.resample("1D").last().dropna()
        return pd.Series(dtype=float)

    # -- crowding ---------------------------------------------------------
    def crowding(self, asset: Asset, as_of: datetime | None = None) -> CrowdingAssessment:
        """How stretched is leverage, without claiming which side is stretched."""
        out = CrowdingAssessment(asset=asset.value)
        components: dict[str, Any] = {}

        funding_ctx = self.funding_context(asset, as_of=as_of)
        oi = self._best_oi_series(asset)
        if as_of is not None and not oi.empty:
            oi = oi[oi.index <= as_of]

        parts: list[float] = []

        # Funding magnitude: distance from neutral in either direction. Extreme
        # negative funding is crowding too - it is just crowded the other way.
        if funding_ctx.percentile is not None:
            out.funding_percentile = funding_ctx.percentile
            funding_stretch = abs(funding_ctx.percentile - 50.0) * 2.0
            parts.append(funding_stretch)
            components["funding_stretch"] = round(funding_stretch, 1)
        else:
            out.missing.append("funding percentile (insufficient history)")

        if len(oi) >= MIN_HISTORY_FOR_PERCENTILE:
            prior = oi.iloc[:-1].to_numpy()
            out.oi_percentile = round(float((prior < oi.iloc[-1]).mean() * 100.0), 1)
            parts.append(out.oi_percentile)
            components["oi_percentile"] = out.oi_percentile

            if len(oi) >= 8:
                out.oi_change_7d_pct = round(float((oi.iloc[-1] / oi.iloc[-8] - 1) * 100), 2)
                # Fast OI build is crowding independent of the absolute level.
                velocity = min(100.0, max(0.0, out.oi_change_7d_pct * 5.0))
                parts.append(velocity)
                components["oi_velocity"] = round(velocity, 1)
        else:
            out.missing.append(
                f"open-interest percentile (only {len(oi)} days, need {MIN_HISTORY_FOR_PERCENTILE})"
            )

        if not parts:
            out.interpretation = (
                "neither funding nor open interest has enough history to place today "
                "against; crowding is UNKNOWN, not low"
            )
            return out

        out.score = round(float(np.mean(parts)), 1)
        out.components = components

        if out.score >= 80:
            out.level = CrowdingLevel.EXTREME
        elif out.score >= 60:
            out.level = CrowdingLevel.ELEVATED
        elif out.score >= 30:
            out.level = CrowdingLevel.NORMAL
        else:
            out.level = CrowdingLevel.LOW

        side = ""
        if funding_ctx.band in (FundingBand.EXTREME_POSITIVE, FundingBand.POSITIVE):
            side = " Longs are paying shorts, which is consistent with long-side crowding."
        elif funding_ctx.band in (FundingBand.EXTREME_NEGATIVE, FundingBand.NEGATIVE):
            side = " Shorts are paying longs, which is consistent with short-side crowding."

        out.interpretation = (
            f"crowding {out.level.value} ({out.score:.0f}/100) from "
            f"{', '.join(components)}.{side} Direction is reported UNKNOWN: open interest "
            "counts contracts, not sides, so the balance of positioning is not observable."
        )
        if out.missing:
            out.interpretation += f" Computed without: {'; '.join(out.missing)}."
        return out

    def assess(self, asset: Asset, as_of: datetime | None = None) -> dict[str, Any]:
        return {
            "asset": asset.value,
            "funding": self.funding_context(asset, as_of).model_dump(),
            "state": self.leverage_state(asset, as_of).model_dump(),
            "crowding": self.crowding(asset, as_of).model_dump(),
            "as_of": (as_of or datetime.now(UTC)).isoformat(),
        }

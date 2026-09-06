"""Implied volatility and the variance risk premium.

DVOL is what the options market expects volatility to be. Realised volatility
is what it turned out to be. The gap between them is the premium paid for
protection, and it is the only quantity in this project that comes from a
market other than spot or perpetuals.

Two rules shape the implementation.

The **level** of implied volatility is nearly a restatement of recent realised
volatility - they correlate strongly by construction. So the level is reported
but the analysis rests on the SPREAD and on trailing percentiles, which is
where the information that is not already in the price series would live.

Realised volatility is computed strictly backwards from the measurement date.
Comparing today's implied volatility with volatility that has not happened yet
would be the cleanest possible look-ahead, and the split here makes that
impossible: `realised_trailing` only ever looks at [t-window, t].
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

from ..core.enums import Asset, Timeframe
from ..history import store
from ..logging_setup import get_logger

log = get_logger("engines.implied_volatility")

MIN_HISTORY_FOR_PERCENTILE = 180
DEFAULT_WINDOW = 30


class VolatilityPricing(StrEnum):
    """How the options market is pricing risk against what has occurred."""

    EXPENSIVE = "EXPENSIVE"           # implied far above realised
    SLIGHTLY_EXPENSIVE = "SLIGHTLY_EXPENSIVE"
    FAIR = "FAIR"
    SLIGHTLY_CHEAP = "SLIGHTLY_CHEAP"
    CHEAP = "CHEAP"                   # implied below realised
    UNKNOWN = "UNKNOWN"


class ImpliedVolatilityReading(BaseModel):
    asset: str
    available: bool = False
    unavailable_reason: str = ""
    dvol: float | None = None
    dvol_percentile: float | None = None
    dvol_change_30d: float | None = None
    realised_vol_annualised: float | None = None
    variance_premium: float | None = Field(
        default=None,
        description="implied minus trailing realised, in annualised volatility points",
    )
    premium_percentile: float | None = None
    pricing: VolatilityPricing = VolatilityPricing.UNKNOWN
    compression: str = "UNKNOWN"
    history_days: int = 0
    interpretation: str = ""
    edge_note: str = (
        "The variance premium is a description of how options are priced. Whether "
        "it precedes anything has not been established for this project and must "
        "not be assumed."
    )

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def _trailing_percentile(series: pd.Series, min_history: int = MIN_HISTORY_FOR_PERCENTILE) -> float | None:
    """Rank of the last value against everything strictly before it."""
    clean = series.dropna()
    if len(clean) < min_history:
        return None
    prior = clean.iloc[:-1].to_numpy()
    return round(float((prior < clean.iloc[-1]).mean() * 100), 1)


class ImpliedVolatilityEngine:
    """Read DVOL against the volatility that actually occurred."""

    def __init__(self, window: int = DEFAULT_WINDOW) -> None:
        self.window = window

    def realised_trailing(
        self, asset: Asset, as_of: datetime | None = None
    ) -> pd.Series:
        """Annualised realised volatility over a strictly PAST window.

        The `.rolling(window)` here closes at each bar, so the value at t uses
        [t-window, t] and never a later bar. That is what keeps the premium
        from being a comparison against the future.
        """
        df = store.load_candles(asset, Timeframe.D1)
        if as_of is not None and not df.empty:
            df = df[df.index <= as_of]
        if df.empty:
            return pd.Series(dtype=float)
        returns = df["close"].pct_change()
        return returns.rolling(self.window).std() * np.sqrt(365) * 100

    def assess(
        self, asset: Asset, as_of: datetime | None = None
    ) -> ImpliedVolatilityReading:
        out = ImpliedVolatilityReading(asset=asset.value)

        dvol = store.load_derivatives(asset, "dvol.index")
        if dvol.empty:
            out.unavailable_reason = (
                "no implied-volatility index stored for this asset. Deribit "
                "publishes one for BTC and ETH only; nothing is substituted for SOL."
            )
            return out
        if as_of is not None:
            dvol = dvol[dvol.index <= as_of]
        if dvol.empty:
            out.unavailable_reason = "no implied-volatility observation at or before this time"
            return out

        out.available = True
        out.history_days = len(dvol)
        out.dvol = round(float(dvol.iloc[-1]), 3)
        out.dvol_percentile = _trailing_percentile(dvol)
        if len(dvol) >= 31:
            out.dvol_change_30d = round(
                float(dvol.iloc[-1] - dvol.iloc[-31]), 3
            )

        realised = self.realised_trailing(asset, as_of)
        if not realised.empty:
            aligned = realised.reindex(dvol.index, method="ffill").dropna()
            if not aligned.empty:
                out.realised_vol_annualised = round(float(aligned.iloc[-1]), 3)
                premium = dvol.reindex(aligned.index) - aligned
                out.variance_premium = round(float(premium.iloc[-1]), 3)
                out.premium_percentile = _trailing_percentile(premium)
                out.pricing = self._classify_pricing(out.premium_percentile)

        # Compression or expansion of the implied series itself.
        if len(dvol) >= 90:
            recent = float(dvol.iloc[-14:].mean())
            earlier = float(dvol.iloc[-90:-14].mean())
            if earlier > 0:
                ratio = recent / earlier
                out.compression = (
                    "COMPRESSION" if ratio < 0.85
                    else "EXPANSION" if ratio > 1.18 else "STABLE"
                )

        out.interpretation = self._interpret(out)
        return out

    def _classify_pricing(self, percentile: float | None) -> VolatilityPricing:
        if percentile is None:
            return VolatilityPricing.UNKNOWN
        if percentile >= 90:
            return VolatilityPricing.EXPENSIVE
        if percentile >= 70:
            return VolatilityPricing.SLIGHTLY_EXPENSIVE
        if percentile > 30:
            return VolatilityPricing.FAIR
        if percentile > 10:
            return VolatilityPricing.SLIGHTLY_CHEAP
        return VolatilityPricing.CHEAP

    def _interpret(self, out: ImpliedVolatilityReading) -> str:
        if out.variance_premium is None:
            return (
                f"Implied volatility {out.dvol}"
                + (f" at the {out.dvol_percentile:.0f}th percentile" if out.dvol_percentile else "")
                + ". Realised volatility could not be aligned, so no premium is shown."
            )
        direction = "above" if out.variance_premium > 0 else "below"
        return (
            f"Implied volatility {out.dvol:.1f} sits {abs(out.variance_premium):.1f} "
            f"points {direction} the {self.window}-day realised volatility of "
            f"{out.realised_vol_annualised:.1f}. That premium is at the "
            f"{out.premium_percentile:.0f}th percentile of its own history "
            f"({out.history_days} days), so options are priced "
            f"{out.pricing.value.replace('_', ' ').lower()} relative to what has "
            f"actually happened. Implied volatility itself is in {out.compression.lower()}. "
            "This describes the price of protection, not a direction."
        )

    def features(self, asset: Asset) -> pd.DataFrame:
        """Point-in-time feature frame for research.

        Every column uses only information available at its own timestamp: the
        percentiles are trailing, and the realised leg closes at the bar.
        """
        dvol = store.load_derivatives(asset, "dvol.index")
        if dvol.empty:
            return pd.DataFrame()

        realised = self.realised_trailing(asset)
        frame = pd.DataFrame(index=dvol.index)
        frame["dvol"] = dvol
        frame["dvol_change_30"] = dvol.diff(30)
        frame["realised_vol"] = realised.reindex(dvol.index, method="ffill")
        frame["variance_premium"] = frame["dvol"] - frame["realised_vol"]

        for column in ("dvol", "variance_premium"):
            values = frame[column].to_numpy(dtype=float)
            ranks = np.full(len(values), np.nan)
            for i in range(MIN_HISTORY_FOR_PERCENTILE, len(values)):
                window = values[:i]
                window = window[~np.isnan(window)]
                if len(window):
                    ranks[i] = float((window < values[i]).mean() * 100)
            frame[f"{column}_percentile"] = ranks

        return frame

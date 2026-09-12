"""Volatility regime: how much the market is moving, not which way.

Kept separate from direction on purpose. Volatility expansion is compatible
with a rally and with a crash; treating it as bearish - the common shortcut -
smuggles a directional claim into a measurement that does not contain one.

Percentiles are trailing, so a regime label computed for a past date uses only
what was knowable then.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

import numpy as np
import pandas as pd
from pydantic import BaseModel

from ..core.enums import Asset, Timeframe
from ..engines.technical import indicators as ind
from ..future_events.models import DirectionalBias, ExpectedMovement
from ..history import store
from ..logging_setup import get_logger

log = get_logger("engines.volatility")

MIN_HISTORY = 200


class VolRegime(StrEnum):
    VERY_LOW = "VERY_LOW"
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"
    UNKNOWN = "UNKNOWN"


class VolatilityAssessment(BaseModel):
    asset: str
    regime: str = VolRegime.UNKNOWN.value
    atr_percent: float | None = None
    atr_percentile: float | None = None
    realised_vol_30d: float | None = None
    realised_vol_annualised: float | None = None
    direction: str = "STABLE"          # EXPANDING / CONTRACTING / STABLE
    expansion_ratio: float | None = None
    history_days: int = 0
    interpretation: str = ""
    note: str = ""

    @property
    def sizing_note(self) -> str:
        return (
            "Position sizing should scale inversely with volatility; this is a "
            "risk statement, not a directional one."
        )


class VolatilityRegimeEngine:
    def assess(self, asset: Asset, as_of: Any = None) -> VolatilityAssessment:
        out = VolatilityAssessment(asset=asset.value)
        df = store.load_candles(asset, Timeframe.D1)
        if as_of is not None and not df.empty:
            df = df[df.index <= as_of]

        if df.empty or len(df) < 30:
            out.note = "insufficient daily history"
            return out

        out.history_days = len(df)
        atr_pct = ind.atr_percent(df["high"], df["low"], df["close"], 14)
        out.atr_percent = round(float(atr_pct.iloc[-1]), 3)

        returns = df["close"].pct_change()
        realised = returns.rolling(30).std()
        if not np.isnan(realised.iloc[-1]):
            out.realised_vol_30d = round(float(realised.iloc[-1]) * 100, 3)
            out.realised_vol_annualised = round(float(realised.iloc[-1]) * np.sqrt(365) * 100, 2)

        # Expansion compares the last two weeks against the prior quarter.
        if len(atr_pct.dropna()) >= 90:
            recent = float(atr_pct.iloc[-14:].mean())
            prior = float(atr_pct.iloc[-90:-14].mean())
            if prior > 0:
                out.expansion_ratio = round(recent / prior, 3)
                if out.expansion_ratio > 1.25:
                    out.direction = "EXPANDING"
                elif out.expansion_ratio < 0.8:
                    out.direction = "CONTRACTING"

        clean = atr_pct.dropna()
        if len(clean) < MIN_HISTORY:
            out.note = (
                f"{len(clean)} days of ATR history, below the {MIN_HISTORY}-day minimum "
                "for a percentile; regime left UNKNOWN"
            )
            return out

        prior_values = clean.iloc[:-1].to_numpy()
        out.atr_percentile = round(float((prior_values < clean.iloc[-1]).mean() * 100), 1)

        if out.atr_percentile >= 90:
            out.regime = VolRegime.VERY_HIGH.value
        elif out.atr_percentile >= 70:
            out.regime = VolRegime.HIGH.value
        elif out.atr_percentile > 30:
            out.regime = VolRegime.NORMAL.value
        elif out.atr_percentile > 10:
            out.regime = VolRegime.LOW.value
        else:
            out.regime = VolRegime.VERY_LOW.value

        out.interpretation = (
            f"ATR is {out.atr_percent:.2f}% of price, the {out.atr_percentile:.0f}th percentile "
            f"of {len(clean)} days, so volatility is {out.regime} and {out.direction.lower()}. "
            f"Annualised realised volatility is {out.realised_vol_annualised:.0f}%. "
            "This describes the size of moves, not their direction."
        )
        return out

    def percentile_series(self, asset: Asset) -> pd.Series:
        """Trailing ATR percentile, for conditioning research."""
        df = store.load_candles(asset, Timeframe.D1)
        if df.empty:
            return pd.Series(dtype=float)
        atr_pct = ind.atr_percent(df["high"], df["low"], df["close"], 14).dropna()
        values = atr_pct.to_numpy()
        ranks = [np.nan] * len(values)
        for i in range(MIN_HISTORY, len(values)):
            ranks[i] = float((values[:i] < values[i]).mean() * 100)
        return pd.Series(ranks, index=atr_pct.index)


class ProspectiveVolatilitySignal(BaseModel):
    available: bool
    squeeze: bool | None = None
    bandwidth: float | None = None
    bandwidth_percentile: float | None = None
    directional_bias: DirectionalBias = DirectionalBias.NEUTRAL
    direction_contribution: float = 0.0
    expected_movement: ExpectedMovement = ExpectedMovement.NORMAL
    explanation: str = ""


class ExpectedVolatilityEngine:
    """Translate compression into amplitude only, never price direction."""

    def assess_bollinger(self, closes: pd.Series, *, min_history: int = 60) -> ProspectiveVolatilitySignal:
        bandwidth = ind.bollinger_bandwidth(closes.astype(float), 20, 2.0).dropna()
        if len(bandwidth) < min_history:
            return ProspectiveVolatilitySignal(
                available=False,
                explanation=(
                    f"UNAVAILABLE - {len(bandwidth)} bandwidth observations; "
                    f"{min_history} required for a trailing percentile."
                ),
            )
        current = float(bandwidth.iloc[-1])
        prior = bandwidth.iloc[:-1].to_numpy()
        percentile = float((prior < current).mean() * 100.0)
        squeeze = percentile <= 10.0
        return ProspectiveVolatilitySignal(
            available=True,
            squeeze=squeeze,
            bandwidth=current,
            bandwidth_percentile=percentile,
            directional_bias=DirectionalBias.NEUTRAL,
            direction_contribution=0.0,
            expected_movement=ExpectedMovement.HIGH if squeeze else ExpectedMovement.NORMAL,
            explanation=(
                "Bollinger compression raises the risk of volatility expansion. "
                "It contains no information about the direction of the next move."
                if squeeze
                else "No extreme Bollinger compression is present; no direction is inferred."
            ),
        )

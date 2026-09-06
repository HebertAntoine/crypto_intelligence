"""Cross-asset context: correlations, ratios, breadth and liquidity regime.

Crypto does not trade in isolation. A SOL drawdown that coincides with a
Nasdaq drawdown and a rising dollar is a macro event wearing a SOL costume;
the same drawdown while BTC and ETH hold is SOL-specific. Telling those apart
requires measuring the relationship rather than assuming it, which is what
this module does.

Everything here is rolling and trailing. Correlations are computed on returns,
never on levels - two rising series correlate near 1.0 whatever their actual
relationship, and level correlation is one of the easiest ways to manufacture
a finding that does not exist.
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

log = get_logger("engines.cross_asset")

# Macro series worth relating crypto to, with the sign convention a reader
# expects. "inverse_expected" only documents the common belief - it is never
# used to force or flip a measured value.
MACRO_SERIES: dict[str, dict[str, Any]] = {
    "macro.nasdaq": {"label": "Nasdaq", "inverse_expected": False},
    "macro.sp500": {"label": "S&P 500", "inverse_expected": False},
    "macro.dxy": {"label": "US dollar index", "inverse_expected": True},
    "macro.vix": {"label": "VIX", "inverse_expected": True},
    "macro.gold": {"label": "Gold", "inverse_expected": False},
    "macro.oil_wti": {"label": "WTI crude", "inverse_expected": False},
    "macro.us10y_yahoo": {"label": "US 10Y yield", "inverse_expected": True},
}

MIN_OVERLAP = 60          # days of shared history before a correlation is shown
DEFAULT_WINDOW = 90


class LiquidityRegime(StrEnum):
    EXPANSION = "EXPANSION"
    NEUTRAL = "NEUTRAL"
    CONTRACTION = "CONTRACTION"
    UNKNOWN = "UNKNOWN"


class CorrelationReading(BaseModel):
    series: str
    label: str
    correlation: float | None = None
    beta: float | None = None
    observations: int = 0
    window_days: int = DEFAULT_WINDOW
    percentile_vs_history: float | None = None
    note: str = ""


class CrossAssetAssessment(BaseModel):
    asset: str
    correlations: list[CorrelationReading] = Field(default_factory=list)
    dominant_relationship: str | None = None
    risk_proxy_correlation: float | None = None
    interpretation: str = ""
    missing: list[str] = Field(default_factory=list)


class RatioReading(BaseModel):
    name: str
    value: float | None = None
    change_30d_pct: float | None = None
    percentile: float | None = None
    trend: str = "UNKNOWN"
    interpretation: str = ""


class BreadthAssessment(BaseModel):
    score: float | None = Field(default=None, description="0-100, share of the set advancing")
    assets_above_ema50: int = 0
    assets_above_ema200: int = 0
    assets_measured: int = 0
    positive_30d: int = 0
    state: str = "UNKNOWN"
    interpretation: str = ""
    per_asset: dict[str, Any] = Field(default_factory=dict)


class LiquidityAssessment(BaseModel):
    regime: LiquidityRegime = LiquidityRegime.UNKNOWN
    components: dict[str, Any] = Field(default_factory=dict)
    score: float | None = None
    interpretation: str = ""
    missing: list[str] = Field(default_factory=list)


def _daily_closes(asset: Asset) -> pd.Series:
    df = store.load_candles(asset, Timeframe.D1)
    if df.empty:
        return pd.Series(dtype=float)
    return df["close"]


def _normalise_index(series: pd.Series) -> pd.Series:
    """Collapse to date-level so daily crypto and daily equities can align."""
    if series.empty:
        return series
    out = series.copy()
    out.index = pd.DatetimeIndex(out.index).tz_convert(UTC).normalize()
    return out[~out.index.duplicated(keep="last")]


class CrossAssetAnalyzer:
    """Rolling correlation and beta of one crypto asset against macro series."""

    def __init__(self, window: int = DEFAULT_WINDOW) -> None:
        self.window = window

    def assess(self, asset: Asset, as_of: datetime | None = None) -> CrossAssetAssessment:
        out = CrossAssetAssessment(asset=asset.value)
        closes = _normalise_index(_daily_closes(asset))
        if as_of is not None and not closes.empty:
            closes = closes[closes.index <= pd.Timestamp(as_of).tz_convert(UTC).normalize()]

        if closes.empty or len(closes) < MIN_OVERLAP:
            out.interpretation = "insufficient price history for cross-asset correlation"
            return out

        crypto_returns = closes.pct_change()

        for metric, meta in MACRO_SERIES.items():
            macro = _normalise_index(store.load_macro(metric))
            if macro.empty:
                out.missing.append(metric)
                continue
            if as_of is not None:
                macro = macro[macro.index <= pd.Timestamp(as_of).tz_convert(UTC).normalize()]

            macro_returns = macro.pct_change()
            joined = pd.concat(
                [crypto_returns.rename("crypto"), macro_returns.rename("macro")], axis=1
            ).dropna()

            reading = CorrelationReading(
                series=metric, label=meta["label"], window_days=self.window
            )
            if len(joined) < MIN_OVERLAP:
                reading.note = (
                    f"only {len(joined)} overlapping days, below the {MIN_OVERLAP} minimum"
                )
                out.correlations.append(reading)
                continue

            recent = joined.iloc[-self.window:]
            reading.observations = len(recent)
            if len(recent) >= 20 and recent["macro"].std() > 0:
                reading.correlation = round(
                    float(recent["crypto"].corr(recent["macro"])), 3
                )
                # Beta: how much crypto moves per unit of the macro series.
                reading.beta = round(
                    float(
                        recent["crypto"].cov(recent["macro"]) / recent["macro"].var()
                    ), 3
                )

                # Where does today's correlation sit against its own history?
                rolling = joined["crypto"].rolling(self.window).corr(joined["macro"]).dropna()
                if len(rolling) >= MIN_OVERLAP and reading.correlation is not None:
                    prior = rolling.iloc[:-1].to_numpy()
                    reading.percentile_vs_history = round(
                        float((prior < reading.correlation).mean() * 100), 1
                    )
            out.correlations.append(reading)

        measured = [c for c in out.correlations if c.correlation is not None]
        if not measured:
            out.interpretation = "no macro series had enough overlapping history"
            return out

        strongest = max(measured, key=lambda c: abs(c.correlation or 0))
        out.dominant_relationship = strongest.label
        nasdaq = next((c for c in measured if c.series == "macro.nasdaq"), None)
        out.risk_proxy_correlation = nasdaq.correlation if nasdaq else None

        out.interpretation = (
            f"Over the last {self.window} days, {asset.value} moves most closely with "
            f"{strongest.label} (correlation {strongest.correlation:+.2f}, beta "
            f"{strongest.beta:+.2f}). "
            + (
                f"Correlation with the Nasdaq is {nasdaq.correlation:+.2f}, so a move of this "
                "size is "
                + (
                    "hard to separate from general risk appetite."
                    if abs(nasdaq.correlation or 0) > 0.4
                    else "not well explained by equities alone."
                )
                if nasdaq and nasdaq.correlation is not None else ""
            )
            + " Correlation is not causation and says nothing about direction."
        )
        return out


class MarketRatiosEngine:
    """BTC dominance proxy plus the ratios that separate rotation from beta."""

    def assess(self, as_of: datetime | None = None) -> dict[str, Any]:
        closes = {a.value: _normalise_index(_daily_closes(a)) for a in Asset.tradables()}
        if as_of is not None:
            cutoff = pd.Timestamp(as_of).tz_convert(UTC).normalize()
            closes = {k: v[v.index <= cutoff] for k, v in closes.items()}

        readings: list[RatioReading] = []
        for name, (numerator, denominator) in {
            "ETH/BTC": ("ETH", "BTC"),
            "SOL/BTC": ("SOL", "BTC"),
            "SOL/ETH": ("SOL", "ETH"),
        }.items():
            top, bottom = closes.get(numerator), closes.get(denominator)
            reading = RatioReading(name=name)
            if top is None or bottom is None or top.empty or bottom.empty:
                reading.interpretation = "missing price history"
                readings.append(reading)
                continue

            ratio = (top / bottom).dropna()
            if len(ratio) < 60:
                reading.interpretation = f"only {len(ratio)} overlapping days"
                readings.append(reading)
                continue

            reading.value = round(float(ratio.iloc[-1]), 6)
            if len(ratio) >= 31:
                reading.change_30d_pct = round(
                    float((ratio.iloc[-1] / ratio.iloc[-31] - 1) * 100), 2
                )
            if len(ratio) >= 200:
                prior = ratio.iloc[:-1].to_numpy()
                reading.percentile = round(float((prior < ratio.iloc[-1]).mean() * 100), 1)

            if reading.change_30d_pct is not None:
                if reading.change_30d_pct > 5:
                    reading.trend = "RISING"
                elif reading.change_30d_pct < -5:
                    reading.trend = "FALLING"
                else:
                    reading.trend = "FLAT"

            reading.interpretation = (
                f"{name} is {reading.trend.lower()} ({reading.change_30d_pct:+.1f}% over 30 days)"
                + (
                    f", at the {reading.percentile:.0f}th percentile of its history"
                    if reading.percentile is not None else ""
                )
                + f". A {'rising' if reading.trend == 'RISING' else 'falling'} ratio means "
                f"{numerator} is outperforming {denominator}, which is a statement about "
                "relative strength only - both can be falling in absolute terms."
            )
            readings.append(reading)

        return {
            "ratios": [r.model_dump() for r in readings],
            "btc_dominance": self.dominance(),
        }

    def dominance(self) -> dict[str, Any]:
        """True market-cap dominance, or an explicit UNAVAILABLE.

        An earlier version of this computed a "dominance proxy" by normalising
        BTC, ETH and SOL to a common start date and reporting each one's share
        of the resulting basket. That number was meaningless: it reported SOL
        at 69.6%, which is cumulative performance since 2020 rather than any
        kind of dominance. It has been removed rather than relabelled, because
        a misleading number with a careful caption is still a misleading
        number.

        Real dominance needs the market cap of every asset. The provider layer
        supplies it live via CoinGecko; there is no stored history, so
        historical dominance is honestly unavailable.
        """
        from ..db import repo

        try:
            observation = repo.latest_observation(Asset.BTC, "market.dominance")
        except Exception as exc:   # storage shape varies; never fail the caller
            log.debug("dominance_lookup_failed", error=str(exc))
            observation = None

        if observation is None:
            return {
                "available": False,
                "status": "UNAVAILABLE",
                "reason": (
                    "BTC dominance requires the market cap of every cryptoasset. It is "
                    "fetched live from CoinGecko during a pipeline run and is not stored "
                    "historically, so no value is available here and none is estimated."
                ),
            }
        return {
            "available": True,
            "btc_dominance_pct": observation.value,
            "as_of": observation.timestamp.isoformat() if observation.timestamp else None,
            "freshness": getattr(observation.freshness, "value", str(observation.freshness)),
            "note": (
                "Point-in-time dominance history is not stored, so this value cannot be "
                "used in a backtest."
            ),
        }


class CryptoBreadthEngine:
    """How much of the set is participating, not how far it moved."""

    def assess(self, as_of: datetime | None = None) -> BreadthAssessment:
        out = BreadthAssessment()
        per_asset: dict[str, Any] = {}
        above_50 = above_200 = positive_30 = measured = 0

        for asset in Asset.tradables():
            closes = _daily_closes(asset)
            if as_of is not None and not closes.empty:
                closes = closes[closes.index <= as_of]
            if closes.empty or len(closes) < 200:
                per_asset[asset.value] = {"available": False, "reason": "insufficient history"}
                continue

            measured += 1
            ema50 = closes.ewm(span=50, adjust=False).mean().iloc[-1]
            ema200 = closes.ewm(span=200, adjust=False).mean().iloc[-1]
            last = float(closes.iloc[-1])
            change_30d = float((closes.iloc[-1] / closes.iloc[-31] - 1) * 100)

            # Explicit bool(): numpy comparisons return numpy.bool_, which
            # pydantic cannot serialise to JSON.
            is_above_50 = bool(last > ema50)
            is_above_200 = bool(last > ema200)
            above_50 += int(is_above_50)
            above_200 += int(is_above_200)
            positive_30 += int(change_30d > 0)

            per_asset[asset.value] = {
                "available": True,
                "above_ema50": is_above_50,
                "above_ema200": is_above_200,
                "change_30d_pct": round(change_30d, 2),
            }

        out.per_asset = per_asset
        out.assets_measured = measured
        out.assets_above_ema50 = above_50
        out.assets_above_ema200 = above_200
        out.positive_30d = positive_30

        if measured == 0:
            out.interpretation = "no asset had enough history to measure breadth"
            return out

        out.score = round((above_50 + above_200 + positive_30) / (measured * 3) * 100, 1)
        if out.score >= 80:
            out.state = "BROAD_PARTICIPATION"
        elif out.score >= 55:
            out.state = "MIXED_POSITIVE"
        elif out.score >= 30:
            out.state = "MIXED_NEGATIVE"
        else:
            out.state = "NARROW"

        out.interpretation = (
            f"{above_50}/{measured} above their 50-day EMA, {above_200}/{measured} above "
            f"their 200-day EMA, {positive_30}/{measured} positive over 30 days: breadth "
            f"{out.state} ({out.score:.0f}/100). "
            "Measured across three assets only, which is far too narrow to represent the "
            "whole market - treat it as participation within this watchlist."
        )
        return out


class LiquidityRegimeEngine:
    """Financial conditions, from the macro series actually held.

    Deliberately built from what exists rather than from the ideal list. Every
    absent component is named in `missing` instead of being silently treated as
    neutral, which would tilt the regime toward NEUTRAL by construction.
    """

    def assess(self, as_of: datetime | None = None) -> LiquidityAssessment:
        out = LiquidityAssessment()
        components: dict[str, Any] = {}
        votes: list[float] = []

        def trend_vote(metric: str, label: str, easing_when_falling: bool) -> None:
            series = _normalise_index(store.load_macro(metric))
            if as_of is not None and not series.empty:
                series = series[series.index <= pd.Timestamp(as_of).tz_convert(UTC).normalize()]
            if series.empty or len(series) < 90:
                out.missing.append(label)
                return
            change = float((series.iloc[-1] / series.iloc[-64] - 1) * 100)
            # A falling dollar or falling yields loosen conditions; a falling
            # VIX does too. The direction of "easing" differs per series.
            vote = -change if easing_when_falling else change
            components[label] = {
                "change_3m_pct": round(change, 2),
                "direction": "easing" if vote > 0 else "tightening",
            }
            votes.append(np.clip(vote, -20, 20))

        trend_vote("macro.dxy", "US dollar", easing_when_falling=True)
        trend_vote("macro.us10y_yahoo", "10Y yield", easing_when_falling=True)
        trend_vote("macro.vix", "VIX", easing_when_falling=True)
        trend_vote("macro.nasdaq", "Nasdaq", easing_when_falling=False)

        # Stablecoin supply is the crypto-native liquidity measure; include it
        # when the history is there.
        stables = _normalise_index(store.load_macro("stablecoin.total_supply"))
        if not stables.empty and len(stables) >= 90:
            change = float((stables.iloc[-1] / stables.iloc[-64] - 1) * 100)
            components["stablecoin supply"] = {
                "change_3m_pct": round(change, 2),
                "direction": "easing" if change > 0 else "tightening",
            }
            votes.append(float(np.clip(change * 2, -20, 20)))
        else:
            out.missing.append("stablecoin supply")

        if not votes:
            out.interpretation = (
                "no macro series had enough history; liquidity regime is UNKNOWN, "
                "which is not the same as neutral"
            )
            return out

        out.components = components
        out.score = round(float(np.mean(votes)), 2)
        if out.score > 2.0:
            out.regime = LiquidityRegime.EXPANSION
        elif out.score < -2.0:
            out.regime = LiquidityRegime.CONTRACTION
        else:
            out.regime = LiquidityRegime.NEUTRAL

        easing = [k for k, v in components.items() if v["direction"] == "easing"]
        tightening = [k for k, v in components.items() if v["direction"] == "tightening"]
        out.interpretation = (
            f"Liquidity regime {out.regime.value} (score {out.score:+.1f}). "
            + (f"Easing: {', '.join(easing)}. " if easing else "")
            + (f"Tightening: {', '.join(tightening)}. " if tightening else "")
            + "This describes financial conditions, not a crypto forecast."
        )
        if out.missing:
            out.interpretation += f" Not included: {', '.join(out.missing)}."
        return out

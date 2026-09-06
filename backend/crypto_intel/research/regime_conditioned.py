"""Regime-conditioned signal studies.

A signal can help in a bull market and hurt in a bear market. Measuring it
unconditionally averages those two opposite behaviours into a number that
describes neither.

This module re-runs signal studies inside each market regime, and reports the
sample size per cell so a result computed on 40 days is never presented like
one computed on 800.

Regimes are RECONSTRUCTED historically from causal indicators only, so the
regime label at day t uses nothing after t.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from ..core.enums import Asset
from ..engines.technical import indicators as ind
from ..logging_setup import get_logger
from .derivatives_study import daily_funding, trailing_rank
from .etf_study import build_price_frame
from .stats import benjamini_hochberg, describe_returns, forward_returns

log = get_logger("research.regime_conditioned")

HORIZONS = [1, 3, 7, 14, 30]

REGIME_LABELS = ["STRONGLY_BEARISH", "BEARISH", "NEUTRAL", "BULLISH", "STRONGLY_BULLISH"]
CONDITION_LABELS = ["TREND", "RANGE", "HIGH_VOL", "LOW_VOL"]


def reconstruct_regime(df: pd.DataFrame) -> pd.Series:
    """Historical regime label per day, from causal indicators only.

    Mirrors the live MarketRegimeEngine's directional axis using the components
    that exist over the full history (trend, structure, position vs EMA200,
    momentum). Domains that only exist recently - ETF flows, stablecoin
    liquidity - are deliberately excluded so the label is comparable across the
    whole period.
    """
    close, high, low = df["close"], df["high"], df["low"]
    ema20, ema50, ema200 = ind.ema(close, 20), ind.ema(close, 50), ind.ema(close, 200)
    adx = ind.adx(high, low, close, 14)
    rsi = ind.rsi(close, 14)

    score = pd.Series(0.0, index=df.index)
    # Trend alignment, weighted as in the live engine.
    score += np.where((close > ema20) & (ema20 > ema50), 30.0, 0.0)
    score += np.where((close < ema20) & (ema20 < ema50), -30.0, 0.0)
    score += np.where(close > ema200, 25.0, -25.0)
    score += ((close - ema200) / close * 100.0).clip(-25, 25)
    score += ((rsi - 50.0) * 0.5).clip(-15, 15)
    # A trend only counts when there is one: ADX gates the directional vote.
    score += np.where(adx > 25, np.sign(close - ema50) * 15.0, 0.0)

    score = score.clip(-100, 100)

    labels = pd.Series(index=df.index, dtype=object)
    labels[score >= 55] = "STRONGLY_BULLISH"
    labels[(score >= 20) & (score < 55)] = "BULLISH"
    labels[(score > -20) & (score < 20)] = "NEUTRAL"
    labels[(score > -55) & (score <= -20)] = "BEARISH"
    labels[score <= -55] = "STRONGLY_BEARISH"
    return labels


def reconstruct_conditions(df: pd.DataFrame) -> pd.DataFrame:
    """Boolean market-character flags, independent of direction."""
    close, high, low = df["close"], df["high"], df["low"]
    adx = ind.adx(high, low, close, 14)
    atr_pct = ind.atr_percent(high, low, close, 14)
    atr_rank = trailing_rank(atr_pct)

    flags = pd.DataFrame(index=df.index)
    flags["TREND"] = adx > 25
    flags["RANGE"] = adx <= 20
    flags["HIGH_VOL"] = atr_rank >= 80
    flags["LOW_VOL"] = atr_rank <= 20
    return flags


def build_signals(asset: Asset, df: pd.DataFrame) -> dict[str, pd.Series]:
    """The signals worth conditioning - the ones the audit flagged as live."""
    close, volume = df["close"], df["volume"]
    rsi = ind.rsi(close, 14)
    ema20, ema50 = ind.ema(close, 20), ind.ema(close, 50)

    signals: dict[str, pd.Series] = {
        "rsi_overbought": (rsi >= 70).astype(float),
        "rsi_oversold": (rsi <= 30).astype(float),
        "rsi_extreme_overbought": (rsi >= 80).astype(float),
        "price_above_ema50": (close > ema50).astype(float),
        "ema20_above_ema50": (ema20 > ema50).astype(float),
        "volume_spike": (ind.relative_volume(volume, 20) > 2.0).astype(float),
    }

    funding = daily_funding(asset, df.index)
    if not funding.dropna().empty:
        ranks = trailing_rank(funding)
        signals["funding_p95"] = (ranks >= 95).astype(float)
        signals["funding_p5"] = (ranks <= 5).astype(float)

    return signals


def analyse_signal_by_regime(
    asset: Asset, signal_name: str, min_sample: int = 30, horizon: int = 7
) -> dict[str, Any]:
    """One signal, measured separately inside each regime."""
    df = build_price_frame(asset)
    if df.empty:
        return {
            "asset": asset.value, "signal": signal_name, "available": False,
            "reason": "UNAVAILABLE - no price history",
        }

    signals = build_signals(asset, df)
    if signal_name not in signals:
        return {
            "asset": asset.value, "signal": signal_name, "available": False,
            "reason": f"Unknown signal '{signal_name}'",
        }

    signal = signals[signal_name]
    regimes = reconstruct_regime(df)
    fwd = forward_returns(df["close"], [horizon])
    target = fwd[f"fwd_{horizon}"]

    observable = signal.dropna().index
    cells: dict[str, Any] = {}
    flat_p: list[float | None] = []
    flat_keys: list[str] = []

    for regime in REGIME_LABELS:
        in_regime = regimes[regimes == regime].index
        active = signal[(signal > 0.5) & signal.index.isin(in_regime)].index
        active = active[active.isin(observable)]

        # Baseline: the same regime WITHOUT the signal. That is the comparison
        # that isolates the signal from the regime it sits in.
        inactive = signal[(signal <= 0.5) & signal.index.isin(in_regime)].index
        inactive = inactive[inactive.isin(observable)]

        cell: dict[str, Any] = {"regime": regime, "n": len(active), "n_baseline": len(inactive)}
        if len(active) < min_sample or len(inactive) < min_sample:
            cell["available"] = False
            cell["reason"] = (
                f"INSUFFICIENT_DATA - {len(active)} signal days, "
                f"{len(inactive)} comparison days in this regime"
            )
            cells[regime] = cell
            continue

        stats = describe_returns(target.loc[target.index.isin(active)])
        baseline = describe_returns(target.loc[target.index.isin(inactive)])
        edge = (
            round(stats.mean - baseline.mean, 4)
            if stats.mean is not None and baseline.mean is not None else None
        )

        cell["available"] = True
        cell["signal"] = stats.to_dict()
        cell["regime_baseline"] = baseline.to_dict()
        cell["edge_vs_regime"] = edge
        cells[regime] = cell
        flat_p.append(stats.p_value)
        flat_keys.append(regime)

    survives = benjamini_hochberg(flat_p, alpha=0.05)
    for regime, passed in zip(flat_keys, survives, strict=True):
        cells[regime]["significant_fdr"] = bool(passed)

    return {
        "asset": asset.value,
        "signal": signal_name,
        "horizon": f"{horizon}d",
        "available": True,
        "by_regime": cells,
        "interpretation": _interpret_regime_split(signal_name, cells),
    }


def _interpret_regime_split(signal_name: str, cells: dict[str, Any]) -> dict[str, Any]:
    """Does this signal behave differently depending on the regime?"""
    usable = {
        regime: cell for regime, cell in cells.items()
        if cell.get("available") and cell.get("edge_vs_regime") is not None
    }

    if len(usable) == 0:
        return {
            "regime_dependent": False,
            "conclusion": "INSUFFICIENT_DATA - no regime has enough observations",
        }

    if len(usable) == 1:
        # Not a failure: a signal that only ever fires in one regime IS regime
        # dependent, by construction. Saying INSUFFICIENT_DATA here would hide a
        # solid result - RSI >= 70 occurs almost exclusively in strong uptrends,
        # and that concentration is itself the finding.
        regime, cell = next(iter(usable.items()))
        edge = cell["edge_vs_regime"]
        supported = " (survives FDR correction)" if cell.get("significant_fdr") else ""
        direction = "outperformance" if edge > 0 else "underperformance"
        return {
            "regime_dependent": True,
            "single_regime": regime,
            "positive_in": [regime] if edge > 0 else [],
            "negative_in": [regime] if edge < 0 else [],
            "conclusion": (
                f"'{signal_name}' occurs almost exclusively in {regime} "
                f"(n={cell['n']}), where it precedes {direction} of "
                f"{edge:+.2f}pp versus other days in the same regime{supported}. "
                "It cannot be compared across regimes because it barely occurs "
                "in the others - which is itself a property of the signal."
            ),
        }

    edges = {regime: cell["edge_vs_regime"] for regime, cell in usable.items()}
    positive = [r for r, e in edges.items() if e > 0.3]
    negative = [r for r, e in edges.items() if e < -0.3]

    if positive and negative:
        return {
            "regime_dependent": True,
            "positive_in": positive,
            "negative_in": negative,
            "conclusion": (
                f"'{signal_name}' flips sign with the regime: edge is positive in "
                f"{', '.join(positive)} and negative in {', '.join(negative)}. "
                "Interpreting it identically in both contexts would be wrong."
            ),
        }

    spread = max(edges.values()) - min(edges.values())
    if spread > 2.0:
        return {
            "regime_dependent": True,
            "conclusion": (
                f"'{signal_name}' keeps the same direction across regimes but its size "
                f"varies by {spread:.2f} percentage points - the regime changes how much "
                "it matters, not whether it matters."
            ),
        }

    return {
        "regime_dependent": False,
        "conclusion": (
            f"'{signal_name}' behaves consistently across the regimes with enough data "
            f"(edge spread {spread:.2f}pp)."
        ),
    }


def analyse_all_signals(asset: Asset, horizon: int = 7) -> dict[str, Any]:
    df = build_price_frame(asset)
    if df.empty:
        return {"asset": asset.value, "available": False, "reason": "UNAVAILABLE - no prices"}

    names = list(build_signals(asset, df))
    results = {
        name: analyse_signal_by_regime(asset, name, horizon=horizon) for name in names
    }
    regimes = reconstruct_regime(df)

    return {
        "asset": asset.value,
        "available": True,
        "horizon": f"{horizon}d",
        "regime_distribution": {
            regime: int((regimes == regime).sum()) for regime in REGIME_LABELS
        },
        "signals": results,
        "regime_dependent_signals": [
            name for name, r in results.items()
            if r.get("available") and r["interpretation"].get("regime_dependent")
        ],
        "note": (
            "Each signal is compared against days in THE SAME regime where the signal "
            "is absent, which isolates the signal from the regime it occurs in. "
            "Regimes are reconstructed from causal indicators only."
        ),
    }


def run_all(assets: list[Asset] | None = None, horizon: int = 7) -> dict[str, Any]:
    assets = assets or Asset.tradables()
    return {a.value: analyse_all_signals(a, horizon) for a in assets}

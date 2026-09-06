"""Baseline models: what a signal has to beat before it means anything.

Any strategy evaluated in isolation looks impressive in a market that rose
tenfold. The only meaningful question is whether it beats the trivial
alternatives, so this module implements the trivial alternatives explicitly
and reports them alongside every result.

The most important baseline is buy-and-hold. If a signal cannot beat holding
the asset, it does not matter that its returns are positive or that its
p-value is small.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd

from ..core.enums import Asset, Timeframe
from ..history import store
from ..logging_setup import get_logger
from .stats import MIN_RELIABLE_SAMPLE

log = get_logger("research.baselines")

HORIZONS = [1, 7, 30]


def _closes(asset: Asset) -> pd.Series:
    df = store.load_candles(asset, Timeframe.D1)
    return df["close"] if not df.empty else pd.Series(dtype=float)


def _summarise(signal: pd.Series, forward: pd.Series, name: str, horizon: int) -> dict[str, Any]:
    """Mean forward return on days the signal is active."""
    aligned = pd.concat(
        [signal.rename("signal"), forward.rename("forward")], axis=1
    ).dropna()
    active = aligned[aligned["signal"] > 0]["forward"]
    inactive = aligned[aligned["signal"] <= 0]["forward"]

    result: dict[str, Any] = {
        "baseline": name,
        "horizon_days": horizon,
        "days_active": len(active),
        "days_inactive": len(inactive),
        "coverage_pct": round(len(active) / len(aligned) * 100, 1) if len(aligned) else 0.0,
        "mean_return_pct": round(float(active.mean()), 4) if len(active) else None,
        "median_return_pct": round(float(active.median()), 4) if len(active) else None,
        "win_rate": round(float((active > 0).mean() * 100), 2) if len(active) else None,
        "reliable": len(active) >= MIN_RELIABLE_SAMPLE,
    }
    if len(active) and len(inactive):
        result["mean_when_inactive_pct"] = round(float(inactive.mean()), 4)
        result["spread_pct"] = round(float(active.mean() - inactive.mean()), 4)
    return result


def build_baselines(asset: Asset) -> dict[str, pd.Series]:
    """The trivial strategies, each as a 0/1 daily signal."""
    closes = _closes(asset)
    if closes.empty:
        return {}

    rng = np.random.default_rng(42)   # fixed so the random baseline is reproducible
    ema50 = closes.ewm(span=50, adjust=False).mean()
    ema200 = closes.ewm(span=200, adjust=False).mean()
    daily_return = closes.pct_change()

    return {
        # Always in the market: the buy-and-hold benchmark.
        "always_long": pd.Series(1.0, index=closes.index),
        # Never in the market: the do-nothing benchmark.
        "never_long": pd.Series(0.0, index=closes.index),
        # Coin flip, fixed seed. A signal must beat this to be worth anything.
        "random": pd.Series(rng.integers(0, 2, size=len(closes)).astype(float), index=closes.index),
        # Trend following, the simplest non-trivial rule.
        "ema_trend": (closes > ema200).astype(float),
        "ema_cross": (ema50 > ema200).astype(float),
        # Momentum: was the last 30 days positive?
        "momentum_30d": (closes.pct_change(30) > 0).astype(float),
        # Yesterday's sign, the weakest possible autocorrelation bet.
        "previous_return_positive": (daily_return.shift(1) > 0).astype(float),
    }


def evaluate(asset: Asset, horizons: list[int] | None = None) -> dict[str, Any]:
    horizons = horizons or HORIZONS
    closes = _closes(asset)
    if closes.empty or len(closes) < 250:
        return {"asset": asset.value, "status": "INSUFFICIENT_DATA", "bars": len(closes)}

    signals = build_baselines(asset)
    results: dict[str, Any] = {}
    for horizon in horizons:
        forward = (closes.shift(-horizon) - closes) / closes * 100.0
        results[f"{horizon}d"] = [
            _summarise(signal, forward, name, horizon) for name, signal in signals.items()
        ]

    # Buy-and-hold is the number every other result must be read against.
    hold = {
        h: next(
            (r for r in rows if r["baseline"] == "always_long"), None
        ) for h, rows in results.items()
    }
    return {
        "asset": asset.value,
        "status": "OK",
        "period": {"start": str(closes.index.min())[:10], "end": str(closes.index.max())[:10]},
        "observations": len(closes),
        "by_horizon": results,
        "buy_and_hold": {h: (v or {}).get("mean_return_pct") for h, v in hold.items()},
        "note": (
            "Any signal claiming an edge must be compared against these numbers, not "
            "against zero. In a market that rose over the sample, beating zero is "
            "automatic and meaningless."
        ),
    }


def compare_against_baselines(
    asset: Asset, signal_mean_pct: float, horizon: int, signal_name: str = "signal"
) -> dict[str, Any]:
    """Where does a candidate signal sit against the trivial alternatives?"""
    baselines = evaluate(asset, [horizon])
    if baselines.get("status") != "OK":
        return {"status": baselines.get("status"), "asset": asset.value}

    rows = baselines["by_horizon"][f"{horizon}d"]
    beaten = [
        r["baseline"] for r in rows
        if r["mean_return_pct"] is not None and signal_mean_pct > r["mean_return_pct"]
    ]
    lost_to = [
        r["baseline"] for r in rows
        if r["mean_return_pct"] is not None and signal_mean_pct <= r["mean_return_pct"]
    ]
    hold_mean = baselines["buy_and_hold"].get(f"{horizon}d")

    return {
        "asset": asset.value,
        "signal": signal_name,
        "horizon_days": horizon,
        "signal_mean_pct": signal_mean_pct,
        "buy_and_hold_mean_pct": hold_mean,
        "excess_over_buy_and_hold_pct": (
            round(signal_mean_pct - hold_mean, 4) if hold_mean is not None else None
        ),
        "baselines_beaten": beaten,
        "baselines_not_beaten": lost_to,
        "verdict": (
            "BEATS_BUY_AND_HOLD"
            if hold_mean is not None and signal_mean_pct > hold_mean
            else "DOES_NOT_BEAT_BUY_AND_HOLD"
        ),
        "note": (
            "Beating buy-and-hold on average return still ignores that the signal is "
            "only active part of the time; compare coverage before drawing conclusions."
        ),
    }


def run_all(assets: list[Asset] | None = None) -> dict[str, Any]:
    assets = assets or Asset.tradables()
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "assets": {a.value: evaluate(a) for a in assets},
    }

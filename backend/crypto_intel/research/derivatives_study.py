"""Derivatives study: percentile thresholds and price x OI x funding states.

The LOT 2 audit showed the derivatives score sitting in the 'neutral' bucket on
97-99% of days. Fixed thresholds are the cause: 0.0025 per 8h is a reasonable
"extreme" for BTC and almost unreachable for SOL, so one number cannot serve
three assets.

This module replaces them with trailing percentiles computed per asset, then
measures the combined price/OI/funding states the brief asks about - without
assuming in advance that any of them is dangerous.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from ..core.enums import Asset
from ..history import store
from ..logging_setup import get_logger
from .etf_study import build_price_frame
from .stats import benjamini_hochberg, describe_returns, forward_returns
from .walkforward import walk_forward_ic

log = get_logger("research.derivatives")

HORIZONS = [1, 3, 7, 14, 30]
TRAILING_WINDOW = 252

# Percentile bands. The tails are narrow on purpose: "extreme" should be rare.
PERCENTILE_BANDS: list[tuple[str, float, float]] = [
    ("p0_5", 0.0, 5.0),
    ("p5_20", 5.0, 20.0),
    ("p20_80", 20.0, 80.0),
    ("p80_95", 80.0, 95.0),
    ("p95_100", 95.0, 100.01),
]


def trailing_rank(series: pd.Series, window: int = TRAILING_WINDOW) -> pd.Series:
    """Percentile rank of each value within its own trailing window.

    Computed on the dense series so missing days cannot drag every observation
    into the bottom band.
    """
    dense = series.dropna()
    if dense.empty:
        return pd.Series(index=series.index, dtype=float)
    ranks = dense.rolling(window, min_periods=60).apply(
        lambda w: float((w[-1] > w[:-1]).sum()) / max(1, len(w) - 1) * 100.0, raw=True
    )
    return ranks.reindex(series.index)


def daily_funding(asset: Asset, index: pd.DatetimeIndex) -> pd.Series:
    funding = store.load_derivatives(asset, "funding.rate")
    if funding.empty:
        return pd.Series(index=index, dtype=float)
    daily = funding.resample("1D").mean()
    daily.index = (
        daily.index.tz_convert("UTC") if daily.index.tz else daily.index.tz_localize("UTC")
    )
    return daily.reindex(index)


# Open interest is stored under two metrics with different units: the live
# scheduler writes notional USD to "oi.value", while the historical backfill
# writes Bybit contract counts to "oi.contracts_bybit". They are never spliced
# into one series - a level jump at the join would read as a real change in
# positioning. The longer of the two is used and named in the result.
OI_METRICS = ("oi.contracts_bybit", "oi.value")


def open_interest_source(asset: Asset) -> tuple[str, pd.DataFrame]:
    """The longest available open-interest series and the metric it came from."""
    best_metric, best_frame = "", pd.DataFrame()
    for metric in OI_METRICS:
        frame = store.load_derivatives(asset, metric)
        if len(frame) > len(best_frame):
            best_metric, best_frame = metric, frame
    return best_metric, best_frame


def daily_open_interest(asset: Asset, index: pd.DatetimeIndex) -> pd.Series:
    _, oi = open_interest_source(asset)
    if oi.empty:
        return pd.Series(index=index, dtype=float)
    daily = oi.resample("1D").mean()
    daily.index = (
        daily.index.tz_convert("UTC") if daily.index.tz else daily.index.tz_localize("UTC")
    )
    return daily.reindex(index)


def analyse_percentile_bands(asset: Asset, min_sample: int = 25) -> dict[str, Any]:
    """Forward returns per funding percentile band, measured per asset.

    Also reports how the fixed thresholds currently in `thresholds.yaml` map
    onto this asset's actual distribution - which is what exposes why the
    derivatives score never fires.
    """
    prices = build_price_frame(asset)
    if prices.empty:
        return {
            "asset": asset.value, "available": False,
            "reason": "UNAVAILABLE - no price history",
        }

    funding = daily_funding(asset, prices.index)
    if funding.dropna().empty:
        return {
            "asset": asset.value, "available": False,
            "reason": f"UNAVAILABLE - no funding history for {asset.value}",
        }

    ranks = trailing_rank(funding)
    fwd = forward_returns(prices["close"], HORIZONS)
    observable = funding.dropna().index
    window_start, window_end = observable.min(), observable.max()
    baseline_index = fwd.index[(fwd.index >= window_start) & (fwd.index <= window_end)]

    bands: dict[str, Any] = {}
    flat_p: list[float | None] = []
    flat_keys: list[tuple[str, str]] = []

    for name, low, high in PERCENTILE_BANDS:
        mask = (ranks >= low) & (ranks < high)
        dates = ranks[mask].index
        entry: dict[str, Any] = {"band": name, "percentile_range": [low, high], "n": len(dates)}

        if len(dates) >= min_sample:
            values = funding[mask].dropna()
            entry["funding_range"] = [
                round(float(values.min()), 8), round(float(values.max()), 8),
            ] if len(values) else None
            entry["available"] = True
            entry["horizons"] = {}
            for h in HORIZONS:
                subset = fwd.loc[fwd.index.isin(dates), f"fwd_{h}"]
                stats = describe_returns(subset)
                baseline = describe_returns(fwd.loc[baseline_index, f"fwd_{h}"])
                edge = (
                    round(stats.mean - baseline.mean, 4)
                    if stats.mean is not None and baseline.mean is not None else None
                )
                entry["horizons"][f"{h}d"] = {
                    **stats.to_dict(),
                    "baseline_mean": baseline.mean,
                    "edge_vs_baseline": edge,
                }
                flat_p.append(stats.p_value)
                flat_keys.append((name, f"{h}d"))
        else:
            entry["available"] = False
            entry["reason"] = f"INSUFFICIENT_DATA - {len(dates)} days"

        bands[name] = entry

    survives = benjamini_hochberg(flat_p, alpha=0.05)
    for (name, horizon), passed in zip(flat_keys, survives, strict=True):
        bands[name]["horizons"][horizon]["significant_fdr"] = bool(passed)

    return {
        "asset": asset.value,
        "available": True,
        "metric": "funding.rate",
        "period": {
            "start": window_start.isoformat(), "end": window_end.isoformat(),
            "days": len(observable),
        },
        "bands": bands,
        "distribution": _describe_distribution(funding),
        "current_threshold_mapping": _map_fixed_thresholds(asset, funding),
        "walk_forward": walk_forward_ic(ranks - 50.0, fwd["fwd_7"]),
    }


def _describe_distribution(series: pd.Series) -> dict[str, Any]:
    clean = series.dropna()
    if clean.empty:
        return {}
    return {
        "n": len(clean),
        "mean": round(float(clean.mean()), 8),
        "median": round(float(clean.median()), 8),
        "std": round(float(clean.std(ddof=1)), 8),
        "percentiles": {
            f"p{p}": round(float(np.percentile(clean, p)), 8)
            for p in (1, 5, 20, 50, 80, 95, 99)
        },
    }


def _map_fixed_thresholds(asset: Asset, funding: pd.Series) -> dict[str, Any]:
    """Where the current fixed thresholds sit in this asset's real distribution.

    This is the diagnostic that explains a 99%-neutral score: if the 'extreme'
    threshold sits at the 99.9th percentile for one asset, it will essentially
    never fire.
    """
    from ..config_loader import threshold

    config = threshold("derivatives", "funding", default={}) or {}
    clean = funding.dropna()
    if clean.empty:
        return {}

    mapping: dict[str, Any] = {}
    for key in ("neutral_abs", "elevated", "extreme", "extreme_negative"):
        value = config.get(key)
        if value is None:
            continue
        share_below = float((clean < value).mean() * 100.0)
        mapping[key] = {
            "threshold": value,
            "percentile_in_this_asset": round(share_below, 2),
            "days_beyond": int((clean >= value).sum()) if value > 0 else int((clean <= value).sum()),
        }

    extreme = config.get("extreme")
    if extreme is not None:
        share = float((clean >= extreme).mean() * 100.0)
        mapping["diagnosis"] = (
            f"The fixed 'extreme' threshold ({extreme}) is exceeded on {share:.2f}% of "
            f"{asset.value} days. "
            + (
                "That is why the derivatives score sits in 'neutral' almost always."
                if share < 2.0 else "The threshold fires often enough to discriminate."
            )
        )
    return mapping


def analyse_price_oi_funding(asset: Asset, min_sample: int = 20) -> dict[str, Any]:
    """The combined states the brief asks about, measured rather than assumed.

    "Price up + OI up + funding above p95" is widely described as dangerous.
    This measures whether it actually has been.
    """
    prices = build_price_frame(asset)
    if prices.empty:
        return {"asset": asset.value, "available": False, "reason": "UNAVAILABLE - no prices"}

    close = prices["close"]
    funding = daily_funding(asset, prices.index)
    oi = daily_open_interest(asset, prices.index)

    price_change = close.pct_change(1) * 100.0
    oi_change = oi.pct_change(1) * 100.0
    funding_rank = trailing_rank(funding)

    usable = pd.concat(
        [price_change.rename("price"), oi_change.rename("oi"), funding_rank.rename("frank")],
        axis=1,
    ).dropna()

    if len(usable) < 60:
        return {
            "asset": asset.value, "available": False,
            "reason": (
                f"INSUFFICIENT_DATA - only {len(usable)} days where price, open interest "
                "and funding all exist. Binance publishes roughly 30 days of open "
                "interest history, which caps this analysis."
            ),
            "limiting_factor": "open_interest_history",
        }

    fwd = forward_returns(close, HORIZONS)
    states: dict[str, Any] = {}

    price_up = usable["price"] > 0.3
    price_down = usable["price"] < -0.3
    oi_up = usable["oi"] > 0.5
    oi_down = usable["oi"] < -0.5

    combinations = {
        "price_up_oi_up": price_up & oi_up,
        "price_up_oi_down": price_up & oi_down,
        "price_down_oi_up": price_down & oi_up,
        "price_down_oi_down": price_down & oi_down,
    }

    funding_levels = {
        "funding_low": usable["frank"] < 20,
        "funding_normal": (usable["frank"] >= 20) & (usable["frank"] < 80),
        "funding_high": (usable["frank"] >= 80) & (usable["frank"] < 95),
        "funding_extreme": usable["frank"] >= 95,
    }

    for state_name, state_mask in combinations.items():
        dates = usable[state_mask].index
        entry: dict[str, Any] = {"n": len(dates), "horizons": {}, "by_funding": {}}
        if len(dates) >= min_sample:
            entry["available"] = True
            for h in HORIZONS:
                entry["horizons"][f"{h}d"] = describe_returns(
                    fwd.loc[fwd.index.isin(dates), f"fwd_{h}"]
                ).to_dict()
        else:
            entry["available"] = False
            entry["reason"] = f"INSUFFICIENT_DATA - {len(dates)} days"

        for funding_name, funding_mask in funding_levels.items():
            crossed = usable[state_mask & funding_mask].index
            cell: dict[str, Any] = {"n": len(crossed)}
            if len(crossed) >= min_sample:
                cell["available"] = True
                cell["return_7d"] = describe_returns(
                    fwd.loc[fwd.index.isin(crossed), "fwd_7"]
                ).to_dict()
            else:
                cell["available"] = False
                cell["reason"] = f"INSUFFICIENT_DATA - {len(crossed)} days"
            entry["by_funding"][funding_name] = cell

        states[state_name] = entry

    return {
        "asset": asset.value,
        "available": True,
        "period": {
            "start": usable.index.min().isoformat(),
            "end": usable.index.max().isoformat(),
            "days": len(usable),
        },
        "states": states,
        "caveat": (
            "Open-interest history from Binance covers roughly 30 days, so the "
            "price x OI combinations rest on a small and recent sample. Treat these "
            "as descriptive until a deeper OI history is imported."
        ),
    }


def suggest_thresholds(asset: Asset) -> dict[str, Any]:
    """Percentile-derived thresholds for this asset, as a documented proposal.

    Returned as a suggestion only. Nothing is written to config - changing
    thresholds stays a human decision.
    """
    prices = build_price_frame(asset)
    if prices.empty:
        return {"asset": asset.value, "available": False, "reason": "no prices"}

    funding = daily_funding(asset, prices.index).dropna()
    if funding.empty:
        return {"asset": asset.value, "available": False, "reason": "no funding history"}

    percentiles = {p: float(np.percentile(funding, p)) for p in (1, 5, 20, 50, 80, 95, 99)}
    return {
        "asset": asset.value,
        "available": True,
        "n": len(funding),
        "suggested": {
            "extreme_negative": round(percentiles[5], 8),
            "elevated_negative": round(percentiles[20], 8),
            "neutral_low": round(percentiles[20], 8),
            "neutral_high": round(percentiles[80], 8),
            "elevated": round(percentiles[80], 8),
            "extreme": round(percentiles[95], 8),
        },
        "percentiles": {f"p{k}": round(v, 8) for k, v in percentiles.items()},
        "rationale": (
            f"Derived from {asset.value}'s own trailing distribution. A percentile "
            "threshold fires on a predictable share of days by construction, which a "
            "fixed rate cannot do across assets with different funding regimes."
        ),
    }


def run_all(assets: list[Asset] | None = None) -> dict[str, Any]:
    assets = assets or Asset.tradables()
    return {
        a.value: {
            "percentile_bands": analyse_percentile_bands(a),
            "price_oi_funding": analyse_price_oi_funding(a),
            "suggested_thresholds": suggest_thresholds(a),
        }
        for a in assets
    }

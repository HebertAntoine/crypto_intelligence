"""Quantitative study: do ETF flows lead price?

The question the brief asks is specifically NOT "are flows and price correlated
today" - they trivially are, because both react to the same day's news. The
question is whether a flow observed on day t tells us anything about the return
from t to t+h.

So every measurement here joins a signal known at the CLOSE of day t to returns
that begin at t and end later. Nothing else is allowed to touch the signal.

Results are reported with sample size and significance, and negative results
are kept: discovering that a signal is useless is a real finding, and hiding it
would defeat the purpose of the exercise.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd

from ..core.enums import Asset, Timeframe
from ..db import repo
from ..history import store
from ..logging_setup import get_logger
from .stats import (
    BucketResult,
    benjamini_hochberg,
    chronological_split,
    describe_returns,
    forward_returns,
    lagged_correlation,
)

log = get_logger("research.etf")

HORIZONS_DAYS = [1, 2, 3, 5, 7, 14, 30]


def build_flow_series(asset: Asset, days: int = 4000) -> pd.Series:
    """Daily net ETF flow (all funds summed), in millions of USD."""
    rows = repo.get_etf_flows(asset, days=days)
    if not rows:
        return pd.Series(dtype=float)

    by_day: dict[pd.Timestamp, float] = defaultdict(float)
    for r in rows:
        day = pd.Timestamp(r["date"]).normalize().tz_convert("UTC") \
            if pd.Timestamp(r["date"]).tzinfo else pd.Timestamp(r["date"]).normalize().tz_localize("UTC")
        by_day[day] += float(r["flow_musd"])

    series = pd.Series(by_day).sort_index()
    series.name = "etf_net_flow"
    return series


def build_signals(flows: pd.Series) -> pd.DataFrame:
    """Every ETF-derived signal, each computed from PAST data only.

    Rolling windows use `.rolling(...)` which looks backwards by construction,
    so the value at day t uses days <= t. No `.shift(-n)` appears anywhere in
    this function - that is the whole point.
    """
    df = pd.DataFrame(index=flows.index)
    df["flow"] = flows
    df["ma3"] = flows.rolling(3, min_periods=3).mean()
    df["ma5"] = flows.rolling(5, min_periods=5).mean()
    df["ma7"] = flows.rolling(7, min_periods=7).mean()
    df["cum30"] = flows.rolling(30, min_periods=10).sum()

    # Acceleration: last 3 days vs the 3 before them.
    prior3 = flows.rolling(3, min_periods=3).mean().shift(3)
    df["acceleration"] = np.where(
        prior3.abs() > 1e-9, (df["ma3"] - prior3) / prior3.abs() * 100.0, np.nan
    )

    # Sign change of the 3-day average (a "reversal").
    sign = np.sign(df["ma3"])
    df["sign_flip"] = (sign != sign.shift(1)) & sign.notna() & sign.shift(1).notna()
    df["flip_to_positive"] = df["sign_flip"] & (sign > 0)
    df["flip_to_negative"] = df["sign_flip"] & (sign < 0)

    # Consecutive positive / negative days, counted backwards from each day.
    pos_streak, neg_streak = [], []
    p = n = 0
    for value in flows.to_numpy(dtype=float):
        if value > 0:
            p, n = p + 1, 0
        elif value < 0:
            p, n = 0, n + 1
        else:
            p = n = 0
        pos_streak.append(p)
        neg_streak.append(n)
    df["pos_streak"] = pos_streak
    df["neg_streak"] = neg_streak

    # Percentile rank of today's flow within the trailing year - scale-free,
    # so a "large" flow means large relative to recent history rather than
    # relative to an absolute figure that ages badly.
    df["flow_pct_rank"] = flows.rolling(252, min_periods=60).apply(
        lambda w: float((w[-1] > w[:-1]).sum()) / max(1, len(w) - 1) * 100.0, raw=True
    )
    return df


def build_price_frame(asset: Asset) -> pd.DataFrame:
    """Daily candles from the local history store, normalised to UTC days."""
    df = store.load_candles(asset, Timeframe.D1)
    if df.empty:
        return df
    df = df.copy()
    idx = pd.DatetimeIndex(df.index)
    idx = idx.tz_localize("UTC") if idx.tz is None else idx.tz_convert("UTC")
    df.index = idx.normalize()
    return df[~df.index.duplicated(keep="last")]


def run_lag_study(asset: Asset, min_overlap: int = 60) -> dict[str, Any]:
    """Correlate each ETF signal with FUTURE returns at several horizons."""
    flows = build_flow_series(asset)
    prices = build_price_frame(asset)

    if flows.empty:
        return {
            "asset": asset.value, "available": False,
            "reason": f"UNAVAILABLE - no ETF flow data for {asset.value}",
        }
    if prices.empty:
        return {
            "asset": asset.value, "available": False,
            "reason": "UNAVAILABLE - no daily candles; run `make backfill` first",
        }

    signals = build_signals(flows)
    close = prices["close"]
    fwd = forward_returns(close, HORIZONS_DAYS)

    joined = signals.join(fwd, how="inner")
    if len(joined) < min_overlap:
        return {
            "asset": asset.value, "available": False,
            "reason": (
                f"INCONCLUSIVE - only {len(joined)} overlapping days between ETF flows "
                f"and price history (need {min_overlap})"
            ),
        }

    signal_columns = ["flow", "ma3", "ma5", "ma7", "cum30", "acceleration",
                      "pos_streak", "neg_streak", "flow_pct_rank"]

    results: dict[str, Any] = {}
    flat_p: list[float | None] = []
    flat_keys: list[tuple[str, str]] = []

    for name in signal_columns:
        per_horizon = {}
        for h in HORIZONS_DAYS:
            r, p, n = lagged_correlation(joined[name], joined[f"fwd_{h}"])
            per_horizon[f"{h}d"] = {
                "spearman_r": r, "p_value": p, "n": n,
                "significant_raw": bool(p is not None and p < 0.05 and n >= 30),
            }
            flat_p.append(p if n >= 30 else None)
            flat_keys.append((name, f"{h}d"))
        results[name] = per_horizon

    # This grid is 9 signals x 7 horizons = 63 hypotheses. Without correction,
    # ~3 of them would clear p<0.05 by chance alone, so the headline
    # "significant" flag is the FDR-corrected one.
    survives = benjamini_hochberg(flat_p, alpha=0.05)
    n_raw = 0
    n_corrected = 0
    for (name, horizon), passed in zip(flat_keys, survives, strict=True):
        cell = results[name][horizon]
        cell["significant"] = bool(passed)
        n_raw += int(cell["significant_raw"])
        n_corrected += int(passed)

    # Contemporaneous correlation, computed on purpose as a CONTROL: if the
    # same-day figure is strong but every forward horizon is flat, the signal
    # reacts to price rather than leading it. That distinction is the point.
    same_day_return = (close - close.shift(1)) / close.shift(1) * 100.0
    control = {}
    for name in ("flow", "ma3"):
        r, p, n = lagged_correlation(joined[name], same_day_return.reindex(joined.index))
        control[name] = {"spearman_r": r, "p_value": p, "n": n}

    split = chronological_split(joined.index)

    return {
        "asset": asset.value,
        "available": True,
        "period": {
            "start": joined.index.min().isoformat(),
            "end": joined.index.max().isoformat(),
            "days": len(joined),
        },
        "correlations": results,
        "contemporaneous_control": control,
        "split": split.to_dict(),
        "multiple_testing": {
            "hypotheses": len(flat_keys),
            "significant_raw": n_raw,
            "significant_after_fdr": n_corrected,
            "expected_false_positives_uncorrected": round(len(flat_keys) * 0.05, 1),
            "method": "Benjamini-Hochberg FDR at alpha=0.05",
        },
        "note": (
            "Spearman correlation between a signal known at the close of day t and "
            "the return from t to t+h. The contemporaneous control measures the "
            "same-day relationship: a strong control with flat forward horizons "
            "means the flow follows price rather than leading it. "
            "The `significant` flag is corrected for multiple comparisons; "
            "`significant_raw` is the uncorrected p<0.05 test and will over-report."
        ),
    }


def run_bucket_study(
    asset: Asset, signal: str = "ma5", n_buckets: int = 5
) -> dict[str, Any]:
    """Split a signal into quantile buckets and describe forward returns in each.

    More informative than a single correlation: a signal can be useless on
    average yet meaningful at its extremes, and quantiles reveal that where a
    correlation coefficient hides it.
    """
    flows = build_flow_series(asset)
    prices = build_price_frame(asset)
    if flows.empty or prices.empty:
        return {"asset": asset.value, "available": False, "reason": "UNAVAILABLE - missing data"}

    signals = build_signals(flows)
    if signal not in signals.columns:
        return {"asset": asset.value, "available": False, "reason": f"unknown signal '{signal}'"}

    fwd = forward_returns(prices["close"], HORIZONS_DAYS)
    joined = signals[[signal]].join(fwd, how="inner").dropna(subset=[signal])
    if len(joined) < 50:
        return {
            "asset": asset.value, "available": False,
            "reason": f"INCONCLUSIVE - only {len(joined)} usable days",
        }

    try:
        labels = [f"Q{i + 1}" for i in range(n_buckets)]
        joined["bucket"] = pd.qcut(joined[signal], n_buckets, labels=labels, duplicates="drop")
    except ValueError:
        return {
            "asset": asset.value, "available": False,
            "reason": f"Signal '{signal}' has too few distinct values to bucket",
        }

    buckets: list[dict[str, Any]] = []
    for label in joined["bucket"].cat.categories:
        subset = joined[joined["bucket"] == label]
        result = BucketResult(
            label=str(label),
            lower=round(float(subset[signal].min()), 3),
            upper=round(float(subset[signal].max()), 3),
        )
        for h in HORIZONS_DAYS:
            result.stats[f"{h}d"] = describe_returns(subset[f"fwd_{h}"])
        buckets.append(result.to_dict())

    return {
        "asset": asset.value, "available": True, "signal": signal,
        "buckets": buckets,
        "period": {
            "start": joined.index.min().isoformat(),
            "end": joined.index.max().isoformat(),
            "days": len(joined),
        },
    }


def run_split_validation(asset: Asset, signal: str = "ma5", horizon: int = 7) -> dict[str, Any]:
    """Measure a signal on train / validation / out-of-sample separately.

    A relationship that only exists in the training window is an artefact. This
    is the guard against fitting the whole history and then "testing" on it.
    """
    flows = build_flow_series(asset)
    prices = build_price_frame(asset)
    if flows.empty or prices.empty:
        return {"asset": asset.value, "available": False, "reason": "UNAVAILABLE - missing data"}

    signals = build_signals(flows)
    fwd = forward_returns(prices["close"], [horizon])
    joined = signals[[signal]].join(fwd, how="inner").dropna()
    if len(joined) < 90:
        return {
            "asset": asset.value, "available": False,
            "reason": f"INCONCLUSIVE - {len(joined)} points, too few to split",
        }

    split = chronological_split(joined.index)
    out: dict[str, Any] = {
        "asset": asset.value, "available": True, "signal": signal,
        "horizon": f"{horizon}d", "split": split.to_dict(), "windows": {},
    }

    for name, window in (
        ("train", split.train), ("validation", split.validation), ("oos", split.oos)
    ):
        if window is None:
            continue
        subset = joined[(joined.index >= window[0]) & (joined.index <= window[1])]
        r, p, n = lagged_correlation(subset[signal], subset[f"fwd_{horizon}"])
        out["windows"][name] = {
            "start": window[0].isoformat(), "end": window[1].isoformat(),
            "n": n, "spearman_r": r, "p_value": p,
            "significant": bool(p is not None and p < 0.05 and n >= 30),
        }

    windows = out["windows"]
    signs = [
        np.sign(w["spearman_r"]) for w in windows.values()
        if w.get("spearman_r") is not None
    ]
    out["stable_sign"] = bool(len(set(signs)) == 1) if signs else False
    out["interpretation"] = (
        "Correlation keeps the same sign across all windows - the relationship is "
        "at least directionally stable."
        if out["stable_sign"]
        else "Correlation changes sign between windows - the relationship is NOT stable "
             "and should not be treated as predictive."
    )
    return out


def persist_results(study: str, asset: Asset, payload: dict[str, Any]) -> int:
    """Store study output so the API and reports can read it without recomputing."""
    from ..db.base import ResearchResultRow
    from ..db.session import session_scope

    if not payload.get("available"):
        return 0

    written = 0
    now = datetime.now(UTC)
    period = payload.get("period") or {}
    start = pd.Timestamp(period["start"]).to_pydatetime() if period.get("start") else None
    end = pd.Timestamp(period["end"]).to_pydatetime() if period.get("end") else None

    rows: list[tuple[str, str, str, dict[str, Any], int]] = []
    if study == "etf_lag":
        for signal, horizons in (payload.get("correlations") or {}).items():
            for horizon, metrics in horizons.items():
                rows.append((signal, horizon, "full", metrics, int(metrics.get("n", 0))))
    elif study == "etf_bucket":
        for bucket in payload.get("buckets") or []:
            for horizon, metrics in bucket["horizons"].items():
                rows.append((
                    f"{payload['signal']}:{bucket['label']}", horizon, "full",
                    metrics, int(metrics.get("n", 0)),
                ))
    elif study == "etf_split":
        for window, metrics in (payload.get("windows") or {}).items():
            rows.append((payload["signal"], payload["horizon"], window, metrics, int(metrics.get("n", 0))))

    with session_scope() as s:
        for signal, horizon, split, metrics, n in rows:
            rid = f"{study}:{asset.value}:{signal}:{horizon}:{split}"[:80]
            row = s.get(ResearchResultRow, rid)
            if row is None:
                row = ResearchResultRow(id=rid, study=study, asset=asset.value,
                                        signal=signal, horizon=horizon, split=split)
                s.add(row)
            row.sample_size = n
            row.metrics = metrics
            row.computed_at = now
            row.data_start = start
            row.data_end = end
            written += 1
    return written

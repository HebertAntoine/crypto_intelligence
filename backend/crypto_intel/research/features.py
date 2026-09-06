"""Feature construction and importance - interpretable, not a black box.

Deliberately avoids fitting a complex model. The brief asks which signals carry
information, and a gradient-boosted ensemble would answer that question in a way
nobody can audit. What is used instead:

  * information coefficient (rank correlation with forward returns)
  * bucket monotonicity - does a higher reading really mean a better outcome?
  * permutation importance inside a deliberately simple linear model
  * stability across walk-forward windows

Every feature is computed from PAST data only. `.rolling()` and the indicator
library are causal by construction, and a test verifies that mutating future
bars leaves earlier feature values untouched.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from ..core.enums import Asset, Timeframe
from ..engines.technical import indicators as ind
from ..history import store
from ..logging_setup import get_logger
from .stats import benjamini_hochberg, forward_returns, lagged_correlation
from .walkforward import bucket_monotonicity, walk_forward_ic

log = get_logger("research.features")

HORIZONS = [1, 3, 7, 14, 30]


def build_technical_features(df: pd.DataFrame) -> pd.DataFrame:
    """Every technical feature the scoring engine relies on, as a matrix.

    Names mirror the components of the live technical score so ablation
    results map directly onto the engine.
    """
    close, high, low, volume = df["close"], df["high"], df["low"], df["volume"]
    features = pd.DataFrame(index=df.index)

    ema20, ema50, ema200 = ind.ema(close, 20), ind.ema(close, 50), ind.ema(close, 200)

    # Trend structure - normalised by price so it is comparable across assets.
    features["ema20_vs_50"] = (ema20 - ema50) / close * 100.0
    features["price_vs_ema20"] = (close - ema20) / close * 100.0
    features["price_vs_ema50"] = (close - ema50) / close * 100.0
    features["price_vs_ema200"] = (close - ema200) / close * 100.0
    features["ema_stack"] = (
        ((close > ema20).astype(float) + (ema20 > ema50).astype(float)
         + (ema50 > ema200).astype(float)) - 1.5
    )

    # Momentum
    rsi = ind.rsi(close, 14)
    features["rsi"] = rsi - 50.0
    features["rsi_change_5"] = rsi.diff(5)
    macd_line, macd_signal, macd_hist = ind.macd(close)
    denom = close.rolling(20, min_periods=20).std(ddof=0).replace(0, np.nan)
    features["macd_hist_norm"] = (macd_hist / denom).clip(-3, 3)
    features["macd_cross"] = np.sign(macd_line - macd_signal)

    # Trend strength
    features["adx"] = ind.adx(high, low, close, 14) - 25.0

    # Volatility
    atr_pct = ind.atr_percent(high, low, close, 14)
    features["atr_pct"] = atr_pct
    features["atr_percentile"] = atr_pct.rolling(252, min_periods=60).rank(pct=True) * 100.0 - 50.0
    bb_upper, _bb_mid, bb_lower = ind.bollinger_bands(close, 20, 2.0)
    band = (bb_upper - bb_lower).replace(0, np.nan)
    features["bb_position"] = ((close - bb_lower) / band - 0.5) * 100.0
    features["bb_width"] = ind.bollinger_bandwidth(close, 20, 2.0)

    # Volume
    rel_volume = ind.relative_volume(volume, 20)
    features["rel_volume"] = (rel_volume - 1.0).clip(-1, 4)
    features["volume_accel"] = (ind.volume_acceleration(volume, 5, 20) - 1.0).clip(-1, 3)

    # Momentum over multiple lookbacks - the simplest baseline that works.
    for days in (5, 10, 20, 60):
        features[f"momentum_{days}d"] = close.pct_change(days) * 100.0

    # Distance from the recent range, a proxy for breakout / drawdown state.
    rolling_high = high.rolling(60, min_periods=20).max()
    rolling_low = low.rolling(60, min_periods=20).min()
    features["pct_from_60d_high"] = (close / rolling_high - 1.0) * 100.0
    features["pct_from_60d_low"] = (close / rolling_low - 1.0) * 100.0

    return features


def build_derivatives_features(asset: Asset, index: pd.DatetimeIndex) -> pd.DataFrame:
    """Funding and open-interest features, expressed as trailing percentiles.

    A raw funding rate of 0.0005 means different things on BTC and on SOL. A
    percentile within each asset's own trailing distribution is comparable
    across assets, which fixed thresholds never are.
    """
    features = pd.DataFrame(index=index)

    funding = store.load_derivatives(asset, "funding.rate")
    if not funding.empty:
        daily = funding.resample("1D").mean()
        daily.index = (
            daily.index.tz_convert("UTC") if daily.index.tz else daily.index.tz_localize("UTC")
        )
        daily = daily.reindex(index)
        features["funding"] = daily
        features["funding_pct"] = (
            daily.rolling(252, min_periods=60).rank(pct=True) * 100.0 - 50.0
        )
        features["funding_change_7d"] = daily.diff(7)
        features["funding_ma7"] = daily.rolling(7, min_periods=5).mean()

    oi = store.load_derivatives(asset, "oi.value")
    if not oi.empty:
        daily_oi = oi.resample("1D").mean()
        daily_oi.index = (
            daily_oi.index.tz_convert("UTC") if daily_oi.index.tz
            else daily_oi.index.tz_localize("UTC")
        )
        daily_oi = daily_oi.reindex(index)
        features["oi_change_1d"] = daily_oi.pct_change(1) * 100.0
        features["oi_change_7d"] = daily_oi.pct_change(7) * 100.0

    return features


def build_etf_features(asset: Asset, index: pd.DatetimeIndex) -> pd.DataFrame:
    """ETF flow features aligned to the daily price grid."""
    from .etf_study import build_flow_series, build_signals

    flows = build_flow_series(asset)
    if flows.empty:
        return pd.DataFrame(index=index)

    signals = build_signals(flows).reindex(index)
    features = pd.DataFrame(index=index)
    features["etf_flow"] = signals["flow"]
    features["etf_ma5"] = signals["ma5"]
    features["etf_ma7"] = signals["ma7"]
    features["etf_cum30"] = signals["cum30"]
    features["etf_acceleration"] = signals["acceleration"]
    features["etf_pct_rank"] = signals["flow_pct_rank"] - 50.0
    return features


def build_all_features(asset: Asset) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Full feature matrix plus the forward returns, kept in SEPARATE frames.

    The separation is structural, not stylistic: a forward return can never end
    up inside the feature matrix by accident.
    """
    df = store.load_candles(asset, Timeframe.D1)
    if df.empty:
        return pd.DataFrame(), pd.DataFrame()

    idx = pd.DatetimeIndex(df.index)
    idx = idx.tz_localize("UTC") if idx.tz is None else idx.tz_convert("UTC")
    df = df.copy()
    df.index = idx.normalize()
    df = df[~df.index.duplicated(keep="last")]

    features = build_technical_features(df)
    derivatives = build_derivatives_features(asset, df.index)
    etf = build_etf_features(asset, df.index)

    for extra in (derivatives, etf):
        for column in extra.columns:
            features[column] = extra[column]

    fwd = forward_returns(df["close"], HORIZONS)
    return features, fwd


def information_coefficients(
    features: pd.DataFrame, fwd: pd.DataFrame, min_observations: int = 100
) -> dict[str, Any]:
    """Rank correlation of every feature against every horizon, FDR-corrected."""
    results: dict[str, dict[str, Any]] = {}
    flat_p: list[float | None] = []
    flat_keys: list[tuple[str, str]] = []

    for column in features.columns:
        per_horizon: dict[str, Any] = {}
        for h in HORIZONS:
            r, p, n = lagged_correlation(features[column], fwd[f"fwd_{h}"])
            usable = n >= min_observations
            per_horizon[f"{h}d"] = {
                "ic": r, "p_value": p, "n": n,
                "significant_raw": bool(p is not None and p < 0.05 and usable),
            }
            flat_p.append(p if usable else None)
            flat_keys.append((column, f"{h}d"))
        results[column] = per_horizon

    # The grid is large (30+ features x 5 horizons), so uncorrected p-values
    # would manufacture findings out of noise.
    survives = benjamini_hochberg(flat_p, alpha=0.05)
    n_raw = n_corrected = 0
    for (column, horizon), passed in zip(flat_keys, survives, strict=True):
        cell = results[column][horizon]
        cell["significant"] = bool(passed)
        n_raw += int(cell["significant_raw"])
        n_corrected += int(passed)

    return {
        "features": results,
        "multiple_testing": {
            "hypotheses": len(flat_keys),
            "significant_raw": n_raw,
            "significant_after_fdr": n_corrected,
            "expected_false_positives_uncorrected": round(len(flat_keys) * 0.05, 1),
            "method": "Benjamini-Hochberg FDR at alpha=0.05",
        },
    }


def permutation_importance(
    features: pd.DataFrame,
    target: pd.Series,
    n_repeats: int = 5,
    seed: int = 42,
) -> dict[str, Any]:
    """Permutation importance inside a ridge regression.

    Ridge on purpose: linear, regularised, no hyperparameter search. The goal
    is to see which features carry information the others do not already
    contain - not to build a predictor. A model that cannot be inspected would
    defeat the purpose.
    """
    from sklearn.linear_model import Ridge
    from sklearn.metrics import r2_score

    # Drop sparse columns BEFORE dropping incomplete rows. Open interest covers
    # only ~30 days (a hard source limit), and a single column that sparse would
    # otherwise wipe out every row in the matrix - which is exactly what
    # happened before this guard: the model never ran at all.
    coverage = features.notna().mean()
    min_coverage = 0.5
    kept = [c for c in features.columns if coverage[c] >= min_coverage]
    excluded = {
        c: round(float(coverage[c]), 3)
        for c in features.columns if coverage[c] < min_coverage
    }

    joined = features[kept].join(target.rename("__target__"), how="inner").dropna()
    if len(joined) < 200:
        return {
            "available": False,
            "reason": f"INSUFFICIENT_DATA - {len(joined)} complete rows after dropping NaN",
            "excluded_sparse_features": excluded,
        }

    columns = [c for c in joined.columns if c != "__target__"]
    x = joined[columns].to_numpy(dtype=float)
    y = joined["__target__"].to_numpy(dtype=float)

    # Standardise so coefficients are comparable; ridge is scale-sensitive.
    mean, std = x.mean(axis=0), x.std(axis=0)
    std[std == 0] = 1.0
    x = (x - mean) / std

    # Chronological split - a random split would leak the future into the past.
    split = int(len(x) * 0.7)
    x_train, x_test = x[:split], x[split:]
    y_train, y_test = y[:split], y[split:]
    if len(x_test) < 60:
        return {"available": False, "reason": "INSUFFICIENT_DATA - test segment too small"}

    model = Ridge(alpha=10.0)
    model.fit(x_train, y_train)
    baseline = r2_score(y_test, model.predict(x_test))

    rng = np.random.default_rng(seed)
    importances: dict[str, dict[str, float]] = {}
    for i, column in enumerate(columns):
        drops = []
        for _ in range(n_repeats):
            permuted = x_test.copy()
            rng.shuffle(permuted[:, i])
            drops.append(baseline - r2_score(y_test, model.predict(permuted)))
        importances[column] = {
            "importance": round(float(np.mean(drops)), 6),
            "std": round(float(np.std(drops)), 6),
            "coefficient": round(float(model.coef_[i]), 6),
        }

    ranked = sorted(importances.items(), key=lambda kv: -kv[1]["importance"])
    return {
        "available": True,
        "baseline_r2_oos": round(float(baseline), 5),
        "n_train": len(x_train),
        "n_test": len(x_test),
        "features_used": len(columns),
        "excluded_sparse_features": excluded,
        "importances": dict(ranked),
        "top_features": [name for name, _ in ranked[:10]],
        "note": (
            "Ridge regression, chronological 70/30 split, permutation on the test "
            "segment. A baseline out-of-sample R^2 near zero (or negative) means the "
            "features jointly explain almost nothing - which is itself the finding. "
            f"Columns with under {min_coverage:.0%} coverage were excluded to stop a "
            "single sparse series (open interest) from emptying the matrix."
        ),
    }


def analyse_features(
    asset: Asset, horizons: list[int] | None = None, run_walk_forward: bool = True
) -> dict[str, Any]:
    """Full feature analysis for one asset: IC, monotonicity, stability."""
    horizons = horizons or HORIZONS
    features, fwd = build_all_features(asset)

    if features.empty:
        return {
            "asset": asset.value, "available": False,
            "reason": "UNAVAILABLE - no daily candles; run `make backfill`",
        }

    ic_results = information_coefficients(features, fwd)

    # Monotonicity and walk-forward are expensive, so they run on the 7-day
    # horizon only - the one the reports lead with.
    detail: dict[str, Any] = {}
    for column in features.columns:
        entry: dict[str, Any] = {}
        entry["monotonicity_7d"] = bucket_monotonicity(features[column], fwd["fwd_7"])
        if run_walk_forward:
            entry["walk_forward_7d"] = walk_forward_ic(features[column], fwd["fwd_7"])
        detail[column] = entry

    permutation = permutation_importance(features, fwd["fwd_7"])

    return {
        "asset": asset.value,
        "available": True,
        "period": {
            "start": features.index.min().isoformat(),
            "end": features.index.max().isoformat(),
            "rows": len(features),
        },
        "feature_count": len(features.columns),
        "information_coefficients": ic_results,
        "detail": detail,
        "permutation_importance": permutation,
        "ranking": rank_features(ic_results, detail),
    }


def rank_features(ic_results: dict[str, Any], detail: dict[str, Any]) -> list[dict[str, Any]]:
    """Rank features by measured usefulness, not by raw effect size.

    A feature with a large IC that flips sign between windows ranks below a
    smaller one that holds - which is why stability enters the score directly.
    """
    rows = []
    for column, horizons in ic_results["features"].items():
        cell = horizons.get("7d", {})
        ic = cell.get("ic")
        if ic is None:
            continue

        entry = detail.get(column, {})
        monotonic = (entry.get("monotonicity_7d") or {}).get("monotonic", False)
        wf = entry.get("walk_forward_7d") or {}
        stability = (wf.get("stability") or {}) if wf.get("available") else {}
        stability_score = stability.get("stability_score", 0.0)

        verdict = _feature_verdict(cell, monotonic, stability)

        # Composite: effect size counts, but is scaled by how much the effect
        # can be relied upon.
        usefulness = abs(ic) * 100.0 * (0.3 + 0.7 * stability_score / 100.0)
        if monotonic:
            usefulness *= 1.25
        if cell.get("significant"):
            usefulness *= 1.2

        # A huge IC computed on a handful of observations is an artefact, not a
        # discovery. Open interest, capped at ~30 days by the source, produced
        # an IC of -0.78 on 17 rows and topped the ranking until this guard.
        if verdict == "INSUFFICIENT_DATA":
            usefulness = 0.0

        rows.append({
            "feature": column,
            "ic_7d": ic,
            "p_value_7d": cell.get("p_value"),
            "significant_fdr": cell.get("significant", False),
            "n": cell.get("n", 0),
            "monotonic_7d": monotonic,
            "stability_score": stability_score,
            "stability_verdict": stability.get("verdict", "INSUFFICIENT_DATA"),
            "usefulness": round(usefulness, 3),
            "verdict": verdict,
        })

    # Sort by usefulness, then push insufficient-data features to the bottom
    # regardless of their nominal effect size.
    return sorted(rows, key=lambda r: (r["verdict"] == "INSUFFICIENT_DATA", -r["usefulness"]))


def _feature_verdict(cell: dict, monotonic: bool, stability: dict) -> str:
    """The five verdicts the brief asks for."""
    n = cell.get("n", 0)
    ic = cell.get("ic")

    if n < 100 or ic is None:
        return "INSUFFICIENT_DATA"

    stability_verdict = stability.get("verdict")
    if stability_verdict == "UNSTABLE":
        return "UNSTABLE"

    if abs(ic) < 0.03:
        return "NO_MEASURABLE_VALUE"

    if cell.get("significant") and monotonic and stability.get("stability_score", 0) >= 50:
        return "USEFUL"

    if cell.get("significant") or monotonic:
        return "WEAK"

    return "NO_MEASURABLE_VALUE"

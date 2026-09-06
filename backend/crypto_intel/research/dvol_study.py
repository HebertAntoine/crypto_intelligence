"""Does the variance risk premium carry information the price series does not?

Hypotheses are declared here, before any result exists:

  H1  an extreme variance premium (options expensive) precedes lower forward
      returns - the insurance is expensive because risk is genuinely elevated;
  H2  a depressed premium (options cheap) precedes higher forward returns;
  H3  a sharp rise in implied volatility precedes lower forward returns;
  H4  implied-volatility compression precedes larger subsequent moves in
      either direction, measured on absolute return.

Four features × three horizons × two assets = 24 primary hypotheses, declared
before computation and corrected together.

Every test runs the full LOT 6A chain: purged folds, stratification AND
residualisation, effective sample, power. The controls include realised
volatility explicitly, because implied and realised volatility are mechanically
linked - without that control the study would measure volatility clustering
and call it an options-market signal.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from ..core.enums import Asset, Timeframe
from ..engines.implied_volatility import ImpliedVolatilityEngine
from ..history import store
from ..logging_setup import get_logger
from .inference import (
    count_independent_blocks,
    effective_sample_v2,
    purged_walk_forward_folds,
    residualise,
)
from .power import VerdictInputs, assess_power, decide_verdict
from .regime_conditioned import reconstruct_regime
from .revalidation import build_controls
from .stats import benjamini_hochberg

log = get_logger("research.dvol")

HORIZONS = [7, 14, 30]

HYPOTHESES: list[dict[str, Any]] = [
    {"id": "premium_expensive", "feature": "variance_premium_percentile",
     "rule": "high", "threshold": 85,
     "hypothesis": "H1 options expensive precedes lower returns",
     "expected_sign": -1},
    {"id": "premium_cheap", "feature": "variance_premium_percentile",
     "rule": "low", "threshold": 15,
     "hypothesis": "H2 options cheap precedes higher returns",
     "expected_sign": 1},
    {"id": "dvol_spike", "feature": "dvol_change_30", "rule": "high",
     "threshold": 85,
     "hypothesis": "H3 implied volatility rising sharply precedes lower returns",
     "expected_sign": -1},
    {"id": "dvol_compressed", "feature": "dvol_percentile", "rule": "low",
     "threshold": 15,
     "hypothesis": "H4 compressed implied volatility precedes larger moves",
     "expected_sign": 0},           # tested on absolute return
]


def build_frame(asset: Asset) -> pd.DataFrame:
    """Implied-volatility features joined to price, controls and targets."""
    features = ImpliedVolatilityEngine().features(asset)
    if features.empty:
        return pd.DataFrame()

    df = store.load_candles(asset, Timeframe.D1)
    if df.empty:
        return pd.DataFrame()

    frame = features.reindex(df.index).copy()
    frame["close"] = df["close"]
    controls = build_controls(df)
    for column in controls.columns:
        frame[column] = controls[column]
    frame["regime"] = reconstruct_regime(df)

    for horizon in HORIZONS:
        forward = (df["close"].shift(-horizon) - df["close"]) / df["close"] * 100
        frame[f"target_{horizon}"] = forward
        frame[f"abs_target_{horizon}"] = forward.abs()

    # Trailing rank of dvol_change, needed for H3.
    values = frame["dvol_change_30"].to_numpy(dtype=float)
    ranks = np.full(len(values), np.nan)
    for i in range(180, len(values)):
        window = values[:i]
        window = window[~np.isnan(window)]
        if len(window):
            ranks[i] = float((window < values[i]).mean() * 100)
    frame["dvol_change_30_percentile"] = ranks
    return frame.dropna(subset=["dvol"])


def _signal(frame: pd.DataFrame, spec: dict[str, Any]) -> pd.Series:
    column = spec["feature"]
    if column == "dvol_change_30":
        column = "dvol_change_30_percentile"
    values = frame[column]
    if spec["rule"] == "high":
        return (values >= spec["threshold"]).astype(float)
    return (values <= spec["threshold"]).astype(float)


def test_one(asset: Asset, spec: dict[str, Any], horizon: int, frame: pd.DataFrame) -> dict[str, Any]:
    out: dict[str, Any] = {
        "asset": asset.value, "hypothesis_id": spec["id"],
        "hypothesis": spec["hypothesis"], "horizon_days": horizon,
        "expected_sign": spec["expected_sign"],
    }

    target_column = (
        f"abs_target_{horizon}" if spec["expected_sign"] == 0 else f"target_{horizon}"
    )
    working = frame.dropna(subset=[target_column, spec["feature"]
                                   if spec["feature"] != "dvol_change_30"
                                   else "dvol_change_30_percentile"])
    if len(working) < 400:
        out["status"] = "INSUFFICIENT_DATA"
        out["note"] = f"{len(working)} usable rows"
        return out

    signal = _signal(working, spec)
    target = working[target_column]
    n_events = int(signal.sum())
    out["raw_occurrences"] = n_events
    if n_events < 30:
        out["status"] = "INSUFFICIENT_DATA"
        out["note"] = f"{n_events} occurrences"
        return out

    out["status"] = "OK"
    mask = signal > 0

    # --- stratification on regime ---------------------------------------
    regimes = working["regime"]
    weighted_event = weighted_baseline = 0.0
    total_weight = 0
    residual_event: list[float] = []
    residual_baseline: list[float] = []
    for _, chunk in pd.DataFrame(
        {"y": target, "regime": regimes, "event": mask}
    ).dropna(subset=["y", "regime"]).groupby("regime"):
        events = chunk.loc[chunk["event"], "y"]
        others = chunk.loc[~chunk["event"], "y"]
        if len(events) < 10 or len(others) < 20:
            continue
        baseline_mean = float(others.mean())
        weighted_event += float(events.mean()) * len(events)
        weighted_baseline += baseline_mean * len(events)
        total_weight += len(events)
        residual_event.extend((events - baseline_mean).tolist())
        residual_baseline.extend((others - baseline_mean).tolist())

    if not total_weight or len(residual_event) < 30:
        out["status"] = "INSUFFICIENT_DATA"
        out["note"] = "no regime stratum had enough observations"
        return out

    strat_excess = (weighted_event - weighted_baseline) / total_weight
    _, p_value = stats.ttest_ind(residual_event, residual_baseline, equal_var=False)
    out["stratified_excess_pct"] = round(float(strat_excess), 4)
    out["stratified_p_value"] = float(p_value)

    # --- residualisation on purged folds ---------------------------------
    controls = working[[
        "return_1", "return_5", "return_20", "return_60",
        "realised_vol_20", "realised_vol_60", "dist_ema200_pct", "adx_14",
    ]]
    folds = purged_walk_forward_folds(
        pd.DatetimeIndex(working.index), horizon_bars=horizon, n_folds=3
    )
    residual_excesses: list[float] = []
    residual_ps: list[float] = []
    for fold in folds:
        train = fold.train_mask.reindex(working.index, fill_value=False)
        test = fold.test_mask.reindex(working.index, fill_value=False)
        result = residualise(target, controls, signal, train, test)
        if result.status == "OK" and result.excess is not None:
            residual_excesses.append(result.excess)
            residual_ps.append(result.p_value)

    if residual_excesses:
        out["residual_excess_pct"] = round(float(np.mean(residual_excesses)), 4)
        out["residual_p_value"] = float(max(residual_ps))
        out["residual_folds"] = len(residual_excesses)
    else:
        out["residual_excess_pct"] = None
        out["residual_p_value"] = None

    # --- sample and power -------------------------------------------------
    event_times = pd.DatetimeIndex(target[mask].dropna().index)
    full_index = pd.DatetimeIndex(working.index)
    sample = effective_sample_v2(
        event_times, horizon_bars=horizon, target=target, full_index=full_index,
        n_blocks=count_independent_blocks(event_times, full_index, horizon),
    )
    out["effective_sample"] = sample

    pooled_sd = float(target.std())
    power = assess_power(
        sample["effective_n"], max(sample["effective_n"] * 4, 30), pooled_sd, horizon
    )
    out["power"] = power.to_dict()

    # Sign agreement with the declared hypothesis.
    if spec["expected_sign"] != 0:
        out["matches_hypothesis"] = bool(
            np.sign(strat_excess) == spec["expected_sign"]
        )
    else:
        out["matches_hypothesis"] = bool(strat_excess > 0)

    out["_verdict_inputs"] = {
        "effective_n": sample["effective_n"],
        "effect_pct": round(float(strat_excess), 4),
        "stratified_excess": round(float(strat_excess), 4),
        "residual_excess": out.get("residual_excess_pct"),
        "residual_p_value": out.get("residual_p_value"),
    }
    return out


def run_all(assets: list[Asset] | None = None) -> dict[str, Any]:
    assets = assets or [Asset.BTC, Asset.ETH]
    results: list[dict[str, Any]] = []
    unavailable: list[str] = []

    for asset in assets:
        frame = build_frame(asset)
        if frame.empty:
            unavailable.append(asset.value)
            continue
        for spec in HYPOTHESES:
            for horizon in HORIZONS:
                results.append(test_one(asset, spec, horizon, frame))

    # SOL is stated explicitly rather than silently omitted.
    for asset in Asset.tradables():
        if asset not in assets:
            unavailable.append(asset.value)

    testable = [r for r in results if r.get("status") == "OK"]
    p_values = [r["stratified_p_value"] for r in testable]
    survives = benjamini_hochberg(p_values, alpha=0.05)

    for result, ok in zip(testable, survives, strict=True):
        inputs = result.pop("_verdict_inputs")
        verdict = decide_verdict(
            VerdictInputs(
                survives_fdr=ok,
                effective_n=inputs["effective_n"],
                effect_pct=inputs["effect_pct"],
                stability_verdict="STABLE",
                oos_confirms=(
                    inputs["residual_p_value"] is not None
                    and inputs["residual_p_value"] < 0.05
                ),
                stratified_excess=inputs["stratified_excess"],
                residual_excess=inputs["residual_excess"],
                residual_p_value=inputs["residual_p_value"],
                power=assess_power(
                    inputs["effective_n"], max(inputs["effective_n"] * 4, 30),
                    float(result.get("power", {}).get("std_dev") or 1.0),
                    result["horizon_days"],
                ),
            ),
            horizon_bars=result["horizon_days"],
        )
        result.update(verdict)
        result["survives_fdr"] = bool(ok)

    for result in results:
        result.pop("_verdict_inputs", None)

    counts: dict[str, int] = {}
    for result in results:
        key = result.get("verdict", result.get("status", "UNKNOWN"))
        counts[key] = counts.get(key, 0) + 1

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "hypotheses_preregistered": len(HYPOTHESES) * len(HORIZONS) * len(assets),
        "assets_tested": [a.value for a in assets],
        "assets_unavailable": sorted(set(unavailable)),
        "multiple_testing": {
            "tests_performed": len(testable),
            "raw_significant": sum(1 for p in p_values if p < 0.05),
            "fdr_significant": sum(survives),
            "expected_false_positives": round(len(testable) * 0.05, 1),
        },
        "verdict_counts": counts,
        "results": results,
        "note": (
            "Hypotheses were declared in the module before any result existed. "
            "Realised volatility is an explicit control: without it the study "
            "would measure volatility clustering rather than options pricing."
        ),
    }

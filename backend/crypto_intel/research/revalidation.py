"""Re-test the surviving LOT 4 and LOT 5 candidates under the LOT 6A framework.

Ten candidates were pre-registered before any of this was run. All ten are
reported whatever the outcome; none may be dropped for being inconvenient.

What changes versus their original evaluation:

  * purged and embargoed folds instead of splits that shared a boundary bar and
    kept training rows whose targets reached into the test period;
  * residualisation on continuous controls alongside the discrete-regime
    stratification, with a verdict that requires BOTH;
  * power reported next to every p-value, so a null result on a small sample is
    INSUFFICIENT_DATA rather than FAILED;
  * effective sample taken as the minimum of four dependence corrections.

An honest outcome is that most candidates are demoted. That would mean the
project previously believed things it could not support, which is worth
knowing.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from ..core.enums import Asset, Timeframe
from ..engines.technical import indicators as ind
from ..history import store
from ..logging_setup import get_logger
from .inference import (
    BaselineCoverageError,
    assert_baseline_is_conditioned,
    count_independent_blocks,
    effective_sample_v2,
    purged_walk_forward_folds,
    residualise,
    verify_embargo,
)
from .power import VerdictInputs, assess_power, decide_verdict
from .regime_conditioned import reconstruct_regime

log = get_logger("research.revalidation")

WINDOW = 150

# Pre-registered before any result was seen.
CANDIDATES: list[dict[str, Any]] = [
    {"id": "ETH_ABOVE_RANGE_7", "asset": "ETH", "kind": "location",
     "label": "ABOVE_RANGE", "horizon": 7, "lot5_excess": 4.04},
    {"id": "ETH_ABOVE_RANGE_14", "asset": "ETH", "kind": "location",
     "label": "ABOVE_RANGE", "horizon": 14, "lot5_excess": 5.55},
    {"id": "BTC_double_top_CONFIRMED_7", "asset": "BTC", "kind": "pattern",
     "label": "double_top|CONFIRMED", "horizon": 7, "lot5_excess": -1.14},
    {"id": "BTC_MID_RANGE_30", "asset": "BTC", "kind": "location",
     "label": "MID_RANGE", "horizon": 30, "lot5_excess": -4.35},
    {"id": "BTC_RANGE_STRUCTURE_30", "asset": "BTC", "kind": "structure",
     "label": "RANGE_STRUCTURE", "horizon": 30, "lot5_excess": -3.78},
    {"id": "ETH_MID_RANGE_7", "asset": "ETH", "kind": "location",
     "label": "MID_RANGE", "horizon": 7, "lot5_excess": -1.60},
    {"id": "ETH_TRANSITION_7", "asset": "ETH", "kind": "structure",
     "label": "TRANSITION", "horizon": 7, "lot5_excess": -1.23},
    {"id": "ETH_double_top_FAILED_3", "asset": "ETH", "kind": "pattern",
     "label": "double_top|FAILED", "horizon": 3, "lot5_excess": 2.76},
    {"id": "ETH_rising_wedge_7", "asset": "ETH", "kind": "pattern",
     "label": "rising_wedge|CANDIDATE", "horizon": 7, "lot5_excess": -2.13},
    {"id": "BTC_inverse_hs_14", "asset": "BTC", "kind": "pattern",
     "label": "inverse_head_and_shoulders|CANDIDATE", "horizon": 14,
     "lot5_excess": -4.38},
]

CONTROL_SPEC = [
    "return_1", "return_5", "return_20", "return_60",
    "realised_vol_20", "realised_vol_60",
    "dist_ema200_pct", "adx_14",
]


def build_controls(df: pd.DataFrame) -> pd.DataFrame:
    """The eight continuous controls, all point-in-time by construction.

    Lagged returns at four horizons target the measured confound directly: the
    regime label correlates +0.73 with the past 40-60 day return, so the
    controls must span that window at full resolution rather than in five
    buckets.
    """
    close, high, low = df["close"], df["high"], df["low"]
    controls = pd.DataFrame(index=df.index)
    controls["return_1"] = close.pct_change(1) * 100
    controls["return_5"] = close.pct_change(5) * 100
    controls["return_20"] = close.pct_change(20) * 100
    controls["return_60"] = close.pct_change(60) * 100
    returns = close.pct_change()
    controls["realised_vol_20"] = returns.rolling(20).std() * 100
    controls["realised_vol_60"] = returns.rolling(60).std() * 100
    controls["dist_ema200_pct"] = (
        (close - close.ewm(span=200, adjust=False).mean()) / close * 100
    )
    controls["adx_14"] = ind.adx(high, low, close, 14)
    return controls


def _event_mask(asset: Asset, kind: str, label: str, df: pd.DataFrame) -> pd.Series:
    """Replay the detector bar by bar, seeing only the past at each step."""
    from ..structure.location import StructuralLocationEngine
    from ..structure.market_structure import MarketStructureEngine
    from ..structure.patterns import build_context, detect_all
    from ..structure.ranges import RangeIntelligenceEngine

    mask = pd.Series(False, index=df.index)
    range_engine = RangeIntelligenceEngine()
    location_engine = StructuralLocationEngine(range_engine)
    structure_engine = MarketStructureEngine()

    for i in range(WINDOW, len(df)):
        window = df.iloc[:i + 1]
        try:
            if kind == "location":
                detected = range_engine.detect_from_frame(window)
                if detected.valid and detected.top_zone and detected.bottom_zone:
                    price = float(window["close"].iloc[-1])
                    state = location_engine._classify(
                        price, detected.top_zone, detected.bottom_zone,
                        detected.position(price),
                    )
                    if state.value == label:
                        mask.iloc[i] = True
            elif kind == "structure":
                from ..structure.swings import find_causal_swings

                atr = ind.atr(window["high"], window["low"], window["close"], 14)
                swings = find_causal_swings(
                    window["high"], window["low"], window["close"], atr, lookback=5
                ).as_of(window.index[-1])
                from ..structure.market_structure import MarketStructureReading

                blank = MarketStructureReading(asset=asset.value, timeframe="1d")
                reading = structure_engine.assess_from_swings(swings, blank, window)
                if reading.state.value == label:
                    mask.iloc[i] = True
            elif kind == "pattern":
                ctx = build_context(window, Timeframe.D1)
                if ctx is not None:
                    for pattern in detect_all(ctx):
                        if f"{pattern.name}|{pattern.state.value}" == label:
                            mask.iloc[i] = True
                            break
        except Exception:
            continue
    return mask


def revalidate_one(candidate: dict[str, Any]) -> dict[str, Any]:
    """Full LOT 6A chain on one pre-registered candidate."""
    asset = Asset(candidate["asset"])
    horizon = candidate["horizon"]
    out: dict[str, Any] = {
        "id": candidate["id"], "asset": asset.value,
        "label": candidate["label"], "horizon_days": horizon,
        "lot5_excess_pct": candidate["lot5_excess"],
    }

    df = store.load_candles(asset, Timeframe.D1)
    if df.empty or len(df) < WINDOW + 200:
        out["status"] = "NO_DATA"
        return out

    close = df["close"]
    target = (close.shift(-horizon) - close) / close * 100.0
    controls = build_controls(df)
    regimes = reconstruct_regime(df)
    mask = _event_mask(asset, candidate["kind"], candidate["label"], df)

    n_events = int(mask.sum())
    out["raw_occurrences"] = n_events
    if n_events < 20:
        out["status"] = "INSUFFICIENT_DATA"
        out["verdict"] = "INSUFFICIENT_DATA"
        out["note"] = f"{n_events} occurrences"
        return out

    out["status"] = "OK"

    # --- embargo verification -------------------------------------------
    out["embargo_check"] = verify_embargo(target, embargo_bars=horizon)

    # --- purged folds -----------------------------------------------------
    usable = target.dropna().index
    folds = purged_walk_forward_folds(usable, horizon_bars=horizon, n_folds=3)
    out["folds"] = [f.to_dict() for f in folds]
    if not folds:
        out["verdict"] = "INSUFFICIENT_DATA"
        out["note"] = "not enough history for purged folds"
        return out

    # --- method A: stratification on regime -------------------------------
    strat = _stratified(target, mask, regimes)
    out["stratified"] = strat

    # --- method B: residualisation on continuous controls -----------------
    residual_results = []
    for fold in folds:
        train = fold.train_mask.reindex(df.index, fill_value=False)
        test = fold.test_mask.reindex(df.index, fill_value=False)
        result = residualise(target, controls, mask.astype(float), train, test)
        residual_results.append(result.to_dict())
    out["residualised_folds"] = residual_results

    usable_residuals = [
        r for r in residual_results if r["status"] == "OK" and r["excess_pct"] is not None
    ]
    if usable_residuals:
        excesses = [r["excess_pct"] for r in usable_residuals]
        # Combine folds by averaging the excess and taking the least favourable
        # p-value: a candidate that only works in one fold is not confirmed.
        out["residual_excess_pct"] = round(float(np.mean(excesses)), 4)
        out["residual_p_value"] = float(max(r["p_value"] for r in usable_residuals))
        out["residual_folds_agreeing"] = int(
            sum(1 for e in excesses if np.sign(e) == np.sign(np.mean(excesses)))
        )
        out["residual_folds_total"] = len(usable_residuals)
    else:
        out["residual_excess_pct"] = None
        out["residual_p_value"] = None

    # --- effective sample --------------------------------------------------
    event_times = pd.DatetimeIndex(target[mask].dropna().index)
    # The block count must come from where the events actually fall. Passing a
    # constant here made it the binding constraint for every candidate.
    n_blocks = count_independent_blocks(
        event_times, pd.DatetimeIndex(target.dropna().index), horizon
    )
    sample = effective_sample_v2(
        event_times, horizon_bars=horizon, target=target, n_blocks=n_blocks,
        full_index=pd.DatetimeIndex(target.dropna().index),
    )
    out["effective_sample"] = sample

    # --- power -------------------------------------------------------------
    event_returns = target[mask].dropna()
    baseline_returns = target[~mask].dropna()
    pooled_sd = float(
        np.sqrt((event_returns.var() * len(event_returns)
                 + baseline_returns.var() * len(baseline_returns))
                / max(len(event_returns) + len(baseline_returns), 1))
    )
    power = assess_power(
        effective_n_event=sample["effective_n"],
        effective_n_baseline=max(sample["effective_n"] * 4, 30),
        std_dev=pooled_sd, horizon_bars=horizon,
    )
    out["power"] = power.to_dict()

    # --- verdict -----------------------------------------------------------
    verdict = decide_verdict(
        VerdictInputs(
            survives_fdr=bool(strat.get("p_value") is not None and strat["p_value"] < 0.05),
            effective_n=sample["effective_n"],
            effect_pct=strat.get("excess_pct"),
            stability_verdict=strat.get("stability_verdict"),
            oos_confirms=out.get("residual_p_value") is not None
            and out["residual_p_value"] < 0.05,
            stratified_excess=strat.get("excess_pct"),
            residual_excess=out.get("residual_excess_pct"),
            residual_p_value=out.get("residual_p_value"),
            power=power,
        ),
        horizon_bars=horizon,
    )
    out.update(verdict)
    out["changed_from_lot5"] = _describe_change(candidate, out)
    return out


def _stratified(
    target: pd.Series, mask: pd.Series, regimes: pd.Series
) -> dict[str, Any]:
    """Regime-matched excess, with the baseline coverage guard applied."""
    aligned = pd.concat(
        [target.rename("y"), regimes.rename("regime"), mask.rename("event")], axis=1
    ).dropna(subset=["y", "regime"])
    if aligned.empty:
        return {"status": "NO_DATA"}

    # The LOT 5 guard: refuse a baseline that is unconditional in disguise.
    baseline_mask = ~aligned["event"]
    try:
        coverage = assert_baseline_is_conditioned(baseline_mask, "stratified baseline")
    except BaselineCoverageError as exc:
        # A rare label leaves a ~100% baseline. That is expected here and is
        # exactly why the stratification is done per regime rather than on the
        # whole-sample mask.
        coverage = {"note": str(exc)[:160], "coverage": float(baseline_mask.mean())}

    weighted_event = weighted_baseline = 0.0
    total_weight = 0
    residual_event: list[float] = []
    residual_baseline: list[float] = []
    strata: list[dict[str, Any]] = []

    for regime_value, chunk in aligned.groupby("regime"):
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
        strata.append({
            "regime": str(regime_value), "n_events": len(events),
            "excess_pct": round(float(events.mean() - baseline_mean), 3),
        })

    if not total_weight or len(residual_event) < 30:
        return {"status": "INSUFFICIENT_DATA", "strata": strata,
                "baseline_coverage": coverage}

    excess = (weighted_event - weighted_baseline) / total_weight
    t_stat, p_value = stats.ttest_ind(residual_event, residual_baseline, equal_var=False)

    by_year: dict[str, float] = {}
    for year, chunk in aligned[aligned["event"]].groupby(aligned[aligned["event"]].index.year):
        base = aligned[(~aligned["event"]) & (aligned.index.year == year)]["y"]
        if len(chunk) >= 3 and len(base) >= 20:
            by_year[str(year)] = round(float(chunk["y"].mean() - base.mean()), 3)
    stability = "INSUFFICIENT_YEARS"
    if len(by_year) >= 3:
        values = list(by_year.values())
        positive = sum(1 for v in values if v > 0)
        share = max(positive, len(values) - positive) / len(values)
        stability = "STABLE" if share >= 0.7 else "MIXED" if share >= 0.55 else "UNSTABLE"

    return {
        "status": "OK",
        "excess_pct": round(float(excess), 4),
        "p_value": float(p_value),
        "t_stat": round(float(t_stat), 3),
        "regimes_used": len(strata),
        "strata": strata,
        "by_year": by_year,
        "stability_verdict": stability,
        "baseline_coverage": coverage,
    }


def _describe_change(candidate: dict[str, Any], result: dict[str, Any]) -> str:
    old = candidate["lot5_excess"]
    new = result.get("stratified", {}).get("excess_pct")
    residual = result.get("residual_excess_pct")
    if new is None:
        return f"LOT 5 reported {old:+.2f}%; the new framework could not measure it"

    parts = [f"LOT 5 {old:+.2f}% → stratified {new:+.2f}%"]
    if residual is not None:
        parts.append(f"residualised {residual:+.2f}%")
        if np.sign(new) != np.sign(residual):
            parts.append("the two control methods disagree in SIGN")
    else:
        parts.append("residualisation could not be computed")
    return "; ".join(parts)


def run_all() -> dict[str, Any]:
    results = []
    for candidate in CANDIDATES:
        try:
            results.append(revalidate_one(candidate))
        except Exception as exc:
            log.warning("revalidation_failed", id=candidate["id"], error=str(exc))
            results.append({
                "id": candidate["id"], "status": "ERROR", "error": str(exc)[:250],
            })

    counts: dict[str, int] = {}
    for result in results:
        verdict = result.get("verdict", result.get("status", "UNKNOWN"))
        counts[verdict] = counts.get(verdict, 0) + 1

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "framework": "LOT 6A - purged folds, dual control, power-aware verdicts",
        "candidates_preregistered": len(CANDIDATES),
        "verdict_counts": counts,
        "results": results,
        "note": (
            "All ten candidates were declared before any of these numbers existed. "
            "Demotions are reported as prominently as confirmations."
        ),
    }

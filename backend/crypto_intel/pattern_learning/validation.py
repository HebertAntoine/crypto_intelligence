"""Historical audit of consensus patterns under the prospective counting rule.

This is deliberately separate from recognition.  An agreement between two
detectors says that a shape is less likely to be an artefact; only returns
observed after ``available_at`` can say whether that shape carried information.

Every horizon is de-duplicated across assets.  BTC, ETH and SOL patterns whose
future windows overlap are therefore one opportunity, never three independent
observations.  Historical results remain exploratory even after this cleanup;
only the live registry can supply genuinely prospective evidence.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from ..core.enums import Asset, Timeframe
from ..history import store
from ..research.regime_conditioned import reconstruct_regime
from ..research.stats import MIN_RELIABLE_SAMPLE, benjamini_hochberg
from .lmw import TEMPLATE_BY_PATTERN, PatternOrientation
from .ontology import StructuralPatternName

HORIZONS = (24, 48, 72, 168)
MIN_EFFECT_PCT = 0.15


def _orientation(pattern: str) -> int:
    template = TEMPLATE_BY_PATTERN.get(StructuralPatternName(pattern))
    if template is None or template.orientation is PatternOrientation.NEUTRAL:
        return 0
    return 1 if template.orientation is PatternOrientation.BULLISH else -1


def select_non_overlapping(
    events: list[dict[str, Any]], horizon_bars: int
) -> list[dict[str, Any]]:
    """Count one chronological opportunity per global forward window."""
    if horizon_bars <= 0:
        raise ValueError("horizon_bars must be positive")
    ordered = sorted(
        events,
        key=lambda item: (
            pd.Timestamp(item["available_at"]),
            str(item["asset"]),
            str(item["pattern"]),
        ),
    )
    selected: list[dict[str, Any]] = []
    separation = timedelta(hours=horizon_bars)
    for event in ordered:
        when = pd.Timestamp(event["available_at"])
        if selected:
            previous = pd.Timestamp(selected[-1]["available_at"])
            if when - previous < separation:
                continue
        selected.append(event)
    return selected


def _candidates(consensus: dict[str, Any]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for result in consensus.get("results", {}).values():
        if result.get("status") != "OK" or result.get("timeframe") != Timeframe.H1.value:
            continue
        asset = str(result["asset"])
        for item in result.get("items", []):
            if item.get("state") != "INDEPENDENT_AGREEMENT":
                continue
            direction = _orientation(str(item["pattern"]))
            if direction == 0:
                continue
            events.append({
                "asset": asset,
                "pattern": str(item["pattern"]),
                "available_at": str(item["available_at"]),
                "direction": direction,
            })
    return events


def _year_stability(frame: pd.DataFrame) -> dict[str, Any]:
    usable: dict[str, float] = {}
    for year, chunk in frame.groupby(frame["available_at"].dt.year):
        if len(chunk) >= 5:
            usable[str(year)] = round(float(chunk["excess_pct"].mean()), 4)
    if not usable:
        return {"years_covered": 0, "verdict": "NO_DATA"}
    positive = sum(value > 0 for value in usable.values())
    consistency = max(positive, len(usable) - positive) / len(usable)
    verdict = (
        "STABLE" if len(usable) >= 3 and consistency >= 0.7
        else "MIXED" if consistency >= 0.55
        else "UNSTABLE"
    )
    return {
        "years_covered": len(usable),
        "years_positive": positive,
        "sign_consistency_pct": round(consistency * 100.0, 1),
        "by_year": usable,
        "verdict": verdict,
    }


def _measure_horizon(
    candidates: list[dict[str, Any]],
    frames: dict[str, pd.DataFrame],
    regimes: dict[str, pd.Series],
    horizon: int,
) -> tuple[dict[str, Any], pd.DataFrame]:
    selected = select_non_overlapping(candidates, horizon)
    event_times: dict[str, set[pd.Timestamp]] = {}
    for event in candidates:
        event_times.setdefault(str(event["asset"]), set()).add(
            pd.Timestamp(event["available_at"])
        )

    returns = {
        asset: (frame["close"].shift(-horizon) / frame["close"] - 1.0) * 100.0
        for asset, frame in frames.items()
    }
    rows: list[dict[str, Any]] = []
    for event in selected:
        asset = str(event["asset"])
        frame = frames.get(asset)
        regime = regimes.get(asset)
        if frame is None or regime is None or frame.empty:
            continue
        when = pd.Timestamp(event["available_at"])
        position = frame.index.get_indexer([when], method="bfill")[0]
        if position < 0 or position + horizon >= len(frame):
            continue
        aligned_time = frame.index[position]
        raw_forward = returns[asset]
        raw_return = float(raw_forward.iloc[position])
        regime_at_event = regime.iloc[position]
        baseline_mask = regime.eq(regime_at_event) & raw_forward.notna()
        baseline_mask &= ~raw_forward.index.isin(event_times.get(asset, set()))
        baseline = raw_forward[baseline_mask]
        if baseline.empty or not np.isfinite(raw_return):
            continue
        direction = int(event["direction"])
        directional = raw_return * direction
        directional_baseline = float(baseline.mean()) * direction
        rows.append({
            **event,
            "available_at": aligned_time,
            "regime": str(regime_at_event),
            "directional_return_pct": directional,
            "baseline_pct": directional_baseline,
            "excess_pct": directional - directional_baseline,
        })

    measured = pd.DataFrame(rows)
    result: dict[str, Any] = {
        "horizon_bars": horizon,
        "raw_directional_candidates": len(candidates),
        "independent_windows_selected": len(selected),
        "settled_observations": len(measured),
    }
    if measured.empty:
        result.update({"status": "NO_DATA", "p_value": None})
        return result, measured

    outcomes = measured["directional_return_pct"]
    excess = measured["excess_pct"]
    result.update({
        "status": "OK" if len(measured) >= MIN_RELIABLE_SAMPLE else "INSUFFICIENT_DATA",
        "mean_directional_return_pct": round(float(outcomes.mean()), 4),
        "win_rate_pct": round(float((outcomes > 0).mean() * 100.0), 2),
        "mean_excess_vs_same_regime_pct": round(float(excess.mean()), 4),
        "positive_excess_rate_pct": round(float((excess > 0).mean() * 100.0), 2),
        "stability": _year_stability(measured),
        "baseline": (
            "Mean forward return of the same asset and causal regime, excluding "
            "consensus timestamps, multiplied by the pattern direction"
        ),
    })
    if len(measured) >= MIN_RELIABLE_SAMPLE and float(excess.std(ddof=1)) > 0:
        t_stat, p_value = stats.ttest_1samp(excess, 0.0)
        result["t_stat"] = round(float(t_stat), 4)
        result["p_value"] = float(p_value)
    else:
        result["p_value"] = None
    return result, measured


def run_consensus_validation(consensus: dict[str, Any]) -> dict[str, Any]:
    """Evaluate H1 consensus events without presenting history as a live test."""
    candidates = _candidates(consensus)
    assets = sorted({str(item["asset"]) for item in candidates})
    frames = {
        value: store.load_candles(Asset(value), Timeframe.H1)
        for value in assets
    }
    regimes = {
        value: reconstruct_regime(frame)
        for value, frame in frames.items()
        if not frame.empty
    }

    results: dict[str, Any] = {}
    measured_by_horizon: dict[int, pd.DataFrame] = {}
    p_values: list[float | None] = []
    for horizon in HORIZONS:
        result, measured = _measure_horizon(
            candidates, frames, regimes, horizon
        )
        results[f"{horizon}h"] = result
        measured_by_horizon[horizon] = measured
        p_values.append(result.get("p_value"))

    decisions = benjamini_hochberg(p_values, alpha=0.05)
    for horizon, survives in zip(HORIZONS, decisions, strict=True):
        result = results[f"{horizon}h"]
        result["survives_fdr"] = bool(survives)
        effect = abs(float(result.get("mean_excess_vs_same_regime_pct") or 0.0))
        stable = result.get("stability", {}).get("verdict") == "STABLE"
        result["verdict"] = (
            "MEASURABLE_EDGE"
            if survives and effect >= MIN_EFFECT_PCT and stable
            else "NO_MEASURABLE_EDGE"
        )

    detail = measured_by_horizon.get(72, pd.DataFrame())
    breakdown: dict[str, Any] = {}
    if not detail.empty:
        for pattern, group in detail.groupby("pattern"):
            breakdown[str(pattern)] = {
                "n": len(group),
                "win_rate_pct": round(
                    float((group["directional_return_pct"] > 0).mean() * 100.0), 1
                ),
                "mean_directional_return_pct": round(
                    float(group["directional_return_pct"].mean()), 4
                ),
                "mean_excess_vs_same_regime_pct": round(
                    float(group["excess_pct"].mean()), 4
                ),
            }

    survivors = [
        key for key, result in results.items() if result["verdict"] == "MEASURABLE_EDGE"
    ]
    return {
        "status": "OK" if candidates else "NO_DATA",
        "timeframe": Timeframe.H1.value,
        "candidate_events": len(candidates),
        "patterns": dict(sorted(Counter(item["pattern"] for item in candidates).items())),
        "horizons": results,
        "pattern_breakdown_72h": breakdown,
        "multiple_testing": {
            "hypotheses_tested": len([value for value in p_values if value is not None]),
            "survives_fdr": len(survivors),
            "survivors": survivors,
            "method": "Benjamini-Hochberg alpha=0.05 across all tested horizons",
        },
        "verdict": "MEASURABLE_EDGE" if survivors else "NO_MEASURABLE_EDGE",
        "note": (
            "Historical exploratory audit. Each horizon uses globally non-overlapping "
            "windows across assets and a same-regime baseline. Only post-registration "
            "observations can validate a predictive claim."
        ),
    }


def save_consensus_validation(
    result: dict[str, Any],
    path: str | Path = "data/research/pattern_consensus_validation.json",
) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2, default=str))
    return target

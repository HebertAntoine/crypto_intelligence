"""The DVOL study run again, with BTC and ETH pooled.

The single-asset version ended with zero supported hypotheses and eighteen
effective observations on its best result. This asks the only question that can
raise that number without waiting years: does combining the two assets that
have DVOL data produce evidence neither has alone?

The same four hypotheses, the same three horizons, the same controls. The
change is that each is now estimated on a panel of both assets under four
pooling assumptions, and the four are required to agree before anything is
called supported.

SOL has no DVOL series and no proxy is constructed for it. A synthetic implied
volatility built from realised volatility would measure realised volatility,
and pooling it in would contaminate the very quantity under test.
"""

from __future__ import annotations

import json
import pathlib
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd

from ..core.enums import Asset
from ..logging_setup import get_logger
from .dvol_study import HORIZONS, HYPOTHESES, _signal, build_frame
from .hypothesis_registry import Hypothesis, HypothesisStatus, get_registry
from .inference import purged_walk_forward_folds, residualise
from .panel import build_panel, compare_methods
from .power import StatisticalPowerEngine
from .stats import benjamini_hochberg

log = get_logger("research.dvol_pooled")

POOLED_ASSETS = [Asset.BTC, Asset.ETH]
CONTROLS = [
    "return_1", "return_5", "return_20", "return_60",
    "realised_vol_20", "realised_vol_60", "dist_ema200_pct", "adx_14",
]


def _preregister() -> list[str]:
    """Declare the pooled hypotheses before running them."""
    registry = get_registry()
    keys: list[str] = []
    for spec in HYPOTHESES:
        for horizon in HORIZONS:
            hypothesis = Hypothesis(
                id=f"dvol_pooled__{spec['id']}__h{horizon}",
                statement=(
                    f"{spec['hypothesis']}, estimated jointly on BTC and ETH "
                    f"at a {horizon}-day horizon"
                ),
                family="implied_volatility_pooled",
                asset="BTC+ETH",
                feature=spec["feature"],
                rule=spec["rule"],
                threshold=float(spec["threshold"]),
                horizon_days=horizon,
                target=(
                    "abs_forward_return_pct" if spec["expected_sign"] == 0
                    else "forward_return_pct"
                ),
                expected_sign=spec["expected_sign"],
                tags=["lot6b", "pooled", "preregistered"],
                notes=(
                    "Pre-registered before the pooled estimation ran. The "
                    "single-asset versions are separate hypotheses and are "
                    "counted separately."
                ),
            )
            keys.append(registry.preregister(hypothesis).key)
    return keys


def build_pooled_panel(spec: dict[str, Any], horizon: int) -> pd.DataFrame:
    """Long panel of both assets for one hypothesis and horizon."""
    target_col = (
        f"abs_target_{horizon}" if spec["expected_sign"] == 0 else f"target_{horizon}"
    )
    frames: dict[str, pd.DataFrame] = {}
    for asset in POOLED_ASSETS:
        frame = build_frame(asset)
        if frame.empty or target_col not in frame.columns:
            continue
        feature_col = (
            "dvol_change_30_percentile" if spec["feature"] == "dvol_change_30"
            else spec["feature"]
        )
        working = frame.dropna(subset=[target_col, feature_col])
        if len(working) < 300:
            continue
        working = working.copy()
        working["_signal"] = _signal(working, spec)
        frames[asset.value] = working
    if not frames:
        return pd.DataFrame()
    return build_panel(frames, target_col=target_col, signal_col="_signal",
                       control_cols=CONTROLS)


def _pooled_residualisation(panel: pd.DataFrame, horizon: int) -> dict[str, Any]:
    """Residualise within each asset on purged folds, then pool the residuals.

    Fitting one control model across both assets would let BTC's relationship
    between momentum and returns stand in for ETH's. Each asset gets its own
    train-only fit; only the residuals are combined.
    """
    available = [c for c in CONTROLS if c in panel.columns]
    if len(available) < 4:
        return {"status": "NO_CONTROLS"}

    excesses: list[float] = []
    p_values: list[float] = []
    per_asset: dict[str, list[float]] = {}
    for asset, chunk in panel.groupby("asset"):
        chunk = chunk.sort_index()
        index = pd.DatetimeIndex(chunk.index)
        if index.has_duplicates:
            chunk = chunk[~index.duplicated(keep="first")]
            index = pd.DatetimeIndex(chunk.index)
        folds = purged_walk_forward_folds(index, horizon_bars=horizon, n_folds=3)
        for fold in folds:
            train = fold.train_mask.reindex(chunk.index, fill_value=False)
            test = fold.test_mask.reindex(chunk.index, fill_value=False)
            result = residualise(
                chunk["y"], chunk[available], chunk["signal"], train, test
            )
            if result.status == "OK" and result.excess is not None:
                excesses.append(result.excess)
                p_values.append(result.p_value)
                per_asset.setdefault(str(asset), []).append(result.excess)

    if not excesses:
        return {"status": "INSUFFICIENT_DATA", "folds": 0}

    signs = {int(np.sign(e)) for e in excesses if e != 0}
    return {
        "status": "OK",
        "mean_excess_pct": round(float(np.mean(excesses)), 4),
        "worst_p_value": float(max(p_values)),
        "median_p_value": float(np.median(p_values)),
        "folds": len(excesses),
        "per_asset_mean": {a: round(float(np.mean(v)), 4) for a, v in per_asset.items()},
        "sign_consistent": len(signs) <= 1,
        "note": (
            "Controls are fitted per asset on training data only; the worst "
            "fold p-value is reported because a signal that survives on average "
            "but fails in one period has not survived."
        ),
    }


def test_pooled(spec: dict[str, Any], horizon: int) -> dict[str, Any]:
    out: dict[str, Any] = {
        "hypothesis_key": f"dvol_pooled__{spec['id']}__h{horizon}",
        "hypothesis_id": spec["id"],
        "hypothesis": spec["hypothesis"],
        "horizon_days": horizon,
        "expected_sign": spec["expected_sign"],
        "assets": [a.value for a in POOLED_ASSETS],
    }

    panel = build_pooled_panel(spec, horizon)
    if panel.empty:
        out["status"] = "INSUFFICIENT_DATA"
        out["note"] = "no asset produced a usable frame"
        return out

    n_events = int((panel["signal"] > 0).sum())
    out["raw_occurrences"] = n_events
    out["panel_rows"] = len(panel)
    if n_events < 40:
        out["status"] = "INSUFFICIENT_DATA"
        out["note"] = f"{n_events} pooled occurrences across both assets"
        return out

    out["status"] = "OK"
    comparison = compare_methods(panel, horizon_bars=horizon, hypothesis=spec["hypothesis"])
    out["pooling"] = comparison.to_dict()

    out["residualisation"] = _pooled_residualisation(panel, horizon)

    effective_n = comparison.effective_sample.get("effective_n_pooled", 0) or 0
    std_dev = float(panel["y"].std())
    effects = comparison.agreement.get("effects", {})
    observed = float(np.mean(list(effects.values()))) if effects else None
    out["power"] = StatisticalPowerEngine().evaluate(
        observed_effect=observed,
        std_dev=std_dev,
        effective_n_event=float(effective_n),
        horizon_bars=horizon,
        events_per_year=comparison.effective_sample.get("events_per_year", 0.0),
    )

    if spec["expected_sign"] != 0 and observed is not None:
        out["matches_hypothesis"] = bool(np.sign(observed) == spec["expected_sign"])
    elif observed is not None:
        out["matches_hypothesis"] = bool(observed > 0)

    out["_p_for_fdr"] = _representative_p(comparison.agreement.get("p_values", {}))
    return out


def _representative_p(p_values: dict[str, float | None]) -> float:
    """The least favourable p-value among the methods that produced one.

    Taking the best would be method shopping. Taking the worst means a claim
    survives multiple testing only if the most sceptical pooling assumption
    also supports it.
    """
    usable = [p for p in p_values.values() if p is not None]
    return float(max(usable)) if usable else 1.0


def _verdict(result: dict[str, Any], survives_fdr: bool) -> dict[str, Any]:
    """A pooled claim is supported only if every stage holds."""
    if result.get("status") != "OK":
        return {"verdict": result.get("status", "UNKNOWN"), "reasons": ["not testable"]}

    pooling = result.get("pooling", {})
    residual = result.get("residualisation", {})
    power = result.get("power", {})
    reasons: list[str] = []

    robust = pooling.get("verdict") == "ROBUST_ACROSS_METHODS"
    if not robust:
        reasons.append(f"pooling verdict is {pooling.get('verdict')}")
    if not survives_fdr:
        reasons.append("does not survive FDR correction across the pooled family")
    residual_ok = (
        residual.get("status") == "OK"
        and residual.get("worst_p_value") is not None
        and residual["worst_p_value"] < 0.05
        and residual.get("sign_consistent", False)
    )
    if not residual_ok:
        reasons.append(
            "does not survive residualisation against price and volatility controls"
        )
    if not result.get("matches_hypothesis", False):
        reasons.append("effect runs against the pre-registered direction")
    powered = power.get("verdict") == "ADEQUATELY_POWERED"
    if not powered:
        reasons.append("underpowered: the sample cannot detect a meaningful effect")

    if robust and survives_fdr and residual_ok and result.get("matches_hypothesis") and powered:
        return {"verdict": "SUPPORTED", "reasons": []}
    if powered and not reasons[:1]:
        return {"verdict": "REJECTED", "reasons": reasons}
    if not powered:
        return {"verdict": "INSUFFICIENT_DATA", "reasons": reasons}
    return {"verdict": "INCONCLUSIVE", "reasons": reasons}


def run_all() -> dict[str, Any]:
    keys = _preregister()
    registry = get_registry()

    results: list[dict[str, Any]] = []
    for spec in HYPOTHESES:
        for horizon in HORIZONS:
            results.append(test_pooled(spec, horizon))

    testable = [r for r in results if r.get("status") == "OK"]
    p_values = [r.pop("_p_for_fdr") for r in testable]
    survives = benjamini_hochberg(p_values, alpha=0.05) if p_values else []
    for result in results:
        result.pop("_p_for_fdr", None)

    for result, ok in zip(testable, survives, strict=True):
        result.update(_verdict(result, bool(ok)))
        result["survives_fdr"] = bool(ok)
    for result in results:
        if "verdict" not in result:
            result.update(_verdict(result, False))

    for result in results:
        status = result["verdict"]
        if status not in set(HypothesisStatus):
            status = HypothesisStatus.INSUFFICIENT_DATA
        try:
            registry.record_result(result["hypothesis_key"], status, {
                "verdict": result["verdict"],
                "reasons": result.get("reasons", []),
                "pooling_verdict": result.get("pooling", {}).get("verdict"),
                "effective_n": result.get("pooling", {})
                                     .get("effective_sample", {})
                                     .get("effective_n_pooled"),
            })
        except KeyError:
            log.warning("unregistered_hypothesis", key=result["hypothesis_key"])
    registry.save()

    counts: dict[str, int] = {}
    for result in results:
        counts[result["verdict"]] = counts.get(result["verdict"], 0) + 1

    comparisons = [r["pooling"] for r in testable if "pooling" in r]
    correlations = [
        c.get("cross_asset_correlation", {}).get("mean_correlation")
        for c in comparisons
    ]
    correlations = [c for c in correlations if c is not None]

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "assets_pooled": [a.value for a in POOLED_ASSETS],
        "assets_unavailable": {
            "SOL": "no DVOL series exists; no proxy was constructed"
        },
        "hypotheses_preregistered": len(keys),
        "multiple_testing": {
            "tests_performed": len(testable),
            "raw_significant": sum(1 for p in p_values if p < 0.05),
            "fdr_significant": int(sum(survives)),
            "p_rule": "worst p-value across the four pooling methods",
        },
        "verdict_counts": counts,
        "mean_cross_asset_correlation": (
            round(float(np.mean(correlations)), 3) if correlations else None
        ),
        "results": results,
        "note": (
            "Pooling was the only available way to raise the effective sample "
            "without waiting for years of new data. Whether it worked is "
            "reported below, including when it did not."
        ),
    }


def run_and_save(path: pathlib.Path | None = None) -> dict[str, Any]:
    payload = run_all()
    out = path or pathlib.Path("data/research/dvol_pooled.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, default=str))
    log.info("dvol_pooled_saved", path=str(out), counts=payload["verdict_counts"])
    return payload

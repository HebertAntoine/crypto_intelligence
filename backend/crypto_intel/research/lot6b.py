"""LOT 6B: how much can be extracted from the data already held.

The question is no longer whether to add indicators. It is whether the data
already collected supports any claim that would survive being taken seriously,
and if not, what specifically is missing.

The order matters and is not arbitrary:

  1  the pipeline is calibrated against known answers, because a broken
     pipeline returns "no edge" just as readily as an honest one;
  2  the detection floor is measured, because a null result means nothing
     above the smallest effect the pipeline can certify;
  3  features are checked for redundancy, because forty correlated features
     are eight questions asked five times each;
  4  families are ablated, because the question "is derivatives data worth
     collecting" is not answered by any single feature's importance;
  5  the surviving claims are placed on the evidence ladder and the funnel
     that produced them is reported alongside them.

A run that ends with nothing on the shortlist is a valid outcome and is
reported as one.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
from datetime import UTC, datetime
from itertools import pairwise
from typing import Any

import numpy as np
import pandas as pd

from ..core.enums import Asset, Timeframe
from ..history import store
from ..logging_setup import get_logger
from .ablation import family_ablation
from .controls import detection_floor, run_control_suite
from .cycles import full_robustness
from .derivatives_study import daily_funding, daily_open_interest
from .dvol_pooled import build_pooled_panel
from .dvol_pooled import run_all as run_pooled_dvol
from .dvol_study import HORIZONS, HYPOTHESES, build_frame
from .evidence import assess_evidence, build_shortlist, fdr_funnel, replication_score
from .live_experiments import LiveExperiment, get_live_registry
from .power import StatisticalPowerEngine
from .redundancy import feature_redundancy_report
from .regime_conditioned import reconstruct_regime
from .revalidation import build_controls

log = get_logger("research.lot6b")

OUTPUT_PATH = pathlib.Path("data/research/lot6b.json")
PRIMARY_ASSET = Asset.BTC
CALIBRATION_HORIZONS = [7, 14, 30]


# --- reproducibility ------------------------------------------------------


def _git_revision() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5, check=True,
        ).stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return "unknown"


def _hash_file(path: pathlib.Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    except OSError:
        return "missing"


def reproducibility_stamp() -> dict[str, Any]:
    """Enough to tell whether two runs should have produced the same numbers.

    Code hash, data coverage and library versions. If a number cannot be
    reproduced and these three match, the difference is a bug rather than
    drift; if they differ, the comparison was never valid.
    """
    modules = sorted(pathlib.Path("backend/crypto_intel/research").glob("*.py"))
    code_hash = hashlib.sha256(
        "".join(_hash_file(p) for p in modules).encode()
    ).hexdigest()[:16]

    coverage: dict[str, Any] = {}
    for asset in Asset.tradables():
        candles = store.load_candles(asset, Timeframe.D1)
        coverage[asset.value] = {
            "rows": len(candles),
            "first": str(candles.index[0])[:10] if len(candles) else None,
            "last": str(candles.index[-1])[:10] if len(candles) else None,
            "hash": (
                hashlib.sha256(
                    pd.util.hash_pandas_object(candles["close"]).values.tobytes()
                ).hexdigest()[:16] if len(candles) else "empty"
            ),
        }

    import numpy
    import scipy
    import sklearn

    return {
        "git_revision": _git_revision(),
        "research_code_hash": code_hash,
        "modules_hashed": len(modules),
        "data_coverage": coverage,
        "library_versions": {
            "numpy": numpy.__version__,
            "pandas": pd.__version__,
            "scipy": scipy.__version__,
            "scikit-learn": sklearn.__version__,
        },
        "stamped_at": datetime.now(UTC).isoformat(),
    }


# --- frames ---------------------------------------------------------------


def build_full_feature_frame(asset: Asset) -> pd.DataFrame:
    """Every family on one daily index, for redundancy and ablation."""
    frame = build_frame(asset)
    if frame.empty:
        candles = store.load_candles(asset, Timeframe.D1)
        if candles.empty:
            return pd.DataFrame()
        frame = build_controls(candles)
        frame["close"] = candles["close"]
        frame["regime"] = reconstruct_regime(candles)
        for horizon in HORIZONS:
            frame[f"target_{horizon}"] = (
                candles["close"].shift(-horizon) - candles["close"]
            ) / candles["close"] * 100

    index = pd.DatetimeIndex(frame.index)
    funding = daily_funding(asset, index)
    if not funding.dropna().empty:
        frame["funding_rate"] = funding
        frame["funding_percentile"] = funding.rolling(365, min_periods=180).rank(pct=True) * 100

    open_interest = daily_open_interest(asset, index)
    if not open_interest.dropna().empty:
        frame["oi_change_7"] = open_interest.pct_change(7, fill_method=None) * 100
        frame["oi_change_30"] = open_interest.pct_change(30, fill_method=None) * 100
    return frame


MIN_COLUMN_COVERAGE = 0.60


def drop_sparse_columns(
    frame: pd.DataFrame, minimum: float = MIN_COLUMN_COVERAGE
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Remove columns too sparse to survive a row-wise dropna.

    One column present on 1 of 1991 rows silently reduces the whole frame to
    nothing, and every downstream stage then reports "insufficient data" with
    no indication of which column caused it. That happened here: the historical
    open-interest backfill wrote to a different metric name than the research
    code read, so `oi_change_30` arrived with a single value and emptied every
    frame it touched. Dropping sparse columns loudly is what makes such a
    mismatch visible instead of fatal.
    """
    if frame.empty:
        return frame, {"dropped": {}, "kept": [], "rows_after_dropna": 0}
    coverage = {c: float(frame[c].notna().mean()) for c in frame.columns}
    dropped = {c: round(v, 3) for c, v in coverage.items() if v < minimum}
    kept = [c for c in frame.columns if c not in dropped]
    trimmed = frame[kept]
    return trimmed, {
        "dropped": dropped,
        "kept": kept,
        "minimum_coverage": minimum,
        "rows_after_dropna": len(trimmed.dropna()),
        "note": (
            f"{len(dropped)} column(s) below {minimum:.0%} coverage were removed "
            f"before analysis: {', '.join(sorted(dropped)) or 'none'}."
        ),
    }


# --- stages ---------------------------------------------------------------


def stage_calibration(asset: Asset = PRIMARY_ASSET) -> dict[str, Any]:
    """Controls and detection floor: can the pipeline see anything at all?"""
    candles = store.load_candles(asset, Timeframe.D1)
    if candles.empty:
        return {"status": "NO_DATA"}
    controls = build_controls(candles)
    regimes = reconstruct_regime(candles)

    floors: dict[str, Any] = {}
    suite: dict[str, Any] = {}
    for horizon in CALIBRATION_HORIZONS:
        target = (
            candles["close"].shift(-horizon) - candles["close"]
        ) / candles["close"] * 100
        aligned = pd.concat(
            [target.rename("y"), regimes.rename("r"), controls], axis=1
        ).dropna()
        if len(aligned) < 400:
            continue
        control_cols = [c for c in controls.columns if c in aligned.columns]
        floors[f"h{horizon}"] = detection_floor(
            aligned["y"], aligned[control_cols], aligned["r"], horizon
        )
        if horizon == 30:
            signal = (
                aligned["return_20"] > aligned["return_20"].quantile(0.85)
            ).astype(float)
            suite = run_control_suite(
                aligned["y"], signal, aligned[control_cols], aligned["r"], horizon,
            )

    above = [
        key for key, payload in floors.items()
        if payload.get("floor_above_meaningful")
    ]
    return {
        "status": "OK",
        "asset": asset.value,
        "control_suite": suite,
        "detection_floors": floors,
        "horizons_where_floor_exceeds_meaningful": above,
        "verdict": (
            "PIPELINE_CALIBRATED_BUT_INSENSITIVE" if suite.get("negatives_passed")
            and above else
            "PIPELINE_CALIBRATED" if suite.get("pipeline_trustworthy") else
            "PIPELINE_SUSPECT"
        ),
        "note": (
            "The pipeline does not manufacture findings from noise, which makes "
            "its positive results meaningful. But its detection floor sits above "
            "the effect size declared as meaningful at every horizon tested, "
            "which means its null results are silent in exactly the band worth "
            "knowing about."
            if above else
            "The pipeline is calibrated on noise and can detect effects at the "
            "declared meaningful size."
        ),
    }


def stage_redundancy(asset: Asset = PRIMARY_ASSET) -> dict[str, Any]:
    frame = build_full_feature_frame(asset)
    if frame.empty:
        return {"status": "NO_DATA"}
    exclude = {"close", "regime", "realised_vol"}
    columns = [
        c for c in frame.columns
        if not c.startswith(("target_", "abs_target_")) and c not in exclude
    ]
    trimmed, coverage = drop_sparse_columns(frame[columns])
    report = feature_redundancy_report(trimmed)
    payload = report.to_dict()
    payload["status"] = "OK" if payload["n_features"] else "NO_USABLE_FEATURES"
    payload["asset"] = asset.value
    payload["coverage"] = coverage
    return payload


def stage_ablation(asset: Asset = PRIMARY_ASSET, horizon: int = 30) -> dict[str, Any]:
    frame = build_full_feature_frame(asset)
    if frame.empty or f"target_{horizon}" not in frame.columns:
        return {"status": "NO_DATA"}
    target = frame[f"target_{horizon}"]
    features = frame[[c for c in frame.columns if not c.startswith(("target_", "abs_target_"))]]
    trimmed, coverage = drop_sparse_columns(features)
    payload = family_ablation(trimmed, target, horizon_bars=horizon).to_dict()
    payload["coverage"] = coverage
    return payload


def stage_pooled_dvol() -> dict[str, Any]:
    return run_pooled_dvol()


def stage_robustness() -> dict[str, Any]:
    """Leave-one-out on every pooled DVOL hypothesis."""
    specs = {spec["id"]: spec for spec in HYPOTHESES}
    out: dict[str, Any] = {}
    for spec_id, spec in specs.items():
        for horizon in HORIZONS:
            panel = build_pooled_panel(spec, horizon)
            if panel.empty:
                continue
            out[f"{spec_id}__h{horizon}"] = full_robustness(panel, is_panel=True)
    counts: dict[str, int] = {}
    for payload in out.values():
        verdict = payload["overall_verdict"]
        counts[verdict] = counts.get(verdict, 0) + 1
    return {"status": "OK", "by_hypothesis": out, "verdict_counts": counts}


def _evidence_for(
    result: dict[str, Any], robustness: dict[str, Any] | None
) -> dict[str, Any]:
    """Place one pooled result on the ladder."""
    pooling = result.get("pooling", {})
    agreement = pooling.get("agreement", {})
    residual = result.get("residualisation", {})
    power = result.get("power", {})

    effects = agreement.get("effects", {})
    effect = float(np.mean(list(effects.values()))) if effects else 0.0
    n_significant = agreement.get("n_methods_significant", 0)

    observed = bool(effects)
    baseline_relative = bool(effect != 0 and n_significant >= 1)
    stratified = n_significant >= 1
    controlled = bool(
        residual.get("status") == "OK"
        and residual.get("worst_p_value") is not None
        and residual["worst_p_value"] < 0.05
        and residual.get("sign_consistent")
    )
    robust = bool(robustness and robustness.get("overall_verdict") == "ROBUST")
    replicated = bool(
        pooling.get("verdict") == "ROBUST_ACROSS_METHODS" and robust
    )

    assessment = assess_evidence(
        claim=f"{result.get('hypothesis')} @{result.get('horizon_days')}d",
        observed=observed,
        baseline_relative=baseline_relative,
        stratified=stratified,
        controlled=controlled,
        robust=robust,
        replicated=replicated,
        live_confirmed=False,
        underpowered=power.get("verdict") != "ADEQUATELY_POWERED",
        details={
            "effect_pct": round(effect, 4),
            "methods_significant": n_significant,
            "pooling_verdict": pooling.get("verdict"),
            "robustness_verdict": (
                robustness.get("overall_verdict") if robustness else None
            ),
            "residual_worst_p": residual.get("worst_p_value"),
            "effective_n": pooling.get("effective_sample", {}).get("effective_n_pooled"),
        },
    )
    payload = assessment.to_dict()
    payload["effect_pct"] = round(effect, 4)
    payload["decidable_before"] = power.get("decidable_before", "UNKNOWN")
    payload["hypothesis_key"] = result.get("hypothesis_key")
    payload["horizon_days"] = result.get("horizon_days")
    return payload


def stage_evidence(
    pooled: dict[str, Any], robustness: dict[str, Any]
) -> dict[str, Any]:
    by_hypothesis = robustness.get("by_hypothesis", {})
    assessments: list[dict[str, Any]] = []
    for result in pooled.get("results", []):
        key = f"{result.get('hypothesis_id')}__h{result.get('horizon_days')}"
        assessments.append(_evidence_for(result, by_hypothesis.get(key)))

    levels: dict[str, int] = {}
    for assessment in assessments:
        name = assessment["level_name"]
        levels[name] = levels.get(name, 0) + 1

    # The funnel must be nested: each stage filters the survivors of the one
    # above it, never the full set. Counting stages independently produced a
    # funnel where a later stage held more claims than an earlier one, which is
    # not a funnel but a list of unrelated filters.
    testable = [r for r in pooled.get("results", []) if r.get("status") == "OK"]
    by_key = {
        f"{r.get('hypothesis_id')}__h{r.get('horizon_days')}": r for r in testable
    }
    level_by_key = {
        f"{a['hypothesis_key'].removeprefix('dvol_pooled__')}": a
        for a in assessments if a.get("hypothesis_key")
    }

    def _agreement(result: dict[str, Any]) -> dict[str, Any]:
        return result.get("pooling", {}).get("agreement", {})

    survivors = list(by_key)
    stages: list[dict[str, Any]] = [
        {"stage": "pre-registered",
         "count": pooled.get("hypotheses_preregistered", 0),
         "detail": "declared in the registry before estimation"},
        {"stage": "testable", "count": len(survivors),
         "detail": "enough pooled occurrences to estimate"},
    ]

    survivors = [
        k for k in survivors
        if _agreement(by_key[k]).get("n_methods_significant", 0) > 0
    ]
    stages.append({
        "stage": "significant under any pooling method", "count": len(survivors),
        "detail": "at least one of four methods rejects zero",
    })

    survivors = [
        k for k in survivors
        if _agreement(by_key[k]).get("n_methods_significant", 0)
        == len(_agreement(by_key[k]).get("effects", {}) or [1])
    ]
    stages.append({
        "stage": "significant under all methods", "count": len(survivors),
        "detail": "the result does not depend on the pooling assumption",
    })

    survivors = [k for k in survivors if (level_by_key.get(k, {}).get("level", 0)) >= 4]
    stages.append({
        "stage": "survives residualisation", "count": len(survivors),
        "detail": "worst-fold p below 0.05 against price and volatility controls",
    })

    survivors = [k for k in survivors if (level_by_key.get(k, {}).get("level", 0)) >= 5]
    stages.append({
        "stage": "survives leave-one-out", "count": len(survivors),
        "detail": "keeps sign and magnitude without any single year, asset or cycle",
    })

    funnel = fdr_funnel(stages)
    # Stages are nested by construction; assert it rather than trust it.
    counts = [row["count"] for row in funnel["stages"]]
    funnel["monotonic"] = all(a >= b for a, b in pairwise(counts))
    funnel["independent_filters"] = {
        "reached_level_4_controlled": sum(1 for a in assessments if a["level"] >= 4),
        "reached_level_5_robust": sum(1 for a in assessments if a["level"] >= 5),
        "note": (
            "These count every claim reaching the level regardless of the "
            "earlier stages, which is why they can exceed the nested funnel. "
            "A claim can survive residualisation while failing the requirement "
            "that all four pooling methods agree."
        ),
    }

    return {
        "status": "OK",
        "assessments": assessments,
        "by_level": levels,
        "highest_level_reached": max((a["level"] for a in assessments), default=0),
        "funnel": funnel,
        "n_actionable": sum(1 for a in assessments if a["actionable"]),
    }


def stage_replication(pooled: dict[str, Any]) -> dict[str, Any]:
    """Per-asset estimates treated as replications of the pooled effect."""
    out: dict[str, Any] = {}
    for result in pooled.get("results", []):
        if result.get("status") != "OK":
            continue
        methods = result.get("pooling", {}).get("methods", {})
        per_asset = methods.get("meta_analysis", {}).get("per_asset", {})
        residual_per_asset = result.get("residualisation", {}).get("per_asset_mean", {})
        fixed = methods.get("fixed_effects", {}).get("beta")
        if fixed is None or not per_asset:
            continue
        replications = {f"asset_{a}": v["effect"] for a, v in per_asset.items()}
        replications.update(
            {f"residualised_{a}": v for a, v in residual_per_asset.items()}
        )
        key = f"{result['hypothesis_id']}__h{result['horizon_days']}"
        out[key] = replication_score(float(fixed), replications)

    verdicts: dict[str, int] = {}
    for payload in out.values():
        verdict = payload.get("verdict", payload.get("status", "UNKNOWN"))
        verdicts[verdict] = verdicts.get(verdict, 0) + 1
    return {"status": "OK", "by_hypothesis": out, "verdict_counts": verdicts}


def stage_shortlist(evidence: dict[str, Any]) -> dict[str, Any]:
    candidates = [
        {
            "claim": a["claim"],
            "hypothesis_key": a.get("hypothesis_key"),
            "evidence_level": a["level"],
            "level_name": a["level_name"],
            "effect_pct": a.get("effect_pct"),
            "decidable_before": a.get("decidable_before", "UNKNOWN"),
            "blocked_at": a.get("blocked_at"),
            "underpowered": a.get("underpowered"),
        }
        for a in evidence.get("assessments", [])
        if a["level"] >= 2
    ]
    return build_shortlist(candidates)


def stage_live_experiments(shortlist: dict[str, Any]) -> dict[str, Any]:
    """Register the shortlist for prospective test and report maturity."""
    registry = get_live_registry()
    engine = StatisticalPowerEngine()
    for entry in shortlist.get("shortlist", []):
        horizon = 30
        claim = entry["claim"]
        if "@" in claim and claim.rsplit("@", 1)[1].endswith("d"):
            try:
                horizon = int(claim.rsplit("@", 1)[1].rstrip("d"))
            except ValueError:
                horizon = 30
        effect = entry.get("effect_pct") or 0.0
        assessment = engine.evaluate(
            observed_effect=effect, std_dev=20.0,
            effective_n_event=0.0, horizon_bars=horizon, events_per_year=12.0,
        )
        required = assessment["requirement"].get("required_effective_n") or 0
        registry.register(LiveExperiment(
            id=entry.get("hypothesis_key") or claim,
            claim=claim,
            hypothesis_key=entry.get("hypothesis_key", ""),
            horizon_days=horizon,
            expected_effect_pct=float(effect),
            expected_sign=int(np.sign(effect)),
            required_observations=int(min(required, 200)),
            expected_events_per_year=12.0,
            note=(
                "Registered from the LOT 6B shortlist. Records what the rule "
                "would have said; places no order."
            ),
        ))
    registry.save()
    return registry.report()


# --- runner ---------------------------------------------------------------


def run_all() -> dict[str, Any]:
    log.info("lot6b_start")
    calibration = stage_calibration()
    redundancy = stage_redundancy()
    ablation = stage_ablation()
    pooled = stage_pooled_dvol()
    robustness = stage_robustness()
    evidence = stage_evidence(pooled, robustness)
    replication = stage_replication(pooled)
    shortlist = stage_shortlist(evidence)
    live = stage_live_experiments(shortlist)

    highest = evidence.get("highest_level_reached", 0)
    actionable = evidence.get("n_actionable", 0)
    verdict = (
        "NO_SIGNAL_SUPPORTED" if actionable == 0 and highest < 5
        else "CANDIDATES_IDENTIFIED_NONE_ACTIONABLE" if actionable == 0
        else "ACTIONABLE_CANDIDATES"
    )

    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "lot": "6B",
        "reproducibility": reproducibility_stamp(),
        "calibration": calibration,
        "redundancy": redundancy,
        "ablation": ablation,
        "pooled_dvol": pooled,
        "robustness": robustness,
        "evidence": evidence,
        "replication": replication,
        "shortlist": shortlist,
        "live_experiments": live,
        "verdict": verdict,
        "note": (
            "The lot's purpose was to find out whether the data already held "
            "supports a defensible claim. The answer is recorded above whether "
            "or not it is the desired one."
        ),
    }
    log.info("lot6b_done", verdict=verdict, highest_level=highest)
    return payload


def run_and_save(path: pathlib.Path | None = None) -> dict[str, Any]:
    payload = run_all()
    out = path or OUTPUT_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, default=str))
    log.info("lot6b_saved", path=str(out))
    return payload

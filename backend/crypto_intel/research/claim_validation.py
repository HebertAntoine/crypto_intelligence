"""Test what the educational material claims against what the data shows.

"A falling wedge is generally bullish" is a hypothesis. This module finds the
historical occurrences the detectors can identify, measures what followed, and
returns a verdict - including CONTRADICTED, which is a perfectly good outcome
and has already happened once (LOT 4 found inverse head-and-shoulders preceded
BELOW-baseline returns on BTC, the opposite of the textbook reading).

The output is designed for the confrontation view: THEORY says X, the SOURCE
says X, HUMAN EXAMPLES show Y, the DATA shows Z. Where they disagree, the data
wins, and the disagreement itself is displayed rather than hidden.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import ttest_ind

from ..core.enums import Asset, Timeframe
from ..history import store
from ..logging_setup import get_logger
from ..structure.patterns import build_context, detect_all
from ..trader_knowledge.educational import load_claims
from .regime_conditioned import reconstruct_regime
from .stats import benjamini_hochberg
from .structural_research import effective_sample

log = get_logger("research.claim_validation")

HORIZONS = [7, 14, 30]
MIN_OCCURRENCES = 20
MIN_EFFECTIVE_N = 20
NEGLIGIBLE_EFFECT_PCT = 0.5
WINDOW = 150

# Which detector answers which concept. Concepts with no detector are reported
# as UNTESTABLE rather than quietly skipped.
CONCEPT_TO_DETECTOR: dict[str, str] = {
    "double_top": "double_top",
    "double_bottom": "double_bottom",
    "triple_top": "triple_top",
    "triple_bottom": "triple_bottom",
    "head_and_shoulders": "head_and_shoulders",
    "inverse_head_and_shoulders": "inverse_head_and_shoulders",
    "ascending_triangle": "ascending_triangle",
    "descending_triangle": "descending_triangle",
    "symmetrical_triangle": "symmetrical_triangle",
    "rising_wedge": "rising_wedge",
    "falling_wedge": "falling_wedge",
    "bull_flag": "bull_flag",
    "bear_flag": "bear_flag",
}


class ClaimVerdict(StrEnum):
    SUPPORTED = "SUPPORTED"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    NOT_SUPPORTED = "NOT_SUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    UNTESTABLE = "UNTESTABLE"


def _stratified_excess(
    forward: pd.Series, mask: pd.Series, regimes: pd.Series,
    min_events: int = 10, min_baseline: int = 20,
) -> dict[str, Any]:
    """Weighted within-regime excess, so the market's drift cancels."""
    aligned = pd.concat(
        [forward.rename("fwd"), regimes.rename("regime"), mask.rename("event")], axis=1
    ).dropna(subset=["fwd", "regime"])
    if aligned.empty:
        return {"excess": None}

    weighted_event = weighted_baseline = 0.0
    total_weight = 0
    residual_events: list[float] = []
    residual_baseline: list[float] = []
    regimes_used = 0

    for _, chunk in aligned.groupby("regime"):
        events = chunk.loc[chunk["event"], "fwd"]
        baseline = chunk.loc[~chunk["event"], "fwd"]
        if len(events) < min_events or len(baseline) < min_baseline:
            continue
        weight = len(events)
        baseline_mean = float(baseline.mean())
        weighted_event += float(events.mean()) * weight
        weighted_baseline += baseline_mean * weight
        total_weight += weight
        regimes_used += 1
        residual_events.extend((events - baseline_mean).tolist())
        residual_baseline.extend((baseline - baseline_mean).tolist())

    if not total_weight or len(residual_events) < 30 or len(residual_baseline) < 30:
        return {"excess": None}

    t_stat, p_value = ttest_ind(residual_events, residual_baseline, equal_var=False)
    return {
        "excess": (weighted_event - weighted_baseline) / total_weight,
        "baseline": round(weighted_baseline / total_weight, 3),
        "p_value": float(p_value), "t_stat": round(float(t_stat), 3),
        "regimes_used": regimes_used,
    }


def _detections(asset: Asset, timeframe: Timeframe) -> tuple[pd.DataFrame, dict[str, list]]:
    """All detector firings across history, grouped by pattern name."""
    df = store.load_candles(asset, timeframe)
    if df.empty or len(df) < WINDOW + 60:
        return df, {}

    by_pattern: dict[str, list] = {}
    for i in range(WINDOW, len(df)):
        window = df.iloc[:i + 1]
        try:
            ctx = build_context(window, timeframe)
            if ctx is None:
                continue
            for pattern in detect_all(ctx):
                by_pattern.setdefault(pattern.name, []).append(df.index[i])
        except Exception:
            continue
    return df, by_pattern


def validate_claim(
    claim: dict[str, Any], asset: Asset, df: pd.DataFrame,
    detections: dict[str, list], timeframe: Timeframe,
) -> dict[str, Any]:
    """Measure one directional claim against a same-regime baseline."""
    concept = claim.get("concept", "")
    direction = claim.get("implied_direction")
    detector = CONCEPT_TO_DETECTOR.get(concept)

    out: dict[str, Any] = {
        "claim_id": claim.get("id"), "concept": concept,
        "statement": claim.get("statement"),
        "implied_direction": direction,
        "source": claim.get("source"), "source_url": claim.get("source_url"),
        "asset": asset.value, "timeframe": timeframe.value,
    }

    if detector is None:
        out["verdict"] = ClaimVerdict.UNTESTABLE.value
        out["note"] = (
            f"no deterministic detector exists for '{concept}', so this claim cannot "
            "be tested; that is a gap in our detectors, not evidence about the claim"
        )
        return out

    timestamps = pd.DatetimeIndex(detections.get(detector, []))
    out["raw_occurrences"] = len(timestamps)

    if len(timestamps) < MIN_OCCURRENCES:
        out["verdict"] = ClaimVerdict.INSUFFICIENT_DATA.value
        out["note"] = (
            f"{len(timestamps)} occurrences on {asset.value} {timeframe.value}, below "
            f"the {MIN_OCCURRENCES} minimum"
        )
        return out

    closes = df["close"]
    regimes = reconstruct_regime(df)
    mask = pd.Series(False, index=df.index)
    mask.loc[mask.index.isin(timestamps)] = True

    horizons_out: dict[str, Any] = {}
    for horizon in HORIZONS:
        forward = (closes.shift(-horizon) - closes) / closes * 100.0
        events = forward[mask].dropna()
        # Regime-MATCHED baseline. Filtering to "regimes where the pattern
        # occurs" selects the whole sample for any pattern that appears in
        # every regime, which silently restores the market drift this study
        # exists to remove.
        stratified = _stratified_excess(forward, mask, regimes)
        baseline = forward[~mask].dropna()
        if len(events) < MIN_OCCURRENCES or stratified.get("excess") is None:
            horizons_out[f"{horizon}d"] = {
                "status": "INSUFFICIENT_DATA",
                "note": (
                    "no regime had enough events and baseline days for a stratified "
                    "comparison"
                ),
            }
            continue

        excess = stratified["excess"]
        p_value = stratified["p_value"]
        t_stat = stratified["t_stat"]
        sample = effective_sample(pd.DatetimeIndex(events.index), horizon, 1.0)

        by_year: dict[str, float] = {}
        for year, chunk in events.groupby(events.index.year):
            base_year = baseline[baseline.index.year == year]
            if len(chunk) >= 3 and len(base_year) >= 20:
                by_year[str(year)] = round(float(chunk.mean() - base_year.mean()), 3)
        consistency = None
        if len(by_year) >= 3:
            values = list(by_year.values())
            positive = sum(1 for v in values if v > 0)
            consistency = round(
                max(positive, len(values) - positive) / len(values) * 100, 1
            )

        horizons_out[f"{horizon}d"] = {
            "status": "OK",
            "raw_n": sample["raw_n"], "effective_n": sample["effective_n"],
            "mean_return_pct": round(float(events.mean()), 3),
            "unconditional_baseline_pct": round(float(baseline.mean()), 3),
            "regime_matched_baseline_pct": stratified["baseline"],
            "regimes_used": stratified["regimes_used"],
            "excess_vs_same_regime_pct": round(excess, 3),
            "win_rate": round(float((events > 0).mean() * 100), 1),
            "p_value": float(p_value), "t_stat": round(float(t_stat), 3),
            "by_year": by_year, "sign_consistency_pct": consistency,
        }

    out["horizons"] = horizons_out
    out.update(_verdict(direction, horizons_out))
    return out


def _verdict(direction: str | None, horizons: dict[str, Any]) -> dict[str, Any]:
    """Compare the claim's implied direction to the measured excess."""
    usable = {k: v for k, v in horizons.items() if v.get("status") == "OK"}
    if not usable:
        return {
            "verdict": ClaimVerdict.INSUFFICIENT_DATA.value,
            "note": "no horizon had enough data for a baseline comparison",
        }

    expected_sign = 1 if direction == "BULLISH" else -1 if direction == "BEARISH" else 0
    if expected_sign == 0:
        return {
            "verdict": ClaimVerdict.UNTESTABLE.value,
            "note": "the claim implies no direction, so there is nothing to confirm",
        }

    agreeing: list[str] = []
    opposing: list[str] = []
    for key, cell in usable.items():
        excess = cell["excess_vs_same_regime_pct"]
        if abs(excess) < NEGLIGIBLE_EFFECT_PCT:
            continue
        significant = cell["p_value"] < 0.05
        stable = (cell.get("sign_consistency_pct") or 0) >= 70
        enough = cell["effective_n"] >= MIN_EFFECTIVE_N
        # Stability GATES the verdict. An earlier version only annotated it,
        # so an effect confined to one era could be reported as SUPPORTED -
        # the precise mistake the LOT 4 funding study was corrected for.
        if not (significant and enough and stable):
            continue
        if np.sign(excess) == expected_sign:
            agreeing.append(f"{key} ({excess:+.2f}%)")
        else:
            opposing.append(f"{key} ({excess:+.2f}%)")

    if opposing and not agreeing:
        return {
            "verdict": ClaimVerdict.CONTRADICTED.value,
            "note": (
                f"The data runs OPPOSITE to the claim at {', '.join(opposing)}. The "
                f"claim says {direction.lower()}; measured excess against a same-regime "
                "baseline has the other sign and survives significance and sample "
                "checks."
            ),
        }
    if agreeing and not opposing:
        return {
            "verdict": ClaimVerdict.SUPPORTED.value,
            "note": f"Measured excess agrees with the claim at {', '.join(agreeing)}.",
        }
    if agreeing and opposing:
        return {
            "verdict": ClaimVerdict.PARTIALLY_SUPPORTED.value,
            "note": (
                f"Mixed: agrees at {', '.join(agreeing)} and disagrees at "
                f"{', '.join(opposing)}."
            ),
        }
    return {
        "verdict": ClaimVerdict.NOT_SUPPORTED.value,
        "note": (
            "No horizon shows an effect that is simultaneously large enough, "
            "statistically distinguishable, built on enough independent "
            "observations, AND consistent in sign across years. The claim is not "
            "supported - and not refuted either."
        ),
    }


def run_all(
    assets: list[Asset] | None = None, timeframe: Timeframe = Timeframe.D1
) -> dict[str, Any]:
    assets = assets or Asset.tradables()
    claims = [c for c in load_claims() if c.get("testable")]
    if not claims:
        return {"status": "NO_CLAIMS", "note": "run the educational ingestion first"}

    results: dict[str, Any] = {}
    all_p_values: list[tuple[str, float]] = []

    for asset in assets:
        df, detections = _detections(asset, timeframe)
        if df.empty:
            results[asset.value] = {"status": "NO_DATA"}
            continue
        asset_results = []
        for claim in claims:
            outcome = validate_claim(claim, asset, df, detections, timeframe)
            asset_results.append(outcome)
            for key, cell in (outcome.get("horizons") or {}).items():
                if cell.get("status") == "OK":
                    all_p_values.append(
                        (f"{asset.value}|{outcome['concept']}|{key}", cell["p_value"])
                    )
        results[asset.value] = {"status": "OK", "claims": asset_results}

    # FDR across every claim, asset and horizon at once.
    survives = benjamini_hochberg([p for _, p in all_p_values], alpha=0.05)
    survivors = {
        name for (name, _), ok in zip(all_p_values, survives, strict=True) if ok
    }

    counts: dict[str, int] = {}
    for asset_result in results.values():
        for claim in asset_result.get("claims", []):
            verdict = claim.get("verdict", "UNKNOWN")
            counts[verdict] = counts.get(verdict, 0) + 1

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "timeframe": timeframe.value,
        "claims_tested": len(claims),
        "results": results,
        "verdict_counts": counts,
        "multiple_testing": {
            "hypotheses_tested": len(all_p_values),
            "raw_significant": sum(1 for _, p in all_p_values if p < 0.05),
            "fdr_significant": len(survivors),
            "expected_false_positives": round(len(all_p_values) * 0.05, 1),
            "survivors": sorted(survivors),
        },
        "note": (
            "Educational claims are hypotheses, not rules. CONTRADICTED and "
            "NOT_SUPPORTED are informative outcomes and are reported as prominently "
            "as SUPPORTED."
        ),
    }

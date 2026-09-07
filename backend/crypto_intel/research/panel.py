"""Pooling BTC and ETH: does two assets mean twice the evidence?

The single-asset DVOL study ended underpowered - the best result had eighteen
effective observations and needed several hundred. Pooling is the only lever
that does not require waiting years, so it is worth doing properly rather than
by concatenating two frames and hoping.

Four methods, because they disagree in informative ways:

  1. asset-normalised   each asset's target is standardised by its own
                        dispersion, then the two are treated as one sample.
                        Assumes the effect is the same in volatility units.
  2. fixed effects      asset dummies absorb level differences, standard
                        errors clustered on date blocks. Assumes one common
                        slope, makes no distributional claim.
  3. hierarchical       per-asset estimates shrunk toward the grand mean by
                        their own precision. Assumes the true effects are
                        drawn from a common distribution.
  4. meta-analysis      inverse-variance combination of two independent
                        estimates, with a heterogeneity test.

Where all four agree the pooled result is robust to the assumption. Where they
disagree, the disagreement is the finding.

The number that governs everything here is the cross-asset correlation of the
targets. BTC and ETH daily returns correlate around 0.8, so two assets are
nowhere near two independent samples, and the honest gain in effective sample
is far below the doubling that row counts suggest. That gain is measured and
reported rather than assumed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from ..logging_setup import get_logger
from .event_sampler import sample_independent_events
from .inference import count_independent_blocks, pooled_effect

log = get_logger("research.panel")


def build_panel(
    frames: dict[str, pd.DataFrame],
    target_col: str,
    signal_col: str,
    control_cols: list[str] | None = None,
) -> pd.DataFrame:
    """Stack per-asset frames into a long panel indexed by date."""
    keep = [target_col, signal_col, *list(control_cols or [])]
    parts: list[pd.DataFrame] = []
    for asset, frame in frames.items():
        available = [c for c in keep if c in frame.columns]
        if target_col not in available or signal_col not in available:
            continue
        part = frame[available].dropna(subset=[target_col, signal_col]).copy()
        if part.empty:
            continue
        part = part.rename(columns={target_col: "y", signal_col: "signal"})
        part["asset"] = asset
        parts.append(part)
    if not parts:
        return pd.DataFrame()
    return pd.concat(parts).sort_index()


def cross_asset_correlation(panel: pd.DataFrame, column: str = "y") -> dict[str, Any]:
    """How much independent information a second asset actually adds.

    With two series correlated at rho, the variance of their mean is
    (1 + rho) / 2 times the variance of one. The effective number of
    independent series is therefore 2 / (1 + rho), which is 1.05 at rho = 0.9
    and 2.0 only at rho = 0.
    """
    wide = panel.pivot_table(values=column, index=panel.index, columns="asset")
    wide = wide.dropna()
    assets = list(wide.columns)
    if len(assets) < 2 or len(wide) < 30:
        return {"status": "INSUFFICIENT_DATA", "assets": assets, "overlapping_dates": len(wide)}

    matrix = wide.corr()
    pairs = {
        f"{a}~{b}": round(float(matrix.loc[a, b]), 3)
        for i, a in enumerate(assets) for b in assets[i + 1:]
    }
    mean_rho = float(np.mean(list(pairs.values()))) if pairs else 0.0
    k = len(assets)
    # Effective series count under an equicorrelation approximation.
    effective_series = k / (1 + (k - 1) * mean_rho) if mean_rho > -1 / (k - 1) else float(k)

    return {
        "status": "OK",
        "assets": assets,
        "overlapping_dates": len(wide),
        "pairwise": pairs,
        "mean_correlation": round(mean_rho, 3),
        "effective_independent_series": round(effective_series, 2),
        "naive_multiplier": k,
        "information_gain_pct": round((effective_series - 1) * 100, 1),
        "note": (
            f"{k} assets correlated at {mean_rho:.2f} carry the information of "
            f"{effective_series:.2f} independent series, not {k}. Pooling raises "
            f"the effective sample by about {(effective_series - 1) * 100:.0f}%, "
            "not by 100% per extra asset."
        ),
    }


# --- the four methods -----------------------------------------------------


def _per_asset_estimates(
    panel: pd.DataFrame, horizon_bars: int
) -> dict[str, dict[str, float]]:
    """Difference in means per asset, with a block-clustered standard error.

    The naive two-sample standard error is wrong here by a wide margin. A
    30-day forward return observed on consecutive days is nearly the same
    observation, so the iid formula divides by a sample size the data does not
    have. Using it made the meta-analysis return p = 3e-13 on eighteen
    genuinely independent events - a number produced entirely by the
    assumption.

    Instead the effect is computed within each block of `horizon_bars`
    consecutive dates, and the standard error comes from the dispersion of
    those block estimates. Blocks overlap nothing, so the central limit theorem
    applies to them even though it does not apply to the rows.
    """
    out: dict[str, dict[str, float]] = {}
    for asset, chunk in panel.groupby("asset"):
        events = chunk.loc[chunk["signal"] > 0, "y"].dropna()
        others = chunk.loc[chunk["signal"] <= 0, "y"].dropna()
        if len(events) < 10 or len(others) < 20:
            continue
        effect = float(events.mean() - others.mean())

        dates = pd.DatetimeIndex(chunk.index)
        unique = dates.unique().sort_values()
        rank = pd.Series(np.arange(len(unique)), index=unique)
        block_id = (rank.reindex(dates).to_numpy() // horizon_bars).astype(int)
        block_effects: list[float] = []
        for block in np.unique(block_id):
            rows = chunk[block_id == block]
            e = rows.loc[rows["signal"] > 0, "y"].dropna()
            o = rows.loc[rows["signal"] <= 0, "y"].dropna()
            if len(e) >= 1 and len(o) >= 1:
                block_effects.append(float(e.mean() - o.mean()))

        if len(block_effects) >= 5:
            se = float(np.std(block_effects, ddof=1) / np.sqrt(len(block_effects)))
            n_blocks = len(block_effects)
        else:
            # Too few blocks for clustered inference; fall back and say so.
            se = float(np.sqrt(
                events.var(ddof=1) / len(events) + others.var(ddof=1) / len(others)
            ))
            n_blocks = len(block_effects)

        out[str(asset)] = {
            "effect": round(effect, 4),
            "std_error": round(se, 4),
            "n_event": len(events),
            "n_baseline": len(others),
            "n_blocks": n_blocks,
            "clustered": n_blocks >= 5,
        }
    return out


def method_asset_normalised(panel: pd.DataFrame, horizon_bars: int) -> dict[str, Any]:
    """Standardise each asset's target by its own dispersion, then pool.

    Puts ETH's larger swings on the same scale as BTC's, so the pooled effect
    is expressed in standard deviations. Converted back to percent using the
    average dispersion, which is only meaningful if the two are comparable -
    the ratio is reported so that assumption can be checked.
    """
    frame = panel.copy()
    scales = {
        str(asset): round(float(chunk["y"].std()), 4)
        for asset, chunk in frame.groupby("asset")
        if float(chunk["y"].std()) > 0
    }
    if not scales:
        return {"status": "NO_DATA"}
    # transform keeps row alignment; concat + reindex would not on duplicate dates.
    grouped = frame.groupby("asset")["y"]
    frame["y_z"] = (frame["y"] - grouped.transform("mean")) / grouped.transform("std")

    events = frame.loc[frame["signal"] > 0, "y_z"].dropna()
    others = frame.loc[frame["signal"] <= 0, "y_z"].dropna()
    if len(events) < 20 or len(others) < 40:
        return {"status": "INSUFFICIENT_DATA", "n_event": len(events)}

    effect_z = float(events.mean() - others.mean())
    _, p_value = stats.ttest_ind(events, others, equal_var=False)

    # Clustered standard error on date blocks: the t test above ignores overlap.
    dates = pd.DatetimeIndex(frame.index)
    unique = dates.unique().sort_values()
    rank = pd.Series(np.arange(len(unique)), index=unique)
    blocks = (rank.reindex(dates).to_numpy() // horizon_bars).astype(int)
    frame["_block"] = blocks
    block_effects = []
    for _, chunk in frame.groupby("_block"):
        e = chunk.loc[chunk["signal"] > 0, "y_z"].dropna()
        o = chunk.loc[chunk["signal"] <= 0, "y_z"].dropna()
        if len(e) >= 1 and len(o) >= 1:
            block_effects.append(float(e.mean() - o.mean()))
    clustered_p = None
    if len(block_effects) >= 5:
        _, clustered_p = stats.ttest_1samp(block_effects, 0.0)
        clustered_p = float(clustered_p)

    mean_scale = float(np.mean(list(scales.values()))) if scales else 1.0
    ratio = (max(scales.values()) / min(scales.values())) if len(scales) > 1 else 1.0
    return {
        "status": "OK",
        "method": "asset_normalised",
        "effect_sd": round(effect_z, 4),
        "effect_pct_equivalent": round(effect_z * mean_scale, 4),
        "p_value_naive": float(p_value),
        "p_value_clustered": clustered_p,
        "n_event": len(events),
        "n_baseline": len(others),
        "n_blocks": len(block_effects),
        "per_asset_scale": scales,
        "scale_ratio": round(ratio, 2),
        "note": (
            f"Effect of {effect_z:.3f} standard deviations. The two assets differ "
            f"in dispersion by a factor of {ratio:.2f}; the percent equivalent "
            "assumes that difference is pure scale."
        ),
    }


def method_fixed_effects(panel: pd.DataFrame, horizon_bars: int) -> dict[str, Any]:
    """Asset dummies, one common slope, block-clustered standard errors."""
    result = pooled_effect(panel, horizon_bars=horizon_bars)
    payload = result.to_dict()
    payload["method"] = "fixed_effects"
    return payload


def method_hierarchical(panel: pd.DataFrame, horizon_bars: int) -> dict[str, Any]:
    """Partial pooling: shrink each asset toward the grand mean by precision.

    A DerSimonian-Laird random-effects estimator. Where the between-asset
    variance is zero the result collapses to full pooling; where it is large
    each asset keeps its own estimate. The shrinkage factor is reported so the
    degree of pooling is visible rather than implicit.
    """
    per_asset = _per_asset_estimates(panel, horizon_bars)
    if len(per_asset) < 2:
        return {"status": "INSUFFICIENT_DATA", "assets": list(per_asset), "method": "hierarchical"}

    effects = np.array([v["effect"] for v in per_asset.values()])
    variances = np.array([v["std_error"] ** 2 for v in per_asset.values()])
    variances = np.where(variances <= 0, np.nan, variances)
    if np.isnan(variances).any():
        return {"status": "DEGENERATE_VARIANCE", "method": "hierarchical"}

    weights = 1 / variances
    fixed_mean = float((weights * effects).sum() / weights.sum())
    q_stat = float((weights * (effects - fixed_mean) ** 2).sum())
    df = len(effects) - 1
    c = float(weights.sum() - (weights**2).sum() / weights.sum())
    tau2 = max(0.0, (q_stat - df) / c) if c > 0 else 0.0

    re_weights = 1 / (variances + tau2)
    pooled = float((re_weights * effects).sum() / re_weights.sum())
    se = float(np.sqrt(1 / re_weights.sum()))
    shrunk = {
        asset: round(float(
            (effect / var + pooled / tau2) / (1 / var + 1 / tau2)
        ), 4) if tau2 > 0 else round(pooled, 4)
        for (asset, _), effect, var in zip(per_asset.items(), effects, variances, strict=True)
    }

    return {
        "status": "OK",
        "method": "hierarchical",
        "pooled_effect": round(pooled, 4),
        "std_error": round(se, 4),
        "t_stat": round(pooled / se, 3) if se > 0 else None,
        "p_value": float(2 * (1 - stats.norm.cdf(abs(pooled / se)))) if se > 0 else None,
        "between_asset_variance": round(tau2, 5),
        "full_pooling": tau2 == 0.0,
        "shrunk_estimates": shrunk,
        "raw_estimates": {a: v["effect"] for a, v in per_asset.items()},
        "note": (
            "Between-asset variance is zero, so the assets are statistically "
            "indistinguishable and full pooling applies."
            if tau2 == 0.0 else
            f"Between-asset variance {tau2:.4f} exceeds what sampling error explains; "
            "the assets are shrunk toward each other but keep distinct estimates."
        ),
    }


def method_meta_analysis(panel: pd.DataFrame, horizon_bars: int) -> dict[str, Any]:
    """Inverse-variance combination with an explicit heterogeneity test.

    Treats each asset as a separate study. This is the most conservative of the
    four: it never borrows strength across assets beyond the weighting, and its
    Q test says plainly whether combining them is defensible at all.
    """
    per_asset = _per_asset_estimates(panel, horizon_bars)
    if len(per_asset) < 2:
        return {"status": "INSUFFICIENT_DATA", "assets": list(per_asset), "method": "meta_analysis"}

    effects = np.array([v["effect"] for v in per_asset.values()])
    variances = np.array([v["std_error"] ** 2 for v in per_asset.values()])
    if (variances <= 0).any():
        return {"status": "DEGENERATE_VARIANCE", "method": "meta_analysis"}

    weights = 1 / variances
    pooled = float((weights * effects).sum() / weights.sum())
    se = float(np.sqrt(1 / weights.sum()))
    q_stat = float((weights * (effects - pooled) ** 2).sum())
    df = len(effects) - 1
    q_p = float(1 - stats.chi2.cdf(q_stat, df)) if df > 0 else None
    i_squared = max(0.0, (q_stat - df) / q_stat * 100) if q_stat > 0 else 0.0

    signs = {int(np.sign(e)) for e in effects if e != 0}
    return {
        "status": "OK",
        "method": "meta_analysis",
        "pooled_effect": round(pooled, 4),
        "std_error": round(se, 4),
        "p_value": float(2 * (1 - stats.norm.cdf(abs(pooled / se)))) if se > 0 else None,
        "ci_95": [round(pooled - 1.96 * se, 4), round(pooled + 1.96 * se, 4)],
        "per_asset": per_asset,
        "heterogeneity_q": round(q_stat, 3),
        "heterogeneity_p": q_p,
        "i_squared_pct": round(i_squared, 1),
        "signs_agree": len(signs) <= 1,
        "combinable": bool(q_p is None or q_p >= 0.10),
        "all_clustered": all(v.get("clustered", False) for v in per_asset.values()),
        "note": (
            f"I2 = {i_squared:.0f}% of the variation across assets is beyond "
            "sampling error. "
            + (
                "The assets are consistent and combining them is defensible."
                if (q_p is None or q_p >= 0.10)
                else "The assets disagree more than chance allows; the pooled "
                     "number should not be quoted as a single effect."
            )
        ),
    }


# --- comparison -----------------------------------------------------------


@dataclass(slots=True)
class PoolingComparison:
    hypothesis: str = ""
    horizon_days: int = 0
    methods: dict[str, Any] = field(default_factory=dict)
    correlation: dict[str, Any] = field(default_factory=dict)
    agreement: dict[str, Any] = field(default_factory=dict)
    effective_sample: dict[str, Any] = field(default_factory=dict)
    verdict: str = "UNKNOWN"
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "hypothesis": self.hypothesis, "horizon_days": self.horizon_days,
            "methods": self.methods, "cross_asset_correlation": self.correlation,
            "agreement": self.agreement, "effective_sample": self.effective_sample,
            "verdict": self.verdict, "note": self.note,
        }


def _first_not_none(payload: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    """First present key, treating 0.0 as a value rather than as absence.

    `payload.get("p_value") or payload.get("fallback")` silently discards a
    p-value of exactly 0.0, because 0.0 is falsy. That drops precisely the most
    significant results and counts them as having no p-value at all.
    """
    for key in keys:
        value = payload.get(key)
        if value is not None:
            return float(value)
    return None


def _extract_effect(payload: dict[str, Any]) -> tuple[float | None, float | None]:
    if payload.get("status") != "OK":
        return None, None
    effect = _first_not_none(payload, ("beta", "pooled_effect", "effect_pct_equivalent"))
    if effect is None:
        return None, None
    return effect, _first_not_none(payload, ("p_value", "p_value_clustered"))


def compare_methods(
    panel: pd.DataFrame, horizon_bars: int, hypothesis: str = ""
) -> PoolingComparison:
    """Run all four, then judge whether they tell the same story."""
    comparison = PoolingComparison(hypothesis=hypothesis, horizon_days=horizon_bars)
    if panel.empty:
        comparison.verdict = "NO_DATA"
        return comparison

    comparison.methods = {
        "asset_normalised": method_asset_normalised(panel, horizon_bars),
        "fixed_effects": method_fixed_effects(panel, horizon_bars),
        "hierarchical": method_hierarchical(panel, horizon_bars),
        "meta_analysis": method_meta_analysis(panel, horizon_bars),
    }
    comparison.correlation = cross_asset_correlation(panel)

    effects: dict[str, float] = {}
    p_values: dict[str, float | None] = {}
    for name, payload in comparison.methods.items():
        effect, p_value = _extract_effect(payload)
        if effect is not None:
            effects[name] = effect
            p_values[name] = p_value

    if len(effects) < 2:
        comparison.verdict = "INSUFFICIENT_DATA"
        comparison.note = f"only {len(effects)} of four methods produced an estimate"
        return comparison

    values = list(effects.values())
    signs = {int(np.sign(v)) for v in values if v != 0}
    spread = float(max(values) - min(values))
    scale = float(np.mean([abs(v) for v in values])) or 1.0
    significant = [n for n, p in p_values.items() if p is not None and p < 0.05]

    comparison.agreement = {
        "effects": {k: round(v, 4) for k, v in effects.items()},
        "p_values": {k: (round(v, 4) if v is not None else None) for k, v in p_values.items()},
        "signs_agree": len(signs) <= 1,
        "spread": round(spread, 4),
        "spread_relative_to_effect": round(spread / scale, 2),
        "methods_significant": significant,
        "n_methods_significant": len(significant),
    }

    # Effective sample of the pooled panel: independent blocks over unique dates.
    event_dates = pd.DatetimeIndex(panel.loc[panel["signal"] > 0].index.unique())
    all_dates = pd.DatetimeIndex(panel.index.unique()).sort_values()
    sampled = sample_independent_events(event_dates, horizon_bars)
    blocks = count_independent_blocks(event_dates, all_dates, horizon_bars)
    rho_gain = comparison.correlation.get("effective_independent_series", 1.0)
    comparison.effective_sample = {
        "unique_event_dates": len(event_dates),
        "non_overlapping_events": sampled.n_independent,
        "independent_blocks": blocks,
        "effective_n_single_asset": min(sampled.n_independent, blocks),
        "effective_n_pooled": round(min(sampled.n_independent, blocks) * rho_gain, 1),
        "gain_from_pooling": (
            f"x{rho_gain:.2f}" if isinstance(rho_gain, int | float) else "unknown"
        ),
        "events_per_year": sampled.events_per_year,
        "note": (
            "Pooling multiplies the effective sample by the number of effective "
            "independent series, not by the number of assets. Rows double; "
            "information does not."
        ),
    }

    all_significant = len(significant) == len(effects)
    none_significant = len(significant) == 0
    consistent = comparison.agreement["signs_agree"] and comparison.agreement[
        "spread_relative_to_effect"
    ] < 1.0

    if none_significant:
        comparison.verdict = "NO_POOLED_EFFECT"
        comparison.note = (
            "No method finds a pooled effect distinguishable from zero. Pooling "
            "did not rescue the single-asset result."
        )
    elif all_significant and consistent:
        comparison.verdict = "ROBUST_ACROSS_METHODS"
        comparison.note = (
            "All four methods agree in sign and magnitude and each rejects zero. "
            "The pooled effect does not depend on the pooling assumption."
        )
    elif consistent:
        comparison.verdict = "METHOD_DEPENDENT"
        comparison.note = (
            f"The estimates agree in direction, but only {len(significant)} of "
            f"{len(effects)} methods reject zero: "
            f"{', '.join(significant)}. Significance rests on the assumption, "
            "not on the data."
        )
    else:
        comparison.verdict = "INCONSISTENT"
        comparison.note = (
            "The methods disagree in sign or by more than the effect itself. "
            "No pooled number should be quoted."
        )
    return comparison


def panel_report(comparisons: list[PoolingComparison]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for comparison in comparisons:
        counts[comparison.verdict] = counts.get(comparison.verdict, 0) + 1
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "comparisons": [c.to_dict() for c in comparisons],
        "verdict_counts": counts,
        "n_comparisons": len(comparisons),
    }

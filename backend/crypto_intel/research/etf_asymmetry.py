"""ETFAsymmetryEngine - inflows and outflows are not mirror images.

LOT 2 hinted that extreme ETH outflows carried more information than equivalent
inflows. A single correlation coefficient cannot express that: it assumes the
relationship is symmetric by construction. So each side is measured separately.

Categories use trailing percentiles, not fixed dollar thresholds, so "extreme"
means extreme relative to the recent past rather than to a number chosen with
hindsight.

Nothing is asserted unless the data supports it. If inflows and outflows carry
the same information, the engine says so.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from ..core.enums import Asset
from ..logging_setup import get_logger
from .etf_study import build_flow_series, build_price_frame
from .stats import benjamini_hochberg, describe_returns, excursions, forward_returns
from .walkforward import walk_forward_ic

log = get_logger("research.etf_asymmetry")

HORIZONS = [1, 3, 7, 14, 30]
TRAILING_WINDOW = 252

# Percentile boundaries. Deliberately asymmetric in naming so the two tails are
# never silently merged.
CATEGORIES: list[tuple[str, float, float, str]] = [
    ("extreme_outflow", 0.0, 10.0, "Daily flow in the bottom decile of the trailing year"),
    ("moderate_outflow", 10.0, 35.0, "Below-average flow"),
    ("neutral", 35.0, 65.0, "Middle of the trailing distribution"),
    ("moderate_inflow", 65.0, 90.0, "Above-average flow"),
    ("extreme_inflow", 90.0, 100.01, "Daily flow in the top decile of the trailing year"),
]


def categorise_flows(flows: pd.Series, window: int = TRAILING_WINDOW) -> pd.Series:
    """Label each day by where its flow sits in the TRAILING distribution.

    A trailing rank rather than a full-history percentile keeps the category
    definition free of look-ahead: the label at day t only uses days up to t.

    The rank is computed on the DENSE series (days that actually have a flow),
    never on a version reindexed onto the price calendar. Reindexing first
    fills the pre-launch years with NaN, and NaN comparisons silently evaluate
    to False - which collapsed 388 of 664 BTC days into the bottom decile and
    left the top decile empty.
    """
    dense = flows.dropna()
    if dense.empty:
        return pd.Series(index=flows.index, dtype=object)

    ranks = dense.rolling(window, min_periods=60).apply(
        lambda w: float((w[-1] > w[:-1]).sum()) / max(1, len(w) - 1) * 100.0, raw=True
    )
    labels = pd.Series(index=dense.index, dtype=object)
    for name, low, high in ((c[0], c[1], c[2]) for c in CATEGORIES):
        labels[(ranks >= low) & (ranks < high)] = name

    # Re-expand onto the original index so callers can align with prices.
    return labels.reindex(flows.index)


def analyse_asymmetry(asset: Asset, min_sample: int = 20) -> dict[str, Any]:
    """Forward-return statistics per flow category, with excursions and stability."""
    if asset not in (Asset.BTC, Asset.ETH):
        return {
            "asset": asset.value, "available": False,
            "reason": f"UNAVAILABLE - {asset.value} has no US spot ETF",
        }

    flows = build_flow_series(asset)
    prices = build_price_frame(asset)
    if flows.empty or prices.empty:
        return {
            "asset": asset.value, "available": False,
            "reason": "UNAVAILABLE - missing ETF flows or price history",
        }

    aligned = flows.reindex(prices.index)
    categories = categorise_flows(aligned)
    fwd = forward_returns(prices["close"], HORIZONS)
    close, high, low = prices["close"], prices["high"], prices["low"]

    # Baseline restricted to the window where flows exist at all - comparing a
    # 2024-2026 category against a 2017-2026 baseline would measure the gap
    # between two market eras, not the effect of the flow.
    observable = aligned.dropna().index
    if len(observable) < 100:
        return {
            "asset": asset.value, "available": False,
            "reason": f"INSUFFICIENT_DATA - only {len(observable)} days with ETF flows",
        }
    window_start, window_end = observable.min(), observable.max()
    baseline_index = fwd.index[(fwd.index >= window_start) & (fwd.index <= window_end)]

    results: dict[str, Any] = {}
    flat_p: list[float | None] = []
    flat_keys: list[tuple[str, str]] = []

    excursion_cache: dict[int, tuple[pd.Series, pd.Series]] = {}

    for name, _low, _high, description in CATEGORIES:
        dates = categories[categories == name].index
        dates = dates[(dates >= window_start) & (dates <= window_end)]

        entry: dict[str, Any] = {
            "category": name, "description": description, "n": len(dates), "horizons": {},
        }
        if len(dates) < min_sample:
            entry["available"] = False
            entry["reason"] = f"INSUFFICIENT_DATA - {len(dates)} occurrences (need {min_sample})"
            results[name] = entry
            continue

        entry["available"] = True
        for h in HORIZONS:
            subset = fwd.loc[fwd.index.isin(dates), f"fwd_{h}"]
            stats = describe_returns(subset)
            baseline = describe_returns(fwd.loc[baseline_index, f"fwd_{h}"])

            if h not in excursion_cache:
                excursion_cache[h] = excursions(high, low, close, h)
            mfe, mae = excursion_cache[h]
            mfe_subset = mfe[mfe.index.isin(dates)].dropna()
            mae_subset = mae[mae.index.isin(dates)].dropna()

            edge = (
                round(stats.mean - baseline.mean, 4)
                if stats.mean is not None and baseline.mean is not None else None
            )
            ci = _confidence_interval(subset)

            entry["horizons"][f"{h}d"] = {
                **stats.to_dict(),
                "baseline_mean": baseline.mean,
                "baseline_win_rate": baseline.win_rate,
                "edge_vs_baseline": edge,
                "ci95_low": ci[0], "ci95_high": ci[1],
                "ci_excludes_zero": bool(ci[0] is not None and (ci[0] > 0 or ci[1] < 0)),
                "mfe_median": (
                    round(float(mfe_subset.median()), 3) if len(mfe_subset) else None
                ),
                "mae_median": (
                    round(float(mae_subset.median()), 3) if len(mae_subset) else None
                ),
            }
            flat_p.append(stats.p_value)
            flat_keys.append((name, f"{h}d"))

        results[name] = entry

    # 5 categories x 5 horizons = 25 tests; correct before claiming anything.
    survives = benjamini_hochberg(flat_p, alpha=0.05)
    for (name, horizon), passed in zip(flat_keys, survives, strict=True):
        results[name]["horizons"][horizon]["significant_fdr"] = bool(passed)

    # Out-of-sample stability of the asymmetry itself: does a signed indicator
    # (extreme outflow = -1, extreme inflow = +1) hold up across windows?
    signed = pd.Series(0.0, index=categories.index)
    signed[categories == "extreme_outflow"] = -1.0
    signed[categories == "extreme_inflow"] = 1.0
    signed[categories == "moderate_outflow"] = -0.5
    signed[categories == "moderate_inflow"] = 0.5
    signed = signed[signed.index.isin(observable)]
    stability = walk_forward_ic(signed, fwd["fwd_7"])

    comparison = compare_tails(results)

    return {
        "asset": asset.value,
        "available": True,
        "period": {
            "start": window_start.isoformat(),
            "end": window_end.isoformat(),
            "days": len(observable),
        },
        "categories": results,
        "asymmetry": comparison,
        "walk_forward_signed": stability,
        "note": (
            "Categories use a trailing 252-day percentile rank, so 'extreme' means "
            "extreme relative to the preceding year, not to a threshold chosen with "
            "hindsight. Significance is FDR-corrected across the 25 category x horizon "
            "tests."
        ),
    }


def _confidence_interval(values: pd.Series, confidence: float = 0.95) -> tuple[float | None, float | None]:
    """Normal-approximation CI for the mean. None when the sample is too small."""
    from scipy import stats as scipy_stats

    clean = values.dropna()
    n = len(clean)
    if n < 20:
        return None, None
    mean = float(clean.mean())
    sem = float(clean.std(ddof=1) / np.sqrt(n))
    if sem == 0:
        return round(mean, 4), round(mean, 4)
    margin = scipy_stats.t.ppf(0.5 + confidence / 2, n - 1) * sem
    return round(mean - margin, 4), round(mean + margin, 4)


def compare_tails(results: dict[str, Any]) -> dict[str, Any]:
    """Is the outflow tail more informative than the inflow tail, or not?

    Compares |edge| on each side at every horizon. A conclusion is only drawn
    when at least one side is statistically supported - otherwise the answer is
    that no asymmetry has been demonstrated.
    """
    inflow = results.get("extreme_inflow", {})
    outflow = results.get("extreme_outflow", {})

    if not inflow.get("available") or not outflow.get("available"):
        return {
            "assessable": False,
            "reason": "One or both tails have too few occurrences to compare",
        }

    per_horizon: dict[str, Any] = {}
    outflow_stronger = 0
    inflow_stronger = 0
    supported = 0

    for h in HORIZONS:
        key = f"{h}d"
        in_cell = inflow["horizons"].get(key, {})
        out_cell = outflow["horizons"].get(key, {})
        in_edge = in_cell.get("edge_vs_baseline")
        out_edge = out_cell.get("edge_vs_baseline")
        if in_edge is None or out_edge is None:
            continue

        in_supported = in_cell.get("significant_fdr") or in_cell.get("ci_excludes_zero")
        out_supported = out_cell.get("significant_fdr") or out_cell.get("ci_excludes_zero")
        if in_supported or out_supported:
            supported += 1

        stronger = "outflow" if abs(out_edge) > abs(in_edge) else "inflow"
        if stronger == "outflow":
            outflow_stronger += 1
        else:
            inflow_stronger += 1

        per_horizon[key] = {
            "inflow_edge": in_edge,
            "outflow_edge": out_edge,
            "inflow_supported": bool(in_supported),
            "outflow_supported": bool(out_supported),
            "abs_ratio": (
                round(abs(out_edge) / abs(in_edge), 2) if abs(in_edge) > 1e-9 else None
            ),
            "stronger_tail": stronger,
        }

    total = outflow_stronger + inflow_stronger
    if total == 0:
        return {"assessable": False, "reason": "No horizon produced comparable edges"}

    # A claim requires both a consistent direction AND at least one horizon
    # where the effect is statistically supported.
    if supported == 0:
        conclusion = (
            "No asymmetry demonstrated: neither tail shows an effect that survives "
            "correction or whose confidence interval excludes zero. The apparent "
            "difference is within noise."
        )
        verdict = "NO_ASYMMETRY_DEMONSTRATED"
    elif outflow_stronger >= total * 0.7:
        conclusion = (
            f"Extreme outflows carry a larger measured effect than equivalent inflows "
            f"at {outflow_stronger}/{total} horizons, with {supported} horizon(s) "
            "statistically supported."
        )
        verdict = "OUTFLOWS_MORE_INFORMATIVE"
    elif inflow_stronger >= total * 0.7:
        conclusion = (
            f"Extreme inflows carry a larger measured effect than equivalent outflows "
            f"at {inflow_stronger}/{total} horizons, with {supported} horizon(s) "
            "statistically supported."
        )
        verdict = "INFLOWS_MORE_INFORMATIVE"
    else:
        conclusion = (
            f"Neither tail dominates ({outflow_stronger} vs {inflow_stronger} horizons) - "
            "the relationship looks broadly symmetric."
        )
        verdict = "SYMMETRIC"

    return {
        "assessable": True,
        "verdict": verdict,
        "conclusion": conclusion,
        "horizons_outflow_stronger": outflow_stronger,
        "horizons_inflow_stronger": inflow_stronger,
        "horizons_statistically_supported": supported,
        "by_horizon": per_horizon,
    }


def run_all(assets: list[Asset] | None = None) -> dict[str, Any]:
    assets = assets or [Asset.BTC, Asset.ETH]
    return {a.value: analyse_asymmetry(a) for a in assets}

"""Score audit: for each asset, is each domain score actually worth its weight?

Produces the table the LOT 3 brief asks for - current weight, observations,
correlation with forward returns, monotonicity, train/validation/OOS stability,
and a verdict from a fixed vocabulary.

The audit measures. It never edits `config/scoring.yaml`; candidate weights are
proposed separately and promotion stays a human decision.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from ..config_loader import asset_weights
from ..core.enums import Asset
from ..logging_setup import get_logger
from .calibration import RECONSTRUCTORS
from .etf_study import build_price_frame
from .stats import (
    chronological_split,
    decompose_ic,
    forward_returns,
    lagged_correlation,
)
from .walkforward import bucket_monotonicity, walk_forward_ic

log = get_logger("research.audit")

HORIZONS = [1, 3, 7, 14, 30]
PRIMARY_HORIZON = 7

VERDICTS = (
    "USEFUL", "WEAK", "UNSTABLE", "NO_MEASURABLE_VALUE", "INSUFFICIENT_DATA",
)


def audit_domain(asset: Asset, domain: str, horizon: int = PRIMARY_HORIZON) -> dict[str, Any]:
    """Measure one domain score against forward returns."""
    weights = asset_weights(asset.value)
    weight = weights.get(domain, 0.0)

    builder = RECONSTRUCTORS.get(domain)
    if builder is None:
        return {
            "asset": asset.value, "domain": domain, "current_weight": weight,
            "horizon": f"{horizon}d", "n": 0,
            "verdict": "INSUFFICIENT_DATA",
            "reason": (
                f"No historical reconstruction exists for '{domain}'. It can only be "
                "calibrated from live reports once enough have accumulated."
            ),
        }

    if weight <= 0:
        return {
            "asset": asset.value, "domain": domain, "current_weight": 0.0,
            "horizon": f"{horizon}d", "n": 0,
            "verdict": "INSUFFICIENT_DATA",
            "reason": (
                f"Weight is 0 for {asset.value} - the domain is deliberately excluded "
                "(e.g. no US spot ETF for SOL) and is not scored."
            ),
        }

    scores = builder(asset)
    prices = build_price_frame(asset)
    if scores.empty or prices.empty:
        return {
            "asset": asset.value, "domain": domain, "current_weight": weight,
            "horizon": f"{horizon}d", "n": 0,
            "verdict": "INSUFFICIENT_DATA",
            "reason": "UNAVAILABLE - missing score history or price history",
        }

    fwd = forward_returns(prices["close"], [horizon])
    target = fwd[f"fwd_{horizon}"]
    joined = pd.concat([scores.rename("score"), target.rename("fwd")], axis=1).dropna()

    if len(joined) < 100:
        return {
            "asset": asset.value, "domain": domain, "current_weight": weight,
            "horizon": f"{horizon}d", "n": len(joined),
            "verdict": "INSUFFICIENT_DATA",
            "reason": f"Only {len(joined)} usable observations (need 100)",
        }

    ic, p_value, n = lagged_correlation(joined["score"], joined["fwd"])
    monotonicity = bucket_monotonicity(joined["score"], joined["fwd"])
    # A global IC can look healthy while being purely a between-period effect.
    decomposition = decompose_ic(joined["score"], joined["fwd"])
    wf = walk_forward_ic(joined["score"], joined["fwd"])
    stability = (wf.get("stability") or {}) if wf.get("available") else {}

    # Train / validation / OOS on the same series, as a second opinion on
    # stability that does not depend on the walk-forward window sizing.
    split = chronological_split(pd.DatetimeIndex(joined.index))
    split_results: dict[str, Any] = {}
    for name, window in (
        ("train", split.train), ("validation", split.validation), ("oos", split.oos)
    ):
        if window is None:
            continue
        subset = joined[(joined.index >= window[0]) & (joined.index <= window[1])]
        window_ic, window_p, window_n = lagged_correlation(subset["score"], subset["fwd"])
        split_results[name] = {
            "ic": window_ic, "p_value": window_p, "n": window_n,
            "significant": bool(window_p is not None and window_p < 0.05 and window_n >= 30),
        }

    signs = [
        1 if r["ic"] > 0 else -1
        for r in split_results.values() if r.get("ic") is not None
    ]
    sign_stable = bool(signs and len(set(signs)) == 1)

    # How concentrated the score is: a score that sits in one bucket 99% of the
    # time cannot discriminate anything, whatever its correlation says.
    concentration = _concentration(joined["score"])

    verdict, reason = _verdict(
        ic=ic, p_value=p_value, n=n,
        monotonic=monotonicity.get("monotonic", False),
        sign_stable=sign_stable,
        stability_score=stability.get("stability_score", 0.0),
        stability_verdict=stability.get("verdict"),
        concentration=concentration,
        decomposition=decomposition,
    )

    return {
        "asset": asset.value,
        "domain": domain,
        "current_weight": weight,
        "horizon": f"{horizon}d",
        "n": n,
        "period": {
            "start": joined.index.min().isoformat(),
            "end": joined.index.max().isoformat(),
        },
        "ic": ic,
        "p_value": p_value,
        "significant": bool(p_value is not None and p_value < 0.05 and n >= 30),
        "monotonic": monotonicity.get("monotonic", False),
        "monotonicity": monotonicity,
        "splits": split_results,
        "sign_stable_across_splits": sign_stable,
        "walk_forward": wf,
        "stability_score": stability.get("stability_score", 0.0),
        "stability_verdict": stability.get("verdict", "INSUFFICIENT_DATA"),
        "concentration": concentration,
        "ic_decomposition": decomposition,
        "verdict": verdict,
        "reason": reason,
    }


def _concentration(scores: pd.Series) -> dict[str, Any]:
    """Share of observations sitting in the single most common score bucket.

    The derivatives score sat in 'neutral' on 99% of days - correlation could
    never reveal that, but it makes the score useless in practice.
    """
    from .calibration import BUCKETS

    counts: dict[str, int] = {}
    for label, low, high in BUCKETS:
        counts[label] = int(((scores >= low) & (scores < high)).sum())
    total = sum(counts.values()) or 1
    dominant = max(counts.items(), key=lambda kv: kv[1])
    return {
        "buckets": counts,
        "dominant_bucket": dominant[0],
        "dominant_share": round(dominant[1] / total * 100.0, 1),
        "distinct_buckets_used": sum(1 for v in counts.values() if v >= total * 0.02),
        "discriminating": bool(dominant[1] / total < 0.80),
    }


def _verdict(
    ic: float | None,
    p_value: float | None,
    n: int,
    monotonic: bool,
    sign_stable: bool,
    stability_score: float,
    stability_verdict: str | None,
    concentration: dict[str, Any],
    decomposition: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """Assign one of the five verdicts, with the reasoning attached."""
    if ic is None or n < 100:
        return "INSUFFICIENT_DATA", f"Only {n} usable observations"

    # A correlation that exists only between periods measures the era, not the
    # moment. It cannot be used for timing, whatever its p-value says.
    if decomposition and decomposition.get("globally_inflated"):
        return (
            "NO_MEASURABLE_VALUE",
            f"Global IC {ic:+.3f} is not reproduced within periods "
            f"(mean within-period IC {decomposition['mean_within_ic']:+.3f}, "
            f"{decomposition['periods_positive']}/{decomposition['periods_total']} "
            "periods positive). The score separates bullish eras from bearish ones "
            "rather than good days from bad days.",
        )

    # A score that never leaves one bucket cannot inform anything, whatever
    # its correlation coefficient happens to be.
    if not concentration["discriminating"]:
        return (
            "NO_MEASURABLE_VALUE",
            f"{concentration['dominant_share']:.0f}% of observations fall in the "
            f"'{concentration['dominant_bucket']}' bucket - the score barely varies, "
            "so it cannot discriminate between outcomes",
        )

    significant = p_value is not None and p_value < 0.05

    if not significant and abs(ic) < 0.03:
        return (
            "NO_MEASURABLE_VALUE",
            f"IC {ic:+.3f} (p={p_value}) - no relationship with forward returns "
            f"distinguishable from zero on {n} observations",
        )

    if not sign_stable or stability_verdict == "UNSTABLE":
        return (
            "UNSTABLE",
            f"IC {ic:+.3f} but the sign is not consistent across train/validation/OOS "
            f"or across walk-forward windows (stability {stability_score:.0f}/100)",
        )

    if significant and monotonic and stability_score >= 50:
        return (
            "USEFUL",
            f"IC {ic:+.3f} (p={p_value}), monotonic across buckets, and stable "
            f"({stability_score:.0f}/100) - it orders outcomes and keeps doing so",
        )

    if significant or monotonic:
        detail = []
        if significant:
            detail.append(f"significant (p={p_value})")
        if monotonic:
            detail.append("monotonic")
        if stability_score < 50:
            detail.append(f"but stability is only {stability_score:.0f}/100")
        return "WEAK", f"IC {ic:+.3f}: " + ", ".join(detail)

    return (
        "NO_MEASURABLE_VALUE",
        f"IC {ic:+.3f} is neither significant nor monotonic",
    )


def audit_asset(asset: Asset, horizons: list[int] | None = None) -> dict[str, Any]:
    """Audit every weighted domain for one asset."""
    horizons = horizons or [PRIMARY_HORIZON]
    weights = asset_weights(asset.value)

    domains: dict[str, Any] = {}
    for domain in sorted(weights, key=lambda d: -weights[d]):
        per_horizon = {}
        for h in horizons:
            per_horizon[f"{h}d"] = audit_domain(asset, domain, h)
        primary = per_horizon.get(f"{PRIMARY_HORIZON}d") or next(iter(per_horizon.values()))
        domains[domain] = {**primary, "by_horizon": per_horizon}

    weighted_useful = sum(
        weights.get(d, 0.0) for d, r in domains.items() if r["verdict"] == "USEFUL"
    )
    weighted_worthless = sum(
        weights.get(d, 0.0) for d, r in domains.items()
        if r["verdict"] in ("NO_MEASURABLE_VALUE", "UNSTABLE")
    )
    weighted_unmeasured = sum(
        weights.get(d, 0.0) for d, r in domains.items() if r["verdict"] == "INSUFFICIENT_DATA"
    )

    return {
        "asset": asset.value,
        "domains": domains,
        "summary": {
            "weight_on_useful": round(weighted_useful, 3),
            "weight_on_worthless_or_unstable": round(weighted_worthless, 3),
            "weight_on_unmeasured": round(weighted_unmeasured, 3),
            "verdicts": {
                verdict: [d for d, r in domains.items() if r["verdict"] == verdict]
                for verdict in VERDICTS
            },
        },
    }


def audit_all(assets: list[Asset] | None = None, horizons: list[int] | None = None) -> dict[str, Any]:
    assets = assets or Asset.tradables()
    return {
        "assets": {a.value: audit_asset(a, horizons) for a in assets},
        "note": (
            "Scores are RECONSTRUCTED by replaying current logic over historical candles. "
            "This measures whether the logic carries information, not what the system "
            "would have output at the time. Domains without a reconstruction "
            "(on-chain, macro, news, regulation, whale, liquidity, defi) cannot be "
            "audited this way and are marked INSUFFICIENT_DATA until live reports "
            "accumulate."
        ),
    }


def format_audit_table(results: dict[str, Any]) -> str:
    """Console rendering of the audit."""
    lines: list[str] = []
    add = lines.append
    width = 108
    add("=" * width)
    add("SCORE AUDIT - is each domain worth its weight?")
    add("=" * width)

    for asset_value, asset_result in results["assets"].items():
        add("")
        add(f"{asset_value}")
        add("-" * width)
        add(
            f"  {'domain':13s}{'weight':>8s}{'n':>7s}{'IC7d':>9s}{'p':>10s}"
            f"{'mono':>6s}{'stable':>8s}{'stab':>6s}{'concentr':>10s}  verdict"
        )
        for domain, r in asset_result["domains"].items():
            if r["verdict"] == "INSUFFICIENT_DATA" and not r.get("ic"):
                add(
                    f"  {domain:13s}{r['current_weight']:>8.2f}{r.get('n', 0):>7}"
                    f"{'—':>9s}{'—':>10s}{'—':>6s}{'—':>8s}{'—':>6s}{'—':>10s}  "
                    f"INSUFFICIENT_DATA"
                )
                continue
            p = f"{r['p_value']:.4f}" if r.get("p_value") is not None else "n/a"
            concentration = r.get("concentration") or {}
            add(
                f"  {domain:13s}{r['current_weight']:>8.2f}{r['n']:>7}"
                f"{r['ic']:>+9.3f}{p:>10s}"
                f"{str(r['monotonic'])[:5]:>6s}"
                f"{str(r['sign_stable_across_splits'])[:5]:>8s}"
                f"{r['stability_score']:>6.0f}"
                f"{concentration.get('dominant_share', 0):>9.0f}%  {r['verdict']}"
            )

        summary = asset_result["summary"]
        add(
            f"  -> weight on USEFUL: {summary['weight_on_useful']:.2f} | "
            f"on worthless/unstable: {summary['weight_on_worthless_or_unstable']:.2f} | "
            f"unmeasured: {summary['weight_on_unmeasured']:.2f}"
        )

    add("")
    add("-" * width)
    add(f"  {results['note']}")
    add("=" * width)
    return "\n".join(lines)

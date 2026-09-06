"""`make research` - run every historical study and persist the results.

Produces a single report covering: ETF lag analysis, quantile buckets,
out-of-sample split validation, event studies, and score calibration.

Negative results are kept and surfaced. A study that shows a signal is useless
is a successful study.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ..core.enums import Asset
from ..logging_setup import get_logger
from . import (
    audit as audit_module,
)
from . import (
    calibration,
    candidate_weights,
    derivatives_study,
    etf_asymmetry,
    etf_study,
    event_study,
)
from . import (
    features as features_module,
)
from . import (
    regime_conditioned as regime_module,
)

log = get_logger("research.runner")


def run_all(
    assets: list[Asset] | None = None,
    persist: bool = True,
    include_lot3: bool = True,
    run_walk_forward: bool = True,
) -> dict[str, Any]:
    """Every study. `include_lot3` adds the LOT 3 layers (audit, asymmetry,
    derivatives bands, regime conditioning, feature importance, candidate
    weights) which are considerably slower."""
    assets = assets or Asset.tradables()
    started = datetime.now(UTC)

    out: dict[str, Any] = {
        "started_at": started.isoformat(),
        "etf_lag": {}, "etf_buckets": {}, "etf_validation": {},
        "events": {}, "calibration": {},
        "audit": {}, "etf_asymmetry": {}, "derivatives": {},
        "regime_conditioned": {}, "features": {},
        "candidate_weights": {}, "champion_challenger": {},
        "persisted": 0,
    }
    persisted = 0

    # --- ETF studies (BTC / ETH only - SOL has no US spot ETF) --------------
    for asset in [a for a in assets if a in (Asset.BTC, Asset.ETH)]:
        lag = etf_study.run_lag_study(asset)
        out["etf_lag"][asset.value] = lag
        if persist:
            persisted += etf_study.persist_results("etf_lag", asset, lag)

        buckets = etf_study.run_bucket_study(asset, signal="ma7")
        out["etf_buckets"][asset.value] = buckets
        if persist:
            persisted += etf_study.persist_results("etf_bucket", asset, buckets)

        validations = {}
        for signal, horizon in (("ma5", 14), ("ma7", 14), ("cum30", 30), ("flow", 7)):
            result = etf_study.run_split_validation(asset, signal=signal, horizon=horizon)
            validations[f"{signal}@{horizon}d"] = result
            if persist:
                persisted += etf_study.persist_results("etf_split", asset, result)
        out["etf_validation"][asset.value] = validations

    # --- event studies -----------------------------------------------------
    for asset in assets:
        events = event_study.run_all_events(asset)
        out["events"][asset.value] = events
        if persist:
            persisted += event_study.persist_events(asset, events)

    # --- calibration -------------------------------------------------------
    calib = calibration.run_full_calibration(assets)
    out["calibration"] = calib
    if persist:
        persisted += calibration.persist_calibration(calib)

    # --- LOT 3 layers -------------------------------------------------------
    if include_lot3:
        try:
            out["audit"] = audit_module.audit_all(assets)
        except Exception as exc:
            log.warning("audit_failed", error=str(exc))
            out["audit"] = {"error": str(exc)[:200]}

        for asset in [a for a in assets if a in (Asset.BTC, Asset.ETH)]:
            try:
                out["etf_asymmetry"][asset.value] = etf_asymmetry.analyse_asymmetry(asset)
            except Exception as exc:
                out["etf_asymmetry"][asset.value] = {"available": False, "reason": str(exc)[:150]}

        for asset in assets:
            try:
                out["derivatives"][asset.value] = {
                    "percentile_bands": derivatives_study.analyse_percentile_bands(asset),
                    "price_oi_funding": derivatives_study.analyse_price_oi_funding(asset),
                    "suggested_thresholds": derivatives_study.suggest_thresholds(asset),
                }
            except Exception as exc:
                out["derivatives"][asset.value] = {"error": str(exc)[:150]}

            try:
                regime_result = regime_module.analyse_all_signals(asset)
                out["regime_conditioned"][asset.value] = regime_result
                if persist:
                    from ..engines.rsi_context import persist_regime_studies

                    persisted += persist_regime_studies(asset, regime_result)
            except Exception as exc:
                out["regime_conditioned"][asset.value] = {"available": False, "reason": str(exc)[:150]}

            try:
                out["features"][asset.value] = features_module.analyse_features(
                    asset, run_walk_forward=run_walk_forward
                )
            except Exception as exc:
                out["features"][asset.value] = {"available": False, "reason": str(exc)[:150]}

        try:
            candidate = candidate_weights.run_full(assets, write_file=persist)
            out["candidate_weights"] = candidate["proposals"]
            out["champion_challenger"] = candidate["comparisons"]
            out["candidate_file"] = candidate["candidate_file"]
            out["promotion_policy"] = candidate["promotion_policy"]
        except Exception as exc:
            log.warning("candidate_weights_failed", error=str(exc))
            out["candidate_weights"] = {"error": str(exc)[:200]}

    out["persisted"] = persisted
    out["finished_at"] = datetime.now(UTC).isoformat()
    out["duration_seconds"] = round((datetime.now(UTC) - started).total_seconds(), 1)
    out["summary"] = summarize(out)
    return out


def summarize(results: dict[str, Any]) -> dict[str, Any]:
    """Distil the findings, keeping the negative ones.

    `useless_signals` is as important as `notable_findings`: knowing that a
    weighted domain has no measurable predictive value is what stops the system
    being built on an illusion.
    """
    findings: list[str] = []
    useless: list[str] = []

    for asset_value, lag in (results.get("etf_lag") or {}).items():
        if not lag.get("available"):
            continue
        mt = lag.get("multiple_testing", {})
        control = (lag.get("contemporaneous_control") or {}).get("flow", {})
        survivors = [
            (signal, horizon, cell["spearman_r"])
            for signal, horizons in lag["correlations"].items()
            for horizon, cell in horizons.items()
            if cell.get("significant")
        ]
        if control.get("spearman_r") is not None:
            findings.append(
                f"{asset_value}: ETF flow correlates {control['spearman_r']:+.3f} with the "
                f"SAME-day return but only {mt.get('significant_after_fdr', 0)}/"
                f"{mt.get('hypotheses', 0)} forward relationships survive multiple-testing "
                "correction - flows largely follow price rather than leading it."
            )
        if not survivors:
            useless.append(
                f"{asset_value} ETF flow signals: no forward horizon survives FDR correction "
                f"({mt.get('significant_raw', 0)} passed raw p<0.05, "
                f"{mt.get('expected_false_positives_uncorrected', 0)} expected by chance)."
            )
        else:
            for signal, horizon, r in survivors:
                findings.append(
                    f"{asset_value}: {signal} vs {horizon} forward return, Spearman {r:+.3f} "
                    "(survives FDR correction)."
                )

    for asset_value, validations in (results.get("etf_validation") or {}).items():
        for key, result in validations.items():
            if not result.get("available"):
                continue
            if not result.get("stable_sign"):
                useless.append(
                    f"{asset_value} {key}: correlation changes sign between train, validation "
                    "and out-of-sample - not stable, must not be treated as predictive."
                )

    for asset_value, events in (results.get("events") or {}).items():
        for event in events.get("events", []):
            if not event.get("available"):
                continue
            cell = event["horizons"].get("7d", {})
            edge = cell.get("edge_vs_baseline")
            if edge is None or not cell.get("reliable_sample"):
                continue
            if edge <= -0.7:
                findings.append(
                    f"{asset_value}: after '{event['label']}' the 7-day return averages "
                    f"{cell['mean']:+.2f}% vs a {cell['baseline_mean']:+.2f}% baseline "
                    f"(edge {edge:+.2f}%, n={cell['n']}) - this condition has historically "
                    "preceded UNDER-performance."
                )
            elif edge >= 1.0:
                findings.append(
                    f"{asset_value}: after '{event['label']}' the 7-day return averages "
                    f"{cell['mean']:+.2f}% vs a {cell['baseline_mean']:+.2f}% baseline "
                    f"(edge {edge:+.2f}%, n={cell['n']}, win {cell['win_rate']:.0f}%)."
                )

    for asset_value, domains in (results.get("calibration", {}).get("reconstructed") or {}).items():
        for domain, result in domains.items():
            if not result.get("available"):
                continue
            corr = result["correlations"].get("7d", {})
            mono = result.get("monotonicity_7d", {})
            if corr.get("significant") and mono.get("monotonic"):
                findings.append(
                    f"{asset_value} {domain} score: Spearman {corr['spearman_r']:+.3f} with the "
                    f"7-day forward return (n={corr['n']}) and monotonic across buckets - "
                    "it orders outcomes correctly."
                )
            elif not corr.get("significant"):
                useless.append(
                    f"{asset_value} {domain} score: no significant relationship with the 7-day "
                    f"forward return (Spearman {corr.get('spearman_r')}, p={corr.get('p_value')}, "
                    f"n={corr.get('n')}) - it carries no measurable predictive value in this test."
                )
            elif not mono.get("monotonic"):
                useless.append(
                    f"{asset_value} {domain} score: statistically correlated but NOT monotonic "
                    "across buckets - a higher score does not reliably mean a better outcome."
                )

    # --- LOT 3 findings -------------------------------------------------------
    for asset_value, asset_result in (results.get("audit", {}).get("assets") or {}).items():
        summary = asset_result.get("summary", {})
        useful = summary.get("verdicts", {}).get("USEFUL", [])
        if useful:
            findings.append(
                f"{asset_value}: domain(s) with measurable value: {', '.join(useful)}"
            )
        else:
            useless.append(
                f"{asset_value}: NO domain score shows measurable predictive value. "
                f"{summary.get('weight_on_worthless_or_unstable', 0):.2f} of the weight sits "
                f"on domains measured as worthless or unstable, and "
                f"{summary.get('weight_on_unmeasured', 0):.2f} on domains that cannot be "
                "measured at all."
            )
        for domain, result in (asset_result.get("domains") or {}).items():
            decomposition = result.get("ic_decomposition") or {}
            if decomposition.get("globally_inflated"):
                useless.append(
                    f"{asset_value} {domain}: global IC "
                    f"{decomposition['global_ic']:+.3f} is NOT reproduced within periods "
                    f"(mean within-period {decomposition['mean_within_ic']:+.3f}, "
                    f"{decomposition['periods_positive']}/{decomposition['periods_total']} "
                    "positive). It separates market eras, not good days from bad days."
                )

    for asset_value, asym in (results.get("etf_asymmetry") or {}).items():
        comparison = (asym or {}).get("asymmetry") or {}
        if comparison.get("assessable"):
            (findings if comparison["verdict"] != "NO_ASYMMETRY_DEMONSTRATED" else useless).append(
                f"{asset_value} ETF tails: {comparison['conclusion']}"
            )

    for asset_value, data in (results.get("derivatives") or {}).items():
        bands = (data or {}).get("percentile_bands") or {}
        mapping = bands.get("current_threshold_mapping") or {}
        if mapping.get("diagnosis"):
            useless.append(f"{asset_value} derivatives thresholds: {mapping['diagnosis']}")

    for asset_value, data in (results.get("regime_conditioned") or {}).items():
        for signal_name in (data or {}).get("regime_dependent_signals", []):
            signal_result = data["signals"][signal_name]
            findings.append(
                f"{asset_value} {signal_name}: {signal_result['interpretation']['conclusion']}"
            )

    for asset_value, features in (results.get("features") or {}).items():
        if not (features or {}).get("available"):
            continue
        permutation = features.get("permutation_importance") or {}
        if permutation.get("available"):
            r2 = permutation["baseline_r2_oos"]
            if r2 <= 0:
                useless.append(
                    f"{asset_value}: a ridge model over {permutation.get('features_used')} "
                    f"features has an out-of-sample R2 of {r2:+.4f} - jointly, the features "
                    "explain nothing beyond a constant."
                )

    for asset_value, comparison in (results.get("champion_challenger") or {}).items():
        if (comparison or {}).get("available"):
            findings.append(
                f"{asset_value} champion vs challenger: {comparison['verdict']} - "
                f"{comparison['reason']}"
            )

    return {
        "notable_findings": findings,
        "useless_or_weak_signals": useless,
        "disclaimer": (
            "All results are historical descriptions, not predictions. Correlations of this "
            "magnitude explain a very small share of variance. Nothing here is calibrated "
            "enough to trade mechanically."
        ),
    }


def format_text_report(results: dict[str, Any]) -> str:
    """Console-friendly rendering of `make research`."""
    lines: list[str] = []
    add = lines.append
    width = 78
    add("=" * width)
    add("CRYPTO INTELLIGENCE - HISTORICAL RESEARCH")
    add("=" * width)
    add(f"Computed: {results.get('finished_at', '')[:19]} UTC "
        f"({results.get('duration_seconds', 0)}s, {results.get('persisted', 0)} rows stored)")
    add("")

    for asset_value, lag in (results.get("etf_lag") or {}).items():
        add("-" * width)
        add(f"ETF FLOW -> FUTURE PRICE : {asset_value}")
        add("-" * width)
        if not lag.get("available"):
            add(f"  {lag.get('reason')}")
            add("")
            continue
        period = lag["period"]
        add(f"  Period: {period['start'][:10]} -> {period['end'][:10]} ({period['days']} days)")
        control = lag["contemporaneous_control"]["flow"]["spearman_r"]
        add(f"  Same-day control correlation: {control:+.3f}")
        mt = lag["multiple_testing"]
        add(f"  Multiple testing: {mt['hypotheses']} hypotheses, {mt['significant_raw']} raw hits, "
            f"{mt['expected_false_positives_uncorrected']} expected by chance, "
            f"{mt['significant_after_fdr']} survive FDR")
        add("")
        header = f"  {'signal':16s}" + "".join(f"{h:>9s}" for h in ["1d", "2d", "3d", "5d", "7d", "14d", "30d"])
        add(header)
        for signal, horizons in lag["correlations"].items():
            cells = ""
            for h in ["1d", "2d", "3d", "5d", "7d", "14d", "30d"]:
                cell = horizons[h]
                if cell["spearman_r"] is None:
                    cells += f"{'n/a':>9s}"
                else:
                    mark = "*" if cell["significant"] else " "
                    cells += f"{cell['spearman_r']:>+8.3f}{mark}"
            add(f"  {signal:16s}{cells}")
        add("  (* survives Benjamini-Hochberg FDR correction)")
        add("")

    for asset_value, events in (results.get("events") or {}).items():
        add("-" * width)
        add(f"EVENT STUDIES : {asset_value}")
        add("-" * width)
        rows = []
        for event in events.get("events", []):
            if not event.get("available"):
                continue
            cell = event["horizons"].get("7d", {})
            rows.append((cell.get("edge_vs_baseline") or 0.0, event, cell))
        add(f"  {'event':24s}{'n':>5s}{'ret7d':>9s}{'base':>8s}{'edge':>9s}{'win':>6s}")
        for _, event, cell in sorted(rows, key=lambda r: -r[0]):
            add(
                f"  {event['event']:24s}{cell['n']:>5}{cell['mean']:>+8.2f}%"
                f"{cell['baseline_mean']:>+7.2f}%{cell['edge_vs_baseline']:>+8.2f}%"
                f"{cell['win_rate']:>5.0f}%"
            )
        add("")

    summary = results.get("summary", {})
    add("-" * width)
    add("NOTABLE FINDINGS")
    add("-" * width)
    for f in summary.get("notable_findings", []) or ["  (none)"]:
        add(f"  - {f}")
    add("")
    add("-" * width)
    add("SIGNALS THAT LOOK USELESS OR UNSTABLE")
    add("-" * width)
    for f in summary.get("useless_or_weak_signals", []) or ["  (none)"]:
        add(f"  - {f}")
    add("")
    add(f"  {summary.get('disclaimer', '')}")
    add("=" * width)
    return "\n".join(lines)

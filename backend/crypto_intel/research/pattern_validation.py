"""Do the chart patterns we detect carry any forward information?

The detectors already exist and produce a recognition confidence. That number
says how cleanly the shape matches its definition - it is NOT a probability
that price moves in the pattern's traditional direction. This module measures
the second thing, and keeps the answer separate from the first.

The method follows what the funding study taught. Patterns are compared to a
same-regime baseline rather than to zero, because in a market that rose over
the sample every pattern "precedes positive returns". Occurrences cluster into
episodes and forward windows overlap, so an effective sample is computed
alongside the raw count. FDR runs across the entire grid of patterns, assets
and horizons at once.

If the answer is that none of them work, that is the result reported.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pandas as pd
from scipy.stats import ttest_ind

from ..core.enums import Asset, ConfirmationState, Timeframe
from ..engines.technical.patterns import PatternContext, all_detectors
from ..engines.technical.structure import find_swings
from ..history import store
from ..logging_setup import get_logger
from .regime_conditioned import reconstruct_regime
from .stats import MIN_RELIABLE_SAMPLE, benjamini_hochberg

log = get_logger("research.pattern_validation")

HORIZONS = [1, 7, 14, 30]
WINDOW = 120           # bars each detector sees, matching live conditions
STEP = 1
MIN_OCCURRENCES = 20
NEGLIGIBLE_EFFECT_PCT = 0.5


def detect_history(
    asset: Asset, timeframe: Timeframe = Timeframe.D1, step: int = STEP
) -> pd.DataFrame:
    """Replay every detector bar by bar, seeing only the past at each point.

    The detector is handed a window ending at bar i and nothing beyond it, so a
    detection at i cannot depend on i+1. This is the same discipline the live
    engine operates under, which is what makes the results comparable.
    """
    df = store.load_candles(asset, timeframe)
    if df.empty or len(df) < WINDOW + max(HORIZONS) + 10:
        return pd.DataFrame()

    detectors = all_detectors()
    records: list[dict[str, Any]] = []

    for i in range(WINDOW, len(df), step):
        window = df.iloc[i - WINDOW:i + 1]
        swing_highs, swing_lows = find_swings(window["high"], window["low"], lookback=5)
        ctx = PatternContext(
            high=window["high"], low=window["low"], close=window["close"],
            volume=window["volume"], swing_highs=swing_highs, swing_lows=swing_lows,
            timeframe=timeframe, config={},
        )
        for detector in detectors:
            try:
                match = detector.detect(ctx)
            except Exception:
                continue
            if match is None:
                continue
            records.append({
                "timestamp": df.index[i],
                "pattern": detector.name,
                "confidence": float(getattr(match, "confidence", 0.0) or 0.0),
                # PatternMatch reports `confirmation_state`, never a `confirmed`
                # flag. Reading the flag returned False for every detection ever
                # recorded, which silently pinned confirmed_share_pct at 0.0 and
                # made `confirmed_only=True` return an empty study.
                "confirmed": match.confirmation_state is ConfirmationState.CONFIRMED,
                "direction": str(getattr(match, "direction", "") or ""),
            })

    if not records:
        return pd.DataFrame()
    return pd.DataFrame(records).set_index("timestamp")


def _episode_stats(timestamps: pd.DatetimeIndex, horizon: int) -> dict[str, Any]:
    """Distinct episodes and an effective sample from overlapping windows."""
    if len(timestamps) == 0:
        return {"episodes": 0, "effective_n": 0.0}
    ordered = timestamps.sort_values()
    gaps = ordered.to_series().diff().dt.days.fillna(999)
    episodes = int((gaps > horizon).sum()) + 1
    # Overlapping h-day windows carry roughly n/h independent draws; the
    # episode count caps it, since one episode cannot be many observations.
    effective = min(len(ordered) / horizon, float(episodes))
    return {"episodes": episodes, "effective_n": round(effective, 1)}


def validate(
    asset: Asset, timeframe: Timeframe = Timeframe.D1, confirmed_only: bool = False
) -> dict[str, Any]:
    """Measure every detected pattern against its same-regime baseline."""
    detections = detect_history(asset, timeframe)
    df = store.load_candles(asset, timeframe)

    out: dict[str, Any] = {
        "asset": asset.value, "timeframe": timeframe.value,
        "confirmed_only": confirmed_only, "patterns": {},
    }
    if detections.empty or df.empty:
        out["status"] = "NO_DETECTIONS"
        out["note"] = "no pattern occurred often enough to study, or history is too short"
        return out

    out["status"] = "OK"
    out["bars_scanned"] = len(df)
    out["total_detections"] = len(detections)

    closes = df["close"]
    regimes = reconstruct_regime(df)
    forward = {
        h: (closes.shift(-h) - closes) / closes * 100.0 for h in HORIZONS
    }

    tests: list[tuple[str, float | None]] = []
    for pattern in sorted(detections["pattern"].unique()):
        subset = detections[detections["pattern"] == pattern]
        if confirmed_only:
            subset = subset[subset["confirmed"]]

        timestamps = pd.DatetimeIndex(subset.index.unique())
        entry: dict[str, Any] = {
            "raw_occurrences": len(timestamps),
            "mean_confidence": round(float(subset["confidence"].mean()), 1) if len(subset) else None,
            "confirmed_share_pct": (
                round(float(subset["confirmed"].mean() * 100), 1) if len(subset) else None
            ),
            "horizons": {},
        }

        if len(timestamps) < MIN_OCCURRENCES:
            entry["verdict"] = "INSUFFICIENT_DATA"
            entry["note"] = (
                f"{len(timestamps)} occurrences, below the {MIN_OCCURRENCES} minimum"
            )
            out["patterns"][pattern] = entry
            continue

        for horizon in HORIZONS:
            fwd = forward[horizon]
            mask = pd.Series(False, index=df.index)
            mask.loc[mask.index.isin(timestamps)] = True

            pattern_returns = fwd[mask].dropna()
            episode = _episode_stats(pd.DatetimeIndex(fwd[mask].dropna().index), horizon)

            # Baseline: same regimes, different days. Holds the trend fixed so
            # the comparison is not just "the market went up".
            pattern_regimes = regimes[mask].dropna()
            regime_counts = pattern_regimes.value_counts(normalize=True)
            baseline_mask = regimes.isin(regime_counts.index) & ~mask
            baseline_returns = fwd[baseline_mask].dropna()

            cell: dict[str, Any] = {
                "n": len(pattern_returns),
                "episodes": episode["episodes"],
                "effective_n": episode["effective_n"],
                "mean_return_pct": (
                    round(float(pattern_returns.mean()), 3) if len(pattern_returns) else None
                ),
                "baseline_mean_pct": (
                    round(float(baseline_returns.mean()), 3) if len(baseline_returns) else None
                ),
                "win_rate": (
                    round(float((pattern_returns > 0).mean() * 100), 1)
                    if len(pattern_returns) else None
                ),
            }

            if len(pattern_returns) >= MIN_RELIABLE_SAMPLE and len(baseline_returns) >= MIN_RELIABLE_SAMPLE:
                excess = float(pattern_returns.mean() - baseline_returns.mean())
                t_stat, p_value = ttest_ind(pattern_returns, baseline_returns, equal_var=False)
                cell["excess_vs_regime_baseline_pct"] = round(excess, 3)
                cell["t_stat"] = round(float(t_stat), 3)
                cell["p_value"] = float(p_value)
                tests.append((f"{pattern}|{horizon}d", float(p_value)))
            else:
                cell["note"] = "sample too small for a baseline comparison"

            # Per-year stability. The funding study showed that a headline
            # excess can come entirely from one era, so this is computed for
            # every cell and gates the verdict below.
            cell["stability"] = _year_stability(fwd, mask, baseline_mask)

            entry["horizons"][f"{horizon}d"] = cell

        out["patterns"][pattern] = entry

    # FDR across every pattern and horizon at once.
    labels = [label for label, _ in tests]
    p_values = [p for _, p in tests]
    survives = benjamini_hochberg(p_values, alpha=0.05)
    survivors = [label for label, ok in zip(labels, survives, strict=True) if ok]

    out["multiple_testing"] = {
        "hypotheses_tested": len(tests),
        "raw_significant": sum(1 for p in p_values if p is not None and p < 0.05),
        "survives_fdr": len(survivors),
        "expected_false_positives": round(len(tests) * 0.05, 1),
        "survivors": survivors,
        "method": "Benjamini-Hochberg alpha=0.05 across all patterns and horizons",
    }
    _assign_verdicts(out, set(survivors))
    return out


def _year_stability(
    forward: pd.Series, mask: pd.Series, baseline_mask: pd.Series
) -> dict[str, Any]:
    """Is the excess present across years, or is it one era?"""
    pattern_returns = forward[mask].dropna()
    baseline_returns = forward[baseline_mask].dropna()
    if pattern_returns.empty or baseline_returns.empty:
        return {"years_covered": 0, "years_positive": 0, "verdict": "NO_DATA"}

    by_year: dict[str, float] = {}
    for year, chunk in pattern_returns.groupby(pattern_returns.index.year):
        base = baseline_returns[baseline_returns.index.year == year]
        if len(chunk) < 5 or len(base) < 20:
            continue
        by_year[str(year)] = round(float(chunk.mean() - base.mean()), 3)

    if not by_year:
        return {"years_covered": 0, "years_positive": 0, "verdict": "NO_DATA"}

    values = list(by_year.values())
    # Sign consistency matters more than the count of positives: a bearish
    # pattern should be consistently negative, not consistently positive.
    positive = sum(1 for v in values if v > 0)
    dominant = max(positive, len(values) - positive)
    share = dominant / len(values)

    verdict = (
        "STABLE" if share >= 0.7 and len(values) >= 3
        else "MIXED" if share >= 0.55
        else "UNSTABLE"
    )
    return {
        "years_covered": len(values),
        "years_positive": positive,
        "sign_consistency_pct": round(share * 100, 1),
        "by_year": by_year,
        "worst_year": min(values),
        "best_year": max(values),
        "verdict": verdict,
    }


def _assign_verdicts(out: dict[str, Any], survivors: set[str]) -> None:
    """One verdict per pattern, applying every filter the edge engine uses."""
    for pattern, entry in out["patterns"].items():
        if entry.get("verdict") == "INSUFFICIENT_DATA":
            continue

        admitted: list[str] = []
        reasons: list[str] = []
        for horizon_key, cell in entry.get("horizons", {}).items():
            label = f"{pattern}|{horizon_key}"
            excess = cell.get("excess_vs_regime_baseline_pct")
            if excess is None:
                continue
            if label not in survivors:
                continue
            if abs(excess) < NEGLIGIBLE_EFFECT_PCT:
                reasons.append(f"{horizon_key}: effect {excess:+.2f}% below the floor")
                continue
            if cell.get("effective_n", 0) < 20:
                reasons.append(
                    f"{horizon_key}: only ~{cell.get('effective_n')} independent windows"
                )
                continue
            stability = cell.get("stability", {})
            if stability.get("verdict") not in ("STABLE",):
                reasons.append(
                    f"{horizon_key}: effect {stability.get('verdict', 'unverified')} across "
                    f"years ({stability.get('years_positive')}/"
                    f"{stability.get('years_covered')} positive, worst "
                    f"{stability.get('worst_year')})"
                )
                continue
            admitted.append(f"{horizon_key} ({excess:+.2f}%)")

        if admitted:
            entry["verdict"] = "MEASURABLE_EDGE"
            entry["note"] = f"survives every filter at {', '.join(admitted)}"
        elif reasons:
            entry["verdict"] = "NO_MEASURABLE_EDGE"
            entry["note"] = (
                "statistically distinguishable but fails the practical filters: "
                + "; ".join(reasons)
            )
        else:
            entry["verdict"] = "NO_MEASURABLE_EDGE"
            entry["note"] = (
                "no horizon survives correction for multiple testing against a "
                "same-regime baseline"
            )


def run_all(
    assets: list[Asset] | None = None, timeframes: list[Timeframe] | None = None
) -> dict[str, Any]:
    assets = assets or Asset.tradables()
    timeframes = timeframes or [Timeframe.D1]
    results: dict[str, Any] = {}
    for asset in assets:
        for timeframe in timeframes:
            key = f"{asset.value}_{timeframe.value}"
            try:
                results[key] = validate(asset, timeframe)
            except Exception as exc:
                log.warning("pattern_validation_failed", key=key, error=str(exc))
                results[key] = {"status": "ERROR", "error": str(exc)[:200]}
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "horizons_days": HORIZONS,
        "results": results,
        "note": (
            "Recognition confidence and predictive edge are different quantities. A "
            "pattern can be detected cleanly and carry no forward information."
        ),
    }

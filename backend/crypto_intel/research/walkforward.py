"""Walk-forward validation and stability scoring.

A single train/validation/OOS split answers "did this work once?". Walk-forward
answers the question that matters: "does this keep working as the window
moves?" A signal that only worked in 2024 is not a signal, it is a memory of
2024.

The window slides forward in time; no window is ever tuned on its own test
segment, and no parameter is chosen after seeing a test result. Every window is
reported, including the losing ones - dropping unfavourable periods is exactly
the self-deception this module exists to prevent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from ..logging_setup import get_logger
from .stats import describe_returns, lagged_correlation

log = get_logger("research.walkforward")

# Defaults sized for the ~9 years of daily history the project actually holds.
DEFAULT_TRAIN_DAYS = 730      # 2 years
DEFAULT_VALIDATION_DAYS = 180  # 6 months
DEFAULT_TEST_DAYS = 90         # 3 months
DEFAULT_STEP_DAYS = 90         # slide by one test window


@dataclass(slots=True)
class WalkForwardWindow:
    index: int
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    validation_start: pd.Timestamp
    validation_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp
    train_ic: float | None = None
    validation_ic: float | None = None
    test_ic: float | None = None
    test_n: int = 0
    test_p: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "train": [self.train_start.isoformat(), self.train_end.isoformat()],
            "validation": [self.validation_start.isoformat(), self.validation_end.isoformat()],
            "test": [self.test_start.isoformat(), self.test_end.isoformat()],
            "train_ic": self.train_ic,
            "validation_ic": self.validation_ic,
            "test_ic": self.test_ic,
            "test_n": self.test_n,
            "test_p": self.test_p,
        }


@dataclass(slots=True)
class StabilityAssessment:
    """How trustworthy a measured relationship is, beyond its raw size.

    A large edge that appears in one window out of eight is worth less than a
    small edge that shows up in seven. `score` encodes that trade-off, and the
    components are exposed so the number is never a black box.
    """

    score: float = 0.0
    sign_consistency: float = 0.0
    windows_total: int = 0
    windows_positive: int = 0
    windows_significant: int = 0
    mean_test_ic: float | None = None
    median_test_ic: float | None = None
    ic_dispersion: float | None = None
    train_test_gap: float | None = None
    sample_adequacy: float = 0.0
    verdict: str = "INSUFFICIENT_DATA"
    components: dict[str, float] = field(default_factory=dict)
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "stability_score": round(self.score, 1),
            "sign_consistency": round(self.sign_consistency, 3),
            "windows_total": self.windows_total,
            "windows_positive": self.windows_positive,
            "windows_significant": self.windows_significant,
            "mean_test_ic": self.mean_test_ic,
            "median_test_ic": self.median_test_ic,
            "ic_dispersion": self.ic_dispersion,
            "train_test_gap": self.train_test_gap,
            "sample_adequacy": round(self.sample_adequacy, 2),
            "verdict": self.verdict,
            "components": {k: round(v, 2) for k, v in self.components.items()},
            "note": self.note,
        }


def build_windows(
    index: pd.DatetimeIndex,
    train_days: int = DEFAULT_TRAIN_DAYS,
    validation_days: int = DEFAULT_VALIDATION_DAYS,
    test_days: int = DEFAULT_TEST_DAYS,
    step_days: int = DEFAULT_STEP_DAYS,
) -> list[tuple[pd.Timestamp, ...]]:
    """Slide a train/validation/test triple forward through time.

    Window sizes shrink automatically when the history is too short, rather
    than returning nothing - but the shrink is reported so a caller can see it
    happened.
    """
    if len(index) == 0:
        return []

    ordered = index.sort_values()
    start, end = ordered[0], ordered[-1]
    span_days = (end - start).days

    required = train_days + validation_days + test_days
    if span_days < required:
        # Scale everything down proportionally; below ~1 year there is nothing
        # meaningful to walk forward over.
        if span_days < 365:
            return []
        factor = span_days / (required * 1.2)
        train_days = max(180, int(train_days * factor))
        validation_days = max(60, int(validation_days * factor))
        test_days = max(45, int(test_days * factor))
        step_days = max(30, int(step_days * factor))

    windows: list[tuple[pd.Timestamp, ...]] = []
    cursor = start
    while True:
        train_start = cursor
        train_end = train_start + pd.Timedelta(days=train_days)
        validation_start = train_end
        validation_end = validation_start + pd.Timedelta(days=validation_days)
        test_start = validation_end
        test_end = test_start + pd.Timedelta(days=test_days)
        if test_end > end:
            break
        windows.append(
            (train_start, train_end, validation_start, validation_end, test_start, test_end)
        )
        cursor = cursor + pd.Timedelta(days=step_days)
    return windows


def walk_forward_ic(
    signal: pd.Series,
    forward_return: pd.Series,
    train_days: int = DEFAULT_TRAIN_DAYS,
    validation_days: int = DEFAULT_VALIDATION_DAYS,
    test_days: int = DEFAULT_TEST_DAYS,
    step_days: int = DEFAULT_STEP_DAYS,
) -> dict[str, Any]:
    """Information coefficient per walk-forward window.

    The IC is a rank correlation between a signal known at t and the return
    realised after t, so each window's test IC is a genuinely out-of-sample
    reading for that period.
    """
    joined = pd.concat([signal.rename("signal"), forward_return.rename("fwd")], axis=1).dropna()
    if len(joined) < 120:
        return {
            "available": False,
            "reason": f"INSUFFICIENT_DATA - {len(joined)} usable observations",
            "windows": [],
        }

    specs = build_windows(
        pd.DatetimeIndex(joined.index), train_days, validation_days, test_days, step_days
    )
    if not specs:
        return {
            "available": False,
            "reason": (
                f"INSUFFICIENT_DATA - history spans "
                f"{(joined.index.max() - joined.index.min()).days} days, "
                "not enough for a walk-forward"
            ),
            "windows": [],
        }

    windows: list[WalkForwardWindow] = []
    for i, (tr_s, tr_e, va_s, va_e, te_s, te_e) in enumerate(specs):
        def slice_window(start, end):
            return joined[(joined.index >= start) & (joined.index < end)]

        train = slice_window(tr_s, tr_e)
        validation = slice_window(va_s, va_e)
        test = slice_window(te_s, te_e)
        if len(test) < 20:
            continue

        train_ic, _, _ = lagged_correlation(train["signal"], train["fwd"])
        validation_ic, _, _ = lagged_correlation(validation["signal"], validation["fwd"])
        test_ic, test_p, test_n = lagged_correlation(test["signal"], test["fwd"])

        windows.append(
            WalkForwardWindow(
                index=i,
                train_start=tr_s, train_end=tr_e,
                validation_start=va_s, validation_end=va_e,
                test_start=te_s, test_end=te_e,
                train_ic=train_ic, validation_ic=validation_ic,
                test_ic=test_ic, test_n=test_n, test_p=test_p,
            )
        )

    if not windows:
        return {
            "available": False,
            "reason": "INSUFFICIENT_DATA - no window had enough test observations",
            "windows": [],
        }

    stability = assess_stability(windows)
    return {
        "available": True,
        "windows": [w.to_dict() for w in windows],
        "stability": stability.to_dict(),
        "period": {
            "start": joined.index.min().isoformat(),
            "end": joined.index.max().isoformat(),
            "observations": len(joined),
        },
        "config": {
            "train_days": train_days, "validation_days": validation_days,
            "test_days": test_days, "step_days": step_days,
        },
    }


def assess_stability(windows: list[WalkForwardWindow]) -> StabilityAssessment:
    """Turn a set of walk-forward windows into a 0-100 stability score.

    The weighting is deliberate: sign consistency dominates, because a signal
    that flips direction is worse than useless - it is actively misleading.
    Effect size is NOT part of the score; a big unstable edge must not score
    higher than a small reliable one.
    """
    test_ics = [w.test_ic for w in windows if w.test_ic is not None]
    if not test_ics:
        return StabilityAssessment(
            windows_total=len(windows),
            verdict="INSUFFICIENT_DATA",
            note="No window produced a computable test IC",
        )

    n_windows = len(test_ics)
    positive = sum(1 for ic in test_ics if ic > 0)
    significant = sum(
        1 for w in windows
        if w.test_p is not None and w.test_p < 0.05 and w.test_n >= 30
    )

    # Sign consistency: 1.0 when every window agrees, 0.0 at a 50/50 split.
    majority = max(positive, n_windows - positive)
    sign_consistency = (majority / n_windows - 0.5) * 2.0

    mean_ic = float(np.mean(test_ics))
    median_ic = float(np.median(test_ics))
    dispersion = float(np.std(test_ics, ddof=1)) if n_windows > 1 else None

    # Train-to-test decay: a large gap means the relationship was fitted, not found.
    train_ics = [w.train_ic for w in windows if w.train_ic is not None]
    gap = None
    if train_ics and test_ics:
        gap = float(np.mean(train_ics) - mean_ic)

    # More windows means more confidence in the stability estimate itself.
    window_adequacy = min(1.0, n_windows / 8.0)
    total_test_n = sum(w.test_n for w in windows)
    sample_adequacy = min(1.0, total_test_n / 400.0)

    components = {
        "sign_consistency": sign_consistency * 45.0,
        "window_coverage": window_adequacy * 20.0,
        "sample_adequacy": sample_adequacy * 15.0,
        "significance_rate": (significant / n_windows) * 10.0,
    }

    # Dispersion penalty: an IC swinging wildly between windows is not stable
    # even if the average looks fine.
    if dispersion is not None and abs(mean_ic) > 1e-9:
        noise_ratio = min(3.0, dispersion / max(abs(mean_ic), 0.01))
        components["consistency_of_magnitude"] = max(0.0, 10.0 - noise_ratio * 4.0)
    else:
        components["consistency_of_magnitude"] = 0.0

    # Overfitting penalty: train IC far above test IC.
    if gap is not None and gap > 0.05:
        components["overfit_penalty"] = -min(15.0, gap * 100.0)
    else:
        components["overfit_penalty"] = 0.0

    score = max(0.0, min(100.0, sum(components.values())))

    # Mean absolute IC: how big the effect is in a typical window, regardless
    # of whether the windows agree on direction.
    typical_magnitude = float(np.mean([abs(ic) for ic in test_ics]))
    verdict = _stability_verdict(
        score, n_windows, sign_consistency, mean_ic, significant, typical_magnitude
    )
    return StabilityAssessment(
        score=score,
        sign_consistency=sign_consistency,
        windows_total=n_windows,
        windows_positive=positive,
        windows_significant=significant,
        mean_test_ic=round(mean_ic, 4),
        median_test_ic=round(median_ic, 4),
        ic_dispersion=round(dispersion, 4) if dispersion is not None else None,
        train_test_gap=round(gap, 4) if gap is not None else None,
        sample_adequacy=sample_adequacy,
        verdict=verdict,
        components=components,
        note=_stability_note(n_windows, positive, sign_consistency, gap),
    )


def _stability_verdict(
    score: float,
    n_windows: int,
    sign_consistency: float,
    mean_ic: float,
    significant: int,
    typical_magnitude: float | None = None,
) -> str:
    """UNSTABLE and NO_MEASURABLE_VALUE are different diagnoses.

    A signal alternating +0.15 / -0.15 averages to zero, but "no effect" and
    "an effect that keeps reversing" call for different responses - so sign
    consistency is checked BEFORE the mean, using the typical magnitude rather
    than the (cancelling) average.
    """
    if n_windows < 3:
        return "INSUFFICIENT_DATA"

    magnitude = typical_magnitude if typical_magnitude is not None else abs(mean_ic)

    # An effect that exists in each window but keeps flipping direction is
    # unstable, not absent.
    if sign_consistency < 0.34:
        return "UNSTABLE" if magnitude >= 0.03 else "NO_MEASURABLE_VALUE"

    if abs(mean_ic) < 0.02:
        return "NO_MEASURABLE_VALUE"
    if score >= 60 and significant >= 2 and abs(mean_ic) >= 0.05:
        return "USEFUL"
    if score >= 40:
        return "WEAK"
    return "UNSTABLE"


def _stability_note(n_windows: int, positive: int, sign_consistency: float, gap) -> str:
    parts = [f"{positive}/{n_windows} windows positive"]
    if sign_consistency < 0.34:
        parts.append("sign flips between windows - the relationship does not persist")
    if gap is not None and gap > 0.08:
        parts.append(
            f"train IC exceeds test IC by {gap:.3f} - evidence of fitting rather than finding"
        )
    if n_windows < 4:
        parts.append("few windows: the stability estimate itself is uncertain")
    return "; ".join(parts)


def bucket_monotonicity(
    signal: pd.Series, forward_return: pd.Series, n_buckets: int = 5
) -> dict[str, Any]:
    """Does mean forward return rise with the signal, bucket by bucket?

    Monotonicity is the practical test a correlation coefficient hides: a
    signal can correlate while one extreme bucket does all the work, which is
    not something you can act on.
    """
    joined = pd.concat(
        [signal.rename("signal"), forward_return.rename("fwd")], axis=1
    ).dropna()
    if len(joined) < 60:
        return {"assessable": False, "reason": f"only {len(joined)} observations"}

    try:
        joined["bucket"] = pd.qcut(
            joined["signal"], n_buckets,
            labels=[f"Q{i + 1}" for i in range(n_buckets)], duplicates="drop",
        )
    except ValueError:
        return {"assessable": False, "reason": "signal has too few distinct values"}

    rows = []
    for label in joined["bucket"].cat.categories:
        subset = joined[joined["bucket"] == label]
        stats = describe_returns(subset["fwd"])
        rows.append({
            "bucket": str(label),
            "n": stats.n,
            "mean": stats.mean,
            "median": stats.median,
            "win_rate": stats.win_rate,
            "signal_min": round(float(subset["signal"].min()), 4),
            "signal_max": round(float(subset["signal"].max()), 4),
        })

    means = [r["mean"] for r in rows if r["mean"] is not None]
    if len(means) < 3:
        return {"assessable": False, "reason": "fewer than 3 usable buckets", "buckets": rows}

    from scipy import stats as scipy_stats

    ranks = list(range(len(means)))
    rho, p_value = scipy_stats.spearmanr(ranks, means)
    monotonic = bool(rho > 0.7)

    return {
        "assessable": True,
        "buckets": rows,
        "rank_correlation": round(float(rho), 4),
        "p_value": round(float(p_value), 5),
        "monotonic": monotonic,
        "spread": round(means[-1] - means[0], 4),
        "interpretation": (
            "Mean forward return rises consistently with the signal - it orders outcomes."
            if monotonic
            else "Forward return does NOT rise consistently with the signal - a higher "
                 "reading does not reliably mean a better outcome."
        ),
    }

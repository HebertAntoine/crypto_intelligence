"""Shared statistics for the research layer.

Two principles run through this module:

  1. Forward returns are ALWAYS computed as (price at t+h) / (price at t) - 1,
     joined to a signal known at t. The join is what makes look-ahead
     impossible: a signal row can only ever meet returns dated strictly after
     it.

  2. Nothing is reported as significant without its sample size. A 62% win rate
     on 9 observations is noise, and the output says so rather than leaving the
     reader to guess.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats


@dataclass(slots=True)
class DistributionStats:
    """Summary of a set of forward returns."""

    n: int = 0
    mean: float | None = None
    median: float | None = None
    std: float | None = None
    q25: float | None = None
    q75: float | None = None
    min: float | None = None
    max: float | None = None
    win_rate: float | None = None
    t_stat: float | None = None
    p_value: float | None = None
    significant: bool = False
    reliable_sample: bool = False
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "n": self.n, "mean": self.mean, "median": self.median, "std": self.std,
            "q25": self.q25, "q75": self.q75, "min": self.min, "max": self.max,
            "win_rate": self.win_rate, "t_stat": self.t_stat, "p_value": self.p_value,
            "significant": self.significant, "reliable_sample": self.reliable_sample,
            "note": self.note,
        }


# Below this, a result is descriptive at best. Chosen so that a t-test has any
# meaning at all; it is not a claim that 30 points is a lot.
MIN_RELIABLE_SAMPLE = 30


def describe_returns(values: pd.Series | np.ndarray | list[float]) -> DistributionStats:
    """Summarise forward returns, with an honest reliability flag."""
    arr = np.asarray(pd.Series(values).dropna(), dtype=float)
    n = int(arr.size)
    if n == 0:
        return DistributionStats(n=0, note="INCONCLUSIVE - no observations")

    stats = DistributionStats(
        n=n,
        mean=round(float(np.mean(arr)), 4),
        median=round(float(np.median(arr)), 4),
        std=round(float(np.std(arr, ddof=1)), 4) if n > 1 else None,
        q25=round(float(np.percentile(arr, 25)), 4),
        q75=round(float(np.percentile(arr, 75)), 4),
        min=round(float(np.min(arr)), 4),
        max=round(float(np.max(arr)), 4),
        win_rate=round(float((arr > 0).sum() / n * 100.0), 2),
        reliable_sample=n >= MIN_RELIABLE_SAMPLE,
    )

    # One-sample t-test against zero: "is the mean return distinguishable from
    # nothing?". Only computed when the sample can support it.
    if n >= MIN_RELIABLE_SAMPLE and stats.std and stats.std > 0:
        t_stat, p_value = scipy_stats.ttest_1samp(arr, 0.0)
        stats.t_stat = round(float(t_stat), 3)
        stats.p_value = round(float(p_value), 5)
        stats.significant = bool(p_value < 0.05)
        if not stats.significant:
            stats.note = (
                f"Mean return not statistically distinguishable from zero "
                f"(p={stats.p_value})"
            )
    else:
        stats.note = (
            f"Sample of {n} is below the {MIN_RELIABLE_SAMPLE} threshold - "
            "descriptive only, no significance claimed"
        )
    return stats


def forward_returns(prices: pd.Series, horizons: list[int]) -> pd.DataFrame:
    """Percentage return h periods AFTER each timestamp.

    Deliberately built in its own frame, never merged into a feature matrix,
    so a forward value cannot leak into a signal by accident.
    """
    out = pd.DataFrame(index=prices.index)
    for h in horizons:
        out[f"fwd_{h}"] = (prices.shift(-h) - prices) / prices * 100.0
    return out


def excursions(
    high: pd.Series, low: pd.Series, close: pd.Series, horizon: int
) -> tuple[pd.Series, pd.Series]:
    """Maximum favourable and adverse excursion over the next `horizon` bars.

    MFE/MAE describe the path, not just the endpoint: a +2% close that first
    dropped 8% is a very different trade from one that never went red.
    """
    n = len(close)
    mfe = pd.Series(np.nan, index=close.index, dtype=float)
    mae = pd.Series(np.nan, index=close.index, dtype=float)

    highs = high.to_numpy(dtype=float)
    lows = low.to_numpy(dtype=float)
    entries = close.to_numpy(dtype=float)

    for i in range(n - horizon):
        entry = entries[i]
        if not np.isfinite(entry) or entry == 0:
            continue
        window_high = np.nanmax(highs[i + 1 : i + 1 + horizon])
        window_low = np.nanmin(lows[i + 1 : i + 1 + horizon])
        mfe.iloc[i] = (window_high - entry) / entry * 100.0
        mae.iloc[i] = (window_low - entry) / entry * 100.0
    return mfe, mae


def lagged_correlation(
    signal: pd.Series, returns: pd.Series, method: str = "spearman"
) -> tuple[float | None, float | None, int]:
    """Correlation between a signal and returns that come strictly after it.

    Spearman by default: crypto returns are heavy-tailed, and a single outlier
    can manufacture a Pearson correlation that does not survive out of sample.
    """
    joined = pd.concat([signal, returns], axis=1).dropna()
    if len(joined) < 10:
        return None, None, len(joined)
    a = joined.iloc[:, 0].to_numpy(dtype=float)
    b = joined.iloc[:, 1].to_numpy(dtype=float)
    if np.std(a) == 0 or np.std(b) == 0:
        return None, None, len(joined)
    if method == "pearson":
        r, p = scipy_stats.pearsonr(a, b)
    else:
        r, p = scipy_stats.spearmanr(a, b)
    return round(float(r), 4), round(float(p), 5), len(joined)


@dataclass(slots=True)
class SplitWindows:
    """Train / validation / out-of-sample split, chronological by construction.

    Random splits leak future information into the past in a time series, so
    the split is always by date: earliest chunk trains, latest chunk is held
    out and never touched during exploration.
    """

    train: tuple[pd.Timestamp, pd.Timestamp] | None = None
    validation: tuple[pd.Timestamp, pd.Timestamp] | None = None
    oos: tuple[pd.Timestamp, pd.Timestamp] | None = None
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        def fmt(w):
            return [w[0].isoformat(), w[1].isoformat()] if w else None
        return {
            "train": fmt(self.train), "validation": fmt(self.validation),
            "oos": fmt(self.oos), "note": self.note,
        }


def chronological_split(
    index: pd.DatetimeIndex, train: float = 0.6, validation: float = 0.2
) -> SplitWindows:
    """Split a time index chronologically into train / validation / OOS."""
    if len(index) < 30:
        return SplitWindows(note=f"Only {len(index)} points - too few to split meaningfully")
    ordered = index.sort_values()
    n = len(ordered)
    i_train = int(n * train)
    i_val = int(n * (train + validation))
    return SplitWindows(
        train=(ordered[0], ordered[max(0, i_train - 1)]),
        validation=(ordered[i_train], ordered[max(i_train, i_val - 1)]),
        oos=(ordered[i_val], ordered[-1]),
        note=(
            f"Chronological split of {n} points: "
            f"{i_train} train / {i_val - i_train} validation / {n - i_val} out-of-sample"
        ),
    )


def slice_window(series: pd.Series, window: tuple[pd.Timestamp, pd.Timestamp] | None) -> pd.Series:
    if window is None:
        return series.iloc[0:0]
    return series[(series.index >= window[0]) & (series.index <= window[1])]


@dataclass(slots=True)
class BucketResult:
    """Forward-return statistics for one bucket of a signal's range."""

    label: str
    lower: float | None
    upper: float | None
    stats: dict[str, DistributionStats] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label, "lower": self.lower, "upper": self.upper,
            "horizons": {h: s.to_dict() for h, s in self.stats.items()},
        }


def benjamini_hochberg(p_values: list[float | None], alpha: float = 0.05) -> list[bool]:
    """False-discovery-rate correction for multiple comparisons.

    Testing 9 signals across 7 horizons is 63 hypotheses. At alpha=0.05 that
    yields roughly 3 "significant" results by chance alone, so reporting raw
    p-values would manufacture findings out of noise. Benjamini-Hochberg
    controls the expected proportion of false discoveries among the rejections,
    which is the right trade-off for exploratory work: less brutal than
    Bonferroni, still honest.

    Returns a survival flag per input, aligned to the input order.
    """
    indexed = [(i, p) for i, p in enumerate(p_values) if p is not None]
    survives = [False] * len(p_values)
    if not indexed:
        return survives

    indexed.sort(key=lambda kv: kv[1])
    m = len(indexed)
    max_rank = 0
    for rank, (_, p) in enumerate(indexed, start=1):
        if p <= alpha * rank / m:
            max_rank = rank

    for rank, (original_index, _) in enumerate(indexed, start=1):
        if rank <= max_rank:
            survives[original_index] = True
    return survives


def decompose_ic(
    signal: pd.Series, forward_return: pd.Series, freq: str = "YE"
) -> dict[str, Any]:
    """Split a correlation into its within-period and between-period parts.

    This exists because of a real and easily missed failure mode found in this
    project: a composite score showed a significant +0.058 correlation with
    7-day forward returns over 2020-2026, yet was negative inside almost every
    individual year.

    The explanation is that the score was simply HIGHER during periods that
    happened to be bullish. That is a level relationship between regimes, not
    an ability to tell good days from bad days - and only the latter is usable.

    A signal whose within-period IC is near zero while its global IC looks
    healthy is measuring the era, not the moment.
    """
    joined = pd.concat(
        [signal.rename("signal"), forward_return.rename("fwd")], axis=1
    ).dropna()
    if len(joined) < 120:
        return {
            "assessable": False,
            "reason": f"INSUFFICIENT_DATA - {len(joined)} observations",
        }

    global_ic, global_p, global_n = lagged_correlation(joined["signal"], joined["fwd"])

    periods = joined.groupby(pd.Grouper(freq=freq))
    within: list[dict[str, Any]] = []
    for period, group in periods:
        if len(group) < 40:
            continue
        ic, p_value, n = lagged_correlation(group["signal"], group["fwd"])
        if ic is None:
            continue
        within.append({
            "period": period.strftime("%Y-%m-%d"),
            "ic": ic, "p_value": p_value, "n": n,
        })

    if len(within) < 3:
        return {
            "assessable": False,
            "reason": "Fewer than three periods with enough observations",
            "global_ic": global_ic,
        }

    within_ics = [w["ic"] for w in within]
    mean_within = float(np.mean(within_ics))
    positive = sum(1 for ic in within_ics if ic > 0)

    # Between-period component: do periods with a higher average signal also
    # show a higher average return?
    aggregated = joined.groupby(pd.Grouper(freq=freq)).mean().dropna()
    between_ic = None
    if len(aggregated) >= 4:
        between_ic, _, _ = lagged_correlation(aggregated["signal"], aggregated["fwd"])

    # The diagnostic: a global IC that survives only through the between term.
    inflated = bool(
        global_ic is not None
        and abs(global_ic) > 0.03
        and abs(mean_within) < abs(global_ic) * 0.5
    )

    if inflated:
        interpretation = (
            f"The global IC ({global_ic:+.4f}) is NOT supported within periods "
            f"(mean within-period IC {mean_within:+.4f}, {positive}/{len(within)} periods "
            "positive). The apparent relationship comes from the signal being higher "
            "during periods that were bullish anyway - it separates eras, not days. "
            "This is not usable as a timing signal."
        )
    elif positive >= len(within) * 0.7:
        interpretation = (
            f"The relationship holds within periods as well as globally "
            f"({positive}/{len(within)} periods positive, mean within-period IC "
            f"{mean_within:+.4f})."
        )
    else:
        interpretation = (
            f"Mixed: {positive}/{len(within)} periods positive, mean within-period IC "
            f"{mean_within:+.4f} against a global {global_ic:+.4f}."
        )

    return {
        "assessable": True,
        "global_ic": global_ic,
        "global_p": global_p,
        "global_n": global_n,
        "mean_within_ic": round(mean_within, 4),
        "median_within_ic": round(float(np.median(within_ics)), 4),
        "periods_positive": positive,
        "periods_total": len(within),
        "between_period_ic": between_ic,
        "by_period": within,
        "globally_inflated": inflated,
        "interpretation": interpretation,
    }

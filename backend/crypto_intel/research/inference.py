"""Inference that can be trusted: purging, residualisation, pooling.

Three defects in the previous framework motivated this module, and each is
addressed by one section below.

**Purging.** A target built over [t, t+H] uses prices from inside the test fold
whenever t is within H bars of the boundary. The old splits kept those rows in
training, so every "out-of-sample confirmation" was contaminated at exactly the
point where autocorrelation is strongest.

**Control resolution.** The discrete regime label is a five-bucket summary of
the past 40-60 days - measured at +0.73 correlation with the 40-60 day return
against +0.35 with the 5-day one. Stratifying on it leaves large within-bucket
differences. Residualising on continuous controls removes them at full
resolution.

**Cross-asset dependence.** BTC, ETH and SOL correlate around 0.8. Three
observations on one date are close to one observation, so inference clusters on
blocks of dates and never treats assets as independent draws.

Nothing here decides whether a signal is real. It decides how much the sample
is actually worth.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

from ..logging_setup import get_logger

log = get_logger("research.inference")

# A baseline covering this much of the sample is not a conditioned subgroup.
# This is the guard that would have caught the LOT 5 bug.
MAX_BASELINE_COVERAGE = 0.95


class BaselineCoverageError(ValueError):
    """A mask presented as conditioned covers almost everything."""


def assert_baseline_is_conditioned(
    baseline_mask: pd.Series, label: str = "baseline"
) -> dict[str, Any]:
    """Refuse a baseline that is unconditional in disguise.

    In LOT 5 a "same regime" baseline was built as
    `regimes.isin(regimes_where_the_event_occurs)`. Structural labels occur in
    every regime, so the mask selected the entire sample and the comparison
    silently became unconditional - restoring the market drift the control was
    supposed to remove. The observable symptom was that the `same_regime` and
    `same_regime_momentum` columns held identical values on every row.
    """
    total = len(baseline_mask)
    if total == 0:
        raise BaselineCoverageError(f"{label}: empty mask")
    covered = int(baseline_mask.sum())
    coverage = covered / total

    if coverage > MAX_BASELINE_COVERAGE:
        raise BaselineCoverageError(
            f"{label} covers {coverage:.1%} of the sample ({covered}/{total}). "
            f"A conditioned subgroup cannot exceed {MAX_BASELINE_COVERAGE:.0%}; "
            "this mask is unconditional in disguise and would reintroduce the "
            "market drift it is supposed to remove."
        )
    return {"coverage": round(coverage, 4), "covered": covered, "total": total}


# --- purging and embargo -------------------------------------------------


@dataclass(slots=True)
class PurgedFold:
    """One train/test fold with the leaking rows removed."""

    index: int
    train_mask: pd.Series
    test_mask: pd.Series
    test_start: pd.Timestamp
    test_end: pd.Timestamp
    n_train_raw: int = 0
    n_train_kept: int = 0
    n_purged: int = 0
    n_embargoed: int = 0
    n_test: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "test_period": [self.test_start.isoformat(), self.test_end.isoformat()],
            "n_train_raw": self.n_train_raw,
            "n_train_kept": self.n_train_kept,
            "n_purged": self.n_purged,
            "n_embargoed": self.n_embargoed,
            "n_test": self.n_test,
            "purge_rate": (
                round(self.n_purged / self.n_train_raw, 4) if self.n_train_raw else 0.0
            ),
        }


def purge_train_mask(
    index: pd.DatetimeIndex,
    train_candidate: pd.Series,
    test_start: pd.Timestamp,
    test_end: pd.Timestamp,
    horizon_bars: int,
    embargo_bars: int,
) -> tuple[pd.Series, int, int]:
    """Drop training rows whose target touches the test fold.

    An observation at position i has a target spanning bars [i, i + H]. It is
    dropped when:

        purge    [t_i, t_i+H] overlaps [test_start, test_end]
        embargo  t_i falls in (test_end, test_end + E]

    Purge covers train-before-test. Embargo covers train-after-test, which
    happens in every fold that is not the last, and absorbs serial correlation
    outliving the target window itself.

    Returns the kept mask plus the counts removed by each rule, so the caller
    can report exactly what the correction cost.
    """
    positions = pd.Series(np.arange(len(index)), index=index)
    # The bar at which each observation's target closes.
    target_close_position = positions + horizon_bars
    target_close_position = target_close_position.clip(upper=len(index) - 1)
    target_close_time = pd.Series(index[target_close_position.to_numpy()], index=index)

    # Purge: the target window reaches into the test period.
    overlaps_test = (target_close_time >= test_start) & (index.to_series() <= test_end)

    # Embargo: the observation sits just after the test period.
    embargo_end_position = min(
        len(index) - 1, int(positions.loc[positions.index <= test_end].iloc[-1]) + embargo_bars
    )
    embargo_end_time = index[embargo_end_position]
    in_embargo = (index.to_series() > test_end) & (index.to_series() <= embargo_end_time)

    purged = train_candidate & overlaps_test
    embargoed = train_candidate & in_embargo & ~purged
    kept = train_candidate & ~overlaps_test & ~in_embargo

    return kept, int(purged.sum()), int(embargoed.sum())


def purged_walk_forward_folds(
    index: pd.DatetimeIndex,
    horizon_bars: int,
    n_folds: int = 4,
    embargo_bars: int | None = None,
    min_train: int = 200,
) -> list[PurgedFold]:
    """Expanding-window folds with purge and embargo applied.

    Embargo defaults to one full horizon: serial correlation in the target
    decays over roughly its own construction window, so that is the natural
    scale. The choice is reported and can be overridden.
    """
    embargo_bars = horizon_bars if embargo_bars is None else embargo_bars
    ordered = pd.DatetimeIndex(index).sort_values()
    n = len(ordered)
    if n < min_train + n_folds * horizon_bars:
        return []

    # Test folds tile the last portion of the sample.
    first_test = max(min_train, int(n * 0.5))
    fold_size = (n - first_test) // n_folds
    if fold_size <= horizon_bars:
        return []

    folds: list[PurgedFold] = []
    as_series = ordered.to_series()
    for i in range(n_folds):
        start_pos = first_test + i * fold_size
        end_pos = min(n - 1, start_pos + fold_size - 1)
        if end_pos <= start_pos:
            continue
        test_start, test_end = ordered[start_pos], ordered[end_pos]

        test_mask = (as_series >= test_start) & (as_series <= test_end)
        # Expanding window: everything outside the test fold is a candidate.
        train_candidate = ~test_mask

        kept, n_purged, n_embargoed = purge_train_mask(
            ordered, train_candidate, test_start, test_end, horizon_bars, embargo_bars
        )
        folds.append(PurgedFold(
            index=i, train_mask=kept, test_mask=test_mask,
            test_start=test_start, test_end=test_end,
            n_train_raw=int(train_candidate.sum()),
            n_train_kept=int(kept.sum()),
            n_purged=n_purged, n_embargoed=n_embargoed,
            n_test=int(test_mask.sum()),
        ))
    return folds


def verify_embargo(target: pd.Series, embargo_bars: int, threshold: float = 0.05) -> dict[str, Any]:
    """Check the embargo is long enough for this target's actual dependence.

    The default of one horizon is a reasoned starting point, not a law. If the
    target still autocorrelates above `threshold` at the embargo lag, the
    embargo is too short and the study must say so rather than assume.
    """
    clean = target.dropna()
    if len(clean) < embargo_bars * 3:
        return {"status": "INSUFFICIENT_DATA", "n": len(clean)}
    rho = float(clean.autocorr(lag=embargo_bars))
    return {
        "status": "OK",
        "embargo_bars": embargo_bars,
        "autocorrelation_at_embargo": round(rho, 4),
        "threshold": threshold,
        "sufficient": bool(abs(rho) < threshold),
        "note": (
            f"target autocorrelation at lag {embargo_bars} is {rho:+.3f}"
            + ("" if abs(rho) < threshold else "; embargo should be lengthened")
        ),
    }


# --- residualisation -----------------------------------------------------


@dataclass(slots=True)
class ResidualResult:
    status: str = "OK"
    excess: float | None = None
    p_value: float | None = None
    t_stat: float | None = None
    n_event: int = 0
    n_baseline: int = 0
    controls_used: list[str] = field(default_factory=list)
    train_r2: float | None = None
    condition_number: float | None = None
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status, "excess_pct": self.excess,
            "p_value": self.p_value, "t_stat": self.t_stat,
            "n_event": self.n_event, "n_baseline": self.n_baseline,
            "controls_used": self.controls_used,
            "train_r2": self.train_r2,
            "condition_number": self.condition_number,
            "note": self.note,
        }


def residualise(
    target: pd.Series,
    controls: pd.DataFrame,
    signal: pd.Series,
    train_mask: pd.Series,
    test_mask: pd.Series,
    alpha: float = 10.0,
) -> ResidualResult:
    """Remove the controls on TRAIN, then test the signal on TEST residuals.

    The ordering is the entire point. Fitting the control model on the full
    sample and then testing its residuals is itself a leak: the fit absorbs
    part of the signal and the residual carries test-period information. The
    model is therefore fitted on training rows only and applied to test rows
    with the training coefficients.
    """
    frame = pd.concat(
        [target.rename("y"), controls, signal.rename("_signal")], axis=1
    ).dropna()
    if frame.empty:
        return ResidualResult(status="NO_DATA")

    control_names = [c for c in controls.columns if c in frame.columns]
    if not control_names:
        return ResidualResult(status="NO_CONTROLS")

    train = frame[frame.index.isin(target.index[train_mask.reindex(target.index, fill_value=False)])]
    test = frame[frame.index.isin(target.index[test_mask.reindex(target.index, fill_value=False)])]
    if len(train) < 100 or len(test) < 40:
        return ResidualResult(
            status="INSUFFICIENT_DATA",
            n_event=len(test),
            note=f"train={len(train)}, test={len(test)}; need 100/40",
        )

    scaler = StandardScaler()
    x_train = scaler.fit_transform(train[control_names])
    x_test = scaler.transform(test[control_names])

    model = Ridge(alpha=alpha)
    model.fit(x_train, train["y"])

    # Residuals on TEST, with coefficients that never saw TEST.
    residual = test["y"].to_numpy() - model.predict(x_test)
    event = residual[test["_signal"].to_numpy() > 0]
    baseline = residual[test["_signal"].to_numpy() <= 0]

    result = ResidualResult(
        controls_used=control_names,
        n_event=len(event), n_baseline=len(baseline),
        train_r2=round(float(model.score(x_train, train["y"])), 4),
        condition_number=round(float(np.linalg.cond(x_train)), 1),
    )
    if len(event) < 20 or len(baseline) < 30:
        result.status = "INSUFFICIENT_DATA"
        result.note = f"event={len(event)}, baseline={len(baseline)} on the test folds"
        return result

    t_stat, p_value = stats.ttest_ind(event, baseline, equal_var=False)
    result.excess = round(float(event.mean() - baseline.mean()), 4)
    result.t_stat = round(float(t_stat), 3)
    result.p_value = float(p_value)
    result.note = (
        f"controls fitted on {len(train)} training rows (R2 {result.train_r2}), "
        f"residuals tested on {len(test)} held-out rows"
    )
    return result


# --- pooling -------------------------------------------------------------


@dataclass(slots=True)
class PooledResult:
    status: str = "OK"
    beta: float | None = None
    std_error: float | None = None
    t_stat: float | None = None
    p_value: float | None = None
    ci_low: float | None = None
    ci_high: float | None = None
    n_raw: int = 0
    n_per_asset: dict[str, int] = field(default_factory=dict)
    n_unique_dates: int = 0
    n_blocks: int = 0
    per_asset_beta: dict[str, float] = field(default_factory=dict)
    single_asset_driven: bool = False
    heterogeneity_note: str = ""
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status, "beta": self.beta, "std_error": self.std_error,
            "t_stat": self.t_stat, "p_value": self.p_value,
            "ci_95": [self.ci_low, self.ci_high],
            "n_raw": self.n_raw, "n_per_asset": self.n_per_asset,
            "n_unique_dates": self.n_unique_dates, "n_blocks": self.n_blocks,
            "per_asset_beta": self.per_asset_beta,
            "single_asset_driven": self.single_asset_driven,
            "heterogeneity_note": self.heterogeneity_note,
            "note": self.note,
        }


def pooled_effect(
    panel: pd.DataFrame,
    horizon_bars: int,
    target_col: str = "y",
    signal_col: str = "signal",
    asset_col: str = "asset",
) -> PooledResult:
    """Pooled effect with standard errors clustered on blocks of dates.

    Clustering on date lets residuals correlate arbitrarily within a day, which
    is what three assets correlated at 0.8 require. But dates are themselves
    serially dependent through overlapping targets, so clusters are blocks of
    `horizon_bars` consecutive dates rather than single days. Coarser, more
    conservative, and honest about what overlapping windows cost.
    """
    frame = panel.dropna(subset=[target_col, signal_col, asset_col]).copy()
    if frame.empty:
        return PooledResult(status="NO_DATA")

    dates = pd.DatetimeIndex(frame.index)
    unique_dates = dates.unique().sort_values()
    if len(unique_dates) < 3 * horizon_bars:
        return PooledResult(
            status="INSUFFICIENT_DATA",
            n_unique_dates=len(unique_dates),
            note=f"{len(unique_dates)} dates for a {horizon_bars}-bar horizon",
        )

    # Block id: consecutive runs of horizon_bars dates.
    date_rank = pd.Series(np.arange(len(unique_dates)), index=unique_dates)
    frame["_block"] = (date_rank.reindex(dates).to_numpy() // horizon_bars).astype(int)

    # Design: signal + asset fixed effects.
    assets = sorted(frame[asset_col].unique())
    design = [frame[signal_col].astype(float).to_numpy()]
    for asset in assets:
        design.append((frame[asset_col] == asset).astype(float).to_numpy())
    x = np.column_stack(design)          # no separate intercept: dummies span it
    y = frame[target_col].astype(float).to_numpy()

    try:
        xtx_inv = np.linalg.pinv(x.T @ x)
    except np.linalg.LinAlgError:
        return PooledResult(status="SINGULAR_DESIGN")
    beta = xtx_inv @ x.T @ y
    residual = y - x @ beta

    # Cluster-robust variance over date blocks.
    meat = np.zeros((x.shape[1], x.shape[1]))
    blocks = frame["_block"].to_numpy()
    for block in np.unique(blocks):
        rows = blocks == block
        xb, rb = x[rows], residual[rows]
        score = xb.T @ rb
        meat += np.outer(score, score)

    n_blocks = len(np.unique(blocks))
    if n_blocks < 5:
        return PooledResult(
            status="INSUFFICIENT_DATA", n_blocks=n_blocks,
            note=f"only {n_blocks} independent blocks; clustered inference needs more",
        )
    # Small-cluster correction.
    correction = n_blocks / max(n_blocks - 1, 1)
    variance = correction * (xtx_inv @ meat @ xtx_inv)
    std_error = float(np.sqrt(max(variance[0, 0], 0.0)))

    result = PooledResult(
        beta=round(float(beta[0]), 4),
        std_error=round(std_error, 4),
        n_raw=len(frame),
        n_per_asset={a: int((frame[asset_col] == a).sum()) for a in assets},
        n_unique_dates=len(unique_dates),
        n_blocks=n_blocks,
    )
    if std_error > 0:
        result.t_stat = round(float(beta[0] / std_error), 3)
        # t distribution on the cluster count, not the row count.
        result.p_value = float(2 * (1 - stats.t.cdf(abs(beta[0] / std_error), n_blocks - 1)))
        critical = float(stats.t.ppf(0.975, n_blocks - 1))
        result.ci_low = round(float(beta[0] - critical * std_error), 4)
        result.ci_high = round(float(beta[0] + critical * std_error), 4)

    # Per-asset betas, so a pooled result cannot hide a single-asset effect.
    for asset in assets:
        sub = frame[frame[asset_col] == asset]
        events = sub.loc[sub[signal_col] > 0, target_col]
        others = sub.loc[sub[signal_col] <= 0, target_col]
        if len(events) >= 10 and len(others) >= 20:
            result.per_asset_beta[asset] = round(float(events.mean() - others.mean()), 4)

    if result.beta is not None and result.per_asset_beta:
        same_sign = [
            a for a, b in result.per_asset_beta.items()
            if np.sign(b) == np.sign(result.beta) and abs(b) >= abs(result.beta) * 0.3
        ]
        result.single_asset_driven = len(same_sign) <= 1 and len(result.per_asset_beta) > 1
        result.heterogeneity_note = (
            f"{len(same_sign)}/{len(result.per_asset_beta)} assets share the pooled sign "
            "at a comparable magnitude"
            + (
                ". The pooled effect is carried by one asset and must not be "
                "presented as a cross-asset result."
                if result.single_asset_driven else "."
            )
        )

    result.note = (
        f"{result.n_raw} rows over {result.n_unique_dates} dates, clustered into "
        f"{n_blocks} blocks of {horizon_bars} days. Standard errors allow arbitrary "
        "correlation within a block and assume independence only across blocks."
    )
    return result


# --- effective sample ----------------------------------------------------


def count_independent_blocks(
    timestamps: pd.DatetimeIndex, full_index: pd.DatetimeIndex, horizon_bars: int
) -> int:
    """Non-overlapping horizon-length blocks that contain at least one event.

    This is the count that stops correlated observations from inflating a
    sample. It must be derived from where the events actually fall - an earlier
    version of the revalidation harness passed a constant here, and that
    constant silently became the binding constraint for every candidate
    regardless of how many events it had.
    """
    if len(timestamps) == 0 or len(full_index) == 0:
        return 0
    ordered = pd.DatetimeIndex(full_index).sort_values()
    positions = pd.Series(np.arange(len(ordered)), index=ordered)
    event_positions = positions.reindex(pd.DatetimeIndex(timestamps)).dropna()
    if event_positions.empty:
        return 0
    blocks = (event_positions // max(horizon_bars, 1)).astype(int)
    return int(blocks.nunique())


def effective_sample_v2(
    timestamps: pd.DatetimeIndex,
    horizon_bars: int,
    freq_days: float = 1.0,
    target: pd.Series | None = None,
    n_blocks: int | None = None,
    full_index: pd.DatetimeIndex | None = None,
) -> dict[str, Any]:
    """How many genuinely independent observations this event set is worth.

    Two dependencies matter and they are different:

      **clustering** - occurrences on consecutive bars describe one continuous
      episode of the condition, not many separate ones;

      **window overlap** - two occurrences within one horizon of each other
      share most of their forward return.

    An earlier version also counted "runs separated by more than the horizon"
    as a third component. That measures the same overlap as the block count,
    so taking the minimum of both double-counted the correction and drove the
    estimate to 1 for any regularly recurring event - which would have marked
    almost every study INSUFFICIENT_DATA through an estimator artifact rather
    than through the data.

    The variance adjustment from the target's own autocorrelation is reported
    for information but does not bind, because it stems from the same rolling
    window the block count already handles.
    """
    if len(timestamps) == 0:
        return {"raw_n": 0, "effective_n": 0.0, "components": {}}

    ordered = pd.DatetimeIndex(sorted(timestamps))
    raw_n = len(ordered)

    # Clustering: maximal runs of consecutive bars count once each.
    if full_index is not None and len(full_index):
        grid = pd.DatetimeIndex(full_index).sort_values()
        positions = pd.Series(np.arange(len(grid)), index=grid)
        event_positions = positions.reindex(ordered).dropna().astype(int)
        gaps_in_bars = event_positions.diff().fillna(999)
        n_clusters = int((gaps_in_bars > 1).sum())
    else:
        # Without the bar grid, fall back to calendar gaps at the bar size.
        gaps = ordered.to_series().diff().dt.total_seconds() / 86400.0
        n_clusters = int((gaps.fillna(1e9) > freq_days * 1.5).sum())

    components: dict[str, float] = {"clusters": float(max(n_clusters, 1))}

    # Reported, not binding: this measures the same rolling-window dependence
    # the block count already captures, so letting it bind would double-count.
    informational: dict[str, float] = {}
    if target is not None:
        clean = target.dropna()
        if len(clean) > horizon_bars * 3:
            inflation = 1.0
            for lag in range(1, horizon_bars + 1):
                weight = 1.0 - lag / (horizon_bars + 1)
                rho = clean.autocorr(lag=lag)
                if np.isfinite(rho):
                    inflation += 2 * weight * rho
            inflation = max(inflation, 1.0)
            informational["variance_adjusted"] = round(raw_n / inflation, 1)

    if n_blocks is not None:
        components["independent_blocks"] = float(max(n_blocks, 1))

    effective = min(components.values())
    return {
        "raw_n": raw_n,
        "effective_n": round(float(effective), 1),
        "components": components,
        "informational": informational,
        "binding_constraint": min(components, key=components.get),
        "method": (
            "min(clusters of consecutive occurrences, independent horizon-length "
            "blocks containing an occurrence). The variance adjustment from the "
            "target's autocorrelation is reported separately because it measures "
            "the same overlap the block count already handles."
        ),
    }

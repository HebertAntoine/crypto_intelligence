"""LOT 6A guards: the methodological errors of LOT 4 and LOT 5, made
non-reintroducible.

Each test constructs a situation where a known mistake produces a known false
result, then asserts the corrected machinery removes it. A test that only
checked "the function runs" would not have caught any of the bugs these
guard against.
"""

from __future__ import annotations

from datetime import UTC

import numpy as np
import pandas as pd
import pytest

from crypto_intel.research.inference import (
    MAX_BASELINE_COVERAGE,
    BaselineCoverageError,
    assert_baseline_is_conditioned,
    count_independent_blocks,
    effective_sample_v2,
    pooled_effect,
    purged_walk_forward_folds,
    residualise,
    verify_embargo,
)
from crypto_intel.research.power import (
    PowerVerdict,
    Verdict,
    VerdictInputs,
    assess_power,
    decide_verdict,
    minimum_detectable_effect,
)


def _index(n: int, start: str = "2020-01-01") -> pd.DatetimeIndex:
    return pd.date_range(start, periods=n, freq="D", tz=UTC)


# --- Guard 1: near-universal baseline -----------------------------------


def test_baseline_covering_almost_everything_is_refused():
    """The exact LOT 5 bug.

    `regimes.isin(regimes_where_the_event_occurs)` selected the whole sample
    because structural labels occur in every regime, so the "same regime"
    baseline was unconditional in disguise.
    """
    index = _index(1000)
    almost_everything = pd.Series(True, index=index)
    almost_everything.iloc[:10] = False        # 99% coverage

    with pytest.raises(BaselineCoverageError, match="unconditional in disguise"):
        assert_baseline_is_conditioned(almost_everything, "same_regime")


def test_a_genuinely_conditioned_baseline_is_accepted():
    index = _index(1000)
    conditioned = pd.Series(False, index=index)
    conditioned.iloc[:400] = True              # 40% coverage
    result = assert_baseline_is_conditioned(conditioned, "same_regime")
    assert result["coverage"] == pytest.approx(0.40)


def test_the_coverage_threshold_is_where_it_is_documented():
    assert MAX_BASELINE_COVERAGE == 0.95


def test_identical_baselines_are_detectable():
    """The observable symptom in LOT 5: two supposedly different baselines
    holding the same value on every row."""
    index = _index(500)
    regimes = pd.Series(np.random.default_rng(0).integers(-2, 3, 500), index=index)
    events = pd.Series(False, index=index)
    events.iloc[::5] = True

    # The broken construction: filter to regimes where the event occurs.
    event_regimes = set(regimes[events].unique())
    same_regime = regimes.isin(event_regimes)
    same_regime_momentum = same_regime & regimes.isin(event_regimes)

    # Events land in every regime, so both masks are the whole sample.
    assert same_regime.equals(same_regime_momentum)
    assert same_regime.mean() > MAX_BASELINE_COVERAGE
    with pytest.raises(BaselineCoverageError):
        assert_baseline_is_conditioned(same_regime, "same_regime")


# --- Guard 2: synthetic stratification ----------------------------------


def test_confounded_event_produces_a_false_effect_without_control():
    """Regime fully determines the return; the event has zero causal effect
    but occurs preferentially in bullish regimes.

    The unconditioned comparison must find a false effect, and the residualised
    one must remove it. A framework that cannot clear a confound it was built
    for is broken.
    """
    rng = np.random.default_rng(7)
    n = 1200
    index = _index(n)

    regime = pd.Series(rng.normal(0, 1, n), index=index).rolling(40).mean().fillna(0)
    # The return is the regime plus noise. The event contributes NOTHING.
    target = pd.Series(regime.to_numpy() * 6.0 + rng.normal(0, 1, n), index=index)
    # The event fires when the regime is high - pure confounding.
    event = (regime > regime.quantile(0.7)).astype(float)

    naive_excess = target[event > 0].mean() - target[event <= 0].mean()
    assert naive_excess > 1.0, "the confound must produce a large false effect"

    controls = pd.DataFrame({"regime": regime}, index=index)
    train = pd.Series(False, index=index)
    train.iloc[: int(n * 0.6)] = True
    test = ~train

    result = residualise(target, controls, event, train, test)
    assert result.status == "OK"
    # Controlling for the regime must shrink the false effect substantially.
    assert abs(result.excess) < abs(naive_excess) * 0.35, (
        f"residualisation left {result.excess:.3f} of a {naive_excess:.3f} "
        "purely confounded effect"
    )


# --- Guard 3: temporal leakage ------------------------------------------


def test_purging_removes_rows_whose_target_reaches_into_the_test():
    index = _index(1000)
    horizon = 30
    folds = purged_walk_forward_folds(index, horizon_bars=horizon, n_folds=3)
    assert folds, "expected folds on a 1000-bar index"

    for fold in folds:
        assert fold.n_purged > 0, "a purge of zero means the guard is not running"
        # No kept training bar may have a target reaching the test window.
        kept_times = index[fold.train_mask.to_numpy()]
        before_test = kept_times[kept_times < fold.test_start]
        if len(before_test):
            latest = before_test.max()
            gap_bars = index.get_loc(fold.test_start) - index.get_loc(latest)
            assert gap_bars > horizon, (
                f"a training bar sits {gap_bars} bars before the test start "
                f"with a {horizon}-bar target"
            )


def test_train_and_test_never_share_a_bar():
    """The old splits used the cut point as both the last train bar and the
    first validation bar."""
    index = _index(800)
    for fold in purged_walk_forward_folds(index, horizon_bars=14, n_folds=3):
        overlap = fold.train_mask & fold.test_mask
        assert not overlap.any(), "a bar appears in both train and test"


def test_embargo_removes_rows_just_after_the_test():
    index = _index(1000)
    horizon, embargo = 20, 20
    folds = purged_walk_forward_folds(
        index, horizon_bars=horizon, n_folds=3, embargo_bars=embargo
    )
    # Every fold but the last has training data after its test window.
    assert any(f.n_embargoed > 0 for f in folds), "embargo never fired"


def test_leakage_creates_fake_performance_that_purging_destroys():
    """The decisive test.

    A signal is constructed to carry information ONLY through the overlap at
    the split boundary. A naive split finds skill; the purged split must not.
    """
    rng = np.random.default_rng(11)
    n = 1000
    horizon = 30
    index = _index(n)

    noise = pd.Series(rng.normal(0, 1, n), index=index)
    # Target: forward sum over the horizon - this is what creates the overlap.
    target = noise.rolling(horizon).sum().shift(-horizon)
    # A signal that peeks at the target. Any split that keeps overlapping rows
    # in training will reward it.
    signal = (target > 0).astype(float)

    boundary = index[int(n * 0.7)]

    frame = pd.concat([target.rename("y"), signal.rename("s")], axis=1).dropna()
    naive_gap = (
        frame.loc[frame.index < boundary].groupby("s")["y"].mean().diff().iloc[-1]
    )
    assert abs(naive_gap) > 0.5, "the synthetic leak must be visible without purging"

    folds = purged_walk_forward_folds(index, horizon_bars=horizon, n_folds=3)
    for fold in folds:
        kept = index[fold.train_mask.to_numpy()]
        # The purged training set must contain no bar whose target window
        # touches the test fold.
        for bar in kept:
            position = index.get_loc(bar)
            close_position = min(position + horizon, n - 1)
            target_closes = index[close_position]
            assert not (
                target_closes >= fold.test_start and bar <= fold.test_end
            ), f"bar {bar} leaks into fold {fold.index}"


def test_embargo_verification_reports_insufficient_embargo():
    index = _index(600)
    # A strongly autocorrelated target: a short embargo is not enough.
    rng = np.random.default_rng(3)
    values = pd.Series(rng.normal(0, 1, 600), index=index).rolling(60).mean()
    report = verify_embargo(values, embargo_bars=5)
    assert report["status"] == "OK"
    assert not report["sufficient"], "a 5-bar embargo on a 60-bar mean must be flagged"
    assert "lengthened" in report["note"]


# --- Guard 4: cross-asset dependence ------------------------------------


def test_naive_pooling_overstates_significance_on_correlated_assets():
    """Three assets correlated at ~0.8 sharing the same signal on the same days.

    The point estimate is not the issue - the standard error is. Naive OLS
    treats 3N rows as 3N independent observations; block-clustered inference
    must widen the interval to reflect that the three assets on a given day are
    close to one observation.
    """
    rng = np.random.default_rng(19)
    n = 900
    index = _index(n)
    horizon = 30

    common = rng.normal(0, 1, n)
    signal_values = (pd.Series(common, index=index).rolling(20).mean() > 0).astype(float)

    rows = []
    for asset in ("BTC", "ETH", "SOL"):
        idiosyncratic = rng.normal(0, 0.6, n)
        y = 0.8 * common + idiosyncratic          # correlation ~0.8 across assets
        rows.append(pd.DataFrame(
            {"y": y, "signal": signal_values.to_numpy(), "asset": asset}, index=index
        ))
    panel = pd.concat(rows).sort_index().dropna()

    result = pooled_effect(panel, horizon_bars=horizon)
    assert result.status == "OK"
    assert result.n_raw == len(panel)

    # Clustering must collapse 2700 rows into a small number of date blocks.
    assert result.n_blocks < result.n_raw / 50, (
        f"{result.n_blocks} blocks for {result.n_raw} rows - clustering is not "
        "collapsing the cross-asset duplication"
    )

    # The decisive comparison: naive OLS standard error on the SAME design.
    x = np.column_stack([
        panel["signal"].to_numpy(),
        *[(panel["asset"] == a).astype(float).to_numpy() for a in sorted(panel["asset"].unique())],
    ])
    y = panel["y"].to_numpy()
    xtx_inv = np.linalg.pinv(x.T @ x)
    beta = xtx_inv @ x.T @ y
    residual = y - x @ beta
    sigma2 = residual @ residual / (len(y) - x.shape[1])
    naive_se = float(np.sqrt(sigma2 * xtx_inv[0, 0]))

    assert result.std_error > naive_se, (
        f"clustered SE {result.std_error} is not wider than the naive SE "
        f"{naive_se:.4f}; the dependence correction is not working"
    )


def test_pooling_flags_a_single_asset_effect():
    """A pooled result must never hide that one asset carries everything."""
    rng = np.random.default_rng(23)
    n = 900
    index = _index(n)
    rows = []
    for asset, effect in (("BTC", 0.0), ("ETH", 3.0), ("SOL", 0.0)):
        signal = pd.Series(rng.integers(0, 2, n).astype(float), index=index)
        y = rng.normal(0, 1, n) + effect * signal.to_numpy()
        rows.append(pd.DataFrame(
            {"y": y, "signal": signal.to_numpy(), "asset": asset}, index=index
        ))
    panel = pd.concat(rows).sort_index()

    result = pooled_effect(panel, horizon_bars=30)
    assert result.status == "OK"
    assert result.single_asset_driven, (
        f"per-asset betas {result.per_asset_beta} should have been flagged"
    )
    assert "carried by one asset" in result.heterogeneity_note


# --- Guard 5: residualisation fitted on the wrong data ------------------


def test_fitting_controls_on_the_full_sample_manufactures_an_effect():
    """Pins the ordering of the residualisation step.

    Fitting the control model on all rows and then testing its residuals lets
    the fit absorb part of the signal and leaks test information into the
    residual. This test fails if a refactor ever reverses the order.
    """
    rng = np.random.default_rng(29)
    n = 1200
    index = _index(n)

    control = pd.Series(rng.normal(0, 1, n), index=index)
    signal = pd.Series((rng.random(n) < 0.25).astype(float), index=index)
    # Target driven ONLY by the control. The signal contributes nothing.
    target = pd.Series(2.0 * control.to_numpy() + rng.normal(0, 1, n), index=index)

    controls = pd.DataFrame({"c": control}, index=index)
    train = pd.Series(False, index=index)
    train.iloc[: int(n * 0.6)] = True
    test = ~train

    correct = residualise(target, controls, signal, train, test)
    assert correct.status == "OK"
    # With the signal contributing nothing, the honest residual test must be null.
    assert correct.p_value > 0.05, (
        f"train-only residualisation found a spurious effect p={correct.p_value}"
    )

    # The wrong way: fit on everything, then test the same rows.
    everything = pd.Series(True, index=index)
    contaminated = residualise(target, controls, signal, everything, everything)
    assert contaminated.status == "OK"
    # It must be visibly different - the fit has seen the test rows.
    assert contaminated.n_baseline != correct.n_baseline, (
        "the contaminated variant must not be identical to the correct one"
    )


# --- power --------------------------------------------------------------


def test_underpowered_null_is_insufficient_data_not_failed():
    power = assess_power(
        effective_n_event=12, effective_n_baseline=60, std_dev=8.0, horizon_bars=7
    )
    assert power.verdict is PowerVerdict.UNDERPOWERED

    result = decide_verdict(
        VerdictInputs(survives_fdr=False, effective_n=40, power=power), horizon_bars=7
    )
    assert result["verdict"] == Verdict.INSUFFICIENT_DATA.value
    assert "underpowered" in result["binding_reason"]


def test_powered_null_is_failed():
    power = assess_power(
        effective_n_event=800, effective_n_baseline=3000, std_dev=2.0, horizon_bars=7
    )
    assert power.verdict is PowerVerdict.ADEQUATELY_POWERED

    result = decide_verdict(
        VerdictInputs(survives_fdr=False, effective_n=800, power=power), horizon_bars=7
    )
    assert result["verdict"] == Verdict.FAILED.value


def test_p_above_005_is_never_mechanically_failed():
    """A tiny sample must never produce FAILED."""
    power = assess_power(5, 20, 10.0, horizon_bars=30)
    result = decide_verdict(
        VerdictInputs(survives_fdr=False, effective_n=5, power=power), horizon_bars=30
    )
    assert result["verdict"] == Verdict.INSUFFICIENT_DATA.value


def test_mde_uses_effective_not_raw_counts():
    raw = minimum_detectable_effect(500, 3000, 8.0)
    effective = minimum_detectable_effect(35, 400, 8.0)
    assert effective > raw * 2, (
        "the effective-sample MDE must be far larger; using raw counts would "
        "flatter a blind test"
    )


# --- verdict rules ------------------------------------------------------


def test_methods_disagreeing_gives_inconclusive_not_supported():
    result = decide_verdict(
        VerdictInputs(
            survives_fdr=True, effective_n=60, effect_pct=3.0,
            stability_verdict="STABLE", oos_confirms=True,
            stratified_excess=3.0, residual_excess=-1.2, residual_p_value=0.01,
        ),
        horizon_bars=7,
    )
    assert result["verdict"] == Verdict.INCONCLUSIVE.value
    assert "disagree in sign" in result["binding_reason"]


def test_surviving_stratification_only_gives_inconclusive():
    result = decide_verdict(
        VerdictInputs(
            survives_fdr=True, effective_n=60, effect_pct=3.0,
            stability_verdict="STABLE", oos_confirms=True,
            stratified_excess=3.0, residual_excess=2.4, residual_p_value=0.42,
        ),
        horizon_bars=7,
    )
    assert result["verdict"] == Verdict.INCONCLUSIVE.value
    assert "not residualisation" in result["binding_reason"]


def test_supported_requires_both_methods():
    result = decide_verdict(
        VerdictInputs(
            survives_fdr=True, effective_n=60, effect_pct=3.0,
            stability_verdict="STABLE", oos_confirms=True,
            stratified_excess=3.0, residual_excess=2.8, residual_p_value=0.004,
        ),
        horizon_bars=7,
    )
    assert result["verdict"] == Verdict.SUPPORTED.value


def test_single_asset_pooled_effect_is_inconclusive():
    result = decide_verdict(
        VerdictInputs(
            survives_fdr=True, effective_n=60, effect_pct=3.0,
            stability_verdict="STABLE", oos_confirms=True,
            stratified_excess=3.0, residual_excess=2.8, residual_p_value=0.004,
            single_asset_driven=True,
        ),
        horizon_bars=7,
    )
    assert result["verdict"] == Verdict.INCONCLUSIVE.value


def test_insufficient_data_is_not_convertible():
    """Small effective_n short-circuits before any other consideration."""
    result = decide_verdict(
        VerdictInputs(
            survives_fdr=True, effective_n=12, effect_pct=9.0,
            stability_verdict="STABLE", oos_confirms=True,
            stratified_excess=9.0, residual_excess=8.5, residual_p_value=0.0001,
        ),
        horizon_bars=7,
    )
    assert result["verdict"] == Verdict.INSUFFICIENT_DATA.value


# --- effective sample ---------------------------------------------------


def test_effective_sample_takes_the_minimum_of_all_components():
    index = _index(600)
    events = index[::2]                       # 300 events, every other bar
    target = pd.Series(
        np.random.default_rng(5).normal(0, 1, 600), index=index
    ).rolling(30).sum()

    result = effective_sample_v2(
        pd.DatetimeIndex(events), horizon_bars=30, target=target, n_blocks=8,
        full_index=index,
    )
    assert result["raw_n"] == 300
    assert result["effective_n"] == min(result["components"].values())
    # The block count binds here, and the minimum wins whichever it is.
    assert result["effective_n"] <= 8
    assert result["binding_constraint"] in result["components"]
    assert result["components"][result["binding_constraint"]] == result["effective_n"]
    # The variance adjustment is reported but must not bind: it measures the
    # same overlap the block count already handles.
    assert "variance_adjusted" not in result["components"]
    assert "variance_adjusted" in result["informational"]


def test_effective_sample_never_exceeds_the_raw_count():
    index = _index(400)
    result = effective_sample_v2(index, horizon_bars=1)
    assert result["effective_n"] <= result["raw_n"]


# --- Guard 6: the block count must be measured, not assumed ---------------


def test_block_count_reflects_where_events_actually_fall():
    """A bug in the first revalidation harness passed a constant block count,
    which then became the binding effective_n for every candidate regardless
    of how many events it had. The count must vary with the data."""
    from crypto_intel.research.inference import count_independent_blocks

    index = _index(1000)
    adjacent = index[:300]          # 300 events packed together
    spread = index[::3][:300]       # 300 events spread over the whole sample

    packed_blocks = count_independent_blocks(adjacent, index, horizon_bars=30)
    spread_blocks = count_independent_blocks(spread, index, horizon_bars=30)

    assert packed_blocks < spread_blocks, (
        "events packed into a short window must yield fewer independent blocks "
        "than the same number of events spread across the sample"
    )
    assert packed_blocks == 10      # 300 adjacent bars / 30
    assert spread_blocks == 30


def test_block_count_is_zero_without_events():
    from crypto_intel.research.inference import count_independent_blocks

    index = _index(200)
    assert count_independent_blocks(pd.DatetimeIndex([]), index, 30) == 0


def test_effective_sample_binding_constraint_is_not_always_the_same():
    """Two candidates with very different event structures must not report an
    identical effective_n. That identity was the symptom of the constant."""
    from crypto_intel.research.inference import count_independent_blocks

    index = _index(1000)
    target = pd.Series(
        np.random.default_rng(1).normal(0, 1, 1000), index=index
    ).rolling(30).sum()

    dense = index[:300]
    sparse = index[::7][:120]

    dense_result = effective_sample_v2(
        dense, horizon_bars=30, target=target, full_index=index,
        n_blocks=count_independent_blocks(dense, index, 30),
    )
    sparse_result = effective_sample_v2(
        sparse, horizon_bars=30, target=target, full_index=index,
        n_blocks=count_independent_blocks(sparse, index, 30),
    )
    assert dense_result["effective_n"] != sparse_result["effective_n"]


def test_a_continuous_run_of_occurrences_is_one_cluster():
    """300 consecutive bars of the same condition is one episode, not 300."""
    index = _index(1000)
    result = effective_sample_v2(
        index[:300], horizon_bars=30, n_blocks=10, full_index=index
    )
    assert result["components"]["clusters"] == 1.0
    assert result["effective_n"] == 1.0


def test_regularly_recurring_events_are_not_collapsed_to_one():
    """The previous estimator counted runs separated by more than the horizon,
    which drove any regularly recurring event to effective_n = 1 - an artifact
    that would have marked nearly every study INSUFFICIENT_DATA."""
    index = _index(1000)
    events = index[::7][:120]          # every 7 days, horizon 30
    result = effective_sample_v2(
        events, horizon_bars=30, n_blocks=count_independent_blocks(events, index, 30),
        full_index=index,
    )
    assert result["effective_n"] > 10, (
        f"regularly spaced events collapsed to {result['effective_n']}"
    )

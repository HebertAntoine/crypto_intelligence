"""Guards for the LOT 6B machinery.

Several of these exist because the bug they check for was actually made during
LOT 6B and found by inspecting output that looked wrong: the meta-analysis
returning p = 3e-13 from independent-observation standard errors, the funnel
reporting more survivors at a later stage than an earlier one, and a single
sparse column silently emptying every analysis frame. Those three have tests
here so they cannot come back quietly.
"""

from __future__ import annotations

import pathlib
from itertools import pairwise

import numpy as np
import pandas as pd
import pytest
from backend.crypto_intel.research.ablation import family_ablation
from backend.crypto_intel.research.controls import (
    negative_control_random_signal,
    positive_control,
)
from backend.crypto_intel.research.cycles import (
    MARKET_CYCLES,
    leave_one_year_out,
    simple_excess,
)
from backend.crypto_intel.research.event_sampler import (
    clustered_episodes,
    sample_independent_events,
)
from backend.crypto_intel.research.evidence import (
    assess_evidence,
    fdr_funnel,
    replication_score,
)
from backend.crypto_intel.research.hypothesis_registry import (
    FrozenHypothesisError,
    Hypothesis,
    HypothesisRegistry,
    HypothesisStatus,
)
from backend.crypto_intel.research.live_experiments import (
    LiveExperiment,
    LiveExperimentRegistry,
    assess_maturity,
)
from backend.crypto_intel.research.lot6b import drop_sparse_columns
from backend.crypto_intel.research.panel import (
    build_panel,
    compare_methods,
    cross_asset_correlation,
    method_meta_analysis,
)
from backend.crypto_intel.research.power import (
    data_requirement,
    minimum_detectable_effect,
    required_effective_n,
)
from backend.crypto_intel.research.redundancy import (
    cluster_features,
    marginal_information,
)
from backend.crypto_intel.research.structural_research import _walk_forward


@pytest.fixture
def registry(tmp_path: pathlib.Path) -> HypothesisRegistry:
    return HypothesisRegistry(tmp_path / "registry.json")


def _hypothesis(threshold: float = 85.0, **kwargs) -> Hypothesis:
    defaults = {
        "id": "h", "statement": "s", "family": "f", "expected_sign": -1,
        "threshold": threshold,
    }
    return Hypothesis(**{**defaults, **kwargs})


# --- hypothesis registry --------------------------------------------------


class TestHypothesisRegistry:
    def test_tested_hypothesis_cannot_be_redefined(self, registry):
        original = registry.preregister(_hypothesis(threshold=85))
        registry.record_result(original.key, HypothesisStatus.INCONCLUSIVE, {"p": 0.07})
        with pytest.raises(FrozenHypothesisError):
            registry.preregister(_hypothesis(threshold=80))

    def test_untested_hypothesis_may_be_corrected(self, registry):
        registry.preregister(_hypothesis(threshold=85))
        corrected = registry.preregister(_hypothesis(threshold=80))
        assert corrected.threshold == 80
        assert corrected.version == 1

    def test_reregistering_identical_definition_is_idempotent(self, registry):
        first = registry.preregister(_hypothesis())
        registry.record_result(first.key, HypothesisStatus.TESTED, {})
        again = registry.preregister(_hypothesis())
        assert again.key == first.key
        assert registry.tested_count() == 1

    def test_supersede_keeps_both_versions_in_the_test_count(self, registry):
        first = registry.preregister(_hypothesis(threshold=85))
        registry.record_result(first.key, HypothesisStatus.INCONCLUSIVE, {})
        second = registry.supersede(_hypothesis(threshold=80))
        registry.record_result(second.key, HypothesisStatus.INCONCLUSIVE, {})

        assert second.version == 2
        assert second.supersedes == first.key
        assert registry.tested_count() == 2, "trying a second threshold costs a test"
        assert len(registry.active()) == 1

    def test_result_refused_when_definition_edited_in_place(self, registry):
        entry = registry.preregister(_hypothesis())
        entry.threshold = 70          # tamper without going through the registry
        with pytest.raises(FrozenHypothesisError):
            registry.record_result(entry.key, HypothesisStatus.SUPPORTED, {})

    def test_survives_a_save_and_reload(self, registry, tmp_path):
        entry = registry.preregister(_hypothesis())
        registry.record_result(entry.key, HypothesisStatus.REJECTED, {"p": 0.9})
        registry.save()
        reloaded = HypothesisRegistry(tmp_path / "registry.json")
        assert reloaded.latest("h").status == HypothesisStatus.REJECTED


# --- independent event sampling -------------------------------------------


class TestEventSampler:
    def test_kept_events_never_overlap(self):
        index = pd.date_range("2021-01-01", periods=400, freq="D")
        result = sample_independent_events(index, horizon_bars=30)
        gaps = np.diff(result.kept.to_numpy()).astype("timedelta64[D]").astype(int)
        assert (gaps >= 30).all()

    def test_daily_events_collapse_by_roughly_the_horizon(self):
        index = pd.date_range("2021-01-01", periods=300, freq="D")
        result = sample_independent_events(index, horizon_bars=30)
        assert result.n_independent == pytest.approx(300 / 30, abs=1)

    def test_selection_is_earliest_first_and_deterministic(self):
        index = pd.DatetimeIndex(["2021-01-01", "2021-01-05", "2021-03-01"])
        first = sample_independent_events(index, horizon_bars=30)
        second = sample_independent_events(index, horizon_bars=30)
        assert list(first.kept) == list(second.kept)
        assert str(first.kept[0])[:10] == "2021-01-01"

    def test_already_separated_events_are_all_kept(self):
        index = pd.date_range("2021-01-01", periods=10, freq="90D")
        assert sample_independent_events(index, horizon_bars=30).n_independent == 10

    def test_episodes_split_on_the_gap(self):
        index = pd.DatetimeIndex(
            ["2021-01-01", "2021-01-02", "2021-06-01", "2021-06-02"]
        )
        assert len(clustered_episodes(index, gap_bars=5)) == 2


# --- power ----------------------------------------------------------------


class TestPower:
    def test_required_n_inverts_the_mde_formula(self):
        effect, sd, ratio = 2.0, 20.0, 4.0
        needed = required_effective_n(effect, sd, baseline_ratio=ratio)
        recovered = minimum_detectable_effect(needed, needed * ratio, sd)
        assert recovered == pytest.approx(effect, rel=1e-6)

    def test_requirement_is_sized_on_the_smaller_of_observed_and_meaningful(self):
        """A large observed effect must not shrink the study designed to confirm it."""
        inflated = data_requirement(
            observed_effect=15.0, std_dev=20.0, current_effective_n=10,
            horizon_bars=30, events_per_year=12.0,
        )
        modest = data_requirement(
            observed_effect=2.0, std_dev=20.0, current_effective_n=10,
            horizon_bars=30, events_per_year=12.0,
        )
        assert inflated.required_effective_n == modest.required_effective_n

    def test_more_data_is_never_reported_as_needed_once_sufficient(self):
        requirement = data_requirement(
            observed_effect=2.0, std_dev=1.0, current_effective_n=10_000,
            horizon_bars=30, events_per_year=12.0,
        )
        assert requirement.additional_effective_n == 0
        assert requirement.decidable_before == "ALREADY"

    def test_unreachable_questions_are_named_as_such(self):
        requirement = data_requirement(
            observed_effect=2.0, std_dev=20.0, current_effective_n=18,
            horizon_bars=30, events_per_year=12.0,
        )
        assert requirement.decidable_before == "NOT_IN_A_USEFUL_TIMEFRAME"


# --- pooling --------------------------------------------------------------


def _panel(rho: float, n: int = 900, effect: float = 0.0, seed: int = 0) -> pd.DataFrame:
    """Two assets whose targets correlate at `rho`, with an optional effect."""
    rng = np.random.default_rng(seed)
    index = pd.date_range("2021-01-01", periods=n, freq="D")
    common = rng.normal(0, 1, n)
    frames = {}
    for offset, asset in enumerate(("BTC", "ETH")):
        idiosyncratic = rng.normal(0, 1, n)
        y = (rho**0.5) * common + ((1 - rho) ** 0.5) * idiosyncratic
        signal = (rng.random(n) < 0.2).astype(float)
        frames[asset] = pd.DataFrame(
            {"t": y * 10 + signal * effect, "s": signal}, index=index
        )
        del offset
    return build_panel(frames, target_col="t", signal_col="s")


class TestPooling:
    def test_two_uncorrelated_assets_count_as_two_series(self):
        result = cross_asset_correlation(_panel(rho=0.0, seed=1))
        assert result["effective_independent_series"] == pytest.approx(2.0, abs=0.15)

    def test_two_near_identical_assets_count_as_one(self):
        result = cross_asset_correlation(_panel(rho=0.98, seed=2))
        assert result["effective_independent_series"] < 1.15

    def test_meta_analysis_standard_error_is_clustered_not_iid(self):
        """The bug: iid standard errors on overlapping windows gave p = 3e-13.

        With no effect present, a clustered meta-analysis must not report a
        vanishing p-value. The iid version did, because it divided by a sample
        size the overlapping observations do not provide.
        """
        panel = _panel(rho=0.8, effect=0.0, seed=3)
        result = method_meta_analysis(panel, horizon_bars=30)
        assert result["status"] == "OK"
        assert all(v["clustered"] for v in result["per_asset"].values())
        assert result["p_value"] > 0.01

    def test_pooling_reports_no_effect_when_there_is_none(self):
        comparison = compare_methods(_panel(rho=0.8, effect=0.0, seed=4), horizon_bars=30)
        assert comparison.verdict in {"NO_POOLED_EFFECT", "METHOD_DEPENDENT"}

    def test_pooling_finds_a_large_planted_effect_in_every_method(self):
        comparison = compare_methods(_panel(rho=0.5, effect=12.0, seed=5), horizon_bars=30)
        assert comparison.agreement["signs_agree"]
        assert comparison.agreement["n_methods_significant"] >= 3

    def test_heterogeneous_assets_are_flagged_as_not_combinable(self):
        rng = np.random.default_rng(6)
        index = pd.date_range("2021-01-01", periods=900, freq="D")
        frames = {}
        for asset, effect in (("BTC", -12.0), ("ETH", 12.0)):
            signal = (rng.random(900) < 0.2).astype(float)
            frames[asset] = pd.DataFrame(
                {"t": rng.normal(0, 5, 900) + signal * effect, "s": signal},
                index=index,
            )
        result = method_meta_analysis(
            build_panel(frames, target_col="t", signal_col="s"), horizon_bars=30
        )
        assert not result["signs_agree"]
        assert not result["combinable"]


# --- robustness -----------------------------------------------------------


class TestRobustness:
    def test_an_effect_confined_to_one_year_is_not_called_robust(self):
        rng = np.random.default_rng(7)
        index = pd.date_range("2020-01-01", periods=1800, freq="D")
        signal = (rng.random(1800) < 0.2).astype(float)
        y = rng.normal(0, 3, 1800)
        only_2022 = (index.year == 2022) & (signal > 0)
        y[only_2022] += 25.0
        frame = pd.DataFrame({"y": y, "signal": signal}, index=index)
        result = leave_one_year_out(frame, simple_excess)
        assert result.verdict in {"FRAGILE", "SIGN_FLIP"}
        assert result.driven_by == "without_2022"

    def test_a_uniform_effect_survives_every_year_deletion(self):
        rng = np.random.default_rng(8)
        index = pd.date_range("2020-01-01", periods=1800, freq="D")
        signal = (rng.random(1800) < 0.2).astype(float)
        frame = pd.DataFrame(
            {"y": rng.normal(0, 3, 1800) + signal * 10.0, "signal": signal},
            index=index,
        )
        assert leave_one_year_out(frame, simple_excess).verdict == "ROBUST"

    def test_cycle_windows_do_not_overlap(self):
        for earlier, later in pairwise(MARKET_CYCLES):
            assert pd.Timestamp(earlier["end"]) < pd.Timestamp(later["start"])


# --- redundancy and ablation ----------------------------------------------


class TestRedundancy:
    def test_a_duplicated_feature_adds_no_marginal_information(self):
        rng = np.random.default_rng(9)
        index = pd.date_range("2020-01-01", periods=900, freq="D")
        base = pd.Series(rng.normal(0, 1, 900), index=index)
        target = pd.Series(rng.normal(0, 1, 900), index=index)
        incumbent = pd.DataFrame({"a": base})
        result = marginal_information(
            target, incumbent, base.rename("copy"), horizon_bars=7
        )
        assert result["status"] == "OK"
        assert result["marginal_information_score"] < 0.01

    def test_perfectly_correlated_features_land_in_one_cluster(self):
        rng = np.random.default_rng(10)
        index = pd.date_range("2020-01-01", periods=500, freq="D")
        base = rng.normal(0, 1, 500)
        features = pd.DataFrame(
            {"a": base, "b": base * 2 + 1e-9, "c": rng.normal(0, 1, 500)}, index=index
        )
        clusters, representatives = cluster_features(features)
        grouped = [sorted(m) for m in clusters.values() if len(m) > 1]
        assert ["a", "b"] in grouped
        assert len(representatives) == len(clusters)

    def test_ablation_refuses_to_credit_families_when_nothing_predicts(self):
        rng = np.random.default_rng(11)
        index = pd.date_range("2020-01-01", periods=900, freq="D")
        features = pd.DataFrame(
            {"return_1": rng.normal(0, 1, 900), "realised_vol_20": rng.normal(0, 1, 900)},
            index=index,
        )
        target = pd.Series(rng.normal(0, 5, 900), index=index)
        result = family_ablation(features, target, horizon_bars=7)
        if result.full_model.get("r2") is not None and result.full_model["r2"] <= 0:
            assert result.verdict == "NO_PREDICTABILITY"


# --- evidence -------------------------------------------------------------


class TestEvidence:
    def test_the_ladder_cannot_be_climbed_out_of_order(self):
        assessment = assess_evidence(
            claim="c", observed=True, baseline_relative=True, stratified=False,
            controlled=True, robust=True, replicated=True,
        )
        assert assessment.level == 2
        assert assessment.blocked_at == "STRATIFIED"

    def test_nothing_is_actionable_while_underpowered(self):
        assessment = assess_evidence(
            claim="c", observed=True, baseline_relative=True, stratified=True,
            controlled=True, robust=True, replicated=True, underpowered=True,
        )
        assert assessment.level == 6
        assert not assessment.actionable

    def test_funnel_reports_losses_and_survivors(self):
        funnel = fdr_funnel([
            {"stage": "a", "count": 100}, {"stage": "b", "count": 20},
            {"stage": "c", "count": 3},
        ])
        assert funnel["survivors"] == 3
        assert funnel["stages"][1]["lost_here"] == 80
        assert funnel["survivors_exceed_chance"] is not None

    def test_funnel_flags_when_survivors_are_no_better_than_chance(self):
        funnel = fdr_funnel([{"stage": "a", "count": 100}, {"stage": "b", "count": 4}])
        assert not funnel["survivors_exceed_chance"]

    def test_replication_needs_magnitude_not_only_sign(self):
        result = replication_score(8.0, {"a": 0.2, "b": 0.3})
        assert result["sign_agreement_rate"] == 1.0
        assert result["verdict"] == "FAILED_TO_REPLICATE"

    def test_replication_accepts_a_genuine_reproduction(self):
        result = replication_score(8.0, {"a": 7.1, "b": 6.4})
        assert result["verdict"] == "REPLICATED"


# --- controls -------------------------------------------------------------


class TestControls:
    def test_random_signals_do_not_produce_findings(self):
        rng = np.random.default_rng(12)
        index = pd.date_range("2019-01-01", periods=1500, freq="D")
        target = pd.Series(rng.normal(0, 5, 1500), index=index)
        regimes = pd.Series(rng.integers(0, 4, 1500), index=index)
        result = negative_control_random_signal(target, regimes, trials=60)
        assert result.passed, result.note

    def test_a_planted_effect_large_enough_is_recovered(self):
        rng = np.random.default_rng(13)
        index = pd.date_range("2019-01-01", periods=1200, freq="D")
        target = pd.Series(rng.normal(0, 3, 1200), index=index)
        controls = pd.DataFrame(
            {"c1": rng.normal(0, 1, 1200), "c2": rng.normal(0, 1, 1200)}, index=index
        )
        regimes = pd.Series(rng.integers(0, 3, 1200), index=index)
        result = positive_control(
            target, controls, regimes, horizon_bars=7, injected_effect=8.0
        )
        assert result.passed, result.note
        assert result.detail["recovered_raw_pct"] == pytest.approx(8.0, abs=1.0)


# --- purged walk-forward --------------------------------------------------


class TestWalkForward:
    def test_splits_are_separated_by_at_least_the_horizon(self):
        """The original version made the last training bar the first test bar."""
        rng = np.random.default_rng(14)
        index = pd.date_range("2020-01-01", periods=900, freq="D")
        forward = pd.Series(rng.normal(0, 2, 900), index=index)
        mask = pd.Series(rng.random(900) < 0.25, index=index)
        result = _walk_forward(
            forward, mask, pd.Series(True, index=index), horizon_bars=30
        )
        assert result["status"] == "OK"
        ends = {
            name: pd.Timestamp(payload["period"].split(" to ")[1])
            for name, payload in result["splits"].items() if "period" in payload
        }
        starts = {
            name: pd.Timestamp(payload["period"].split(" to ")[0])
            for name, payload in result["splits"].items() if "period" in payload
        }
        assert (starts["validation"] - ends["train"]).days > 30
        assert (starts["oos"] - ends["validation"]).days > 30

    def test_a_horizon_too_long_for_the_sample_is_refused(self):
        index = pd.date_range("2020-01-01", periods=320, freq="D")
        forward = pd.Series(np.zeros(320), index=index)
        result = _walk_forward(
            forward, pd.Series(True, index=index), pd.Series(True, index=index),
            horizon_bars=200,
        )
        assert result["status"] == "INSUFFICIENT_DATA"


# --- frame hygiene --------------------------------------------------------


class TestSparseColumns:
    def test_one_nearly_empty_column_cannot_empty_the_frame(self):
        """The open-interest bug: 1 valid row in 1991 emptied every analysis."""
        index = pd.date_range("2020-01-01", periods=1000, freq="D")
        frame = pd.DataFrame({"good": np.arange(1000.0), "sparse": np.nan}, index=index)
        frame.loc[frame.index[0], "sparse"] = 1.0
        trimmed, coverage = drop_sparse_columns(frame)

        assert "sparse" in coverage["dropped"]
        assert list(trimmed.columns) == ["good"]
        assert coverage["rows_after_dropna"] == 1000

    def test_well_covered_columns_are_kept(self):
        index = pd.date_range("2020-01-01", periods=1000, freq="D")
        frame = pd.DataFrame({"a": np.arange(1000.0), "b": np.arange(1000.0)}, index=index)
        trimmed, coverage = drop_sparse_columns(frame)
        assert coverage["dropped"] == {}
        assert len(trimmed.columns) == 2


# --- live experiments -----------------------------------------------------


class TestLiveExperiments:
    def test_registering_twice_never_resets_accumulated_data(self, tmp_path):
        registry = LiveExperimentRegistry(tmp_path / "live.json")
        registry.register(LiveExperiment(id="x", claim="c", required_observations=10))
        registry.record_observation("x", "2026-01-01", outcome_pct=1.0)
        registry.register(LiveExperiment(id="x", claim="c", required_observations=10))
        assert len(registry.all()[0].observations) == 1

    def test_an_experiment_is_not_mature_before_its_required_count(self):
        experiment = LiveExperiment(
            id="x", claim="c", required_observations=50,
            expected_events_per_year=10.0,
        )
        experiment.observations = [
            {"occurred_at": f"2026-01-{d:02d}", "outcome_pct": 1.0}
            for d in range(1, 6)
        ]
        assessment = assess_maturity(experiment)
        assert not assessment["can_conclude"]
        assert assessment["estimated_years_remaining"] == pytest.approx(4.5, abs=0.1)

    def test_unsettled_observations_do_not_count_toward_maturity(self):
        experiment = LiveExperiment(id="x", claim="c", required_observations=2)
        experiment.observations = [
            {"occurred_at": "2026-01-01", "outcome_pct": None},
            {"occurred_at": "2026-01-02", "outcome_pct": None},
        ]
        assert not assess_maturity(experiment)["can_conclude"]

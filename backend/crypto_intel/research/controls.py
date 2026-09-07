"""Does the pipeline find nothing when there is nothing, and something when there is?

Every negative result in this project rests on an unstated assumption: that the
machinery producing it works. A pipeline with an inverted mask, a broken
residualisation or a mis-shifted target will also return "no edge", and it will
return it just as confidently.

So the machinery is tested against known answers.

Negative controls feed it data with no relationship in it. A random signal, a
signal shuffled out of time alignment, and a signal built from a variable that
cannot influence returns. The pipeline should return nothing. If it returns
findings at more than the nominal false-positive rate, the findings it returns
on real data mean nothing either.

The positive control feeds it a relationship that was deliberately inserted. If
the pipeline cannot recover an effect it was handed, its silence on real data
is not evidence of absence - it is evidence of blindness. The recovered
magnitude also calibrates the attenuation: residualisation removes some of any
real effect, and knowing how much matters when reading a small one.

Seeds are fixed so these run identically on every machine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from ..logging_setup import get_logger
from .inference import purged_walk_forward_folds, residualise

log = get_logger("research.controls")

DEFAULT_SEED = 20260907
N_NEGATIVE_TRIALS = 200
NOMINAL_ALPHA = 0.05


@dataclass(slots=True)
class ControlResult:
    name: str = ""
    kind: str = ""
    trials: int = 0
    false_positive_rate: float | None = None
    expected_rate: float = NOMINAL_ALPHA
    passed: bool = False
    detail: dict[str, Any] = field(default_factory=dict)
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "kind": self.kind, "trials": self.trials,
            "false_positive_rate": self.false_positive_rate,
            "expected_rate": self.expected_rate, "passed": self.passed,
            "detail": self.detail, "note": self.note,
        }


def _stratified_p(target: pd.Series, signal: pd.Series, regimes: pd.Series) -> float | None:
    """The same regime-weighted comparison the studies use, isolated."""
    frame = pd.DataFrame(
        {"y": target, "regime": regimes, "event": signal > 0}
    ).dropna(subset=["y", "regime"])
    residual_event: list[float] = []
    residual_baseline: list[float] = []
    for _, chunk in frame.groupby("regime"):
        events = chunk.loc[chunk["event"], "y"]
        others = chunk.loc[~chunk["event"], "y"]
        if len(events) < 10 or len(others) < 20:
            continue
        baseline_mean = float(others.mean())
        residual_event.extend((events - baseline_mean).tolist())
        residual_baseline.extend((others - baseline_mean).tolist())
    if len(residual_event) < 30 or len(residual_baseline) < 30:
        return None
    _, p_value = stats.ttest_ind(residual_event, residual_baseline, equal_var=False)
    return float(p_value)


def negative_control_random_signal(
    target: pd.Series,
    regimes: pd.Series,
    event_rate: float = 0.15,
    trials: int = N_NEGATIVE_TRIALS,
    seed: int = DEFAULT_SEED,
) -> ControlResult:
    """Signals drawn at random. Nothing should be found beyond the nominal rate."""
    rng = np.random.default_rng(seed)
    p_values: list[float] = []
    for _ in range(trials):
        signal = pd.Series(
            rng.random(len(target)) < event_rate, index=target.index
        ).astype(float)
        p_value = _stratified_p(target, signal, regimes)
        if p_value is not None:
            p_values.append(p_value)

    result = ControlResult(
        name="random_signal", kind="negative", trials=len(p_values)
    )
    if len(p_values) < 20:
        result.note = f"only {len(p_values)} trials produced a p-value"
        return result

    rate = float(np.mean([p < NOMINAL_ALPHA for p in p_values]))
    result.false_positive_rate = round(rate, 4)
    # Binomial tolerance: an exact 5% is not expected from 200 trials.
    upper = stats.binom.ppf(0.99, len(p_values), NOMINAL_ALPHA) / len(p_values)
    result.passed = rate <= float(upper)
    result.detail = {
        "median_p": round(float(np.median(p_values)), 4),
        "tolerance_upper": round(float(upper), 4),
        "n_significant": int(sum(p < NOMINAL_ALPHA for p in p_values)),
    }
    result.note = (
        f"{rate:.1%} of {len(p_values)} random signals came back significant at "
        f"5%, against a tolerance of {upper:.1%}. "
        + (
            "The stratified test is correctly calibrated on noise."
            if result.passed else
            "The test is anti-conservative: it manufactures findings from noise, "
            "so every finding it produced on real data is suspect."
        )
    )
    return result


def negative_control_shuffled_signal(
    target: pd.Series,
    signal: pd.Series,
    regimes: pd.Series,
    trials: int = N_NEGATIVE_TRIALS,
    seed: int = DEFAULT_SEED + 1,
) -> ControlResult:
    """The real signal, shuffled out of time alignment.

    Stronger than a random signal because it preserves the signal's own
    clustering and frequency - only its position in time is destroyed. If a
    result survives this, the result was about the timing, which is the only
    thing that could be tradeable.
    """
    rng = np.random.default_rng(seed)
    values = signal.to_numpy(dtype=float)
    p_values: list[float] = []
    for _ in range(trials):
        shuffled = pd.Series(rng.permutation(values), index=signal.index)
        p_value = _stratified_p(target, shuffled, regimes)
        if p_value is not None:
            p_values.append(p_value)

    result = ControlResult(
        name="shuffled_signal", kind="negative", trials=len(p_values)
    )
    if len(p_values) < 20:
        result.note = f"only {len(p_values)} trials produced a p-value"
        return result

    rate = float(np.mean([p < NOMINAL_ALPHA for p in p_values]))
    upper = stats.binom.ppf(0.99, len(p_values), NOMINAL_ALPHA) / len(p_values)
    result.false_positive_rate = round(rate, 4)
    result.passed = rate <= float(upper)
    result.detail = {
        "median_p": round(float(np.median(p_values)), 4),
        "tolerance_upper": round(float(upper), 4),
        "event_rate_preserved": round(float(values.mean()), 4),
    }
    result.note = (
        f"Shuffling the signal in time leaves {rate:.1%} of trials significant, "
        f"against a {upper:.1%} tolerance. "
        + (
            "Timing, not frequency, is what the test responds to."
            if result.passed else
            "The test responds to how often the signal fires rather than to when, "
            "which means it is not measuring predictability."
        )
    )
    return result


def positive_control(
    target: pd.Series,
    controls: pd.DataFrame,
    regimes: pd.Series,
    horizon_bars: int,
    injected_effect: float = 2.0,
    event_rate: float = 0.15,
    seed: int = DEFAULT_SEED + 2,
) -> ControlResult:
    """Insert a known effect and check the pipeline recovers it.

    The signal is drawn at random, then `injected_effect` is added to the target
    wherever it fires. The true answer is known exactly, so both the detection
    and the attenuation can be checked.
    """
    rng = np.random.default_rng(seed)
    signal = pd.Series(
        (rng.random(len(target)) < event_rate).astype(float), index=target.index
    )
    spiked = target + signal * injected_effect

    result = ControlResult(name="injected_effect", kind="positive", trials=1)
    strat_p = _stratified_p(spiked, signal, regimes)
    events = spiked[signal > 0]
    others = spiked[signal <= 0]
    recovered = float(events.mean() - others.mean())

    folds = purged_walk_forward_folds(
        pd.DatetimeIndex(target.index), horizon_bars=horizon_bars, n_folds=3
    )
    residual_excesses: list[float] = []
    residual_ps: list[float] = []
    for fold in folds:
        train = fold.train_mask.reindex(target.index, fill_value=False)
        test = fold.test_mask.reindex(target.index, fill_value=False)
        outcome = residualise(spiked, controls, signal, train, test)
        if outcome.status == "OK" and outcome.excess is not None:
            residual_excesses.append(outcome.excess)
            residual_ps.append(outcome.p_value)

    residual_effect = float(np.mean(residual_excesses)) if residual_excesses else None
    detected_strat = strat_p is not None and strat_p < NOMINAL_ALPHA
    detected_resid = bool(residual_ps) and max(residual_ps) < NOMINAL_ALPHA
    result.passed = detected_strat and detected_resid

    attenuation = (
        round(residual_effect / injected_effect, 3)
        if residual_effect is not None and injected_effect else None
    )
    result.detail = {
        "injected_effect_pct": injected_effect,
        "recovered_raw_pct": round(recovered, 4),
        "recovered_after_residualisation_pct": (
            round(residual_effect, 4) if residual_effect is not None else None
        ),
        "stratified_p": round(strat_p, 6) if strat_p is not None else None,
        "residual_worst_p": round(max(residual_ps), 6) if residual_ps else None,
        "attenuation_factor": attenuation,
        "detected_by_stratification": detected_strat,
        "detected_by_residualisation": detected_resid,
        "folds": len(residual_excesses),
    }
    result.note = (
        f"A {injected_effect:.1f}% effect was inserted. Stratification recovered "
        f"{recovered:.2f}%"
        + (
            f" and residualisation {residual_effect:.2f}% "
            f"({attenuation:.0%} of what was inserted)."
            if residual_effect is not None else " but residualisation could not run."
        )
        + (
            " The pipeline detects an effect of this size, so a null result on "
            "real data is informative at this magnitude."
            if result.passed else
            " The pipeline failed to detect an effect it was handed. Its null "
            "results cannot be read as evidence of absence."
        )
    )
    return result


def run_control_suite(
    target: pd.Series,
    signal: pd.Series,
    controls: pd.DataFrame,
    regimes: pd.Series,
    horizon_bars: int,
    trials: int = N_NEGATIVE_TRIALS,
) -> dict[str, Any]:
    """All controls, with a single pass or fail for the pipeline as a whole."""
    aligned = pd.concat(
        [target.rename("_y"), signal.rename("_s"), regimes.rename("_r"), controls],
        axis=1,
    ).dropna()
    if len(aligned) < 400:
        return {
            "status": "INSUFFICIENT_DATA",
            "rows": len(aligned),
            "note": "controls need at least 400 aligned rows",
        }

    y = aligned["_y"]
    s = aligned["_s"]
    r = aligned["_r"]
    c = aligned[[col for col in controls.columns if col in aligned.columns]]

    results = [
        negative_control_random_signal(y, r, trials=trials),
        negative_control_shuffled_signal(y, s, r, trials=trials),
        positive_control(y, c, r, horizon_bars),
    ]
    negatives = [x for x in results if x.kind == "negative"]
    positives = [x for x in results if x.kind == "positive"]
    all_passed = all(x.passed for x in results)

    return {
        "status": "OK",
        "generated_at": datetime.now(UTC).isoformat(),
        "rows": len(aligned),
        "horizon_bars": horizon_bars,
        "controls": [x.to_dict() for x in results],
        "negatives_passed": all(x.passed for x in negatives),
        "positive_passed": all(x.passed for x in positives),
        "pipeline_trustworthy": all_passed,
        "note": (
            "The pipeline is calibrated on noise and sensitive to a planted "
            "effect. Its negative results carry information."
            if all_passed else
            "At least one control failed. Until it is fixed, results from this "
            "pipeline - positive and negative alike - should not be relied on."
        ),
    }


# --- what the pipeline can actually see -----------------------------------


def detection_floor(
    target: pd.Series,
    controls: pd.DataFrame,
    regimes: pd.Series,
    horizon_bars: int,
    sizes: list[float] | None = None,
    event_rate: float = 0.15,
    seed: int = DEFAULT_SEED + 3,
) -> dict[str, Any]:
    """The smallest planted effect this pipeline certifies, found by search.

    The minimum detectable effect computed in `power.py` is analytic: it
    assumes a two-sample t test on independent observations. This is the same
    quantity measured empirically, by planting effects of known size and seeing
    which ones survive the actual chain of stratification, purged folds and
    worst-fold residualisation that the studies use.

    The two should agree, and where they do the analytic number can be trusted
    for hypotheses that were never simulated. Where they disagree, the
    empirical number governs, because it is the one the studies are subject to.

    This is the number that decides what a null result means. If the floor is
    8% and the meaningful effect is 2%, then "no effect found" says nothing
    about effects between 2% and 8% - the pipeline was never able to see them.
    """
    sizes = sizes or [0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 12.0]
    trials: list[dict[str, Any]] = []
    floor_worst: float | None = None
    floor_mean: float | None = None

    for offset, size in enumerate(sorted(sizes)):
        outcome = positive_control(
            target, controls, regimes, horizon_bars,
            injected_effect=size, event_rate=event_rate, seed=seed + offset,
        )
        detail = outcome.detail
        worst_p = detail.get("residual_worst_p")
        strat_p = detail.get("stratified_p")
        detected_worst = bool(outcome.passed)
        detected_mean = bool(
            strat_p is not None and strat_p < NOMINAL_ALPHA
            and worst_p is not None
        )
        trials.append({
            "injected_pct": size,
            "recovered_pct": detail.get("recovered_raw_pct"),
            "recovered_residual_pct": detail.get("recovered_after_residualisation_pct"),
            "stratified_p": strat_p,
            "residual_worst_p": worst_p,
            "detected": detected_worst,
        })
        if detected_worst and floor_worst is None:
            floor_worst = size
        if detected_mean and floor_mean is None:
            floor_mean = size

    from .power import meaningful_effect, minimum_detectable_effect

    target_effect = meaningful_effect(horizon_bars)
    std_dev = float(target.std())
    n_events = int(len(target) * event_rate)
    analytic = minimum_detectable_effect(
        n_events / horizon_bars, (len(target) - n_events) / horizon_bars, std_dev
    )

    return {
        "horizon_bars": horizon_bars,
        "trials": trials,
        "empirical_floor_pct": floor_worst,
        "empirical_floor_stratified_only_pct": floor_mean,
        "analytic_mde_pct": round(analytic, 3) if analytic else None,
        "meaningful_effect_pct": round(target_effect, 3),
        "floor_above_meaningful": bool(
            floor_worst is not None and floor_worst > target_effect
        ),
        "std_dev_pct": round(std_dev, 3),
        "note": (
            f"The smallest planted effect this pipeline certifies at a "
            f"{horizon_bars}-bar horizon is {floor_worst}%, against a declared "
            f"meaningful effect of {target_effect:.2f}%. "
            + (
                "Every null result at this horizon is therefore silent about "
                "effects between those two numbers: they were planted and missed. "
                "Null results here are not evidence of absence below the floor."
                if floor_worst is not None and floor_worst > target_effect else
                "The pipeline can see effects smaller than the meaningful "
                "threshold, so null results at this horizon are informative."
            )
        ),
    }

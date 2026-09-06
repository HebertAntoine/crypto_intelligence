"""Statistical power: telling FAILED apart from "we could never have seen it".

A p-value above 0.05 means one of two very different things. Either the effect
is absent on a sample large enough to have revealed it, or the test had no
chance of detecting anything worth detecting. Reporting both as FAILED throws
away the distinction that matters most when a study returns nothing.

So every test now carries its minimum detectable effect. If the MDE exceeds the
effect that would have been economically meaningful, a null result is
INSUFFICIENT_DATA, not FAILED.

All power calculations use the EFFECTIVE sample. Using the raw count would
report a reassuring MDE for a test that cannot actually detect anything, which
is worse than reporting no MDE at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import numpy as np
from scipy import stats

from ..logging_setup import get_logger

log = get_logger("research.power")

# The effect that would matter economically, net of the 0.20% round trip.
# Declared in advance, per horizon, so no threshold can be chosen after seeing
# a result.
MEANINGFUL_EFFECT_PCT: dict[int, float] = {
    1: 0.4,
    3: 0.7,
    7: 1.0,
    14: 1.5,
    30: 2.0,
}

DEFAULT_ALPHA = 0.05
DEFAULT_POWER = 0.80
MIN_EFFECTIVE_N = 30


def meaningful_effect(horizon_bars: int, freq_days: float = 1.0) -> float:
    """Interpolate the declared threshold for an arbitrary horizon."""
    horizon_days = horizon_bars * freq_days
    known = sorted(MEANINGFUL_EFFECT_PCT)
    if horizon_days <= known[0]:
        return MEANINGFUL_EFFECT_PCT[known[0]]
    if horizon_days >= known[-1]:
        # Beyond the table, scale with the square root of time - the natural
        # scale for a random walk's dispersion.
        longest = known[-1]
        return MEANINGFUL_EFFECT_PCT[longest] * float(np.sqrt(horizon_days / longest))
    return float(np.interp(horizon_days, known, [MEANINGFUL_EFFECT_PCT[k] for k in known]))


class PowerVerdict(StrEnum):
    ADEQUATELY_POWERED = "ADEQUATELY_POWERED"
    UNDERPOWERED = "UNDERPOWERED"
    UNKNOWN = "UNKNOWN"


@dataclass(slots=True)
class PowerAssessment:
    effective_n_event: float = 0.0
    effective_n_baseline: float = 0.0
    std_dev: float | None = None
    mde: float | None = None
    meaningful_effect_pct: float | None = None
    power_at_meaningful: float | None = None
    verdict: PowerVerdict = PowerVerdict.UNKNOWN
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "effective_n_event": self.effective_n_event,
            "effective_n_baseline": self.effective_n_baseline,
            "std_dev": self.std_dev,
            "minimum_detectable_effect_pct": self.mde,
            "meaningful_effect_pct": self.meaningful_effect_pct,
            "power_at_meaningful_effect": self.power_at_meaningful,
            "verdict": self.verdict.value,
            "note": self.note,
        }


def minimum_detectable_effect(
    n_event: float, n_baseline: float, std_dev: float,
    alpha: float = DEFAULT_ALPHA, power: float = DEFAULT_POWER,
) -> float | None:
    """Smallest difference in means this sample could detect.

        MDE = (z_{1-a/2} + z_{power}) * sd * sqrt(1/n_e + 1/n_b)

    Both n are EFFECTIVE counts. Passing raw counts here produces a number that
    flatters a test which cannot see anything.
    """
    if n_event <= 0 or n_baseline <= 0 or std_dev <= 0:
        return None
    z_alpha = float(stats.norm.ppf(1 - alpha / 2))
    z_power = float(stats.norm.ppf(power))
    return float((z_alpha + z_power) * std_dev * np.sqrt(1 / n_event + 1 / n_baseline))


def statistical_power(
    effect: float, n_event: float, n_baseline: float, std_dev: float,
    alpha: float = DEFAULT_ALPHA,
) -> float | None:
    """Probability of detecting `effect` at this sample size."""
    if n_event <= 0 or n_baseline <= 0 or std_dev <= 0:
        return None
    standard_error = std_dev * np.sqrt(1 / n_event + 1 / n_baseline)
    if standard_error <= 0:
        return None
    z_alpha = float(stats.norm.ppf(1 - alpha / 2))
    ncp = abs(effect) / standard_error
    return float(stats.norm.cdf(ncp - z_alpha) + stats.norm.cdf(-ncp - z_alpha))


def assess_power(
    effective_n_event: float,
    effective_n_baseline: float,
    std_dev: float,
    horizon_bars: int,
    freq_days: float = 1.0,
) -> PowerAssessment:
    """Was this test capable of seeing an effect worth seeing?"""
    target = meaningful_effect(horizon_bars, freq_days)
    assessment = PowerAssessment(
        effective_n_event=round(effective_n_event, 1),
        effective_n_baseline=round(effective_n_baseline, 1),
        std_dev=round(std_dev, 4) if std_dev else None,
        meaningful_effect_pct=round(target, 3),
    )

    mde = minimum_detectable_effect(effective_n_event, effective_n_baseline, std_dev)
    if mde is None:
        assessment.note = "cannot compute: sample or dispersion is zero"
        return assessment

    assessment.mde = round(mde, 4)
    assessment.power_at_meaningful = round(
        statistical_power(target, effective_n_event, effective_n_baseline, std_dev) or 0.0, 3
    )
    assessment.verdict = (
        PowerVerdict.ADEQUATELY_POWERED if mde <= target else PowerVerdict.UNDERPOWERED
    )
    assessment.note = (
        f"With {effective_n_event:.0f} effective event observations the smallest "
        f"detectable difference is {mde:.2f}%, against a meaningful effect of "
        f"{target:.2f}%. "
        + (
            "A null result here is evidence of absence."
            if assessment.verdict is PowerVerdict.ADEQUATELY_POWERED
            else "A null result here is uninformative: the test could not have "
                 "seen a meaningful effect."
        )
    )
    return assessment


class Verdict(StrEnum):
    SUPPORTED = "SUPPORTED"
    INCONCLUSIVE = "INCONCLUSIVE"
    FAILED = "FAILED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


@dataclass(slots=True)
class VerdictInputs:
    """Everything the verdict rule needs, gathered explicitly."""

    survives_fdr: bool = False
    effective_n: float = 0.0
    effect_pct: float | None = None
    friction_pct: float = 0.20
    stability_verdict: str | None = None
    oos_confirms: bool | None = None
    stratified_excess: float | None = None
    residual_excess: float | None = None
    residual_p_value: float | None = None
    power: PowerAssessment | None = None
    single_asset_driven: bool = False
    point_in_time_established: bool = True


def decide_verdict(inputs: VerdictInputs, horizon_bars: int, freq_days: float = 1.0) -> dict[str, Any]:
    """Apply the LOT 6A rules, and say exactly which one bound.

    The addition over LOT 5: a result must survive BOTH stratification and
    residualisation. Passing one and failing the other is INCONCLUSIVE - the
    disagreement is itself the finding, and hiding it behind whichever method
    was kinder would be method shopping.
    """
    reasons: list[str] = []
    target = meaningful_effect(horizon_bars, freq_days)

    if not inputs.point_in_time_established:
        return {
            "verdict": Verdict.INSUFFICIENT_DATA.value,
            "binding_reason": "point-in-time status of an input is not established",
            "reasons": ["a control or feature could not be shown to be knowable at T"],
        }

    if inputs.effective_n < MIN_EFFECTIVE_N:
        return {
            "verdict": Verdict.INSUFFICIENT_DATA.value,
            "binding_reason": f"effective_n {inputs.effective_n:.1f} < {MIN_EFFECTIVE_N}",
            "reasons": [
                "not convertible by adding assets or horizons: the sample is "
                "genuinely this small"
            ],
        }

    underpowered = (
        inputs.power is not None and inputs.power.verdict is PowerVerdict.UNDERPOWERED
    )

    # A null result: is it absence, or blindness?
    if not inputs.survives_fdr:
        if underpowered:
            return {
                "verdict": Verdict.INSUFFICIENT_DATA.value,
                "binding_reason": "null result on an underpowered test",
                "reasons": [inputs.power.note if inputs.power else ""],
            }
        return {
            "verdict": Verdict.FAILED.value,
            "binding_reason": "null result on an adequately powered test",
            "reasons": [
                f"the test could have detected {target:.2f}% and found nothing"
            ],
        }

    # It survived FDR. Now the practical filters.
    if inputs.effect_pct is not None and abs(inputs.effect_pct) < target:
        reasons.append(
            f"effect {inputs.effect_pct:+.2f}% below the {target:.2f}% meaningful floor"
        )
    if inputs.effect_pct is not None and abs(inputs.effect_pct) <= inputs.friction_pct:
        reasons.append(f"effect does not clear {inputs.friction_pct:.2f}% friction")
    if inputs.stability_verdict not in (None, "STABLE"):
        reasons.append(f"stability {inputs.stability_verdict}")
    if inputs.oos_confirms is False:
        reasons.append("not confirmed in purged out-of-sample")
    if inputs.single_asset_driven:
        reasons.append("pooled effect carried by a single asset")

    # The two-method rule.
    both_available = (
        inputs.stratified_excess is not None and inputs.residual_excess is not None
    )
    if both_available:
        agree = np.sign(inputs.stratified_excess) == np.sign(inputs.residual_excess)
        residual_significant = (
            inputs.residual_p_value is not None and inputs.residual_p_value < 0.05
        )
        if not agree:
            reasons.append(
                f"methods disagree in sign: stratified {inputs.stratified_excess:+.2f}%, "
                f"residualised {inputs.residual_excess:+.2f}%"
            )
        elif not residual_significant:
            reasons.append(
                f"survives stratification but not residualisation "
                f"(p={inputs.residual_p_value:.3f})"
            )
    else:
        reasons.append("only one control method available; both are required")

    if reasons:
        return {
            "verdict": Verdict.INCONCLUSIVE.value,
            "binding_reason": reasons[0],
            "reasons": reasons,
        }

    return {
        "verdict": Verdict.SUPPORTED.value,
        "binding_reason": "survives every filter under both control methods",
        "reasons": [],
    }

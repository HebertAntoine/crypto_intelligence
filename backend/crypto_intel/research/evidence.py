"""How far up the ladder a claim has actually climbed.

Every study in this system produces a verdict, and the verdicts are not
comparable: "survives FDR" and "survives residualisation" and "held up in a
different cycle" are different achievements, and a claim can have one without
the others. The ladder makes the ordering explicit, so a result can be
described by the highest rung it reached rather than by whichever test it
happened to pass.

  0  NOT_TESTED          declared, never run
  1  OBSERVED            a difference exists in sample against some comparison
  2  BASELINE_RELATIVE   the comparison is a conditioned baseline, not zero,
                         and the difference survives it
  3  STRATIFIED          survives regime stratification: not a repackaging of
                         "the market went up"
  4  CONTROLLED          survives residualisation against price, momentum and
                         volatility on purged folds
  5  ROBUST              keeps sign and magnitude when any single year, asset
                         or market cycle is removed
  6  REPLICATED          reproduces on data not used to find it - another
                         asset, a later period, or a pooled panel
  7  LIVE_CONFIRMED      confirmed prospectively, on data that did not exist
                         when the claim was made

Rungs are cumulative and strictly ordered: a claim that survives
residualisation but fails stratification stops at 2. Skipping is not allowed,
because the tests are not independent - passing a harder one while failing an
easier one nearly always means the harder test was misapplied.

No claim in this system has reached rung 7, and reaching it takes calendar
time that cannot be shortened.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import numpy as np

from ..logging_setup import get_logger

log = get_logger("research.evidence")

LADDER: list[dict[str, Any]] = [
    {"level": 0, "name": "NOT_TESTED",
     "meaning": "declared but never run"},
    {"level": 1, "name": "OBSERVED",
     "meaning": "a difference exists in sample"},
    {"level": 2, "name": "BASELINE_RELATIVE",
     "meaning": "survives comparison against a conditioned baseline"},
    {"level": 3, "name": "STRATIFIED",
     "meaning": "survives regime stratification"},
    {"level": 4, "name": "CONTROLLED",
     "meaning": "survives residualisation on purged folds"},
    {"level": 5, "name": "ROBUST",
     "meaning": "survives leave-one-year, leave-one-asset and cycle deletion"},
    {"level": 6, "name": "REPLICATED",
     "meaning": "reproduces on data not used to find it"},
    {"level": 7, "name": "LIVE_CONFIRMED",
     "meaning": "confirmed prospectively on data that did not exist at claim time"},
]

LEVEL_NAMES = {entry["level"]: entry["name"] for entry in LADDER}

# Below this, a claim is not actionable regardless of its p-value.
ACTIONABLE_LEVEL = 6


@dataclass(slots=True)
class EvidenceAssessment:
    claim: str = ""
    level: int = 0
    level_name: str = "NOT_TESTED"
    passed: list[str] = field(default_factory=list)
    blocked_at: str | None = None
    blocked_reason: str = ""
    underpowered: bool = False
    actionable: bool = False
    details: dict[str, Any] = field(default_factory=dict)
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim": self.claim, "level": self.level, "level_name": self.level_name,
            "passed": self.passed, "blocked_at": self.blocked_at,
            "blocked_reason": self.blocked_reason, "underpowered": self.underpowered,
            "actionable": self.actionable, "details": self.details, "note": self.note,
        }


def assess_evidence(
    claim: str,
    observed: bool = False,
    baseline_relative: bool = False,
    stratified: bool = False,
    controlled: bool = False,
    robust: bool = False,
    replicated: bool = False,
    live_confirmed: bool = False,
    underpowered: bool = True,
    details: dict[str, Any] | None = None,
) -> EvidenceAssessment:
    """Walk the ladder and stop at the first rung that fails."""
    rungs = [
        ("OBSERVED", observed),
        ("BASELINE_RELATIVE", baseline_relative),
        ("STRATIFIED", stratified),
        ("CONTROLLED", controlled),
        ("ROBUST", robust),
        ("REPLICATED", replicated),
        ("LIVE_CONFIRMED", live_confirmed),
    ]
    assessment = EvidenceAssessment(
        claim=claim, underpowered=underpowered, details=details or {}
    )
    for offset, (name, passed) in enumerate(rungs, start=1):
        if not passed:
            assessment.blocked_at = name
            assessment.blocked_reason = f"did not reach {name}"
            break
        assessment.level = offset
        assessment.passed.append(name)

    assessment.level_name = LEVEL_NAMES[assessment.level]
    assessment.actionable = assessment.level >= ACTIONABLE_LEVEL and not underpowered

    tail = ""
    if underpowered and assessment.level >= 3:
        tail = (
            " The rungs it passed were passed with a sample too small to detect a "
            "meaningful effect, so passing them is weaker evidence than it looks."
        )
    assessment.note = (
        f"Reached level {assessment.level} ({assessment.level_name})"
        + (
            f", blocked at {assessment.blocked_at}."
            if assessment.blocked_at else " - the top of the ladder."
        )
        + tail
    )
    return assessment


# --- the funnel -----------------------------------------------------------


def fdr_funnel(stages: list[dict[str, Any]]) -> dict[str, Any]:
    """Attrition from every test run to whatever is left standing.

    The funnel exists to make the denominator visible. A report that mentions
    three surviving results without saying how many were tried is not a report,
    it is a selection.
    """
    if not stages:
        return {"stages": [], "note": "no stages recorded"}

    start = stages[0].get("count", 0)
    rows: list[dict[str, Any]] = []
    previous = start
    for stage in stages:
        count = stage.get("count", 0)
        rows.append({
            "stage": stage.get("stage", "?"),
            "count": count,
            "lost_here": max(previous - count, 0),
            "share_of_start_pct": round(count / start * 100, 1) if start else 0.0,
            "detail": stage.get("detail", ""),
        })
        previous = count

    survivors = rows[-1]["count"] if rows else 0
    expected_false = round(start * 0.05, 1)
    return {
        "stages": rows,
        "tests_started": start,
        "survivors": survivors,
        "attrition_pct": round((1 - survivors / start) * 100, 1) if start else 0.0,
        "expected_false_positives_at_alpha_05": expected_false,
        "survivors_exceed_chance": survivors > expected_false,
        "note": (
            f"{start} tests entered the funnel and {survivors} survived. "
            + (
                f"Pure chance at alpha = 0.05 would have produced about "
                f"{expected_false} apparent findings, so {survivors} survivors "
                "is not more than chance would give."
                if survivors <= expected_false else
                f"Chance alone would give about {expected_false}; {survivors} is "
                "more than that, though the margin is what matters, not the fact."
            )
        ),
    }


# --- replication ----------------------------------------------------------


def replication_score(
    original_effect: float,
    replications: dict[str, float | None],
    magnitude_tolerance: float = 0.5,
) -> dict[str, Any]:
    """How often an independent re-run agrees with the original.

    Agreement means the same sign and at least `magnitude_tolerance` of the
    original size. Sign alone is too easy: a signal reported at +8% that
    replicates at +0.2% has not replicated in any sense that matters.
    """
    usable = {k: v for k, v in replications.items() if v is not None}
    if not usable or original_effect == 0:
        return {
            "status": "INSUFFICIENT_DATA",
            "score": None,
            "attempts": len(replications),
            "usable": len(usable),
            "note": "no usable replication attempts",
        }

    sign = int(np.sign(original_effect))
    agreements = {
        name: bool(
            int(np.sign(value)) == sign
            and abs(value) >= abs(original_effect) * magnitude_tolerance
        )
        for name, value in usable.items()
    }
    sign_only = {
        name: bool(int(np.sign(value)) == sign) for name, value in usable.items()
    }
    score = sum(agreements.values()) / len(agreements)
    ratios = {
        name: round(value / original_effect, 3) for name, value in usable.items()
    }
    median_ratio = float(np.median(list(ratios.values())))

    return {
        "status": "OK",
        "score": round(score, 3),
        "original_effect": round(original_effect, 4),
        "replications": {k: round(v, 4) for k, v in usable.items()},
        "agreement": agreements,
        "sign_agreement": sign_only,
        "sign_agreement_rate": round(sum(sign_only.values()) / len(sign_only), 3),
        "effect_ratios": ratios,
        "median_shrinkage": round(median_ratio, 3),
        "attempts": len(replications),
        "verdict": (
            "REPLICATED" if score >= 0.8
            else "PARTIALLY_REPLICATED" if score >= 0.5
            else "FAILED_TO_REPLICATE"
        ),
        "note": (
            f"{sum(agreements.values())} of {len(agreements)} replications keep the "
            f"sign and at least {magnitude_tolerance:.0%} of the original effect. "
            f"The median replication is {median_ratio:.2f} times the original"
            + (
                "; shrinkage of this size is the normal signature of a first "
                "estimate inflated by selection."
                if median_ratio < 0.7 else "."
            )
        ),
    }


# --- shortlist ------------------------------------------------------------


def build_shortlist(
    candidates: list[dict[str, Any]], minimum: int = 5, maximum: int = 10
) -> dict[str, Any]:
    """Rank surviving candidates by evidence level, then by tractability.

    The shortlist is explicitly not a list of things that work. It is a list of
    what is worth continuing to measure, ordered by how close each is to being
    decidable. Entries can and mostly do sit at low evidence levels.
    """
    ranked = sorted(
        candidates,
        key=lambda c: (
            -c.get("evidence_level", 0),
            {"ALREADY": 0, "WITHIN_2_YEARS": 1, "WITHIN_10_YEARS": 2,
             "NOT_IN_A_USEFUL_TIMEFRAME": 3, "UNKNOWN": 4}.get(
                c.get("decidable_before", "UNKNOWN"), 4
            ),
            -abs(c.get("effect_pct") or 0.0),
        ),
    )
    selected = ranked[:maximum]
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "n_candidates_considered": len(candidates),
        "n_selected": len(selected),
        "meets_minimum": len(selected) >= minimum,
        "shortlist": selected,
        "highest_level": max((c.get("evidence_level", 0) for c in selected), default=0),
        "note": (
            "Ordered by evidence level, then by how soon each could be decided. "
            "Nothing here is a recommendation to act; entries at level 4 or below "
            "are open questions, not findings."
            + (
                ""
                if len(selected) >= minimum else
                f" Only {len(selected)} candidates cleared the entry bar, below the "
                f"target of {minimum}. Padding the list with weaker candidates "
                "would make it longer without making it more informative."
            )
        ),
    }

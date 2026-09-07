"""Does the result survive removing one asset, one year, or one market cycle?

A signal measured over 2021-2026 has lived through one mania, one collapse, one
long recovery and one more advance. If its entire effect comes from the 2022
bear market, it is not a signal about crypto - it is a description of 2022, and
it will fail the moment conditions change.

Three deletions, each answering a different question:

  leave one asset out   is this a market-wide relationship or one asset's
                        idiosyncrasy wearing a pooled label?
  leave one year out    does any single year carry the result?
  leave one cycle out   does the effect exist in more than one regime of the
                        four-year cycle?

The bar is deliberately blunt: the effect must keep its sign in every fold, and
no single deletion may cut its magnitude by more than half. A result that
depends on keeping one particular year is reported as fragile even when its
full-sample p-value is small.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from ..logging_setup import get_logger

log = get_logger("research.cycles")

# Cycle boundaries are set from Bitcoin's halving schedule and its major
# drawdowns, not from the performance of any signal under test. Fixing them in
# advance prevents the boundaries themselves from becoming a tuned parameter.
MARKET_CYCLES: list[dict[str, str]] = [
    {"name": "2021_mania", "start": "2020-10-01", "end": "2021-11-10",
     "character": "post-halving advance into the November 2021 top"},
    {"name": "2022_bear", "start": "2021-11-11", "end": "2022-12-31",
     "character": "drawdown, deleveraging, LUNA and FTX failures"},
    {"name": "2023_recovery", "start": "2023-01-01", "end": "2024-03-31",
     "character": "recovery and the spot ETF approval"},
    {"name": "2024_2026_advance", "start": "2024-04-01", "end": "2030-01-01",
     "character": "post-halving period, institutional participation"},
]

SIGN_FLIP = "SIGN_FLIP"
FRAGILE = "FRAGILE"
ROBUST = "ROBUST"
INSUFFICIENT = "INSUFFICIENT_DATA"

# A fold may not more than halve the effect before the result is called fragile.
MAGNITUDE_TOLERANCE = 0.5


def simple_excess(frame: pd.DataFrame) -> float | None:
    """Difference in means between signalled and unsignalled rows."""
    events = frame.loc[frame["signal"] > 0, "y"].dropna()
    others = frame.loc[frame["signal"] <= 0, "y"].dropna()
    if len(events) < 10 or len(others) < 20:
        return None
    return float(events.mean() - others.mean())


@dataclass(slots=True)
class RobustnessResult:
    kind: str = ""
    full_sample_effect: float | None = None
    folds: dict[str, Any] = field(default_factory=dict)
    verdict: str = INSUFFICIENT
    driven_by: str | None = None
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind, "full_sample_effect": self.full_sample_effect,
            "folds": self.folds, "verdict": self.verdict,
            "driven_by": self.driven_by, "note": self.note,
        }


def _judge(
    kind: str,
    full: float | None,
    fold_effects: dict[str, float | None],
    label: str,
) -> RobustnessResult:
    """Shared verdict logic: sign stability first, then magnitude."""
    result = RobustnessResult(kind=kind, full_sample_effect=(
        round(full, 4) if full is not None else None
    ))
    usable = {k: v for k, v in fold_effects.items() if v is not None}
    result.folds = {
        k: (round(v, 4) if v is not None else None) for k, v in fold_effects.items()
    }

    if full is None or len(usable) < 2:
        result.verdict = INSUFFICIENT
        result.note = (
            f"{len(usable)} of {len(fold_effects)} {label} folds produced an "
            "estimate; robustness cannot be judged"
        )
        return result

    signs = {int(np.sign(v)) for v in usable.values() if v != 0}
    full_sign = int(np.sign(full))
    flipped = [k for k, v in usable.items() if v != 0 and int(np.sign(v)) != full_sign]
    if flipped or len(signs) > 1:
        result.verdict = SIGN_FLIP
        result.driven_by = flipped[0] if flipped else None
        result.note = (
            f"The effect changes sign when {', '.join(flipped) or 'a fold'} is "
            f"removed. It is not a stable relationship across {label}."
        )
        return result

    shrunk = [
        k for k, v in usable.items()
        if abs(full) > 0 and abs(v) < abs(full) * MAGNITUDE_TOLERANCE
    ]
    if shrunk:
        result.verdict = FRAGILE
        result.driven_by = shrunk[0]
        result.note = (
            f"Removing {shrunk[0]} cuts the effect from {full:.2f} to "
            f"{usable[shrunk[0]]:.2f}, more than half. The full-sample result is "
            f"carried by that {label[:-1] if label.endswith('s') else label}."
        )
        return result

    spread = max(abs(v) for v in usable.values()) - min(abs(v) for v in usable.values())
    result.verdict = ROBUST
    result.note = (
        f"Every one of {len(usable)} {label} folds keeps the sign and at least "
        f"half the magnitude (spread {spread:.2f}). No single deletion carries "
        "the result."
    )
    return result


def leave_one_asset_out(
    panel: pd.DataFrame,
    estimator: Callable[[pd.DataFrame], float | None] = simple_excess,
) -> RobustnessResult:
    """Re-estimate with each asset removed in turn."""
    if panel.empty or "asset" not in panel.columns:
        return RobustnessResult(kind="leave_one_asset_out", note="no panel")
    assets = sorted(panel["asset"].unique())
    if len(assets) < 2:
        return RobustnessResult(
            kind="leave_one_asset_out",
            note=f"only {len(assets)} asset; the test needs at least two",
        )
    full = estimator(panel)
    folds = {
        f"without_{asset}": estimator(panel[panel["asset"] != asset])
        for asset in assets
    }
    return _judge("leave_one_asset_out", full, folds, "asset")


def leave_one_year_out(
    frame: pd.DataFrame,
    estimator: Callable[[pd.DataFrame], float | None] = simple_excess,
    min_rows: int = 60,
) -> RobustnessResult:
    """Re-estimate with each calendar year removed in turn."""
    if frame.empty:
        return RobustnessResult(kind="leave_one_year_out", note="no data")
    years = pd.DatetimeIndex(frame.index).year
    unique_years = sorted({int(y) for y in years})
    eligible = [y for y in unique_years if int((years == y).sum()) >= min_rows]
    if len(eligible) < 3:
        return RobustnessResult(
            kind="leave_one_year_out",
            note=f"only {len(eligible)} years with {min_rows}+ rows",
        )
    full = estimator(frame)
    folds = {f"without_{year}": estimator(frame[years != year]) for year in eligible}
    result = _judge("leave_one_year_out", full, folds, "years")
    result.folds["years_available"] = eligible
    return result


def by_cycle(
    frame: pd.DataFrame,
    estimator: Callable[[pd.DataFrame], float | None] = simple_excess,
) -> dict[str, Any]:
    """Effect estimated within each market cycle separately.

    This is not a deletion test - it reports where the effect lives. A signal
    present in the mania and absent in the bear is a different object from one
    present in both, even when the pooled numbers match.
    """
    index = pd.DatetimeIndex(frame.index)
    out: dict[str, Any] = {"cycles": {}}
    present: list[str] = []
    for cycle in MARKET_CYCLES:
        start = pd.Timestamp(cycle["start"], tz=index.tz)
        end = pd.Timestamp(cycle["end"], tz=index.tz)
        window = frame[(index >= start) & (index <= end)]
        n_events = int((window["signal"] > 0).sum()) if "signal" in window else 0
        effect = estimator(window) if len(window) else None
        out["cycles"][cycle["name"]] = {
            "character": cycle["character"],
            "rows": len(window),
            "events": n_events,
            "effect": round(effect, 4) if effect is not None else None,
            "status": "OK" if effect is not None else "INSUFFICIENT_DATA",
        }
        if effect is not None:
            present.append(cycle["name"])

    measured = {
        name: payload["effect"] for name, payload in out["cycles"].items()
        if payload["effect"] is not None
    }
    out["cycles_measured"] = len(measured)
    out["cycles_total"] = len(MARKET_CYCLES)
    if len(measured) >= 2:
        signs = {int(np.sign(v)) for v in measured.values() if v != 0}
        out["sign_consistent"] = len(signs) <= 1
        out["strongest_cycle"] = max(measured, key=lambda k: abs(measured[k]))
        out["weakest_cycle"] = min(measured, key=lambda k: abs(measured[k]))
        out["note"] = (
            f"Measured in {len(measured)} of {len(MARKET_CYCLES)} cycles. "
            + (
                "The sign holds across every cycle in which it could be measured."
                if out["sign_consistent"]
                else "The sign is not the same in every cycle; the relationship is "
                     "conditional on the market phase."
            )
        )
    else:
        out["sign_consistent"] = None
        out["note"] = (
            f"Only {len(measured)} cycle produced an estimate. A signal that can "
            "be measured in one cycle has not been shown to generalise beyond it."
        )
    out["cycles_present"] = present
    return out


def full_robustness(
    frame: pd.DataFrame,
    estimator: Callable[[pd.DataFrame], float | None] = simple_excess,
    is_panel: bool = False,
) -> dict[str, Any]:
    """All three views, plus a single summary verdict."""
    year = leave_one_year_out(frame, estimator)
    cycle = by_cycle(frame, estimator)
    asset = (
        leave_one_asset_out(frame, estimator) if is_panel
        else RobustnessResult(kind="leave_one_asset_out", note="single asset study")
    )

    verdicts = [year.verdict]
    if is_panel:
        verdicts.append(asset.verdict)

    if SIGN_FLIP in verdicts:
        overall = SIGN_FLIP
    elif FRAGILE in verdicts:
        overall = FRAGILE
    elif all(v == ROBUST for v in verdicts) and cycle.get("sign_consistent") is True:
        overall = ROBUST
    elif all(v == ROBUST for v in verdicts):
        overall = FRAGILE
    else:
        overall = INSUFFICIENT

    return {
        "leave_one_year_out": year.to_dict(),
        "leave_one_asset_out": asset.to_dict(),
        "by_cycle": cycle,
        "overall_verdict": overall,
        "note": (
            "A result is robust only if it keeps its sign and most of its "
            "magnitude when any single year, asset or cycle is removed. "
            "Surviving the full sample is not enough."
        ),
    }

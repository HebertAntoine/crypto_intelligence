"""Remove a whole family of features and see whether anything is lost.

Individual feature importance is a poor guide when features are correlated:
drop one of two near-identical columns and the other absorbs its role, so both
look expendable while the pair is not. Ablating an entire family answers the
question that actually matters - is there anything in derivatives data, or in
implied volatility, or in structure, that price alone does not already contain?

Everything is scored out of sample on purged folds. The comparison is against
the price-and-volatility block, which is the incumbent every new family has to
beat to justify the cost of collecting it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from ..logging_setup import get_logger
from .inference import purged_walk_forward_folds

log = get_logger("research.ablation")

# Feature families, declared by what they are collected from rather than by
# what they are believed to predict.
FAMILIES: dict[str, list[str]] = {
    "price": ["return_1", "return_5", "return_20", "return_60", "dist_ema200_pct"],
    "volatility": ["realised_vol_20", "realised_vol_60"],
    "trend": ["adx_14"],
    "implied_volatility": [
        "dvol", "dvol_percentile", "dvol_change_30", "variance_premium",
        "variance_premium_percentile",
    ],
    "derivatives": [
        "funding_rate", "funding_percentile", "oi_change_7", "oi_change_30",
        "basis_annualised",
    ],
}


def _oos_r2(
    frame: pd.DataFrame, columns: list[str], horizon_bars: int,
    n_folds: int = 4, alpha: float = 10.0,
) -> dict[str, Any]:
    """Mean out-of-sample R squared for a column subset."""
    usable = [c for c in columns if c in frame.columns]
    if not usable:
        return {"status": "NO_COLUMNS", "r2": None}
    work = frame[["_y", *usable]].dropna()
    if len(work) < 250:
        return {"status": "INSUFFICIENT_DATA", "rows": len(work), "r2": None}

    y = work["_y"].to_numpy(dtype=float)
    x = work[usable].to_numpy(dtype=float)
    folds = purged_walk_forward_folds(
        pd.DatetimeIndex(work.index), horizon_bars=horizon_bars, n_folds=n_folds
    )
    scores: list[float] = []
    for fold in folds:
        train = fold.train_mask.reindex(work.index, fill_value=False).to_numpy()
        test = fold.test_mask.reindex(work.index, fill_value=False).to_numpy()
        if train.sum() < 100 or test.sum() < 30:
            continue
        # Standardise inside the pipeline so the scaler is fitted on training
        # rows only. Ridge penalises coefficients, not effects, so on raw
        # columns spanning funding rates near 0.0001 and DVOL near 100 the
        # penalty falls almost entirely on the small-scale features - which
        # makes the comparison between families a comparison of their units.
        model = make_pipeline(StandardScaler(), Ridge(alpha=alpha))
        model.fit(x[train], y[train])
        prediction = model.predict(x[test])
        denominator = float(((y[test] - y[train].mean()) ** 2).sum())
        if denominator <= 0:
            continue
        scores.append(1 - float(((y[test] - prediction) ** 2).sum()) / denominator)

    if len(scores) < 2:
        return {"status": "INSUFFICIENT_FOLDS", "folds": len(scores), "r2": None}
    return {
        "status": "OK",
        "r2": round(float(np.mean(scores)), 5),
        "per_fold": [round(s, 5) for s in scores],
        "folds": len(scores),
        "n_features": len(usable),
        "rows": len(work),
    }


@dataclass(slots=True)
class AblationResult:
    horizon_days: int = 0
    full_model: dict[str, Any] = field(default_factory=dict)
    families_present: list[str] = field(default_factory=list)
    ablations: dict[str, Any] = field(default_factory=dict)
    ranking: list[dict[str, Any]] = field(default_factory=list)
    verdict: str = "UNKNOWN"
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "horizon_days": self.horizon_days, "full_model": self.full_model,
            "families_present": self.families_present, "ablations": self.ablations,
            "ranking": self.ranking, "verdict": self.verdict, "note": self.note,
        }


def family_ablation(
    frame: pd.DataFrame,
    target: pd.Series,
    horizon_bars: int,
    families: dict[str, list[str]] | None = None,
) -> AblationResult:
    """Fit with everything, then with each family removed in turn.

    Two numbers per family: the loss from removing it (does anything else
    already carry its information?) and its performance alone (does it carry
    anything at all?). A family can be worthless on both counts, valuable on
    both, or - most commonly - informative alone and redundant in company.
    """
    families = families or FAMILIES
    work = frame.copy()
    work["_y"] = target.reindex(work.index)

    present = {
        name: [c for c in columns if c in work.columns]
        for name, columns in families.items()
    }
    present = {name: columns for name, columns in present.items() if columns}
    result = AblationResult(horizon_days=horizon_bars, families_present=sorted(present))
    if len(present) < 2:
        result.verdict = "INSUFFICIENT_FAMILIES"
        result.note = f"only {len(present)} family present in the frame"
        return result

    all_columns = [c for columns in present.values() for c in columns]
    result.full_model = _oos_r2(work, all_columns, horizon_bars)
    full_r2 = result.full_model.get("r2")
    if full_r2 is None:
        result.verdict = result.full_model.get("status", "FAILED")
        result.note = "the full model could not be scored"
        return result

    for name, columns in present.items():
        without = [c for c in all_columns if c not in columns]
        removed = _oos_r2(work, without, horizon_bars) if without else {"r2": None}
        alone = _oos_r2(work, columns, horizon_bars)
        loss = (
            round(full_r2 - removed["r2"], 5) if removed.get("r2") is not None else None
        )
        result.ablations[name] = {
            "features": columns,
            "r2_without_family": removed.get("r2"),
            "r2_family_alone": alone.get("r2"),
            "loss_from_removal": loss,
            "carries_unique_information": bool(loss is not None and loss > 0),
            "informative_alone": bool(
                alone.get("r2") is not None and alone["r2"] > 0
            ),
            "status_alone": alone.get("status"),
        }

    scored = [
        {"family": name, "loss": payload["loss_from_removal"],
         "alone": payload["r2_family_alone"]}
        for name, payload in result.ablations.items()
        if payload["loss_from_removal"] is not None
    ]
    result.ranking = sorted(scored, key=lambda r: r["loss"], reverse=True)

    contributors = [r["family"] for r in result.ranking if r["loss"] > 0]
    if full_r2 <= 0:
        result.verdict = "NO_PREDICTABILITY"
        result.note = (
            f"The full model's out-of-sample R2 is {full_r2:+.5f}. It does not beat "
            "predicting the training mean, so no family can be credited with "
            "contributing to a model that predicts nothing. Ablation losses below "
            "are differences between two failing models and must not be read as "
            "evidence for any family."
        )
    elif not contributors:
        result.verdict = "NO_FAMILY_CONTRIBUTES"
        result.note = (
            "Every family can be removed without out-of-sample loss. The features "
            "are mutually substitutable and none carries unique information."
        )
    else:
        result.verdict = "CONTRIBUTORS_IDENTIFIED"
        result.note = (
            f"Full-model out-of-sample R2 is {full_r2:.5f}. "
            f"{len(contributors)} of {len(present)} families cause a loss when "
            f"removed: {', '.join(contributors)}. Losses are small in absolute "
            "terms because daily returns are mostly unpredictable; the ordering "
            "is what carries the information."
        )
    return result

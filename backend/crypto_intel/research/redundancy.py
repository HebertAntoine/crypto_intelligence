"""How much of what a feature says was already being said by something else.

The system computes several dozen features. Most of them are transformations of
the same two underlying series - price and volume - and the correlation matrix
shows it. A feature that is 0.95 correlated with one already in use adds
almost nothing, but it does add a test, and tests are the currency multiple-
testing correction is paid in.

Two measurements:

  marginal information   the variance in the target a feature explains that
                         the incumbent set does not. Computed out of sample on
                         purged folds, because in-sample R squared always rises
                         when a column is added.
  redundancy             how much of the feature itself is predictable from the
                         others. A feature with 0.98 redundancy is a linear
                         combination of things already present, whatever it is
                         named.

Features are then grouped into clusters by correlation, and one representative
is chosen per cluster. Testing one representative per cluster instead of every
feature is the difference between forty tests and eight.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from scipy.cluster import hierarchy
from scipy.spatial.distance import squareform
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from ..logging_setup import get_logger
from .inference import purged_walk_forward_folds

log = get_logger("research.redundancy")

HIGH_REDUNDANCY = 0.90
CLUSTER_CORRELATION_THRESHOLD = 0.80


def _fit_predict(
    x_train: np.ndarray, y_train: np.ndarray, x_test: np.ndarray, alpha: float = 10.0
) -> np.ndarray:
    """Ridge on standardised columns, with the scaler fitted on train only.

    Ridge penalises coefficient size, so on unstandardised columns the penalty
    lands on whichever features happen to be measured in small units rather
    than on whichever features are least useful.
    """
    model = make_pipeline(StandardScaler(), Ridge(alpha=alpha))
    model.fit(x_train, y_train)
    return model.predict(x_test)


def marginal_information(
    target: pd.Series,
    incumbent: pd.DataFrame,
    candidate: pd.Series,
    horizon_bars: int,
    n_folds: int = 4,
    alpha: float = 10.0,
) -> dict[str, Any]:
    """Out-of-sample R squared gained by adding `candidate` to `incumbent`.

    Both models are fitted on training folds only and scored on the held-out
    fold, with the usual purge and embargo. An in-sample comparison would
    always favour the larger model, which is why it is not used.

    The score can be negative. That is not a failure of the measurement - it is
    the feature actively hurting out-of-sample prediction, and it is the most
    common outcome for a feature correlated with things already present.
    """
    frame = pd.concat([target.rename("_y"), incumbent, candidate.rename("_cand")], axis=1)
    frame = frame.dropna()
    if len(frame) < 200:
        return {"status": "INSUFFICIENT_DATA", "rows": len(frame)}

    y = frame["_y"].to_numpy(dtype=float)
    base_cols = [c for c in frame.columns if c not in ("_y", "_cand")]
    if not base_cols:
        return {"status": "NO_INCUMBENT"}
    x_base = frame[base_cols].to_numpy(dtype=float)
    x_full = frame[[*base_cols, "_cand"]].to_numpy(dtype=float)

    folds = purged_walk_forward_folds(
        pd.DatetimeIndex(frame.index), horizon_bars=horizon_bars, n_folds=n_folds
    )
    if not folds:
        return {"status": "NO_FOLDS"}

    base_scores: list[float] = []
    full_scores: list[float] = []
    for fold in folds:
        train = fold.train_mask.reindex(frame.index, fill_value=False).to_numpy()
        test = fold.test_mask.reindex(frame.index, fill_value=False).to_numpy()
        if train.sum() < 100 or test.sum() < 30:
            continue
        y_test = y[test]
        denominator = float(((y_test - y[train].mean()) ** 2).sum())
        if denominator <= 0:
            continue
        for matrix, scores in ((x_base, base_scores), (x_full, full_scores)):
            prediction = _fit_predict(matrix[train], y[train], matrix[test], alpha)
            residual = float(((y_test - prediction) ** 2).sum())
            scores.append(1 - residual / denominator)

    if len(base_scores) < 2 or len(full_scores) != len(base_scores):
        return {"status": "INSUFFICIENT_FOLDS", "folds": len(base_scores)}

    base_r2 = float(np.mean(base_scores))
    full_r2 = float(np.mean(full_scores))
    gain = full_r2 - base_r2
    per_fold_gain = [f - b for f, b in zip(full_scores, base_scores, strict=True)]
    positive = sum(1 for g in per_fold_gain if g > 0)

    return {
        "status": "OK",
        "baseline_oos_r2": round(base_r2, 5),
        "with_candidate_oos_r2": round(full_r2, 5),
        "marginal_information_score": round(gain, 5),
        "folds": len(base_scores),
        "folds_improved": positive,
        "consistent": positive == len(per_fold_gain),
        "per_fold_gain": [round(g, 5) for g in per_fold_gain],
        "verdict": (
            "ADDS_INFORMATION" if gain > 0 and positive >= len(per_fold_gain) - 1
            else "NO_MARGINAL_INFORMATION" if gain <= 0
            else "INCONSISTENT"
        ),
        "note": (
            f"Adding the feature changes out-of-sample R2 by {gain:+.5f}, "
            f"improving {positive} of {len(per_fold_gain)} folds. "
            + (
                "Negative or inconsistent gains mean the feature is noise once "
                "the incumbents are present."
                if gain <= 0 or positive < len(per_fold_gain) - 1 else
                "The gain is small in absolute terms, as all such gains are on "
                "daily returns; what matters is that it is positive in every fold."
            )
        ),
    }


def redundancy_score(features: pd.DataFrame, column: str, alpha: float = 1.0) -> float | None:
    """R squared from regressing one feature on all the others.

    1.0 means the feature is exactly reconstructible from the rest and carries
    no independent content.
    """
    frame = features.dropna()
    others = [c for c in frame.columns if c != column]
    if len(frame) < 100 or not others:
        return None
    x = frame[others].to_numpy(dtype=float)
    y = frame[column].to_numpy(dtype=float)
    if float(np.var(y)) <= 0:
        return None
    model = make_pipeline(StandardScaler(), Ridge(alpha=alpha))
    model.fit(x, y)
    residual = float(((y - model.predict(x)) ** 2).sum())
    total = float(((y - y.mean()) ** 2).sum())
    return float(1 - residual / total) if total > 0 else None


@dataclass(slots=True)
class RedundancyReport:
    n_features: int = 0
    correlations: dict[str, float] = field(default_factory=dict)
    redundancy: dict[str, float] = field(default_factory=dict)
    clusters: dict[str, list[str]] = field(default_factory=dict)
    representatives: dict[str, str] = field(default_factory=dict)
    effective_features: int = 0
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_features": self.n_features,
            "highest_correlations": self.correlations,
            "redundancy_r2": self.redundancy,
            "clusters": self.clusters,
            "representatives": self.representatives,
            "effective_features": self.effective_features,
            "reduction_pct": (
                round((1 - self.effective_features / self.n_features) * 100, 1)
                if self.n_features else 0.0
            ),
            "note": self.note,
        }


def cluster_features(
    features: pd.DataFrame, threshold: float = CLUSTER_CORRELATION_THRESHOLD
) -> tuple[dict[str, list[str]], dict[str, str]]:
    """Group features by correlation; pick one representative per group.

    Average-linkage clustering on 1 - |correlation|. The representative is the
    feature with the highest average correlation to its own cluster, which is
    the one that best stands for the others rather than the one that happens to
    be listed first.
    """
    frame = features.dropna()
    columns = [c for c in frame.columns if float(frame[c].var()) > 0]
    if len(columns) < 2:
        return ({c: [c] for c in columns}, {c: c for c in columns})

    correlation = frame[columns].corr().abs().fillna(0.0)
    distance = 1 - correlation.to_numpy()
    np.fill_diagonal(distance, 0.0)
    distance = (distance + distance.T) / 2          # enforce exact symmetry
    linkage = hierarchy.linkage(squareform(distance, checks=False), method="average")
    labels = hierarchy.fcluster(linkage, t=1 - threshold, criterion="distance")

    clusters: dict[str, list[str]] = {}
    for column, label in zip(columns, labels, strict=True):
        clusters.setdefault(f"cluster_{int(label)}", []).append(column)

    representatives: dict[str, str] = {}
    for name, members in clusters.items():
        if len(members) == 1:
            representatives[name] = members[0]
            continue
        centrality = {
            member: float(correlation.loc[member, members].sum() - 1)
            for member in members
        }
        representatives[name] = max(centrality, key=lambda m: centrality[m])
    return clusters, representatives


def feature_redundancy_report(features: pd.DataFrame) -> RedundancyReport:
    """Correlation, redundancy and clustering for a feature block."""
    frame = features.dropna()
    columns = [c for c in frame.columns if float(frame[c].var()) > 0]
    report = RedundancyReport(n_features=len(columns))
    if len(columns) < 2:
        report.note = "fewer than two usable features"
        return report

    correlation = frame[columns].corr().abs()
    pairs = {
        f"{a}~{b}": round(float(correlation.loc[a, b]), 3)
        for i, a in enumerate(columns) for b in columns[i + 1:]
    }
    report.correlations = dict(
        sorted(pairs.items(), key=lambda kv: kv[1], reverse=True)[:15]
    )
    report.redundancy = {
        column: round(value, 4)
        for column in columns
        if (value := redundancy_score(frame[columns], column)) is not None
    }
    report.clusters, report.representatives = cluster_features(frame[columns])
    report.effective_features = len(report.clusters)

    highly_redundant = [
        c for c, v in report.redundancy.items() if v >= HIGH_REDUNDANCY
    ]
    report.note = (
        f"{len(columns)} features collapse to {report.effective_features} "
        f"correlation clusters. {len(highly_redundant)} are at least "
        f"{HIGH_REDUNDANCY:.0%} reconstructible from the others"
        + (f": {', '.join(sorted(highly_redundant)[:6])}. " if highly_redundant else ". ")
        + "Testing one representative per cluster rather than every feature is "
        "what keeps the multiple-testing burden honest."
    )
    return report

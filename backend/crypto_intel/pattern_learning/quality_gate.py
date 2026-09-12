"""Chronological quality gate for raw structural-pattern detections.

The target is independent geometric agreement, not a future price return.  All
features are available at the production detector's ``first_seen_at`` time.
The last 20% of detections are locked away while the model and its threshold
are selected on earlier walk-forward folds, then evaluated exactly once.

This gate is intentionally a shadow model.  It may reduce the number of noisy
shapes shown to a user, but it cannot turn recognition quality into a trading
probability or directional edge.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import norm
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from ..core.enums import Asset, Timeframe
from ..engines.technical.indicators import atr
from ..history import store
from ..structure.history_scan import scan_cached
from ..structure.patterns import StructuralPattern
from .consensus import compare_with_lmw, production_detection_id
from .lmw import LMWConfig, scan_lmw

DEVELOPMENT_SHARE = 0.80
TARGET_PRECISION = 0.50
# The validation target includes a buffer so normal drift does not immediately
# push a nominal 50% result below the user's requested floor.
VALIDATION_PRECISION_TARGET = 0.55
MIN_VALIDATION_SELECTIONS = 60
MIN_FINAL_SELECTIONS = 30

CATEGORICAL_FEATURES = ("pattern", "pattern_class", "state", "timeframe")
METADATA_COLUMNS = frozenset({"time", "asset", "target"})


def _live_payload(pattern: StructuralPattern, index: int) -> dict[str, Any]:
    times = [point.time for point in pattern.geometry.points]
    for line in pattern.geometry.trend_lines:
        times.extend((line.start.time, line.end.time))
    start = min(times) if times else pattern.detected_at
    return {
        "id": f"live-{index}",
        "name": pattern.name,
        "span_start": start.isoformat(),
        "span_end": pattern.detected_at.isoformat(),
        "first_seen_at": pattern.detected_at.isoformat(),
        "recognition_confidence": pattern.recognition_confidence,
    }


def apply_independent_live_gate(
    patterns: list[StructuralPattern],
    close: pd.Series,
    *,
    config: LMWConfig | None = None,
) -> dict[str, Any]:
    """Promote only live shapes independently recognised by both methods.

    The final 400 bars are sufficient for a comparator whose maximum figure
    span is 180 bars, while retaining ample warm-up for its causal smoother.
    Raw detections are returned as decisions rather than discarded, so a
    rejected pattern remains auditable.
    """
    if not patterns:
        return {
            "status": "NO_CANDIDATES",
            "accepted": [],
            "decisions": [],
            "summary": {"candidates": 0, "promoted": 0, "rejected": 0},
            "edge_claim": False,
        }
    payloads = [_live_payload(pattern, index) for index, pattern in enumerate(patterns)]
    lmw = scan_lmw(close.iloc[-400:], config=config)
    report = compare_with_lmw(payloads, lmw)
    agreements = {item.ours_id: item for item in report.agreements}
    accepted: list[StructuralPattern] = []
    decisions: list[dict[str, Any]] = []
    for index, pattern in enumerate(patterns):
        identity = f"live-{index}"
        agreement = agreements.get(identity)
        promoted = agreement is not None
        if promoted:
            accepted.append(pattern)
        decisions.append({
            "id": identity,
            "pattern": pattern.name,
            "promoted": promoted,
            "state": "INDEPENDENT_AGREEMENT" if promoted else "REJECTED_NO_AGREEMENT",
            "temporal_iou": agreement.temporal_iou if agreement else None,
            "lmw_score": agreement.lmw_score if agreement else None,
            "reason": (
                "same canonical figure and temporal IoU >= 0.35"
                if promoted
                else "no independent kernel-template match for this live figure"
            ),
        })
    return {
        "status": "OK",
        "accepted": accepted,
        "decisions": decisions,
        "summary": {
            "candidates": len(patterns),
            "promoted": len(accepted),
            "rejected": len(patterns) - len(accepted),
            "independent_confirmation_share_of_promoted_pct": (
                100.0 if accepted else None
            ),
        },
        "edge_claim": False,
        "note": (
            "Promotion requires actual independent agreement. This is a geometry "
            "quality gate, never a probability of a future return."
        ),
    }


def _point_kind(pattern: str, role: str) -> str | None:
    if "top" in role or "upper" in role:
        return "high"
    if "bottom" in role or "lower" in role:
        return "low"
    inverse = pattern == "inverse_head_and_shoulders"
    if "head" in role or "shoulder" in role:
        return "low" if inverse else "high"
    if "armpit" in role:
        return "high" if inverse else "low"
    return None


def _features(
    detection: dict[str, Any], frame: pd.DataFrame, atr_values: pd.Series
) -> dict[str, Any] | None:
    when = pd.Timestamp(detection["first_seen_at"])
    position = frame.index.get_indexer([when], method="bfill")[0]
    if position < 0:
        return None

    components = detection.get("components") or {}
    geometry = detection.get("geometry") or {}
    validation = detection.get("geometry_validation") or {}
    component_values = [
        float(value)
        for value in components.values()
        if isinstance(value, (int, float)) and np.isfinite(value)
    ]
    current_atr = float(atr_values.iloc[position])
    close_distances: list[float] = []
    close_extrema: list[int] = []
    for point in geometry.get("points") or []:
        point_time = pd.Timestamp(point["time"])
        point_position = frame.index.get_indexer([point_time])[0]
        if point_position < 0 or point_position > position:
            continue
        if current_atr > 0 and np.isfinite(current_atr):
            close_distances.append(
                abs(float(point["price"]) - float(frame["close"].iloc[point_position]))
                / current_atr
            )
        expected = _point_kind(str(detection["name"]), str(point.get("role") or ""))
        if expected is None:
            continue
        start = max(0, point_position - 5)
        stop = min(position, point_position + 5)
        local = frame["close"].iloc[start:stop + 1]
        value = float(frame["close"].iloc[point_position])
        close_extrema.append(
            int(value >= float(local.max()))
            if expected == "high"
            else int(value <= float(local.min()))
        )

    numeric_components = {
        f"component__{key}": float(value)
        for key, value in components.items()
        if isinstance(value, (int, float)) and np.isfinite(value)
    }
    price = float(frame["close"].iloc[position])
    returns = frame["close"].pct_change()
    record: dict[str, Any] = {
        "time": when,
        "pattern": str(detection["name"]),
        "pattern_class": str(detection["pattern_class"]),
        "state": str(detection["state"]),
        "timeframe": str(detection.get("timeframe") or ""),
        "confidence": float(detection["recognition_confidence"]),
        "span": float(detection.get("bars_span") or 0.0),
        "geometry_score": validation.get("score"),
        "n_points": len(geometry.get("points") or []),
        "n_lines": len(geometry.get("trend_lines") or []),
        "n_zones": len(geometry.get("zones") or []),
        "component_mean": np.mean(component_values) if component_values else np.nan,
        "component_min": np.min(component_values) if component_values else np.nan,
        "component_max": np.max(component_values) if component_values else np.nan,
        "close_distance_mean_atr": (
            np.mean(close_distances) if close_distances else np.nan
        ),
        "close_distance_max_atr": (
            np.max(close_distances) if close_distances else np.nan
        ),
        "close_extrema_share": np.mean(close_extrema) if close_extrema else np.nan,
        "atr_pct": current_atr / price if price > 0 else np.nan,
        **numeric_components,
    }
    for lookback in (5, 20, 60):
        start = max(0, position - lookback)
        record[f"return_{lookback}"] = (
            price / float(frame["close"].iloc[start]) - 1.0
            if position > 0 else 0.0
        )
        record[f"volatility_{lookback}"] = returns.iloc[start + 1:position + 1].std()
    volume_window = frame["volume"].iloc[max(0, position - 19):position + 1]
    median_volume = float(volume_window.median())
    record["volume_ratio"] = (
        float(frame["volume"].iloc[position]) / median_volume
        if median_volume > 0 else np.nan
    )
    return record


def build_quality_dataset(consensus: dict[str, Any]) -> pd.DataFrame:
    """Join production-only causal features to independent agreement labels."""
    rows: list[dict[str, Any]] = []
    for result in consensus.get("results", {}).values():
        if result.get("status") != "OK":
            continue
        asset = Asset(str(result["asset"]))
        timeframe = Timeframe(str(result["timeframe"]))
        frame = store.load_candles(asset, timeframe)
        if frame.empty:
            continue
        labels = {
            str(item["ours_id"]): int(item["state"] == "INDEPENDENT_AGREEMENT")
            for item in result.get("items", [])
            if item.get("ours_id")
        }
        atr_values = atr(frame["high"], frame["low"], frame["close"], 14)
        for detection in scan_cached(asset.value, timeframe, frame):
            identity = production_detection_id(detection)
            if identity not in labels:
                continue
            enriched = dict(detection)
            enriched["timeframe"] = timeframe.value
            record = _features(enriched, frame, atr_values)
            if record is None:
                continue
            record["asset"] = asset.value
            record["target"] = labels[identity]
            rows.append(record)
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("time").reset_index(drop=True)


def _model(numeric_features: list[str]) -> Pipeline:
    preprocessing = ColumnTransformer(
        [
            (
                "numeric",
                SimpleImputer(strategy="median", keep_empty_features=True),
                numeric_features,
            ),
            (
                "categorical",
                OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                list(CATEGORICAL_FEATURES),
            ),
        ],
        sparse_threshold=0,
    )
    classifier = HistGradientBoostingClassifier(
        max_iter=150,
        max_leaf_nodes=12,
        l2_regularization=8.0,
        class_weight="balanced",
        random_state=42,
    )
    return Pipeline([("features", preprocessing), ("classifier", classifier)])


def _development_folds(frame: pd.DataFrame) -> list[tuple[pd.Series, pd.Series]]:
    folds: list[tuple[pd.Series, pd.Series]] = []
    for lower, upper in ((0.40, 0.55), (0.55, 0.675), (0.675, 0.80)):
        start = frame["time"].quantile(lower)
        stop = frame["time"].quantile(upper)
        folds.append((frame["time"] < start, frame["time"].between(start, stop, inclusive="left")))
    return folds


def choose_validation_threshold(
    target: np.ndarray,
    scores: np.ndarray,
    *,
    minimum_precision: float = VALIDATION_PRECISION_TARGET,
    minimum_selected: int = MIN_VALIDATION_SELECTIONS,
) -> dict[str, Any]:
    """Keep the broadest validation subset meeting the buffered target."""
    if len(target) != len(scores):
        raise ValueError("target and scores must have the same length")
    candidates: list[tuple[int, float, float]] = []
    for threshold in np.unique(scores):
        selected = scores >= threshold
        count = int(selected.sum())
        if count < minimum_selected:
            continue
        precision = float(target[selected].mean())
        if precision >= minimum_precision:
            candidates.append((count, float(threshold), precision))
    if not candidates:
        return {"status": "TARGET_NOT_REACHED"}
    count, threshold, precision = max(candidates, key=lambda item: item[0])
    return {
        "status": "OK",
        "threshold": threshold,
        "selected": count,
        "precision": precision,
    }


def _wilson(successes: int, total: int, confidence: float = 0.95) -> list[float] | None:
    if total <= 0:
        return None
    z = float(norm.ppf(1.0 - (1.0 - confidence) / 2.0))
    share = successes / total
    denominator = 1.0 + z * z / total
    centre = (share + z * z / (2.0 * total)) / denominator
    margin = z * np.sqrt(share * (1.0 - share) / total + z * z / (4.0 * total**2))
    margin /= denominator
    return [round(float(centre - margin), 4), round(float(centre + margin), 4)]


def train_and_audit_quality_gate(consensus: dict[str, Any]) -> dict[str, Any]:
    """Select on walk-forward development folds, then open the final holdout."""
    frame = build_quality_dataset(consensus)
    if frame.empty or len(frame) < 500:
        return {"status": "INSUFFICIENT_DATA", "rows": len(frame)}

    cutoff = frame["time"].quantile(DEVELOPMENT_SHARE)
    development = frame[frame["time"] < cutoff]
    final = frame[frame["time"] >= cutoff]
    numeric = sorted(
        column
        for column in frame.columns
        if column not in METADATA_COLUMNS and column not in CATEGORICAL_FEATURES
    )

    oof_scores: list[float] = []
    oof_targets: list[int] = []
    fold_reports: list[dict[str, Any]] = []
    for index, (train_mask, validation_mask) in enumerate(_development_folds(frame)):
        train = frame[train_mask]
        validation = frame[validation_mask]
        model = _model(numeric)
        model.fit(train, train["target"])
        scores = model.predict_proba(validation)[:, 1]
        oof_scores.extend(float(value) for value in scores)
        oof_targets.extend(int(value) for value in validation["target"])
        fold_reports.append({
            "fold": index,
            "train_end": train["time"].max().isoformat(),
            "validation_period": [
                validation["time"].min().isoformat(),
                validation["time"].max().isoformat(),
            ],
            "n_train": len(train),
            "n_validation": len(validation),
        })

    threshold_result = choose_validation_threshold(
        np.asarray(oof_targets, dtype=int),
        np.asarray(oof_scores, dtype=float),
    )
    if threshold_result["status"] != "OK":
        return {
            "status": "TARGET_NOT_REACHED_ON_VALIDATION",
            "rows": len(frame),
            "folds": fold_reports,
        }

    threshold = float(threshold_result["threshold"])
    final_model = _model(numeric)
    final_model.fit(development, development["target"])
    final_scores = final_model.predict_proba(final)[:, 1]
    selected = final_scores >= threshold
    n_selected = int(selected.sum())
    successes = int(final.loc[selected, "target"].sum()) if n_selected else 0
    precision = successes / n_selected if n_selected else None
    interval = _wilson(successes, n_selected)
    enough = n_selected >= MIN_FINAL_SELECTIONS
    reaches_target = bool(enough and precision is not None and precision >= TARGET_PRECISION)
    statistically_above = bool(interval and interval[0] >= TARGET_PRECISION)

    return {
        "status": "OK",
        "objective": (
            "At least 50% independent geometric agreement among promoted raw "
            "detections on the untouched chronological holdout"
        ),
        "target_precision_pct": TARGET_PRECISION * 100.0,
        "dataset": {
            "rows": len(frame),
            "independent_agreements": int(frame["target"].sum()),
            "base_rate_pct": round(float(frame["target"].mean() * 100.0), 2),
            "development_rows": len(development),
            "final_rows": len(final),
            "final_period": [final["time"].min().isoformat(), final["time"].max().isoformat()],
        },
        "selection": {
            "method": "three expanding chronological folds inside the first 80%",
            "validation_precision_target_pct": VALIDATION_PRECISION_TARGET * 100.0,
            "threshold": round(threshold, 6),
            "selected_oof": int(threshold_result["selected"]),
            "precision_oof_pct": round(float(threshold_result["precision"]) * 100.0, 2),
            "folds": fold_reports,
        },
        "untouched_final_test": {
            "opened_after_rule_frozen": True,
            "candidates": len(final),
            "promoted": n_selected,
            "independent_agreements": successes,
            "precision_pct": round(float(precision) * 100.0, 2) if precision is not None else None,
            "promotion_rate_pct": round(n_selected / len(final) * 100.0, 2),
            "recall_pct": round(successes / int(final["target"].sum()) * 100.0, 2),
            "precision_wilson_95": interval,
            "minimum_sample_met": enough,
            "point_target_reached": reaches_target,
            "lower_confidence_bound_reaches_target": statistically_above,
        },
        "verdict": (
            "TARGET_REACHED" if reaches_target else "TARGET_NOT_REACHED"
        ),
        "deployment": (
            "SHADOW_ONLY. This predicts independent geometry agreement, not price. "
            "Production promotion still requires the actual second detector."
        ),
        "features": numeric + list(CATEGORICAL_FEATURES),
        "leakage_guards": [
            "all features end at first_seen_at",
            "breakout outcome and later resolution are excluded",
            "threshold selected before the final 20% is opened",
            "asset is metadata, not a predictive feature",
        ],
    }


def save_quality_gate_audit(
    result: dict[str, Any],
    path: str | Path = "data/research/pattern_quality_gate.json",
) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2, default=str))
    return target

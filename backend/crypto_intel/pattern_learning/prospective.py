"""Prospective monitoring for the only promising pattern-consensus candidate.

The historical scan suggested that independent agreement on one-hour figures
may improve the textbook-direction hit rate around 72 hours.  It did not
survive correction across every horizon, so it is not promoted.  This module
starts a clean clock and records only agreements that occur after registration.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from ..core.enums import Asset, Timeframe
from ..history import store
from ..research.live_experiments import (
    LiveExperiment,
    LiveExperimentRegistry,
    assess_maturity,
    get_live_registry,
)
from ..structure.history_scan import scan_cached
from .consensus import compare_with_lmw
from .lmw import TEMPLATE_BY_PATTERN, PatternOrientation, scan_lmw
from .ontology import StructuralPatternName

EXPERIMENT_ID = "pattern_consensus__1h__textbook_direction__h72"
HORIZON_BARS = 72
EXPECTED_EVENTS_PER_YEAR = 25.0
REQUIRED_OBSERVATIONS = 200
# Freeze the rule that was actually registered.  Adding a new comparator
# template later must not silently widen an experiment already in progress.
ELIGIBLE_PATTERNS = frozenset({
    StructuralPatternName.DOUBLE_TOP,
    StructuralPatternName.DOUBLE_BOTTOM,
    StructuralPatternName.HEAD_SHOULDERS,
    StructuralPatternName.INVERSE_HEAD_SHOULDERS,
})
EXPERIMENT_NOTE = (
    "Prospective only. Historical exploration selected this candidate; no "
    "historical observation is allowed into the live experiment. Frozen v1 "
    "families: double top/bottom and head-and-shoulders/inverse. Places no order."
)


def ensure_pattern_experiment(
    registry: LiveExperimentRegistry | None = None,
) -> LiveExperiment:
    target = registry or get_live_registry()
    experiment = target.register(LiveExperiment(
        id=EXPERIMENT_ID,
        claim=(
            "A 1h structural pattern independently recognised by the causal-pivot "
            "and LMW kernel-template methods has a positive textbook-direction "
            "return 72 bars later across BTC, ETH and SOL"
        ),
        hypothesis_key=EXPERIMENT_ID,
        horizon_days=3,
        expected_effect_pct=0.7,
        expected_sign=1,
        required_observations=REQUIRED_OBSERVATIONS,
        expected_events_per_year=EXPECTED_EVENTS_PER_YEAR,
        note=EXPERIMENT_NOTE,
    ))
    # Before the first observation, keep planning metadata aligned with the
    # measured non-overlapping event rate. This does not alter the frozen rule
    # or reset any evidence; once collection starts even this field is left
    # untouched.
    if not experiment.observations:
        experiment.expected_events_per_year = EXPECTED_EVENTS_PER_YEAR
        experiment.note = EXPERIMENT_NOTE
    return experiment


def update_pattern_experiment(
    registry: LiveExperimentRegistry | None = None,
) -> dict[str, Any]:
    """Record new agreements and settle those with 72 subsequent hourly bars."""
    target = registry or get_live_registry()
    experiment = ensure_pattern_experiment(target)
    registered_at = datetime.fromisoformat(experiment.registered_at)
    if registered_at.tzinfo is None:
        registered_at = registered_at.replace(tzinfo=UTC)

    new_events = newly_settled = 0
    by_asset: dict[str, int] = {}
    frames: dict[str, Any] = {}
    candidates: list[tuple[datetime, Asset, Any, Any, int]] = []
    for asset in Asset.tradables():
        frame = store.load_candles(asset, Timeframe.H1)
        if frame.empty:
            continue
        frames[asset.value] = frame
        ours = scan_cached(asset.value, Timeframe.H1, frame)
        lmw = [
            detection for detection in scan_lmw(frame["close"])
            if detection.pattern in ELIGIBLE_PATTERNS
        ]
        agreements = compare_with_lmw(ours, lmw).agreements
        for agreement in agreements:
            if agreement.available_at < registered_at:
                continue
            if agreement.pattern not in ELIGIBLE_PATTERNS:
                continue
            template = TEMPLATE_BY_PATTERN[agreement.pattern]
            if template.orientation is PatternOrientation.NEUTRAL:
                continue
            position = frame.index.get_indexer([agreement.available_at], method="bfill")[0]
            if position < 0:
                continue
            candidates.append((agreement.available_at, asset, agreement, template, position))
        by_asset[asset.value] = 0

    # One future 72-hour window is one independent observation. Simultaneous
    # signals on correlated assets, or another figure the next hour, cannot
    # inflate maturity. The first event starts the block; later overlapping
    # candidates remain visible in the consensus report but not in this test.
    separation = timedelta(hours=HORIZON_BARS)
    selected_times = [
        datetime.fromisoformat(str(item["occurred_at"]))
        for item in experiment.observations
        if item.get("occurred_at")
    ]
    for when, asset, agreement, _template, _position in sorted(
        candidates,
        key=lambda item: (item[0], item[1].value, item[2].pattern.value),
    ):
        if any(abs(when - previous) < separation for previous in selected_times):
            continue
        metadata = {
            "asset": asset.value,
            "timeframe": Timeframe.H1.value,
            "pattern": agreement.pattern.value,
            "ours_id": agreement.ours_id,
            "lmw_id": agreement.lmw_id,
            "horizon_bars": HORIZON_BARS,
            "target": "textbook_direction_return_pct",
            "rule_version": "v1_frozen",
        }
        target.record_observation(
            EXPERIMENT_ID,
            when.isoformat(),
            signal_value=agreement.temporal_iou,
            metadata=metadata,
        )
        selected_times.append(when)
        new_events += 1
        by_asset[asset.value] += 1

    # Settle previously recorded events once their complete target window is
    # available. This does not depend on the detector finding them again.
    for observation in experiment.observations:
        if observation.get("outcome_pct") is not None:
            continue
        metadata = observation.get("metadata") or {}
        asset_value = str(metadata.get("asset") or "")
        frame = frames.get(asset_value)
        if frame is None:
            continue
        occurred_at = datetime.fromisoformat(str(observation["occurred_at"]))
        position = frame.index.get_indexer([occurred_at], method="bfill")[0]
        if position < 0 or position + HORIZON_BARS >= len(frame):
            continue
        pattern = TEMPLATE_BY_PATTERN[StructuralPatternName(metadata["pattern"])]
        direction = (
            1.0 if pattern.orientation is PatternOrientation.BULLISH else -1.0
        )
        start = float(frame["close"].iloc[position])
        end = float(frame["close"].iloc[position + HORIZON_BARS])
        outcome = round((end / start - 1.0) * 100.0 * direction, 6)
        target.record_observation(
            EXPERIMENT_ID,
            occurred_at.isoformat(),
            outcome_pct=outcome,
            metadata=metadata,
        )
        newly_settled += 1

    target.save()
    return {
        "experiment_id": EXPERIMENT_ID,
        "new_events_recorded": new_events,
        "newly_settled": newly_settled,
        "events_by_asset": by_asset,
        "maturity": assess_maturity(experiment),
        "note": (
            "Only events at or after registered_at are recorded. Forward windows "
            "overlapping by less than 72 hours count once across all assets. Historical "
            "results remain exploratory and cannot mature this experiment."
        ),
    }

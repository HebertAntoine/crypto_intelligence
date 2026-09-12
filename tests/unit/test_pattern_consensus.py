"""Independent agreement must be strict, one-to-one, and never claim edge."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd

from crypto_intel.pattern_learning import (
    ConsensusState,
    compare_with_lmw,
    methods_are_independent,
    temporal_iou,
)
from crypto_intel.pattern_learning.lmw import LMWConfig, scan_lmw
from crypto_intel.pattern_learning.ontology import StructuralPatternName
from crypto_intel.structure.history_scan import HistoricalPattern
from crypto_intel.structure.patterns import (
    PatternClass,
    PatternState,
    StructuralPattern,
)

START = datetime(2024, 1, 1, tzinfo=UTC)


def _ours(name: str, start_day: int, end_day: int) -> HistoricalPattern:
    end = START + timedelta(days=end_day)
    pattern = StructuralPattern(
        name=name,
        pattern_class=PatternClass.DETERMINISTIC,
        state=PatternState.CANDIDATE,
        recognition_confidence=82.0,
        detected_at=end,
    )
    return HistoricalPattern(
        pattern=pattern,
        first_seen_index=end_day,
        first_seen_time=end,
        start_time=START + timedelta(days=start_day),
        end_time=end,
    )


def _lmw_double_top():
    legs = [
        pd.Series([100 + i * 2 for i in range(12)]),
        pd.Series([124 - i * 2 for i in range(11)]),
        pd.Series([104 + i * 2 for i in range(10)]),
        pd.Series([123 - i * 1.5 for i in range(12)]),
    ]
    values = pd.concat(legs, ignore_index=True).astype(float)
    values.index = pd.date_range(START, periods=len(values), freq="D")
    config = LMWConfig(
        causal_bandwidth_bars=1.5,
        min_bars=20,
        min_amplitude_to_noise=2.0,
        min_shape_fit=50.0,
        min_match_score=50.0,
    )
    matches = scan_lmw(
        values,
        config=config,
        patterns=[StructuralPatternName.DOUBLE_TOP],
    )
    assert matches
    return matches[0]


def test_temporal_iou_penalises_shift_and_size():
    same = temporal_iou(START, START + timedelta(days=20), START, START + timedelta(days=20))
    shifted = temporal_iou(
        START,
        START + timedelta(days=20),
        START + timedelta(days=10),
        START + timedelta(days=30),
    )
    assert same == 1.0
    assert shifted == 1 / 3


def test_matching_name_and_window_produces_independent_agreement():
    lmw = _lmw_double_top()
    ours = _ours("double_top", lmw.start_index, lmw.end_index)

    report = compare_with_lmw([ours], [lmw])

    assert report.summary()["independent_agreements"] == 1
    item = report.agreements[0]
    assert item.state is ConsensusState.INDEPENDENT_AGREEMENT
    assert item.to_dict()["independent_methods"] is True
    assert item.to_dict()["edge_claim"] is False


def test_same_window_with_different_pattern_is_not_agreement():
    lmw = _lmw_double_top()
    ours = _ours("double_bottom", lmw.start_index, lmw.end_index)

    summary = compare_with_lmw([ours], [lmw]).summary()

    assert summary["independent_agreements"] == 0
    assert summary["ours_only"] == 1
    assert summary["lmw_only"] == 1


def test_one_lmw_detection_cannot_validate_two_production_detections():
    lmw = _lmw_double_top()
    ours = [
        _ours("double_top", lmw.start_index, lmw.end_index),
        _ours("double_top", lmw.start_index + 1, lmw.end_index + 1),
    ]

    summary = compare_with_lmw(ours, [lmw]).summary()

    assert summary["independent_agreements"] == 1
    assert summary["ours_only"] == 1


def test_unsupported_production_family_is_not_counted_as_disagreement():
    report = compare_with_lmw([_ours("cup_handle", 0, 20)], [])
    assert report.summary()["not_comparable_ours"] == 1
    assert report.summary()["comparable_ours"] == 0


def test_method_families_are_actually_different():
    assert methods_are_independent()


def test_cached_serialised_production_detection_can_be_compared():
    lmw = _lmw_double_top()
    payload = _ours("double_top", lmw.start_index, lmw.end_index).to_dict()

    report = compare_with_lmw([payload], [lmw])

    assert report.summary()["independent_agreements"] == 1
    assert report.agreements[0].available_at >= lmw.available_at

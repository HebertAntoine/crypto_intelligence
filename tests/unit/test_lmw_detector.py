"""Guards for the independent kernel-template pattern comparator."""

from __future__ import annotations

import numpy as np
import pandas as pd

from crypto_intel.pattern_learning.lmw import (
    TEMPLATE_BY_PATTERN,
    LMWConfig,
    LMWDetection,
    LMWMode,
    LMWStatus,
    detect_latest,
    scan_lmw,
)
from crypto_intel.pattern_learning.lmw.smoothing import (
    causal_kernel_smooth,
    kernel_smooth,
)
from crypto_intel.pattern_learning.ontology import (
    OURS_TO_CANONICAL,
    MethodFamily,
    StructuralPatternName,
)


def _leg(start: float, end: float, bars: int) -> np.ndarray:
    return np.linspace(start, end, bars, endpoint=False)


def _double_top() -> pd.Series:
    values = np.concatenate(
        [
            _leg(100, 124, 14),
            _leg(124, 104, 13),
            _leg(104, 123, 15),
            _leg(123, 106, 15),
        ]
    )
    index = pd.date_range("2024-01-01", periods=len(values), freq="D", tz="UTC")
    return pd.Series(values, index=index, name="close")


def _triple_bottom() -> pd.Series:
    values = np.concatenate(
        [
            _leg(120, 100, 12),
            _leg(100, 122, 12),
            _leg(122, 101, 12),
            _leg(101, 123, 12),
            _leg(123, 100.5, 12),
            _leg(100.5, 119, 12),
        ]
    )
    index = pd.date_range("2024-01-01", periods=len(values), freq="h", tz="UTC")
    return pd.Series(values, index=index, name="close")


def _permissive() -> LMWConfig:
    # Used only to isolate behaviour in synthetic guards. Production defaults
    # remain stricter and are never tuned from forward returns.
    return LMWConfig(
        bandwidth_fraction=0.02,
        causal_bandwidth_bars=2.0,
        min_bars=20,
        min_amplitude_to_noise=2.0,
        min_shape_fit=55.0,
        min_match_score=55.0,
    )


def test_known_double_top_is_recognised_with_explained_score():
    matches = scan_lmw(
        _double_top(),
        config=_permissive(),
        patterns=[StructuralPatternName.DOUBLE_TOP],
    )

    assert matches
    match = matches[-1]
    assert match.pattern is StructuralPatternName.DOUBLE_TOP
    assert match.score_is_explained()
    assert match.method_family is MethodFamily.KERNEL_TEMPLATE_MATCHING
    assert match.metadata["outcome_data_used"] is False
    assert match.detection_delay_bars == 1


def test_new_triple_family_is_covered_by_independent_template():
    matches = scan_lmw(
        _triple_bottom(),
        config=_permissive(),
        patterns=[StructuralPatternName.TRIPLE_BOTTOM],
    )

    assert matches
    assert matches[-1].pattern is StructuralPatternName.TRIPLE_BOTTOM
    assert matches[-1].orientation.value == "BULLISH"


def test_every_family_emitted_by_production_has_an_independent_template():
    assert set(OURS_TO_CANONICAL.values()) <= set(TEMPLATE_BY_PATTERN)


def test_flat_price_does_not_manufacture_a_pattern():
    close = pd.Series(
        np.full(200, 100.0),
        index=pd.date_range("2024-01-01", periods=200, freq="h", tz="UTC"),
    )
    assert scan_lmw(close) == []
    assert detect_latest(close).status is LMWStatus.NO_VALID_PATTERN


def test_causal_detections_do_not_move_when_future_bars_are_added():
    early = _double_top()
    future = pd.Series(
        np.linspace(float(early.iloc[-1]), 150.0, 30),
        index=pd.date_range(early.index[-1] + pd.Timedelta(days=1), periods=30, freq="D"),
    )
    full = pd.concat([early, future])

    before = scan_lmw(
        early,
        config=_permissive(),
        patterns=[StructuralPatternName.DOUBLE_TOP],
    )
    after = scan_lmw(
        full,
        config=_permissive(),
        patterns=[StructuralPatternName.DOUBLE_TOP],
    )
    assert before
    after_ids = {item.id for item in after}
    assert {item.id for item in before} <= after_ids
    for item in before:
        assert item.available_index < len(early)
        same = next(candidate for candidate in after if candidate.id == item.id)
        assert same.to_dict() == item.to_dict()


def test_retrospective_mode_is_never_presented_as_causal():
    matches = scan_lmw(
        _double_top(),
        mode=LMWMode.RETROSPECTIVE,
        config=_permissive(),
        patterns=[StructuralPatternName.DOUBLE_TOP],
    )
    assert matches
    for match in matches:
        assert not match.causal
        assert match.available_index == len(_double_top()) - 1
        assert match.available_at == _double_top().index[-1]


def test_serialisation_round_trip_preserves_the_public_contract():
    match = scan_lmw(
        _double_top(),
        config=_permissive(),
        patterns=[StructuralPatternName.DOUBLE_TOP],
    )[-1]
    restored = LMWDetection.from_dict(match.to_dict())

    assert restored.id == match.id
    assert restored.pattern is match.pattern
    assert restored.mode is match.mode
    assert restored.geometry.to_dict() == match.geometry.to_dict()


def test_bad_or_short_input_returns_a_qualified_no_result():
    short = _double_top().iloc[:10]
    assert detect_latest(short).status is LMWStatus.INSUFFICIENT_DATA

    broken = _double_top().copy()
    broken.iloc[5] = np.nan
    result = detect_latest(broken, config=_permissive())
    assert result.status is LMWStatus.INSUFFICIENT_DATA
    assert "missing" in result.reason


def test_fast_causal_kernel_matches_the_full_gaussian_formula():
    rng = np.random.default_rng(42)
    values = rng.normal(100.0, 4.0, 120)
    bandwidth = 3.0
    actual = causal_kernel_smooth(values, bandwidth)
    expected = []
    for index in range(len(values)):
        distance = np.arange(index + 1, dtype=float) - index
        weights = np.exp(-0.5 * (distance / bandwidth) ** 2)
        expected.append(float(values[:index + 1] @ weights / weights.sum()))
    np.testing.assert_allclose(actual, expected, rtol=2e-8, atol=2e-8)


def test_only_the_retrospective_kernel_reads_future_values():
    values = np.linspace(100.0, 120.0, 80)
    changed = values.copy()
    changed[40:] += 50.0

    causal_before = causal_kernel_smooth(values, 4.0)
    causal_after = causal_kernel_smooth(changed, 4.0)
    retrospective_before = kernel_smooth(values, 4.0)
    retrospective_after = kernel_smooth(changed, 4.0)

    np.testing.assert_allclose(causal_before[:40], causal_after[:40])
    assert not np.allclose(retrospective_before[35:40], retrospective_after[35:40])

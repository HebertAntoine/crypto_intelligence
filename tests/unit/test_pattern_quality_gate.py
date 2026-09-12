"""Selection and uncertainty guards for the structural quality gate."""

from __future__ import annotations

import numpy as np
import pandas as pd

from crypto_intel.pattern_learning.lmw import LMWConfig, scan_lmw
from crypto_intel.pattern_learning.quality_gate import (
    _point_kind,
    _wilson,
    apply_independent_live_gate,
    choose_validation_threshold,
)
from crypto_intel.structure.patterns import PatternClass, PatternState, StructuralPattern


def test_threshold_is_selected_without_relaxing_precision_floor():
    scores = np.linspace(0.0, 1.0, 100)
    target = np.zeros(100, dtype=int)
    target[-20:] = 1

    result = choose_validation_threshold(
        target,
        scores,
        minimum_precision=0.5,
        minimum_selected=20,
    )

    selected = scores >= result["threshold"]
    assert result["status"] == "OK"
    assert selected.sum() == 40
    assert target[selected].mean() == 0.5


def test_threshold_refuses_an_unreachable_target():
    result = choose_validation_threshold(
        np.zeros(100, dtype=int),
        np.linspace(0.0, 1.0, 100),
        minimum_selected=20,
    )
    assert result == {"status": "TARGET_NOT_REACHED"}


def test_wilson_interval_does_not_confuse_point_estimate_with_certainty():
    interval = _wilson(18, 30)
    assert interval is not None
    assert 0.5 < 18 / 30
    assert interval[0] < 0.5


def test_inverse_head_roles_have_the_right_polarity():
    assert _point_kind("head_and_shoulders", "head") == "high"
    assert _point_kind("inverse_head_and_shoulders", "head") == "low"


def test_live_gate_promotes_only_an_actual_independent_agreement():
    values = np.concatenate([
        np.linspace(100, 124, 14, endpoint=False),
        np.linspace(124, 104, 13, endpoint=False),
        np.linspace(104, 123, 15, endpoint=False),
        np.linspace(123, 106, 15, endpoint=False),
    ])
    close = pd.Series(
        values,
        index=pd.date_range("2024-01-01", periods=len(values), freq="h", tz="UTC"),
    )
    config = LMWConfig(
        causal_bandwidth_bars=2.0,
        min_bars=20,
        min_amplitude_to_noise=2.0,
        min_shape_fit=55.0,
        min_match_score=55.0,
    )
    independent = scan_lmw(close, config=config)[-1]
    pattern = StructuralPattern(
        name="double_top",
        pattern_class=PatternClass.DETERMINISTIC,
        state=PatternState.CANDIDATE,
        recognition_confidence=80.0,
        detected_at=independent.available_at,
        geometry=independent.geometry,
    )

    result = apply_independent_live_gate([pattern], close, config=config)

    assert result["summary"]["promoted"] == 1
    assert result["summary"]["independent_confirmation_share_of_promoted_pct"] == 100.0
    assert result["edge_claim"] is False

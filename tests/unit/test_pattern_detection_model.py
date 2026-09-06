"""The published pattern record must stay honest and reconstructable.

Two properties matter more than the rest and are pinned here:

  * a confidence that cannot be taken apart is flagged, per §22;
  * a signal with no data reads as UNAVAILABLE, never as adverse, per §9.

The geometry tests exist because the frontend redraws figures from this payload
alone. Bar indices would break the moment the store gains earlier history, so
every geometric element is asserted to carry a real timestamp.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from crypto_intel.core.enums import Timeframe
from crypto_intel.structure.detection import (
    ConfirmationSignal,
    GeometryPoint,
    GeometryZone,
    PatternDetection,
    PatternDirection,
    PatternFamily,
    PatternGeometry,
    PatternStatus,
    SignalVerdict,
    TrendLine,
    family_for,
    from_structural,
    make_pattern_id,
)
from crypto_intel.structure.patterns import (
    PatternClass,
    PatternEdgeState,
    PatternState,
    StructuralPattern,
)

START = datetime(2026, 6, 1, tzinfo=UTC)
END = datetime(2026, 8, 1, tzinfo=UTC)


def _detection(**overrides) -> PatternDetection:
    base = {
        "symbol": "BTC",
        "timeframe": Timeframe.H4,
        "pattern_type": "double_top",
        "family": PatternFamily.REVERSAL,
        "direction": PatternDirection.BEARISH,
        "start_time": START,
        "end_time": END,
        "detected_at": END,
        "status": PatternStatus.DETECTED,
        "recognition_confidence": 80.0,
        "confidence_components": {"extreme_agreement": 90.0, "reaction_depth": 70.0},
    }
    return PatternDetection(**{**base, **overrides})


# --- identity --------------------------------------------------------------

def test_id_is_stable_across_recomputation():
    """Re-running the detector on the same bars must not move the selection."""
    first = _detection()
    second = _detection(recognition_confidence=81.0, status=PatternStatus.CONFIRMED)

    assert first.id == second.id


def test_id_separates_assets_timeframes_and_windows():
    base = _detection()

    assert base.id != _detection(symbol="ETH").id
    assert base.id != _detection(timeframe=Timeframe.D1).id
    assert base.id != _detection(pattern_type="double_bottom").id
    assert base.id != _detection(end_time=END + timedelta(days=1)).id


def test_id_does_not_depend_on_when_it_was_computed():
    assert (
        make_pattern_id("BTC", "4h", "double_top", START, END)
        == make_pattern_id("BTC", "4h", "double_top", START, END)
    )


# --- traceability (§22) ----------------------------------------------------

def test_confidence_backed_by_its_components_is_explained():
    detection = _detection(
        recognition_confidence=80.0,
        confidence_components={"extreme_agreement": 90.0, "reaction_depth": 70.0},
    )

    assert detection.components_explain_confidence()
    assert detection.to_dict()["confidence_is_explained"] is True


def test_confidence_that_does_not_follow_from_its_parts_is_flagged():
    """A score invented independently of its components must not pass silently."""
    detection = _detection(
        recognition_confidence=95.0,
        confidence_components={"extreme_agreement": 40.0, "reaction_depth": 30.0},
    )

    assert not detection.components_explain_confidence()
    assert detection.to_dict()["confidence_is_explained"] is False


def test_confidence_without_components_is_never_considered_explained():
    detection = _detection(confidence_components={})

    assert not detection.components_explain_confidence()


# --- confluence signals (§9) ----------------------------------------------

def test_missing_signal_is_unavailable_and_carries_no_score():
    signal = ConfirmationSignal(
        family="volatility", name="dvol", verdict=SignalVerdict.UNAVAILABLE,
        detail="no DVOL provider configured",
    )

    assert not signal.available
    assert signal.score is None
    assert signal.to_dict()["available"] is False


def test_available_families_exclude_those_with_no_data():
    detection = _detection(
        confirmation_signals=[
            ConfirmationSignal("volume", "relative_volume", SignalVerdict.FAVOURABLE, 71.0),
            ConfirmationSignal("momentum", "rsi", SignalVerdict.NEUTRAL, 50.0),
            ConfirmationSignal("volatility", "dvol", SignalVerdict.UNAVAILABLE),
        ]
    )

    assert detection.available_families() == ["momentum", "volume"]
    assert "volatility" in detection.signals_by_family()


def test_adverse_signal_stays_available():
    """An unfavourable reading is data. Only a missing one is excluded."""
    detection = _detection(
        confirmation_signals=[
            ConfirmationSignal("derivatives", "funding", SignalVerdict.ADVERSE, 20.0),
        ]
    )

    assert detection.available_families() == ["derivatives"]


# --- geometry --------------------------------------------------------------

def test_geometry_serialises_with_timestamps_not_indices():
    """A chart holding a different candle window must still draw this correctly."""
    geometry = PatternGeometry(
        points=[GeometryPoint(START, 100.0, role="first_top")],
        trend_lines=[
            TrendLine(
                GeometryPoint(START, 100.0), GeometryPoint(END, 100.0),
                role="upper", extend=True,
            )
        ],
        zones=[GeometryZone(START, END, 95.0, 97.0, role="breakout")],
    )

    payload = geometry.to_dict()

    assert payload["points"][0]["time"] == START.isoformat()
    assert payload["trend_lines"][0]["start"]["time"] == START.isoformat()
    assert payload["trend_lines"][0]["extend"] is True
    assert payload["zones"][0]["start_time"] == START.isoformat()
    assert "index" not in str(payload)


def test_empty_geometry_is_reported_as_empty():
    assert PatternGeometry().is_empty
    assert not PatternGeometry(points=[GeometryPoint(START, 100.0)]).is_empty


# --- family classification -------------------------------------------------

def test_every_known_detector_has_a_declared_family():
    for name in (
        "double_top", "double_bottom", "triple_top", "triple_bottom",
        "head_and_shoulders", "inverse_head_and_shoulders",
        "ascending_triangle", "descending_triangle", "symmetrical_triangle",
        "rising_wedge", "falling_wedge",
    ):
        assert isinstance(family_for(name), PatternFamily)


def test_unclassified_pattern_raises_rather_than_guessing():
    """Adding a detector without declaring its family must not slip through."""
    with pytest.raises(KeyError, match="no declared family"):
        family_for("some_new_shape")


# --- adapting a detector's output ------------------------------------------

def _structural(**overrides) -> StructuralPattern:
    base = {
        "name": "double_top",
        "pattern_class": PatternClass.DETERMINISTIC,
        "state": PatternState.CANDIDATE,
        "recognition_confidence": 80.0,
        "detected_at": END,
        "direction_if_textbook": "BEARISH",
        "key_levels": {"neckline": 95.0, "first_extreme": 100.0},
        "invalidation_level": 101.0,
        "invalidation_rule": "a close above 101 invalidates it",
        "components": {
            "extreme_agreement": 90.0,
            "reaction_depth": 70.0,
            "difference_atr": 0.4,
            "bars_between": 22,
        },
    }
    return StructuralPattern(**{**base, **overrides})


def test_adapter_preserves_the_detector_verdict():
    detection = from_structural(
        _structural(), symbol="BTC", timeframe=Timeframe.H4,
        start_time=START, end_time=END,
    )

    assert detection.recognition_confidence == 80.0
    assert detection.pattern_class is PatternClass.DETERMINISTIC
    assert detection.direction is PatternDirection.BEARISH
    assert detection.invalidation_level == 101.0
    assert detection.breakout_level == 95.0


def test_adapter_separates_score_components_from_raw_measurements():
    """Only the parts that build the score may claim to explain it."""
    detection = from_structural(
        _structural(), symbol="BTC", timeframe=Timeframe.H4,
        start_time=START, end_time=END,
    )

    assert set(detection.confidence_components) == {"extreme_agreement", "reaction_depth"}
    assert detection.metadata["difference_atr"] == 0.4
    assert detection.metadata["bars_between"] == 22
    assert detection.components_explain_confidence()


def test_adapter_keeps_edge_state_untouched():
    """Recognition and edge must never be merged by the transport layer."""
    detection = from_structural(
        _structural(), symbol="BTC", timeframe=Timeframe.H4,
        start_time=START, end_time=END,
    )

    assert detection.edge_state is PatternEdgeState.NOT_YET_TESTED
    assert "not a probability" in detection.to_dict()["separation_note"]


def test_confirmed_at_is_only_set_once_confirmed():
    """detected_at and confirmed_at stay distinct - §15 depends on it."""
    candidate = from_structural(
        _structural(state=PatternState.CANDIDATE, confirmation_time=END),
        symbol="BTC", timeframe=Timeframe.H4, start_time=START, end_time=END,
    )
    confirmed = from_structural(
        _structural(state=PatternState.CONFIRMED, confirmation_time=END),
        symbol="BTC", timeframe=Timeframe.H4, start_time=START, end_time=END,
    )

    assert candidate.confirmed_at is None
    assert candidate.status is PatternStatus.DETECTED
    assert confirmed.confirmed_at == END
    assert confirmed.status is PatternStatus.CONFIRMED


def test_failed_pattern_becomes_invalidated():
    detection = from_structural(
        _structural(state=PatternState.FAILED),
        symbol="BTC", timeframe=Timeframe.H4, start_time=START, end_time=END,
    )

    assert detection.status is PatternStatus.INVALIDATED


def test_full_payload_is_json_serialisable():
    import json

    detection = from_structural(
        _structural(), symbol="BTC", timeframe=Timeframe.H4,
        start_time=START, end_time=END,
        geometry=PatternGeometry(points=[GeometryPoint(START, 100.0, role="first_top")]),
    )
    detection.confirmation_signals = [
        ConfirmationSignal("volume", "relative_volume", SignalVerdict.FAVOURABLE, 71.0),
    ]

    payload = json.loads(json.dumps(detection.to_dict()))

    assert payload["id"] == detection.id
    assert payload["symbol"] == "BTC"
    assert payload["timeframe"] == "4h"
    assert payload["family"] == "REVERSAL"
    assert payload["geometry"]["points"][0]["role"] == "first_top"
    assert payload["available_families"] == ["volume"]

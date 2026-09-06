"""Regression guard: the confirmation flag must be read from the real field.

`detect_history` used to record `getattr(match, "confirmed", False)`, but
`PatternMatch` has no `confirmed` field - it has `confirmation_state`. The
getattr silently returned False for every detection ever recorded, which pinned
`confirmed_share_pct` at 0.0 across the whole study and made `confirmed_only=True`
return an empty result set.

Nothing crashed, so nothing surfaced it. These tests make the same mistake
impossible to reintroduce quietly.
"""

from __future__ import annotations

from crypto_intel.core.enums import ConfirmationState, Direction, Timeframe
from crypto_intel.core.models import PatternMatch


def test_pattern_match_has_no_confirmed_attribute():
    """The field the old code reached for does not exist. It never did."""
    assert "confirmed" not in PatternMatch.model_fields
    assert "confirmation_state" in PatternMatch.model_fields


def test_confirmation_is_read_from_the_state_enum():
    confirmed = PatternMatch(
        pattern="double_top", confidence=80.0, timeframe=Timeframe.D1,
        confirmation_state=ConfirmationState.CONFIRMED, direction=Direction.BEARISH,
    )
    forming = PatternMatch(
        pattern="double_top", confidence=80.0, timeframe=Timeframe.D1,
        confirmation_state=ConfirmationState.FORMING, direction=Direction.BEARISH,
    )

    assert (confirmed.confirmation_state is ConfirmationState.CONFIRMED) is True
    assert (forming.confirmation_state is ConfirmationState.CONFIRMED) is False

    # The shape of the old bug: a default-valued getattr on a field that is not
    # there answers False for both, erasing the distinction entirely.
    assert getattr(confirmed, "confirmed", False) == getattr(forming, "confirmed", False)


def test_invalidated_is_not_counted_as_confirmed():
    invalidated = PatternMatch(
        pattern="double_top", confidence=80.0, timeframe=Timeframe.D1,
        confirmation_state=ConfirmationState.INVALIDATED, direction=Direction.BEARISH,
    )

    assert invalidated.confirmation_state is not ConfirmationState.CONFIRMED


def test_detect_history_records_a_real_confirmation_flag(monkeypatch):
    """A study on synthetic detections must see both True and False."""
    import pandas as pd

    from crypto_intel.core.enums import Asset
    from crypto_intel.research import pattern_validation

    n = 400
    index = pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC")
    frame = pd.DataFrame(
        {
            "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0,
            "volume": 1000.0,
        },
        index=index,
    )
    monkeypatch.setattr(pattern_validation.store, "load_candles", lambda *a, **k: frame)

    calls = {"n": 0}

    class _Detector:
        name = "double_top"

        def detect(self, ctx):
            calls["n"] += 1
            # Alternate so a flag that is always False cannot pass.
            state = (
                ConfirmationState.CONFIRMED if calls["n"] % 2 else ConfirmationState.FORMING
            )
            return PatternMatch(
                pattern="double_top", confidence=80.0, timeframe=Timeframe.D1,
                confirmation_state=state, direction=Direction.BEARISH,
            )

    monkeypatch.setattr(pattern_validation, "all_detectors", lambda: [_Detector()])

    detections = pattern_validation.detect_history(Asset.BTC, Timeframe.D1, step=1)

    assert not detections.empty
    share = detections["confirmed"].mean()
    assert 0.0 < share < 1.0, (
        f"confirmed share is {share}; a share pinned at 0.0 is the original bug"
    )

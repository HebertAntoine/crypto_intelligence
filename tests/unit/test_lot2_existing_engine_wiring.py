from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from crypto_intel.core.enums import Asset
from crypto_intel.core.usability import FamilyState, Freshness
from crypto_intel.engines.future_context import build_five_family_snapshot
from crypto_intel.engines.future_decision import FutureFamily
from crypto_intel.future_events.models import (
    DecisionHorizon,
    DirectionalBias,
    EventImportance,
    EventScheduleType,
    ExpectedMovement,
    FutureEvent,
    FutureEventCategory,
    FutureEventSourceTier,
)

NOW = datetime(2026, 9, 13, 12, tzinfo=UTC)


def _state(name: str) -> FamilyState:
    return FamilyState(
        family=name,
        available=True,
        valid=True,
        freshness=Freshness.RECENT,
        observed_at=NOW,
        source=f"real {name} source",
        points=250,
    )


def _snapshot(**overrides):
    empty = SimpleNamespace(available=False, freshness="UNAVAILABLE", components=[])
    kwargs = {
        "analysis_id": "an_engine_wiring",
        "as_of": NOW,
        "states": {
            "ohlcv_4h": _state("ohlcv_4h"),
            "ohlcv_daily": _state("ohlcv_daily"),
        },
        "events": [],
        "macro_context": {"available": False},
        "liquidity": {"available": False},
        "pressure": empty,
        "institutional_flow": empty,
        "structure": {
            "timeframes": {
                "4h": {"state": "BULLISH_STRUCTURE"},
                "1d": {"state": "BULLISH_STRUCTURE"},
            }
        },
        "regime": SimpleNamespace(regime="UNDETERMINED"),
        "volatility": SimpleNamespace(regime="NORMAL", direction="STABLE"),
        "implied_volatility": empty,
        "expected_volatility": empty,
        "horizon": DecisionHorizon.D7,
    }
    kwargs.update(overrides)
    return build_five_family_snapshot(**kwargs)


def test_expected_volatility_engine_changes_amplitude_but_never_direction() -> None:
    expected = SimpleNamespace(
        available=True,
        squeeze=True,
        expected_movement=ExpectedMovement.HIGH,
        directional_bias=DirectionalBias.NEUTRAL,
    )
    technical = _snapshot(expected_volatility=expected).assessments[
        FutureFamily.TECHNICAL_VOLATILITY
    ]

    assert technical.directional_bias is DirectionalBias.BULLISH
    assert technical.expected_movement is ExpectedMovement.HIGH
    assert any(source["source"] == "ExpectedVolatilityEngine" for source in technical.sources)


def test_geopolitical_engine_is_a_traceable_catalyst_family_input() -> None:
    shock = FutureEvent(
        event_type="CHOKEPOINT_CLOSURE",
        category=FutureEventCategory.GEOPOLITICAL,
        schedule_type=EventScheduleType.UNSCHEDULED,
        title="Verified chokepoint closure",
        source="official maritime authority",
        source_tier=FutureEventSourceTier.A,
        source_url="https://authority.test/notice",
        source_published_at=NOW - timedelta(minutes=5),
        detected_at=NOW - timedelta(minutes=4),
        last_updated=NOW,
        affected_assets=[Asset.BTC],
        importance=EventImportance.CRITICAL,
        directional_effect=DirectionalBias.BEARISH,
        magnitude_effect=ExpectedMovement.HIGH,
        confidence=0.9,
        metadata={"concrete_type": "CHOKEPOINT_CLOSURE"},
    )
    catalyst = _snapshot(events=[shock]).assessments[
        FutureFamily.CATALYSTS_REGULATION
    ]

    assert catalyst.directional_bias is DirectionalBias.BEARISH
    assert catalyst.expected_movement is ExpectedMovement.HIGH
    assert any(source["source"] == "GeopoliticalRiskEngine" for source in catalyst.sources)

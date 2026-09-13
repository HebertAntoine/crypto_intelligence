from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from crypto_intel.core.enums import Asset
from crypto_intel.engines.future_context import build_five_family_snapshot
from crypto_intel.engines.future_decision import FutureDecisionEngine
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


def _event(
    title: str,
    hours: int,
    direction: DirectionalBias,
    *,
    category: FutureEventCategory = FutureEventCategory.MACRO,
    importance: EventImportance = EventImportance.HIGH,
) -> FutureEvent:
    return FutureEvent(
        event_type=title.upper().replace(" ", "_"),
        category=category,
        schedule_type=EventScheduleType.SCHEDULED,
        title=title,
        source="official test source",
        source_tier=FutureEventSourceTier.A,
        source_url="https://example.test/official",
        scheduled_at=NOW + timedelta(hours=hours),
        detected_at=NOW,
        last_updated=NOW,
        affected_assets=[Asset.BTC],
        importance=importance,
        directional_effect=direction,
        magnitude_effect=ExpectedMovement.NORMAL,
        confidence=0.9,
    )


def _families(events, horizon):
    empty = SimpleNamespace(available=False, freshness="UNAVAILABLE", components=[])
    return build_five_family_snapshot(
        analysis_id="an_horizon_test",
        as_of=NOW,
        states={},
        events=events,
        macro_context={"available": False},
        liquidity={"available": False},
        pressure=empty,
        institutional_flow=empty,
        structure={"timeframes": {}},
        regime=SimpleNamespace(regime="UNDETERMINED"),
        volatility=SimpleNamespace(regime="NORMAL", direction="STABLE"),
        implied_volatility=empty,
        expected_volatility=empty,
        horizon=horizon,
    )


def test_horizon_contexts_and_decisions_can_diverge() -> None:
    events = [
        _event("near bullish", 12, DirectionalBias.BULLISH),
        _event(
            "week bearish",
            72,
            DirectionalBias.BEARISH,
            importance=EventImportance.CRITICAL,
        ),
        _event(
            "month bullish",
            20 * 24,
            DirectionalBias.BULLISH,
            importance=EventImportance.CRITICAL,
        ),
        _event(
            "protocol neutral",
            6,
            DirectionalBias.NEUTRAL,
            category=FutureEventCategory.PROTOCOL,
        ),
    ]
    snapshots = {
        horizon: _families(events, horizon)
        for horizon in DecisionHorizon
    }
    decisions = {
        horizon: FutureDecisionEngine().decide(
            Asset.BTC,
            events,
            snapshots[horizon],
            horizon=horizon,
            as_of=NOW,
            analysis_uncertainty=0.2,
        ).decision.value
        for horizon in DecisionHorizon
    }

    assert snapshots[DecisionHorizon.H24] is not snapshots[DecisionHorizon.D7]
    assert snapshots[DecisionHorizon.D7] is not snapshots[DecisionHorizon.D30]
    assert decisions == {
        DecisionHorizon.H24: "BUY",
        DecisionHorizon.D7: "SELL",
        DecisionHorizon.D30: "WAIT",
    }

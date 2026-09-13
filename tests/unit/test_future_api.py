from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from crypto_intel.api import routes_future
from crypto_intel.core.enums import Asset
from crypto_intel.engines.future_decision import (
    FamilyAssessment,
    FiveFamilySnapshot,
    FutureFamily,
)
from crypto_intel.future_events.models import (
    DirectionalBias,
    EventImportance,
    EventScheduleType,
    ExpectedMovement,
    FutureEvent,
    FutureEventCategory,
    FutureEventSourceTier,
    FutureEventStatus,
)
from crypto_intel.main import create_app

NOW = datetime(2026, 9, 13, 12, tzinfo=UTC)


def _event() -> FutureEvent:
    return FutureEvent(
        event_type="FOMC_DECISION",
        category=FutureEventCategory.MONETARY_POLICY,
        schedule_type=EventScheduleType.SCHEDULED,
        title="FOMC monetary policy decision",
        source="Federal Reserve",
        source_tier=FutureEventSourceTier.A,
        source_url="https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
        scheduled_at=NOW + timedelta(hours=36),
        detected_at=NOW - timedelta(hours=2),
        last_updated=NOW - timedelta(hours=2),
        importance=EventImportance.CRITICAL,
        magnitude_effect=ExpectedMovement.HIGH,
        affected_assets=Asset.tradables(),
        confidence=1,
    )


def _families() -> FiveFamilySnapshot:
    return FiveFamilySnapshot.from_partial(
        {
            FutureFamily.MACRO_LIQUIDITY: FamilyAssessment(
                family=FutureFamily.MACRO_LIQUIDITY,
                available=True,
                directional_bias=DirectionalBias.NEUTRAL,
                expected_movement=ExpectedMovement.HIGH,
                confidence=0.9,
                summary="Official monetary-policy event ahead.",
                sources=[
                    {
                        "source": "Federal Reserve",
                        "url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
                    }
                ],
                as_of=NOW.isoformat(),
                freshness="FRESH",
            ),
            FutureFamily.TECHNICAL_VOLATILITY: FamilyAssessment(
                family=FutureFamily.TECHNICAL_VOLATILITY,
                available=True,
                directional_bias=DirectionalBias.STRONGLY_BULLISH,
                expected_movement=ExpectedMovement.NORMAL,
                confidence=0.8,
                summary="Bullish price structure.",
                sources=[{"source": "MarketStructureEngine", "reference": "an_test"}],
                as_of=NOW.isoformat(),
                freshness="FRESH",
            ),
        }
    )


def _snapshot() -> SimpleNamespace:
    return SimpleNamespace(
        asset="BTC",
        analysis_id="an_test",
        analysis_time=NOW,
        price_at_analysis=100_000.0,
        future_events=[_event()],
        future_families=_families(),
        future_horizons={"24h": {}, "7d": {}, "30d": {}},
        uncertainty=SimpleNamespace(score=80),
    )


def test_future_routes_are_in_openapi() -> None:
    paths = create_app().openapi()["paths"]
    assert "/api/future/{symbol}" in paths
    assert "/api/future/{symbol}/why" in paths
    assert "/api/future/{symbol}/timeline" in paths


def test_future_decision_endpoint_contract(monkeypatch) -> None:
    monkeypatch.setattr(routes_future, "context_for", lambda _asset: _snapshot())
    result = routes_future.future_decision("BTC", "7d")

    assert result["decision"] == "WAIT"
    assert result["event_risk"]["active"] is True
    assert result["families"]["total_count"] == 5
    assert len(result["scenarios"]) == 4
    assert result["reasons"][0]["source"] == "Federal Reserve"


def test_why_and_timeline_are_sourced(monkeypatch) -> None:
    monkeypatch.setattr(routes_future, "context_for", lambda _asset: _snapshot())
    why = routes_future.future_why("BTC", "7d")
    timeline = routes_future.future_timeline("BTC", 7)

    assert why["title"] == "Pourquoi attendre ?"
    assert why["reasons"][0]["source_url"].startswith("https://www.federalreserve.gov")
    assert timeline["events"][0]["source_tier"] == "A"
    assert timeline["events"][0]["status"] == "UPCOMING"
    assert timeline["events"][0]["freshness"] != "LIVE"


def test_timeline_excludes_past_unscheduled_release(monkeypatch) -> None:
    snapshot = _snapshot()
    released = _event().model_copy(
        update={
            "schedule_type": EventScheduleType.UNSCHEDULED,
            "scheduled_at": None,
            "status": FutureEventStatus.RELEASED,
            "source_published_at": NOW - timedelta(hours=2),
        }
    )
    snapshot.future_events = [released]
    monkeypatch.setattr(routes_future, "context_for", lambda _asset: snapshot)

    assert routes_future.future_timeline("BTC", 7)["events"] == []

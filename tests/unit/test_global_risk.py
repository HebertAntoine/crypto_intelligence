from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

from crypto_intel.api import routes_global_risk
from crypto_intel.core.enums import Asset
from crypto_intel.engines.future_decision import (
    FamilyAssessment,
    FiveFamilySnapshot,
    FutureFamily,
)
from crypto_intel.engines.global_risk import (
    GlobalRiskEngine,
    GlobalRiskHorizon,
    authorized_events_for_window,
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


def _event(title: str, days: int) -> FutureEvent:
    return FutureEvent(
        event_type="OFFICIAL_CALENDAR_EVENT",
        category=FutureEventCategory.MONETARY_POLICY,
        schedule_type=EventScheduleType.SCHEDULED,
        title=title,
        source="Official authority",
        source_tier=FutureEventSourceTier.A,
        source_url="https://example.gov/calendar",
        detected_at=NOW,
        last_updated=NOW,
        scheduled_at=NOW + timedelta(days=days),
        importance=EventImportance.HIGH,
        magnitude_effect=ExpectedMovement.HIGH,
        affected_assets=[Asset.BTC],
        evidence_ids=[f"evidence-{days}"],
        confidence=1.0,
    )


def _families(
    *,
    available: int = 5,
    movement: ExpectedMovement = ExpectedMovement.NORMAL,
) -> FiveFamilySnapshot:
    partial: dict[FutureFamily, FamilyAssessment] = {}
    for index, family in enumerate(FutureFamily):
        if index >= available:
            break
        partial[family] = FamilyAssessment(
            family=family,
            available=True,
            directional_bias=DirectionalBias.NEUTRAL,
            expected_movement=movement,
            confidence=0.8,
            summary=f"Lecture {family.value}",
            sources=[
                {
                    "source": "Measured source",
                    "reference": f"ref-{family.value}",
                    "evidence_ids": [f"family-{family.value}"],
                }
            ],
            as_of=NOW.isoformat(),
            freshness="FRESH",
        )
    return FiveFamilySnapshot.from_partial(partial)


def _all_keys(value: Any) -> list[str]:
    if isinstance(value, dict):
        return [
            *(str(key) for key in value),
            *(key for item in value.values() for key in _all_keys(item)),
        ]
    if isinstance(value, list):
        return [key for item in value for key in _all_keys(item)]
    return []


def test_three_risk_windows_are_strictly_independent() -> None:
    short = _event("Short event", 3)
    medium = _event("Medium event", 14)
    long = _event("Long event", 45)
    diagnoses = GlobalRiskEngine().assess(
        [short, medium, long],
        {
            GlobalRiskHorizon.SHORT: _families(),
            GlobalRiskHorizon.MEDIUM: _families(),
            GlobalRiskHorizon.LONG: None,
        },
        as_of=NOW,
    )

    by_horizon = {item.horizon: item.to_dict() for item in diagnoses}
    short_ids = by_horizon[GlobalRiskHorizon.SHORT]["evidence_ids"]
    medium_ids = by_horizon[GlobalRiskHorizon.MEDIUM]["evidence_ids"]
    long_ids = by_horizon[GlobalRiskHorizon.LONG]["evidence_ids"]

    assert short.id in short_ids and medium.id not in short_ids and long.id not in short_ids
    assert medium.id in medium_ids and short.id not in medium_ids and long.id not in medium_ids
    assert long.id in long_ids and short.id not in long_ids and medium.id not in long_ids
    assert by_horizon[GlobalRiskHorizon.LONG]["risk_level"] == "INDETERMINATE"
    assert "Long event" in " ".join(by_horizon[GlobalRiskHorizon.LONG]["main_drivers"])


def test_window_boundaries_and_source_authority_are_fail_closed() -> None:
    day_7 = _event("Day seven", 7)
    day_30 = _event("Day thirty", 30)
    day_90 = _event("Day ninety", 90)
    social = _event("Social rumor", 3).model_copy(update={"source_tier": FutureEventSourceTier.E})
    resolved = _event("Resolved entry", 4).model_copy(update={"status": FutureEventStatus.RESOLVED})
    events = [day_7, day_30, day_90, social, resolved]

    short = authorized_events_for_window(events, GlobalRiskHorizon.SHORT, as_of=NOW)
    medium = authorized_events_for_window(events, GlobalRiskHorizon.MEDIUM, as_of=NOW)
    long = authorized_events_for_window(events, GlobalRiskHorizon.LONG, as_of=NOW)

    assert [event.id for event in short] == [day_7.id]
    assert [event.id for event in medium] == [day_30.id]
    assert [event.id for event in long] == [day_90.id]


def test_risk_contract_contains_no_probability() -> None:
    payload = [
        item.to_dict()
        for item in GlobalRiskEngine().assess(
            [_event("Short event", 2)],
            {
                GlobalRiskHorizon.SHORT: _families(movement=ExpectedMovement.HIGH),
                GlobalRiskHorizon.MEDIUM: _families(),
                GlobalRiskHorizon.LONG: None,
            },
            as_of=NOW,
        )
    ]

    assert not [key for key in _all_keys(payload) if "probability" in key.lower()]
    assert payload[0]["risk_level"] == "HIGH"


def test_insufficient_family_data_fails_closed() -> None:
    diagnoses = GlobalRiskEngine().assess(
        [],
        {
            GlobalRiskHorizon.SHORT: _families(available=2),
            GlobalRiskHorizon.MEDIUM: _families(available=2),
            GlobalRiskHorizon.LONG: None,
        },
        as_of=NOW,
    )

    assert all(item.risk_level.value == "INDETERMINATE" for item in diagnoses)
    assert diagnoses[0].data_coverage.status == "INSUFFICIENT"
    assert diagnoses[0].data_coverage.available_families == [
        FutureFamily.MACRO_LIQUIDITY.value,
        FutureFamily.CATALYSTS_REGULATION.value,
    ]


def test_available_family_without_source_or_amplitude_does_not_count() -> None:
    families = _families()
    for family in list(FutureFamily)[:3]:
        item = families.assessments[family]
        item.sources = []
        item.expected_movement = None

    diagnosis = GlobalRiskEngine().assess(
        [],
        {
            GlobalRiskHorizon.SHORT: families,
            GlobalRiskHorizon.MEDIUM: _families(),
            GlobalRiskHorizon.LONG: None,
        },
        as_of=NOW,
    )[0]

    assert diagnosis.risk_level.value == "INDETERMINATE"
    assert diagnosis.data_coverage.status == "INSUFFICIENT"
    assert diagnosis.data_coverage.available_families == [family.value for family in FutureFamily]
    assert diagnosis.data_coverage.usable_families == [
        FutureFamily.POSITIONING_DERIVATIVES.value,
        FutureFamily.TECHNICAL_VOLATILITY.value,
    ]


def test_event_driver_names_affected_assets() -> None:
    diagnosis = GlobalRiskEngine().assess(
        [_event("Asset-specific event", 3)],
        {
            GlobalRiskHorizon.SHORT: _families(),
            GlobalRiskHorizon.MEDIUM: _families(),
            GlobalRiskHorizon.LONG: None,
        },
        as_of=NOW,
    )[0]

    assert "actifs affectés: BTC" in diagnosis.main_drivers[0]


def test_global_risk_api_exposes_exact_contract(monkeypatch) -> None:
    snapshot = SimpleNamespace(
        asset="BTC",
        analysis_id="an_global_risk",
        analysis_time=NOW,
        future_events=[],
    )
    events = [_event("Short event", 2), _event("Medium event", 20), _event("Long event", 60)]
    monkeypatch.setattr(routes_global_risk, "context_for", lambda _asset: snapshot)
    monkeypatch.setattr(
        routes_global_risk.repo,
        "list_future_events",
        lambda **_kwargs: events,
    )
    monkeypatch.setattr(
        routes_global_risk,
        "_family_snapshot",
        lambda _snapshot, _events, _horizon: _families(),
    )

    payload = routes_global_risk.global_risk("BTC")

    assert [item["horizon"] for item in payload["risk_horizons"]] == [
        "1-7d",
        "8-30d",
        "31-90d",
    ]
    required = {
        "risk_level",
        "horizon",
        "assessment_time",
        "data_coverage",
        "main_drivers",
        "counter_signals",
        "change_since_previous",
        "evidence_ids",
        "invalidation_conditions",
    }
    assert all(set(item) == required for item in payload["risk_horizons"])
    assert not [key for key in _all_keys(payload) if "probability" in key.lower()]
    assert "/api/future/{symbol}/global-risk" in create_app().openapi()["paths"]

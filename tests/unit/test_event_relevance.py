"""Sections 12-14: the same event does not hit three assets equally."""

from datetime import UTC, datetime, timedelta

from crypto_intel.core.enums import Asset
from crypto_intel.engines.event_relevance import (
    AssetImpact,
    EventRelevanceEngine,
    asset_impact,
)
from crypto_intel.future_events.models import (
    EventImportance,
    EventScheduleType,
    ExpectedMovement,
    FutureEvent,
    FutureEventCategory,
    FutureEventSourceTier,
)

NOW = datetime(2026, 9, 14, 12, tzinfo=UTC)


def event(
    category: FutureEventCategory,
    *,
    importance: EventImportance = EventImportance.HIGH,
    tier: FutureEventSourceTier = FutureEventSourceTier.A,
    assets: list[Asset] | None = None,
    hours: int = 48,
    title: str = "Événement",
) -> FutureEvent:
    return FutureEvent(
        event_type="TEST",
        category=category,
        schedule_type=EventScheduleType.SCHEDULED,
        title=title,
        source="source officielle",
        source_tier=tier,
        source_url="https://example.org/",
        importance=importance,
        magnitude_effect=ExpectedMovement.HIGH,
        scheduled_at=NOW + timedelta(hours=hours),
        detected_at=NOW,
        affected_assets=assets or [],
    )


# --- section 12: impact per asset -------------------------------------------


def test_monetary_policy_reaches_every_asset_through_the_same_channel() -> None:
    fomc = event(FutureEventCategory.MONETARY_POLICY, importance=EventImportance.CRITICAL)
    impacts = {asset: asset_impact(fomc, asset) for asset in (Asset.BTC, Asset.ETH, Asset.SOL)}
    assert set(impacts.values()) == {AssetImpact.HIGH}


def test_regulation_lands_harder_on_smart_contract_networks() -> None:
    rule = event(FutureEventCategory.REGULATION)
    assert asset_impact(rule, Asset.BTC) is AssetImpact.MEDIUM
    assert asset_impact(rule, Asset.ETH) is AssetImpact.HIGH
    assert asset_impact(rule, Asset.SOL) is AssetImpact.HIGH


def test_an_event_naming_one_asset_is_trusted_on_that_point() -> None:
    """A Solana ETF decision says which network it concerns better than a table."""

    sol_etf = event(FutureEventCategory.ETF, assets=[Asset.SOL], title="ETF SOL")
    assert asset_impact(sol_etf, Asset.SOL) is AssetImpact.VERY_HIGH
    assert asset_impact(sol_etf, Asset.BTC) is AssetImpact.LOW


def test_a_protocol_event_does_not_touch_another_network() -> None:
    upgrade = event(FutureEventCategory.PROTOCOL, assets=[Asset.ETH])
    assert asset_impact(upgrade, Asset.ETH) is AssetImpact.VERY_HIGH
    assert asset_impact(upgrade, Asset.BTC) is AssetImpact.NONE


def test_the_same_event_is_never_applied_identically_by_default() -> None:
    rule = event(FutureEventCategory.REGULATION)
    assert len({asset_impact(rule, a) for a in (Asset.BTC, Asset.ETH, Asset.SOL)}) > 1


# --- section 13: relevance score --------------------------------------------


def test_a_critical_imminent_primary_event_scores_high() -> None:
    result = EventRelevanceEngine().score(
        event(FutureEventCategory.MONETARY_POLICY, importance=EventImportance.CRITICAL, hours=24),
        Asset.BTC,
        now=NOW,
    )
    assert result.score >= 75
    assert result.impact is AssetImpact.HIGH


def test_a_minor_distant_event_scores_low() -> None:
    result = EventRelevanceEngine().score(
        event(FutureEventCategory.ENERGY, importance=EventImportance.LOW, hours=24 * 40),
        Asset.SOL,
        now=NOW,
    )
    assert result.score < EventRelevanceEngine.DISPLAY_FLOOR


def test_a_social_source_scores_zero_and_can_never_outrank_a_calendar() -> None:
    social = EventRelevanceEngine().score(
        event(
            FutureEventCategory.REGULATION,
            importance=EventImportance.CRITICAL,
            tier=FutureEventSourceTier.E,
            hours=12,
        ),
        Asset.ETH,
        now=NOW,
    )
    assert social.score == 0
    assert social.may_decide is False


def test_the_score_never_claims_to_be_a_probability() -> None:
    payload = EventRelevanceEngine().score(
        event(FutureEventCategory.MACRO), Asset.BTC, now=NOW
    ).to_dict()
    assert "pas une probabilité" in payload["usage"]
    assert "direction" not in payload


def test_proximity_raises_the_score_of_an_otherwise_identical_event() -> None:
    engine = EventRelevanceEngine()
    near = engine.score(event(FutureEventCategory.MACRO, hours=12), Asset.BTC, now=NOW)
    far = engine.score(event(FutureEventCategory.MACRO, hours=24 * 25), Asset.BTC, now=NOW)
    assert near.score > far.score


# --- section 14: only a few events reach the screen -------------------------


def test_only_the_most_relevant_events_are_surfaced() -> None:
    events = [
        event(FutureEventCategory.MONETARY_POLICY, importance=EventImportance.CRITICAL, hours=24),
        event(FutureEventCategory.REGULATION, importance=EventImportance.HIGH, hours=48),
        event(FutureEventCategory.MACRO, importance=EventImportance.MEDIUM, hours=72),
        *[
            event(FutureEventCategory.ENERGY, importance=EventImportance.LOW, hours=24 * 35)
            for _ in range(12)
        ],
    ]
    top = EventRelevanceEngine().top(events, Asset.ETH, limit=3, now=NOW)
    assert len(top) == 3
    assert top[0].score >= top[1].score >= top[2].score


def test_discovery_only_events_never_reach_the_surfaced_list() -> None:
    events = [
        event(
            FutureEventCategory.REGULATION,
            importance=EventImportance.CRITICAL,
            tier=FutureEventSourceTier.E,
            hours=6,
        ),
        event(FutureEventCategory.MACRO, importance=EventImportance.MEDIUM, hours=48),
    ]
    top = EventRelevanceEngine().top(events, Asset.BTC, limit=3, now=NOW)
    assert all(item.may_decide for item in top)
    assert len(top) == 1


def test_a_credible_source_does_not_make_an_irrelevant_event_relevant() -> None:
    """Credibility scales relevance; it never creates it."""

    engine = EventRelevanceEngine()
    minor = event(FutureEventCategory.ENERGY, importance=EventImportance.LOW, hours=24 * 40)
    official = engine.score(minor, Asset.SOL, now=NOW)
    assert official.score < EventRelevanceEngine.DISPLAY_FLOOR

    # The same event from a less authoritative source scores lower still,
    # never higher.
    press = engine.score(
        event(
            FutureEventCategory.ENERGY,
            importance=EventImportance.LOW,
            tier=FutureEventSourceTier.C,
            hours=24 * 40,
        ),
        Asset.SOL,
        now=NOW,
    )
    assert press.score <= official.score


def test_the_reasons_always_name_the_source_level() -> None:
    result = EventRelevanceEngine().score(
        event(FutureEventCategory.MACRO), Asset.BTC, now=NOW
    )
    assert any("source de niveau" in reason for reason in result.reasons)

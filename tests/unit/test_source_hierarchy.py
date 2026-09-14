"""Sections 11-14, 49 and 50: who may decide, and who may only point.

The rule these tests defend: a social post can tell us *what to look at*. It can
never tell us *what is true*. Section 50 adds a second one - a procedural vote
is not a law.
"""

from datetime import UTC, datetime, timedelta

import pytest

from crypto_intel.engines.future_context import usable_events_for_horizon
from crypto_intel.engines.source_hierarchy import (
    MAX_PRODUCTION_TIER,
    ProductionSourceError,
    SocialDiscoveryLayer,
    SourceTier,
    VerificationStatus,
    assert_production_source,
    filter_production_events,
    may_influence_decision,
    tier_of,
)
from crypto_intel.future_events.models import (
    DecisionHorizon,
    EventImportance,
    EventScheduleType,
    ExpectedMovement,
    FutureEvent,
    FutureEventCategory,
    FutureEventSourceTier,
)

NOW = datetime(2026, 9, 14, 12, tzinfo=UTC)


def event(tier: FutureEventSourceTier, *, title: str = "Événement") -> FutureEvent:
    return FutureEvent(
        event_type="TEST",
        category=FutureEventCategory.REGULATION,
        schedule_type=EventScheduleType.SCHEDULED,
        title=title,
        source="test",
        source_tier=tier,
        source_url="https://example.org/",
        importance=EventImportance.HIGH,
        magnitude_effect=ExpectedMovement.HIGH,
        scheduled_at=NOW + timedelta(hours=30),
        detected_at=NOW,
    )


# --- section 14: the ladder -------------------------------------------------


def test_the_hierarchy_is_ordered_from_most_to_least_authoritative() -> None:
    assert SourceTier.PRIMARY < SourceTier.SPECIALIZED < SourceTier.PRESS < SourceTier.SOCIAL
    assert MAX_PRODUCTION_TIER is SourceTier.PRESS


def test_each_event_tier_maps_to_its_place_in_the_hierarchy() -> None:
    assert tier_of(FutureEventSourceTier.A) is SourceTier.PRIMARY
    assert tier_of(FutureEventSourceTier.B) is SourceTier.SPECIALIZED
    assert tier_of(FutureEventSourceTier.C) is SourceTier.PRESS
    assert tier_of(FutureEventSourceTier.E) is SourceTier.SOCIAL


def test_an_unknown_tier_is_treated_as_social_not_as_primary() -> None:
    """Defaulting an unrecognised source to trustworthy would invert the rule."""

    assert tier_of("something-else") is SourceTier.SOCIAL
    assert tier_of(None) is SourceTier.SOCIAL


# --- section 49: social may never decide ------------------------------------


def test_social_tier_can_never_influence_a_decision() -> None:
    assert may_influence_decision(FutureEventSourceTier.A) is True
    assert may_influence_decision(FutureEventSourceTier.C) is True
    assert may_influence_decision(FutureEventSourceTier.E) is False


def test_using_a_social_source_as_a_production_input_raises() -> None:
    assert_production_source(FutureEventSourceTier.A, what="FOMC")
    with pytest.raises(ProductionSourceError, match="source sociale"):
        assert_production_source(FutureEventSourceTier.E, what="rumeur de vote")


def test_social_events_are_dropped_before_reaching_a_decision() -> None:
    """The regression this closes: tier E was labelled and then flowed on."""

    events = [
        event(FutureEventSourceTier.A, title="Vote officiel"),
        event(FutureEventSourceTier.E, title="Rumeur sur X"),
    ]
    usable = usable_events_for_horizon(events, DecisionHorizon.D7, NOW)
    titles = {item.title for item in usable}
    assert "Vote officiel" in titles
    assert "Rumeur sur X" not in titles


def test_filtering_keeps_the_discovery_items_visible_separately() -> None:
    """Dropped is not deleted: the topic stays available as something to check."""

    usable, discovery = filter_production_events(
        [event(FutureEventSourceTier.A), event(FutureEventSourceTier.E)]
    )
    assert len(usable) == 1
    assert len(discovery) == 1


# --- sections 11-13: discovery layer ----------------------------------------


def test_the_discovery_layer_is_declared_discovery_only() -> None:
    assert SocialDiscoveryLayer.status == "DISCOVERY_ONLY"


def test_discovery_extracts_themes_not_values() -> None:
    topics = SocialDiscoveryLayer().discover(
        [
            {"handle": "@analyst", "text": "Vote crypto au Sénat mardi, énorme"},
            {"handle": "@other", "text": "Le Brent explose à 108$"},
        ],
        now=NOW,
    )
    categories = {item.category for item in topics}
    assert "REGULATION" in categories
    assert "ENERGY" in categories
    # No numeric field exists at all, so a figure read in a post cannot be
    # mistaken for one the system holds.
    for item in topics:
        assert not hasattr(item, "value")
        assert item.status == "DISCOVERY_ONLY"
        assert item.verification is VerificationStatus.UNVERIFIED


def test_an_unverified_topic_can_never_become_an_event() -> None:
    topics = SocialDiscoveryLayer().discover(
        [{"handle": "@a", "text": "vote SEC demain"}], now=NOW
    )
    assert topics
    assert all(not item.may_become_an_event for item in topics)


def test_verification_requires_a_real_source() -> None:
    layer = SocialDiscoveryLayer()
    topic = layer.discover([{"handle": "@a", "text": "vote au Sénat"}], now=NOW)[0]

    rejected = layer.verify(topic, primary_source=None)
    assert rejected.verification is VerificationStatus.REJECTED
    assert not rejected.may_become_an_event

    verified = layer.verify(
        topic,
        primary_source="US Senate Banking Committee",
        primary_url="https://www.banking.senate.gov/hearings",
    )
    assert verified.verification is VerificationStatus.VERIFIED
    assert verified.may_become_an_event
    assert verified.verified_url.startswith("https://")


def test_a_verified_topic_is_still_marked_discovery_only() -> None:
    """Verification promotes the topic; it does not turn the post into a source."""

    layer = SocialDiscoveryLayer()
    topic = layer.discover([{"handle": "@a", "text": "cpi vendredi"}], now=NOW)[0]
    verified = layer.verify(topic, primary_source="BLS")
    assert verified.status == "DISCOVERY_ONLY"
    assert "n'alimente aucune décision" in verified.to_dict()["usage"]


def test_noise_outside_the_watched_themes_is_ignored() -> None:
    topics = SocialDiscoveryLayer().discover(
        [{"handle": "@a", "text": "bonjour tout le monde"}], now=NOW
    )
    assert topics == []

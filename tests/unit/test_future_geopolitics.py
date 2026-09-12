from __future__ import annotations

from datetime import UTC, datetime

from crypto_intel.engines.geopolitics import GeopoliticalRiskEngine
from crypto_intel.providers.events.geopolitical_news import geopolitical_items_to_events

NOW = datetime(2028, 9, 10, 12, tzinfo=UTC)


def _item(title: str, *, source: str = "Reuters", tier: int = 2):
    return {
        "title": title,
        "summary": "",
        "url": "https://example.com/source-backed-event",
        "published_at": datetime(2028, 9, 10, 10, tzinfo=UTC),
        "source": source,
        "tier": tier,
    }


def test_generic_fear_headline_does_not_become_a_concrete_event():
    events = geopolitical_items_to_events(
        [_item("Markets fear geopolitical uncertainty may worsen")], fetched_at=NOW
    )

    assert events == []
    analysis = GeopoliticalRiskEngine().analyze(events)
    assert analysis.available is False
    assert analysis.directional_bias.value == "NEUTRAL"


def test_energy_attack_has_explicit_causal_chain_and_risk_not_certainty():
    events = geopolitical_items_to_events(
        [_item("Strike hit major oil terminal and halted exports")], fetched_at=NOW
    )
    analysis = GeopoliticalRiskEngine().analyze(events)

    assert len(events) == 1
    assert events[0].metadata["concrete_type"] == "ENERGY_INFRASTRUCTURE_ATTACK"
    assert events[0].causal_chain[0] == "Infrastructure énergétique attaquée"
    assert analysis.available is True
    assert analysis.directional_bias.value == "BEARISH"
    assert analysis.expected_movement.value == "HIGH"
    assert "never a certain" in analysis.explanation.lower()
    assert analysis.provenance[0]["source_url"]


def test_ceasefire_and_opec_change_do_not_collapse_into_one_signal():
    events = geopolitical_items_to_events(
        [
            _item("Governments signed a ceasefire agreement"),
            _item("OPEC announces production increase for next month"),
        ],
        fetched_at=NOW,
    )

    assert len(events) == 2
    assert {event.metadata["concrete_type"] for event in events} == {
        "CEASEFIRE",
        "OPEC_PRODUCTION_CHANGE",
    }


def test_discovery_tier_cannot_masquerade_as_primary_source():
    event = geopolitical_items_to_events(
        [_item("Strike hit oil refinery", source="Social account", tier=4)],
        fetched_at=NOW,
    )[0]

    assert event.source_tier.value == "E"
    assert event.confidence == 0.2

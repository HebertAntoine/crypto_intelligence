"""La décision est déterministe, et « pas de preuve » n'est pas « non ».

Le défaut que ces tests verrouillent: l'écran répondait NON dès qu'aucun
avantage statistique n'était démontré. NO_MEASURABLE_EDGE veut dire que rien
n'a été prouvé, pas que le prix va baisser. Un marché fortement haussier sans
edge appelle ATTENDRE.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from crypto_intel.core.enums import Asset
from crypto_intel.engines.buy_opportunity import (
    BuyOpportunityState,
    Polarity,
    decide,
)


def _entry(state: str, factors=None, missing=None, score: float = 0.0):
    return SimpleNamespace(
        state=SimpleNamespace(value=state),
        score=score,
        factors=factors or [],
        missing=missing or [],
        invalidation="",
    )


def _factor(name: str, contribution: float, detail: str = ""):
    return SimpleNamespace(name=name, contribution=contribution, detail=detail)


def _edge(state: str = "NO_MEASURABLE_EDGE", admitted: int = 0, rejected: int = 3):
    return SimpleNamespace(
        state=SimpleNamespace(value=state),
        admitted_count=admitted, rejected_count=rejected,
    )


def _uncertainty(score: float = 40.0):
    return SimpleNamespace(score=score, drivers=[])


def _crowding(level: str = "NORMAL"):
    return SimpleNamespace(level=SimpleNamespace(value=level))


def _pressure(components=None):
    return SimpleNamespace(components=components or [])


def _component(name: str, available: bool, score: float | None, label: str = ""):
    return SimpleNamespace(
        name=name, label=label or name, available=available, score=score,
        detail="détail", reason="raison", source="source",
    )


def _decide(**kwargs):
    base = {
        "entry": _entry("NEUTRAL"),
        "edge": _edge(),
        "uncertainty": _uncertainty(),
        "macro_events": [],
        "crowding": _crowding(),
        "pressure": _pressure(),
        "unusable_families": [],
    }
    base.update(kwargs)
    return decide(Asset.BTC, **base)


class TestNoEdgeIsNotNo:
    def test_neutral_entry_without_edge_says_wait_not_unfavourable(self):
        """Le cas observé sur BTC: haussier, neutre, aucun edge."""
        result = _decide()
        assert result.state is BuyOpportunityState.WAIT
        assert result.headline == "ATTENDRE"

    def test_the_absence_of_edge_is_a_wait_factor_not_an_opposing_one(self):
        result = _decide()
        edge_factor = next(f for f in result.factors if f.id == "edge.none")
        assert edge_factor.polarity is Polarity.WAIT
        assert "ne dit pas que le prix va baisser" in edge_factor.explanation

    def test_a_favourable_entry_without_edge_cannot_exceed_watch(self):
        result = _decide(entry=_entry("VERY_FAVORABLE"))
        assert result.state is BuyOpportunityState.WATCH
        assert any("Aucun avantage" in g for g in result.guard_rails_applied)

    def test_a_favourable_entry_with_edge_may_be_an_opportunity(self):
        result = _decide(
            entry=_entry("VERY_FAVORABLE"),
            edge=_edge("POSITIVE_EDGE", admitted=2, rejected=1),
        )
        assert result.state is BuyOpportunityState.STRONG_OPPORTUNITY
        assert result.guard_rails_applied == []


class TestMapping:
    @pytest.mark.parametrize(
        ("entry_state", "expected"),
        [
            ("FAVORABLE", BuyOpportunityState.OPPORTUNITY),
            ("NEUTRAL", BuyOpportunityState.WAIT),
            ("UNFAVORABLE", BuyOpportunityState.UNFAVORABLE),
            ("VERY_UNFAVORABLE", BuyOpportunityState.UNFAVORABLE),
            ("INSUFFICIENT_DATA", BuyOpportunityState.INSUFFICIENT_DATA),
        ],
    )
    def test_entry_state_maps_before_guard_rails(self, entry_state, expected):
        result = _decide(
            entry=_entry(entry_state),
            edge=_edge("POSITIVE_EDGE", admitted=1, rejected=0),
        )
        assert result.state is expected

    def test_insufficient_data_is_never_softened_by_a_guard_rail(self):
        result = _decide(entry=_entry("INSUFFICIENT_DATA"), uncertainty=_uncertainty(90))
        assert result.state is BuyOpportunityState.INSUFFICIENT_DATA


class TestGuardRails:
    def test_high_uncertainty_caps_at_wait(self):
        result = _decide(
            entry=_entry("VERY_FAVORABLE"),
            edge=_edge("POSITIVE_EDGE", admitted=2, rejected=0),
            uncertainty=_uncertainty(75),
        )
        assert result.state is BuyOpportunityState.WAIT
        assert any("Incertitude" in g for g in result.guard_rails_applied)

    def test_extreme_crowding_makes_it_unfavourable(self):
        result = _decide(
            entry=_entry("FAVORABLE"),
            edge=_edge("POSITIVE_EDGE", admitted=1, rejected=0),
            crowding=_crowding("EXTREME"),
        )
        assert result.state is BuyOpportunityState.UNFAVORABLE

    def test_stale_inputs_cap_at_wait(self):
        result = _decide(
            entry=_entry("VERY_FAVORABLE"),
            edge=_edge("POSITIVE_EDGE", admitted=2, rejected=0),
            unusable_families=["funding", "open_interest"],
        )
        assert result.state is BuyOpportunityState.WAIT

    def test_a_guard_rail_only_ever_lowers_the_state(self):
        """Aucun garde-fou ne doit rendre la lecture plus favorable."""
        without = _decide(entry=_entry("UNFAVORABLE"), edge=_edge("POSITIVE_EDGE", 1, 0))
        with_guards = _decide(
            entry=_entry("UNFAVORABLE"), edge=_edge("POSITIVE_EDGE", 1, 0),
            uncertainty=_uncertainty(90), crowding=_crowding("EXTREME"),
        )
        assert without.state is BuyOpportunityState.UNFAVORABLE
        assert with_guards.state is BuyOpportunityState.UNFAVORABLE


class TestMacro:
    def test_an_imminent_critical_event_forces_wait_and_appears(self):
        result = _decide(
            entry=_entry("VERY_FAVORABLE"),
            edge=_edge("POSITIVE_EDGE", admitted=2, rejected=0),
            macro_events=[{
                "kind": "FOMC", "name": "FOMC Rate Decision",
                "importance": "CRITICAL", "hours_until": 18.0,
                "scheduled_at": "2026-09-16T18:00:00+00:00",
            }],
        )
        assert result.state is BuyOpportunityState.WAIT
        fomc = next(f for f in result.factors if "FOMC" in f.title)
        assert fomc.polarity is Polarity.WAIT
        assert fomc.importance >= 80

    def test_no_event_means_no_macro_factor_at_all(self):
        """Rien ne doit évoquer la Fed si le calendrier est vide."""
        result = _decide(macro_events=[])
        text = " ".join(f"{f.title} {f.explanation}" for f in result.factors)
        for interdit in ("FOMC", "Fed", "CPI"):
            assert interdit not in text

    def test_a_past_event_is_ignored(self):
        result = _decide(macro_events=[{
            "kind": "FOMC", "name": "FOMC", "importance": "CRITICAL",
            "hours_until": -5.0, "scheduled_at": "2026-09-01T18:00:00+00:00",
        }])
        assert not any("FOMC" in f.title for f in result.factors)

    def test_a_distant_event_does_not_force_waiting(self):
        result = _decide(
            entry=_entry("FAVORABLE"),
            edge=_edge("POSITIVE_EDGE", admitted=1, rejected=0),
            macro_events=[{
                "kind": "CPI", "name": "US CPI", "importance": "CRITICAL",
                "hours_until": 200.0, "scheduled_at": "2026-09-16T12:30:00+00:00",
            }],
        )
        assert result.state is BuyOpportunityState.OPPORTUNITY


class TestWhales:
    def test_an_unavailable_provider_is_missing_never_a_direction(self):
        result = _decide(pressure=_pressure([
            _component("baleines", available=False, score=None,
                       label="Baleines (gros portefeuilles)"),
        ]))
        whales = next(f for f in result.factors if "Baleines" in f.title)
        assert whales.polarity is Polarity.MISSING
        assert whales.available is False

        text = " ".join(f"{f.title} {f.explanation}" for f in result.factors)
        for interdit in ("baleines vendeuses", "baleines acheteuses"):
            assert interdit not in text.lower()

    def test_a_missing_component_never_counts_as_neutral_support(self):
        result = _decide(pressure=_pressure([
            _component("baleines", available=False, score=None, label="Baleines"),
        ]))
        assert not any(
            f.polarity is Polarity.SUPPORTS and "Baleines" in f.title
            for f in result.factors
        )


class TestExplanation:
    def test_the_measured_edge_stays_visible_even_when_favourable(self):
        result = _decide(
            entry=_entry("FAVORABLE"),
            edge=_edge("POSITIVE_EDGE", admitted=1, rejected=2),
        )
        assert result.measured_edge_state == "POSITIVE_EDGE"

    def test_the_payload_separates_positives_waits_negatives_and_missing(self):
        payload = _decide(pressure=_pressure([
            _component("institutions", available=True, score=60.0, label="ETF"),
            _component("baleines", available=False, score=None, label="Baleines"),
        ])).to_dict()
        assert payload["positives"] and payload["waits"] and payload["missing"]
        assert "disclaimer" in payload
        assert "pas une garantie" in payload["disclaimer"]

    def test_what_would_change_the_reading_is_never_empty_when_waiting(self):
        result = _decide(entry=_entry("NEUTRAL", factors=[
            _factor("structural location", -25.0, "près du haut du range"),
        ]))
        assert result.what_would_improve

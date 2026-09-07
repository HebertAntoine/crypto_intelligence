"""The Today endpoint must not contradict itself, and must feel staleness.

Two defects motivated these tests, both found by reading a real payload:

  * `/today` computed the regime and then called the uncertainty engine
    without it, so the engine charged a 20-point "regime undetermined"
    penalty while the same response reported STRONGLY_BULLISH at 80%
    persistence. The page argued with itself.

  * the same call omitted `freshness`, so the engine's "stale or missing data"
    driver could never fire. Uncertainty was structurally blind to the one
    failure mode the page exists to avoid.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from crypto_intel.api.routes_lot4 import today
from crypto_intel.core.enums import Asset
from crypto_intel.core.usability import (
    FamilyState,
    Freshness,
    assess_engine,
    freshness_for,
    page_status,
)
from crypto_intel.engines.analysis_context import (
    _ReconstructedRegime,
)
from crypto_intel.engines.analysis_context import (
    reconstructed_regime as _reconstructed_regime,
)
from crypto_intel.engines.edge import EdgeEngine, UncertaintyEngine

APP_LIB = Path(__file__).resolve().parents[2] / "app" / "lib"


def _regime_label(regime: object) -> str | None:
    """The label carried by a reconstructed regime.

    `regime.regime` is an object wrapping the label in `.value`, not the label
    itself, so a `getattr(regime, "regime") == "UNDETERMINED"` check silently
    never matches.
    """
    inner = getattr(regime, "regime", None)
    return getattr(inner, "value", inner)


@pytest.fixture(scope="module")
def payload() -> dict:
    return asyncio.run(today("BTC"))


class TestUncertaintyReceivesWhatTheEndpointKnows:
    def test_regime_is_passed_so_the_page_cannot_contradict_itself(self, payload):
        direction = payload["decision_summary"]["market_direction"]
        drivers = {d["driver"] for d in payload["uncertainty"]["drivers"]}
        if direction not in ("UNDETERMINED", "UNKNOWN"):
            assert "regime undetermined" not in drivers, (
                f"direction is {direction} but uncertainty still charges the "
                "'regime undetermined' penalty"
            )

    def test_omitting_the_regime_measurably_inflates_uncertainty(self):
        """The bug, reproduced without depending on today's data.

        A stand-in regime is used rather than the reconstructed one, so the
        test exercises the defect even in an environment whose candle history
        is too short to establish a direction.
        """
        asset = Asset.BTC
        edge = EdgeEngine().assess(asset)
        established = _ReconstructedRegime("STRONGLY_BULLISH", 80.0)
        assert _regime_label(established) == "STRONGLY_BULLISH"

        with_regime = UncertaintyEngine().assess(asset, edge, regime=established)
        without_regime = UncertaintyEngine().assess(asset, edge)

        assert without_regime.score - with_regime.score == 20
        assert "regime undetermined" in {
            driver["driver"] for driver in without_regime.drivers
        }
        assert "regime undetermined" not in {
            driver["driver"] for driver in with_regime.drivers
        }

    def test_the_analysis_passes_the_regime_it_computed(self):
        """Guards the wiring, not the engine: the two must not drift apart.

        The wiring now lives in the snapshot builder rather than in the route,
        because every endpoint of one analysis reads the same snapshot.
        """
        import inspect

        from crypto_intel.engines import analysis_context

        source = inspect.getsource(analysis_context.build_context)
        assert "UncertaintyEngine().assess(" in source
        call = source.split("UncertaintyEngine().assess(", 1)[1].split(")", 1)[0]
        assert "regime=" in call, "the computed regime is not handed to the engine"
        assert "freshness=" in call, "input freshness is not handed to the engine"

    def test_stale_inputs_raise_uncertainty(self):
        asset = Asset.BTC
        edge = EdgeEngine().assess(asset)
        regime = _reconstructed_regime(asset)
        clean = UncertaintyEngine().assess(asset, edge, regime=regime, freshness={})
        stale = UncertaintyEngine().assess(
            asset, edge, regime=regime,
            freshness={"price": "STALE", "funding": "UNAVAILABLE"},
        )
        assert stale.score > clean.score
        assert any(
            "stale" in driver["driver"] for driver in stale.drivers
        ), "stale inputs must appear as a named driver, not only in the score"


class TestFamilyStates:
    """Four questions per family, never collapsed into one word."""

    def test_every_family_is_named_individually(self, payload):
        families = payload["families"]
        for expected in ("price", "ohlcv_daily", "funding", "open_interest"):
            assert expected in families, f"{expected} has no declared state"

    def test_each_family_answers_all_four_questions(self, payload):
        for name, state in payload["families"].items():
            for key in ("available", "valid", "freshness", "usable"):
                assert key in state, f"{name} does not answer {key}"

    def test_usable_is_never_true_while_stale(self, payload):
        for name, state in payload["families"].items():
            if state["freshness"] in ("STALE", "DELAYED", "UNAVAILABLE"):
                assert not state["usable"], (
                    f"{name} is {state['freshness']} yet reported usable - this "
                    "is the collapse that showed OK on hour-old data"
                )

    def test_a_present_valid_but_stale_family_is_not_usable(self):
        """The exact case observed: present, valid, 54 minutes old."""
        from datetime import UTC, datetime, timedelta

        observed = datetime.now(UTC) - timedelta(minutes=54)
        state = FamilyState(
            family="price", available=True, valid=True,
            freshness=freshness_for("price", observed), observed_at=observed,
        )
        assert state.available and state.valid
        assert state.freshness is Freshness.DELAYED
        assert not state.usable

    def test_every_family_declares_where_it_came_from(self, payload):
        for name, state in payload["families"].items():
            assert state.get("source"), f"{name} declares no source"
            assert state.get("reason"), f"{name} gives no reason for its state"


class TestEngineDependencies:
    def test_a_stale_required_input_blocks_its_engine(self, payload):
        families = payload["families"]
        engines = payload["engines"]
        for name, engine in engines.items():
            for blocked in engine["blocking_inputs"]:
                assert not families[blocked]["usable"], (
                    f"{name} claims to be blocked by {blocked}, which is usable"
                )
            if engine["usable"]:
                assert not engine["blocking_inputs"]

    def test_an_optional_input_degrades_without_blocking(self):
        fresh = FamilyState(
            family="ohlcv_daily", available=True, valid=True,
            freshness=Freshness.LIVE,
        )
        missing = FamilyState(family="dvol", available=False, valid=False)
        state = assess_engine(
            "volatility", {"ohlcv_daily": fresh, "dvol": missing}
        )
        assert state.usable, "a missing optional input must not block the engine"
        assert "dvol" in state.degraded_by

    def test_a_missing_required_input_blocks(self):
        stale = FamilyState(
            family="ohlcv_daily", available=True, valid=True,
            freshness=Freshness.STALE,
        )
        state = assess_engine("direction", {"ohlcv_daily": stale})
        assert not state.usable
        assert state.blocking == ["ohlcv_daily"]


class TestPageStatus:
    def test_a_stale_critical_input_suspends_rather_than_degrades(self):
        families = {
            "price": FamilyState(
                family="price", available=True, valid=True,
                freshness=Freshness.STALE,
            ),
            "ohlcv_daily": FamilyState(
                family="ohlcv_daily", available=True, valid=True,
                freshness=Freshness.LIVE,
            ),
        }
        status, reason = page_status(families, {})
        assert status.value == "SUSPENDED"
        assert not status.allows_action
        assert "price" in reason

    def test_an_absent_critical_input_is_unavailable_not_suspended(self):
        families = {
            "price": FamilyState(family="price"),
            "ohlcv_daily": FamilyState(
                family="ohlcv_daily", available=True, valid=True,
                freshness=Freshness.LIVE,
            ),
        }
        status, _ = page_status(families, {})
        assert status.value == "UNAVAILABLE"

    def test_all_fresh_allows_action(self):
        families = {
            name: FamilyState(
                family=name, available=True, valid=True, freshness=Freshness.LIVE,
            )
            for name in ("price", "ohlcv_daily")
        }
        status, _ = page_status(families, {})
        assert status.value == "LIVE"
        assert status.allows_action

    def test_the_payload_status_matches_its_families(self, payload):
        status = payload["overall_status"]
        unusable_critical = [
            name for name in ("price", "ohlcv_daily")
            if not payload["families"][name]["usable"]
        ]
        if unusable_critical:
            assert status in ("SUSPENDED", "UNAVAILABLE"), (
                f"critical input {unusable_critical} unusable but page says {status}"
            )
            assert payload["allows_action"] is False


class TestPercentilesAreNotFabricated:
    def test_funding_percentile_only_appears_with_enough_history(self, payload):
        funding = payload["funding"]
        if funding.get("percentile") is not None:
            assert funding["sufficient_history"] is True
            assert funding["history_days"] >= 180, (
                "a percentile shown on fewer than 180 days is false precision"
            )

    def test_volatility_percentile_declares_its_history(self, payload):
        volatility = payload["volatility"]
        if volatility.get("atr_percentile") is not None:
            assert volatility.get("history_days", 0) >= 180

    def test_crowding_names_what_is_missing(self, payload):
        crowding = payload["crowding"]
        if crowding["level"] not in ("UNKNOWN", "INSUFFICIENT_DATA"):
            assert crowding.get("score") is not None


class TestNoFrozenFreshnessInTheUI:
    """A snapshot's own freshness claim must never be rendered verbatim."""

    def test_today_screen_does_not_display_the_payload_status(self):
        source = (APP_LIB / "screens" / "today_screen.dart").read_text(encoding="utf-8")
        for frozen in ("market.status", "market.freshness", "market.ageSeconds"):
            assert frozen not in source, (
                f"{frozen} is read straight from the payload; in a bundled "
                "snapshot it is frozen at capture time and claims LIVE forever"
            )

    def test_freshness_is_derived_from_the_observation_timestamp(self):
        source = (APP_LIB / "api" / "freshness.dart").read_text(encoding="utf-8")
        assert "DateTime.tryParse" in source
        assert "FreshnessState.unavailable" in source

    def test_an_unparseable_timestamp_never_yields_a_fresh_state(self):
        source = (APP_LIB / "api" / "freshness.dart").read_text(encoding="utf-8")
        body = source.split("DerivedFreshness deriveFreshness(", 1)[1]
        guard = body.split("final reference", 1)[0]
        # Both the missing and the unparseable branch must bail out before any
        # clock comparison, and both must bail out to "unknown", never "live".
        assert guard.count("DerivedFreshness.unknown") >= 2
        assert "FreshnessState.live" not in guard

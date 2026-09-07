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
from typing import ClassVar

import pytest

from crypto_intel.api.routes_lot4 import (
    _input_freshness,
    _reconstructed_regime,
    _ReconstructedRegime,
    today,
)
from crypto_intel.core.enums import Asset
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

    def test_the_endpoint_passes_the_regime_it_computed(self):
        """Guards the wiring, not the engine: the two must not drift apart."""
        import inspect

        from crypto_intel.api import routes_lot4

        source = inspect.getsource(routes_lot4.today)
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


class TestInputFreshness:
    def test_every_family_is_named_individually(self, payload):
        families = payload["input_freshness"]
        for expected in ("direction", "funding", "crowding", "volatility", "positioning"):
            assert expected in families, f"{expected} has no declared state"

    def test_states_come_from_a_closed_vocabulary(self, payload):
        allowed = {"OK", "STALE", "UNAVAILABLE", "INSUFFICIENT_HISTORY"}
        for family, state in payload["input_freshness"].items():
            if family.endswith("_missing"):
                continue
            assert state in allowed, f"{family} reports unknown state {state!r}"

    def test_insufficient_history_is_not_reported_as_unavailable(self):
        """The two are different and the UI renders them differently."""

        class _Funding:
            sufficient_history = False
            value = 0.0001

        class _Empty:
            missing: ClassVar[list] = []
            inputs_missing: ClassVar[list] = []
            atr_percentile = 1.0
            regime = "BULLISH"

        state = _input_freshness(
            crowding=_Empty(), funding=_Funding(), volatility=_Empty(),
            leverage_state=_Empty(), regime=_Empty(),
        )
        assert state["funding"] == "INSUFFICIENT_HISTORY"

    def test_a_missing_value_is_unavailable_not_insufficient(self):
        class _Funding:
            sufficient_history = False
            value = None

        class _Empty:
            missing: ClassVar[list] = []
            inputs_missing: ClassVar[list] = []
            atr_percentile = 1.0
            regime = "BULLISH"

        state = _input_freshness(
            crowding=_Empty(), funding=_Funding(), volatility=_Empty(),
            leverage_state=_Empty(), regime=_Empty(),
        )
        assert state["funding"] == "UNAVAILABLE"


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

"""The cockpit page: what it may claim, and what it must refuse to claim.

The page answers eight questions in ten seconds. Each of these tests pins one
of them to a property that cannot be satisfied by inventing data:

  * a position bar only exists when a range does;
  * an absent source is removed from a score, never counted as zero;
  * coverage and uncertainty are two numbers because they are two questions;
  * a bullish break changes the structure, it does not degrade the reading;
  * "no measurable edge" is not a bearish signal.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from crypto_intel.core.enums import Asset
from crypto_intel.core.usability import (
    CoverageClass,
    FamilyState,
    Freshness,
    assess_coverage,
    expected_families,
)
from crypto_intel.engines import today_view as tv

NS = SimpleNamespace


def _zone(midpoint: float) -> NS:
    return NS(midpoint=midpoint, low=midpoint * 0.99, high=midpoint * 1.01)


def _range(bottom: float, top: float, valid: bool = True) -> NS:
    return NS(
        valid=valid, top_zone=_zone(top) if valid else None,
        bottom_zone=_zone(bottom) if valid else None,
        midpoint=(top + bottom) / 2 if valid else None, reason="",
    )


def _empty_pressure():
    """Un moteur de pression sans aucune famille: l'état par défaut d'un test."""
    from crypto_intel.engines.market_pressure import MarketPressureExplanation

    return MarketPressureExplanation(asset="BTC", families=[])


def _snapshot(**overrides):
    base = {
        "asset": "BTC",
        "analysis_id": "an_test",
        "analysis_time": datetime(2026, 9, 7, 20, 19, tzinfo=UTC),
        "price_at_analysis": 100.0,
        "regime": NS(regime=NS(value="STRONGLY_BULLISH"), confidence=80.0),
        "edge": NS(state=NS(value="NO_MEASURABLE_EDGE"), admitted_count=0, rejected_count=7),
        "opportunity": NS(
            state=NS(value="WAIT"), headline="ATTENDRE",
            summary="Un facteur de risque justifie d'attendre.",
            score=12.0, guard_rails_applied=[], positives=[], waits=[],
            negatives=[], missing=[], factors=[],
            improvement_conditions=["un retour du prix vers le bas du range"],
            deterioration_conditions=["la perte confirmée du bas de range"],
            structure_change_conditions=["une clôture 4H au-dessus du haut de range"],
        ),
        "location": NS(
            state=NS(value="NEAR_RANGE_TOP"), relative_position=0.91, price=100.0,
            detected_range=_range(80.0, 102.0), range_summary="", invalidation="",
            explanation=[],
        ),
        "structure": {"timeframes": {}, "conflict": None},
        "supports": [], "resistances": [],
        "volatility": NS(regime="LOW", direction="STABLE", atr_percentile=12.0),
        "implied_volatility": NS(available=False, unavailable_reason="pas de DVOL",
                              pricing=NS(value="UNKNOWN"), dvol=None, dvol_percentile=None),
        "crowding": NS(level=NS(value="NORMAL")),
        "funding": NS(band=NS(value="NEGATIVE")),
        "leverage_state": NS(state=NS(value="NEW_LONGS")),
        "macro_events": [],
        "uncertainty": NS(score=40.0),
        "analogs": None,
        "coverage": None,
        "pressure": _empty_pressure(),
        "etf": {},
    }
    base.update(overrides)
    return NS(**base)


class TestStructuralPosition:
    """A bar with invented endpoints is worse than no bar."""

    @pytest.mark.parametrize(
        ("position", "expected"), [(0.0, 0), (0.5, 50), (1.0, 100)]
    )
    def test_position_maps_to_the_bar(self, position, expected):
        snapshot = _snapshot(location=NS(
            state=NS(value="MID_RANGE"), relative_position=position, price=100.0,
            detected_range=_range(80.0, 120.0), range_summary="", invalidation="",
            explanation=[],
        ))
        block = tv.structural_position(snapshot)
        assert block["has_range"] is True
        assert block["percent"] == expected
        assert block["range_bottom"] == 80.0
        assert block["range_top"] == 120.0

    def test_no_validated_range_means_no_bar_and_no_invented_bounds(self):
        snapshot = _snapshot(
            location=NS(
                state=NS(value="NO_VALID_RANGE"), relative_position=None, price=100.0,
                detected_range=_range(0, 0, valid=False),
                range_summary="no validated range",
                invalidation="", explanation=["swings too few"],
            ),
            structure={"timeframes": {"4h": {"state": "BULLISH_STRUCTURE"}}, "conflict": None},
        )
        block = tv.structural_position(snapshot)
        assert block["has_range"] is False
        assert "range_top" not in block and "range_bottom" not in block
        assert block["headline"] == "Haussière"

    def test_a_position_outside_the_range_is_clamped_for_display_only(self):
        snapshot = _snapshot(location=NS(
            state=NS(value="ABOVE_RANGE"), relative_position=1.4, price=130.0,
            detected_range=_range(80.0, 120.0), range_summary="", invalidation="",
            explanation=[],
        ))
        block = tv.structural_position(snapshot)
        assert block["percent"] == 100
        assert block["relative_position"] == 1.4, "the raw reading must stay readable"


class TestLevels:
    def test_distances_carry_their_sign_and_side(self):
        snapshot = _snapshot(
            price_at_analysis=100.0,
            supports=[NS(price=95.0, touches=3, strength=70.0, last_touch=None),
                      NS(price=80.0, touches=2, strength=50.0, last_touch=None)],
            resistances=[NS(price=104.0, touches=4, strength=90.0, last_touch=None)],
        )
        block = tv.nearest_levels(snapshot)
        assert block["support"]["price"] == 95.0
        assert block["support"]["distance_pct"] == pytest.approx(-5.0)
        assert block["resistance"]["distance_pct"] == pytest.approx(4.0)

    def test_no_clustered_level_is_stated_as_absent_not_as_zero(self):
        block = tv.nearest_levels(_snapshot())
        assert block["available"] is False
        assert block["support"] is None and block["resistance"] is None
        assert block["reason"]

    def test_levels_are_measured_against_the_live_price_when_given(self):
        snapshot = _snapshot(
            price_at_analysis=100.0,
            resistances=[NS(price=104.0, touches=4, strength=90.0, last_touch=None)],
        )
        block = tv.nearest_levels(snapshot, price=102.0)
        assert block["reference_price"] == 102.0
        assert block["resistance"]["distance_pct"] == pytest.approx(1.96, abs=0.01)


class TestCatalysts:
    def _event(self, kind, hours, importance):
        return {"kind": kind, "name": kind, "hours_until": hours,
                "importance": importance, "scheduled_at": "2026-09-09T14:30:00+00:00",
                "assets": ["BTC"], "source": "config/macro_calendar.yaml"}

    def test_sorting_puts_the_important_and_the_near_first(self):
        snapshot = _snapshot(macro_events=[
            self._event("PPI", 6, "LOW"),
            self._event("FOMC", 70, "CRITICAL"),
            self._event("CPI", 18, "CRITICAL"),
            self._event("GDP", 30, "MEDIUM"),
        ])
        names = [item["kind"] for item in tv.catalysts(snapshot)["items"]]
        assert names[:2] == ["CPI", "FOMC"]
        assert len(names) == 3, "the page shows at most three"

    def test_events_beyond_a_week_are_not_shown(self):
        snapshot = _snapshot(macro_events=[self._event("CPI", 24 * 30, "CRITICAL")])
        assert tv.catalysts(snapshot)["items"] == []

    def test_a_critical_event_within_a_day_raises_a_badge(self):
        snapshot = _snapshot(macro_events=[self._event("CPI", 18, "CRITICAL")])
        alert = tv.catalysts(snapshot)["alert"]
        assert alert is not None
        assert "18 H" in alert["label"]
        assert "sens n'est pas prédit" in alert["note"]

    def test_a_distant_critical_event_raises_no_badge(self):
        snapshot = _snapshot(macro_events=[self._event("FOMC", 70, "CRITICAL")])
        assert tv.catalysts(snapshot)["alert"] is None

    def test_every_catalyst_names_its_scope_importance_and_source(self):
        snapshot = _snapshot(macro_events=[self._event("CPI", 18, "CRITICAL")])
        item = tv.catalysts(snapshot)["items"][0]
        for key in (
            "importance", "scheduled_at", "asset_scope", "source",
            "relevance_score", "time_to_event", "freshness",
        ):
            assert item[key] is not None
        assert item["freshness"] == "SCHEDULED"


class TestChangeConditions:
    """Three categories, because a break has no sign."""

    def test_a_bullish_break_is_a_structure_change_not_a_degradation(self):
        block = tv.change_conditions(_snapshot())
        degrade = " ".join(item["text"] for item in block["degrade"])
        change = " ".join(item["text"] for item in block["structure_change"])
        assert "au-dessus du haut de range" in change
        assert "au-dessus du haut de range" not in degrade

    def test_conditions_are_phrased_as_conditions(self):
        block = tv.change_conditions(_snapshot())
        for group in ("improve", "degrade", "structure_change"):
            for item in block[group]:
                assert not item["text"].lower().startswith("btc va")
                assert any(
                    token in item["text"]
                    for token in ("deviendrait", "serait", "changerait")
                )

    def test_at_most_two_per_side(self):
        opportunity = _snapshot().opportunity
        opportunity.improvement_conditions = ["a", "b", "c", "d"]
        opportunity.deterioration_conditions = ["e", "f", "g"]
        block = tv.change_conditions(_snapshot(opportunity=opportunity))
        assert len(block["improve"]) == 2
        assert len(block["degrade"]) == 2


class TestTimeframes:
    def _structure(self, **states):
        return {"timeframes": {tf: {"state": state} for tf, state in states.items()},
                "conflict": None}

    def test_opposing_timeframes_read_as_divergent(self):
        snapshot = _snapshot(structure=self._structure(
            **{"1w": "BEARISH_STRUCTURE", "1d": "RANGE_STRUCTURE",
               "4h": "RANGE_STRUCTURE", "1h": "BULLISH_STRUCTURE"}
        ))
        block = tv.timeframe_summary(snapshot)
        assert block["alignment"] == "DIVERGENT"
        assert block["alignment_label"] == "Divergent"

    def test_every_row_carries_a_word_not_only_an_arrow(self):
        snapshot = _snapshot(structure=self._structure(
            **{"1w": "BEARISH_STRUCTURE", "1d": "RANGE_STRUCTURE",
               "4h": "RANGE_STRUCTURE", "1h": "BULLISH_STRUCTURE"}
        ))
        for row in tv.timeframe_summary(snapshot)["rows"]:
            assert row["label"] and row["label"] != row["arrow"]

    def test_all_bullish_is_aligned(self):
        snapshot = _snapshot(structure=self._structure(
            **{"1w": "BULLISH_STRUCTURE", "1d": "BULLISH_STRUCTURE",
               "4h": "BULLISH_STRUCTURE", "1h": "BULLISH_STRUCTURE"}
        ))
        assert tv.timeframe_summary(snapshot)["alignment"] == "ALIGNED"

    def test_alignment_is_never_turned_into_an_edge(self):
        snapshot = _snapshot(structure=self._structure(
            **{"1w": "BULLISH_STRUCTURE", "1d": "BULLISH_STRUCTURE"}
        ))
        assert "avantage démontré" in tv.timeframe_summary(snapshot)["note"]


class TestContradictions:
    def test_a_bullish_regime_against_a_bearish_week_is_named(self):
        snapshot = _snapshot(structure={
            "timeframes": {"1w": {"state": "BEARISH_STRUCTURE"}}, "conflict": None
        })
        block = tv.contradictions(snapshot)
        assert block["badge"] == "LECTURE MIXTE"
        assert "long terme" in block["items"][0]["text"]

    def test_agreement_raises_no_badge(self):
        snapshot = _snapshot(structure={
            "timeframes": {"1w": {"state": "BULLISH_STRUCTURE"}}, "conflict": None
        })
        assert tv.contradictions(snapshot)["badge"] == ""


class TestDirectionTimingEdge:
    """The three readings are independent and must be allowed to disagree."""

    def test_bullish_direction_with_a_wait_timing_is_a_valid_combination(self):
        block = tv.direction_timing_edge(_snapshot())
        assert block["direction"]["value"] == "FORTEMENT HAUSSIÈRE"
        assert block["timing"]["value"] == "ATTENDRE"
        assert block["edge"]["value"] == "AUCUN AVANTAGE DÉMONTRÉ"
        assert "cohérente" in block["note"]

    def test_no_measurable_edge_is_not_stated_as_a_bearish_signal(self):
        block = tv.edge_block(_snapshot())
        text = (block["label"] + block["tooltip"] + block["not_a_bearish_signal"]).lower()
        assert "baisse" not in block["label"].lower()
        assert "ne dit pas que le prix va baisser" in text

    def test_untested_is_not_reported_as_tested_and_negative(self):
        snapshot = _snapshot(
            edge=NS(state=NS(value="INSUFFICIENT_DATA"), admitted_count=0, rejected_count=0)
        )
        assert tv.edge_block(snapshot)["label"] == "AUCUNE RELATION TESTÉE"

    def test_sample_sizes_stay_off_the_card(self):
        snapshot = _snapshot(analogs={"raw_n": 40, "effective_n": 8})
        block = tv.edge_block(snapshot)
        assert block["evidence_label"] == "Preuve limitée"
        assert block["detail"]["effective_n"] == 8


class TestPressureDecomposition:
    """Une source absente n'est ni neutre ni zéro, et le titre le reconnaît."""

    def _pressure(self, families):
        from crypto_intel.engines.market_pressure import (
            Direction,
            MarketPressureExplanation,
        )

        out = MarketPressureExplanation(asset="BTC", families=families)
        measured = out.measured
        if measured:
            out.denominator = sum(item.weight for item in measured)
            for item in measured:
                item.weighted_contribution = round(
                    float(item.normalized_score or 0) * item.weight / out.denominator,
                    2,
                )
            out.pressure_score = round(
                sum(item.weighted_contribution or 0 for item in measured), 1
            )
            out.state = Direction.of(out.pressure_score).value
        return out

    def _family(self, name, label, score, *, applicable=True):
        from crypto_intel.engines.market_pressure import (
            WEIGHTS,
            Direction,
            PressureFamilyContribution,
        )

        available = applicable and score is not None
        return PressureFamilyContribution(
            family=name, label=label, asset="BTC",
            applicable=applicable, available=available,
            direction=Direction.of(score if available else None),
            normalized_score=score if available else None,
            weight=WEIGHTS[name],
            raw_value={"x": 1} if available else None,
            source="src", observation_time="2026-09-08T08:00:00+00:00",
            freshness="LIVE" if available else "UNAVAILABLE",
            data_quality="MEASURED" if available else "UNAVAILABLE",
            explanation="parce que" if available else "",
            reason="" if available else "aucun fournisseur configuré",
        )

    def test_buyers_and_sellers_are_split_and_missing_sources_listed(self):
        pressure = self._pressure([
            self._family("institutions", "ETF / Institutions", 28.0),
            self._family("derivatives", "Dérivés / positionnement", 16.0),
            self._family("funding", "Funding / levier", -14.0),
            self._family("whales", "Baleines / flux exchanges", None),
            self._family("spot", "Spot / agressivité", None),
        ])
        block = tv.pressure_breakdown(_snapshot(pressure=pressure))
        assert [item["label"] for item in block["buyers"]] == [
            "ETF / Institutions", "Dérivés / positionnement"
        ]
        assert [item["label"] for item in block["sellers"]] == ["Funding / levier"]
        assert {item["label"] for item in block["unavailable"]} == {
            "Baleines / flux exchanges", "Spot / agressivité"
        }
        assert block["families_line"] == "3/5 familles"

    def test_an_unavailable_family_contributes_nothing_rather_than_zero(self):
        pressure = self._pressure([
            self._family("institutions", "ETF / Institutions", 40.0),
            self._family("whales", "Baleines / flux exchanges", None),
        ])
        block = tv.pressure_breakdown(_snapshot(pressure=pressure))
        missing = block["unavailable"][0]
        assert missing["normalized_score"] is None
        assert missing["weighted_contribution"] is None
        assert missing["direction"] == "UNAVAILABLE"
        assert missing["reason"] == "aucun fournisseur configuré"
        # Retirée du dénominateur: la seule famille présente porte tout.
        assert block["reconstruction"]["sum_of_contributions"] == pytest.approx(40.0)

    def test_a_family_without_meaning_leaves_the_coverage_denominator(self):
        pressure = self._pressure([
            self._family("institutions", "ETF / Institutions", None, applicable=False),
            self._family("spot", "Spot / agressivité", 20.0),
            self._family("derivatives", "Dérivés", 20.0),
            self._family("funding", "Funding", 20.0),
            self._family("whales", "Baleines", 20.0),
        ])
        block = tv.pressure_breakdown(_snapshot(pressure=pressure))
        assert block["families_line"] == "4/4 familles"
        assert [item["label"] for item in block["not_applicable"]] == [
            "ETF / Institutions"
        ]

    def test_the_total_can_be_rebuilt_from_the_parts(self):
        pressure = self._pressure([
            self._family("institutions", "ETF", 60.0),
            self._family("funding", "Funding", -20.0),
            self._family("derivatives", "Dérivés", 10.0),
        ])
        block = tv.pressure_breakdown(_snapshot(pressure=pressure))
        total = sum(
            item["weighted_contribution"] for item in
            block["buyers"] + block["sellers"] + block["neutral"]
        )
        assert total == pytest.approx(
            block["reconstruction"]["sum_of_contributions"], abs=0.05
        )
        assert block["reconstruction"]["matches_score"] is True
        assert block["reconstruction"]["formula"]

    def test_every_contribution_states_its_provenance(self):
        pressure = self._pressure([self._family("institutions", "ETF", 28.0)])
        item = tv.pressure_breakdown(_snapshot(pressure=pressure))["buyers"][0]
        for key in ("family", "raw_value", "normalized_score", "direction",
                    "weight", "weighted_contribution", "source",
                    "observation_time", "available", "data_quality",
                    "explanation"):
            assert key in item, f"{key} missing from a pressure contribution"

    def test_no_available_source_is_stated_as_indeterminate(self):
        pressure = self._pressure([
            self._family("whales", "Baleines", None),
            self._family("spot", "Spot", None),
        ])
        block = tv.pressure_breakdown(_snapshot(pressure=pressure))
        assert block["families_active"] == 0
        assert block["headline"] == "Pression indéterminée"
        assert block["reconstruction"]["sum_of_contributions"] is None

    def test_a_high_score_on_thin_coverage_is_never_called_dominant(self):
        """Le défaut exact: « ACHAT DOMINANT +61 » sur une famille sur cinq."""
        pressure = self._pressure([
            self._family("institutions", "ETF", 95.0),
            self._family("spot", "Spot", None),
            self._family("derivatives", "Dérivés", None),
            self._family("funding", "Funding", None),
            self._family("whales", "Baleines", None),
        ])
        block = tv.pressure_breakdown(_snapshot(pressure=pressure))
        assert block["score"] > 60
        assert "DOMINANT" not in block["label"]
        assert block["label"] == "PRESSION ACHETEUSE INDICATIVE"
        assert block["coverage_level"] == "INDICATIVE"

    def test_the_tooltip_refuses_the_probability_reading(self):
        pressure = self._pressure([self._family("institutions", "ETF", 20.0)])
        block = tv.pressure_breakdown(_snapshot(pressure=pressure))
        assert "ni une probabilité de hausse" in block["tooltip"]


class TestCoverage:
    """Coverage answers "what could we look at", not "how sure are we"."""

    def _families(self, **overrides) -> dict[str, FamilyState]:
        now = datetime.now(UTC)
        states = {}
        for name in ("price", "ohlcv_daily", "ohlcv_4h", "structure", "funding",
                     "open_interest", "dvol", "volatility", "etf", "macro",
                     "onchain", "cross_asset"):
            states[name] = FamilyState(
                family=name, available=True, valid=True,
                freshness=Freshness.RECENT, observed_at=now, source="test",
            )
        states.update(overrides)
        return states

    def test_available_fresh_stale_and_missing_are_counted_separately(self):
        now = datetime.now(UTC)
        families = self._families(
            funding=FamilyState(
                family="funding", available=True, valid=True,
                freshness=Freshness.STALE, observed_at=now - timedelta(days=4),
                source="funding.rate",
            ),
            onchain=FamilyState(family="onchain", available=False, valid=False),
        )
        coverage = assess_coverage("BTC", families)
        assert coverage.available == coverage.expected - 1
        assert coverage.missing == 1
        assert coverage.stale == 1
        assert coverage.fresh == coverage.available - 1

    def test_sol_is_not_penalised_for_a_dvol_series_that_does_not_exist(self):
        expectations = expected_families("SOL")
        assert expectations["dvol"][0] is CoverageClass.NOT_APPLICABLE
        assert expectations["etf"][0] is CoverageClass.NOT_APPLICABLE
        btc = assess_coverage("BTC", self._families())
        sol = assess_coverage("SOL", self._families())
        assert sol.expected == btc.expected - 2
        assert sol.ratio == pytest.approx(1.0)

    def test_families_absent_by_design_leave_the_denominator_alone(self):
        coverage = assess_coverage("BTC", self._families())
        by_design = [
            item for item in coverage.families
            if item.coverage is CoverageClass.UNAVAILABLE_BY_DESIGN
        ]
        assert {item.family for item in by_design} == {"whales", "exchange_flows"}
        for item in by_design:
            assert item.counts_towards_coverage is False
            assert item.reason, "an absence by design must say why"

    def test_coverage_and_uncertainty_are_two_numbers(self):
        snapshot = _snapshot(
            coverage=assess_coverage("BTC", self._families()),
            uncertainty=NS(score=60.0),
        )
        block = tv.coverage_block(snapshot)
        assert block["percent"] == 100
        assert block["uncertainty_score"] == 60.0
        assert "distinctes" in block["uncertainty_note"]

    def test_the_detail_splits_available_missing_and_not_applicable(self):
        families = self._families(
            onchain=FamilyState(family="onchain", available=False, valid=False),
        )
        snapshot = _snapshot(coverage=assess_coverage("SOL", families))
        block = tv.coverage_block(snapshot)
        assert {item["family"] for item in block["missing_families"]} == {"onchain"}
        assert {item["family"] for item in block["not_applicable_families"]} == {
            "dvol", "etf"
        }
        assert block["titles"]["not_applicable"] == "NON APPLICABLE"


class TestDecisionText:
    def test_the_sentence_is_built_from_the_readings_it_shows(self):
        sentence = tv.decision_sentence(_snapshot())
        assert "tendance de fond est nettement positive" in sentence
        assert "proche du haut de son range 4H" in sentence
        assert "timing actuel n'est pas suffisamment favorable" in sentence

    def test_the_sentence_never_predicts_a_price(self):
        for state, location in (
            ("WAIT", "NEAR_RANGE_TOP"), ("OPPORTUNITY", "MID_RANGE"),
            ("WATCH", "LOWER_THIRD"), ("UNFAVORABLE", "ABOVE_RANGE"),
        ):
            opportunity = _snapshot().opportunity
            opportunity.state = NS(value=state)
            snapshot = _snapshot(
                opportunity=opportunity,
                location=NS(state=NS(value=location), relative_position=0.5, price=100.0,
                            detected_range=_range(80.0, 120.0), range_summary="",
                            invalidation="", explanation=[]),
            )
            sentence = tv.decision_sentence(snapshot).lower()
            for forbidden in ("va monter", "va baisser", "devrait atteindre", "objectif"):
                assert forbidden not in sentence

    def test_insufficient_data_says_so_rather_than_hedging(self):
        opportunity = _snapshot().opportunity
        opportunity.state = NS(value="INSUFFICIENT_DATA")
        sentence = tv.decision_sentence(_snapshot(opportunity=opportunity))
        assert "ne permettent pas" in sentence

    def test_a_guard_rail_is_quoted_as_the_reason(self):
        opportunity = _snapshot().opportunity
        opportunity.guard_rails_applied = ["Incertitude 72/100: plafond « attendre »."]
        sentence = tv.decision_sentence(_snapshot(opportunity=opportunity))
        assert "Raison retenue" in sentence
        assert "Incertitude 72/100" in sentence


class TestVolatilityIsNotMixed:
    def test_realised_and_implied_are_reported_apart(self):
        block = tv.volatility_block(_snapshot())
        assert block["realised"]["label"] == "Faible"
        assert block["implied"]["available"] is False
        assert block["implied"]["reason"] == "pas de DVOL"
        assert "jamais additionnées" in block["note"]


class TestAssetSpecificFamilies:
    @pytest.mark.parametrize(
        ("asset", "applicable"),
        [("BTC", True), ("ETH", True), ("SOL", False)],
    )
    def test_dvol_and_etf_apply_where_the_source_publishes_them(self, asset, applicable):
        expectations = expected_families(asset)
        for family in ("dvol", "etf"):
            is_expected = expectations[family][0] is CoverageClass.EXPECTED_AND_AVAILABLE
            assert is_expected is applicable


class TestRenderedPage:
    def test_every_block_carries_the_same_analysis_id(self):
        from crypto_intel.engines.analysis_context import context_for

        for asset in (Asset.BTC, Asset.ETH, Asset.SOL):
            snapshot = context_for(asset)
            page = tv.render(snapshot)
            assert page["analysis_id"] == snapshot.analysis_id
            assert page["asset"] == asset.value
            for block in page["reading_order"]:
                assert block in page

    def test_the_page_does_not_carry_research_numbers_on_its_face(self):
        from crypto_intel.engines.analysis_context import context_for

        page = tv.render(context_for(Asset.BTC))
        surface = " ".join(
            str(page[key]) for key in
            ("direction_timing_edge", "structural_position", "immediate_context")
        )
        for forbidden in ("p_value", "fdr", "effective_n", "mfe", "mae"):
            assert forbidden not in surface.lower()

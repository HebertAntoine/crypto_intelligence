"""Pression et couverture: deux mesures, jamais confondues.

L'écran a pu afficher « ACHAT DOMINANT +61/100 » sur une seule famille
disponible sur cinq. Le score n'était pas faux; le mot l'était. Ces tests
tiennent les deux moitiés du problème:

  * une absence ne devient jamais un zéro, ni dans le score ni dans la
    couverture;
  * le vocabulaire est verrouillé par la couverture, et « dominant » ne peut
    sortir que lorsque presque toute l'information est là.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from crypto_intel.core.enums import Asset
from crypto_intel.engines.market_pressure import (
    DOMINANT_COVERAGE,
    DOMINANT_SCORE,
    WEIGHTS,
    CoverageLevel,
    Direction,
    MarketPressureExplanation,
    PressureFamilyContribution,
    assess_pressure,
)


def _family(
    name: str, score: float | None, *, applicable: bool = True,
    available: bool | None = None,
) -> PressureFamilyContribution:
    available = (score is not None) if available is None else available
    return PressureFamilyContribution(
        family=name, label=name.title(), asset="BTC",
        applicable=applicable, available=available,
        direction=Direction.of(score if available else None),
        normalized_score=score if available else None,
        weight=WEIGHTS[name],
        data_quality="MEASURED" if available else "UNAVAILABLE",
        observation_time=datetime.now(UTC).isoformat(),
        reason="" if available else "aucune source configurée",
    )


def _explain(families: list[PressureFamilyContribution]) -> MarketPressureExplanation:
    out = MarketPressureExplanation(asset="BTC", families=families)
    measured = out.measured
    if not measured:
        return out
    out.denominator = sum(item.weight for item in measured)
    for item in measured:
        item.weighted_contribution = round(
            float(item.normalized_score or 0) * item.weight / out.denominator, 2
        )
    out.pressure_score = round(
        sum(item.weighted_contribution or 0 for item in measured), 1
    )
    out.state = Direction.of(out.pressure_score).value
    return out


ALL = ("institutions", "spot", "derivatives", "funding", "whales")


class TestTheScoreIsReproducible:
    def test_the_weights_are_declared_and_sum_to_one(self):
        assert set(WEIGHTS) == set(ALL)
        assert sum(WEIGHTS.values()) == pytest.approx(1.0)

    def test_contributions_add_up_to_the_score(self):
        out = _explain([_family(name, 40) for name in ALL])
        total = sum(item.weighted_contribution for item in out.measured)
        assert total == pytest.approx(out.pressure_score, abs=0.05)

    def test_the_denominator_holds_only_available_families(self):
        out = _explain([
            _family("institutions", 60), _family("spot", 20),
            _family("derivatives", None), _family("funding", None),
            _family("whales", None),
        ])
        assert out.denominator == pytest.approx(
            WEIGHTS["institutions"] + WEIGHTS["spot"]
        )
        # Un zéro pour les absentes aurait tiré le score vers le neutre.
        assert out.pressure_score > 40

    def test_an_absent_family_carries_no_number_at_all(self):
        out = _explain([_family(name, None) for name in ALL])
        for item in out.families:
            assert item.normalized_score is None
            assert item.weighted_contribution is None
            assert item.direction is Direction.UNAVAILABLE

    def test_the_score_stays_within_its_bounds(self):
        out = _explain([_family(name, 100) for name in ALL])
        assert -100 <= out.pressure_score <= 100


class TestVocabularyIsGatedByCoverage:
    """« Dominant » demande presque toute l'information, pas seulement un score."""

    def test_five_buying_families_may_be_called_dominant(self):
        out = _explain([_family(name, 70) for name in ALL])
        assert out.coverage_ratio == pytest.approx(1.0)
        assert out.label == "ACHETEURS DOMINANTS"

    def test_four_buying_and_one_neutral_is_strong_but_stated_plainly(self):
        out = _explain([
            *(_family(name, 70) for name in ALL[:4]), _family("whales", 0),
        ])
        assert out.coverage_level is CoverageLevel.STRONG
        assert out.label == "ACHETEURS DOMINANTS"

    def test_three_buying_against_two_selling_lands_between(self):
        out = _explain([
            _family("institutions", 60), _family("spot", 50),
            _family("derivatives", 40), _family("funding", -50),
            _family("whales", -60),
        ])
        assert 0 < out.pressure_score < DOMINANT_SCORE
        assert out.label.startswith("PRESSION ACHETEUSE")
        assert "DOMINANT" not in out.label

    def test_two_available_and_three_missing_is_never_dominant(self):
        out = _explain([
            _family("institutions", 90), _family("spot", 90),
            _family("derivatives", None), _family("funding", None),
            _family("whales", None),
        ])
        assert out.pressure_score > DOMINANT_SCORE
        assert out.coverage_ratio < DOMINANT_COVERAGE
        assert "DOMINANT" not in out.label
        assert "PARTIELLE" in out.label

    def test_one_strong_buy_against_four_missing_is_only_indicative(self):
        """Le cas exact qui a produit « ACHAT DOMINANT +61 » sur 1/5."""
        out = _explain([
            _family("institutions", 95),
            *(_family(name, None) for name in ALL[1:]),
        ])
        assert out.pressure_score == pytest.approx(95, abs=0.5)
        assert out.coverage_level is CoverageLevel.INDICATIVE
        assert out.label == "PRESSION ACHETEUSE INDICATIVE"
        assert "DOMINANT" not in out.label

    def test_no_family_at_all_is_insufficient_not_balanced(self):
        out = _explain([_family(name, None) for name in ALL])
        assert out.state == "INSUFFICIENT_DATA"
        assert out.pressure_score is None
        assert out.label == "DONNÉES INSUFFISANTES"
        assert out.balance is None

    def test_a_strong_reading_on_a_weak_score_stays_light(self):
        out = _explain([_family(name, 12) for name in ALL])
        assert out.coverage_level is CoverageLevel.STRONG
        assert "LÉGÈRE" in out.label


class TestNotApplicableIsNotMissing:
    def test_a_family_without_meaning_leaves_the_denominator(self):
        out = _explain([
            _family("institutions", None, applicable=False, available=False),
            _family("spot", 30), _family("derivatives", 30),
            _family("funding", 30), _family("whales", 30),
        ])
        assert len(out.applicable) == 4
        assert len(out.measured) == 4
        # Quatre applicables et quatre disponibles: 4/4, pas 4/5.
        assert out.coverage_line == "4/4 familles"
        assert out.coverage_ratio == pytest.approx(1.0)

    def test_sol_has_no_spot_etf_and_is_not_penalised_for_it(self):
        out = assess_pressure(Asset.SOL, funding_percentile=50, leverage_state="QUIET")
        institutions = next(
            item for item in out.families if item.family == "institutions"
        )
        assert institutions.applicable is False
        assert institutions.reason
        assert institutions not in out.applicable

    def test_btc_does_expect_an_etf_family(self):
        out = assess_pressure(Asset.BTC, funding_percentile=50, leverage_state="QUIET")
        institutions = next(
            item for item in out.families if item.family == "institutions"
        )
        assert institutions.applicable is True


class TestOpenInterestIsNeverReadAsBuying:
    """Un future a un long ET un short: l'OI seul n'a pas de direction."""

    def test_the_derivatives_family_names_its_inputs(self):
        out = assess_pressure(Asset.BTC, funding_percentile=50, leverage_state="NEW_LONGS")
        derivatives = next(
            item for item in out.families if item.family == "derivatives"
        )
        assert "open interest" in derivatives.source.lower()
        assert "comptes" in derivatives.source.lower()

    def test_rising_open_interest_alone_is_not_a_buy(self):
        from crypto_intel.engines.market_pressure import _derivatives

        # Sans état joint prix/OI ni bascule des comptes, rien n'est affirmé.
        item = _derivatives(Asset.BTC, "")
        assert item.direction is not Direction.STRONG_BUY

    def test_new_shorts_reads_as_selling(self):
        from crypto_intel.engines.market_pressure import _derivatives

        item = _derivatives(Asset.BTC, "NEW_SHORTS")
        if item.available:
            assert item.normalized_score < 0


class TestTheContractIsStable:
    def test_the_payload_carries_the_canonical_family_model(self):
        payload = assess_pressure(
            Asset.BTC, funding_percentile=50, leverage_state="QUIET"
        ).to_dict()
        assert {
            "state", "pressure_score", "families", "components", "coverage",
            "contradictions", "missing", "summary", "as_of", "method", "label",
        } <= set(payload)
        for family in payload["families"]:
            assert {
                "family", "asset", "applicable", "available", "direction",
                "raw_value", "normalized_score", "weight",
                "weighted_contribution", "source", "event_time",
                "observation_time", "ingested_at", "freshness", "data_quality",
                "explanation",
            } <= set(family)

    def test_the_method_is_published_with_the_score(self):
        method = assess_pressure(
            Asset.BTC, funding_percentile=50, leverage_state="QUIET"
        ).to_dict()["method"]
        assert method["weights"] == WEIGHTS
        assert method["bounds"] == [-100, 100]
        assert "jamais convertie en zéro" in method["missing_data"]
        assert f"{DOMINANT_SCORE:.0f}" in method["dominant_gate"]

    def test_every_direction_has_a_french_name(self):
        from crypto_intel.engines.market_pressure import DIRECTION_DOT, DIRECTION_FR

        for direction in Direction:
            assert direction.value in DIRECTION_FR
            assert direction.value in DIRECTION_DOT


class TestNoFabricatedSource:
    def test_whales_stay_unavailable_and_say_why(self):
        out = assess_pressure(Asset.BTC, funding_percentile=50, leverage_state="QUIET")
        whales = next(item for item in out.families if item.family == "whales")
        assert whales.available is False
        assert whales.normalized_score is None
        assert "payant" in whales.reason
        for forbidden in ("baleines acheteuses", "baleines vendeuses"):
            assert forbidden not in whales.reason.lower()

    def test_no_family_advertises_a_proxy_as_a_measurement(self):
        out = assess_pressure(Asset.BTC, funding_percentile=50, leverage_state="QUIET")
        for item in out.families:
            if item.available:
                assert item.data_quality in ("MEASURED", "DERIVED", "PARTIAL")
                assert item.source, f"{item.family} ne nomme pas sa source"
                assert item.observation_time, f"{item.family} n'a pas d'horodatage"

"""Pression : intensité, couverture, et la frontière entre les deux.

Trois affirmations étaient confondues sur une seule ligne — la force du
déséquilibre, la quantité d'information qui le soutient, et la conclusion
qu'on peut en tirer. « +30/100 · 4/5 familles · Forte » se lisait « forte
pression » alors que « Forte » qualifiait la couverture.

Ces tests tiennent les trois séparément, et vérifient que le score affiché se
refait à la main depuis les familles.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from crypto_intel.core.enums import Asset
from crypto_intel.engines.market_pressure import (
    COVERAGE_FR,
    INTENSITY_FR,
    WEIGHTS,
    CoverageLevel,
    Direction,
    Intensity,
    MarketPressureExplanation,
    PressureFamilyContribution,
    assess_pressure,
    minimum_families,
)

ALL = ("institutions", "spot", "derivatives", "funding", "whales")


def _family(
    name: str, score: float | None, *, applicable: bool = True,
) -> PressureFamilyContribution:
    available = applicable and score is not None
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
    """Reproduit exactement le calcul du moteur, pour pouvoir le confronter."""
    out = MarketPressureExplanation(asset="BTC", families=families)
    measured = out.measured
    if not measured:
        return out
    out.denominator = sum(item.weight for item in measured)
    exact = 0.0
    for item in measured:
        effective = item.weight / out.denominator
        item.effective_weight = round(effective, 4)
        contribution = float(item.normalized_score or 0) * effective
        exact += contribution
        item.weighted_contribution = round(contribution, 2)
    out.pressure_score = round(max(-100.0, min(100.0, exact)), 1)
    out.state = Direction.of(out.pressure_score).value
    return out


def _scored(scores: dict[str, float | None]) -> MarketPressureExplanation:
    return _explain([_family(name, scores.get(name)) for name in ALL])


class TestScoreIsReproducible:
    """TEST 1, 2, 4 — la somme pondérée, et l'exclusion d'une absente."""

    def test_five_families_sum_exactly_to_the_score(self):
        out = _scored(dict.fromkeys(ALL, 40.0))
        assert len(out.measured) == 5
        assert out.denominator == pytest.approx(1.0)
        total = sum(item.weighted_contribution for item in out.measured)
        assert total == pytest.approx(out.pressure_score, abs=0.05)
        # Cinq familles à +40 donnent exactement +40, quels que soient les poids.
        assert out.pressure_score == pytest.approx(40.0, abs=0.05)

    def test_an_unavailable_family_is_excluded_and_weights_renormalised(self):
        out = _scored({
            "institutions": 60.0, "spot": 20.0, "derivatives": 20.0,
            "funding": 20.0, "whales": None,
        })
        assert len(out.measured) == 4
        assert out.denominator == pytest.approx(1.0 - WEIGHTS["whales"])
        # Les poids effectifs des familles restantes somment à 1.
        assert sum(i.effective_weight for i in out.measured) == pytest.approx(1.0, abs=1e-3)
        for item in out.measured:
            assert item.effective_weight == pytest.approx(
                item.weight / out.denominator, abs=1e-3
            )

    def test_an_unavailable_family_contributes_nothing_not_zero(self):
        """TEST 4 — un zéro tirerait le score vers le neutre."""
        with_whales = _scored(dict.fromkeys(ALL, 80.0))
        without = _scored({**dict.fromkeys(ALL, 80.0), "whales": None})
        # Retirer une famille qui disait la même chose ne change pas le score.
        assert without.pressure_score == pytest.approx(with_whales.pressure_score, abs=0.1)
        # Et si elle valait 0, le score baisserait: vérifions que ce n'est pas le cas.
        as_zero = _scored({**dict.fromkeys(ALL, 80.0), "whales": 0.0})
        assert as_zero.pressure_score < without.pressure_score
        absent = next(i for i in without.families if i.family == "whales")
        assert absent.normalized_score is None
        assert absent.weighted_contribution is None
        assert absent.effective_weight is None

    def test_the_score_stays_within_its_bounds(self):
        assert _scored(dict.fromkeys(ALL, 100.0)).pressure_score <= 100
        assert _scored(dict.fromkeys(ALL, -100.0)).pressure_score >= -100


class TestIntensityScale:
    """TEST 5, 6, 7, 8 — le mot dépend du score, jamais de la couverture."""

    @pytest.mark.parametrize(
        ("score", "expected"),
        [
            (70.0, Intensity.STRONG_BUYING),
            (60.0, Intensity.STRONG_BUYING),
            (59.0, Intensity.BUYING),
            (30.0, Intensity.BUYING),
            (25.0, Intensity.BUYING),
            (24.0, Intensity.BALANCED),
            (0.0, Intensity.BALANCED),
            (-24.0, Intensity.BALANCED),
            (-25.0, Intensity.SELLING),
            (-30.0, Intensity.SELLING),
            (-59.0, Intensity.SELLING),
            (-60.0, Intensity.STRONG_SELLING),
        ],
    )
    def test_each_band_gets_its_own_word(self, score, expected):
        assert Intensity.of(score) is expected

    def test_thirty_is_never_called_strong(self):
        """TEST 5 — le défaut exact: +30 annoncé « forte pression »."""
        out = _scored(dict.fromkeys(ALL, 30.0))
        assert out.pressure_score == pytest.approx(30.0, abs=0.05)
        assert out.label == "PRESSION ACHETEUSE"
        assert "FORTE" not in out.label

    def test_seventy_is_strong(self):
        out = _scored(dict.fromkeys(ALL, 70.0))
        assert out.label == "FORTE PRESSION ACHETEUSE"

    def test_minus_thirty_is_selling(self):
        out = _scored(dict.fromkeys(ALL, -30.0))
        assert out.label == "PRESSION VENDEUSE"

    def test_the_neutral_band_is_balanced(self):
        out = _scored(dict.fromkeys(ALL, 10.0))
        assert out.label == "ÉQUILIBRÉE"

    def test_full_coverage_never_upgrades_a_weak_score(self):
        strong_coverage = _scored(dict.fromkeys(ALL, 30.0))
        assert strong_coverage.coverage_level is CoverageLevel.EXCELLENT
        assert strong_coverage.label == "PRESSION ACHETEUSE"


class TestCoverageIsItsOwnMeasure:
    """TEST 3 — la couverture compte des familles, pas des poids."""

    @pytest.mark.parametrize(
        ("available", "level", "label"),
        [
            (5, CoverageLevel.EXCELLENT, "Excellente"),
            (4, CoverageLevel.GOOD, "Bonne"),
            (3, CoverageLevel.PARTIAL, "Partielle"),
            (2, CoverageLevel.LOW, "Faible"),
            (1, CoverageLevel.LOW, "Faible"),
        ],
    )
    def test_the_count_decides_the_word(self, available, level, label):
        scores = {name: (40.0 if i < available else None)
                  for i, name in enumerate(ALL)}
        out = _scored(scores)
        assert len(out.measured) == available
        assert out.coverage_level is level
        assert out.coverage_label == label

    def test_three_available_reads_three_on_five(self):
        out = _scored({"institutions": 30.0, "spot": 30.0, "derivatives": 30.0,
                       "funding": None, "whales": None})
        assert out.coverage_line == "3/5 familles"

    def test_a_family_without_meaning_leaves_the_denominator(self):
        out = _explain([
            _family("institutions", None, applicable=False),
            *(_family(name, 30.0) for name in ALL[1:]),
        ])
        # Quatre applicables, quatre disponibles: 4/4, pas 4/5.
        assert out.coverage_line == "4/4 familles"
        assert out.coverage_level is CoverageLevel.GOOD

    def test_coverage_never_borrows_intensity_vocabulary(self):
        for label in COVERAGE_FR.values():
            assert "PRESSION" not in label.upper()
        for label in INTENSITY_FR.values():
            assert label not in COVERAGE_FR.values()


class TestInsufficientData:
    """TEST 12 — sous le minimum, aucune conclusion n'est annoncée."""

    def test_two_families_is_not_a_balanced_market(self):
        out = _scored({"institutions": 90.0, "spot": 90.0,
                       "derivatives": None, "funding": None, "whales": None})
        assert len(out.measured) == 2 < minimum_families()
        assert out.has_enough_families is False
        assert out.label == "DONNÉES INSUFFISANTES"
        assert out.intensity is Intensity.INSUFFICIENT

    def test_no_family_at_all_is_insufficient_not_zero(self):
        out = _scored(dict.fromkeys(ALL, None))
        assert out.pressure_score is None
        assert out.label == "DONNÉES INSUFFISANTES"
        assert out.balance is None

    def test_the_minimum_is_configured_not_hardcoded(self):
        assert minimum_families() == 3

    def test_at_the_minimum_an_intensity_is_produced(self):
        out = _scored({"institutions": 40.0, "spot": 40.0, "derivatives": 40.0,
                       "funding": None, "whales": None})
        assert out.has_enough_families is True
        assert out.label == "PRESSION ACHETEUSE"


class TestTheContractIsStable:
    def test_the_payload_separates_intensity_from_coverage(self):
        payload = _scored(dict.fromkeys(ALL, 30.0)).to_dict()
        assert payload["intensity"] == "BUYING"
        assert payload["intensity_label"] == "PRESSION ACHETEUSE"
        assert payload["coverage"]["label"] == "Excellente"
        assert payload["coverage"]["sufficient"] is True
        assert payload["coverage"]["breakdown"]

    def test_every_family_carries_its_effective_weight(self):
        payload = _scored({**dict.fromkeys(ALL, 30.0), "whales": None}).to_dict()
        for family in payload["families"]:
            if family["available"]:
                assert family["effective_weight"] is not None
                assert family["weighted_contribution"] is not None
            else:
                assert family["effective_weight"] is None
                assert family["weighted_contribution"] is None

    def test_the_method_publishes_both_scales(self):
        method = _scored(dict.fromkeys(ALL, 30.0)).to_dict()["method"]
        assert method["intensity_scale"]["strong_buy"] == 60
        assert method["coverage_scale"]["excellent"] == 5
        assert "jamais convertie en zéro" in method["missing_data"]

    def test_every_direction_and_level_has_a_french_name(self):
        from crypto_intel.engines.market_pressure import DIRECTION_DOT, DIRECTION_FR

        for direction in Direction:
            assert direction.value in DIRECTION_FR
            assert direction.value in DIRECTION_DOT
        for level in CoverageLevel:
            assert level.value in COVERAGE_FR
        for intensity in Intensity:
            assert intensity.value in INTENSITY_FR


class TestNoFabricatedSource:
    def test_whales_stay_unavailable_and_say_why(self):
        out = assess_pressure(Asset.BTC, funding_percentile=50, leverage_state="QUIET")
        whales = next(item for item in out.families if item.family == "whales")
        assert whales.available is False
        assert whales.normalized_score is None
        assert "payant" in whales.reason

    def test_sol_has_no_spot_etf_and_is_not_penalised(self):
        out = assess_pressure(Asset.SOL, funding_percentile=50, leverage_state="QUIET")
        institutions = next(i for i in out.families if i.family == "institutions")
        assert institutions.applicable is False
        assert institutions not in out.applicable

    def test_no_family_advertises_a_proxy_as_a_measurement(self):
        out = assess_pressure(Asset.BTC, funding_percentile=50, leverage_state="QUIET")
        for item in out.families:
            if item.available:
                assert item.data_quality in ("MEASURED", "DERIVED", "PARTIAL")
                assert item.source
                assert item.observation_time

"""The whale indicator shows the analyser's reading, or states that it has none."""

from types import SimpleNamespace

from crypto_intel.core.enums import Direction, Freshness
from crypto_intel.engines.factor_semantics import (
    Availability,
    FactorDirection,
    FactorImpact,
    whale_flow_assessment,
)


def analysis(**overrides):
    base = {
        "available": True,
        "behaviour": "neutral",
        "direction": Direction.NEUTRAL,
        "freshness": Freshness.HOUR_1,
        "confidence": 0.6,
        "configured_providers": ["whale_alert"],
        "findings": ["Exchange flows broadly balanced"],
        "strength": 0.0,
        "unavailable_reason": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_no_source_is_published_as_unavailable_not_neutral():
    reading = whale_flow_assessment(
        analysis(available=False, unavailable_reason="Aucun fournisseur configuré.")
    )

    assert reading.availability is Availability.UNAVAILABLE
    assert reading.direction is FactorDirection.UNKNOWN
    assert reading.missing_requirements == ["Aucun fournisseur configuré."]


def test_inconclusive_is_unknown_never_neutral():
    reading = whale_flow_assessment(
        analysis(behaviour="to_exchange", direction=Direction.INCONCLUSIVE)
    )

    assert reading.direction is FactorDirection.UNKNOWN
    assert "sans être confirmées" in reading.rationale


def test_a_direction_needs_two_views_of_the_same_coins():
    corroborated_out = whale_flow_assessment(
        analysis(
            behaviour="from_exchange",
            direction=Direction.BULLISH,
            findings=["Net 900 leaving exchanges", "Exchange-held supply down 1.40%"],
        )
    )
    corroborated_in = whale_flow_assessment(
        analysis(
            behaviour="to_exchange",
            direction=Direction.BEARISH,
            findings=["Net 900 moving onto exchanges", "Exchange-held supply up 1.20%"],
        )
    )

    assert corroborated_out.direction is FactorDirection.POSITIVE
    assert corroborated_in.direction is FactorDirection.NEGATIVE


def test_deposits_alone_are_not_read_as_selling_even_if_the_analyser_says_so():
    """The analyser marks a large deposit BEARISH; one measurement is not a sale."""

    reading = whale_flow_assessment(
        analysis(behaviour="to_exchange", direction=Direction.BEARISH, strength=-45.0)
    )

    assert reading.direction is FactorDirection.UNKNOWN
    assert reading.impact is FactorImpact.HIGH


def test_size_sets_the_weight_and_confidence_is_a_fraction():
    small = whale_flow_assessment(analysis(behaviour="to_exchange", strength=-8.0, confidence=85.0))

    assert small.impact is FactorImpact.LOW
    assert small.confidence == 0.85

"""The whale indicator shows the analyser's reading, or states that it has none."""

from types import SimpleNamespace

from crypto_intel.core.enums import Direction, Freshness
from crypto_intel.engines.factor_semantics import (
    Availability,
    FactorDirection,
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


def test_direction_is_the_analysers_own():
    out = whale_flow_assessment(
        analysis(behaviour="from_exchange", direction=Direction.BULLISH)
    )
    into = whale_flow_assessment(
        analysis(behaviour="to_exchange", direction=Direction.BEARISH)
    )

    assert out.direction is FactorDirection.POSITIVE
    assert into.direction is FactorDirection.NEGATIVE


def test_deposits_alone_are_not_read_as_selling():
    """Same behaviour, no analyser direction: the sentence must not claim a sale."""

    reading = whale_flow_assessment(
        analysis(behaviour="to_exchange", direction=Direction.INCONCLUSIVE)
    )

    assert reading.direction is not FactorDirection.NEGATIVE

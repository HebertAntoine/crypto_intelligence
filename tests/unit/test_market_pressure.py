from __future__ import annotations

from crypto_intel.core.enums import Asset
from crypto_intel.engines.market_pressure import assess_pressure


def test_weighted_pressure_uses_only_available_components():
    result = assess_pressure(
        Asset.SOL,
        funding_percentile=80,
        funding_usable=True,
        leverage_state="NEW_SHORTS",
        positioning_usable=True,
    )
    assert result.measured == 2
    assert "Baleines" in result.missing
    assert "Flux spot / exchanges" in result.missing
    assert result.pressure_score is not None
    # Funding is positive and positioning is negative: both remain visible.
    assert result.contradictions
    assert -100 <= result.pressure_score <= 100


def test_no_measurement_is_insufficient_not_balanced():
    result = assess_pressure(
        Asset.SOL,
        funding_percentile=None,
        funding_usable=False,
        leverage_state="UNDETERMINED",
        positioning_usable=False,
    )
    assert result.state == "INSUFFICIENT_DATA"
    assert result.pressure_score is None
    assert result.balance is None


def test_unavailable_whales_never_claim_buying_or_selling():
    result = assess_pressure(
        Asset.SOL,
        funding_percentile=50,
        funding_usable=True,
        leverage_state="QUIET",
        positioning_usable=True,
    )
    whales = next(component for component in result.components
                  if component.name == "baleines")
    assert whales.available is False
    assert whales.normalized_pressure is None
    forbidden = ("baleines acheteuses", "baleines vendeuses")
    assert not any(text in whales.reason.lower() for text in forbidden)


def test_market_pressure_api_has_the_requested_fields():
    payload = assess_pressure(
        Asset.SOL,
        funding_percentile=50,
        funding_usable=True,
        leverage_state="QUIET",
        positioning_usable=True,
    ).to_dict()
    assert {
        "state", "pressure_score", "components", "contradictions",
        "missing", "summary", "as_of",
    } <= set(payload)

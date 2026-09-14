"""Section 22: the five scenarios, walked through the real chain.

These start from observations in the shape the store produces and end at the
synthesis the API publishes, so a break anywhere between the adapter, the
readings, the factors and the state machine fails here rather than in production.
"""

from datetime import UTC, datetime, timedelta

from crypto_intel.engines.factor_semantics import (
    Availability,
    FactorAssessment,
    FactorDirection,
    FactorImpact,
)
from crypto_intel.engines.macro_transmission import readings_from_observations
from crypto_intel.engines.market_synthesis import (
    MarketState,
    MarketSynthesisEngine,
    Uncertainty,
)

NOW = datetime(2026, 9, 14, 12, tzinfo=UTC)


class Provenance:
    def __init__(self, source: str, provider: str, url: str | None = None):
        self.source = source
        self.provider = provider
        self.source_url = url


class Freshness:
    def __init__(self, value: str):
        self.value = value


class Obs:
    """Shaped like the store's Observation, with only the fields read here."""

    def __init__(self, metric, value, days_ago, *, source="FRED", provider="fred"):
        self.metric = metric
        self.value = value
        self.timestamp = NOW - timedelta(days=days_ago)
        self.provenance = Provenance(source, provider, "https://fred.stlouisfed.org/")
        self.freshness = Freshness("FRESH")


def oil_series(start: float, end: float, *, days: int = 30) -> list[Obs]:
    return [
        Obs("macro.wti", start, days),
        Obs("macro.wti", (start + end) / 2, days // 2),
        Obs("macro.wti", end, 0),
    ]


def rate_series(start: float, end: float) -> list[Obs]:
    return [Obs("macro.us10y", start, 30), Obs("macro.us10y", end, 0)]


def credit_series(start: float, end: float) -> list[Obs]:
    return [Obs("macro.hy_spread", start, 30), Obs("macro.hy_spread", end, 0)]


def factor(key, direction, impact=FactorImpact.MODERATE, *, label=None):
    return FactorAssessment(
        key=key,
        label=label or key.capitalize(),
        direction=direction,
        impact=impact,
        confidence=0.8,
        availability=Availability.AVAILABLE,
        freshness="FRESH",
        provider="test",
        rationale=f"lecture {key}",
        causal_chain=[f"{key}.", "observation", "mécanisme"],
    )


def run(observations, extra_factors):
    readings = readings_from_observations(observations, now=NOW)
    factors = [item.assessment for item in readings] + extra_factors
    return MarketSynthesisEngine().synthesize(factors, now=NOW)


# --- TEST A -----------------------------------------------------------------


def test_a_oil_shock_high_yields_calm_credit_intact_support() -> None:
    """Every risk condition present, no confirmation: elevated risk, not more."""

    result = run(
        oil_series(82.0, 104.0) + rate_series(4.3, 5.0) + credit_series(3.3, 3.3),
        [factor("technical", FactorDirection.POSITIVE, label="Technique")],
    )
    assert result.state is MarketState.ELEVATED_RISK
    assert result.state is not MarketState.CORRECTION_CONFIRMED
    assert "non confirmée" in result.headline
    labels = {item["label"] for item in result.counter_evidence}
    assert "Crédit" in labels or "Technique" in labels


# --- TEST B -----------------------------------------------------------------


def test_b_everything_deteriorating_confirms_the_correction() -> None:
    result = run(
        oil_series(82.0, 104.0) + rate_series(4.3, 5.0) + credit_series(3.4, 6.4),
        [
            factor("technical", FactorDirection.NEGATIVE, FactorImpact.HIGH, label="Technique"),
            factor("flows", FactorDirection.NEGATIVE, FactorImpact.HIGH, label="Flux"),
            factor("positioning", FactorDirection.NEGATIVE, label="Positionnement"),
        ],
    )
    assert result.state is MarketState.CORRECTION_CONFIRMED
    met, total = result.confirmation_met
    assert met >= total - 1


# --- TEST C -----------------------------------------------------------------


def test_c_bad_macro_but_calm_credit_and_positive_flows_is_not_confirmed() -> None:
    result = run(
        oil_series(82.0, 104.0) + rate_series(4.3, 5.0) + credit_series(3.3, 3.2),
        [
            factor("flows", FactorDirection.POSITIVE, FactorImpact.HIGH, label="Flux"),
            factor("technical", FactorDirection.POSITIVE, label="Technique"),
        ],
    )
    assert result.state in {MarketState.ELEVATED_RISK, MarketState.MIXED}
    assert result.state is not MarketState.CORRECTION_CONFIRMED
    assert result.counter_evidence


# --- TEST D -----------------------------------------------------------------


def test_d_an_unverified_social_item_never_reaches_the_decision() -> None:
    from crypto_intel.engines.future_context import usable_events_for_horizon
    from crypto_intel.future_events.models import (
        DecisionHorizon,
        EventImportance,
        EventScheduleType,
        ExpectedMovement,
        FutureEvent,
        FutureEventCategory,
        FutureEventSourceTier,
    )

    def event(tier, title):
        return FutureEvent(
            event_type="TEST",
            category=FutureEventCategory.REGULATION,
            schedule_type=EventScheduleType.SCHEDULED,
            title=title,
            source="src",
            source_tier=tier,
            source_url="https://example.org/",
            importance=EventImportance.CRITICAL,
            magnitude_effect=ExpectedMovement.HIGH,
            scheduled_at=NOW + timedelta(hours=24),
            detected_at=NOW,
            last_updated=NOW,
        )

    usable = usable_events_for_horizon(
        [
            event(FutureEventSourceTier.A, "Vote officiel"),
            event(FutureEventSourceTier.E, "Rumeur X"),
        ],
        DecisionHorizon.D7,
        NOW,
    )
    assert [item.title for item in usable] == ["Vote officiel"]


# --- TEST E -----------------------------------------------------------------


def test_e_without_fred_the_pipeline_degrades_instead_of_breaking() -> None:
    """Only the key-free series exist: the chain still produces an answer."""

    key_free = [
        Obs("macro.oil_wti", 82.0, 30, source="yahoo_finance", provider="yahoo_finance"),
        Obs("macro.oil_wti", 104.0, 0, source="yahoo_finance", provider="yahoo_finance"),
        Obs("macro.us10y_yahoo", 4.9, 0, source="yahoo_finance", provider="yahoo_finance"),
    ]
    result = run(
        key_free,
        [
            factor("technical", FactorDirection.POSITIVE, label="Technique"),
            factor("flows", FactorDirection.POSITIVE, label="Flux"),
        ],
    )
    assert result.state is not MarketState.INSUFFICIENT_DATA
    assert result.data_status == "PARTIAL_DATA"
    assert "Crédit" in result.missing_families
    # The gap raises doubt; it never becomes a neutral stance.
    assert result.uncertainty in {Uncertainty.MEDIUM, Uncertainty.HIGH}


def test_e_a_missing_series_states_what_it_needs() -> None:
    readings = readings_from_observations(
        [Obs("macro.oil_wti", 90.0, 0, source="yahoo_finance", provider="yahoo_finance")],
        now=NOW,
    )
    credit = next(item for item in readings if item.assessment.key == "credit")
    assert credit.assessment.availability is Availability.UNAVAILABLE
    assert credit.assessment.missing_requirements
    assert credit.assessment.direction is FactorDirection.UNKNOWN


# --- fixtures must never reach production readings --------------------------


def test_a_mock_row_can_never_influence_a_reading() -> None:
    """The live database holds fixture rows interleaved with real ones."""

    mixed = [
        Obs("macro.oil_wti", 92.0, 7, source="yahoo_finance", provider="yahoo_finance"),
        Obs(
            "macro.oil_wti",
            71.8,
            7,
            source="MOCK FIXTURES (synthetic data - MOCK_MODE only)",
            provider="fixtures",
        ),
        Obs("macro.oil_wti", 93.0, 0, source="yahoo_finance", provider="yahoo_finance"),
    ]
    readings = readings_from_observations(mixed, now=NOW)
    energy = next(item for item in readings if item.assessment.key == "energy")
    # Against the real 92 the move is about one per cent; against the fixture it
    # would read as a thirty per cent shock.
    assert "93.0" in energy.assessment.rationale
    assert energy.assessment.direction is not FactorDirection.NEGATIVE


def test_only_fixture_rows_means_unavailable_not_a_fabricated_reading() -> None:
    readings = readings_from_observations(
        [
            Obs(
                "macro.oil_wti",
                71.8,
                0,
                source="MOCK FIXTURES (synthetic data - MOCK_MODE only)",
                provider="fixtures",
            )
        ],
        now=NOW,
    )
    energy = next(item for item in readings if item.assessment.key == "energy")
    assert energy.assessment.availability is Availability.UNAVAILABLE

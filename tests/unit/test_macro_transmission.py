"""Sections 51 and 52: energy, credit and rates must be read as a chain.

The point of these tests is not that oil is bearish. It is that the system must
refuse to say so when the rest of the chain disagrees.
"""

from crypto_intel.engines.factor_semantics import (
    Availability,
    FactorDirection,
    FactorImpact,
    FactorTrend,
)
from crypto_intel.engines.macro_transmission import (
    MacroRegime,
    confront,
    credit_assessment,
    oil_assessment,
    rates_assessment,
)

# --- section 51: oil --------------------------------------------------------


def test_case_a_oil_high_but_stable_is_a_standing_condition() -> None:
    """A high level is already priced; it is not a fresh impulse."""

    result = oil_assessment(
        brent=108.0, change_7d_pct=0.4, change_30d_pct=1.2, freshness="FRESH"
    )
    assert result.assessment.direction is FactorDirection.NEUTRAL
    assert result.assessment.impact is FactorImpact.LOW
    assert "déjà intégré" in " ".join(result.chain)


def test_case_b_a_fast_oil_rise_is_an_inflation_impulse() -> None:
    result = oil_assessment(
        brent=108.0, change_7d_pct=12.0, change_30d_pct=22.0, freshness="FRESH"
    )
    assert result.assessment.direction is FactorDirection.NEGATIVE
    assert result.assessment.impact is FactorImpact.HIGH
    assert result.assessment.trend is FactorTrend.DETERIORATING


def test_case_b_full_chain_is_strongly_restrictive() -> None:
    """Oil shock + rising yields: every link points the same way."""

    readings = [
        oil_assessment(brent=108.0, change_30d_pct=22.0, freshness="FRESH"),
        rates_assessment(
            us2y=4.8, us10y=4.95, us30y=5.1, us10y_change_30d_pct=0.6, freshness="FRESH"
        ),
    ]
    verdict = confront(readings)
    assert verdict.regime in {
        MacroRegime.RESTRICTIVE,
        MacroRegime.STRONGLY_RESTRICTIVE,
    }


def test_case_c_oil_rising_while_yields_fall_is_not_a_crisis() -> None:
    """The chain is broken: the system must say so rather than average it."""

    readings = [
        oil_assessment(brent=108.0, change_30d_pct=22.0, freshness="FRESH"),
        rates_assessment(
            us2y=3.9, us10y=3.8, us30y=4.1, us10y_change_30d_pct=-0.7, freshness="FRESH"
        ),
    ]
    verdict = confront(readings)
    assert verdict.regime is MacroRegime.CONFLICTING
    assert "contredisent" in verdict.rationale
    assert verdict.agreeing and verdict.disagreeing


def test_oil_never_becomes_a_direct_crypto_signal() -> None:
    """The chain must pass through inflation and policy, never jump to price."""

    chain = " ".join(
        oil_assessment(brent=108.0, change_30d_pct=22.0, freshness="FRESH").chain
    ).lower()
    assert "inflation" in chain
    assert "monétaire" in chain
    assert "rendements" in chain
    assert "pas automatique" in chain or "sans que ce lien" in chain


def test_falling_oil_is_read_as_an_easing_impulse() -> None:
    result = oil_assessment(brent=70.0, change_30d_pct=-19.0, freshness="FRESH")
    assert result.assessment.direction is FactorDirection.POSITIVE
    assert result.assessment.trend is FactorTrend.IMPROVING


def test_missing_oil_series_is_unknown_not_neutral() -> None:
    result = oil_assessment(brent=None)
    assert result.assessment.direction is FactorDirection.UNKNOWN
    assert result.assessment.availability is Availability.UNAVAILABLE
    assert result.assessment.missing_requirements


# --- section 52: credit -----------------------------------------------------


def test_equities_falling_with_calm_credit_is_a_drawdown() -> None:
    result = credit_assessment(
        hy_spread_pct=3.4, hy_change_30d_pct=0.05, freshness="FRESH"
    )
    assert result.assessment.direction is FactorDirection.POSITIVE
    assert "non un stress systémique confirmé" in " ".join(result.chain)


def test_widening_spreads_raise_the_risk_level() -> None:
    calm = credit_assessment(hy_spread_pct=3.4, hy_change_30d_pct=0.05, freshness="FRESH")
    widening = credit_assessment(
        hy_spread_pct=5.2, hy_change_30d_pct=1.1, freshness="FRESH"
    )
    assert widening.assessment.direction is FactorDirection.NEGATIVE
    assert widening.assessment.impact is FactorImpact.HIGH
    assert calm.assessment.impact is not FactorImpact.HIGH


def test_high_and_widening_spreads_are_the_systemic_signature() -> None:
    result = credit_assessment(
        hy_spread_pct=7.4, hy_change_30d_pct=1.8, freshness="FRESH"
    )
    assert result.assessment.impact is FactorImpact.VERY_HIGH
    assert "stress" in " ".join(result.chain)


def test_missing_credit_series_is_unknown_not_neutral() -> None:
    result = credit_assessment(hy_spread_pct=None)
    assert result.assessment.direction is FactorDirection.UNKNOWN
    assert result.assessment.availability is Availability.UNAVAILABLE


# --- section 8: the curve ---------------------------------------------------


def test_all_three_maturities_are_read_when_available() -> None:
    result = rates_assessment(
        us2y=4.2, us10y=4.6, us30y=4.9, us10y_change_30d_pct=0.1, freshness="FRESH"
    )
    chain = " ".join(result.chain)
    assert "2 ans" in chain and "10 ans" in chain and "30 ans" in chain
    assert "politique monétaire" in chain
    assert "budgétaire" in chain


def test_the_curve_slope_is_reported_when_both_ends_exist() -> None:
    result = rates_assessment(us2y=4.2, us10y=4.6, us10y_change_30d_pct=0.0)
    assert "pente 10-2" in result.assessment.rationale


def test_rising_yields_tighten_conditions() -> None:
    result = rates_assessment(us2y=4.8, us10y=5.0, us10y_change_30d_pct=0.6)
    assert result.assessment.direction is FactorDirection.NEGATIVE
    assert "resserrent" in " ".join(result.chain)


# --- section 53/55: multi-signal and insufficient data ----------------------


def test_a_single_negative_link_does_not_produce_the_strongest_regime() -> None:
    verdict = confront(
        [
            rates_assessment(
                us2y=4.8, us10y=5.0, us10y_change_30d_pct=0.6, freshness="FRESH"
            )
        ]
    )
    assert verdict.regime is MacroRegime.RESTRICTIVE
    assert verdict.regime is not MacroRegime.STRONGLY_RESTRICTIVE


def test_no_usable_variable_is_unknown_and_lists_what_is_missing() -> None:
    verdict = confront(
        [oil_assessment(brent=None), credit_assessment(hy_spread_pct=None)]
    )
    assert verdict.regime is MacroRegime.UNKNOWN
    assert set(verdict.missing) == {"Énergie", "Crédit"}


def test_calm_credit_tempers_a_restrictive_rate_reading() -> None:
    """Credit staying calm is exactly the counter-evidence section 20 wants."""

    verdict = confront(
        [
            rates_assessment(
                us2y=4.8, us10y=5.0, us10y_change_30d_pct=0.6, freshness="FRESH"
            ),
            credit_assessment(hy_spread_pct=3.2, hy_change_30d_pct=0.0, freshness="FRESH"),
        ]
    )
    assert verdict.disagreeing == ["Crédit"] or "Crédit" in verdict.disagreeing


def test_confrontation_never_averages_contradictory_links() -> None:
    verdict = confront(
        [
            oil_assessment(brent=110.0, change_30d_pct=25.0, freshness="FRESH"),
            rates_assessment(us2y=3.5, us10y=3.4, us10y_change_30d_pct=-0.8, freshness="FRESH"),
        ]
    )
    assert verdict.regime is MacroRegime.CONFLICTING
    assert "moyenne" in verdict.to_dict()["methodology"]


def test_a_measured_variable_is_never_dropped_for_its_freshness_label() -> None:
    """Excluding a degraded reading silently turned a verdict into UNKNOWN."""

    verdict = confront(
        [rates_assessment(us2y=4.8, us10y=5.0, us10y_change_30d_pct=0.6)]
    )
    assert verdict.regime is MacroRegime.RESTRICTIVE
    assert "dégradée" in verdict.rationale


def test_oil_reads_wti_when_brent_is_unavailable() -> None:
    """WTI arrives without an API key; requiring Brent made this unusable."""

    result = oil_assessment(wti=78.0, change_30d_pct=21.0, freshness="FRESH")
    assert result.assessment.direction is FactorDirection.NEGATIVE
    assert "WTI" in result.assessment.rationale


def test_brent_is_preferred_when_both_benchmarks_exist() -> None:
    result = oil_assessment(brent=82.0, wti=78.0, change_30d_pct=1.0, freshness="FRESH")
    assert "Brent" in result.assessment.rationale


def test_no_benchmark_at_all_is_unavailable() -> None:
    result = oil_assessment(brent=None, wti=None)
    assert result.assessment.availability is Availability.UNAVAILABLE

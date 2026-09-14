"""Section 16: direction, impact, trend and confidence must stay independent."""

from crypto_intel.engines.factor_semantics import (
    FactorDirection,
    FactorImpact,
    FactorTrend,
    event_assessment,
    flow_assessment,
    positioning_assessment,
    positioning_from_leverage_state,
    technical_assessment,
    volatility_assessment,
)


class Flow:
    """Minimal stand-in for InstitutionalFlowAnalysis."""

    def __init__(self, regime, recent, reversal="NONE", sessions=20, available=61):
        self.regime_total_musd = regime
        self.rolling_5_sessions_musd = recent
        self.regime_sessions = sessions
        self.flow_reversal = reversal
        self.sessions_available = available
        self.freshness = "TODAY"
        self.evidence_ids = ["BTC_IBIT_20260913"]


# --- events -----------------------------------------------------------------


def test_future_fomc_unknown_without_expectations() -> None:
    result = event_assessment(title="Décision de la Fed", importance="CRITICAL")
    assert result.direction is FactorDirection.UNKNOWN
    assert "non valorisée" in result.rationale


def test_future_fomc_can_be_very_high_impact() -> None:
    result = event_assessment(title="Décision de la Fed", importance="CRITICAL")
    assert result.impact is FactorImpact.VERY_HIGH


def test_unknown_is_not_neutral() -> None:
    """An unheld event and a measured balance are different statements."""

    unheld = event_assessment(title="Décision de la Fed", importance="CRITICAL")
    balanced = technical_assessment(
        bullish_timeframes=["1d"], bearish_timeframes=["4h"]
    )
    assert unheld.direction is FactorDirection.UNKNOWN
    assert balanced.direction is FactorDirection.NEUTRAL
    assert unheld.direction is not balanced.direction


def test_impact_independent_from_direction() -> None:
    """Very high impact with no direction at all must be expressible."""

    result = event_assessment(title="Décision de la Fed", importance="CRITICAL")
    assert result.direction is FactorDirection.UNKNOWN
    assert result.impact is FactorImpact.VERY_HIGH
    assert result.confidence == 0.0


def test_a_priced_event_may_carry_a_direction() -> None:
    result = event_assessment(
        title="Décision de la Fed",
        importance="CRITICAL",
        priced_direction=FactorDirection.POSITIVE,
    )
    assert result.direction is FactorDirection.POSITIVE
    assert "horodatée" in result.rationale


# --- institutional flows ----------------------------------------------------


def test_etf_positive_long_term_deteriorating_short_term() -> None:
    """The reported BTC case: +3 310 M$ over twenty sessions, −288 over five."""

    result = flow_assessment(Flow(3310.1, -288.1, reversal="INFLOW_TO_OUTFLOW"))
    assert result.direction is FactorDirection.POSITIVE
    assert result.trend is FactorTrend.DETERIORATING
    assert "+3 310.1 M$" in result.rationale
    assert "-288.1 M$" in result.rationale


def test_etf_negative_flow_not_labeled_positive_without_context() -> None:
    result = flow_assessment(Flow(-1200.0, -300.0))
    assert result.direction is FactorDirection.NEGATIVE
    assert result.trend is FactorTrend.STABLE


def test_etf_reversal_state() -> None:
    improving = flow_assessment(Flow(-1200.0, 150.0, reversal="OUTFLOW_TO_INFLOW"))
    assert improving.direction is FactorDirection.NEGATIVE
    assert improving.trend is FactorTrend.IMPROVING


def test_etf_steady_inflow_is_stable_and_high_impact() -> None:
    result = flow_assessment(Flow(3310.1, 400.0))
    assert result.direction is FactorDirection.POSITIVE
    assert result.trend is FactorTrend.STABLE
    assert result.impact is FactorImpact.HIGH


def test_a_contradicted_regime_is_not_high_impact() -> None:
    result = flow_assessment(Flow(3310.1, -288.1, reversal="INFLOW_TO_OUTFLOW"))
    assert result.impact is FactorImpact.MODERATE


# --- positioning ------------------------------------------------------------


def test_oi_down_price_down() -> None:
    result = positioning_assessment(price_change_pct=-2.0, oi_change_pct=-3.0)
    assert result.direction is FactorDirection.NEGATIVE
    assert "abandonnent" in result.rationale


def test_oi_down_price_up() -> None:
    """Short covering is not a bearish confirmation."""

    result = positioning_assessment(price_change_pct=2.0, oi_change_pct=-3.0)
    assert result.direction is FactorDirection.NEUTRAL
    assert "rachètent" in result.rationale


def test_oi_up_price_down() -> None:
    result = positioning_assessment(price_change_pct=-2.0, oi_change_pct=4.0)
    assert result.direction is FactorDirection.NEGATIVE
    assert "vendeuses" in result.rationale


def test_oi_up_price_up() -> None:
    result = positioning_assessment(price_change_pct=2.0, oi_change_pct=4.0)
    assert result.direction is FactorDirection.POSITIVE
    assert "acheteurs participent" in result.rationale


def test_positioning_is_unknown_without_both_series() -> None:
    result = positioning_assessment(price_change_pct=-2.0, oi_change_pct=None)
    assert result.direction is FactorDirection.UNKNOWN


def test_extreme_funding_raises_positioning_impact() -> None:
    calm = positioning_assessment(price_change_pct=-1.0, oi_change_pct=-1.0)
    extreme = positioning_assessment(
        price_change_pct=-1.0, oi_change_pct=-1.0, funding_state="EXTREME_POSITIVE"
    )
    assert calm.impact is FactorImpact.MODERATE
    assert extreme.impact is FactorImpact.HIGH


# --- volatility -------------------------------------------------------------


def test_bollinger_no_direction() -> None:
    result = volatility_assessment(squeeze=True)
    assert result.direction is FactorDirection.UNKNOWN
    assert result.impact_on_direction == "NONE"


def test_bollinger_high_movement() -> None:
    assert volatility_assessment(squeeze=True).impact is FactorImpact.HIGH
    assert volatility_assessment(squeeze=False).impact is FactorImpact.LOW


# --- technical --------------------------------------------------------------


def test_single_timeframe_not_high_impact_without_confirmation() -> None:
    single = technical_assessment(bullish_timeframes=["1d"], bearish_timeframes=[])
    assert single.direction is FactorDirection.POSITIVE
    assert single.impact is FactorImpact.MODERATE


def test_multiple_independent_confirmations_raise_impact() -> None:
    converging = technical_assessment(
        bullish_timeframes=["1w", "1d", "4h"],
        bearish_timeframes=[],
        volume_confirms=True,
    )
    assert converging.impact is FactorImpact.VERY_HIGH


def test_no_timeframe_means_unknown_not_a_regime_label() -> None:
    """The ETH case: zero agreeing timeframes produced BULLISH at confidence 0."""

    result = technical_assessment(bullish_timeframes=[], bearish_timeframes=[])
    assert result.direction is FactorDirection.UNKNOWN
    assert result.confidence == 0.0
    assert result.impact is FactorImpact.LOW


def test_conflicting_timeframes_are_low_impact() -> None:
    result = technical_assessment(
        bullish_timeframes=["1d"], bearish_timeframes=["4h"]
    )
    assert result.direction is FactorDirection.NEUTRAL
    assert result.impact is FactorImpact.LOW


def test_leverage_states_map_the_four_quadrants() -> None:
    """The pressure engine already reads price and OI jointly; reuse its label."""

    cases = {
        "NEW_LONGS": FactorDirection.POSITIVE,
        "NEW_SHORTS": FactorDirection.NEGATIVE,
        "LONG_LIQUIDATION": FactorDirection.NEGATIVE,
        "SHORT_COVERING": FactorDirection.NEUTRAL,
    }
    for state, expected in cases.items():
        assert positioning_from_leverage_state(state).direction is expected


def test_short_covering_is_never_read_as_a_buy_signal() -> None:
    result = positioning_from_leverage_state("SHORT_COVERING")
    assert result.direction is not FactorDirection.POSITIVE
    assert "ne confirme pas" in result.rationale


def test_an_unmapped_leverage_state_is_unknown_not_neutral() -> None:
    result = positioning_from_leverage_state("SOMETHING_ELSE")
    assert result.direction is FactorDirection.UNKNOWN



class Component:
    """Stand-in for PressureFamilyContribution."""

    def __init__(self, family, direction, score, *, available=True, detail="mesure"):
        self.family = family
        self.label = family
        self.direction = direction
        self.normalized_score = score
        self.available = available
        self.freshness = "LIVE"
        self.source = "Binance"
        self.detail = detail
        self.explanation = detail
        self.confidence = 0.9


def test_pressure_components_keep_the_direction_the_engine_measured() -> None:
    """The engine names directions BUY/SELL; the layer names them POSITIVE/NEGATIVE."""

    from crypto_intel.engines.factor_semantics import pressure_component_assessment

    cases = {
        "STRONG_SELL": FactorDirection.NEGATIVE,
        "SELL": FactorDirection.NEGATIVE,
        "SLIGHT_SELL": FactorDirection.NEGATIVE,
        "NEUTRAL": FactorDirection.NEUTRAL,
        "SLIGHT_BUY": FactorDirection.POSITIVE,
        "BUY": FactorDirection.POSITIVE,
        "STRONG_BUY": FactorDirection.POSITIVE,
    }
    for raw, expected in cases.items():
        got = pressure_component_assessment(Component("funding", raw, -40))
        assert got.direction is expected, raw


def test_a_measured_component_is_never_reported_as_unknown() -> None:
    from crypto_intel.engines.factor_semantics import pressure_component_assessment

    result = pressure_component_assessment(Component("spot", "SELL", -30))
    assert result.direction is FactorDirection.NEGATIVE
    assert result.availability.value == "AVAILABLE"
    assert result.provider == "Binance"
    assert len(result.causal_chain) >= 3


def test_an_unavailable_component_states_what_is_missing() -> None:
    from crypto_intel.engines.factor_semantics import pressure_component_assessment

    result = pressure_component_assessment(
        Component("whales", "UNAVAILABLE", None, available=False, detail="pas de flux")
    )
    assert result.direction is FactorDirection.UNKNOWN
    assert result.availability.value == "UNAVAILABLE"
    assert result.missing_requirements

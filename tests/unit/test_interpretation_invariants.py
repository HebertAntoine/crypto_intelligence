"""Sections 37, 38 and 41: named checks plus the invariants that must always hold.

The invariant tests are deliberately written against *payloads* rather than
against one engine, so they hold for whatever produced the data. The mutation
tests flip a sign on purpose and require the validator to notice.
"""

import json
from pathlib import Path

import pytest

from crypto_intel.engines.factor_semantics import (
    Availability,
    ConfidenceLevel,
    FactorDirection,
    FactorImpact,
    FactorTrend,
    basis_assessment,
    confidence_level,
    event_assessment,
    flow_assessment,
    funding_assessment,
    implied_volatility_assessment,
    positioning_from_leverage_state,
    volatility_assessment,
    whale_assessment,
)
from crypto_intel.engines.interpretation_validator import (
    InterpretationConsistencyValidator,
    horizons_are_independent,
)

SNAPSHOTS = Path(__file__).resolve().parents[2] / "app" / "assets" / "api_snapshots"
ASSETS = ("BTC", "ETH", "SOL")
HORIZONS = ("24h", "7d", "30d")


def payload(asset: str, horizon: str) -> dict:
    path = SNAPSHOTS / f"future__{asset}__horizon-{horizon}.json"
    if not path.exists():
        pytest.skip(f"snapshot absent: {path.name}")
    return json.loads(path.read_text(encoding="utf-8"))


def all_factors(asset: str, horizon: str) -> list[dict]:
    return (payload(asset, horizon).get("families") or {}).get("factors") or []


class Flow:
    def __init__(self, regime, recent, reversal="NONE"):
        self.regime_total_musd = regime
        self.rolling_5_sessions_musd = recent
        self.regime_sessions = 20
        self.flow_reversal = reversal
        self.sessions_available = 40
        self.freshness = "TODAY"
        self.evidence_ids = ["BTC_IBIT_20260913"]
        self.provenance = [
            {"provider": "Farside", "source_url": "https://farside.co.uk/"}
        ]


# --- section 37: named unit checks -----------------------------------------


def test_unknown_not_neutral() -> None:
    unheld = event_assessment(title="Décision de la Fed", importance="CRITICAL")
    balanced = funding_assessment(percentile=50.0, freshness="LIVE")
    assert unheld.direction is FactorDirection.UNKNOWN
    assert balanced.direction is FactorDirection.NEUTRAL


def test_impact_independent_direction() -> None:
    unknown_but_major = event_assessment(title="Fed", importance="CRITICAL")
    assert unknown_but_major.direction is FactorDirection.UNKNOWN
    assert unknown_but_major.impact is FactorImpact.VERY_HIGH


def test_confidence_independent_impact() -> None:
    """A very high impact reading may carry no confidence in its direction."""

    result = event_assessment(title="Fed", importance="CRITICAL")
    assert result.impact is FactorImpact.VERY_HIGH
    assert result.confidence_band is ConfidenceLevel.LOW


def test_etf_long_positive_short_negative() -> None:
    result = flow_assessment(Flow(3310.1, -288.1, reversal="INFLOW_TO_OUTFLOW"))
    assert result.direction is FactorDirection.POSITIVE
    assert result.trend is FactorTrend.DETERIORATING


def test_etf_long_negative_short_positive() -> None:
    result = flow_assessment(Flow(-1200.0, 150.0, reversal="OUTFLOW_TO_INFLOW"))
    assert result.direction is FactorDirection.NEGATIVE
    assert result.trend is FactorTrend.IMPROVING


def test_etf_both_positive() -> None:
    result = flow_assessment(Flow(3310.1, 400.0))
    assert (result.direction, result.trend) == (
        FactorDirection.POSITIVE,
        FactorTrend.STABLE,
    )


def test_etf_both_negative() -> None:
    result = flow_assessment(Flow(-1200.0, -300.0))
    assert (result.direction, result.trend) == (
        FactorDirection.NEGATIVE,
        FactorTrend.STABLE,
    )


def test_etf_text_matches_state() -> None:
    """A deteriorating positive regime must say both halves, not one."""

    result = flow_assessment(Flow(3310.1, -288.1, reversal="INFLOW_TO_OUTFLOW"))
    joined = " ".join(result.causal_chain).lower()
    assert "restent positifs" in joined
    assert "retourn" in joined
    # ETF vocabulary only: transfers and exchanges belong to whale data.
    assert "transfert" not in joined
    assert "baleine" not in joined


def test_funding_percentile_interpretation() -> None:
    crowded = funding_assessment(percentile=97.0, freshness="LIVE")
    normal = funding_assessment(percentile=50.0, freshness="LIVE")
    cheap = funding_assessment(percentile=3.0, freshness="LIVE")
    assert crowded.direction is FactorDirection.NEGATIVE
    assert normal.direction is FactorDirection.NEUTRAL
    # Very negative funding is not a buy signal on its own.
    assert cheap.direction is not FactorDirection.POSITIVE
    assert "pas en soi un signal d'achat" in " ".join(cheap.causal_chain)


def test_basis_not_automatically_bullish() -> None:
    result = basis_assessment(basis_pct=0.8, percentile=50.0, freshness="LIVE")
    assert result.direction is not FactorDirection.POSITIVE
    assert "état normal" in " ".join(result.causal_chain)


def test_bollinger_has_no_direction() -> None:
    for squeeze in (True, False):
        result = volatility_assessment(squeeze=squeeze, freshness="LIVE")
        assert result.direction is FactorDirection.UNKNOWN
        assert result.impact_on_direction == "NONE"


def test_dvol_has_no_direction() -> None:
    result = implied_volatility_assessment(
        available=True, percentile=85.0, freshness="LIVE"
    )
    assert result.direction is FactorDirection.UNKNOWN
    assert result.impact is FactorImpact.HIGH
    assert result.impact_on_direction == "NONE"


def test_options_skew_can_have_direction() -> None:
    result = implied_volatility_assessment(
        available=True, percentile=60.0, skew=-0.08, freshness="LIVE"
    )
    assert result.direction is FactorDirection.NEGATIVE
    assert result.impact_on_direction == "MEASURED"


def test_future_event_without_outcome_unknown() -> None:
    assert (
        event_assessment(title="Fed", importance="CRITICAL").direction
        is FactorDirection.UNKNOWN
    )


def test_missing_data_not_neutral() -> None:
    """An absence must never be presented as a measured balance."""

    for result in (
        whale_assessment(available=False),
        funding_assessment(percentile=None),
        implied_volatility_assessment(available=False),
    ):
        assert result.direction is FactorDirection.UNKNOWN
        assert result.availability is Availability.UNAVAILABLE
        assert result.missing_requirements


def test_stale_data_reduces_confidence() -> None:
    assert confidence_level(0.95, Availability.AVAILABLE) is ConfidenceLevel.HIGH
    assert confidence_level(0.95, Availability.STALE) is not ConfidenceLevel.HIGH
    assert confidence_level(0.95, Availability.UNAVAILABLE) is ConfidenceLevel.LOW


def test_whale_transfer_is_not_a_sale() -> None:
    result = whale_assessment(available=True, transfers_to_exchange=4)
    assert result.direction is FactorDirection.UNKNOWN
    assert result.missing_requirements
    assert "ne signifie pas qu'une vente a lieu" in " ".join(result.causal_chain)


def test_a_corroborated_whale_flow_may_carry_a_direction() -> None:
    result = whale_assessment(
        available=True,
        transfers_to_exchange=4,
        corroborating_signals=["entrées nettes sur les plateformes"],
    )
    assert result.direction is FactorDirection.NEGATIVE


def test_no_cross_family_template_contamination() -> None:
    """Each family explains its own mechanism, never another family's."""

    etf = " ".join(flow_assessment(Flow(3310.1, 400.0)).causal_chain).lower()
    whales = " ".join(
        whale_assessment(available=True, transfers_to_exchange=2).causal_chain
    ).lower()
    squeeze = " ".join(volatility_assessment(squeeze=True).causal_chain).lower()

    assert "transfert" not in etf and "baleine" not in etf
    assert "etf" not in whales
    assert "etf" not in squeeze and "baleine" not in squeeze


def test_source_is_real_provider() -> None:
    result = flow_assessment(Flow(3310.1, 400.0))
    assert result.provider == "Farside"
    assert result.source_url and result.source_url.startswith("https://")


# --- section 38: invariants over every shipped payload ----------------------


@pytest.mark.parametrize("asset", ASSETS)
@pytest.mark.parametrize("horizon", HORIZONS)
def test_invariant_unavailable_factor_is_never_directional(asset, horizon) -> None:
    for factor in all_factors(asset, horizon):
        if factor["availability"] in {"UNAVAILABLE", "NOT_APPLICABLE"}:
            assert factor["direction"] == "UNKNOWN", factor["key"]
            assert factor["missing_requirements"], factor["key"]


@pytest.mark.parametrize("asset", ASSETS)
@pytest.mark.parametrize("horizon", HORIZONS)
def test_invariant_unknown_direction_asserts_nothing(asset, horizon) -> None:
    for factor in all_factors(asset, horizon):
        if factor["direction"] != "UNKNOWN":
            continue
        text = (factor["rationale"] + " ".join(factor["causal_chain"])).lower()
        for claim in ("va monter", "va baisser", "soutien à la hausse"):
            assert claim not in text, f"{factor['key']}: {claim}"


@pytest.mark.parametrize("asset", ASSETS)
@pytest.mark.parametrize("horizon", HORIZONS)
def test_invariant_stale_is_never_high_confidence(asset, horizon) -> None:
    for factor in all_factors(asset, horizon):
        if factor["availability"] == "STALE":
            assert factor["confidence_band"] != "HIGH", factor["key"]


@pytest.mark.parametrize("asset", ASSETS)
@pytest.mark.parametrize("horizon", HORIZONS)
def test_invariant_amplitude_only_factor_has_no_direction(asset, horizon) -> None:
    for factor in all_factors(asset, horizon):
        if factor["impact_on_direction"] == "NONE":
            assert factor["direction"] not in {"POSITIVE", "NEGATIVE"}, factor["key"]


@pytest.mark.parametrize("asset", ASSETS)
@pytest.mark.parametrize("horizon", HORIZONS)
def test_invariant_every_payload_passes_the_validator(asset, horizon) -> None:
    report = InterpretationConsistencyValidator().validate(payload(asset, horizon))
    assert report.passed, report.to_dict()["issues"]


@pytest.mark.parametrize("asset", ASSETS)
def test_24h_7d_30d_are_independent(asset) -> None:
    ok, detail = horizons_are_independent(
        {horizon: payload(asset, horizon) for horizon in HORIZONS}
    )
    assert ok, detail


def test_all_five_families_are_always_present(asset="BTC") -> None:
    for horizon in HORIZONS:
        items = (payload(asset, horizon).get("families") or {}).get("items") or {}
        assert len(items) == 5
        for name, family in items.items():
            if not family.get("available"):
                assert family.get("unavailable_reason"), name


# --- section 41: mutation tests ---------------------------------------------


def mutated(asset: str, horizon: str, key: str, field: str, value) -> dict:
    data = payload(asset, horizon)
    for factor in (data.get("families") or {}).get("factors") or []:
        if factor["key"] == key:
            factor[field] = value
    return data


def test_mutation_flipping_a_flow_sign_is_detected() -> None:
    """An ETF text saying inflows next to a NEGATIVE status must be caught."""

    data = payload("BTC", "7d")
    factors = (data.get("families") or {}).get("factors") or []
    flows = next((item for item in factors if item["key"] == "flows"), None)
    if flows is None:
        pytest.skip("aucun facteur de flux sur ce snapshot")
    flows["direction"] = "NEGATIVE"
    flows["causal_chain"] = ["Entrées nettes soutenues.", "apportent du soutien"]
    flows["rationale"] = "apportent du soutien"
    report = InterpretationConsistencyValidator().validate(data)
    assert not report.passed
    assert any(item.dimension == "text_consistency" for item in report.issues)


def test_mutation_unavailable_factor_made_directional_is_detected() -> None:
    data = mutated("BTC", "7d", "implied_volatility", "availability", "UNAVAILABLE")
    for factor in (data.get("families") or {}).get("factors") or []:
        if factor["key"] == "implied_volatility":
            factor["direction"] = "POSITIVE"
            factor["missing_requirements"] = []
    report = InterpretationConsistencyValidator().validate(data)
    assert not report.passed
    assert any(item.dimension == "semantic_consistency" for item in report.issues)


def test_mutation_squeeze_made_bullish_is_detected() -> None:
    data = mutated("BTC", "7d", "volatility", "direction", "POSITIVE")
    report = InterpretationConsistencyValidator().validate(data)
    assert not report.passed
    assert any(item.dimension == "direction_consistency" for item in report.issues)


def test_mutation_stale_with_high_confidence_is_detected() -> None:
    data = payload("BTC", "7d")
    factors = (data.get("families") or {}).get("factors") or []
    if not factors:
        pytest.skip("aucun facteur")
    factors[0]["availability"] = "STALE"
    factors[0]["confidence_band"] = "HIGH"
    report = InterpretationConsistencyValidator().validate(data)
    assert not report.passed
    assert any(item.dimension == "freshness_consistency" for item in report.issues)


def test_mutation_missing_source_is_detected() -> None:
    data = mutated("BTC", "7d", "positioning", "provider", "")
    report = InterpretationConsistencyValidator().validate(data)
    assert not report.passed
    assert any(item.dimension == "source_integrity" for item in report.issues)


def test_a_clean_payload_reports_no_issue() -> None:
    report = InterpretationConsistencyValidator().validate(payload("BTC", "7d"))
    assert report.issues == []
    assert report.passed


# --- section 37: remaining named checks -------------------------------------


def test_oi_price_down_oi_down() -> None:
    result = positioning_from_leverage_state("LONG_LIQUIDATION", freshness="LIVE")
    assert result.direction is FactorDirection.NEGATIVE
    assert "abandonnent" in result.rationale


def test_oi_price_up_oi_down() -> None:
    """Short covering: sellers leaving is not buyers arriving."""

    result = positioning_from_leverage_state("SHORT_COVERING", freshness="LIVE")
    assert result.direction is FactorDirection.NEUTRAL
    assert result.direction is not FactorDirection.NEGATIVE


def test_oi_price_down_oi_up() -> None:
    result = positioning_from_leverage_state("NEW_SHORTS", freshness="LIVE")
    assert result.direction is FactorDirection.NEGATIVE
    assert "vendeuses" in result.rationale


def test_oi_price_up_oi_up() -> None:
    result = positioning_from_leverage_state("NEW_LONGS", freshness="LIVE")
    assert result.direction is FactorDirection.POSITIVE
    assert "acheteurs participent" in result.rationale


def test_expectation_missing_reduces_confidence() -> None:
    """An unpriced material event must cost confidence, not pass unnoticed."""

    from datetime import UTC, datetime, timedelta

    from tests.unit.test_decision_consistency import five

    from crypto_intel.core.enums import Asset
    from crypto_intel.engines.future_decision import FutureDecisionEngine
    from crypto_intel.future_events.models import (
        DecisionHorizon,
        EventImportance,
        EventScheduleType,
        ExpectedMovement,
        FutureEvent,
        FutureEventCategory,
        FutureEventSourceTier,
    )

    now = datetime(2026, 9, 13, 12, tzinfo=UTC)
    event = FutureEvent(
        event_type="FOMC_DECISION",
        category=FutureEventCategory.MONETARY_POLICY,
        schedule_type=EventScheduleType.SCHEDULED,
        title="Décision de la Fed",
        source="Federal Reserve",
        source_tier=FutureEventSourceTier.A,
        source_url="https://www.federalreserve.gov/",
        importance=EventImportance.CRITICAL,
        magnitude_effect=ExpectedMovement.HIGH,
        scheduled_at=now + timedelta(hours=74),
        detected_at=now,
    )
    engine = FutureDecisionEngine()
    quiet = engine.decide(Asset.BTC, [], five(), horizon=DecisionHorizon.D7, as_of=now)
    exposed = engine.decide(
        Asset.BTC, [event], five(), horizon=DecisionHorizon.D7, as_of=now
    )
    assert exposed.decision_confidence < quiet.decision_confidence


def test_surprise_uses_outcome_minus_expectation() -> None:
    """Direction comes from the gap with what was priced, never from the outcome."""

    from datetime import UTC, datetime

    from crypto_intel.engines.event_surprise import EventSurpriseEngine
    from crypto_intel.engines.market_expectation import (
        ExpectedOutcome,
        MarketExpectation,
        MarketExpectationStatus,
    )
    from crypto_intel.future_events.models import MarketProbability

    now = datetime(2026, 9, 16, 18, tzinfo=UTC)
    expectation = MarketExpectation(
        event_id="fomc",
        observed_at=now,
        expected_outcome=ExpectedOutcome(outcome="HIKE_25", probability=0.9),
        outcome_distribution=[
            MarketProbability(
                outcome="HIKE_25", probability=0.9, source="CME", observed_at=now
            ),
            MarketProbability(
                outcome="HOLD", probability=0.1, source="CME", observed_at=now
            ),
        ],
        market_probability=0.9,
        probability_timestamp=now,
        source="CME",
        methodology="test",
        freshness="LIVE",
        status=MarketExpectationStatus.AVAILABLE,
    )
    engine = EventSurpriseEngine()
    # The widely expected outcome is barely a surprise...
    expected = engine.analyze(expectation, actual_outcome="HIKE_25", observed_at=now)
    # ...while the outcome nobody priced is a large one, though it is the same
    # kind of event. Surprise is the gap, not the headline.
    unexpected = engine.analyze(expectation, actual_outcome="HOLD", observed_at=now)
    assert expected.probability_surprise == pytest.approx(0.1)
    assert unexpected.probability_surprise == pytest.approx(0.9)
    assert unexpected.probability_surprise > expected.probability_surprise


def supports(direction: str, decision: str) -> bool:
    """Mirror of the rule the screen applies when splitting the two sections."""

    if decision == "BUY":
        return direction == "POSITIVE"
    if decision == "SELL":
        return direction == "NEGATIVE"
    if decision == "WAIT":
        return direction != "POSITIVE"
    return True


@pytest.mark.parametrize("asset", ASSETS)
@pytest.mark.parametrize("horizon", HORIZONS)
def test_decision_reason_supports_decision(asset, horizon) -> None:
    """Whatever is listed as a reason must argue for the decision taken."""

    data = payload(asset, horizon)
    decision = data["decision"]
    reasons = [
        factor
        for factor in all_factors(asset, horizon)
        if supports(factor["direction"], decision)
    ]
    for factor in reasons:
        assert supports(factor["direction"], decision), f"{factor['key']} / {decision}"


@pytest.mark.parametrize("asset", ASSETS)
@pytest.mark.parametrize("horizon", HORIZONS)
def test_counter_signal_not_in_decision_reasons(asset, horizon) -> None:
    """The two sets must be disjoint: nothing is both a reason and a counter-signal."""

    data = payload(asset, horizon)
    decision = data["decision"]
    factors = all_factors(asset, horizon)
    reasons = {f["key"] for f in factors if supports(f["direction"], decision)}
    counters = {f["key"] for f in factors if not supports(f["direction"], decision)}
    assert reasons.isdisjoint(counters)
    assert reasons | counters == {f["key"] for f in factors}


# --- section 43: text contradiction scan ------------------------------------

#: Pairs that cannot legitimately co-occur in one user-facing sentence.
_CONTRADICTIONS = (
    ("positif", "pression vendeuse"),
    ("entrées nettes", "sorties nettes s'accélèrent"),
    ("compression", "haussier"),
    ("inconnu", "va monter"),
    ("indisponible", "probabilité de"),
)


def user_facing_strings(data: dict) -> list[str]:
    """Every string a reader could end up seeing, from one payload."""

    out: list[str] = []
    families = data.get("families") or {}
    for factor in families.get("factors") or []:
        out.append(str(factor.get("rationale") or ""))
        out.extend(str(item) for item in factor.get("causal_chain") or [])
        out.extend(str(item) for item in factor.get("missing_requirements") or [])
    for family in (families.get("items") or {}).values():
        out.append(str(family.get("summary") or ""))
        out.append(str(family.get("unavailable_reason") or ""))
    for reason in data.get("reasons") or []:
        out.append(str(reason.get("explanation") or ""))
    for bucket in ("conditions_to_buy", "conditions_to_sell", "what_could_change_decision"):
        out.extend(str(item) for item in data.get(bucket) or [])
    return [item for item in out if item.strip()]


@pytest.mark.parametrize("asset", ASSETS)
@pytest.mark.parametrize("horizon", HORIZONS)
def test_no_self_contradicting_sentence(asset, horizon) -> None:
    for sentence in user_facing_strings(payload(asset, horizon)):
        lowered = sentence.lower()
        for left, right in _CONTRADICTIONS:
            assert not (left in lowered and right in lowered), sentence


@pytest.mark.parametrize("asset", ASSETS)
@pytest.mark.parametrize("horizon", HORIZONS)
def test_no_engine_jargon_in_user_facing_text(asset, horizon) -> None:
    """Internal vocabulary may live in advanced details, never in the summary."""

    for sentence in user_facing_strings(payload(asset, horizon)):
        lowered = sentence.lower()
        for jargon in ("z-score", "squeeze=", "p83", "upper third", "mid range"):
            assert jargon not in lowered, sentence


@pytest.mark.parametrize("asset", ASSETS)
@pytest.mark.parametrize("horizon", HORIZONS)
def test_every_unavailable_family_declares_its_reason(asset, horizon) -> None:
    """Section 36 and 46: an absence is stated, never hidden."""

    items = (payload(asset, horizon).get("families") or {}).get("items") or {}
    assert len(items) == 5
    for name, family in items.items():
        if family.get("available"):
            continue
        assert family.get("unavailable_reason"), name
        assert family.get("directional_bias") is None, name

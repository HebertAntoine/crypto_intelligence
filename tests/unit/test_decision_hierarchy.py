"""Section 15: what can move the market outranks what merely describes it."""

from datetime import UTC, datetime, timedelta

from tests.unit.test_decision_consistency import five

from crypto_intel.core.enums import Asset
from crypto_intel.engines.decision_hierarchy import (
    PRINCIPAL_FLOOR,
    DriverDirection,
    DriverRole,
    Reading,
    Tier,
    build_hierarchy,
)
from crypto_intel.engines.edge import EdgeState
from crypto_intel.engines.factor_semantics import (
    Availability,
    FactorAssessment,
    FactorDirection,
    FactorImpact,
)
from crypto_intel.engines.future_decision import DecisionAction, FutureDecisionEngine
from crypto_intel.engines.market_radar import AttentionLevel
from crypto_intel.future_events.models import (
    DecisionHorizon,
    DirectionalBias,
    EventImportance,
    EventScheduleType,
    ExpectedMovement,
    FutureEvent,
    FutureEventCategory,
    FutureEventSourceTier,
)

NOW = datetime(2026, 9, 18, 12, tzinfo=UTC)


def event(
    event_type: str,
    *,
    hours: float,
    category: FutureEventCategory = FutureEventCategory.MONETARY_POLICY,
    importance: EventImportance = EventImportance.CRITICAL,
    title: str | None = None,
    surprise: float | None = None,
    actual: object = None,
    metadata: dict | None = None,
) -> FutureEvent:
    return FutureEvent(
        event_type=event_type,
        category=category,
        schedule_type=EventScheduleType.SCHEDULED,
        title=title or event_type,
        source="source officielle",
        source_tier=FutureEventSourceTier.A,
        source_url="https://example.org/",
        importance=importance,
        magnitude_effect=ExpectedMovement.HIGH,
        directional_effect=DirectionalBias.NEUTRAL,
        scheduled_at=NOW + timedelta(hours=hours),
        detected_at=NOW - timedelta(days=10),
        last_updated=NOW,
        confidence=1.0,
        surprise=surprise,
        actual_value=actual,
        metadata=metadata or {},
    )


def factor(
    key: str,
    direction: FactorDirection = FactorDirection.POSITIVE,
    *,
    impact: FactorImpact = FactorImpact.MODERATE,
    confidence: float = 0.7,
    availability: Availability = Availability.AVAILABLE,
    rationale: str = "",
) -> FactorAssessment:
    return FactorAssessment(
        key=key,
        label=key,
        direction=direction,
        impact=impact,
        confidence=confidence,
        freshness="HOUR_1",
        availability=availability,
        rationale=rationale,
        missing_requirements=(
            ["Source non configurée."] if availability is Availability.UNAVAILABLE else []
        ),
    )


def healthy_market() -> list[FactorAssessment]:
    return [
        factor("flows", impact=FactorImpact.HIGH, confidence=0.8),
        factor("spot", confidence=0.7),
        factor("positioning", FactorDirection.NEUTRAL, confidence=0.7),
        factor("technical", confidence=0.7),
        factor("rates", FactorDirection.NEUTRAL, confidence=0.6),
        factor("energy", FactorDirection.NEUTRAL, confidence=0.6),
        factor("credit", FactorDirection.NEUTRAL, confidence=0.6),
        factor("whales", FactorDirection.UNKNOWN, availability=Availability.UNAVAILABLE),
    ]


def hierarchy(factors, events=(), *, horizon=DecisionHorizon.D7, action="WAIT", **kwargs):
    return build_hierarchy(
        asset=Asset.BTC,
        horizon=horizon,
        action=action,
        factors=list(factors),
        events=list(events),
        now=NOW,
        **kwargs,
    )


# --- TEST 1: an imminent Fed outranks a bullish chart ------------------------


def test_fed_in_eight_hours_leads_over_a_bullish_trend():
    result = hierarchy(
        [factor("technical", impact=FactorImpact.HIGH, confidence=0.9)],
        [event("FOMC_DECISION", hours=8)],
    )

    assert result.primary is not None
    assert result.primary.key == "FOMC_DECISION"
    assert result.home_factors()[0].key == "FOMC_DECISION"
    trend = next(d for d in result.drivers if d.key == "technical")
    assert result.primary.counted_weight > 2 * trend.counted_weight


# --- TEST 2: a distant Fed does not crush today's flows ---------------------


def test_fed_a_month_away_does_not_override_a_huge_etf_flow():
    for horizon in (DecisionHorizon.D7, DecisionHorizon.D30):
        result = hierarchy(
            [factor("flows", impact=FactorImpact.VERY_HIGH, confidence=0.9)],
            [event("FOMC_DECISION", hours=24 * 29)],
            horizon=horizon,
        )
        assert result.primary is not None
        assert result.primary.key == "flows", horizon


# --- TEST 3: critical and unknown is a complete answer ---------------------


def test_boj_tomorrow_is_critical_with_no_direction():
    result = hierarchy([], [event("BOJ_POLICY_DECISION", hours=20, importance=EventImportance.HIGH)])

    boj = result.drivers[0]
    assert boj.attention is AttentionLevel.CRITICAL
    assert boj.direction is DriverDirection.UNKNOWN
    assert boj.emoji == "🇯🇵"


# --- TEST 4: a surprise changes the weight after publication ----------------


def test_ecb_surprise_is_reweighted_after_publication():
    in_line = hierarchy([], [event("ECB_RATE_DECISION", hours=-3, surprise=0.05, actual="2.00")])
    shock = hierarchy([], [event("ECB_RATE_DECISION", hours=-3, surprise=0.9, actual="2.50")])

    assert shock.drivers[0].counted_weight > 1.8 * in_line.drivers[0].counted_weight
    assert shock.drivers[0].released is True
    # Still no invented direction: nobody stated which way the surprise cuts.
    assert shock.drivers[0].direction is DriverDirection.UNKNOWN


def test_a_stated_outcome_is_the_only_source_of_a_released_direction():
    stated = hierarchy(
        [],
        [event("ECB_RATE_DECISION", hours=-3, surprise=0.9, actual="2.50",
               metadata={"overall_direction": "NEGATIVE"})],
    )
    assert stated.drivers[0].direction is DriverDirection.NEGATIVE


# --- TEST 5 / 6: whales -----------------------------------------------------


def test_a_small_whale_transfer_stays_out_of_the_main_factors():
    small = factor("whales", FactorDirection.UNKNOWN, impact=FactorImpact.LOW, confidence=0.3)
    result = hierarchy([*healthy_market()[:-1], small])

    assert all(item.key != "whales" for item in result.home_factors())
    assert result.whale_status["principal"] is False
    assert result.whale_status["status"] == "Pas de signal majeur confirmé"


def test_a_massive_transfer_to_an_exchange_draws_attention_not_a_sell():
    massive = factor(
        "whales",
        FactorDirection.UNKNOWN,
        impact=FactorImpact.VERY_HIGH,
        confidence=0.8,
        rationale="Dépôts nets vers les plateformes : des ventes sont possibles, sans être confirmées.",
    )
    result = hierarchy([massive, factor("technical", FactorDirection.NEUTRAL)])

    whale = next(d for d in result.drivers if d.key == "whales")
    assert whale.attention in {AttentionLevel.HIGH, AttentionLevel.CRITICAL}
    assert whale.direction is DriverDirection.UNKNOWN
    assert whale in result.home_factors()
    assert "vente non confirmée" in whale.status
    assert result.reading is not Reading.NEGATIVE


def test_the_engine_never_turns_a_whale_deposit_into_a_sell():
    snapshot = five()
    snapshot.normalised_factors = [
        factor(
            "whales", FactorDirection.UNKNOWN, impact=FactorImpact.VERY_HIGH, confidence=0.9
        ).to_dict()
    ]
    decision = FutureDecisionEngine().decide(
        Asset.BTC, [], snapshot, as_of=NOW, edge_state=EdgeState.POSITIVE_EDGE.value
    )
    assert decision.decision is not DecisionAction.SELL


# --- TEST 7: leverage is an amplifier, not a cause --------------------------


def test_extreme_funding_is_presented_as_fragility():
    result = hierarchy(
        [*healthy_market(), factor("funding", FactorDirection.NEGATIVE, impact=FactorImpact.VERY_HIGH, confidence=0.9)]
    )

    funding = next(d for d in result.drivers if d.key == "funding")
    assert funding.tier is Tier.FRAGILITY
    assert funding.role is DriverRole.AMPLIFIER
    assert "amplifier" in funding.status
    # Fragility says how far a move can run, not where it goes.
    assert result.reading is Reading.POSITIVE


# --- TEST 8: why an entry is deferred ---------------------------------------


def test_bullish_chart_under_an_imminent_fed_explains_the_deferral():
    snapshot = five()
    snapshot.normalised_factors = [
        item.to_dict() for item in [factor("technical", impact=FactorImpact.HIGH), *healthy_market()[:-2]]
    ]
    decision = FutureDecisionEngine().decide(
        Asset.BTC,
        [event("FOMC_DECISION", hours=8)],
        snapshot,
        as_of=NOW,
        analysis_uncertainty=0.8,
        edge_state=EdgeState.POSITIVE_EDGE.value,
    )

    assert decision.decision is DecisionAction.WAIT
    text = " ".join(decision.hierarchy.explanation)
    assert decision.hierarchy.primary.key == "FOMC_DECISION"
    assert "Décision de la Fed dans 8 h" in text
    assert "différée" in text
    assert "réaction du marché" in text


# --- TEST 9: a clean market is not held back by a generic sentence ----------


def test_a_clean_positive_market_can_buy_and_says_why():
    snapshot = five()
    snapshot.normalised_factors = [item.to_dict() for item in healthy_market()]
    decision = FutureDecisionEngine().decide(
        Asset.BTC,
        [],
        snapshot,
        as_of=NOW,
        analysis_uncertainty=0.2,
        edge_state=EdgeState.POSITIVE_EDGE.value,
    )

    assert decision.decision is DecisionAction.BUY
    text = " ".join(decision.hierarchy.explanation)
    for vague in ("Confirmation encore insuffisante", "signaux sont mitigés", "reste incertain"):
        assert vague not in text
    assert decision.hierarchy.primary.key == "flows"
    assert text.startswith("💸 Les ETF enregistrent des entrées nettes")
    assert "✅" in text


def test_without_an_edge_the_wait_names_its_cause():
    snapshot = five()
    snapshot.normalised_factors = [item.to_dict() for item in healthy_market()]
    decision = FutureDecisionEngine().decide(
        Asset.BTC,
        [],
        snapshot,
        as_of=NOW,
        analysis_uncertainty=0.2,
        edge_state=EdgeState.NO_MEASURABLE_EDGE.value,
    )

    assert decision.decision is DecisionAction.WAIT
    assert "avantage mesurable" in decision.hierarchy.explanation[-1]


# --- TEST 10: one cause, not three ------------------------------------------


def test_fed_yields_and_credit_are_counted_once():
    result = hierarchy(
        [
            factor("rates", FactorDirection.NEGATIVE, impact=FactorImpact.HIGH, confidence=0.8),
            factor("credit", FactorDirection.NEGATIVE, impact=FactorImpact.HIGH, confidence=0.8),
        ],
        [event("FOMC_DECISION", hours=-4, surprise=0.8, actual="4.75")],
    )

    monetary = [d for d in result.drivers if d.cluster == "monetary_conditions"]
    assert len(monetary) == 3
    counted = [d for d in monetary if d.counted_in is None]
    assert len(counted) == 1
    assert all(d.role is DriverRole.CONSEQUENCE for d in monetary if d.counted_in)
    leader = counted[0].counted_weight
    followers = sum(d.counted_weight for d in monetary if d.counted_in)
    assert followers < leader


def test_etf_and_spot_are_one_demand_signal():
    result = hierarchy(
        [
            factor("flows", impact=FactorImpact.HIGH, confidence=0.8),
            factor("spot", confidence=0.8),
        ]
    )
    spot = next(d for d in result.drivers if d.key == "spot")
    assert spot.counted_in == "factor:flows"


def test_seven_treasury_auctions_count_as_one():
    auctions = [
        event(
            "TREASURY_AUCTION",
            hours=40 + index,
            category=FutureEventCategory.MACRO,
            importance=EventImportance.HIGH,
            title=f"{index}-Year Note Treasury auction",
        )
        for index in range(7)
    ]
    result = hierarchy([], auctions)
    assert sum(1 for d in result.drivers if d.counted_in is None) == 1


# --- TEST 11 / 12 -------------------------------------------------------------


def test_opposed_evidence_reads_mixed():
    market = [f for f in healthy_market() if f.key != "rates"]
    result = hierarchy(
        [*market, factor("rates", FactorDirection.NEGATIVE, impact=FactorImpact.HIGH, confidence=0.8)]
    )
    assert result.reading is Reading.MIXED
    assert result.by_role(DriverRole.CONTRADICTION) or result.primary.direction in {
        DriverDirection.POSITIVE,
        DriverDirection.NEGATIVE,
    }


def test_missing_major_data_reduces_coverage_to_insufficient():
    missing = [
        factor(key, FactorDirection.UNKNOWN, availability=Availability.UNAVAILABLE)
        for key in ("rates", "energy", "credit", "flows", "spot", "whales")
    ]
    result = hierarchy([*missing, factor("technical")])

    assert result.coverage < 0.4
    assert result.reading is Reading.INSUFFICIENT_DATA
    assert "ETF" in result.data_gaps


# --- horizons and wording ---------------------------------------------------


def test_the_same_fed_ranks_differently_on_each_horizon():
    """Beyond 24 h it does not exist for the 24 h call; on 7 d it leads."""

    fed = event("FOMC_DECISION", hours=60)
    chart = factor("technical", impact=FactorImpact.HIGH, confidence=0.9)

    short = hierarchy([chart], [fed], horizon=DecisionHorizon.H24)
    week = hierarchy([chart], [fed], horizon=DecisionHorizon.D7)

    assert all(d.key != "FOMC_DECISION" for d in short.drivers)
    assert short.primary.key == "technical"
    assert week.primary.key == "FOMC_DECISION"


def test_every_explanation_line_starts_with_an_emoji_and_stays_short():
    result = hierarchy(
        healthy_market(),
        [event("FOMC_DECISION", hours=14)],
        gate_active=True,
        gate_event_ids=[],
        no_edge=True,
    )
    assert 2 <= len(result.explanation) <= 5
    for line in result.explanation:
        assert not line[0].isalnum(), line


def test_no_event_is_given_a_direction_by_its_type():
    for kind in ("FOMC_DECISION", "ECB_RATE_DECISION", "BOJ_POLICY_DECISION"):
        driver = hierarchy([], [event(kind, hours=5)]).drivers[0]
        assert driver.direction is DriverDirection.UNKNOWN


def test_principal_floor_filters_home_factors():
    result = hierarchy(healthy_market(), [event("FOMC_DECISION", hours=14)])
    assert all(item.counted_weight >= PRINCIPAL_FLOOR for item in result.home_factors())
    assert len(result.home_factors()) <= 4


# --- section 5: the gate weighs the asset's real exposure --------------------


def test_a_critical_event_on_another_network_does_not_gate_this_asset():
    from crypto_intel.engines.future_decision import EventRiskGate

    incident = FutureEvent(
        event_type="SOLANA_NETWORK_INCIDENT",
        category=FutureEventCategory.PROTOCOL,
        schedule_type=EventScheduleType.SCHEDULED,
        title="Incident réseau Solana",
        source="Solana status",
        source_tier=FutureEventSourceTier.A,
        source_url="https://status.solana.com/",
        importance=EventImportance.CRITICAL,
        magnitude_effect=ExpectedMovement.HIGH,
        scheduled_at=NOW + timedelta(hours=6),
        detected_at=NOW,
        last_updated=NOW,
        affected_assets=[Asset.SOL],
    )
    gate = EventRiskGate()

    assert gate.assess([incident], as_of=NOW, asset=Asset.SOL).active is True
    assert gate.assess([incident], as_of=NOW, asset=Asset.BTC).active is False


# --- found on real data -----------------------------------------------------


def test_the_cause_leads_its_cluster_when_weights_are_comparable():
    """ETF creations drive spot demand; spot being slightly louder does not flip that."""

    result = hierarchy(
        [
            factor("flows", confidence=0.6),
            factor("spot", impact=FactorImpact.HIGH, confidence=0.7),
        ]
    )
    spot = next(d for d in result.drivers if d.key == "spot")
    assert spot.counted_in == "factor:flows"
    assert "ce que confirment les achats au comptant" in result.explanation[0]


def test_calm_leverage_is_context_not_a_main_factor():
    result = hierarchy(
        [*healthy_market(), factor("implied_volatility", FactorDirection.UNKNOWN)]
    )
    keys = [d.key for d in result.home_factors()]
    assert "positioning" not in keys
    assert "implied_volatility" not in keys


def test_a_rates_level_weighs_less_on_the_next_session_than_on_a_month():
    rates = factor("rates", FactorDirection.NEGATIVE, impact=FactorImpact.HIGH, confidence=0.8)
    flows = factor("flows", impact=FactorImpact.HIGH, confidence=0.8)

    day = hierarchy([rates, flows], horizon=DecisionHorizon.H24)
    month = hierarchy([rates, flows], horizon=DecisionHorizon.D30)

    assert day.primary.key == "flows"
    assert month.primary.key == "rates"


def test_the_event_holding_the_decision_is_shown_as_the_blocker():
    pce = event(
        "PCE_PERSONAL_INCOME",
        hours=24 * 12,
        category=FutureEventCategory.MACRO,
        title="Personal Income and Outlays",
    )
    result = hierarchy(
        healthy_market(),
        [pce],
        horizon=DecisionHorizon.D30,
        gate_active=True,
        gate_event_ids=[pce.id],
    )
    driver = next(d for d in result.drivers if d.id == pce.id)
    assert driver.status.startswith("Bloque l'entrée")
    assert driver.tone == "RED"
    assert driver in result.home_factors()

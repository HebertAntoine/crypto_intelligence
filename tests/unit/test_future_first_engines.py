"""LOT 2 phases 6-10: validation of engines that shipped without any test.

These engines were already wired (or, for the surprise engine, already written
and never wired). Phase 12 asks for them to be validated, not rewritten, so
every test below pins existing behaviour and the guarantees the mission
requires - above all that no economic direction is inferred from an event type.
"""

from datetime import UTC, datetime

import pandas as pd
import pytest

from crypto_intel.core.enums import Asset
from crypto_intel.engines.contradiction_resolver import (
    ContradictionResolver,
    ContradictionState,
)
from crypto_intel.engines.event_surprise import EventSurpriseEngine, EventSurpriseStatus
from crypto_intel.engines.market_causal_graph import (
    CausalEdge,
    CausalFactor,
    MarketCausalGraph,
)
from crypto_intel.engines.market_expectation import (
    ExpectedOutcome,
    MarketExpectation,
    MarketExpectationStatus,
)
from crypto_intel.engines.signal_convergence import SignalConvergenceEngine
from crypto_intel.engines.volatility import ExpectedVolatilityEngine
from crypto_intel.engines.whales import (
    WhaleEntityType,
    WhaleObservation,
    WhaleProvenance,
    WhaleTransferKind,
    normalize_entity_type,
)
from crypto_intel.future_events.models import DirectionalBias, ExpectedMovement, MarketProbability

NOW = datetime(2026, 9, 13, 12, tzinfo=UTC)


def probability(outcome: str, value: float) -> MarketProbability:
    return MarketProbability(
        outcome=outcome, probability=value, source="CME FedWatch", observed_at=NOW
    )


def priced_expectation() -> MarketExpectation:
    return MarketExpectation(
        event_id="fomc-2026-09",
        observed_at=NOW,
        expected_outcome=ExpectedOutcome(outcome="HOLD", probability=0.8),
        outcome_distribution=[probability("HOLD", 0.8), probability("CUT_25", 0.2)],
        market_probability=0.8,
        probability_timestamp=NOW,
        uncertainty=0.2,
        source="CME FedWatch",
        methodology="test",
        freshness="LIVE",
        status=MarketExpectationStatus.AVAILABLE,
    )


def unpriced_expectation() -> MarketExpectation:
    return MarketExpectation(
        event_id="fomc-2026-09",
        observed_at=NOW,
        methodology="test",
        freshness="UNAVAILABLE",
        status=MarketExpectationStatus.UNAVAILABLE,
        unavailable_reason="no timestamped pricing",
    )


def factor(
    identifier: str,
    direction: DirectionalBias,
    *,
    strength: float = 1.0,
    confidence: float = 0.9,
) -> CausalFactor:
    return CausalFactor(
        id=identifier,
        type=identifier,
        observed_at=NOW,
        direction=direction,
        strength=strength,
        confidence=confidence,
        source_ids=[f"src:{identifier}"],
        affected_assets=[Asset.BTC],
    )


# --- PHASE 6: EventSurpriseEngine ------------------------------------------


def test_surprise_is_unavailable_without_a_pre_event_expectation() -> None:
    result = EventSurpriseEngine().analyze(
        unpriced_expectation(), actual_outcome="HOLD", observed_at=NOW
    )
    assert result.status is EventSurpriseStatus.UNAVAILABLE
    assert "no valid pre-event market expectation" in (result.unavailable_reason or "")


def test_surprise_is_unavailable_before_the_outcome_is_observed() -> None:
    result = EventSurpriseEngine().analyze(
        priced_expectation(), actual_outcome=None, observed_at=NOW
    )
    assert result.status is EventSurpriseStatus.UNAVAILABLE
    assert result.expected_outcome == "HOLD"


def test_a_fully_priced_outcome_is_not_a_surprise() -> None:
    result = EventSurpriseEngine().analyze(
        priced_expectation(), actual_outcome="HOLD", observed_at=NOW
    )
    assert result.status is EventSurpriseStatus.AVAILABLE
    assert result.probability_surprise == pytest.approx(0.2)


def test_an_unpriced_outcome_is_a_large_surprise() -> None:
    result = EventSurpriseEngine().analyze(
        priced_expectation(), actual_outcome="HIKE_25", observed_at=NOW
    )
    assert result.probability_surprise == pytest.approx(1.0)


def test_the_engine_never_infers_a_direction_from_the_event_wording() -> None:
    """A rate cut carries no built-in bullish sign; direction must be supplied."""

    result = EventSurpriseEngine().analyze(
        priced_expectation(), actual_outcome="CUT_25", observed_at=NOW
    )
    assert result.overall_direction is None
    assert result.directional_surprise is None
    assert "hike" in result.methodology and "cut" in result.methodology


def test_direction_appears_only_through_an_explicit_adapter() -> None:
    result = EventSurpriseEngine().analyze(
        priced_expectation(),
        actual_outcome="CUT_25",
        observed_at=NOW,
        outcome_direction={"HOLD": 0.0, "CUT_25": 1.0},
    )
    assert result.directional_surprise == pytest.approx(0.8)
    assert result.overall_direction == "POSITIVE"


def test_the_same_adapter_with_opposite_signs_flips_the_reading() -> None:
    """Proof the sign lives in the adapter, not in the engine."""

    result = EventSurpriseEngine().analyze(
        priced_expectation(),
        actual_outcome="CUT_25",
        observed_at=NOW,
        outcome_direction={"HOLD": 0.0, "CUT_25": -1.0},
    )
    assert result.overall_direction == "NEGATIVE"


# --- PHASE 7: whale observation semantics ----------------------------------


def observation(
    from_type: WhaleEntityType,
    to_type: WhaleEntityType,
    *,
    identifier: str = "w1",
    tx_hash: str | None = "0xABC",
    transaction_type: str = "transfer",
) -> WhaleObservation:
    return WhaleObservation(
        id=identifier,
        asset=Asset.BTC,
        observed_at=NOW,
        amount_asset=500.0,
        amount_usd=33_000_000.0,
        from_type=from_type,
        to_type=to_type,
        transaction_type=transaction_type,
        provider="test-provider",
        confidence=0.8,
        provenance=(
            [WhaleProvenance(source="test-provider", transaction_hash=tx_hash)]
            if tx_hash
            else []
        ),
    )


def test_wallet_to_exchange_and_exchange_to_wallet_are_distinguished() -> None:
    to_exchange = observation(WhaleEntityType.WALLET, WhaleEntityType.EXCHANGE)
    to_wallet = observation(WhaleEntityType.EXCHANGE, WhaleEntityType.WALLET)
    assert to_exchange.kind is WhaleTransferKind.WALLET_TO_EXCHANGE
    assert to_wallet.kind is WhaleTransferKind.EXCHANGE_TO_WALLET


def test_custody_is_not_treated_as_an_exchange_deposit() -> None:
    moved = observation(WhaleEntityType.WALLET, WhaleEntityType.CUSTODY)
    assert moved.kind is WhaleTransferKind.WALLET_TO_WALLET


def test_an_unattributed_transfer_stays_unknown_rather_than_guessed() -> None:
    moved = observation(WhaleEntityType.UNKNOWN, WhaleEntityType.UNKNOWN)
    assert moved.kind is WhaleTransferKind.UNKNOWN


def test_mint_and_burn_override_the_entity_pair() -> None:
    minted = observation(
        WhaleEntityType.WALLET, WhaleEntityType.EXCHANGE, transaction_type="mint"
    )
    assert minted.kind is WhaleTransferKind.MINT


def test_the_same_transaction_from_two_providers_deduplicates() -> None:
    left = observation(WhaleEntityType.WALLET, WhaleEntityType.EXCHANGE, identifier="a")
    right = observation(WhaleEntityType.WALLET, WhaleEntityType.EXCHANGE, identifier="b")
    assert left.deduplication_key == right.deduplication_key


def test_the_deduplication_key_is_case_insensitive_on_the_hash() -> None:
    upper = observation(WhaleEntityType.WALLET, WhaleEntityType.EXCHANGE, tx_hash="0xABC")
    lower = observation(WhaleEntityType.WALLET, WhaleEntityType.EXCHANGE, tx_hash="0xabc")
    assert upper.deduplication_key == lower.deduplication_key


def test_an_unknown_entity_label_never_raises() -> None:
    assert normalize_entity_type(None) is WhaleEntityType.UNKNOWN
    assert normalize_entity_type("something-unmapped") is WhaleEntityType.UNKNOWN


# --- PHASE 9: expected volatility ------------------------------------------


def test_compression_raises_amplitude_and_stays_directionless() -> None:
    """A Bollinger squeeze may only speak about size, never about which way."""

    calm = [100.0 + (i % 2) * 0.01 for i in range(120)]
    signal = ExpectedVolatilityEngine().assess_bollinger(pd.Series(calm))
    assert signal.available is True
    assert signal.directional_bias is DirectionalBias.NEUTRAL
    assert signal.direction_contribution == 0.0


def test_volatility_is_unavailable_without_enough_history() -> None:
    signal = ExpectedVolatilityEngine().assess_bollinger(pd.Series([100.0] * 30))
    assert signal.available is False
    assert "UNAVAILABLE" in signal.explanation


def test_a_wide_market_is_not_reported_as_a_squeeze() -> None:
    noisy = [100.0 + (i % 7) * 3.0 for i in range(100)] + [100.0, 140.0, 90.0, 150.0]
    signal = ExpectedVolatilityEngine().assess_bollinger(pd.Series(noisy))
    assert signal.available is True
    assert signal.squeeze is False
    assert signal.expected_movement is ExpectedMovement.NORMAL


# --- PHASE 10A: MarketCausalGraph ------------------------------------------


def test_unconnected_factors_are_independent_units() -> None:
    factors = [
        factor("macro", DirectionalBias.BULLISH),
        factor("flows", DirectionalBias.BULLISH),
    ]
    graph = MarketCausalGraph(factors)
    assert len(graph.independence_groups()) == 2


def test_a_causal_edge_merges_two_factors_into_one_unit() -> None:
    factors = [
        factor("macro", DirectionalBias.BULLISH),
        factor("flows", DirectionalBias.BULLISH),
    ]
    edges = [
        CausalEdge(
            source_factor="macro",
            target_factor="flows",
            mechanism="la liquidité macro alimente les flux",
            confidence=0.7,
        )
    ]
    graph = MarketCausalGraph(factors, edges)
    assert len(graph.independence_groups()) == 1
    assert graph.has_causal_edge({"macro", "flows"}) is True


def test_a_cyclic_causal_graph_is_refused() -> None:
    factors = [factor("a", DirectionalBias.BULLISH), factor("b", DirectionalBias.BULLISH)]
    edges = [
        CausalEdge(source_factor="a", target_factor="b", mechanism="x", confidence=0.5),
        CausalEdge(source_factor="b", target_factor="a", mechanism="y", confidence=0.5),
    ]
    with pytest.raises(ValueError):
        MarketCausalGraph(factors, edges)


# --- PHASE 10B: SignalConvergenceEngine ------------------------------------


def test_two_correlated_signals_count_as_one_confirmation() -> None:
    factors = [
        factor("macro", DirectionalBias.BULLISH),
        factor("flows", DirectionalBias.BULLISH),
    ]
    edges = [
        CausalEdge(
            source_factor="macro", target_factor="flows", mechanism="m", confidence=0.7
        )
    ]
    graph = MarketCausalGraph(factors, edges)
    result = SignalConvergenceEngine().analyze(factors, graph)
    assert result.independent_confirmation_count == 1
    assert result.correlated_confirmation_reduction == 1


def test_two_unrelated_signals_count_as_two_confirmations() -> None:
    factors = [
        factor("macro", DirectionalBias.BULLISH),
        factor("flows", DirectionalBias.BULLISH),
    ]
    result = SignalConvergenceEngine().analyze(factors, MarketCausalGraph(factors))
    assert result.independent_confirmation_count == 2
    assert result.correlated_confirmation_reduction == 0


def test_opposing_independent_signals_raise_mixed_strength() -> None:
    factors = [
        factor("macro", DirectionalBias.BULLISH),
        factor("flows", DirectionalBias.BEARISH),
    ]
    result = SignalConvergenceEngine().analyze(factors, MarketCausalGraph(factors))
    assert result.bullish_independent_count == 1
    assert result.bearish_independent_count == 1
    assert result.mixed_signal_strength == pytest.approx(1.0)


def test_convergence_refuses_a_graph_that_does_not_match_its_factors() -> None:
    factors = [factor("macro", DirectionalBias.BULLISH)]
    other = [factor("flows", DirectionalBias.BULLISH)]
    with pytest.raises(ValueError, match="must match"):
        SignalConvergenceEngine().analyze(factors, MarketCausalGraph(other))


# --- PHASE 10C: ContradictionResolver --------------------------------------


def test_one_sided_evidence_is_reported_as_aligned() -> None:
    factors = [
        factor("macro", DirectionalBias.BULLISH),
        factor("flows", DirectionalBias.BULLISH),
    ]
    result = ContradictionResolver().resolve(factors)
    assert result.state is ContradictionState.ALIGNED_BULLISH
    assert result.opposing_signals == []


def test_balanced_opposing_evidence_is_strongly_mixed() -> None:
    factors = [
        factor("macro", DirectionalBias.BULLISH),
        factor("flows", DirectionalBias.BEARISH),
    ]
    result = ContradictionResolver().resolve(factors)
    assert result.state is ContradictionState.STRONGLY_MIXED
    assert result.independent_conflicts


def test_a_weak_opposing_signal_is_only_mixed() -> None:
    factors = [
        factor("macro", DirectionalBias.BULLISH),
        factor("flows", DirectionalBias.BEARISH, strength=0.2, confidence=0.3),
    ]
    result = ContradictionResolver().resolve(factors)
    assert result.state is ContradictionState.MIXED


def test_no_directional_evidence_is_insufficient_data() -> None:
    factors = [factor("macro", DirectionalBias.NEUTRAL)]
    result = ContradictionResolver().resolve(factors)
    assert result.state is ContradictionState.INSUFFICIENT_DATA


def test_the_resolver_never_emits_an_action() -> None:
    factors = [factor("macro", DirectionalBias.BULLISH)]
    payload = ContradictionResolver().resolve(factors).model_dump()
    assert not {"decision", "action", "buy", "sell"} & set(payload)
    assert "does not alter BUY/WAIT/SELL" in payload["methodology"]

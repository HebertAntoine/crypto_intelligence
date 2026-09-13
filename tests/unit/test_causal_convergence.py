from __future__ import annotations

from datetime import UTC, datetime

from crypto_intel.core.enums import Asset
from crypto_intel.engines.contradiction_resolver import (
    ContradictionResolver,
    ContradictionState,
)
from crypto_intel.engines.market_causal_graph import (
    CausalEdge,
    CausalFactor,
    MarketCausalGraph,
)
from crypto_intel.engines.signal_convergence import SignalConvergenceEngine
from crypto_intel.future_events.models import DirectionalBias

NOW = datetime(2028, 9, 20, 18, tzinfo=UTC)


def _factor(
    identifier: str,
    family: str,
    direction: DirectionalBias,
    strength: float = 0.8,
) -> CausalFactor:
    return CausalFactor(
        id=identifier,
        type=family,
        observed_at=NOW,
        direction=direction,
        strength=strength,
        confidence=0.9,
        source_ids=[f"source:{identifier}"],
        affected_assets=[Asset.BTC, Asset.ETH],
    )


def _macro_chain() -> tuple[list[CausalFactor], list[CausalEdge]]:
    factors = [
        _factor("fed.hawkish", "macro", DirectionalBias.BEARISH),
        _factor("yields.up", "rates", DirectionalBias.BEARISH),
        _factor("usd.up", "cross_asset", DirectionalBias.BEARISH),
    ]
    edges = [
        CausalEdge(
            source_factor="fed.hawkish",
            target_factor="yields.up",
            mechanism="higher expected policy path raises yields",
            confidence=0.9,
        ),
        CausalEdge(
            source_factor="yields.up",
            target_factor="usd.up",
            mechanism="rate differential supports USD",
            confidence=0.7,
        ),
    ]
    return factors, edges


def test_causal_chain_no_double_count():
    factors, edges = _macro_chain()
    graph = MarketCausalGraph(factors, edges)
    result = SignalConvergenceEngine().analyze(factors, graph)

    assert result.causal_chain_count == 1
    assert result.independent_confirmation_count == 1
    assert result.bearish_independent_count == 1


def test_independent_family_confirmation():
    factors = [
        _factor("macro", "macro", DirectionalBias.BEARISH),
        _factor("etf", "institutional_flows", DirectionalBias.BEARISH),
        _factor("whales", "whales", DirectionalBias.BEARISH),
        _factor("crowding", "positioning", DirectionalBias.BEARISH),
    ]
    result = SignalConvergenceEngine().analyze(factors)

    assert result.independent_confirmation_count == 4
    assert result.bearish_independent_count == 4
    assert result.causal_chain_count == 0


def test_correlated_confirmation_reduction():
    factors, edges = _macro_chain()
    factors.append(_factor("etf.outflow", "institutional_flows", DirectionalBias.BEARISH))
    result = SignalConvergenceEngine().analyze(
        factors,
        MarketCausalGraph(factors, edges),
    )

    assert result.independent_confirmation_count == 2
    assert result.correlated_confirmation_reduction == 2


def test_contradiction_mixed():
    factors = [
        _factor("macro", "macro", DirectionalBias.BEARISH, 0.8),
        _factor("etf", "institutional_flows", DirectionalBias.BULLISH, 0.7),
        _factor("whales", "whales", DirectionalBias.BULLISH, 0.7),
        _factor("technical", "technical", DirectionalBias.BULLISH, 0.7),
    ]
    result = ContradictionResolver().resolve(factors)

    assert result.state is ContradictionState.MIXED
    assert result.supporting_signals
    assert result.opposing_signals
    assert result.independent_conflicts


def test_contradiction_aligned():
    factors = [
        _factor("etf", "institutional_flows", DirectionalBias.BULLISH),
        _factor("whales", "whales", DirectionalBias.STRONGLY_BULLISH),
    ]
    result = ContradictionResolver().resolve(factors)

    assert result.state is ContradictionState.ALIGNED_BULLISH
    assert result.opposing_signals == []


def test_zero_confidence_direction_is_not_a_signal_or_correlation():
    bearish = _factor("spot", "flows", DirectionalBias.BEARISH)
    zero_confidence = _factor("technical", "technical", DirectionalBias.BULLISH).model_copy(
        update={"confidence": 0.0}
    )

    convergence = SignalConvergenceEngine().analyze([bearish, zero_confidence])
    contradiction = ContradictionResolver().resolve([bearish, zero_confidence])

    assert convergence.correlated_confirmation_reduction == 0
    assert convergence.independent_confirmation_count == 1
    assert contradiction.state is ContradictionState.ALIGNED_BEARISH
    assert contradiction.opposing_signals == []

"""Count independent confirmations separately from correlated causal factors."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .market_causal_graph import CausalFactor, MarketCausalGraph, direction_sign


class ConvergenceUnit(BaseModel):
    model_config = ConfigDict(frozen=True)

    factor_ids: list[str]
    direction: str
    strength: float = Field(ge=0.0, le=1.0)
    causal: bool


class SignalConvergence(BaseModel):
    model_config = ConfigDict(frozen=True)

    independent_confirmation_count: int
    causal_chain_count: int
    bullish_independent_count: int
    bearish_independent_count: int
    mixed_signal_strength: float = Field(ge=0.0, le=1.0)
    correlated_confirmation_reduction: int
    units: list[ConvergenceUnit]
    methodology: str


class SignalConvergenceEngine:
    def analyze(
        self,
        factors: list[CausalFactor],
        graph: MarketCausalGraph | None = None,
    ) -> SignalConvergence:
        causal_graph = graph or MarketCausalGraph(factors)
        if set(causal_graph.factors) != {factor.id for factor in factors}:
            raise ValueError("convergence factors must match the causal graph")

        groups = causal_graph.independence_groups()
        units: list[ConvergenceUnit] = []
        bullish_count = 0
        bearish_count = 0
        bullish_strength = 0.0
        bearish_strength = 0.0
        correlated_reduction = 0
        for group in groups:
            members = [causal_graph.factors[item] for item in group]
            effective_directional_count = sum(
                direction_sign(item.direction) != 0
                and item.strength * item.confidence > 0
                for item in members
            )
            if causal_graph.has_causal_edge(group):
                correlated_reduction += max(0, effective_directional_count - 1)
            bullish = sum(
                item.strength * item.confidence
                for item in members
                if direction_sign(item.direction) > 0
            )
            bearish = sum(
                item.strength * item.confidence
                for item in members
                if direction_sign(item.direction) < 0
            )
            net = bullish - bearish
            total = bullish + bearish
            if net > 0:
                direction = "BULLISH"
                bullish_count += 1
                bullish_strength += abs(net)
            elif net < 0:
                direction = "BEARISH"
                bearish_count += 1
                bearish_strength += abs(net)
            else:
                direction = "MIXED" if total > 0 else "NEUTRAL"
            units.append(
                ConvergenceUnit(
                    factor_ids=sorted(group),
                    direction=direction,
                    strength=min(1.0, abs(net)),
                    causal=causal_graph.has_causal_edge(group),
                )
            )

        total_strength = bullish_strength + bearish_strength
        mixed_strength = (
            2.0 * min(bullish_strength, bearish_strength) / total_strength
            if total_strength > 0
            else 0.0
        )
        independent_count = bullish_count + bearish_count
        return SignalConvergence(
            independent_confirmation_count=independent_count,
            causal_chain_count=sum(item.causal for item in units),
            bullish_independent_count=bullish_count,
            bearish_independent_count=bearish_count,
            mixed_signal_strength=mixed_strength,
            correlated_confirmation_reduction=correlated_reduction,
            units=units,
            methodology=(
                "Each weakly connected causal component counts as at most one "
                "confirmation; unconnected factors are independent units. "
                "Mixed strength compares confidence-weighted evidence on both sides."
            ),
        )

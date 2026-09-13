"""Expose aligned and opposing signals without changing the final decision."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from .market_causal_graph import CausalFactor, MarketCausalGraph, direction_sign
from .signal_convergence import SignalConvergence, SignalConvergenceEngine


class ContradictionState(StrEnum):
    ALIGNED_BULLISH = "ALIGNED_BULLISH"
    ALIGNED_BEARISH = "ALIGNED_BEARISH"
    MIXED = "MIXED"
    STRONGLY_MIXED = "STRONGLY_MIXED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class ContradictionResolution(BaseModel):
    model_config = ConfigDict(frozen=True)

    state: ContradictionState
    supporting_signals: list[str] = Field(default_factory=list)
    opposing_signals: list[str] = Field(default_factory=list)
    dominant_family: str | None = None
    independent_conflicts: list[dict[str, str]] = Field(default_factory=list)
    convergence: SignalConvergence
    methodology: str


class ContradictionResolver:
    """Resolve evidence presentation only; it has no decision/action output."""

    strongly_mixed_floor = 0.75

    def resolve(
        self,
        factors: list[CausalFactor],
        graph: MarketCausalGraph | None = None,
    ) -> ContradictionResolution:
        causal_graph = graph or MarketCausalGraph(factors)
        convergence = SignalConvergenceEngine().analyze(factors, causal_graph)
        directional = [
            item
            for item in factors
            if direction_sign(item.direction) != 0
            and item.strength * item.confidence > 0
        ]
        methodology = (
            "Aligned requires one directional side only. Opposing evidence is MIXED; "
            "STRONGLY_MIXED requires the weaker independent side to be substantial "
            "relative to the stronger side. This result does not alter BUY/WAIT/SELL."
        )
        if not directional:
            return ContradictionResolution(
                state=ContradictionState.INSUFFICIENT_DATA,
                convergence=convergence,
                methodology=methodology,
            )

        ranked = sorted(
            directional,
            key=lambda item: (-item.strength * item.confidence, item.id),
        )
        dominant = ranked[0]
        dominant_sign = direction_sign(dominant.direction)
        supporting = [
            item.id for item in directional if direction_sign(item.direction) == dominant_sign
        ]
        opposing = [
            item.id for item in directional if direction_sign(item.direction) != dominant_sign
        ]

        signs = {direction_sign(item.direction) for item in directional}
        if signs == {1}:
            state = ContradictionState.ALIGNED_BULLISH
        elif signs == {-1}:
            state = ContradictionState.ALIGNED_BEARISH
        elif convergence.mixed_signal_strength >= self.strongly_mixed_floor:
            state = ContradictionState.STRONGLY_MIXED
        else:
            state = ContradictionState.MIXED

        conflicts: list[dict[str, str]] = []
        units = [unit for unit in convergence.units if unit.direction in {"BULLISH", "BEARISH"}]
        for index, left in enumerate(units):
            for right in units[index + 1 :]:
                if left.direction != right.direction:
                    conflicts.append(
                        {
                            "supporting_unit": ",".join(left.factor_ids),
                            "opposing_unit": ",".join(right.factor_ids),
                        }
                    )
        return ContradictionResolution(
            state=state,
            supporting_signals=sorted(supporting),
            opposing_signals=sorted(opposing),
            dominant_family=dominant.type,
            independent_conflicts=conflicts,
            convergence=convergence,
            methodology=methodology,
        )

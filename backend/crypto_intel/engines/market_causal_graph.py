"""Causal graph primitives used to prevent correlated signal double-counting."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..core.enums import Asset
from ..future_events.models import DirectionalBias


class CausalFactor(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    type: str = Field(min_length=1)
    observed_at: datetime
    direction: DirectionalBias
    strength: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    source_ids: list[str] = Field(min_length=1)
    affected_assets: list[Asset] = Field(default_factory=list)

    @field_validator("observed_at")
    @classmethod
    def ensure_utc(cls, value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class CausalEdge(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_factor: str
    target_factor: str
    mechanism: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)


class CausalChain(BaseModel):
    model_config = ConfigDict(frozen=True)

    root_factor: str
    derived_factors: list[str]
    affected_assets: list[Asset]
    direction: DirectionalBias
    strength: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    source_ids: list[str] = Field(default_factory=list)


def direction_sign(direction: DirectionalBias) -> int:
    if direction in {DirectionalBias.BULLISH, DirectionalBias.STRONGLY_BULLISH}:
        return 1
    if direction in {DirectionalBias.BEARISH, DirectionalBias.STRONGLY_BEARISH}:
        return -1
    return 0


class MarketCausalGraph:
    """A validated DAG-like evidence graph.

    Connected factors form one independence unit. This does not assert that an
    edge is true: the edge carries its own confidence and mechanism, and the
    graph only reduces confirmation counts when the relationship is supplied.
    """

    def __init__(
        self,
        factors: Iterable[CausalFactor] = (),
        edges: Iterable[CausalEdge] = (),
    ) -> None:
        factor_list = list(factors)
        self.factors = {factor.id: factor for factor in factor_list}
        if len(self.factors) != len(factor_list):
            raise ValueError("causal factor ids must be unique")
        self.edges = list(edges)
        for edge in self.edges:
            if edge.source_factor not in self.factors or edge.target_factor not in self.factors:
                raise ValueError("causal edges must reference known factors")
            if edge.source_factor == edge.target_factor:
                raise ValueError("causal self-edges are not allowed")
        self._assert_acyclic()

    def _assert_acyclic(self) -> None:
        indegree = dict.fromkeys(self.factors, 0)
        children: dict[str, list[str]] = {factor_id: [] for factor_id in self.factors}
        for edge in self.edges:
            indegree[edge.target_factor] += 1
            children[edge.source_factor].append(edge.target_factor)
        queue = deque(item for item, degree in indegree.items() if degree == 0)
        visited = 0
        while queue:
            current = queue.popleft()
            visited += 1
            for child in children[current]:
                indegree[child] -= 1
                if indegree[child] == 0:
                    queue.append(child)
        if visited != len(self.factors):
            raise ValueError("market causal graph must not contain a cycle")

    def independence_groups(self) -> list[set[str]]:
        """Return weakly connected components; each counts at most once."""

        neighbours: dict[str, set[str]] = {factor_id: set() for factor_id in self.factors}
        for edge in self.edges:
            neighbours[edge.source_factor].add(edge.target_factor)
            neighbours[edge.target_factor].add(edge.source_factor)
        remaining = set(self.factors)
        groups: list[set[str]] = []
        while remaining:
            start = min(remaining)
            group: set[str] = set()
            queue = deque([start])
            while queue:
                current = queue.popleft()
                if current in group:
                    continue
                group.add(current)
                queue.extend(neighbours[current] - group)
            remaining -= group
            groups.append(group)
        return groups

    def chains(self) -> list[CausalChain]:
        parents: dict[str, set[str]] = {factor_id: set() for factor_id in self.factors}
        children: dict[str, set[str]] = {factor_id: set() for factor_id in self.factors}
        edge_confidence: dict[tuple[str, str], float] = {}
        for edge in self.edges:
            parents[edge.target_factor].add(edge.source_factor)
            children[edge.source_factor].add(edge.target_factor)
            edge_confidence[(edge.source_factor, edge.target_factor)] = edge.confidence

        output: list[CausalChain] = []
        for group in self.independence_groups():
            roots = sorted(item for item in group if not (parents[item] & group))
            root = roots[0]
            terminals = sorted(item for item in group if not (children[item] & group))
            terminal_factors = [self.factors[item] for item in terminals]
            signed = sum(
                direction_sign(item.direction) * item.strength * item.confidence
                for item in terminal_factors
            )
            direction = (
                DirectionalBias.BULLISH
                if signed > 0
                else DirectionalBias.BEARISH
                if signed < 0
                else DirectionalBias.NEUTRAL
            )
            factors = [self.factors[item] for item in group]
            strengths = [item.strength for item in terminal_factors] or [0.0]
            confidences = [item.confidence for item in factors]
            confidences.extend(
                edge_confidence[(edge.source_factor, edge.target_factor)]
                for edge in self.edges
                if edge.source_factor in group and edge.target_factor in group
            )
            output.append(
                CausalChain(
                    root_factor=root,
                    derived_factors=sorted(group - {root}),
                    affected_assets=sorted(
                        {asset for item in factors for asset in item.affected_assets},
                        key=lambda asset: asset.value,
                    ),
                    direction=direction,
                    strength=max(strengths),
                    confidence=min(confidences) if confidences else 0.0,
                    source_ids=sorted(
                        {source_id for item in factors for source_id in item.source_ids}
                    ),
                )
            )
        return output

    def has_causal_edge(self, group: set[str]) -> bool:
        return any(
            edge.source_factor in group and edge.target_factor in group
            for edge in self.edges
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "factors": [item.model_dump(mode="json") for item in self.factors.values()],
            "edges": [item.model_dump(mode="json") for item in self.edges],
            "chains": [item.model_dump(mode="json") for item in self.chains()],
            "independence_groups": [
                sorted(group) for group in self.independence_groups()
            ],
            "methodology": (
                "Causally connected factors form one independence unit. An edge "
                "is only present when an explicit mechanism has been supplied."
            ),
        }

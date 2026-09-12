"""GeopoliticalRiskAnalyzer.

Explicitly NOT a predictor. Geopolitical shocks are not forecastable, and any
tool claiming otherwise is lying. What this does instead is assess the risk
level implied by events that have ALREADY happened, and trace the transmission
channels through which they reach crypto: oil, inflation, the dollar, and risk
appetite.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, Field

from ..core.enums import Direction, RiskLevel
from ..future_events.models import (
    DirectionalBias,
    ExpectedMovement,
    FutureEvent,
    FutureEventCategory,
)

_THEMES: dict[str, tuple[re.Pattern[str], float, list[str]]] = {
    "armed_conflict": (
        re.compile(r"\b(war|invasion|missile|strike[sd]?|airstrike|offensive|troops|"
                   r"military action|bombing|attack on)\b", re.I),
        30.0, ["oil", "risk_appetite", "dollar"]),
    "sanctions": (
        re.compile(r"\b(sanction|embargo|export control|blacklist|asset freeze|"
                   r"secondary sanctions)\b", re.I),
        18.0, ["dollar", "trade", "energy"]),
    "energy_chokepoint": (
        re.compile(r"\b(hormuz|suez|strait of|pipeline|opec|oil supply|crude supply|"
                   r"tanker)\b", re.I),
        22.0, ["oil", "inflation"]),
    "trade_tension": (
        re.compile(r"\b(tariff|trade war|trade dispute|import duty|retaliat)\b", re.I),
        14.0, ["inflation", "risk_appetite"]),
    "banking_stress": (
        re.compile(r"\b(bank failure|bank run|bailout|liquidity crisis|credit crunch|"
                   r"insolvency|deposit flight)\b", re.I),
        26.0, ["risk_appetite", "liquidity"]),
    "sovereign_stress": (
        re.compile(r"\b(default|debt ceiling|downgrade|sovereign debt|currency crisis|"
                   r"capital controls)\b", re.I),
        20.0, ["dollar", "risk_appetite"]),
    "political_instability": (
        re.compile(r"\b(coup|impeach|snap election|government collapse|state of emergency|"
                   r"civil unrest|protest[s]? erupt)\b", re.I),
        12.0, ["risk_appetite"]),
}


class GeopoliticalRisk(BaseModel):
    level: RiskLevel = RiskLevel.LOW
    score: float = 0.0
    justification: str = ""
    themes: dict[str, int] = Field(default_factory=dict)
    transmission_channels: list[str] = Field(default_factory=list)
    crypto_implication: str = ""
    direction: Direction = Direction.NEUTRAL
    evidence_headlines: list[str] = Field(default_factory=list)
    available: bool = True
    unavailable_reason: str | None = None
    disclaimer: str = (
        "Geopolitical events are not predictable. This assesses risk implied by events "
        "that have already occurred; it does not forecast new ones."
    )


class GeopoliticalRiskAnalyzer:
    name = "geopolitical_analyzer"

    def analyze(
        self,
        raw_items: list[dict],
        now: datetime | None = None,
        lookback_days: int = 7,
        unavailable_reason: str | None = None,
    ) -> GeopoliticalRisk:
        now = now or datetime.now(UTC)
        if unavailable_reason or not raw_items:
            return GeopoliticalRisk(
                available=False,
                unavailable_reason=unavailable_reason
                or "UNAVAILABLE - no news feed to assess geopolitical risk",
                level=RiskLevel.LOW, justification="No data available to assess risk",
            )

        cutoff = now - timedelta(days=lookback_days)
        theme_hits: dict[str, int] = {}
        channels: set[str] = set()
        headlines: list[str] = []
        score = 0.0

        for item in raw_items:
            published = item.get("published_at")
            if not isinstance(published, datetime):
                continue
            if published.tzinfo is None:
                published = published.replace(tzinfo=UTC)
            if published < cutoff:
                continue

            text = f"{item.get('title', '')}. {str(item.get('summary', ''))[:300]}"
            matched = False
            for theme, (pattern, weight, chans) in _THEMES.items():
                if pattern.search(text):
                    theme_hits[theme] = theme_hits.get(theme, 0) + 1
                    channels.update(chans)
                    # Diminishing returns: ten headlines about one war is still one war.
                    occurrence = theme_hits[theme]
                    score += weight / occurrence
                    matched = True
            if matched and len(headlines) < 8:
                headlines.append(str(item.get("title", ""))[:130])

        score = min(100.0, score)
        if score >= 70:
            level = RiskLevel.EXTREME
        elif score >= 45:
            level = RiskLevel.HIGH
        elif score >= 20:
            level = RiskLevel.MODERATE
        else:
            level = RiskLevel.LOW

        if theme_hits:
            top = sorted(theme_hits.items(), key=lambda kv: -kv[1])[:3]
            justification = (
                f"Risk level {level.value} (score {score:.0f}/100). Active themes: "
                + ", ".join(f"{t.replace('_', ' ')} ({n} item(s))" for t, n in top)
                + ". Transmission channels: " + ", ".join(sorted(channels)) + "."
            )
        else:
            justification = (
                f"Risk level {level.value}: no significant geopolitical themes detected in "
                f"the last {lookback_days} days of monitored feeds."
            )

        implication, direction = self._crypto_implication(level, channels)
        return GeopoliticalRisk(
            level=level, score=round(score, 1), justification=justification,
            themes=theme_hits, transmission_channels=sorted(channels),
            crypto_implication=implication, direction=direction,
            evidence_headlines=headlines, available=True,
        )

    def _crypto_implication(self, level: RiskLevel, channels: set[str]) -> tuple[str, Direction]:
        if level is RiskLevel.LOW:
            return (
                "No material geopolitical pressure on crypto through the monitored channels.",
                Direction.NEUTRAL,
            )
        parts = []
        if "oil" in channels:
            parts.append("higher energy prices feed inflation, which argues for tighter policy")
        if "dollar" in channels:
            parts.append("safe-haven dollar demand typically pressures crypto")
        if "risk_appetite" in channels:
            parts.append("risk-off flows usually hit crypto harder than equities given its beta")
        if "liquidity" in channels:
            parts.append("funding stress drains liquidity from speculative assets")

        detail = "; ".join(parts) if parts else "channels to crypto are unclear"
        if level in (RiskLevel.HIGH, RiskLevel.EXTREME):
            return (
                f"{level.value} geopolitical risk: {detail}. Historically crypto sells off "
                "in the acute phase of such episodes, with any 'digital gold' behaviour "
                "appearing only later, if at all.",
                Direction.BEARISH,
            )
        return (
            f"{level.value} geopolitical risk: {detail}. Effect on crypto is real but not dominant.",
            Direction.NEUTRAL,
        )


class ProspectiveGeopoliticalRisk(BaseModel):
    available: bool
    unavailable_reason: str | None = None
    event_count: int = 0
    level: RiskLevel = RiskLevel.LOW
    directional_bias: DirectionalBias = DirectionalBias.NEUTRAL
    expected_movement: ExpectedMovement = ExpectedMovement.NORMAL
    causal_chains: list[list[str]] = Field(default_factory=list)
    event_ids: list[str] = Field(default_factory=list)
    provenance: list[dict[str, str | None]] = Field(default_factory=list)
    explanation: str = ""


_CONCRETE_EVENT_TYPES = {
    "ENERGY_INFRASTRUCTURE_ATTACK",
    "CHOKEPOINT_CLOSURE",
    "SANCTIONS",
    "ARMED_CONFLICT",
    "CEASEFIRE",
    "OPEC_PRODUCTION_CHANGE",
    "STRATEGIC_RESERVE_RELEASE",
    "PIPELINE_DISRUPTION",
}


class GeopoliticalRiskEngine:
    """Prospective view over concrete, source-backed events only.

    It deliberately refuses a bag-of-words sentiment score. Providers must
    identify a concrete event type and preserve its source before it reaches
    this engine.
    """

    def analyze(self, events: list[FutureEvent]) -> ProspectiveGeopoliticalRisk:
        concrete = [
            event
            for event in events
            if event.category in {FutureEventCategory.GEOPOLITICAL, FutureEventCategory.ENERGY}
            and str(event.metadata.get("concrete_type") or event.event_type)
            in _CONCRETE_EVENT_TYPES
        ]
        if not concrete:
            return ProspectiveGeopoliticalRisk(
                available=False,
                unavailable_reason="UNAVAILABLE - no source-backed concrete geopolitical event",
                explanation="No direction is inferred from generic geopolitical headlines.",
            )

        movement_rank = {
            ExpectedMovement.LOW: 0,
            ExpectedMovement.NORMAL: 1,
            ExpectedMovement.HIGH: 2,
            ExpectedMovement.EXTREME: 3,
        }
        movement = max(concrete, key=lambda event: movement_rank[event.magnitude_effect]).magnitude_effect
        bearish = sum(
            1
            for event in concrete
            if event.directional_effect in {
                DirectionalBias.BEARISH,
                DirectionalBias.STRONGLY_BEARISH,
            }
        )
        bullish = sum(
            1
            for event in concrete
            if event.directional_effect in {
                DirectionalBias.BULLISH,
                DirectionalBias.STRONGLY_BULLISH,
            }
        )
        direction = (
            DirectionalBias.BEARISH if bearish > bullish
            else DirectionalBias.BULLISH if bullish > bearish
            else DirectionalBias.NEUTRAL
        )
        if movement is ExpectedMovement.EXTREME:
            level = RiskLevel.EXTREME
        elif movement is ExpectedMovement.HIGH:
            level = RiskLevel.HIGH
        else:
            level = RiskLevel.MODERATE
        return ProspectiveGeopoliticalRisk(
            available=True,
            event_count=len(concrete),
            level=level,
            directional_bias=direction,
            expected_movement=movement,
            causal_chains=[event.causal_chain for event in concrete if event.causal_chain],
            event_ids=[event.canonical_event_id for event in concrete],
            provenance=[
                {
                    "source": event.source,
                    "source_url": event.source_url,
                    "source_tier": event.source_tier.value,
                }
                for event in concrete
            ],
            explanation=(
                "Concrete events are mapped through explicit transmission channels; "
                "the result is a risk contribution, never a certain price forecast."
            ),
        )

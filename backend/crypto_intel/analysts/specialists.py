"""The ten specialised analysts.

Each converts its engine's output into a uniform AnalystResult. The score comes
from the engine (deterministic); the analyst adds domain framing, pulls in
relevant course passages, and marks what is missing.
"""

from __future__ import annotations

from typing import Any

from ..core.enums import Asset, Direction, Freshness
from ..engines.scoring import confidence_from
from .base import AnalystResult, BaseAnalyst


def _split_findings(findings: list[str], direction: Direction) -> tuple[list[str], list[str], list[str]]:
    """Route engine findings into positive / negative / neutral buckets."""
    positives, negatives, neutral = [], [], []
    pos_markers = ("rising", "up ", "grew", "growing", "inflow", "accumul", "expand",
                   "positive", "confirms", "strong daily inflow", "supportive", "healthy",
                   "improve", "higher", "increase")
    neg_markers = ("falling", "down ", "fell", "declin", "outflow", "contract", "negative",
                   "weak", "crowded", "squeeze", "capitulation", "drain", "cooling",
                   "not backed", "not confirming", "lower", "congested")
    for f in findings:
        low = f.lower()
        if any(m in low for m in neg_markers):
            negatives.append(f)
        elif any(m in low for m in pos_markers):
            positives.append(f)
        else:
            neutral.append(f)
    return positives, negatives, neutral


class TechnicalAnalyst(BaseAnalyst):
    name = "technical_analyst"
    domain = "technical"
    knowledge_category = "trading"

    def analyze_rules(self, asset: Asset, context: dict[str, Any]) -> AnalystResult:
        mtf = context.get("mtf")
        snapshots = context.get("snapshots") or {}
        card = context.get("technical_card")

        if not mtf or mtf.timeframes_available == 0 or card is None or not card.available:
            return self.unavailable(
                self.name, self.domain, asset, "UNAVAILABLE - no market data to analyse"
            )

        positives, negatives, neutral = [], [], []
        for v in mtf.verdicts:
            if not v.available:
                continue
            line = f"{v.timeframe.value}: {v.direction.value.lower()} ({v.trend.value.lower()})"
            if v.direction is Direction.BULLISH:
                positives.append(line)
            elif v.direction is Direction.BEARISH:
                negatives.append(line)
            else:
                neutral.append(line)

        daily = next((s for tf, s in snapshots.items() if tf.value == "1d" and s and s.has_data), None)
        if daily:
            if daily.rsi is not None:
                neutral.append(f"Daily RSI {daily.rsi:.1f} ({daily.rsi_state})")
            if daily.structure.value != "UNDETERMINED":
                neutral.append(f"Daily market structure: {daily.structure.value}")
            for p in daily.patterns[:3]:
                line = (f"{p.pattern} on {p.timeframe.value} - {p.confirmation_state.value}, "
                        f"confidence {p.confidence:.0f}%, invalidation {p.invalidation_level}")
                (positives if p.direction is Direction.BULLISH else
                 negatives if p.direction is Direction.BEARISH else neutral).append(line)
            for d in daily.divergences[:2]:
                line = f"{d.indicator} {d.kind} divergence on {d.timeframe.value} (strength {d.strength:.0f})"
                (positives if "bull" in d.kind else negatives).append(line)
            if daily.levels_support:
                neutral.append(
                    "Supports: " + ", ".join(f"{lv.price:,.0f}" for lv in daily.levels_support[:3])
                )
            if daily.levels_resistance:
                neutral.append(
                    "Resistances: " + ", ".join(f"{lv.price:,.0f}" for lv in daily.levels_resistance[:3])
                )

        missing = list(mtf.conflicts)
        summary = (
            f"Multi-timeframe alignment {mtf.alignment_score:+.0f} with {mtf.coherence:.0f}% "
            f"coherence across {mtf.timeframes_available} timeframes; dominant direction "
            f"{mtf.dominant_direction.value}."
        )
        return AnalystResult(
            analyst=self.name, domain=self.domain, asset=asset, available=True,
            score=card.score, confidence=card.confidence, freshness=card.freshness,
            direction=mtf.dominant_direction, summary=summary,
            positives=positives, negatives=negatives, neutral=neutral,
            missing_data=missing, evidence_ids=card.evidence_ids,
            raw={"alignment": mtf.alignment_score, "coherence": mtf.coherence},
        )

    def knowledge_query(self, result: AnalystResult, context: dict[str, Any]) -> str | None:
        terms = []
        snapshots = context.get("snapshots") or {}
        daily = next((s for tf, s in snapshots.items() if tf.value == "1d" and s and s.has_data), None)
        if daily:
            for d in daily.divergences[:2]:
                terms.append(f"divergence {d.indicator} {d.kind}")
            for p in daily.patterns[:2]:
                terms.append(p.pattern.replace("_", " "))
            if daily.rsi_state not in ("NEUTRAL", "UNAVAILABLE"):
                terms.append(f"RSI {daily.rsi_state.lower()}")
        return " ".join(terms) if terms else "analyse technique tendance support resistance"


class _EngineAnalyst(BaseAnalyst):
    """Shared conversion for engine analyses exposing the usual attributes."""

    engine_key = ""
    base_confidence = 85.0

    def analyze_rules(self, asset: Asset, context: dict[str, Any]) -> AnalystResult:
        analysis = context.get(self.engine_key)
        if analysis is None or not getattr(analysis, "available", False):
            reason = getattr(analysis, "unavailable_reason", None) if analysis else None
            return self.unavailable(
                self.name, self.domain, asset,
                reason or f"UNAVAILABLE - no {self.domain} data",
            )

        findings = list(getattr(analysis, "findings", []) or [])
        direction = getattr(analysis, "direction", Direction.NEUTRAL)
        positives, negatives, neutral = _split_findings(findings, direction)

        evidence_ids = list(getattr(analysis, "evidence_ids", []) or [])
        freshness = getattr(analysis, "freshness", Freshness.UNAVAILABLE)
        declared = getattr(analysis, "confidence", None)
        confidence = (
            float(declared) if isinstance(declared, int | float) and declared > 0
            else confidence_from(
                base=self.base_confidence,
                evidence_count=len(evidence_ids) or len(findings),
                freshness=freshness,
            )
        )
        warnings = list(getattr(analysis, "warnings", []) or [])
        negatives.extend(warnings)

        return AnalystResult(
            analyst=self.name, domain=self.domain, asset=asset, available=True,
            score=float(getattr(analysis, "strength", 0.0)),
            confidence=confidence, freshness=freshness, direction=direction,
            summary=self.summarize(analysis),
            positives=positives, negatives=negatives, neutral=neutral,
            evidence_ids=evidence_ids,
        )

    def summarize(self, analysis: Any) -> str:
        return f"{self.domain} score {getattr(analysis, 'strength', 0):+.0f}"


class ETFAnalyst(_EngineAnalyst):
    name = "etf_analyst"
    domain = "etf"
    engine_key = "etf"
    base_confidence = 90.0

    def summarize(self, a: Any) -> str:
        parts = []
        if a.latest_total is not None:
            parts.append(f"Latest daily net flow {a.latest_total:+.1f}M USD on {a.latest_date:%Y-%m-%d}")
        if a.ma_5d is not None:
            parts.append(f"5-day average {a.ma_5d:+.1f}M")
        if a.streak_days >= 2 and a.streak_direction:
            parts.append(f"{a.streak_days} consecutive {a.streak_direction} days")
        if a.flow_price_divergence:
            parts.append(f"flow/price signal: {a.flow_price_divergence}")
        return ". ".join(parts) + "." if parts else "ETF flow data available."

    def knowledge_query(self, result, context) -> str | None:
        return "ETF flux institutionnels demande accumulation distribution"


class DerivativesAnalyst(_EngineAnalyst):
    name = "derivatives_analyst"
    domain = "derivatives"
    engine_key = "derivatives"

    def summarize(self, a: Any) -> str:
        parts = []
        if a.funding_rate is not None:
            parts.append(f"Funding {a.funding_rate:.6f}/8h ({a.funding_state})")
        if a.oi_change_24h_pct is not None:
            parts.append(f"open interest {a.oi_change_24h_pct:+.1f}% in 24h")
        if a.price_oi_regime:
            parts.append(f"regime {a.price_oi_regime}")
        if not a.liquidations_available:
            parts.append("liquidations UNAVAILABLE")
        return ". ".join(parts) + "." if parts else "Derivatives data available."

    def knowledge_query(self, result, context) -> str | None:
        return "funding rate open interest levier liquidation squeeze"


class OnChainAnalyst(_EngineAnalyst):
    name = "onchain_analyst"
    domain = "onchain"
    engine_key = "onchain"
    base_confidence = 80.0

    def summarize(self, a: Any) -> str:
        return (
            f"On-chain analysis for {a.asset.value} ({a.chain_type}), "
            f"{len(a.metrics)} metrics available."
        )


class LiquidityAnalyst(_EngineAnalyst):
    name = "liquidity_analyst"
    domain = "liquidity"
    engine_key = "liquidity"

    def summarize(self, a: Any) -> str:
        if a.change_7d_pct is not None and a.total_supply is not None:
            return (
                f"Stablecoin supply ${a.total_supply / 1e9:,.1f}B, {a.change_7d_pct:+.2f}% "
                f"over 7 days - regime {a.regime}."
            )
        return f"Stablecoin liquidity regime {a.regime}."


class DefiAnalyst(_EngineAnalyst):
    name = "defi_analyst"
    domain = "defi"
    engine_key = "defi"

    def summarize(self, a: Any) -> str:
        if a.tvl is not None:
            base = f"{a.asset.value} chain TVL ${a.tvl / 1e9:,.2f}B"
            if a.tvl_change_7d_pct is not None:
                base += f" ({a.tvl_change_7d_pct:+.1f}% / 7d)"
            return base + "."
        return "DeFi data available."


class MacroAnalyst(_EngineAnalyst):
    name = "macro_analyst"
    domain = "macro"
    engine_key = "macro"

    def summarize(self, a: Any) -> str:
        parts = [f"Risk appetite {a.risk_appetite}", f"dollar {a.dollar_trend}", f"rates {a.rates_trend}"]
        if a.imminent_event:
            parts.append(f"{a.imminent_event.name} in {a.imminent_event.hours_until:.1f}h")
        return ", ".join(parts) + "."

    def knowledge_query(self, result, context) -> str | None:
        return "macroeconomie taux inflation dollar liquidite risque"


class RegulationAnalyst(_EngineAnalyst):
    name = "regulation_analyst"
    domain = "regulation"
    engine_key = "regulation"

    def summarize(self, a: Any) -> str:
        return (
            f"{len(a.events)} crypto-relevant regulatory item(s): {a.binding_count} binding "
            f"decision(s), {a.proposal_count} proposal(s) which are NOT law."
        )


class NewsAnalyst(_EngineAnalyst):
    name = "news_analyst"
    domain = "news"
    engine_key = "news"
    base_confidence = 55.0

    def summarize(self, a: Any) -> str:
        return (
            f"{a.unique_events} distinct events from {a.total_items} items "
            f"({a.duplicates_removed} republications collapsed)."
        )


class WhaleAnalyst(_EngineAnalyst):
    name = "whale_analyst"
    domain = "whale"
    engine_key = "whale"
    base_confidence = 50.0

    def summarize(self, a: Any) -> str:
        return (
            f"Whale behaviour {a.behaviour or 'undetermined'} "
            f"(reliability {a.reliability.value}, threshold {a.threshold:.0f} {a.threshold_unit})."
        )


class HistoricalAnalyst(BaseAnalyst):
    name = "historical_analyst"
    domain = "historical"
    uses_llm = False   # this is a statistical read-out, prose adds nothing

    def analyze_rules(self, asset: Asset, context: dict[str, Any]) -> AnalystResult:
        a = context.get("historical")
        if a is None or not a.available:
            return self.unavailable(
                self.name, self.domain, asset,
                getattr(a, "unavailable_reason", None) or "UNAVAILABLE - insufficient history",
            )

        positives, negatives, neutral = [], [], []
        neutral.append(a.interpretation)
        for m in a.matches[:5]:
            r7 = m.forward_returns.get("7d")
            neutral.append(
                f"{m.date}: similarity {m.similarity * 100:.1f}%"
                + (f", +7d return {r7:+.2f}%" if r7 is not None else "")
            )

        # This analyst informs; it does not vote in the conviction score.
        score = 0.0
        avg7 = a.avg_forward_returns.get("7d")
        if avg7 is not None and a.sample_size >= 5:
            score = max(-40.0, min(40.0, avg7 * 4.0))

        return AnalystResult(
            analyst=self.name, domain=self.domain, asset=asset, available=True,
            score=score,
            # Confidence stays low by design: a handful of analogues is not a model.
            confidence=min(45.0, a.sample_size * 5.0),
            freshness=Freshness.TODAY,
            direction=(
                Direction.BULLISH if score > 8 else
                Direction.BEARISH if score < -8 else Direction.NEUTRAL
            ),
            summary=a.interpretation, positives=positives, negatives=negatives, neutral=neutral,
            missing_data=[a.caveat],
        )


ALL_ANALYSTS: list[type[BaseAnalyst]] = [
    TechnicalAnalyst, ETFAnalyst, DerivativesAnalyst, OnChainAnalyst,
    LiquidityAnalyst, DefiAnalyst, MacroAnalyst, RegulationAnalyst,
    NewsAnalyst, WhaleAnalyst, HistoricalAnalyst,
]

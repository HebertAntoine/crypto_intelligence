"""ChiefMarketAnalyst - the synthesis layer.

Receives the specialists' STRUCTURED CONCLUSIONS, never the raw data. Its job
is to find convergence, divergence, contradiction, missing data, catalysts and
risks - and to produce scenarios.

Without an LLM it still works: a deterministic synthesis is built from the
scores, the contradictions and the levels. The narrative is richer with a
model, but nothing essential depends on one.
"""

from __future__ import annotations

from typing import Any

from ..core.enums import Asset, LegalStatus
from ..core.models import Scenario
from ..engines.contradictions import ContradictionReport
from ..engines.conviction import ConvictionResult
from ..llm.base import LLMProvider
from ..llm.schemas import ChiefAnalystOutput
from ..llm.validation import ANTI_HALLUCINATION_RULES, find_unsupported_numbers
from ..logging_setup import get_logger
from .base import AnalystResult

log = get_logger("analysts.chief")


class ChiefSynthesis:
    def __init__(self) -> None:
        self.synthesis: str = ""
        self.positives: list[str] = []
        self.negatives: list[str] = []
        self.contradictions: list[str] = []
        self.key_catalysts: list[str] = []
        self.key_risks: list[str] = []
        self.what_would_change_my_mind: list[str] = []
        self.scenarios: list[Scenario] = []
        self.missing_data: list[str] = []
        self.data_quality_note: str = ""
        self.recent_decisions: list[str] = []
        self.llm_used: bool = False


class ChiefMarketAnalyst:
    name = "chief_market_analyst"

    def __init__(self, llm: LLMProvider | None = None) -> None:
        self.llm = llm

    async def synthesize(
        self,
        asset: Asset,
        analysts: dict[str, AnalystResult],
        conviction: ConvictionResult,
        contradictions: ContradictionReport,
        context: dict[str, Any],
    ) -> ChiefSynthesis:
        result = self._rule_based(asset, analysts, conviction, contradictions, context)

        if self.llm:
            try:
                await self._llm_synthesis(result, asset, analysts, conviction, contradictions, context)
            except Exception as exc:
                log.info("chief_llm_failed", error=str(exc)[:200])
                result.missing_data.append(
                    f"LLM synthesis unavailable ({type(exc).__name__}) - "
                    "deterministic synthesis shown instead"
                )
        return result

    # --- deterministic path ------------------------------------------------

    def _rule_based(
        self, asset, analysts, conviction, contradictions, context
    ) -> ChiefSynthesis:
        out = ChiefSynthesis()

        available = {k: a for k, a in analysts.items() if a.available}
        unavailable = {k: a for k, a in analysts.items() if not a.available}

        # Rank domains by how strongly they lean, weighted by confidence.
        ranked = sorted(
            available.values(),
            key=lambda a: abs(a.score) * (a.confidence / 100.0),
            reverse=True,
        )
        for a in ranked:
            if a.score > 10 and a.confidence >= 25:
                out.positives.append(
                    f"{a.domain.upper()} ({a.score:+.0f}, {a.confidence:.0f}% conf): "
                    + (a.positives[0] if a.positives else a.summary[:150])
                )
            elif a.score < -10 and a.confidence >= 25:
                out.negatives.append(
                    f"{a.domain.upper()} ({a.score:+.0f}, {a.confidence:.0f}% conf): "
                    + (a.negatives[0] if a.negatives else a.summary[:150])
                )

        out.contradictions = [c.description for c in contradictions.contradictions]
        for a in unavailable.values():
            out.missing_data.append(f"{a.domain}: {a.unavailable_reason}")

        macro = context.get("macro")
        if macro is not None and getattr(macro, "upcoming_events", None):
            for ev in macro.upcoming_events[:4]:
                if ev.hours_until is not None:
                    out.key_catalysts.append(
                        f"{ev.scheduled_at:%Y-%m-%d %H:%M}Z - {ev.name} "
                        f"(in {ev.hours_until:.0f}h, {ev.importance})"
                    )

        # Only genuinely FORWARD-looking items belong here. A regulatory action
        # that already happened is context, not an upcoming catalyst - listing it
        # as one would misrepresent the timeline.
        reg = context.get("regulation")
        if reg is not None and getattr(reg, "available", False):
            for e in reg.events[:3]:
                if e.legal_status in (LegalStatus.VOTE_SCHEDULED, LegalStatus.CONSULTATION):
                    out.key_catalysts.append(
                        f"[{e.legal_status.value}] {e.title[:100]}"
                    )
                elif e.legal_status.is_binding and e.importance >= 75:
                    # Recent binding decisions still shape the days ahead, but
                    # they are labelled as already-decided.
                    out.recent_decisions.append(
                        f"[{e.legal_status.value}, {e.published_at:%Y-%m-%d}] {e.title[:100]}"
                    )

        deriv = context.get("derivatives")
        if deriv is not None and getattr(deriv, "warnings", None):
            out.key_risks.extend(deriv.warnings)
        if contradictions.is_high:
            out.key_risks.append(
                "Signals are strongly contradictory - conviction is capped and position "
                "sizing should reflect that"
            )
        geo = context.get("geopolitics")
        if geo is not None and getattr(geo, "level", None) and geo.level.value in ("HIGH", "EXTREME"):
            out.key_risks.append(f"Geopolitical risk {geo.level.value}: {geo.crypto_implication[:180]}")

        out.what_would_change_my_mind = self._change_my_mind(asset, analysts, context)
        out.scenarios = self._scenarios(asset, conviction, context)

        stale = [a.domain for a in available.values() if a.freshness.value in ("STALE",)]
        out.data_quality_note = (
            f"{len(available)}/{len(analysts)} domains available. "
            + (f"Stale: {', '.join(stale)}. " if stale else "")
            + (f"Missing: {', '.join(unavailable)}." if unavailable else "")
        )

        direction = conviction.medium.direction.value
        out.synthesis = (
            f"{asset.value}: medium-term conviction {conviction.medium.score:+.1f} "
            f"({conviction.medium.label}, {conviction.medium.confidence:.0f}% confidence). "
            f"Short term {conviction.short.score:+.1f}, long term {conviction.long.score:+.1f}. "
            f"{len(out.positives)} supportive and {len(out.negatives)} adverse domain signals; "
            f"{len(out.contradictions)} contradiction(s) detected. "
            f"Direction {direction}. "
            + (
                "Note that a low-confidence reading means the data does not currently support "
                "a firm view."
                if conviction.medium.confidence < 40 else ""
            )
        )
        return out

    def _change_my_mind(self, asset, analysts, context) -> list[str]:
        """Falsifiable conditions - the most useful part of any analysis."""
        out: list[str] = []
        snapshots = context.get("snapshots") or {}
        daily = next((s for tf, s in snapshots.items() if tf.value == "1d" and s and s.has_data), None)
        if daily:
            if daily.levels_support:
                lv = daily.levels_support[0]
                out.append(
                    f"A daily close below {lv.price:,.0f} would break the nearest support "
                    f"({lv.touches} touches) and invalidate the constructive technical read"
                )
            if daily.levels_resistance:
                lv = daily.levels_resistance[0]
                out.append(
                    f"A daily close above {lv.price:,.0f} on above-average volume would clear "
                    "the nearest resistance and invalidate the cautious read"
                )
            for p in daily.patterns[:1]:
                if p.invalidation_level:
                    out.append(
                        f"The {p.pattern} is invalidated at {p.invalidation_level:,.0f}"
                    )

        etf = context.get("etf")
        if etf is not None and getattr(etf, "available", False):
            if etf.strength > 0:
                out.append(
                    "Three consecutive days of ETF outflows would remove the main pillar of "
                    "the constructive case"
                )
            else:
                out.append(
                    "A sustained return to ETF inflows would materially improve the picture"
                )

        macro = context.get("macro")
        if macro is not None and getattr(macro, "imminent_event", None):
            out.append(
                f"The outcome of {macro.imminent_event.name} could reset the macro read entirely"
            )
        return out[:6]

    def _scenarios(self, asset, conviction: ConvictionResult, context) -> list[Scenario]:
        """Three scenarios with indicative analytical probabilities.

        The probabilities are heuristic, derived from conviction and confidence.
        They are explicitly NOT calibrated, and every rendering says so.
        """
        snapshots = context.get("snapshots") or {}
        daily = next((s for tf, s in snapshots.items() if tf.value == "1d" and s and s.has_data), None)
        price = daily.price if daily else None
        support = daily.levels_support[0].price if daily and daily.levels_support else None
        resistance = daily.levels_resistance[0].price if daily and daily.levels_resistance else None

        score = conviction.medium.score
        confidence = conviction.medium.confidence

        # Lean the distribution toward the conviction, but keep it humble:
        # the central case never exceeds 60% and both tails stay meaningful.
        lean = max(-1.0, min(1.0, score / 100.0)) * (confidence / 100.0)
        central = 45.0 + confidence * 0.15
        bull = 27.5 + lean * 20.0
        bear = 27.5 - lean * 20.0
        total = central + bull + bear
        central, bull, bear = (x / total * 100.0 for x in (central, bull, bear))

        levels_bull = {k: v for k, v in {"resistance": resistance, "current": price}.items() if v}
        levels_bear = {k: v for k, v in {"support": support, "current": price}.items() if v}

        catalysts = []
        macro = context.get("macro")
        if macro is not None and getattr(macro, "upcoming_events", None):
            catalysts = [e.name for e in macro.upcoming_events[:3]]

        return [
            Scenario(
                name="central", label="Continuation of the current configuration",
                probability=round(central, 1), calibrated=False,
                narrative=(
                    f"The dominant signals ({conviction.medium.label}, "
                    f"{conviction.medium.confidence:.0f}% confidence) persist without a "
                    "decisive catalyst; price works within the identified levels."
                ),
                conditions=["No major macro or regulatory shock", "ETF flows stay in their recent range"],
                key_levels={k: v for k, v in {"support": support, "resistance": resistance}.items() if v},
                catalysts=catalysts,
                invalidation="A decisive break of either boundary on strong volume",
            ),
            Scenario(
                name="bull", label="Upside resolution",
                probability=round(bull, 1), calibrated=False,
                narrative=(
                    "Resistance is cleared on rising volume with ETF inflows accelerating and "
                    "no macro deterioration."
                ),
                conditions=(
                    [f"Daily close above {resistance:,.0f} with volume above average"] if resistance
                    else ["Daily close above the nearest resistance on strong volume"]
                ) + ["ETF flows accelerate", "Dollar weakens or stays flat"],
                key_levels=levels_bull, catalysts=catalysts,
                invalidation="Failure to hold the breakout level on a daily close",
            ),
            Scenario(
                name="bear", label="Downside resolution",
                probability=round(bear, 1), calibrated=False,
                narrative=(
                    "Support gives way with ETF flows turning negative, or a macro/regulatory "
                    "shock forces broad risk reduction."
                ),
                conditions=(
                    [f"Daily close below {support:,.0f}"] if support
                    else ["Daily close below the nearest support"]
                ) + ["ETF flows turn persistently negative", "Risk appetite deteriorates"],
                key_levels=levels_bear, catalysts=catalysts,
                invalidation="Reclaiming the broken support on a daily close",
            ),
        ]

    # --- LLM path ----------------------------------------------------------

    async def _llm_synthesis(
        self, result, asset, analysts, conviction, contradictions, context
    ) -> None:
        block = self._build_conclusions_block(asset, analysts, conviction, contradictions, context)

        system = (
            "You are the chief market analyst of a personal crypto research tool. You receive "
            "the STRUCTURED CONCLUSIONS of specialist analysts - never raw data. Your job is to "
            "find convergence, divergence, contradictions, missing data, catalysts and risks, "
            "and to lay out scenarios.\n\n"
            "You never recommend a trade, an entry, an exit or a position size. You explain "
            "what the evidence supports; the human decides.\n\n"
            f"{ANTI_HALLUCINATION_RULES}\n\n"
            "Probabilities you give are INDICATIVE ANALYTICAL estimates, never calibrated "
            "statistics. Be concise and specific. No filler, no hedging boilerplate."
        )
        user = (
            f"ASSET: {asset.value}\n\nANALYST CONCLUSIONS AND COMPUTED SCORES:\n{block}\n\n"
            "Return a JSON object with: synthesis (a few precise paragraphs), positives, "
            "negatives, contradictions, key_catalysts, key_risks, what_would_change_my_mind, "
            "scenarios (exactly 3: central, bull, bear, each with name, label, probability, "
            "narrative, conditions, key_levels, catalysts, invalidation), missing_data, "
            "data_quality_note."
        )

        output: ChiefAnalystOutput = await self.llm.complete_json(system, user, ChiefAnalystOutput)

        unsupported = find_unsupported_numbers(output.synthesis, block)
        if unsupported:
            log.warning("chief_hallucination_blocked", asset=asset.value, unsupported=unsupported[:5])
            result.missing_data.append(
                f"LLM synthesis rejected: cited values absent from the analyst conclusions "
                f"({unsupported[:3]}). Deterministic synthesis shown instead."
            )
            return

        result.synthesis = output.synthesis
        result.llm_used = True
        if output.positives:
            result.positives = output.positives
        if output.negatives:
            result.negatives = output.negatives
        if output.contradictions:
            result.contradictions = output.contradictions
        if output.key_catalysts:
            result.key_catalysts = output.key_catalysts
        if output.key_risks:
            result.key_risks = output.key_risks
        if output.what_would_change_my_mind:
            result.what_would_change_my_mind = output.what_would_change_my_mind
        if output.data_quality_note:
            result.data_quality_note = output.data_quality_note
        if output.scenarios:
            result.scenarios = [
                Scenario(
                    name=s.name, label=s.label, probability=s.probability, calibrated=False,
                    narrative=s.narrative, conditions=s.conditions, key_levels=s.key_levels,
                    catalysts=s.catalysts, invalidation=s.invalidation,
                )
                for s in output.scenarios
            ]

    def _build_conclusions_block(
        self, asset, analysts, conviction, contradictions, context
    ) -> str:
        """Compact, sourced summary - conclusions only, no raw series."""
        lines: list[str] = []
        lines.append(
            f"CONVICTION short={conviction.short.score:+.1f} ({conviction.short.label}, "
            f"{conviction.short.confidence:.0f}%) | "
            f"medium={conviction.medium.score:+.1f} ({conviction.medium.label}, "
            f"{conviction.medium.confidence:.0f}%) | "
            f"long={conviction.long.score:+.1f} ({conviction.long.label}, "
            f"{conviction.long.confidence:.0f}%)"
        )
        lines.append("")
        lines.append("ANALYSTS:")
        for a in analysts.values():
            if not a.available:
                lines.append(f"- {a.domain}: {a.unavailable_reason}")
                continue
            lines.append(
                f"- {a.domain}: score {a.score:+.1f}, confidence {a.confidence:.0f}%, "
                f"freshness {a.freshness.value}, direction {a.direction.value}"
            )
            lines.append(f"    summary: {a.summary[:300]}")
            for p in a.positives[:3]:
                lines.append(f"    + {p[:200]}")
            for n in a.negatives[:3]:
                lines.append(f"    - {n[:200]}")

        if contradictions.contradictions:
            lines.append("")
            lines.append("CONTRADICTIONS:")
            for c in contradictions.contradictions:
                lines.append(f"- [{c.strength:.0f}/100] {c.description}")

        snapshots = context.get("snapshots") or {}
        daily = next((s for tf, s in snapshots.items() if tf.value == "1d" and s and s.has_data), None)
        if daily:
            lines.append("")
            lines.append("KEY LEVELS (daily):")
            lines.append(f"- price: {daily.price}")
            if daily.levels_support:
                lines.append("- supports: " + ", ".join(str(lv.price) for lv in daily.levels_support[:3]))
            if daily.levels_resistance:
                lines.append("- resistances: " + ", ".join(str(lv.price) for lv in daily.levels_resistance[:3]))

        macro = context.get("macro")
        if macro is not None and getattr(macro, "upcoming_events", None):
            lines.append("")
            lines.append("UPCOMING EVENTS:")
            for e in macro.upcoming_events[:5]:
                lines.append(
                    f"- {e.scheduled_at:%Y-%m-%d %H:%M}Z {e.name} ({e.importance}, "
                    f"in {e.hours_until:.0f}h)"
                )
        return "\n".join(lines)

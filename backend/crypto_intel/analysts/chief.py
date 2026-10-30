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
        out.scenarios = self._scenarios(asset, conviction, context, contradictions)

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

    def _scenarios(
        self,
        asset: Asset,
        conviction: ConvictionResult,
        context: dict[str, Any],
        contradiction_report: ContradictionReport | None = None,
    ) -> list[Scenario]:
        """Three conditional scenarios, deliberately without probabilities.

        Conviction and confidence help describe the current base case but are
        not a calibrated distribution of future returns.  Converting them
        into percentages would add false precision.  Conditions are emitted
        only for inputs that are actually present in the validated context.
        """
        snapshots = context.get("snapshots") or {}
        daily = next(
            (
                snapshot
                for timeframe, snapshot in snapshots.items()
                if getattr(timeframe, "value", timeframe) == "1d"
                and snapshot
                and snapshot.has_data
            ),
            None,
        )
        price = daily.price if daily else None
        support = daily.levels_support[0].price if daily and daily.levels_support else None
        resistance = daily.levels_resistance[0].price if daily and daily.levels_resistance else None

        levels_all = {
            key: value
            for key, value in {
                "support": support,
                "resistance": resistance,
                "current": price,
            }.items()
            if value is not None
        }
        levels_bull = {
            key: value
            for key, value in {"resistance": resistance, "current": price}.items()
            if value is not None
        }
        levels_bear = {
            key: value
            for key, value in {"support": support, "current": price}.items()
            if value is not None
        }

        catalysts: list[str] = []
        macro = context.get("macro")
        if macro is not None and getattr(macro, "upcoming_events", None):
            catalysts = [e.name for e in macro.upcoming_events[:3]]

        etf = context.get("etf")
        raw_etf_total = (
            getattr(etf, "latest_total", None)
            if etf is not None and getattr(etf, "available", False)
            else None
        )
        etf_total = (
            float(raw_etf_total)
            if isinstance(raw_etf_total, int | float) and not isinstance(raw_etf_total, bool)
            else None
        )
        etf_available = etf_total is not None

        dollar_trend = (
            getattr(macro, "dollar_trend", "UNKNOWN")
            if macro is not None and getattr(macro, "available", False)
            else "UNKNOWN"
        )
        dollar_available = dollar_trend not in (None, "", "UNKNOWN", "UNAVAILABLE")

        liquidity = context.get("liquidity")
        liquidity_regime = (
            getattr(liquidity, "regime", "UNKNOWN")
            if liquidity is not None and getattr(liquidity, "available", False)
            else "UNKNOWN"
        )
        liquidity_available = liquidity_regime not in (None, "", "UNKNOWN", "UNAVAILABLE")

        derivatives = context.get("derivatives")
        funding_state = (
            getattr(derivatives, "funding_state", "UNAVAILABLE")
            if derivatives is not None and getattr(derivatives, "available", False)
            else "UNAVAILABLE"
        )
        funding_available = funding_state not in (None, "", "UNKNOWN", "UNAVAILABLE")

        confirmed: list[str] = [
            (
                f"The computed medium-horizon diagnostic is {conviction.medium.label} "
                f"(score {conviction.medium.score:+.1f}; confidence "
                f"{conviction.medium.confidence:.0f}%, not a scenario probability)."
            )
        ]
        if price is not None:
            confirmed.append(f"The latest validated daily price is {price:,.6g}.")
        if support is not None:
            confirmed.append(f"Measured daily support is {support:,.6g}.")
        if resistance is not None:
            confirmed.append(f"Measured daily resistance is {resistance:,.6g}.")
        if etf_available:
            confirmed.append(f"The latest validated ETF net flow is {etf_total:+,.1f} MUSD.")
        if dollar_available:
            confirmed.append(f"The measured dollar trend is {dollar_trend}.")
        if liquidity_available:
            confirmed.append(f"The measured stablecoin-liquidity regime is {liquidity_regime}.")
        if funding_available:
            confirmed.append(f"The measured funding state is {funding_state}.")

        report = contradiction_report or context.get("contradictions")
        conflicts = list(getattr(report, "contradictions", []) or [])
        common_uncertainties = [
            "No calibrated scenario model is available; probability is intentionally not quantified."
        ]
        if daily is None:
            common_uncertainties.append(
                "No validated daily technical snapshot is available to define price boundaries."
            )
        if not etf_available:
            common_uncertainties.append(
                "Validated ETF net-flow data is unavailable for this scenario calculation."
            )
        if not dollar_available:
            common_uncertainties.append(
                "A validated dollar-trend input is unavailable for this scenario calculation."
            )
        common_uncertainties.extend(
            f"Contradictory evidence: {conflict.description}" for conflict in conflicts[:3]
        )

        high_contradiction = bool(getattr(report, "is_high", False))
        prudence_note = (
            "High signal contradiction: require multiple independent confirmations, treat all "
            "paths as conditional, and do not interpret confidence as probability."
            if high_contradiction
            else (
                "Treat this as a conditional path, not a forecast or an automated order; "
                "reassess when a confirmation or invalidation signal is observed."
            )
        )

        central_conditions: list[str] = []
        central_confirmation: list[str] = []
        if support is not None and resistance is not None:
            central_conditions.append(
                f"Daily closes remain between measured support {support:,.6g} and "
                f"resistance {resistance:,.6g}"
            )
            central_confirmation.append("Repeated daily closes remain inside the measured range")
        elif support is not None:
            central_conditions.append(f"Measured daily support {support:,.6g} continues to hold")
            central_confirmation.append("Daily closes continue to hold measured support")
        elif resistance is not None:
            central_conditions.append(
                f"No confirmed daily break above measured resistance {resistance:,.6g}"
            )
            central_confirmation.append("Daily closes remain below measured resistance")
        if etf_total is not None:
            flow_condition = (
                "Observed ETF net inflows do not reverse into sustained outflows"
                if etf_total >= 0
                else "Observed ETF net outflows do not materially accelerate"
            )
            central_conditions.append(flow_condition)
            central_confirmation.append("Validated ETF flows remain near their observed regime")
        if dollar_available:
            central_conditions.append(f"The measured dollar trend remains {dollar_trend.lower()}")
            central_confirmation.append("The validated dollar-trend classification is unchanged")

        bull_conditions: list[str] = []
        bull_confirmation: list[str] = []
        if resistance is not None:
            volume_known = getattr(daily, "volume_state", "UNAVAILABLE") != "UNAVAILABLE"
            suffix = " with confirming volume" if volume_known else ""
            bull_conditions.append(
                f"A daily close holds above measured resistance {resistance:,.6g}{suffix}"
            )
            bull_confirmation.append("The measured resistance becomes support on a later close")
        if etf_total is not None:
            bull_conditions.append(
                "Validated ETF net outflows reverse into sustained inflows"
                if etf_total < 0
                else "Validated ETF net inflows persist and strengthen"
            )
            bull_confirmation.append("Several validated ETF observations confirm positive flows")
        if dollar_available:
            bull_conditions.append(
                "The measured dollar uptrend weakens or reverses"
                if dollar_trend == "STRENGTHENING"
                else "The measured dollar trend does not turn strengthening"
            )
            bull_confirmation.append("A subsequent dollar-trend reading remains non-strengthening")
        if liquidity_available:
            bull_conditions.append(
                "The measured stablecoin-liquidity contraction reverses"
                if "CONTRACTION" in liquidity_regime
                else "The measured stablecoin-liquidity regime persists or improves"
            )
            bull_confirmation.append("A later liquidity reading confirms improvement")
        if funding_available and funding_state == "EXTREME_POSITIVE":
            bull_conditions.append("Funding leaves its measured extreme-positive state")
            bull_confirmation.append("Funding cools without invalidating the price structure")

        bear_conditions: list[str] = []
        bear_confirmation: list[str] = []
        if support is not None:
            bear_conditions.append(f"A daily close holds below measured support {support:,.6g}")
            bear_confirmation.append("The measured support becomes resistance on a later close")
        if etf_total is not None:
            bear_conditions.append(
                "Validated ETF net inflows reverse into sustained outflows"
                if etf_total >= 0
                else "Validated ETF net outflows persist and deepen"
            )
            bear_confirmation.append("Several validated ETF observations confirm negative flows")
        if dollar_available:
            bear_conditions.append(
                "The measured dollar uptrend persists"
                if dollar_trend == "STRENGTHENING"
                else "The measured dollar trend turns strengthening"
            )
            bear_confirmation.append("A subsequent dollar-trend reading confirms strengthening")
        if liquidity_available:
            bear_conditions.append(
                "The measured stablecoin-liquidity contraction persists"
                if "CONTRACTION" in liquidity_regime
                else "The measured stablecoin-liquidity regime deteriorates into contraction"
            )
            bear_confirmation.append("A later liquidity reading confirms deterioration")
        if funding_available and funding_state == "EXTREME_POSITIVE":
            bear_conditions.append("Extreme-positive funding unwinds alongside weakening price")
            bear_confirmation.append("Validated funding and price readings confirm deleveraging")

        def narrative(label: str, conditions: list[str]) -> str:
            if not conditions:
                return (
                    f"{label} remains underspecified because the validated context contains no "
                    "scenario-specific trigger."
                )
            return f"{label} is conditional on: " + "; ".join(conditions[:4]) + "."

        def unavailable_invalidation() -> str:
            return "Cannot be specified until a validated scenario trigger is available"

        return [
            Scenario(
                name="central", label="Intermediate / continuation of the current configuration",
                probability=None, calibrated=False,
                narrative=narrative("The intermediate path", central_conditions),
                horizon="8-30 days", affected_assets=[asset],
                confirmed_evidence=confirmed,
                conditions=central_conditions,
                confirmation_signals=central_confirmation,
                key_levels=levels_all,
                catalysts=catalysts,
                invalidation=(
                    f"A confirmed daily close outside {support:,.6g}-{resistance:,.6g}"
                    if support is not None and resistance is not None
                    else (
                        "A sustained reversal in the validated ETF-flow regime"
                        if etf_available
                        else unavailable_invalidation()
                    )
                ),
                uncertainties=common_uncertainties,
                prudence_note=prudence_note,
            ),
            Scenario(
                name="bull", label="Favourable / upside resolution",
                probability=None, calibrated=False,
                narrative=narrative("The favourable path", bull_conditions),
                horizon="8-30 days", affected_assets=[asset],
                confirmed_evidence=confirmed,
                conditions=bull_conditions,
                confirmation_signals=bull_confirmation,
                key_levels=levels_bull, catalysts=catalysts,
                invalidation=(
                    f"A daily close falls back below measured resistance {resistance:,.6g}"
                    if resistance is not None
                    else (
                        "Validated ETF flows fail to improve or reverse lower"
                        if etf_available
                        else unavailable_invalidation()
                    )
                ),
                uncertainties=common_uncertainties,
                prudence_note=prudence_note,
            ),
            Scenario(
                name="bear", label="Unfavourable / downside resolution",
                probability=None, calibrated=False,
                narrative=narrative("The unfavourable path", bear_conditions),
                horizon="8-30 days", affected_assets=[asset],
                confirmed_evidence=confirmed,
                conditions=bear_conditions,
                confirmation_signals=bear_confirmation,
                key_levels=levels_bear, catalysts=catalysts,
                invalidation=(
                    f"A daily close reclaims measured support {support:,.6g}"
                    if support is not None
                    else (
                        "Validated ETF flows fail to deteriorate or reverse higher"
                        if etf_available
                        else unavailable_invalidation()
                    )
                ),
                uncertainties=common_uncertainties,
                prudence_note=prudence_note,
            ),
        ]

    # --- LLM path ----------------------------------------------------------

    async def _llm_synthesis(
        self, result, asset, analysts, conviction, contradictions, context
    ) -> None:
        llm = self.llm
        if llm is None:
            return
        block = self._build_conclusions_block(asset, analysts, conviction, contradictions, context)

        system = (
            "You are the chief market analyst of a personal crypto research tool. You receive "
            "the STRUCTURED CONCLUSIONS of specialist analysts - never raw data. Your job is to "
            "find convergence, divergence, contradictions, missing data, catalysts and risks, "
            "and to lay out scenarios.\n\n"
            "You never recommend a trade, an entry, an exit or a position size. You explain "
            "what the evidence supports; the human decides.\n\n"
            f"{ANTI_HALLUCINATION_RULES}\n\n"
            "Never generate scenario probabilities. The deterministic engine owns scenarios "
            "and their conditions. Be concise and specific. No filler, no hedging boilerplate."
        )
        user = (
            f"ASSET: {asset.value}\n\nANALYST CONCLUSIONS AND COMPUTED SCORES:\n{block}\n\n"
            "Return a JSON object with: synthesis (a few precise paragraphs), positives, "
            "negatives, contradictions, key_catalysts, key_risks, what_would_change_my_mind, "
            "scenarios as an empty list (the deterministic engine already supplied them), "
            "missing_data, data_quality_note."
        )

        output: ChiefAnalystOutput = await llm.complete_json(system, user, ChiefAnalystOutput)

        # Validate every LLM-authored narrative field that may replace or be
        # copied into ChiefSynthesis, not only the headline synthesis.
        copied_narrative = [
            output.synthesis,
            *output.positives,
            *output.negatives,
            *output.contradictions,
            *output.key_catalysts,
            *output.key_risks,
            *output.what_would_change_my_mind,
            output.data_quality_note,
        ]
        unsupported = find_unsupported_numbers("\n".join(copied_narrative), block)
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
        # Scenarios remain the deterministic ones built above.  Narrative
        # output cannot replace their levels, conditions or probabilities.

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

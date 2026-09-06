"""Analyst layer.

Each analyst owns one domain and produces a STRUCTURED output. There is no
single giant prompt receiving everything: each LLM call is small, focused and
schema-constrained, which is what keeps the model grounded.

Every analyst works in two modes:
  * rule-based  - always available, no LLM required;
  * LLM-assisted - adds narrative and links in knowledge-base passages.

The rule-based path is the source of the SCORE. The LLM adds explanation, never
the number - so a model outage degrades prose, not analysis.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from ..core.enums import Asset, Direction, Freshness
from ..core.models import Interpretation, ScoreCard
from ..knowledge.store import get_retriever
from ..llm.base import LLMProvider
from ..llm.schemas import AnalystOutput
from ..llm.validation import ANTI_HALLUCINATION_RULES, find_unsupported_numbers
from ..logging_setup import get_logger

log = get_logger("analysts")


class AnalystResult(BaseModel):
    """What every analyst returns to the pipeline."""

    analyst: str
    domain: str
    asset: Asset | None = None
    available: bool = True
    unavailable_reason: str | None = None

    score: float = 0.0
    confidence: float = 0.0
    freshness: Freshness = Freshness.UNAVAILABLE
    direction: Direction = Direction.INCONCLUSIVE

    summary: str = ""
    positives: list[str] = Field(default_factory=list)
    negatives: list[str] = Field(default_factory=list)
    neutral: list[str] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)

    evidence_ids: list[str] = Field(default_factory=list)
    knowledge_citations: list[dict[str, Any]] = Field(default_factory=list)
    interpretations: list[Interpretation] = Field(default_factory=list)
    llm_used: bool = False
    raw: dict[str, Any] = Field(default_factory=dict)

    def to_scorecard(self) -> ScoreCard:
        if not self.available:
            return ScoreCard.unavailable_card(self.domain, self.unavailable_reason or "UNAVAILABLE")
        return ScoreCard(
            domain=self.domain, score=self.score, confidence=self.confidence,
            freshness=self.freshness, evidence_count=len(self.evidence_ids),
            evidence_ids=self.evidence_ids[:20],
            notes=(self.positives + self.negatives)[:6],
        )


class BaseAnalyst(ABC):
    """One domain, one analyst."""

    name: str = "base"
    domain: str = "base"
    knowledge_category: str | None = None
    uses_llm: bool = True

    def __init__(self, llm: LLMProvider | None = None) -> None:
        self.llm = llm

    @abstractmethod
    def analyze_rules(self, asset: Asset, context: dict[str, Any]) -> AnalystResult:
        """Deterministic analysis. Must never require an LLM."""

    def knowledge_query(self, result: AnalystResult, context: dict[str, Any]) -> str | None:
        """Query used to pull relevant passages from the personal knowledge base."""
        return None

    async def analyze(self, asset: Asset, context: dict[str, Any]) -> AnalystResult:
        result = self.analyze_rules(asset, context)

        if result.available:
            query = self.knowledge_query(result, context)
            if query:
                try:
                    passages = get_retriever().search(
                        query, limit=3, category=self.knowledge_category
                    )
                    result.knowledge_citations = [
                        {
                            "document": p["document_title"],
                            "category": p["category"],
                            "chunk_id": p["chunk_id"],
                            "excerpt": p["text"][:400],
                        }
                        for p in passages
                    ]
                except Exception as exc:
                    log.debug("knowledge_lookup_failed", analyst=self.name, error=str(exc))

        if self.llm and self.uses_llm and result.available:
            try:
                await self._enrich_with_llm(result, asset, context)
            except Exception as exc:
                # An LLM failure must never invalidate a computed analysis.
                log.info("llm_enrichment_failed", analyst=self.name, error=str(exc)[:200])
                result.missing_data.append(f"LLM narrative unavailable ({type(exc).__name__})")

        return result

    async def _enrich_with_llm(
        self, result: AnalystResult, asset: Asset, context: dict[str, Any]
    ) -> None:
        """Ask the model to explain the computed findings - never to produce the score."""
        data_block = self.build_data_block(result, asset, context)
        knowledge_block = ""
        if result.knowledge_citations:
            knowledge_block = "\n\nYOUR OWN COURSE NOTES (use to explain concepts, cite by document name):\n"
            for c in result.knowledge_citations:
                knowledge_block += f"\n[{c['document']}] {c['excerpt'][:350]}\n"

        system = (
            f"You are a specialist {self.domain} analyst inside a personal crypto research "
            f"tool. You explain what the computed data means. You never place trades and "
            f"never recommend one.\n\n{ANTI_HALLUCINATION_RULES}\n\n"
            "The numeric score has ALREADY been computed by deterministic code. Do not "
            "invent a different one: return the score you are given."
        )
        user = (
            f"ASSET: {asset.value}\n"
            f"DOMAIN: {self.domain}\n"
            f"COMPUTED SCORE: {result.score:+.1f} (confidence {result.confidence:.0f}%)\n"
            f"DATA FRESHNESS: {result.freshness.value}\n\n"
            f"DATA:\n{data_block}\n{knowledge_block}\n\n"
            "Return a JSON object with fields: analyst, summary, score, confidence, "
            "positives (list of {statement, direction, importance, evidence_refs}), "
            "negatives (same shape), missing_data (list of strings), "
            "knowledge_citations (list of document names you actually used).\n"
            "The summary must be factual, concise and free of filler."
        )

        output: AnalystOutput = await self.llm.complete_json(system, user, AnalystOutput)

        # Grounding check: any number the model wrote must trace back to the data.
        unsupported = find_unsupported_numbers(output.summary, data_block)
        if unsupported:
            log.warning(
                "llm_hallucination_blocked", analyst=self.name, asset=asset.value,
                unsupported=unsupported[:5],
            )
            result.missing_data.append(
                f"LLM narrative rejected: it cited values absent from the data ({unsupported[:3]})"
            )
            return

        result.summary = output.summary
        result.llm_used = True
        for f in output.positives:
            if f.statement not in result.positives:
                result.positives.append(f.statement)
        for f in output.negatives:
            if f.statement not in result.negatives:
                result.negatives.append(f.statement)
        for m in output.missing_data:
            if m not in result.missing_data:
                result.missing_data.append(m)

    def build_data_block(
        self, result: AnalystResult, asset: Asset, context: dict[str, Any]
    ) -> str:
        """Compact, sourced text given to the model.

        Deliberately small: the model receives conclusions and key figures, not
        300k lines of raw data.
        """
        lines = [f"Score: {result.score:+.1f}", f"Confidence: {result.confidence:.0f}%",
                 f"Freshness: {result.freshness.value}"]
        if result.positives:
            lines.append("Positive findings:")
            lines += [f"  - {p}" for p in result.positives]
        if result.negatives:
            lines.append("Negative findings:")
            lines += [f"  - {n}" for n in result.negatives]
        if result.neutral:
            lines.append("Neutral observations:")
            lines += [f"  - {n}" for n in result.neutral]
        if result.missing_data:
            lines.append("Missing/unavailable:")
            lines += [f"  - {m}" for m in result.missing_data]
        return "\n".join(lines)

    @staticmethod
    def unavailable(analyst: str, domain: str, asset: Asset, reason: str) -> AnalystResult:
        return AnalystResult(
            analyst=analyst, domain=domain, asset=asset, available=False,
            unavailable_reason=reason, direction=Direction.INCONCLUSIVE,
            freshness=Freshness.UNAVAILABLE, missing_data=[reason],
        )

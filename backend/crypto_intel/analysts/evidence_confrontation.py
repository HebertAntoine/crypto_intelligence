"""DATA SAYS vs KNOWLEDGE BASE SAYS.

Personal course notes are a source of interpretation, never of measurement.
They explain what a configuration is supposed to mean; the measured history
says what it actually preceded. When the two disagree, the disagreement is the
most useful output the system can produce.

The rule this module enforces: a course can never change a number. It can only
sit beside one, clearly labelled, so the reader sees both and knows which is
which.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..core.enums import Asset
from ..logging_setup import get_logger

log = get_logger("analysts.confrontation")


@dataclass(slots=True)
class Confrontation:
    """One measured finding, set against what the notes say about it."""

    topic: str
    data_says: str
    data_evidence: dict[str, Any] = field(default_factory=dict)
    knowledge_says: str | None = None
    knowledge_citations: list[dict[str, Any]] = field(default_factory=list)
    agreement: str = "NO_KNOWLEDGE"   # AGREES | CONTRADICTS | COMPLEMENTS | NO_KNOWLEDGE
    conclusion: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "data_says": self.data_says,
            "data_evidence": self.data_evidence,
            "knowledge_says": self.knowledge_says,
            "knowledge_citations": self.knowledge_citations,
            "agreement": self.agreement,
            "conclusion": self.conclusion,
        }


class EvidenceConfrontationEngine:
    """Builds DATA SAYS / KNOWLEDGE BASE SAYS pairs for the report."""

    name = "evidence_confrontation"

    def confront_rsi(
        self, asset: Asset, rsi_reading: Any, limit: int = 2
    ) -> Confrontation | None:
        """The clearest case: measured RSI behaviour vs the textbook rule."""
        if rsi_reading is None:
            return None

        evidence = rsi_reading.evidence or {}
        if not evidence.get("n"):
            return None

        confrontation = Confrontation(
            topic=f"{asset.value} RSI {rsi_reading.zone.replace('_', ' ').lower()}",
            data_says=rsi_reading.measured_reading,
            data_evidence={
                "rsi": rsi_reading.value,
                "regime": rsi_reading.regime,
                "edge_pp": evidence.get("edge"),
                "sample": evidence.get("n"),
                "win_rate": evidence.get("win_rate"),
                "significant": evidence.get("significant"),
                "confidence": rsi_reading.confidence,
            },
        )

        passages = self._search(
            f"RSI {rsi_reading.zone.replace('_', ' ')} surachat survente retournement momentum",
            limit=limit,
        )
        if not passages:
            confrontation.agreement = "NO_KNOWLEDGE"
            confrontation.conclusion = (
                "No passage in your notes covers this configuration. Only the measured "
                "history is available."
            )
            return confrontation

        confrontation.knowledge_citations = passages
        confrontation.knowledge_says = self._summarise(passages)

        if rsi_reading.contradicts_textbook:
            confrontation.agreement = "CONTRADICTS"
            confrontation.conclusion = (
                f"Historical evidence for {asset.value} currently CONTRADICTS the generic "
                f"rule. In {rsi_reading.regime} regimes this reading preceded "
                f"{evidence.get('edge', 0):+.2f}pp versus comparable days "
                f"(n={evidence.get('n')}). The course describes the general case; the "
                "measurement describes this asset in this regime. Neither overrides the "
                "other - but the measurement is the one with a sample size."
            )
        else:
            confrontation.agreement = "AGREES"
            confrontation.conclusion = (
                f"The measured behaviour for {asset.value} is consistent with the course "
                f"note (edge {evidence.get('edge', 0):+.2f}pp, n={evidence.get('n')})."
            )
        return confrontation

    def confront_entry_timing(
        self, asset: Asset, timing: Any, empirical: Any = None, limit: int = 2
    ) -> Confrontation | None:
        """Timing verdict against what the notes say about entry quality."""
        if timing is None or not getattr(timing, "negatives", None):
            return None

        data_says = timing.summary
        evidence: dict[str, Any] = {
            "timing": getattr(timing.timing, "value", str(timing.timing)),
            "timing_score": timing.timing_score,
            "main_obstacles": timing.negatives[:3],
        }
        if empirical is not None and getattr(empirical, "available", False):
            cell = empirical.horizons.get("7d", {})
            evidence["historical_analogues"] = {
                "n": cell.get("n"),
                "median_7d": cell.get("median"),
                "win_rate": cell.get("win_rate"),
                "match_level": empirical.match_level,
            }
            risk_reward = empirical.risk_reward
            if risk_reward.get("available"):
                evidence["reward_risk"] = {
                    "mfe_median": risk_reward["mfe_median"],
                    "mae_median": risk_reward["mae_median"],
                    "ratio": risk_reward["reward_risk_ratio"],
                }
                data_says += (
                    f" In {risk_reward['n']} comparable past configurations, price "
                    f"typically reached {risk_reward['mfe_median']:+.1f}% in favour and "
                    f"{risk_reward['mae_median']:+.1f}% against within 7 days."
                )

        confrontation = Confrontation(
            topic=f"{asset.value} entry timing",
            data_says=data_says,
            data_evidence=evidence,
        )

        passages = self._search(
            "point entree gestion risque distance moyenne mobile rapport gain risque",
            limit=limit,
        )
        if passages:
            confrontation.knowledge_citations = passages
            confrontation.knowledge_says = self._summarise(passages)
            confrontation.agreement = "COMPLEMENTS"
            confrontation.conclusion = (
                "Your notes describe the reasoning behind entry quality; the numbers "
                "above measure it for the current configuration."
            )
        else:
            confrontation.agreement = "NO_KNOWLEDGE"
            confrontation.conclusion = "No relevant passage found in your notes."
        return confrontation

    def _search(self, query: str, limit: int) -> list[dict[str, Any]]:
        try:
            from ..knowledge.store import get_retriever

            hits = get_retriever().search(query, limit=limit)
        except Exception as exc:
            log.debug("knowledge_search_failed", error=str(exc))
            return []

        return [
            {
                "document": h.get("document_title", ""),
                "category": h.get("category", ""),
                "chunk_id": h.get("chunk_id"),
                "page": h.get("page"),
                "retrieval": h.get("retrieval", "bm25"),
                "excerpt": (h.get("text") or "")[:420],
            }
            for h in hits
        ]

    @staticmethod
    def _summarise(passages: list[dict[str, Any]]) -> str:
        """Quote the notes; never paraphrase them into a new claim."""
        if not passages:
            return ""
        first = passages[0]
        excerpt = first["excerpt"].strip().replace("\n", " ")
        if len(excerpt) > 260:
            excerpt = excerpt[:260].rsplit(" ", 1)[0] + "…"
        return f'"{excerpt}" — {first["document"]}'

    def build_all(
        self, asset: Asset, context: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Every confrontation available for one asset."""
        out: list[Confrontation] = []

        rsi_reading = context.get("rsi_context")
        if rsi_reading is not None:
            confrontation = self.confront_rsi(asset, rsi_reading)
            if confrontation:
                out.append(confrontation)

        timing = context.get("entry_timing")
        empirical = context.get("empirical")
        if timing is not None:
            confrontation = self.confront_entry_timing(asset, timing, empirical)
            if confrontation:
                out.append(confrontation)

        return [c.to_dict() for c in out]


def format_confrontations(confrontations: list[dict[str, Any]]) -> str:
    """Report rendering, with the two sources clearly separated."""
    if not confrontations:
        return ""

    lines: list[str] = []
    for c in confrontations:
        lines.append(f"  {c['topic'].upper()}")
        lines.append("")
        lines.append("  DATA SAYS:")
        for chunk in _wrap(c["data_says"], 68):
            lines.append(f"    {chunk}")

        if c.get("knowledge_says"):
            lines.append("")
            lines.append("  KNOWLEDGE BASE SAYS:")
            for chunk in _wrap(c["knowledge_says"], 68):
                lines.append(f"    {chunk}")

        if c.get("conclusion"):
            lines.append("")
            marker = "!" if c["agreement"] == "CONTRADICTS" else " "
            lines.append(f"  {marker} CONCLUSION:")
            for chunk in _wrap(c["conclusion"], 68):
                lines.append(f"    {chunk}")
        lines.append("")
    return "\n".join(lines)


def _wrap(text: str, width: int) -> list[str]:
    import textwrap

    return textwrap.wrap(text, width=width) or [""]

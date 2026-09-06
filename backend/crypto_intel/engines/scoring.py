"""ScoreCard construction from each analyzer's output.

Every domain score arrives with:
  score          -100..+100
  confidence     0..100      how much we trust this reading
  freshness      how recent the underlying evidence is
  evidence_count how many facts back it

Confidence is derived from data availability, evidence volume and freshness -
never asserted. A domain with one stale datapoint cannot report 90% confidence.
"""

from __future__ import annotations

from typing import Any

from ..core.enums import Freshness
from ..core.models import ScoreCard


def confidence_from(
    *,
    base: float,
    evidence_count: int,
    freshness: Freshness,
    penalties: float = 0.0,
) -> float:
    """Blend evidence volume and freshness into a confidence figure."""
    if freshness is Freshness.UNAVAILABLE or evidence_count == 0:
        return 0.0
    # More evidence helps, with diminishing returns; 10+ datapoints is plenty.
    evidence_factor = min(1.0, 0.35 + evidence_count / 10.0 * 0.65)
    freshness_factor = {
        Freshness.LIVE: 1.0, Freshness.MIN_15: 0.98, Freshness.HOUR_1: 0.93,
        Freshness.TODAY: 0.82, Freshness.STALE: 0.45, Freshness.UNAVAILABLE: 0.0,
    }[freshness]
    return max(0.0, min(100.0, base * evidence_factor * freshness_factor - penalties))


class ScoringEngine:
    name = "scoring_engine"

    def technical(self, mtf: Any, snapshots: dict, evidence_ids: list[str] | None = None) -> ScoreCard:
        if not mtf or mtf.timeframes_available == 0:
            return ScoreCard.unavailable_card("technical", "UNAVAILABLE - no market data")

        score = mtf.alignment_score
        components = {v.timeframe.value: v.weight for v in mtf.verdicts if v.available}
        evidence = sum(1 for s in snapshots.values() if s and s.has_data)

        notes: list[str] = list(mtf.conflicts)
        # Pattern and divergence evidence nudges the score, capped so technicals
        # never swing wildly on one detector.
        daily = snapshots.get(next((tf for tf in snapshots if tf.value == "1d"), None))
        if daily and daily.has_data:
            for p in daily.patterns[:2]:
                bump = p.confidence / 100.0 * 12.0
                if p.direction.value == "BULLISH":
                    score += bump
                elif p.direction.value == "BEARISH":
                    score -= bump
                notes.append(f"{p.pattern} ({p.confirmation_state.value}, {p.confidence:.0f}%)")
            for d in daily.divergences[:2]:
                bump = d.strength / 100.0 * 10.0
                if "bull" in d.kind:
                    score += bump
                else:
                    score -= bump
                notes.append(f"{d.indicator} {d.kind} divergence ({d.strength:.0f})")

        # Timeframe disagreement is a reason for less confidence, not a different score.
        penalty = 15.0 if mtf.conflicts else 0.0
        confidence = confidence_from(
            base=88.0, evidence_count=evidence * 3, freshness=mtf.freshness, penalties=penalty
        )
        return ScoreCard(
            domain="technical", score=max(-100.0, min(100.0, score)),
            confidence=confidence, freshness=mtf.freshness,
            evidence_count=evidence, components=components, notes=notes,
            evidence_ids=(evidence_ids or [])[:20],
        )

    def from_analysis(
        self,
        domain: str,
        analysis: Any,
        base_confidence: float = 85.0,
        components: dict[str, float] | None = None,
    ) -> ScoreCard:
        """Generic conversion for analyzers exposing available/strength/freshness."""
        if analysis is None or not getattr(analysis, "available", False):
            reason = getattr(analysis, "unavailable_reason", None) if analysis else None
            return ScoreCard.unavailable_card(domain, reason or f"UNAVAILABLE - no {domain} data")

        evidence_ids = list(getattr(analysis, "evidence_ids", []) or [])
        findings = list(getattr(analysis, "findings", []) or [])
        evidence_count = len(evidence_ids) or len(findings)
        freshness = getattr(analysis, "freshness", Freshness.UNAVAILABLE)

        # An analyzer may state its own confidence (whales do); respect it.
        declared = getattr(analysis, "confidence", None)
        confidence = (
            float(declared)
            if isinstance(declared, int | float) and declared > 0
            else confidence_from(
                base=base_confidence, evidence_count=evidence_count, freshness=freshness
            )
        )
        return ScoreCard(
            domain=domain,
            score=float(getattr(analysis, "strength", 0.0)),
            confidence=confidence,
            freshness=freshness,
            evidence_count=evidence_count,
            components=components or {},
            evidence_ids=evidence_ids[:20],
            notes=findings[:6],
        )

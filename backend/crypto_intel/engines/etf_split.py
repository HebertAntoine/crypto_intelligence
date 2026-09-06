"""ETF context score vs ETF predictive score.

The measurements are unambiguous: ETF flows correlate strongly with the SAME
day's return (+0.41 on BTC) and carry almost nothing about future returns. But
"no predictive edge" is not the same as "not worth showing" - institutional
participation is real information about the market's structure, it simply does
not tell you what happens next.

So the single ETF score is split in two:

  ETF_CONTEXT_SCORE     - how strong institutional participation is right now.
                          Always shown. Makes no claim about the future.
  ETF_PREDICTIVE_SCORE  - only the components with a DEMONSTRATED historical
                          relationship to forward returns, read from stored
                          research. Empty until something demonstrates itself.

This lets the report say the thing that is actually true: participation is
strong, and that has limited measured predictive value at this horizon.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ..core.enums import Asset, Direction, Freshness
from ..logging_setup import get_logger

log = get_logger("engines.etf_split")

# A component enters the predictive score only above this measured effect,
# and only when the study says it survived correction.
MIN_ABS_IC = 0.05
MIN_SAMPLE = 200


class ETFScoreSplit(BaseModel):
    asset: Asset
    available: bool = True
    unavailable_reason: str | None = None

    context_score: float = Field(default=0.0, ge=-100.0, le=100.0)
    context_confidence: float = Field(default=0.0, ge=0.0, le=100.0)
    context_label: str = "UNKNOWN"
    context_findings: list[str] = Field(default_factory=list)

    predictive_score: float = Field(default=0.0, ge=-100.0, le=100.0)
    predictive_confidence: float = Field(default=0.0, ge=0.0, le=100.0)
    predictive_components: list[dict[str, Any]] = Field(default_factory=list)
    predictive_available: bool = False
    predictive_reason: str = ""

    direction: Direction = Direction.INCONCLUSIVE
    freshness: Freshness = Freshness.UNAVAILABLE
    evidence_ids: list[str] = Field(default_factory=list)
    statement: str = ""


class ETFSplitEngine:
    name = "etf_split_engine"

    def split(self, asset: Asset, etf_analysis: Any) -> ETFScoreSplit:
        """Build both scores from an existing ETFFlowAnalysis."""
        if etf_analysis is None or not getattr(etf_analysis, "available", False):
            reason = (
                getattr(etf_analysis, "unavailable_reason", None)
                or f"UNAVAILABLE - no ETF data for {asset.value}"
            )
            return ETFScoreSplit(
                asset=asset, available=False, unavailable_reason=reason,
                statement=reason,
            )

        context_score, context_label, context_findings, context_confidence = (
            self._context(etf_analysis)
        )
        predictive = self._predictive(asset, etf_analysis)

        return ETFScoreSplit(
            asset=asset,
            available=True,
            context_score=context_score,
            context_confidence=context_confidence,
            context_label=context_label,
            context_findings=context_findings,
            predictive_score=predictive["score"],
            predictive_confidence=predictive["confidence"],
            predictive_components=predictive["components"],
            predictive_available=predictive["available"],
            predictive_reason=predictive["reason"],
            direction=(
                Direction.BULLISH if predictive["score"] > 12
                else Direction.BEARISH if predictive["score"] < -12
                else Direction.NEUTRAL if predictive["available"]
                else Direction.INCONCLUSIVE
            ),
            freshness=getattr(etf_analysis, "freshness", Freshness.UNAVAILABLE),
            evidence_ids=list(getattr(etf_analysis, "evidence_ids", []) or [])[:20],
            statement=self._statement(
                asset, context_label, context_score, predictive
            ),
        )

    def _context(self, analysis: Any) -> tuple[float, str, list[str], float]:
        """Current institutional participation. A description, not a forecast."""
        findings: list[str] = []
        score = 0.0

        latest = analysis.latest_total
        ma5 = analysis.ma_5d
        cumulative = analysis.cumulative_30d
        streak = analysis.streak_days or 0
        streak_direction = analysis.streak_direction

        if latest is not None:
            findings.append(f"Latest daily net flow {latest:+.1f}M USD")
            score += max(-40.0, min(40.0, latest / 300.0 * 40.0))
        if ma5 is not None:
            findings.append(f"5-day average {ma5:+.1f}M USD")
            score += max(-30.0, min(30.0, ma5 / 150.0 * 30.0))
        if cumulative is not None:
            findings.append(f"30-day cumulative {cumulative:+.0f}M USD")
            score += max(-20.0, min(20.0, cumulative / 4000.0 * 20.0))
        if streak >= 3 and streak_direction:
            findings.append(f"{streak} consecutive {streak_direction} days")
            score += min(10.0, streak * 2.0) * (1 if streak_direction == "inflow" else -1)

        score = max(-100.0, min(100.0, score))
        if score >= 50:
            label = "STRONG_INSTITUTIONAL_DEMAND"
        elif score >= 15:
            label = "MODERATE_INSTITUTIONAL_DEMAND"
        elif score <= -50:
            label = "STRONG_INSTITUTIONAL_SELLING"
        elif score <= -15:
            label = "MODERATE_INSTITUTIONAL_SELLING"
        else:
            label = "BALANCED"

        # Context confidence is about data quality, not about prediction.
        evidence_count = len(getattr(analysis, "evidence_ids", []) or [])
        freshness = getattr(analysis, "freshness", Freshness.UNAVAILABLE)
        confidence = min(
            100.0,
            60.0 + min(evidence_count, 40) * 0.5,
        ) * (1.0 if freshness.rank >= 2 else 0.5)

        return score, label, findings, round(confidence, 1)

    def _predictive(self, asset: Asset, analysis: Any) -> dict[str, Any]:
        """Only components with a demonstrated forward relationship.

        Reads stored study results rather than assuming. If nothing has
        demonstrated itself, the score is zero and says why - it does not fall
        back on the context score.
        """
        demonstrated = self._load_demonstrated(asset)

        if not demonstrated:
            return {
                "available": False,
                "score": 0.0,
                "confidence": 0.0,
                "components": [],
                "reason": (
                    "No ETF flow component has demonstrated a stable relationship with "
                    f"forward returns for {asset.value} in this system's own studies. "
                    "Measured same-day correlation is high, forward correlation is not, "
                    "so no predictive claim is made. Run `make research` to refresh."
                ),
            }

        components: list[dict[str, Any]] = []
        weighted_sum = 0.0
        total_weight = 0.0

        signal_values = {
            "flow": analysis.latest_total,
            "ma3": analysis.ma_3d,
            "ma5": analysis.ma_5d,
            "ma7": analysis.ma_7d,
            "cum30": analysis.cumulative_30d,
        }

        for entry in demonstrated:
            name = entry["signal"]
            value = signal_values.get(name)
            if value is None:
                continue
            ic = entry["ic"]
            # Scale the current reading into a bounded contribution, signed by
            # the MEASURED direction of the relationship - which may be negative.
            magnitude = max(-1.0, min(1.0, value / entry["scale"]))
            contribution = magnitude * 100.0 * (1.0 if ic > 0 else -1.0)
            weight = abs(ic) * (entry.get("stability", 50.0) / 100.0)

            components.append({
                "signal": name,
                "current_value": round(value, 2),
                "measured_ic": ic,
                "horizon": entry["horizon"],
                "n": entry["n"],
                "stability": entry.get("stability"),
                "contribution": round(contribution, 1),
                "weight": round(weight, 4),
                "relationship": "positive" if ic > 0 else "inverse",
            })
            weighted_sum += contribution * weight
            total_weight += weight

        if total_weight == 0:
            return {
                "available": False, "score": 0.0, "confidence": 0.0, "components": [],
                "reason": "Demonstrated components exist but none has a current value",
            }

        score = max(-100.0, min(100.0, weighted_sum / total_weight))
        # Confidence stays modest by design: these are small effects.
        confidence = min(
            60.0,
            sum(abs(c["measured_ic"]) for c in components) / len(components) * 400.0,
        )

        return {
            "available": True,
            "score": round(score, 1),
            "confidence": round(confidence, 1),
            "components": components,
            "reason": (
                f"{len(components)} component(s) with a demonstrated forward relationship"
            ),
        }

    def _load_demonstrated(self, asset: Asset) -> list[dict[str, Any]]:
        """Components that passed this system's own studies.

        Requires FDR-corrected significance, a minimum effect size and a
        minimum sample. Anything weaker stays out of the predictive score.
        """
        from sqlalchemy import select

        from ..db.base import ResearchResultRow
        from ..db.session import session_scope

        scales = {
            "flow": 400.0, "ma3": 250.0, "ma5": 200.0,
            "ma7": 200.0, "cum30": 4000.0,
        }

        demonstrated: list[dict[str, Any]] = []
        with session_scope() as s:
            rows = s.execute(
                select(ResearchResultRow).where(
                    ResearchResultRow.study == "etf_lag",
                    ResearchResultRow.asset == asset.value,
                    ResearchResultRow.split == "full",
                )
            ).scalars().all()

            for row in rows:
                metrics = row.metrics or {}
                ic = metrics.get("spearman_r")
                if ic is None or not metrics.get("significant"):
                    continue
                if abs(ic) < MIN_ABS_IC or row.sample_size < MIN_SAMPLE:
                    continue
                if row.signal not in scales:
                    continue
                demonstrated.append({
                    "signal": row.signal,
                    "horizon": row.horizon,
                    "ic": ic,
                    "n": row.sample_size,
                    "scale": scales[row.signal],
                    "stability": 50.0,
                })

        # Keep the strongest horizon per signal so one signal cannot vote twice.
        best: dict[str, dict[str, Any]] = {}
        for entry in demonstrated:
            current = best.get(entry["signal"])
            if current is None or abs(entry["ic"]) > abs(current["ic"]):
                best[entry["signal"]] = entry
        return list(best.values())

    @staticmethod
    def _statement(asset: Asset, label: str, context_score: float, predictive: dict) -> str:
        """The sentence the brief asks for, when the two disagree."""
        readable = label.replace("_", " ").lower()
        if not predictive["available"]:
            return (
                f"Institutional participation in {asset.value} is {readable} "
                f"(context score {context_score:+.0f}), but current ETF flows have "
                "limited measured predictive value at this horizon in this system's "
                "own studies."
            )
        return (
            f"Institutional participation in {asset.value} is {readable} "
            f"(context {context_score:+.0f}); the components with a demonstrated "
            f"forward relationship give a predictive score of "
            f"{predictive['score']:+.0f} at {predictive['confidence']:.0f}% confidence."
        )

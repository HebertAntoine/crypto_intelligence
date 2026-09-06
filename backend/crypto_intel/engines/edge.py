"""Edge and uncertainty: what we have actually measured, kept apart from direction.

The distinction this module exists to protect: a market can be strongly
bullish while we hold no measured ability to predict it. Those are answers to
different questions - "where is price going" versus "have we demonstrated we
can tell". Merging them is how a trend-following read gets mistaken for a
tested one, so EdgeState never consults regime direction and regime never
consults EdgeState.

Edge here means one thing only: a signal whose relationship to forward returns
survived FDR correction, out-of-sample testing and a stability check, with an
effect large enough to matter after costs. By that standard the honest answer
across most of this system is NO_MEASURABLE_EDGE, and the engine is built to
say so plainly rather than to find something.
"""

from __future__ import annotations

import json
import pathlib
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from ..core.enums import Asset
from ..logging_setup import get_logger

log = get_logger("engines.edge")

RESEARCH_DIR = pathlib.Path("data/research")

# Below this many independent observations, a result describes its sample and
# nothing beyond it. Overlapping forward windows make the raw row count
# misleading, so this is applied to the EFFECTIVE count.
MIN_INDEPENDENT_OBSERVATIONS = 20

# Round-trip cost assumption: taker fees both sides plus slippage. An "edge"
# smaller than this is not an edge, whatever its p-value.
ROUND_TRIP_COST_PCT = 0.20
MIN_MATERIAL_EFFECT_PCT = 0.50


class EdgeState(StrEnum):
    POSITIVE_EDGE = "POSITIVE_EDGE"
    NEGATIVE_EDGE = "NEGATIVE_EDGE"
    NO_MEASURABLE_EDGE = "NO_MEASURABLE_EDGE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class EdgeEvidence(BaseModel):
    source: str
    signal: str
    horizon_days: int | None = None
    effect_pct: float | None = None
    p_value: float | None = None
    survives_fdr: bool = False
    effective_n: float | None = None
    stability: str | None = None
    admitted: bool = False
    rejection_reason: str = ""


class EdgeAssessment(BaseModel):
    asset: str
    state: EdgeState = EdgeState.INSUFFICIENT_DATA
    horizon_days: int | None = None
    effect_pct: float | None = None
    evidence: list[EdgeEvidence] = Field(default_factory=list)
    admitted_count: int = 0
    rejected_count: int = 0
    criteria: dict[str, Any] = Field(default_factory=dict)
    statement: str = ""
    independent_of_regime: bool = True


class UncertaintyAssessment(BaseModel):
    asset: str
    score: float = Field(default=100.0, description="0-100, higher = less certain")
    level: str = "HIGH"
    drivers: list[dict[str, Any]] = Field(default_factory=list)
    statement: str = ""


class DecisionSummary(BaseModel):
    """The paragraph the whole system exists to produce."""

    asset: str
    market_direction: str = "UNDETERMINED"
    direction_confidence: str = "LOW"
    entry_timing: str = "UNDETERMINED"
    edge_state: EdgeState = EdgeState.INSUFFICIENT_DATA
    crowding: str = "UNKNOWN"
    volatility_regime: str = "UNKNOWN"
    uncertainty: float = 100.0
    actionable: bool = False
    statement: str = ""
    caveats: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EdgeEngine:
    """Decide whether any measured predictive edge exists, per asset."""

    def __init__(self, research_dir: pathlib.Path | None = None) -> None:
        self.research_dir = research_dir or RESEARCH_DIR

    def _load(self, name: str) -> dict[str, Any] | None:
        path = self.research_dir / name
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("research_file_unreadable", file=name, error=str(exc))
            return None

    def assess(self, asset: Asset) -> EdgeAssessment:
        out = EdgeAssessment(asset=asset.value)
        out.criteria = {
            "survives_fdr": "Benjamini-Hochberg at alpha=0.05 across the whole study",
            "min_effective_observations": MIN_INDEPENDENT_OBSERVATIONS,
            "min_effect_pct": MIN_MATERIAL_EFFECT_PCT,
            "round_trip_cost_pct": ROUND_TRIP_COST_PCT,
            "stability": "excess must hold in the majority of years, not one era",
        }

        self._collect_funding_evidence(asset, out)
        self._collect_audit_evidence(asset, out)

        admitted = [e for e in out.evidence if e.admitted]
        out.admitted_count = len(admitted)
        out.rejected_count = len(out.evidence) - len(admitted)

        if not out.evidence:
            out.state = EdgeState.INSUFFICIENT_DATA
            out.statement = (
                f"No research output is available for {asset.value}, so the existence of an "
                "edge has not been tested. This is not the same as having found none."
            )
            return out

        if not admitted:
            out.state = EdgeState.NO_MEASURABLE_EDGE
            out.statement = (
                f"{out.rejected_count} candidate relationships were tested for {asset.value} "
                "and none survived correction for multiple testing, the minimum effective "
                "sample, the effect-size floor and the stability check. There is no "
                "demonstrated ability to predict forward returns. This says nothing about "
                "where the market is going - only that we cannot claim to know."
            )
            return out

        best = max(admitted, key=lambda e: abs(e.effect_pct or 0))
        out.horizon_days = best.horizon_days
        out.effect_pct = best.effect_pct
        out.state = (
            EdgeState.POSITIVE_EDGE if (best.effect_pct or 0) > 0 else EdgeState.NEGATIVE_EDGE
        )
        out.statement = (
            f"{len(admitted)} relationship(s) passed every filter for {asset.value}. "
            f"Strongest: {best.signal} at {best.horizon_days} days, excess "
            f"{best.effect_pct:+.2f}% against baseline on roughly {best.effective_n} "
            f"independent observations. Net of an assumed {ROUND_TRIP_COST_PCT}% round trip, "
            f"about {(abs(best.effect_pct or 0) - ROUND_TRIP_COST_PCT):+.2f}% remains."
        )
        return out

    def _collect_funding_evidence(self, asset: Asset, out: EdgeAssessment) -> None:
        data = self._load("funding_conditioned.json")
        if not data:
            return
        assets = data.get("assets", data)
        result = assets.get(asset.value)
        if not isinstance(result, dict) or result.get("status") != "OK":
            return

        stability = result.get("stability_check", {})
        effective_n = stability.get("effective_independent_windows")
        verdict = stability.get("independence_verdict")
        years_total = stability.get("years_covered", 0)
        years_positive = stability.get("years_with_positive_excess", 0)

        for detail in result.get("survivor_detail", []):
            excess = detail.get("excess_vs_baseline_pct")
            evidence = EdgeEvidence(
                source="funding_conditioned",
                signal=detail.get("cell", "?"),
                effect_pct=excess,
                p_value=detail.get("excess_p_value"),
                survives_fdr=True,
                effective_n=effective_n,
                stability=verdict,
            )
            cell = detail.get("cell", "")
            if cell.endswith("d"):
                tail = cell.rsplit("|", 1)[-1].rstrip("d")
                if tail.isdigit():
                    evidence.horizon_days = int(tail)

            reasons = []
            if detail.get("effect_size_verdict") != "MATERIAL":
                reasons.append(f"effect below the {MIN_MATERIAL_EFFECT_PCT}% floor")
            if excess is not None and abs(excess) <= ROUND_TRIP_COST_PCT:
                reasons.append(f"effect does not clear {ROUND_TRIP_COST_PCT}% costs")
            if effective_n is not None and effective_n < MIN_INDEPENDENT_OBSERVATIONS:
                reasons.append(
                    f"only ~{effective_n} independent windows, below "
                    f"{MIN_INDEPENDENT_OBSERVATIONS}"
                )
            if verdict == "CONCENTRATED":
                reasons.append("effect concentrated in a minority of years")
            if years_total and years_positive < years_total * 0.7:
                reasons.append(f"positive in only {years_positive}/{years_total} years")

            evidence.admitted = not reasons
            evidence.rejection_reason = "; ".join(reasons)
            out.evidence.append(evidence)

    def _collect_audit_evidence(self, asset: Asset, out: EdgeAssessment) -> None:
        """Domain-score audit verdicts: only USEFUL can ever count as edge."""
        data = self._load("research_latest.json") or self._load("audit_latest.json")
        if not data:
            return
        audit = (data.get("audit") or {}).get("assets", {}).get(asset.value)
        if not isinstance(audit, dict):
            return
        for domain, result in (audit.get("domains") or {}).items():
            if not isinstance(result, dict):
                continue
            verdict = result.get("verdict")
            evidence = EdgeEvidence(
                source="domain_audit", signal=f"score.{domain}",
                effect_pct=None, stability=verdict,
                survives_fdr=verdict == "USEFUL",
                rejection_reason="" if verdict == "USEFUL" else f"audit verdict {verdict}",
                admitted=False,
            )
            out.evidence.append(evidence)


class UncertaintyEngine:
    """How much should we distrust today's read, on its own terms."""

    def assess(
        self,
        asset: Asset,
        edge: EdgeAssessment,
        regime: Any = None,
        contradictions: list[Any] | None = None,
        freshness: dict[str, Any] | None = None,
        crowding: Any = None,
    ) -> UncertaintyAssessment:
        out = UncertaintyAssessment(asset=asset.value)
        drivers: list[dict[str, Any]] = []
        score = 0.0

        # 1. No measured edge is the single largest source of uncertainty.
        if edge.state is EdgeState.NO_MEASURABLE_EDGE:
            score += 40
            drivers.append({
                "driver": "no measured edge", "contribution": 40,
                "detail": "no relationship survived the full filter chain",
            })
        elif edge.state is EdgeState.INSUFFICIENT_DATA:
            score += 45
            drivers.append({
                "driver": "edge untested", "contribution": 45,
                "detail": "research output unavailable, so nothing has been verified",
            })
        else:
            score += 15
            drivers.append({
                "driver": "edge measured but modest", "contribution": 15,
                "detail": edge.statement[:120],
            })

        # 2. Regime clarity.
        regime_value = getattr(regime, "regime", None)
        regime_name = getattr(regime_value, "value", regime_value)
        if regime_name in (None, "UNDETERMINED"):
            score += 20
            drivers.append({
                "driver": "regime undetermined", "contribution": 20,
                "detail": "directional read is not established",
            })
        elif regime_name == "NEUTRAL":
            score += 12
            drivers.append({
                "driver": "neutral regime", "contribution": 12,
                "detail": "no clear directional bias",
            })

        # 3. Open contradictions between domains.
        count = len(contradictions or [])
        if count:
            contribution = min(15, count * 5)
            score += contribution
            drivers.append({
                "driver": "unresolved contradictions", "contribution": contribution,
                "detail": f"{count} domain(s) disagree",
            })

        # 4. Stale or missing inputs.
        if freshness:
            stale = [k for k, v in freshness.items() if str(v).upper() in ("STALE", "UNAVAILABLE")]
            if stale:
                contribution = min(15, len(stale) * 3)
                score += contribution
                drivers.append({
                    "driver": "stale or missing data", "contribution": contribution,
                    "detail": ", ".join(stale[:6]),
                })

        # 5. Crowding raises the cost of being wrong, so it raises uncertainty
        # even when the directional read itself is clear.
        level = getattr(getattr(crowding, "level", None), "value", None)
        if level == "EXTREME":
            score += 12
            drivers.append({
                "driver": "extreme crowding", "contribution": 12,
                "detail": "positioning is stretched; moves can be violent in either direction",
            })
        elif level == "ELEVATED":
            score += 6
            drivers.append({
                "driver": "elevated crowding", "contribution": 6, "detail": "positioning above normal",
            })

        out.score = round(min(100.0, score), 1)
        out.level = (
            "VERY_HIGH" if out.score >= 75 else
            "HIGH" if out.score >= 55 else
            "MODERATE" if out.score >= 35 else "LOW"
        )
        out.drivers = sorted(drivers, key=lambda d: -d["contribution"])
        top = ", ".join(d["driver"] for d in out.drivers[:3])
        out.statement = f"Uncertainty {out.level} ({out.score:.0f}/100), driven by: {top}."
        return out


def build_decision_summary(
    asset: Asset,
    edge: EdgeAssessment,
    uncertainty: UncertaintyAssessment,
    regime: Any = None,
    timing: Any = None,
    crowding: Any = None,
    volatility: Any = None,
) -> DecisionSummary:
    """Assemble the sentence, keeping direction and edge visibly separate."""
    summary = DecisionSummary(asset=asset.value, edge_state=edge.state)

    regime_value = getattr(regime, "regime", None)
    summary.market_direction = str(getattr(regime_value, "value", regime_value) or "UNDETERMINED")
    summary.direction_confidence = str(getattr(regime, "confidence", "LOW"))
    timing_value = getattr(timing, "timing", None)
    summary.entry_timing = str(getattr(timing_value, "value", timing_value) or "UNDETERMINED")
    summary.crowding = str(getattr(getattr(crowding, "level", None), "value", "UNKNOWN"))
    summary.volatility_regime = str(getattr(volatility, "regime", None) or "UNKNOWN")
    summary.uncertainty = uncertainty.score

    direction_phrase = {
        "STRONGLY_BULLISH": "is strongly bullish", "BULLISH": "is bullish",
        "NEUTRAL": "is directionless", "BEARISH": "is bearish",
        "STRONGLY_BEARISH": "is strongly bearish",
        "UNDETERMINED": "has no established direction",
    }.get(summary.market_direction, "has no established direction")

    edge_phrase = {
        EdgeState.NO_MEASURABLE_EDGE: (
            "we currently hold no robust directional edge"
        ),
        EdgeState.INSUFFICIENT_DATA: (
            "the existence of an edge has not been tested"
        ),
        EdgeState.POSITIVE_EDGE: (
            f"a measured edge of {edge.effect_pct:+.2f}% exists at "
            f"{edge.horizon_days} days" if edge.effect_pct is not None else "a measured edge exists"
        ),
        EdgeState.NEGATIVE_EDGE: (
            f"the measured relationship runs against the signal "
            f"({edge.effect_pct:+.2f}%)" if edge.effect_pct is not None
            else "the measured relationship runs against the signal"
        ),
    }[edge.state]

    parts = [f"{asset.value} {direction_phrase}, but {edge_phrase}"]
    if summary.crowding in ("ELEVATED", "EXTREME"):
        parts.append(f"and crowding is {summary.crowding.lower()}")
    summary.statement = ", ".join(parts) + "."

    # Actionable only when an edge was actually measured. A clean trend is not
    # a reason to act if we never demonstrated we can read it.
    summary.actionable = edge.state is EdgeState.POSITIVE_EDGE and uncertainty.score < 55
    if not summary.actionable:
        summary.caveats.append(
            "Not actionable: no measured edge clears the evidence bar, so any position "
            "would rest on the narrative, not on a tested relationship."
            if edge.state is not EdgeState.POSITIVE_EDGE else
            f"Edge measured but uncertainty is {uncertainty.level}."
        )
    summary.caveats.append(
        "Market direction and measured edge are computed independently; a bullish "
        "regime is not evidence of predictive ability."
    )
    return summary

"""MarketConvictionEngine.

Explicitly NOT an average of the domain scores. The effective weight of a
score is:

    base_weight(asset, domain)     from config/scoring.yaml, differs per asset
  x confidence_factor(confidence)  a 20%-confidence +90 must not dominate
  x freshness_factor(freshness)    stale data counts little, missing counts zero
  x horizon_factor(domain, horizon) an RSI does not drive the 3-month view

Three convictions are produced separately - short, medium and long term -
because a 15-minute RSI and an FOMC decision act on different clocks and
blending them is how a tool ends up saying nothing useful about either.
"""

from __future__ import annotations

from itertools import pairwise

from pydantic import BaseModel, Field

from ..config_loader import asset_weights, horizon_weights, scoring_config
from ..core.enums import Asset, Direction, Freshness, Horizon
from ..core.freshness import freshness_factor
from ..core.models import Conviction, ScoreCard


def _interp(curve: list[list[float]], x: float) -> float:
    """Piecewise-linear interpolation over the confidence curve."""
    pts = sorted((float(a), float(b)) for a, b in curve)
    if x <= pts[0][0]:
        return pts[0][1]
    if x >= pts[-1][0]:
        return pts[-1][1]
    for (x0, y0), (x1, y1) in pairwise(pts):
        if x0 <= x <= x1:
            if x1 == x0:
                return y1
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return pts[-1][1]


class ConvictionResult(BaseModel):
    asset: Asset
    short: Conviction
    medium: Conviction
    long: Conviction
    overall_confidence: float = 0.0
    domains_available: int = 0
    domains_missing: list[str] = Field(default_factory=list)
    contradiction_penalty: float = 0.0


class MarketConvictionEngine:
    name = "conviction_engine"

    def __init__(self) -> None:
        cfg = scoring_config()
        self.confidence_curve = cfg.get("confidence", {}).get(
            "curve", [[0, 0.05], [50, 0.6], [100, 1.0]]
        )
        self.min_confidence = float(
            cfg.get("confidence", {}).get("min_confidence_to_include", 15)
        )
        self.freshness_table = cfg.get("freshness", {})
        self.labels = cfg.get("labels", [])

    def label_for(self, score: float) -> str:
        for band in self.labels:
            if float(band["min"]) <= score < float(band["max"]):
                return str(band["label"])
        return "NEUTRAL" if abs(score) < 8 else ("BULLISH" if score > 0 else "BEARISH")

    def compute(
        self,
        asset: Asset,
        scores: dict[str, ScoreCard],
        contradiction_strength: float = 0.0,
    ) -> ConvictionResult:
        base_weights = asset_weights(asset.value)
        missing = [
            name for name, card in scores.items()
            if not card.available or card.freshness is Freshness.UNAVAILABLE
        ]
        available_count = sum(1 for c in scores.values() if c.available)

        convictions: dict[Horizon, Conviction] = {}
        for horizon in (Horizon.SHORT, Horizon.MEDIUM, Horizon.LONG):
            convictions[horizon] = self._for_horizon(
                asset, scores, base_weights, horizon, contradiction_strength
            )

        usable = [c.confidence for c in scores.values() if c.available and c.confidence > 0]
        overall_conf = sum(usable) / len(usable) if usable else 0.0
        # Missing domains reduce how much the whole picture can be trusted.
        coverage = available_count / max(1, len(scores))
        overall_conf *= 0.55 + 0.45 * coverage

        return ConvictionResult(
            asset=asset,
            short=convictions[Horizon.SHORT],
            medium=convictions[Horizon.MEDIUM],
            long=convictions[Horizon.LONG],
            overall_confidence=round(min(100.0, overall_conf), 1),
            domains_available=available_count,
            domains_missing=missing,
            contradiction_penalty=contradiction_strength,
        )

    def _for_horizon(
        self,
        asset: Asset,
        scores: dict[str, ScoreCard],
        base_weights: dict[str, float],
        horizon: Horizon,
        contradiction_strength: float,
    ) -> Conviction:
        hz = horizon_weights(horizon.value)
        contributors: dict[str, float] = {}
        rationale: list[str] = []

        weighted_sum = 0.0
        total_weight = 0.0
        confidence_acc = 0.0

        for domain, card in scores.items():
            base = base_weights.get(domain, 0.0)
            if base <= 0:
                # e.g. SOL has etf weight 0 - the domain simply does not apply.
                continue
            if not card.available:
                continue
            if card.confidence < self.min_confidence:
                rationale.append(
                    f"{domain} excluded: confidence {card.confidence:.0f}% below "
                    f"{self.min_confidence:.0f}% floor"
                )
                continue

            conf_factor = _interp(self.confidence_curve, card.confidence)
            fresh_factor = freshness_factor(card.freshness, self.freshness_table)
            horizon_factor = hz.get(domain, 1.0)

            effective = base * conf_factor * fresh_factor * horizon_factor
            if effective <= 0:
                continue

            weighted_sum += card.score * effective
            total_weight += effective
            confidence_acc += card.confidence * effective
            contributors[domain] = round(effective, 4)

        if total_weight == 0:
            return Conviction(
                horizon=horizon, score=0.0, label="INCONCLUSIVE", confidence=0.0,
                direction=Direction.INCONCLUSIVE,
                rationale=["INCONCLUSIVE - no domain had usable data for this horizon"],
            )

        score = max(-100.0, min(100.0, weighted_sum / total_weight))
        confidence = min(100.0, confidence_acc / total_weight)

        # Contradictions do not change the direction; they reduce how far we
        # are willing to commit to it.
        capped = False
        if contradiction_strength >= 65:
            factor = 0.5
            capped = True
            rationale.append(
                f"Conviction halved: contradictory signals (strength {contradiction_strength:.0f}/100)"
            )
            score *= factor
            confidence *= 0.7
        elif contradiction_strength >= 40:
            score *= 0.8
            confidence *= 0.85
            rationale.append(
                f"Conviction reduced 20%: some contradictory signals "
                f"({contradiction_strength:.0f}/100)"
            )

        top = sorted(contributors.items(), key=lambda kv: -kv[1])[:3]
        if top:
            rationale.append(
                "Main drivers: "
                + ", ".join(f"{d} (weight {w:.3f}, score {scores[d].score:+.0f})" for d, w in top)
            )

        direction = (
            Direction.BULLISH if score > 8
            else Direction.BEARISH if score < -8
            else Direction.NEUTRAL
        )
        return Conviction(
            horizon=horizon, score=round(score, 1), label=self.label_for(score),
            confidence=round(confidence, 1), direction=direction,
            contributors=contributors, capped_by_contradiction=capped, rationale=rationale,
        )

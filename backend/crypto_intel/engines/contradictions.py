"""ContradictionEngine.

The brief is emphatic: when signals conflict, say so. Do not hide the conflict
behind an average. A +40 and a -40 averaging to 0 looks like "neutral" but is
actually "the market is sending incompatible messages", which is a completely
different thing to act on.

Contradictions are surfaced explicitly AND they cap overall conviction.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ..config_loader import threshold
from ..core.models import Contradiction, ScoreCard


class ContradictionReport(BaseModel):
    contradictions: list[Contradiction] = Field(default_factory=list)
    max_strength: float = 0.0
    is_high: bool = False
    summary: str = ""


class ContradictionEngine:
    name = "contradiction_engine"

    def __init__(self) -> None:
        self.t = threshold("contradictions", default={}) or {}
        self.min_strength = float(self.t.get("min_strength_to_report", 40))
        self.high_threshold = float(self.t.get("high_contradiction_threshold", 65))

    def detect(
        self, scores: dict[str, ScoreCard], context: dict[str, Any] | None = None
    ) -> ContradictionReport:
        ctx = context or {}
        found: list[Contradiction] = []

        # --- 1. domains pointing in opposite directions with real confidence --
        available = {
            k: v for k, v in scores.items()
            if v.available and v.confidence >= 30 and abs(v.score) >= 20
        }
        for a, b in self._pairs(available):
            sa, sb = available[a], available[b]
            if sa.score * sb.score >= 0:
                continue
            gap = abs(sa.score - sb.score)
            # Both sides must be reasonably confident, or it is noise not conflict.
            strength = min(100.0, gap * 0.5 + min(sa.confidence, sb.confidence) * 0.4)
            if strength < self.min_strength:
                continue
            found.append(Contradiction(
                description=(
                    f"{a} is {self._word(sa.score)} ({sa.score:+.0f}, {sa.confidence:.0f}% conf) "
                    f"while {b} is {self._word(sb.score)} ({sb.score:+.0f}, {sb.confidence:.0f}% conf)"
                ),
                signals=[f"{a}={sa.score:+.0f}", f"{b}={sb.score:+.0f}"],
                strength=round(strength, 1),
                domains=[a, b],
                evidence_ids=(sa.evidence_ids[:5] + sb.evidence_ids[:5]),
            ))

        # --- 2. named structural contradictions ------------------------------
        found.extend(self._structural(ctx))

        found.sort(key=lambda c: c.strength, reverse=True)
        found = found[:8]
        max_strength = max((c.strength for c in found), default=0.0)
        is_high = max_strength >= self.high_threshold

        if not found:
            summary = "No significant contradictions: the available signals are broadly consistent."
        elif is_high:
            summary = (
                f"Signals are strongly contradictory ({len(found)} conflicts, "
                f"strongest {max_strength:.0f}/100). Overall conviction is capped as a result - "
                "this is a situation to size down, not to average out."
            )
        else:
            summary = (
                f"{len(found)} contradiction(s) detected (strongest {max_strength:.0f}/100). "
                "Worth noting but not disqualifying."
            )

        return ContradictionReport(
            contradictions=found, max_strength=max_strength, is_high=is_high, summary=summary
        )

    def _structural(self, ctx: dict[str, Any]) -> list[Contradiction]:
        """Specific combinations that matter regardless of scores."""
        out: list[Contradiction] = []

        price_24h = ctx.get("price_change_24h_pct")
        funding_state = ctx.get("funding_state")
        volume_state = ctx.get("volume_state")
        etf_divergence = ctx.get("etf_divergence")
        whale_behaviour = ctx.get("whale_behaviour")
        tvl_divergence = ctx.get("tvl_divergence")
        mtf_conflicts = ctx.get("mtf_conflicts") or []

        # Rally on thin volume with crowded leverage: the classic fragile top.
        if (price_24h or 0) > 1.0 and funding_state == "EXTREME_POSITIVE" and volume_state == "LOW":
            out.append(Contradiction(
                description=(
                    f"Price up {price_24h:+.1f}% but spot volume is LOW while funding is "
                    "extremely positive: the move is leverage-driven rather than backed by "
                    "genuine spot demand"
                ),
                signals=["price up", "volume low", "funding extreme"],
                strength=75.0, domains=["technical", "derivatives"],
            ))

        if etf_divergence == "DISTRIBUTION_INTO_STRENGTH":
            out.append(Contradiction(
                description=(
                    "Price is rising while ETF flows are negative: institutional demand is not "
                    "confirming the move"
                ),
                signals=["price up", "etf outflows"], strength=68.0,
                domains=["technical", "etf"],
            ))
        if etf_divergence == "ACCUMULATION_BEFORE_PRICE":
            out.append(Contradiction(
                description=(
                    "ETFs are accumulating while price falls: institutions are buying weakness, "
                    "which conflicts with the bearish price action"
                ),
                signals=["price down", "etf inflows"], strength=60.0,
                domains=["technical", "etf"],
            ))

        if whale_behaviour == "to_exchange" and (price_24h or 0) > 0.5:
            out.append(Contradiction(
                description=(
                    "Price is rising while large holders move coins onto exchanges - "
                    "potential distribution into strength"
                ),
                signals=["price up", "whales to exchange"], strength=62.0,
                domains=["technical", "whale"],
            ))

        if tvl_divergence == "TVL_DOWN_PRICE_UP":
            out.append(Contradiction(
                description=(
                    "Price is rising while chain TVL falls: on-chain capital is not confirming "
                    "the price move"
                ),
                signals=["price up", "tvl down"], strength=55.0,
                domains=["technical", "defi"],
            ))

        for conflict in mtf_conflicts:
            if "disagree" in conflict.lower():
                out.append(Contradiction(
                    description=conflict, signals=["multi-timeframe conflict"],
                    strength=52.0, domains=["technical"],
                ))

        return [c for c in out if c.strength >= self.min_strength]

    @staticmethod
    def _pairs(d: dict[str, ScoreCard]) -> list[tuple[str, str]]:
        keys = sorted(d)
        return [(keys[i], keys[j]) for i in range(len(keys)) for j in range(i + 1, len(keys))]

    @staticmethod
    def _word(score: float) -> str:
        return "positive" if score > 0 else "negative"

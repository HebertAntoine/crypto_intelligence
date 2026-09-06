"""RSIContextEngine - read RSI against measured history, not the textbook rule.

The textbook rule says RSI above 70 means overbought and RSI below 30 means
oversold. The measurements in this project contradict that on every asset:

  BTC  RSI >= 70 in a strong uptrend   -> +2.28pp vs same-regime days (FDR)
  SOL  RSI >= 70 in a strong uptrend   -> +8.25pp (FDR)
  ETH  RSI <= 30 in a strong downtrend -> -1.16pp   (buying it lost money)
  SOL  RSI <= 30 in a strong downtrend -> +7.18pp (FDR)

So the same reading means different things depending on the asset and the
regime. This engine looks up the measured behaviour for the current context
instead of applying a generic rule, and says plainly when it has no measurement
to lean on.

It never overrides the deterministic technical engine. It adds interpretation,
with the sample size attached.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar

from ..core.enums import Asset, Timeframe
from ..logging_setup import get_logger

log = get_logger("engines.rsi_context")


@dataclass(slots=True)
class RSIReading:
    """What an RSI value means in the current context, backed by evidence."""

    asset: Asset
    timeframe: Timeframe
    value: float
    zone: str                       # EXTREME_OVERSOLD … EXTREME_OVERBOUGHT
    regime: str
    textbook_reading: str
    measured_reading: str
    contradicts_textbook: bool = False
    evidence: dict[str, Any] = field(default_factory=dict)
    sample_size: int = 0
    confidence: str = "NONE"        # NONE | LOW | MODERATE | HIGH
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset": self.asset.value,
            "timeframe": self.timeframe.value,
            "value": round(self.value, 2),
            "zone": self.zone,
            "regime": self.regime,
            "textbook_reading": self.textbook_reading,
            "measured_reading": self.measured_reading,
            "contradicts_textbook": self.contradicts_textbook,
            "evidence": self.evidence,
            "sample_size": self.sample_size,
            "confidence": self.confidence,
            "note": self.note,
        }


def rsi_zone(value: float) -> str:
    if value >= 80:
        return "EXTREME_OVERBOUGHT"
    if value >= 70:
        return "OVERBOUGHT"
    if value <= 20:
        return "EXTREME_OVERSOLD"
    if value <= 30:
        return "OVERSOLD"
    if value >= 55:
        return "BULLISH"
    if value <= 45:
        return "BEARISH"
    return "NEUTRAL"


TEXTBOOK = {
    "EXTREME_OVERBOUGHT": "textbook: strongly overbought, a reversal is often expected",
    "OVERBOUGHT": "textbook: overbought, a pullback is often expected",
    "BULLISH": "textbook: positive momentum",
    "NEUTRAL": "textbook: no momentum signal",
    "BEARISH": "textbook: negative momentum",
    "OVERSOLD": "textbook: oversold, a bounce is often expected",
    "EXTREME_OVERSOLD": "textbook: strongly oversold, a bounce is often expected",
}


class RSIContextEngine:
    """Interprets RSI using stored research results rather than a fixed rule."""

    name = "rsi_context_engine"

    # Which stored study answers each zone. Only the two tails have measured
    # counterparts; the middle zones have no directional claim to make.
    _SIGNAL_FOR_ZONE: ClassVar[dict[str, str]] = {
        "EXTREME_OVERBOUGHT": "rsi_overbought",
        "OVERBOUGHT": "rsi_overbought",
        "OVERSOLD": "rsi_oversold",
        "EXTREME_OVERSOLD": "rsi_oversold",
    }

    def interpret(
        self,
        asset: Asset,
        rsi_value: float | None,
        regime: str,
        timeframe: Timeframe = Timeframe.D1,
        context: dict[str, Any] | None = None,
    ) -> RSIReading | None:
        """Read the current RSI against measured history for this asset+regime."""
        if rsi_value is None:
            return None

        zone = rsi_zone(rsi_value)
        reading = RSIReading(
            asset=asset, timeframe=timeframe, value=rsi_value, zone=zone,
            regime=regime,
            textbook_reading=TEXTBOOK.get(zone, "no textbook reading"),
            measured_reading="No measurement available for this configuration.",
        )

        signal_name = self._SIGNAL_FOR_ZONE.get(zone)
        if signal_name is None:
            reading.measured_reading = (
                "RSI is in its middle range; no directional reading is claimed."
            )
            reading.confidence = "NONE"
            return reading

        evidence = self._lookup(asset, signal_name, regime)
        if evidence is None:
            reading.note = (
                f"No stored study covers {signal_name} for {asset.value} in a "
                f"{regime} regime. Run `make research` to populate it."
            )
            reading.measured_reading = (
                "INCONCLUSIVE - the textbook reading is shown, but this system has no "
                "measurement of how this configuration actually behaved."
            )
            return reading

        edge = evidence.get("edge")
        n = evidence.get("n", 0)
        win_rate = evidence.get("win_rate")
        significant = evidence.get("significant", False)

        reading.evidence = evidence
        reading.sample_size = n
        reading.confidence = self._confidence(n, significant)

        expects_reversal = zone in ("OVERBOUGHT", "EXTREME_OVERBOUGHT")
        # A positive edge after an overbought reading means continuation, which
        # is the opposite of what the textbook expects.
        contradicts = (expects_reversal and edge is not None and edge > 0.3) or (
            not expects_reversal and edge is not None and edge < -0.3
        )
        reading.contradicts_textbook = bool(contradicts)

        if edge is None:
            reading.measured_reading = "INCONCLUSIVE - no measurable edge recorded."
            return reading

        direction = "outperformance" if edge > 0 else "underperformance"
        reading.measured_reading = (
            f"In {asset.value} {regime} regimes, RSI {zone.lower().replace('_', ' ')} has "
            f"historically preceded {direction} of {edge:+.2f}pp over 7 days versus other "
            f"days in the same regime (n={n}"
            + (f", win rate {win_rate:.0f}%" if win_rate is not None else "")
            + (", survives multiple-testing correction" if significant else ", not significant")
            + ")."
        )

        if contradicts:
            reading.note = (
                "This CONTRADICTS the generic textbook rule. On the measured history "
                f"for {asset.value}, this reading behaved more like "
                + ("momentum continuation than exhaustion."
                   if expects_reversal else "continued weakness than a bounce.")
            )
        return reading

    def _lookup(self, asset: Asset, signal_name: str, regime: str) -> dict[str, Any] | None:
        """Read the measured cell from stored research results."""

        from ..db.base import ResearchResultRow
        from ..db.session import session_scope

        rid = f"regime:{asset.value}:{signal_name}:{regime}:7d"[:80]
        with session_scope() as s:
            row = s.get(ResearchResultRow, rid)
            if row is None or not row.metrics:
                return None
            metrics = row.metrics
            return {
                "edge": metrics.get("edge_vs_regime"),
                "n": row.sample_size,
                "win_rate": (metrics.get("signal") or {}).get("win_rate"),
                "mean": (metrics.get("signal") or {}).get("mean"),
                "baseline_mean": (metrics.get("regime_baseline") or {}).get("mean"),
                "significant": metrics.get("significant_fdr", False),
                "computed_at": row.computed_at.isoformat() if row.computed_at else None,
            }

    @staticmethod
    def _confidence(n: int, significant: bool) -> str:
        if n < 30:
            return "NONE"
        if n < 80:
            return "LOW"
        if significant and n >= 150:
            return "HIGH"
        return "MODERATE"


def persist_regime_studies(asset: Asset, payload: dict[str, Any]) -> int:
    """Store regime-conditioned results so the engine can read them at runtime."""
    from datetime import UTC, datetime

    from ..db.base import ResearchResultRow
    from ..db.session import session_scope

    if not payload.get("available"):
        return 0

    written = 0
    now = datetime.now(UTC)
    with session_scope() as s:
        for signal_name, result in (payload.get("signals") or {}).items():
            if not result.get("available"):
                continue
            for regime, cell in (result.get("by_regime") or {}).items():
                if not cell.get("available"):
                    continue
                rid = f"regime:{asset.value}:{signal_name}:{regime}:{result['horizon']}"[:80]
                row = s.get(ResearchResultRow, rid)
                if row is None:
                    row = ResearchResultRow(
                        id=rid, study="regime_conditioned", asset=asset.value,
                        signal=f"{signal_name}:{regime}", horizon=result["horizon"],
                        split="full",
                    )
                    s.add(row)
                row.sample_size = cell.get("n", 0)
                row.metrics = cell
                row.computed_at = now
                written += 1
    return written

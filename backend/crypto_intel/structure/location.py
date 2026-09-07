"""Where price sits inside its structure.

"BTC is at 91,000" carries less information than "BTC is in the lower third of
a validated 4H range whose bottom has held four times". This engine produces
the second statement.

Location is DESCRIPTIVE. Whether being near a range bottom actually predicts
anything is the question the research layer answers, and the answer so far is
mostly no. Nothing here implies an action.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from ..core.enums import Asset, Timeframe
from ..engines.technical import indicators as ind
from ..history import store
from ..logging_setup import get_logger
from .ranges import DetectedRange, RangeIntelligenceEngine

log = get_logger("structure.location")


class LocationState(StrEnum):
    AT_RANGE_BOTTOM = "AT_RANGE_BOTTOM"
    NEAR_RANGE_BOTTOM = "NEAR_RANGE_BOTTOM"
    LOWER_THIRD = "LOWER_THIRD"
    MID_RANGE = "MID_RANGE"
    UPPER_THIRD = "UPPER_THIRD"
    NEAR_RANGE_TOP = "NEAR_RANGE_TOP"
    AT_RANGE_TOP = "AT_RANGE_TOP"
    ABOVE_RANGE = "ABOVE_RANGE"
    BELOW_RANGE = "BELOW_RANGE"
    NO_VALID_RANGE = "NO_VALID_RANGE"


@dataclass(slots=True)
class StructuralLocation:
    asset: str
    timeframe: str
    state: LocationState = LocationState.NO_VALID_RANGE
    price: float | None = None
    relative_position: float | None = None      # 0 = bottom, 1 = top
    distance_to_top_atr: float | None = None
    distance_to_bottom_atr: float | None = None
    range_summary: str = ""
    invalidation: str = ""
    detected_range: DetectedRange | None = None
    explanation: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset": self.asset, "timeframe": self.timeframe,
            "state": self.state.value, "price": self.price,
            "relative_position": self.relative_position,
            "distance_to_top_atr": self.distance_to_top_atr,
            "distance_to_bottom_atr": self.distance_to_bottom_atr,
            "range_summary": self.range_summary,
            "invalidation": self.invalidation,
            "explanation": self.explanation,
            "range": self.detected_range.to_dict() if self.detected_range else None,
        }


class StructuralLocationEngine:
    """Turn price plus a range into a named structural position."""

    def __init__(self, range_engine: RangeIntelligenceEngine | None = None) -> None:
        self.range_engine = range_engine or RangeIntelligenceEngine()

    def assess(
        self,
        asset: Asset,
        timeframe: Timeframe = Timeframe.D1,
        as_of: datetime | None = None,
    ) -> StructuralLocation:
        out = StructuralLocation(asset=asset.value, timeframe=timeframe.value)

        df = store.load_candles(asset, timeframe)
        if as_of is not None and not df.empty:
            df = df[df.index <= as_of]
        if df.empty:
            out.range_summary = "no price history"
            return out

        detected = self.range_engine.detect_from_frame(df)
        out.detected_range = detected
        out.price = float(df["close"].iloc[-1])
        out.range_summary = detected.describe()

        if not detected.valid or detected.top_zone is None or detected.bottom_zone is None:
            out.state = LocationState.NO_VALID_RANGE
            out.explanation.append(detected.reason or "no validated range")
            return out

        atr_series = ind.atr(df["high"], df["low"], df["close"], 14)
        atr = float(atr_series.iloc[-1]) if len(atr_series.dropna()) else 0.0

        top, bottom = detected.top_zone, detected.bottom_zone
        out.distance_to_top_atr = top.distance_atr(out.price, atr) if atr > 0 else None
        out.distance_to_bottom_atr = bottom.distance_atr(out.price, atr) if atr > 0 else None
        out.relative_position = detected.position(out.price)

        out.state = self._classify(out.price, top, bottom, out.relative_position)
        out.invalidation = self._invalidation(out.state, top, bottom, timeframe)
        out.explanation = self._explain(out, detected)
        return out

    def _classify(self, price, top, bottom, position) -> LocationState:
        if price > top.high:
            return LocationState.ABOVE_RANGE
        if price < bottom.low:
            return LocationState.BELOW_RANGE
        if bottom.contains(price):
            return LocationState.AT_RANGE_BOTTOM
        if top.contains(price):
            return LocationState.AT_RANGE_TOP
        if position is None:
            return LocationState.NO_VALID_RANGE

        # Thresholds describe thirds plus a "near" band just outside each zone.
        if position <= 0.15:
            return LocationState.NEAR_RANGE_BOTTOM
        if position <= 0.33:
            return LocationState.LOWER_THIRD
        if position < 0.67:
            return LocationState.MID_RANGE
        if position < 0.85:
            return LocationState.UPPER_THIRD
        return LocationState.NEAR_RANGE_TOP

    def _invalidation(self, state, top, bottom, timeframe) -> str:
        """What would objectively break this reading.

        Deliberately phrased as a structural event, never as a stop-loss: the
        system does not know the reader's position or risk tolerance. In
        French, because this sentence is displayed as written — it used to
        reach the page as "A 4h close above 84508.99 would break the range top
        zone".
        """
        label = timeframe.value
        if state in (
            LocationState.AT_RANGE_BOTTOM, LocationState.NEAR_RANGE_BOTTOM,
            LocationState.LOWER_THIRD,
        ):
            return (
                f"Une clôture {label} sous {bottom.low:.2f} casserait la zone basse "
                "du range et invaliderait cette lecture."
            )
        if state in (
            LocationState.AT_RANGE_TOP, LocationState.NEAR_RANGE_TOP,
            LocationState.UPPER_THIRD,
        ):
            return (
                f"Une clôture {label} au-dessus de {top.high:.2f} casserait la zone "
                "haute du range et invaliderait cette lecture."
            )
        if state is LocationState.ABOVE_RANGE:
            return (
                f"Une clôture {label} de retour sous {top.low:.2f} signifierait que "
                "la cassure a échoué et que le prix a réintégré le range."
            )
        if state is LocationState.BELOW_RANGE:
            return (
                f"Une clôture {label} de retour au-dessus de {bottom.high:.2f} "
                "signifierait que la cassure par le bas a échoué et que le prix a "
                "réintégré le range."
            )
        return (
            f"Une clôture {label} hors de {bottom.low:.2f}-{top.high:.2f} "
            "invaliderait cette lecture du range."
        )

    def _explain(self, out: StructuralLocation, detected: DetectedRange) -> list[str]:
        """The WHY list: what makes this location claim defensible."""
        lines: list[str] = []
        bottom, top = detected.bottom_zone, detected.top_zone

        relevant = bottom if out.state in (
            LocationState.AT_RANGE_BOTTOM, LocationState.NEAR_RANGE_BOTTOM,
            LocationState.LOWER_THIRD, LocationState.BELOW_RANGE,
        ) else top

        quality = relevant.quality
        side = "haute" if relevant.kind == "resistance" else "basse"
        lines.append(f"Zone {side} testée {quality.touches} fois")
        if quality.dispersion_atr is not None:
            lines.append(
                f"Les touches se regroupent à {quality.dispersion_atr:.2f} ATR près"
            )
        if quality.median_reaction_atr is not None:
            lines.append(
                f"Réaction médiane depuis la zone : {quality.median_reaction_atr:.2f} ATR"
            )
        lines.append(
            f"{quality.close_penetrations} clôture(s) au travers de la zone"
            if quality.close_penetrations else "Jamais clôturé au travers de la zone"
        )
        if quality.recency_bars is not None:
            lines.append(f"Dernier test il y a {quality.recency_bars} bougies")
        lines.append(f"Range actif depuis {detected.duration_bars} bougies")
        if detected.deviations:
            lines.append(
                f"{len(detected.deviations)} déviation(s) enregistrée(s), dont "
                f"{sum(1 for d in detected.deviations if d.followed_through)} "
                "revenue(s) dans le range"
            )
        return lines

    def multi_timeframe(
        self,
        asset: Asset,
        timeframes: list[Timeframe] | None = None,
        as_of: datetime | None = None,
    ) -> dict[str, Any]:
        """Structure across timeframes, with conflicts named explicitly."""
        timeframes = timeframes or [
            Timeframe.H1, Timeframe.H4, Timeframe.D1, Timeframe.W1
        ]
        readings: dict[str, Any] = {}
        for timeframe in timeframes:
            try:
                readings[timeframe.value] = self.assess(asset, timeframe, as_of).to_dict()
            except Exception as exc:
                log.warning(
                    "location_failed", asset=asset.value, tf=timeframe.value, error=str(exc)
                )
                readings[timeframe.value] = {"state": "NO_VALID_RANGE", "error": str(exc)[:120]}

        valid = {
            tf: r for tf, r in readings.items()
            if r.get("state") not in (None, "NO_VALID_RANGE")
        }
        conflict = None
        if len(valid) >= 2:
            positions = {
                tf: r.get("relative_position") for tf, r in valid.items()
                if r.get("relative_position") is not None
            }
            if len(positions) >= 2:
                spread = max(positions.values()) - min(positions.values())
                if spread > 0.5:
                    lowest = min(positions, key=positions.get)
                    highest = max(positions, key=positions.get)
                    conflict = (
                        f"Timeframes disagree: price sits near the bottom of its "
                        f"{lowest} range but near the top of its {highest} range. "
                        "Both are true - they describe different structures."
                    )

        return {
            "asset": asset.value,
            "timeframes": readings,
            "valid_ranges": len(valid),
            "conflict": conflict,
            "note": (
                "Structural location is descriptive. Whether it predicts anything is "
                "measured separately and is not assumed here."
            ),
        }

"""Market structure from confirmed swings: HH/HL/LH/LL, BOS and CHOCH.

BOS (break of structure) and CHOCH (change of character) are borrowed from a
trading vocabulary that treats them as signals. Here they are DESCRIPTIONS of
what the swing sequence did, nothing more. Whether either predicts anything is
a research question, and until it is answered they carry no weight.

The whole reading is built from swings filtered by `confirmation_time`, so a
structure computed for T never uses a pivot that was not yet knowable at T.
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
from .swings import CausalSwing, SwingSeries, find_causal_swings

log = get_logger("structure.market_structure")


class StructureState(StrEnum):
    BULLISH_STRUCTURE = "BULLISH_STRUCTURE"
    BEARISH_STRUCTURE = "BEARISH_STRUCTURE"
    RANGE_STRUCTURE = "RANGE_STRUCTURE"
    TRANSITION = "TRANSITION"
    UNCLEAR = "UNCLEAR"


@dataclass(slots=True)
class StructureEvent:
    """A BOS or CHOCH, recorded with when it became knowable."""

    kind: str                     # "BOS" | "CHOCH"
    direction: str                # "bullish" | "bearish"
    level: float
    broken_at: datetime
    confirmation_time: datetime
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind, "direction": self.direction, "level": self.level,
            "broken_at": self.broken_at.isoformat(),
            "confirmation_time": self.confirmation_time.isoformat(),
            "note": self.note,
        }


@dataclass(slots=True)
class MarketStructureReading:
    asset: str
    timeframe: str
    state: StructureState = StructureState.UNCLEAR
    labels: list[str] = field(default_factory=list)
    last_confirmed_hh: float | None = None
    last_confirmed_hl: float | None = None
    last_confirmed_lh: float | None = None
    last_confirmed_ll: float | None = None
    swings_used: int = 0
    events: list[StructureEvent] = field(default_factory=list)
    interpretation: str = ""
    caveat: str = (
        "BOS and CHOCH are descriptions of the swing sequence. Neither has been "
        "shown to carry predictive information and neither is treated as a signal."
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset": self.asset, "timeframe": self.timeframe,
            "state": self.state.value, "labels": self.labels,
            "last_confirmed_hh": self.last_confirmed_hh,
            "last_confirmed_hl": self.last_confirmed_hl,
            "last_confirmed_lh": self.last_confirmed_lh,
            "last_confirmed_ll": self.last_confirmed_ll,
            "swings_used": self.swings_used,
            "events": [e.to_dict() for e in self.events],
            "interpretation": self.interpretation,
            "caveat": self.caveat,
        }


class MarketStructureEngine:
    """Label the confirmed swing sequence and derive the structural state."""

    def __init__(self, lookback: int = 5, min_swings: int = 4) -> None:
        self.lookback = lookback
        self.min_swings = min_swings

    def assess(
        self,
        asset: Asset,
        timeframe: Timeframe = Timeframe.D1,
        as_of: datetime | None = None,
    ) -> MarketStructureReading:
        out = MarketStructureReading(asset=asset.value, timeframe=timeframe.value)

        df = store.load_candles(asset, timeframe)
        if as_of is not None and not df.empty:
            df = df[df.index <= as_of]
        if df.empty or len(df) < 60:
            out.interpretation = f"only {len(df)} bars, too few to establish structure"
            return out

        atr = ind.atr(df["high"], df["low"], df["close"], 14)
        swings = find_causal_swings(
            df["high"], df["low"], df["close"], atr, lookback=self.lookback
        )
        # Only what was confirmed by the last bar counts.
        swings = swings.as_of(df.index[-1])
        return self.assess_from_swings(swings, out, df)

    def assess_from_swings(
        self, swings: SwingSeries, out: MarketStructureReading, df: Any = None
    ) -> MarketStructureReading:
        highs, lows = swings.highs, swings.lows
        out.swings_used = len(highs) + len(lows)

        if len(highs) < 2 or len(lows) < 2:
            out.state = StructureState.UNCLEAR
            out.interpretation = (
                f"only {len(highs)} confirmed highs and {len(lows)} confirmed lows; "
                "at least two of each are needed to label a sequence"
            )
            return out

        labels: list[str] = []
        for previous, current in zip(highs[-3:], highs[-2:], strict=False):
            label = "HH" if current.price > previous.price else "LH"
            labels.append(label)
            if label == "HH":
                out.last_confirmed_hh = current.price
            else:
                out.last_confirmed_lh = current.price
        for previous, current in zip(lows[-3:], lows[-2:], strict=False):
            label = "HL" if current.price > previous.price else "LL"
            labels.append(label)
            if label == "HL":
                out.last_confirmed_hl = current.price
            else:
                out.last_confirmed_ll = current.price

        out.labels = labels
        bullish = labels.count("HH") + labels.count("HL")
        bearish = labels.count("LH") + labels.count("LL")

        if bullish >= 2 and bearish == 0:
            out.state = StructureState.BULLISH_STRUCTURE
        elif bearish >= 2 and bullish == 0:
            out.state = StructureState.BEARISH_STRUCTURE
        elif bullish and bearish:
            # A mixed sequence is either a range or a turn in progress. The
            # most recent label decides which reading is more honest.
            out.state = (
                StructureState.TRANSITION if labels[-1] in ("HH", "LL")
                else StructureState.RANGE_STRUCTURE
            )
        else:
            out.state = StructureState.RANGE_STRUCTURE

        out.events = self._events(highs, lows, labels)
        out.interpretation = self._interpret(out)
        return out

    def _events(
        self, highs: list[CausalSwing], lows: list[CausalSwing], labels: list[str]
    ) -> list[StructureEvent]:
        """BOS and CHOCH, derived only from confirmed swings."""
        events: list[StructureEvent] = []

        # BOS: a new high above the previous confirmed high continues the
        # bullish sequence; the mirror applies for lows.
        if len(highs) >= 2 and highs[-1].price > highs[-2].price:
            events.append(StructureEvent(
                kind="BOS", direction="bullish", level=highs[-2].price,
                broken_at=highs[-1].pivot_time,
                confirmation_time=highs[-1].confirmation_time,
                note="a confirmed swing high exceeded the previous confirmed high",
            ))
        if len(lows) >= 2 and lows[-1].price < lows[-2].price:
            events.append(StructureEvent(
                kind="BOS", direction="bearish", level=lows[-2].price,
                broken_at=lows[-1].pivot_time,
                confirmation_time=lows[-1].confirmation_time,
                note="a confirmed swing low broke below the previous confirmed low",
            ))

        # CHOCH: the sequence flipped character - a higher low after a run of
        # lower lows, or a lower high after higher highs.
        if len(labels) >= 3:
            if labels[-1] == "HL" and "LL" in labels[:-1]:
                events.append(StructureEvent(
                    kind="CHOCH", direction="bullish", level=lows[-1].price,
                    broken_at=lows[-1].pivot_time,
                    confirmation_time=lows[-1].confirmation_time,
                    note="a higher low appeared after a sequence of lower lows",
                ))
            if labels[-1] == "LH" and "HH" in labels[:-1]:
                events.append(StructureEvent(
                    kind="CHOCH", direction="bearish", level=highs[-1].price,
                    broken_at=highs[-1].pivot_time,
                    confirmation_time=highs[-1].confirmation_time,
                    note="a lower high appeared after a sequence of higher highs",
                ))
        return events

    def _interpret(self, out: MarketStructureReading) -> str:
        sequence = " ".join(out.labels) if out.labels else "no labelled swings"
        text = (
            f"{out.state.value} from the confirmed swing sequence [{sequence}] "
            f"across {out.swings_used} confirmed pivots."
        )
        if out.events:
            described = ", ".join(f"{e.kind} {e.direction}" for e in out.events)
            text += f" Structural events: {described}."
        return text

    def multi_timeframe(
        self,
        asset: Asset,
        timeframes: list[Timeframe] | None = None,
        as_of: datetime | None = None,
    ) -> dict[str, Any]:
        timeframes = timeframes or [
            Timeframe.H1, Timeframe.H4, Timeframe.D1, Timeframe.W1
        ]
        readings = {
            tf.value: self.assess(asset, tf, as_of).to_dict() for tf in timeframes
        }
        states = {
            tf: r["state"] for tf, r in readings.items() if r["state"] != "UNCLEAR"
        }
        bullish = [tf for tf, s in states.items() if s == "BULLISH_STRUCTURE"]
        bearish = [tf for tf, s in states.items() if s == "BEARISH_STRUCTURE"]

        conflict = None
        if bullish and bearish:
            conflict = (
                f"Structure conflicts across timeframes: {', '.join(bullish)} bullish "
                f"while {', '.join(bearish)} bearish. Higher timeframes describe the "
                "wider context; lower ones describe the current leg. Neither is wrong."
            )
        return {
            "asset": asset.value, "timeframes": readings,
            "bullish_timeframes": bullish, "bearish_timeframes": bearish,
            "conflict": conflict,
        }

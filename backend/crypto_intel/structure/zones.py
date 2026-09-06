"""Price ZONES, not price levels.

A support is never one number. Traders draw a band, and price respects a band:
the 2021 BTC "60k support" was reacted to anywhere between 58.5k and 61k. A
detector that stores 60,127.43 and asks whether price touched it will answer
"no" almost always, and a detector using a fixed percentage tolerance will be
too wide for BTC and too narrow for SOL.

So zones are built by clustering swings with an ATR-scaled tolerance, and
carry a quality score built from what actually makes a level meaningful: how
many times it was tested, how tightly the touches agree, how strongly price
reacted, and whether it has been broken.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from .swings import CausalSwing

# A zone spans this many ATR by default. Chosen because it is roughly the
# width of a typical wick, so a level tested by wicks stays one level.
DEFAULT_ZONE_ATR = 0.5
MIN_TOUCHES = 2


@dataclass(slots=True)
class ZoneQuality:
    """Why we believe this zone is real, component by component."""

    touches: int = 0
    dispersion_atr: float | None = None
    median_reaction_atr: float | None = None
    close_penetrations: int = 0
    wick_penetrations: int = 0
    age_bars: int = 0
    recency_bars: int | None = None
    score: float = 0.0
    components: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "touches": self.touches, "dispersion_atr": self.dispersion_atr,
            "median_reaction_atr": self.median_reaction_atr,
            "close_penetrations": self.close_penetrations,
            "wick_penetrations": self.wick_penetrations,
            "age_bars": self.age_bars, "recency_bars": self.recency_bars,
            "score": self.score, "components": self.components,
        }


@dataclass(slots=True)
class Zone:
    """A support or resistance band."""

    low: float
    high: float
    kind: str                      # "support" | "resistance"
    quality: ZoneQuality = field(default_factory=ZoneQuality)
    first_touch: datetime | None = None
    last_touch: datetime | None = None
    swing_prices: list[float] = field(default_factory=list)

    @property
    def midpoint(self) -> float:
        return (self.low + self.high) / 2.0

    @property
    def width(self) -> float:
        return self.high - self.low

    def contains(self, price: float) -> bool:
        return self.low <= price <= self.high

    def distance_atr(self, price: float, atr: float) -> float | None:
        """Distance to the nearest edge, in ATR. Zero when inside."""
        if atr <= 0:
            return None
        if self.contains(price):
            return 0.0
        gap = self.low - price if price < self.low else price - self.high
        return round(gap / atr, 3)

    def to_dict(self) -> dict[str, Any]:
        return {
            "low": round(self.low, 8), "high": round(self.high, 8),
            "midpoint": round(self.midpoint, 8), "kind": self.kind,
            "quality": self.quality.to_dict(),
            "first_touch": self.first_touch.isoformat() if self.first_touch else None,
            "last_touch": self.last_touch.isoformat() if self.last_touch else None,
            "touch_count": len(self.swing_prices),
        }

    def describe(self) -> str:
        """The WHY string - what makes this zone credible."""
        q = self.quality
        parts = [
            f"{self.kind} zone {self.low:.2f}-{self.high:.2f}",
            f"tested {q.touches} times",
        ]
        if q.dispersion_atr is not None:
            parts.append(f"touches agree within {q.dispersion_atr:.2f} ATR")
        if q.median_reaction_atr is not None:
            parts.append(f"median reaction {q.median_reaction_atr:.2f} ATR")
        if q.close_penetrations == 0:
            parts.append("never closed through")
        else:
            parts.append(f"{q.close_penetrations} closes through")
        if q.age_bars:
            parts.append(f"active for {q.age_bars} bars")
        return ", ".join(parts) + f" (quality {q.score:.0f}/100)"


def build_zones(
    swings: list[CausalSwing],
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    atr: pd.Series,
    kind: str,
    *,
    zone_atr: float = DEFAULT_ZONE_ATR,
    min_touches: int = MIN_TOUCHES,
    max_zones: int = 8,
) -> list[Zone]:
    """Cluster swings into ATR-scaled zones and score each one.

    ATR scaling is what makes this comparable across assets: a 0.5-ATR band is
    the same *structural* tolerance on BTC and SOL, whereas 0.6% is not.
    """
    if not swings or atr.empty:
        return []

    current_atr = float(atr.iloc[-1])
    if not np.isfinite(current_atr) or current_atr <= 0:
        return []
    tolerance = current_atr * zone_atr

    ordered = sorted(swings, key=lambda s: s.price)
    clusters: list[list[CausalSwing]] = []
    for swing in ordered:
        if clusters and abs(swing.price - np.mean([s.price for s in clusters[-1]])) <= tolerance:
            clusters[-1].append(swing)
        else:
            clusters.append([swing])

    zones: list[Zone] = []
    for cluster in clusters:
        if len(cluster) < min_touches:
            continue
        prices = [s.price for s in cluster]
        centre = float(np.mean(prices))
        # The zone spans the touches themselves, widened to at least the
        # tolerance so a single tight cluster still has usable width.
        low_edge = min(min(prices), centre - tolerance / 2)
        high_edge = max(max(prices), centre + tolerance / 2)

        zone = Zone(
            low=low_edge, high=high_edge, kind=kind,
            swing_prices=prices,
            first_touch=min(s.pivot_time for s in cluster),
            last_touch=max(s.pivot_time for s in cluster),
        )
        zone.quality = _score_zone(zone, cluster, high, low, close, current_atr)
        zones.append(zone)

    zones.sort(key=lambda z: -z.quality.score)
    return zones[:max_zones]


def _score_zone(
    zone: Zone, cluster: list[CausalSwing],
    high: pd.Series, low: pd.Series, close: pd.Series, atr: float,
) -> ZoneQuality:
    quality = ZoneQuality(touches=len(cluster))
    components: dict[str, float] = {}
    parts: list[float] = []

    # 1. Number of tests. Two is the minimum that means anything; beyond about
    # five, extra touches add little and often mean the level is failing.
    touch_score = float(np.clip((quality.touches - 1) / 4 * 100, 0, 100))
    parts.append(touch_score)
    components["touches"] = round(touch_score, 1)

    # 2. Agreement between touches. Tight clustering is what distinguishes a
    # real level from a coincidence of nearby extremes.
    prices = [s.price for s in cluster]
    if len(prices) > 1 and atr > 0:
        quality.dispersion_atr = round(float(np.std(prices, ddof=1) / atr), 3)
        dispersion_score = float(np.clip((0.6 - quality.dispersion_atr) / 0.6 * 100, 0, 100))
        parts.append(dispersion_score)
        components["touch_agreement"] = round(dispersion_score, 1)

    # 3. Reaction depth: did price actually move away from here?
    reactions = [s.reaction_atr for s in cluster if s.reaction_atr is not None]
    if reactions:
        quality.median_reaction_atr = round(float(np.median(reactions)), 3)
        reaction_score = float(np.clip(quality.median_reaction_atr / 2.5 * 100, 0, 100))
        parts.append(reaction_score)
        components["reaction_depth"] = round(reaction_score, 1)

    # 4. Integrity: closes through a zone damage it far more than wicks do.
    first_index = close.index.get_indexer([zone.first_touch], method="nearest")[0]
    window_close = close.iloc[first_index:]
    window_high = high.iloc[first_index:]
    window_low = low.iloc[first_index:]

    if zone.kind == "support":
        quality.close_penetrations = int((window_close < zone.low).sum())
        quality.wick_penetrations = int((window_low < zone.low).sum())
    else:
        quality.close_penetrations = int((window_close > zone.high).sum())
        quality.wick_penetrations = int((window_high > zone.high).sum())

    integrity_score = float(np.clip(100 - quality.close_penetrations * 12, 0, 100))
    parts.append(integrity_score)
    components["integrity"] = round(integrity_score, 1)

    # 5. Age and recency. A level that has held for a long time and was tested
    # recently is more actionable than one last touched two years ago.
    quality.age_bars = len(window_close)
    if zone.last_touch is not None:
        last_index = close.index.get_indexer([zone.last_touch], method="nearest")[0]
        quality.recency_bars = int(len(close) - 1 - last_index)
        recency_score = float(np.clip(100 - quality.recency_bars / 2.0, 0, 100))
        parts.append(recency_score)
        components["recency"] = round(recency_score, 1)

    quality.components = components
    quality.score = round(float(np.mean(parts)), 1) if parts else 0.0
    return quality

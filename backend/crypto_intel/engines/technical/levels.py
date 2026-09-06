"""Support and resistance from swing clustering.

Levels are not drawn from round numbers or arbitrary Fibonacci ratios: they
come from prices the market actually reacted at. Nearby swings are clustered,
and a level's strength grows with the number of touches and their recency.
"""

from __future__ import annotations

import pandas as pd

from ...core.models import Level
from .structure import SwingPoint


def cluster_levels(
    swings: list[SwingPoint],
    current_price: float,
    kind: str,
    *,
    tolerance_pct: float = 0.6,
    min_touches: int = 2,
    max_levels: int = 6,
) -> list[Level]:
    """Group swing points that sit within `tolerance_pct` of each other."""
    if not swings or current_price <= 0:
        return []

    clusters: list[list[SwingPoint]] = []
    for sp in sorted(swings, key=lambda s: s.price):
        placed = False
        for cluster in clusters:
            centre = sum(p.price for p in cluster) / len(cluster)
            if abs(sp.price - centre) / centre * 100.0 <= tolerance_pct:
                cluster.append(sp)
                placed = True
                break
        if not placed:
            clusters.append([sp])

    max_index = max((sp.index for sp in swings), default=1) or 1
    levels: list[Level] = []
    for cluster in clusters:
        touches = len(cluster)
        if touches < min_touches:
            continue
        price = sum(p.price for p in cluster) / touches
        # Recent reactions matter more than year-old ones.
        recency = max(sp.index for sp in cluster) / max_index
        strength = min(100.0, touches * 22.0 + recency * 30.0)
        last_ts = max((sp.timestamp for sp in cluster if sp.timestamp is not None), default=None)
        levels.append(
            Level(
                price=round(price, 8),
                kind=kind,
                touches=touches,
                strength=round(strength, 1),
                last_touch=last_ts.to_pydatetime() if isinstance(last_ts, pd.Timestamp) else None,
                distance_pct=round((price - current_price) / current_price * 100.0, 2),
            )
        )

    # Keep the levels closest to price - those are the ones that matter now.
    levels.sort(key=lambda lv: abs(lv.distance_pct or 0))
    return levels[:max_levels]


def build_levels(
    swing_highs: list[SwingPoint],
    swing_lows: list[SwingPoint],
    current_price: float,
    *,
    tolerance_pct: float = 0.6,
    min_touches: int = 2,
    max_levels: int = 6,
) -> tuple[list[Level], list[Level]]:
    """Supports below price, resistances above.

    A former resistance that price has broken above becomes a support, so
    classification uses the level's position relative to price now - not the
    swing type that produced it.
    """
    highs = cluster_levels(swing_highs, current_price, "resistance",
                           tolerance_pct=tolerance_pct, min_touches=min_touches,
                           max_levels=max_levels * 2)
    lows = cluster_levels(swing_lows, current_price, "support",
                          tolerance_pct=tolerance_pct, min_touches=min_touches,
                          max_levels=max_levels * 2)

    supports: list[Level] = []
    resistances: list[Level] = []
    for lv in highs + lows:
        if lv.price < current_price:
            supports.append(lv.model_copy(update={"kind": "support"}))
        else:
            resistances.append(lv.model_copy(update={"kind": "resistance"}))

    supports.sort(key=lambda lv: -lv.price)
    resistances.sort(key=lambda lv: lv.price)
    return supports[:max_levels], resistances[:max_levels]

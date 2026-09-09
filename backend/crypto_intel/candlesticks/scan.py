"""Balayage historique des figures de chandeliers.

Même discipline que pour les structures chartistes, et pour les mêmes raisons:
chaque figure est datée du moment où elle est devenue reconnaissable, et rien
au-delà de cette barre n'entre dans sa détection.

Une différence de taille avec `structure/history_scan.py`: là-bas, une figure
se définit par des pivots et le balayage ne s'arrête qu'aux pivots confirmés.
Ici une figure tient en une à trois bougies, donc **chaque barre est un point
de détection**. Le balayage est linéaire et ne pose aucun problème d'identité:
deux figures à deux instants différents sont deux figures.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from ..logging_setup import get_logger
from .patterns import DEFAULT_MIN_CONFIDENCE, CandlestickDetection, detect_at
from .taxonomy import DETECTOR_VERSION

log = get_logger("candlesticks.scan")

#: Assez de barres pour que l'ATR et la tendance préalable existent.
MIN_BARS = 25


def scan_candlesticks(
    frame: pd.DataFrame,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    symbol: str = "",
    timeframe: str = "",
) -> list[CandlestickDetection]:
    """Toutes les figures de chandeliers de la série, les plus anciennes d'abord."""
    if frame is None or frame.empty or len(frame) < MIN_BARS:
        return []

    from ..engines.technical import indicators as ind

    atr = ind.atr(frame["high"], frame["low"], frame["close"], 14)
    found: list[CandlestickDetection] = []
    for index in range(MIN_BARS, len(frame)):
        value = float(atr.iloc[index])
        if value != value or value <= 0:
            continue
        found.extend(detect_at(frame, index, value, min_confidence,
                               symbol=symbol, timeframe=timeframe))

    log.info("candlesticks_scanned", bars=len(frame), figures=len(found),
             version=DETECTOR_VERSION)
    return found


def summarise(detections: list[CandlestickDetection]) -> dict[str, Any]:
    """Combien de chaque, pour un rapport. Sans agrégation avec les structures."""
    from collections import Counter

    counts = Counter(d.pattern.value for d in detections)
    families = Counter(d.family for d in detections)
    return {
        "taxonomy": "CANDLESTICK_PATTERN",
        "total": len(detections),
        "by_pattern": dict(counts.most_common()),
        "by_family": dict(families.most_common()),
        "detector_version": DETECTOR_VERSION,
        "note": (
            "Counts of candlestick figures only. They are never added to the "
            "chart-structure counts: one spans a bar, the other hundreds."
        ),
    }

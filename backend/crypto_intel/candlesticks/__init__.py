"""Figures de chandeliers — une famille distincte des structures chartistes.

Ce paquet ne partage aucun type avec `structure/`. C'est délibéré: un
`HAMMER` et un `DOUBLE_TOP` ne sont pas deux valeurs d'une même énumération,
et rien ne doit permettre de les compter ensemble.
"""

from .patterns import CandlestickDetection, detect_at
from .scan import scan_candlesticks, summarise
from .taxonomy import (
    DETECTOR_VERSION,
    CandlestickFamily,
    CandlestickPattern,
)

__all__ = [
    "DETECTOR_VERSION",
    "CandlestickDetection",
    "CandlestickFamily",
    "CandlestickPattern",
    "detect_at",
    "scan_candlesticks",
    "summarise",
]

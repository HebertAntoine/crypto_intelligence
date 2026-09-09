"""Figures de chandeliers — une famille distincte des structures chartistes.

Ce paquet ne partage aucun type avec `structure/`. C'est délibéré: un
`HAMMER` et un `DOUBLE_TOP` ne sont pas deux valeurs d'une même énumération,
et rien ne doit permettre de les compter ensemble.

**Usage: `DESCRIPTIVE_ONLY`.** La mesure d'avantage n'a rien trouvé — voir
`USAGE_EVIDENCE`. Ces figures se décrivent et se stockent; elles ne décident
de rien.
"""

from .patterns import CandlestickDetection, detect_at
from .scan import scan_candlesticks, summarise
from .taxonomy import (
    DETECTOR_VERSION,
    USAGE,
    USAGE_EVIDENCE,
    CandlestickFamily,
    CandlestickPattern,
)

__all__ = [
    "DETECTOR_VERSION",
    "USAGE",
    "USAGE_EVIDENCE",
    "CandlestickDetection",
    "CandlestickFamily",
    "CandlestickPattern",
    "detect_at",
    "scan_candlesticks",
    "summarise",
]

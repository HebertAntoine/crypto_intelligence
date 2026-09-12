"""Independent kernel-template baseline for structural chart patterns.

The baseline is intentionally separate from the production pivot detector.
Agreement is useful only when the two methods do not share the same machinery.
"""

from .detector import LMWConfig, detect_latest, extract_extrema, scan_lmw
from .models import (
    LMWDetection,
    LMWMode,
    LMWResult,
    LMWScoreComponents,
    LMWStatus,
    PatternOrientation,
)
from .templates import TEMPLATE_BY_PATTERN, TEMPLATES, TemplateSpec

__all__ = [
    "TEMPLATES",
    "TEMPLATE_BY_PATTERN",
    "LMWConfig",
    "LMWDetection",
    "LMWMode",
    "LMWResult",
    "LMWScoreComponents",
    "LMWStatus",
    "PatternOrientation",
    "TemplateSpec",
    "detect_latest",
    "extract_extrema",
    "scan_lmw",
]

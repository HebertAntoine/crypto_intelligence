"""Chart pattern detectors, registered on import."""

from .base import PatternContext, PatternDetector, all_detectors, register, registered_names
from .detectors import register_all

register_all()

__all__ = [
    "PatternContext",
    "PatternDetector",
    "all_detectors",
    "register",
    "register_all",
    "registered_names",
]

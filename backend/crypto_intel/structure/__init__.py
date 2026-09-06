"""Structural analysis: swings, zones, ranges, location, market structure.

Everything in this package obeys one rule: a structure computed for time T
uses only bars at or before T, and stays identical when later bars change.
That is asserted directly by the mutation tests rather than assumed.
"""

from .location import LocationState, StructuralLocation, StructuralLocationEngine
from .market_structure import (
    MarketStructureEngine,
    MarketStructureReading,
    StructureState,
)
from .ranges import DetectedRange, RangeIntelligenceEngine, RangeType
from .swings import CausalSwing, SwingSeries, find_causal_swings
from .zones import Zone, ZoneQuality, build_zones

__all__ = [
    "CausalSwing",
    "DetectedRange",
    "LocationState",
    "MarketStructureEngine",
    "MarketStructureReading",
    "RangeIntelligenceEngine",
    "RangeType",
    "StructuralLocation",
    "StructuralLocationEngine",
    "StructureState",
    "SwingSeries",
    "Zone",
    "ZoneQuality",
    "build_zones",
    "find_causal_swings",
]

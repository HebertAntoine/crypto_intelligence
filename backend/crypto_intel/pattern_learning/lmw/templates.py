"""Declared v1 templates for the LMW-inspired matcher.

These coordinates are hypotheses written before the historical comparison.
They describe extrema after affine price normalisation to ``[0, 1]``.  No
forward return or production-detector output enters the definitions.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..ontology import StructuralPatternName
from .models import PatternOrientation


@dataclass(slots=True, frozen=True)
class TemplateSpec:
    pattern: StructuralPatternName
    kinds: tuple[str, ...]
    values: tuple[float, ...]
    roles: tuple[str, ...]
    orientation: PatternOrientation


TEMPLATES: tuple[TemplateSpec, ...] = (
    TemplateSpec(
        StructuralPatternName.DOUBLE_TOP,
        ("max", "min", "max"),
        (1.0, 0.0, 1.0),
        ("first_top", "neckline_low", "second_top"),
        PatternOrientation.BEARISH,
    ),
    TemplateSpec(
        StructuralPatternName.DOUBLE_BOTTOM,
        ("min", "max", "min"),
        (0.0, 1.0, 0.0),
        ("first_bottom", "neckline_high", "second_bottom"),
        PatternOrientation.BULLISH,
    ),
    TemplateSpec(
        StructuralPatternName.TRIPLE_TOP,
        ("max", "min", "max", "min", "max"),
        (1.0, 0.0, 1.0, 0.0, 1.0),
        ("first_top", "first_reaction", "second_top", "second_reaction", "third_top"),
        PatternOrientation.BEARISH,
    ),
    TemplateSpec(
        StructuralPatternName.TRIPLE_BOTTOM,
        ("min", "max", "min", "max", "min"),
        (0.0, 1.0, 0.0, 1.0, 0.0),
        (
            "first_bottom",
            "first_reaction",
            "second_bottom",
            "second_reaction",
            "third_bottom",
        ),
        PatternOrientation.BULLISH,
    ),
    TemplateSpec(
        StructuralPatternName.HEAD_SHOULDERS,
        ("max", "min", "max", "min", "max"),
        (0.72, 0.12, 1.0, 0.12, 0.72),
        ("left_shoulder", "left_armpit", "head", "right_armpit", "right_shoulder"),
        PatternOrientation.BEARISH,
    ),
    TemplateSpec(
        StructuralPatternName.INVERSE_HEAD_SHOULDERS,
        ("min", "max", "min", "max", "min"),
        (0.28, 0.88, 0.0, 0.88, 0.28),
        ("left_shoulder", "left_armpit", "head", "right_armpit", "right_shoulder"),
        PatternOrientation.BULLISH,
    ),
    TemplateSpec(
        StructuralPatternName.ASCENDING_TRIANGLE,
        ("min", "max", "min", "max", "min", "max"),
        (0.0, 1.0, 0.25, 1.0, 0.5, 1.0),
        ("lower_1", "upper_1", "lower_2", "upper_2", "lower_3", "upper_3"),
        PatternOrientation.BULLISH,
    ),
    TemplateSpec(
        StructuralPatternName.DESCENDING_TRIANGLE,
        ("max", "min", "max", "min", "max", "min"),
        (1.0, 0.0, 0.75, 0.0, 0.5, 0.0),
        ("upper_1", "lower_1", "upper_2", "lower_2", "upper_3", "lower_3"),
        PatternOrientation.BEARISH,
    ),
    TemplateSpec(
        StructuralPatternName.SYMMETRICAL_TRIANGLE,
        ("min", "max", "min", "max", "min", "max"),
        (0.0, 1.0, 0.20, 0.80, 0.40, 0.60),
        ("lower_1", "upper_1", "lower_2", "upper_2", "lower_3", "upper_3"),
        PatternOrientation.NEUTRAL,
    ),
    TemplateSpec(
        StructuralPatternName.RECTANGLE_RANGE,
        ("min", "max", "min", "max", "min", "max"),
        (0.0, 1.0, 0.0, 1.0, 0.0, 1.0),
        ("lower_1", "upper_1", "lower_2", "upper_2", "lower_3", "upper_3"),
        PatternOrientation.NEUTRAL,
    ),
    # A wedge needs both boundaries to move in the same direction while their
    # distance contracts.  The coordinates encode that geometry directly;
    # they do not encode, and were not selected from, a subsequent return.
    TemplateSpec(
        StructuralPatternName.RISING_WEDGE,
        ("min", "max", "min", "max", "min", "max"),
        (0.0, 0.72, 0.25, 0.85, 0.48, 1.0),
        ("lower_1", "upper_1", "lower_2", "upper_2", "lower_3", "upper_3"),
        PatternOrientation.BEARISH,
    ),
    TemplateSpec(
        StructuralPatternName.FALLING_WEDGE,
        ("max", "min", "max", "min", "max", "min"),
        (1.0, 0.28, 0.75, 0.15, 0.52, 0.0),
        ("upper_1", "lower_1", "upper_2", "lower_2", "upper_3", "lower_3"),
        PatternOrientation.BULLISH,
    ),
    # Flags include the pole in the template.  That makes the comparator
    # genuinely stricter than merely calling any short counter-trend channel a
    # flag, and keeps it independent from the production detector's ATR rules.
    TemplateSpec(
        StructuralPatternName.BULL_FLAG,
        ("min", "max", "min", "max", "min", "max"),
        (0.0, 1.0, 0.62, 0.82, 0.52, 0.72),
        ("pole_start", "pole_end", "lower_1", "upper_1", "lower_2", "upper_2"),
        PatternOrientation.BULLISH,
    ),
    TemplateSpec(
        StructuralPatternName.BEAR_FLAG,
        ("max", "min", "max", "min", "max", "min"),
        (1.0, 0.0, 0.38, 0.18, 0.48, 0.28),
        ("pole_start", "pole_end", "upper_1", "lower_1", "upper_2", "lower_2"),
        PatternOrientation.BEARISH,
    ),
)


TEMPLATE_BY_PATTERN = {template.pattern: template for template in TEMPLATES}

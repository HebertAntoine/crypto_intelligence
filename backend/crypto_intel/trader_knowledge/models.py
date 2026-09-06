"""Schema for human analysis and educational material.

Three things are kept rigorously apart, because collapsing them is how a
system starts believing traders instead of learning from them:

  WHAT_TRADER_SAID          the claim, as made, at the time it was made
  WHAT_MARKET_DATA_SHOWED   what was measurable at that same instant
  WHAT_HAPPENED_AFTER       the outcome, known only later

A trader saying "BTC is at the range bottom" is a claim. Whether a validated
range existed at that timestamp is a measurement. Whether price rose afterwards
is an outcome. Each is stored in its own structure and they are never merged.

Educational material is stored as CLAIMS about how to read charts, never as
facts about markets. "A falling wedge is generally bullish" is a hypothesis to
be tested, not a rule to be applied.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from ..core.sources import SourceTier, tier_for


class ExtractionMethod(StrEnum):
    USER_PROVIDED_TRANSCRIPT = "USER_PROVIDED_TRANSCRIPT"
    USER_MANUAL_NOTES = "USER_MANUAL_NOTES"
    OFFICIAL_CAPTIONS = "OFFICIAL_CAPTIONS"
    EXPORTED_TEXT = "EXPORTED_TEXT"
    USER_ANNOTATION = "USER_ANNOTATION"


class DataQuality(StrEnum):
    HIGH = "HIGH"               # asset, timeframe, date and levels all explicit
    MEDIUM = "MEDIUM"           # some fields inferred but unambiguous
    LOW = "LOW"                 # significant ambiguity
    UNUSABLE = "UNUSABLE"       # cannot be aligned to market data


class ClaimType(StrEnum):
    EDUCATIONAL_CLAIM = "EDUCATIONAL_CLAIM"          # "falling wedge is bullish"
    EDUCATIONAL_DEFINITION = "EDUCATIONAL_DEFINITION"  # what a wedge IS
    EDUCATIONAL_EXAMPLE = "EDUCATIONAL_EXAMPLE"      # an illustration


class TraderAnalysisExample(BaseModel):
    """One human analysis, with its provenance and ambiguities recorded."""

    id: str
    source: str                              # "lexa_moon", "personal_course", ...
    author: str = ""
    source_url: str | None = None
    published_at: datetime | None = None
    analysis_time: datetime | None = None    # when the analyst was speaking
    market_timestamp: datetime | None = None # the bar this aligns to
    asset: str | None = None
    timeframe: str | None = None

    transcript_reference: str = Field(
        default="",
        description="Short excerpt or pointer. Never a full reproduction of the source.",
    )
    concepts: list[str] = Field(default_factory=list)
    structure_type: str | None = None
    range_top: float | None = None
    range_bottom: float | None = None
    mid_range: float | None = None
    supports: list[float] = Field(default_factory=list)
    resistances: list[float] = Field(default_factory=list)
    invalidation: float | None = None
    target_if_mentioned: float | None = None
    directional_bias_if_mentioned: str | None = None
    reasoning: str = ""
    confidence_if_mentioned: float | None = None
    chart_reference: str | None = None

    data_quality: DataQuality = DataQuality.LOW
    extraction_method: ExtractionMethod = ExtractionMethod.USER_PROVIDED_TRANSCRIPT
    human_verified: bool = False
    market_episode_id: str | None = None
    annotation_version: int = 1
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def source_tier(self) -> SourceTier:
        return tier_for(self.source)

    @property
    def is_measurement(self) -> bool:
        """Always False. A human analysis is a claim, never a measurement."""
        return False

    @property
    def alignable(self) -> bool:
        """Can this be tied to a specific bar, without guessing?"""
        return (
            self.asset is not None
            and self.timeframe is not None
            and (self.analysis_time is not None or self.published_at is not None)
            and self.data_quality is not DataQuality.UNUSABLE
        )

    def what_trader_said(self) -> dict[str, Any]:
        """The claim, isolated from any market data."""
        return {
            "structure_type": self.structure_type,
            "range_top": self.range_top, "range_bottom": self.range_bottom,
            "supports": self.supports, "resistances": self.resistances,
            "invalidation": self.invalidation,
            "target": self.target_if_mentioned,
            "directional_bias": self.directional_bias_if_mentioned,
            "reasoning": self.reasoning,
            "confidence": self.confidence_if_mentioned,
            "concepts": self.concepts,
            "note": (
                "This is what a human asserted. It is not evidence about the market "
                "and cannot override any measured value."
            ),
        }


class AnnotationCorrection(BaseModel):
    """A user correction, versioned and never overwriting the original."""

    example_id: str
    field_name: str
    previous_value: Any = None
    new_value: Any = None
    correction_reason: str = ""
    corrected_by: str = "user"
    corrected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    annotation_version: int = 2


class EducationalClaim(BaseModel):
    """A testable assertion drawn from educational material."""

    id: str
    claim_type: ClaimType = ClaimType.EDUCATIONAL_CLAIM
    concept: str                              # "falling_wedge"
    statement: str                            # "generally resolves upward"
    implied_direction: str | None = None       # BULLISH / BEARISH / NEUTRAL
    implied_timeframe: str | None = None
    conditions: list[str] = Field(default_factory=list)
    source: str = "goodcrypto"
    source_url: str | None = None
    source_title: str | None = None
    language: str = "en"
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    paraphrase: str = Field(
        default="",
        description="Our own summary. Short quotations only where unavoidable.",
    )
    testable: bool = True
    test_note: str = ""

    @property
    def source_tier(self) -> SourceTier:
        return tier_for(self.source)

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.model_dump(mode="json"),
            "source_tier": int(self.source_tier),
            "tier_label": self.source_tier.label,
            "status_note": (
                "This is an EDUCATIONAL CLAIM about how to read charts. It is not a "
                "market fact and carries no authority over measured data."
            ),
        }


class MarketContextAtT(BaseModel):
    """What was measurable at the analysis timestamp - and nothing after it."""

    market_timestamp: datetime
    asset: str
    timeframe: str
    price_at_analysis: float | None = None
    ohlcv_at_t: dict[str, float] = Field(default_factory=dict)
    regime_at_t: str | None = None
    structure_at_t: str | None = None
    location_at_t: str | None = None
    range_top_at_t: float | None = None
    range_bottom_at_t: float | None = None
    funding_at_t: float | None = None
    funding_percentile_at_t: float | None = None
    oi_at_t: float | None = None
    volatility_at_t: str | None = None
    atr_at_t: float | None = None
    macro_known_at_t: dict[str, Any] = Field(default_factory=dict)
    etf_known_at_t: dict[str, Any] = Field(default_factory=dict)
    supports_at_t: list[dict[str, float]] = Field(default_factory=list)
    resistances_at_t: list[dict[str, float]] = Field(default_factory=list)
    bars_available: int = 0
    causality_note: str = (
        "Every value here was computed from bars at or before market_timestamp. "
        "No later bar contributed to any of it."
    )


class HumanOutcome(BaseModel):
    """What actually happened after - known only later, stored separately."""

    example_id: str
    market_timestamp: datetime
    returns: dict[str, float | None] = Field(default_factory=dict)
    benchmark_adjusted: dict[str, float | None] = Field(default_factory=dict)
    mfe_pct: float | None = None
    mae_pct: float | None = None
    time_to_mfe_bars: int | None = None
    time_to_mae_bars: int | None = None
    max_drawdown_pct: float | None = None
    realised_volatility: float | None = None
    target_hit: bool | None = None
    invalidation_hit: bool | None = None
    target_before_invalidation: bool | None = None
    invalidation_before_target: bool | None = None
    evaluation_note: str = ""

"""The four epistemic levels, as Pydantic models.

    Observation    -> a FACT, straight from a source, value untouched
    Computation    -> a CALCULATION we performed, with its formula recorded
    Interpretation -> what an analyst concludes from facts and calculations
    Hypothesis     -> a conditional statement about the future

Every level above FACT carries `evidence_ids` pointing one level down, which is
what makes the "WHY?" panel possible: any conclusion can be unrolled back to
the raw numbers a source published.

Hard rule enforced here: an Observation can only be built by a provider.
`Observation.from_llm` does not exist, and never will.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .enums import (
    Asset,
    ConfirmationState,
    DataQuality,
    Direction,
    EvidenceKind,
    Freshness,
    Horizon,
    LegalStatus,
    Reliability,
    Timeframe,
    TrendDirection,
)


def utcnow() -> datetime:
    return datetime.now(UTC)


def _ensure_utc(value: datetime) -> datetime:
    """Naive datetimes are assumed UTC - mixing tz-aware and naive silently
    corrupts every freshness computation downstream."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class Provenance(BaseModel):
    """Where a number came from. Mandatory on every Observation."""

    model_config = ConfigDict(frozen=True)

    source: str = Field(..., description="Human-facing source name, e.g. 'Binance'")
    provider: str = Field(..., description="Exact provider implementation, e.g. 'binance_spot'")
    source_url: str | None = None
    fetched_at: datetime = Field(default_factory=utcnow)
    license_note: str | None = None

    @field_validator("fetched_at")
    @classmethod
    def _utc(cls, v: datetime) -> datetime:
        return _ensure_utc(v)


class Observation(BaseModel):
    """A FACT: one measured value, from one source, at one point in time.

    `value` holds the ORIGINAL value as published. Any transformation produces
    a separate Computation, so the raw published number stays recoverable.
    """

    model_config = ConfigDict(frozen=True)

    kind: EvidenceKind = EvidenceKind.FACT
    id: str = ""
    asset: Asset | None = None
    metric: str = Field(..., description="Dotted metric name, e.g. 'price.close'")
    value: float | int | str | dict[str, Any] | list[Any] | None = None
    unit: str = Field(default="", description="USD, USD_M, pct, count, ratio, bool, text")
    timestamp: datetime = Field(..., description="What time the value refers to (UTC)")
    provenance: Provenance
    freshness: Freshness = Freshness.UNAVAILABLE
    confidence: float = Field(default=80.0, ge=0.0, le=100.0)
    quality: DataQuality = DataQuality.MEASURED
    timeframe: Timeframe | None = None
    meta: dict[str, Any] = Field(default_factory=dict)

    @field_validator("timestamp")
    @classmethod
    def _utc(cls, v: datetime) -> datetime:
        return _ensure_utc(v)

    def model_post_init(self, __context: Any) -> None:
        if not self.id:
            object.__setattr__(self, "id", self.compute_id())

    def compute_id(self) -> str:
        """Deterministic id: re-fetching the same datapoint yields the same id,
        so re-collection is idempotent and never duplicates rows."""
        raw = "|".join(
            [
                self.provenance.provider,
                self.asset.value if self.asset else "-",
                self.metric,
                self.timeframe.value if self.timeframe else "-",
                self.timestamp.isoformat(),
            ]
        )
        return "obs_" + hashlib.sha1(raw.encode()).hexdigest()[:16]

    @property
    def numeric_value(self) -> float | None:
        """None when the value is not a number.

        Callers must handle None rather than coerce, otherwise a text metric
        silently becomes 0.0 and reads as a real measurement.

        Note: booleans are normalised to 1.0/0.0 by the field's type union
        before they reach here, which is intended - flag metrics carry
        unit="bool" and are consumed numerically.
        """
        if isinstance(self.value, int | float):
            return float(self.value)
        return None

    @property
    def age_seconds(self) -> float:
        return (utcnow() - self.timestamp).total_seconds()

    def describe(self) -> str:
        val = self.value if not isinstance(self.value, dict | list) else "<structured>"
        return (
            f"{self.metric}={val}{(' ' + self.unit) if self.unit else ''} "
            f"[{self.provenance.source}, {self.timestamp:%Y-%m-%d %H:%M}Z, {self.freshness.value}]"
        )


class Computation(BaseModel):
    """A CALCULATION. Deterministic, reproducible, and it records its formula."""

    model_config = ConfigDict(frozen=True)

    kind: EvidenceKind = EvidenceKind.COMPUTATION
    id: str = ""
    asset: Asset | None = None
    name: str
    value: float | int | str | dict[str, Any] | list[Any] | None
    unit: str = ""
    formula: str = Field(default="", description="Plain-language description of the maths")
    engine: str = Field(default="", description="Which engine produced it")
    timeframe: Timeframe | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    freshness: Freshness = Freshness.UNAVAILABLE
    quality: DataQuality = DataQuality.DERIVED
    computed_at: datetime = Field(default_factory=utcnow)
    meta: dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        if not self.id:
            raw = f"{self.engine}|{self.name}|{self.asset}|{self.timeframe}|{self.computed_at.isoformat()}"
            object.__setattr__(self, "id", "cmp_" + hashlib.sha1(raw.encode()).hexdigest()[:16])


class Interpretation(BaseModel):
    """An INTERPRETATION: what an analyst reads into the facts and calculations.

    `directional_impact` is deliberately separate from `statement`: the prose
    can stay nuanced while the machine-readable signal stays crisp.
    """

    model_config = ConfigDict(frozen=True)

    kind: EvidenceKind = EvidenceKind.INTERPRETATION
    id: str = ""
    asset: Asset | None = None
    analyst: str
    statement: str
    direction: Direction = Direction.NEUTRAL
    strength: float = Field(default=0.0, ge=-100.0, le=100.0)
    confidence: float = Field(default=50.0, ge=0.0, le=100.0)
    evidence_ids: list[str] = Field(default_factory=list)
    knowledge_citations: list[str] = Field(default_factory=list)
    horizon: Horizon = Horizon.MEDIUM
    created_at: datetime = Field(default_factory=utcnow)
    meta: dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        if not self.id:
            raw = f"{self.analyst}|{self.asset}|{self.statement}|{self.created_at.isoformat()}"
            object.__setattr__(self, "id", "int_" + hashlib.sha1(raw.encode()).hexdigest()[:16])


class Hypothesis(BaseModel):
    """A HYPOTHESIS: conditional, never asserted as fact.

    `probability` is an *indicative analytical* probability unless
    `calibrated` is True - which only a backtested model may set.
    """

    model_config = ConfigDict(frozen=True)

    kind: EvidenceKind = EvidenceKind.HYPOTHESIS
    id: str = ""
    asset: Asset | None = None
    statement: str
    conditions: list[str] = Field(default_factory=list)
    probability: float | None = Field(default=None, ge=0.0, le=100.0)
    calibrated: bool = False
    invalidation: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    horizon: Horizon = Horizon.MEDIUM
    created_at: datetime = Field(default_factory=utcnow)

    @property
    def probability_label(self) -> str:
        if self.probability is None:
            return "non quantifiee"
        if self.calibrated:
            return f"{self.probability:.0f}% (modele calibre)"
        return f"{self.probability:.0f}% (probabilite analytique indicative)"

    def model_post_init(self, __context: Any) -> None:
        if not self.id:
            raw = f"{self.asset}|{self.statement}|{self.created_at.isoformat()}"
            object.__setattr__(self, "id", "hyp_" + hashlib.sha1(raw.encode()).hexdigest()[:16])


class Candle(BaseModel):
    """One OHLCV bar."""

    model_config = ConfigDict(frozen=True)

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    @field_validator("timestamp")
    @classmethod
    def _utc(cls, v: datetime) -> datetime:
        return _ensure_utc(v)


class OHLCVSeries(BaseModel):
    """A candle series plus its provenance - the series itself is a fact."""

    asset: Asset
    timeframe: Timeframe
    candles: list[Candle]
    provenance: Provenance
    freshness: Freshness = Freshness.UNAVAILABLE

    @property
    def closes(self) -> list[float]:
        return [c.close for c in self.candles]

    @property
    def last(self) -> Candle | None:
        return self.candles[-1] if self.candles else None

    def __len__(self) -> int:
        return len(self.candles)


class PatternMatch(BaseModel):
    """A chart pattern. Only emitted above the configured confidence floor -
    a vaguely similar shape is not a pattern."""

    model_config = ConfigDict(frozen=True)

    pattern: str
    confidence: float = Field(..., ge=0.0, le=100.0)
    timeframe: Timeframe
    confirmation_state: ConfirmationState
    invalidation_level: float | None = None
    target_level: float | None = None
    direction: Direction = Direction.NEUTRAL
    detected_at: datetime = Field(default_factory=utcnow)
    start_index: int | None = None
    end_index: int | None = None
    notes: str = ""
    evidence: dict[str, Any] = Field(default_factory=dict)


class Level(BaseModel):
    """A support or resistance level derived from swing clustering."""

    model_config = ConfigDict(frozen=True)

    price: float
    kind: str                     # "support" | "resistance"
    touches: int
    strength: float = Field(..., ge=0.0, le=100.0)
    last_touch: datetime | None = None
    distance_pct: float | None = None


class Divergence(BaseModel):
    model_config = ConfigDict(frozen=True)

    indicator: str                # "RSI" | "MACD"
    kind: str                     # "bullish" | "bearish" | "hidden_bullish" | "hidden_bearish"
    timeframe: Timeframe
    strength: float = Field(..., ge=0.0, le=100.0)
    price_points: list[float] = Field(default_factory=list)
    indicator_points: list[float] = Field(default_factory=list)
    start_time: datetime | None = None
    end_time: datetime | None = None


class ScoreCard(BaseModel):
    """A domain score, with everything needed to weight it honestly.

    A +90 at 20% confidence must not dominate a +40 at 95% - that is why
    confidence, freshness and evidence_count travel with the score itself
    rather than being bolted on later.
    """

    domain: str
    score: float = Field(..., ge=-100.0, le=100.0)
    confidence: float = Field(..., ge=0.0, le=100.0)
    freshness: Freshness = Freshness.UNAVAILABLE
    evidence_count: int = 0
    available: bool = True
    unavailable_reason: str | None = None
    components: dict[str, float] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @classmethod
    def unavailable_card(cls, domain: str, reason: str) -> ScoreCard:
        """The only honest score for missing data: zero weight, not zero signal."""
        return cls(
            domain=domain,
            score=0.0,
            confidence=0.0,
            freshness=Freshness.UNAVAILABLE,
            evidence_count=0,
            available=False,
            unavailable_reason=reason,
        )


class Contradiction(BaseModel):
    model_config = ConfigDict(frozen=True)

    description: str
    signals: list[str]
    strength: float = Field(..., ge=0.0, le=100.0)
    domains: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class Scenario(BaseModel):
    name: str                     # "central" | "bull" | "bear"
    label: str
    probability: float = Field(..., ge=0.0, le=100.0)
    calibrated: bool = False
    narrative: str
    conditions: list[str] = Field(default_factory=list)
    key_levels: dict[str, float] = Field(default_factory=dict)
    catalysts: list[str] = Field(default_factory=list)
    invalidation: str = ""

    @property
    def probability_label(self) -> str:
        if self.calibrated:
            return f"{self.probability:.0f}%"
        return f"{self.probability:.0f}% (probabilite analytique indicative)"


class Conviction(BaseModel):
    horizon: Horizon
    score: float = Field(..., ge=-100.0, le=100.0)
    label: str
    confidence: float = Field(..., ge=0.0, le=100.0)
    direction: Direction
    contributors: dict[str, float] = Field(default_factory=dict)
    capped_by_contradiction: bool = False
    rationale: list[str] = Field(default_factory=list)


class Alert(BaseModel):
    kind: str
    importance: str
    asset: Asset | None = None
    title: str
    detail: str
    triggered_at: datetime = Field(default_factory=utcnow)
    evidence_ids: list[str] = Field(default_factory=list)


class RegulatoryEvent(BaseModel):
    """A regulatory or political item, with its legal status made explicit.

    Presenting a bill as enacted law would be the single most damaging error
    this system could make, so `legal_status` is required, never inferred late.
    """

    model_config = ConfigDict(frozen=True)

    title: str
    institution: str
    legal_status: LegalStatus
    published_at: datetime
    summary: str = ""
    assets_concerned: list[Asset] = Field(default_factory=list)
    importance: float = Field(default=50.0, ge=0.0, le=100.0)
    sentiment: Direction = Direction.NEUTRAL
    uncertainty: float = Field(default=50.0, ge=0.0, le=100.0)
    source_url: str = ""
    source_name: str = ""
    tier: int = 4


class NewsItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: str
    url: str
    source: str
    tier: int = 4
    published_at: datetime
    summary: str = ""
    assets: list[Asset] = Field(default_factory=list)
    is_opinion: bool = False
    is_official: bool = False


class NewsCluster(BaseModel):
    """One real-world event, however many outlets reported it.

    30 sites republishing one story is one signal, weighted by the most
    credible member of the cluster - not 30 signals.
    """

    event_title: str
    items: list[NewsItem]
    primary_source: str
    best_tier: int
    published_at: datetime
    assets: list[Asset] = Field(default_factory=list)
    importance: float = Field(default=50.0, ge=0.0, le=100.0)
    duplicate_count: int = 0


class WhaleSignal(BaseModel):
    """Whale activity. `reliability` is mandatory: without a credible source,
    no whale signal is emitted at all."""

    model_config = ConfigDict(frozen=True)

    asset: Asset
    behaviour: str                # accumulating | distributing | to_exchange | from_exchange
    magnitude: float | None = None
    unit: str = ""
    reliability: Reliability = Reliability.UNVERIFIED
    threshold_used: float | None = None
    threshold_unit: str = ""
    window_hours: int = 24
    source: str = ""
    evidence_ids: list[str] = Field(default_factory=list)


class TrendState(BaseModel):
    direction: TrendDirection
    strength: float = Field(default=0.0, ge=0.0, le=100.0)
    reason: str = ""


class MacroEvent(BaseModel):
    name: str
    kind: str
    scheduled_at: datetime
    importance: str
    hours_until: float | None = None
    is_past: bool = False
    assets_impact: list[Asset] = Field(default_factory=list)

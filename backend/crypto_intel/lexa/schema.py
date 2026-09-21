"""Typed schema of what a Lexa video says, as extracted from its transcript.

Every claim carries where it was said (timestamp + the passage) and how we
know it:

    EXPLICIT   Lexa says it in so many words            confidence HIGH
    INFERRED   read from the context around the value    confidence MEDIUM
    UNKNOWN    cannot be determined - never guessed      shown « ⚪ Non précisé »

A value that cannot be tied back to the transcript is not a claim: the
verifier moves it to `rejected`, and it never reaches the report or the plan.
Figures the application computes itself live apart, under `app_simulation`,
and are labelled « CALCUL APP ».
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Basis = Literal["EXPLICIT", "INFERRED", "UNKNOWN"]
Confidence = Literal["HIGH", "MEDIUM", "LOW"]
Timeframe = Literal["15M", "1H", "4H", "1D", "1W", "LONG_TERM"]

LevelKind = Literal[
    "SUPPORT", "RESISTANCE", "BUY_ZONE", "REINFORCEMENT", "CONFIRMATION",
    "INVALIDATION", "TARGET", "TAKE_PROFIT", "OTHER",
]
ConditionKind = Literal[
    "BREAKOUT", "CLOSE_ABOVE", "CLOSE_BELOW", "RETEST", "VOLUME", "HOLD_ABOVE",
    "HOLD_BELOW", "OTHER", "UNKNOWN",
]

BASIS_FR = {
    "EXPLICIT": "🟢 Dit explicitement",
    "INFERRED": "🟡 Interprétation du contexte",
    "UNKNOWN": "⚪ Non précisé",
}
CONFIDENCE_BY_BASIS = {"EXPLICIT": "HIGH", "INFERRED": "MEDIUM", "UNKNOWN": "LOW"}


class Evidence(BaseModel):
    """Where it was said. `quote` is copied from the transcript, not rephrased."""

    timestamp_s: int | None = None
    quote: str = ""
    verified: bool = False
    verification_note: str = ""


class Claim(BaseModel):
    text: str
    basis: Basis = "UNKNOWN"
    evidence: Evidence = Field(default_factory=Evidence)


class Condition(BaseModel):
    kind: ConditionKind = "UNKNOWN"
    timeframe: Timeframe | None = None
    text: str = ""


class Level(BaseModel):
    value: float
    kind: LevelKind
    role: str = ""  # "Achat principal", "TP1", ... in Lexa's own ordering
    basis: Basis = "UNKNOWN"
    confidence: Confidence = "LOW"
    timeframe: Timeframe | None = None
    condition: Condition = Field(default_factory=Condition)
    # Only when Lexa states it. Never filled in by the application.
    allocation_pct: float | None = None
    allocation_basis: Basis = "UNKNOWN"
    allocation_evidence: Evidence | None = None
    reasoning: str = ""
    evidence: Evidence = Field(default_factory=Evidence)


class Scenario(BaseModel):
    scenario_id: str
    condition: str
    direction: Literal["UP", "DOWN", "RANGE"] | None = None
    level_values: list[float] = Field(default_factory=list)
    targets: list[float] = Field(default_factory=list)
    invalidation: float | None = None
    evidence: Evidence = Field(default_factory=Evidence)


class Argument(BaseModel):
    indicator: str  # STRUCTURE, VOLUME, RSI, BOLLINGER, LIQUIDITY, BTC_DOMINANCE, ...
    argument: str
    direction: Literal["BULLISH", "BEARISH", "NEUTRAL"] | None = None
    evidence: Evidence = Field(default_factory=Evidence)


class Event(BaseModel):
    event: str
    date: str | None = None  # only as said in the video
    asset: str | None = None
    comment: str = ""
    evidence: Evidence = Field(default_factory=Evidence)


class Rejected(BaseModel):
    """What the model proposed and the verifier could not tie to the transcript."""

    what: str
    value: float | None = None
    reason: str
    timestamp_s: int | None = None


class AssetAnalysis(BaseModel):
    symbol: str
    price_at_video: float | None = None
    price_at_video_evidence: Evidence = Field(default_factory=Evidence)
    stance: Literal["WAIT", "BUY", "SELL", "NEUTRAL", "UNSPECIFIED"] = "UNSPECIFIED"
    stance_basis: Basis = "UNKNOWN"
    situation: list[Claim] = Field(default_factory=list)
    levels: list[Level] = Field(default_factory=list)
    scenarios: list[Scenario] = Field(default_factory=list)
    arguments: list[Argument] = Field(default_factory=list)
    events: list[Event] = Field(default_factory=list)
    reasoning: list[str] = Field(default_factory=list)
    rejected: list[Rejected] = Field(default_factory=list)
    ambiguous: list[str] = Field(default_factory=list)


class TranscriptInfo(BaseModel):
    source: str
    segments: int
    duration_s: int
    characters: int
    uncertain_passages: list[Evidence] = Field(default_factory=list)
    quality: str = ""


class VideoInfo(BaseModel):
    title: str
    published_at: str | None = None
    source: str = "Lexa"


class ExtractionResult(BaseModel):
    schema_version: Literal["lexa-extraction/1"] = "lexa-extraction/1"
    video: VideoInfo
    transcript: TranscriptInfo
    model: str
    assets_mentioned: dict[str, int] = Field(default_factory=dict)
    assets: list[AssetAnalysis] = Field(default_factory=list)
    not_analysed: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

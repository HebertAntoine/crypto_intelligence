"""Pydantic schemas for every LLM output.

The model never returns free text into the pipeline: it returns a structure
that must validate. Anything that fails validation is rejected and retried with
the error fed back, so a malformed answer can never propagate.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class Finding(BaseModel):
    statement: str = Field(..., min_length=5, max_length=400)
    direction: str = Field(default="NEUTRAL")
    importance: int = Field(default=50, ge=0, le=100)
    evidence_refs: list[str] = Field(default_factory=list)

    @field_validator("direction")
    @classmethod
    def _dir(cls, v: str) -> str:
        v = v.upper().strip()
        return v if v in ("BULLISH", "BEARISH", "NEUTRAL", "INCONCLUSIVE") else "NEUTRAL"

    @field_validator("evidence_refs")
    @classmethod
    def _evidence_refs(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(value.strip() for value in values if value.strip()))


class AnalystOutput(BaseModel):
    """What each specialised analyst returns."""

    analyst: str
    summary: str = Field(..., min_length=10, max_length=1200)
    score: float = Field(..., ge=-100, le=100)
    confidence: float = Field(..., ge=0, le=100)
    positives: list[Finding] = Field(default_factory=list)
    negatives: list[Finding] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)
    knowledge_citations: list[str] = Field(default_factory=list)


class ScenarioOutput(BaseModel):
    name: str
    label: str = Field(..., max_length=160)
    # The language model is never the authority for a scenario probability.
    # Calibrated probabilities enter through deterministic model contracts,
    # not through this narrative schema.
    probability: None = None
    narrative: str = Field(..., min_length=15, max_length=1200)
    conditions: list[str] = Field(default_factory=list)
    key_levels: dict[str, float] = Field(default_factory=dict)
    catalysts: list[str] = Field(default_factory=list)
    invalidation: str = ""

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = v.lower().strip()
        return v if v in ("central", "bull", "bear") else "central"


class ChiefAnalystOutput(BaseModel):
    """The synthesis. Receives analyst conclusions, never raw data."""

    synthesis: str = Field(..., min_length=40, max_length=3000)
    positives: list[str] = Field(default_factory=list, max_length=8)
    negatives: list[str] = Field(default_factory=list, max_length=8)
    contradictions: list[str] = Field(default_factory=list, max_length=6)
    key_catalysts: list[str] = Field(default_factory=list, max_length=8)
    key_risks: list[str] = Field(default_factory=list, max_length=8)
    what_would_change_my_mind: list[str] = Field(default_factory=list, max_length=6)
    scenarios: list[ScenarioOutput] = Field(default_factory=list, max_length=3)
    missing_data: list[str] = Field(default_factory=list, max_length=10)
    data_quality_note: str = ""

class NewsAssessment(BaseModel):
    """LLM reading of clustered news - kept separate from numeric scoring."""

    overall_tone: str = Field(default="NEUTRAL")
    score: float = Field(default=0.0, ge=-100, le=100)
    confidence: float = Field(default=40.0, ge=0, le=100)
    key_events: list[str] = Field(default_factory=list, max_length=6)
    notes: str = ""

    @field_validator("overall_tone")
    @classmethod
    def _tone(cls, v: str) -> str:
        v = v.upper().strip()
        return v if v in ("BULLISH", "BEARISH", "NEUTRAL", "INCONCLUSIVE") else "NEUTRAL"

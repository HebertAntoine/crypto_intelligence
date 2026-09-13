"""Timestamped market expectations with no generated probabilities."""

from __future__ import annotations

import math
import re
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..future_events.models import FutureEvent, MarketProbability


class MarketExpectationStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"


class ExpectedOutcome(BaseModel):
    model_config = ConfigDict(frozen=True)

    outcome: str
    probability: float = Field(ge=0.0, le=1.0)


class MarketExpectation(BaseModel):
    """One auditable market-pricing observation for one future event."""

    model_config = ConfigDict(frozen=True)

    event_id: str
    observed_at: datetime
    expected_outcome: ExpectedOutcome | None = None
    outcome_distribution: list[MarketProbability] = Field(default_factory=list)
    market_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    probability_timestamp: datetime | None = None
    uncertainty: float | None = Field(default=None, ge=0.0, le=1.0)
    source: str | None = None
    methodology: str
    freshness: str
    status: MarketExpectationStatus
    unavailable_reason: str | None = None
    asymmetry: list[dict[str, Any]] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def probability_has_provenance(self) -> MarketExpectation:
        if self.outcome_distribution:
            if self.probability_timestamp is None:
                raise ValueError("probability_timestamp is mandatory for market probabilities")
            if not self.source:
                raise ValueError("source is mandatory for market probabilities")
            if self.expected_outcome is None or self.market_probability is None:
                raise ValueError("a priced distribution requires its most likely outcome")
            total = sum(item.probability for item in self.outcome_distribution)
            if not 0.98 <= total <= 1.02:
                raise ValueError("market probability distribution must sum to one")
        if self.status is MarketExpectationStatus.AVAILABLE and not self.outcome_distribution:
            raise ValueError("AVAILABLE expectation requires a probability distribution")
        return self

    @property
    def available(self) -> bool:
        return self.status is MarketExpectationStatus.AVAILABLE

    @property
    def distribution(self) -> list[MarketProbability]:
        """Compatibility alias for the former response model."""

        return self.outcome_distribution

    @property
    def degree_priced(self) -> float | None:
        """Compatibility alias; this is the top market probability."""

        return self.market_probability


MarketExpectationAnalysis = MarketExpectation


def _numeric_outcome(label: str) -> float | None:
    """Return the midpoint of a target-range/rate label when it is numeric."""

    values = [float(value) for value in re.findall(r"\d+(?:\.\d+)?", label)]
    if not values:
        return None
    if len(values) >= 2 and ("-" in label or "to" in label.lower()):
        return (values[0] + values[1]) / 2.0
    if label.lstrip().startswith("-"):
        return -values[0]
    return values[0]


class MarketExpectationEngine:
    """Read complete, sourced probability distributions; never infer one."""

    default_max_age = timedelta(hours=6)
    live_age = timedelta(minutes=15)

    def analyze(
        self,
        event: FutureEvent,
        *,
        as_of: datetime | None = None,
        max_age: timedelta | None = None,
    ) -> MarketExpectation:
        now = as_of or datetime.now(UTC)
        now = now.replace(tzinfo=UTC) if now.tzinfo is None else now.astimezone(UTC)
        distribution = event.market_probabilities
        timestamp = event.probability_timestamp
        methodology = (
            "The distribution is supplied by the named market-data source. "
            "Uncertainty is normalised Shannon entropy; confidence describes "
            "source/data quality, not scenario probability."
        )
        if not distribution or timestamp is None:
            return MarketExpectation(
                event_id=event.id,
                observed_at=now,
                methodology=(
                    "No probability is inferred when timestamped market pricing "
                    "is unavailable."
                ),
                freshness="UNAVAILABLE",
                status=MarketExpectationStatus.UNAVAILABLE,
                unavailable_reason=(
                    "UNAVAILABLE - no complete timestamped market probability distribution"
                ),
            )

        observed = (
            timestamp.replace(tzinfo=UTC)
            if timestamp.tzinfo is None
            else timestamp.astimezone(UTC)
        )
        probability_sources = {
            item.source.strip() for item in distribution if item.source.strip()
        }
        timestamp_mismatch = any(item.observed_at != observed for item in distribution)
        if not probability_sources or timestamp_mismatch or observed > now + timedelta(minutes=5):
            reason = (
                "UNAVAILABLE - probability rows do not share the event timestamp"
                if timestamp_mismatch
                else "UNAVAILABLE - probability provenance/timestamp is invalid"
            )
            return MarketExpectation(
                event_id=event.id,
                observed_at=now,
                methodology="Invalid probability metadata is rejected, not repaired.",
                freshness="UNAVAILABLE",
                status=MarketExpectationStatus.UNAVAILABLE,
                unavailable_reason=reason,
            )

        source = ", ".join(sorted(probability_sources))
        expected = max(distribution, key=lambda item: item.probability)
        count = len(distribution)
        entropy = -sum(
            item.probability * math.log(item.probability)
            for item in distribution
            if item.probability > 0
        )
        uncertainty = entropy / math.log(count) if count > 1 else 0.0

        numeric_distribution = [
            (_numeric_outcome(item.outcome), item.probability) for item in distribution
        ]
        expected_value: float | None = None
        if all(value is not None for value, _probability in numeric_distribution):
            expected_value = 0.0
            for value, probability in numeric_distribution:
                assert value is not None
                expected_value += value * probability
        asymmetry = []
        for item in sorted(distribution, key=lambda value: value.probability, reverse=True):
            numeric = _numeric_outcome(item.outcome)
            asymmetry.append(
                {
                    "outcome": item.outcome,
                    "probability": item.probability,
                    "distance_from_expected": (
                        numeric - expected_value
                        if numeric is not None and expected_value is not None
                        else None
                    ),
                }
            )

        age = max(timedelta(0), now - observed)
        allowed_age = max_age or self.default_max_age
        if age > allowed_age:
            status = MarketExpectationStatus.STALE
            freshness = "STALE"
            unavailable_reason = (
                f"STALE - probability observation is {int(age.total_seconds())} seconds old; "
                f"maximum is {int(allowed_age.total_seconds())}"
            )
        else:
            status = MarketExpectationStatus.AVAILABLE
            freshness = "LIVE" if age <= self.live_age else "RECENT"
            unavailable_reason = None

        return MarketExpectation(
            event_id=event.id,
            observed_at=now,
            expected_outcome=ExpectedOutcome(
                outcome=expected.outcome,
                probability=expected.probability,
            ),
            outcome_distribution=distribution,
            market_probability=expected.probability,
            probability_timestamp=observed,
            uncertainty=uncertainty,
            source=source,
            methodology=methodology,
            freshness=freshness,
            status=status,
            unavailable_reason=unavailable_reason,
            asymmetry=asymmetry,
            confidence=event.confidence,
        )

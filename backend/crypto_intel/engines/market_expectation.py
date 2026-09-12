"""Expectation-versus-surprise analysis with no generated probabilities."""

from __future__ import annotations

import math
import re
from typing import Any

from pydantic import BaseModel, Field

from ..future_events.models import FutureEvent, MarketProbability


class ExpectedOutcome(BaseModel):
    outcome: str
    probability: float


class SurpriseResult(BaseModel):
    actual_outcome: str
    expected_probability: float
    surprise_score: float
    signed_distance: float | None = None
    methodology: str


class MarketExpectationAnalysis(BaseModel):
    available: bool
    unavailable_reason: str | None = None
    expected_outcome: ExpectedOutcome | None = None
    distribution: list[MarketProbability] = Field(default_factory=list)
    probability_timestamp: str | None = None
    degree_priced: float | None = None
    uncertainty: float | None = None
    asymmetry: list[dict[str, Any]] = Field(default_factory=list)
    surprise: SurpriseResult | None = None
    confidence: float = 0.0
    methodology: str = ""


def _numeric_outcome(label: str) -> float | None:
    """Midpoint of a target range/rate label, in percentage points."""
    values = [float(value) for value in re.findall(r"\d+(?:\.\d+)?", label)]
    if not values:
        return None
    # Labels such as "4.25-4.50%" are ranges; "+25 bp" is a single outcome.
    if len(values) >= 2 and ("-" in label or "to" in label.lower()):
        return (values[0] + values[1]) / 2.0
    if label.lstrip().startswith("-"):
        return -values[0]
    return values[0]


class MarketExpectationEngine:
    """Read market probabilities; never estimate a missing distribution."""

    def calculate_surprise(
        self, distribution: list[MarketProbability], actual_outcome: str
    ) -> SurpriseResult:
        probabilities = {item.outcome: item.probability for item in distribution}
        expected_probability = probabilities.get(actual_outcome, 0.0)
        surprise_score = 1.0 - expected_probability

        actual_numeric = _numeric_outcome(actual_outcome)
        numeric_distribution = [
            (_numeric_outcome(item.outcome), item.probability) for item in distribution
        ]
        signed_distance = None
        if actual_numeric is not None and all(value is not None for value, _ in numeric_distribution):
            expected_numeric = sum(
                float(value) * probability for value, probability in numeric_distribution
            )
            signed_distance = actual_numeric - expected_numeric

        return SurpriseResult(
            actual_outcome=actual_outcome,
            expected_probability=expected_probability,
            surprise_score=surprise_score,
            signed_distance=signed_distance,
            methodology=(
                "surprise_score = 1 - market probability assigned to the realised outcome; "
                "signed_distance = realised numeric outcome - probability-weighted expectation"
            ),
        )

    def analyze(self, event: FutureEvent, *, actual_outcome: str | None = None) -> MarketExpectationAnalysis:
        distribution = event.market_probabilities
        if not distribution or event.probability_timestamp is None:
            return MarketExpectationAnalysis(
                available=False,
                unavailable_reason="UNAVAILABLE - no timestamped market probability distribution",
                confidence=0.0,
                methodology="No probability is inferred when market pricing is unavailable.",
            )

        expected = max(distribution, key=lambda item: item.probability)
        count = len(distribution)
        entropy = -sum(
            item.probability * math.log(item.probability)
            for item in distribution
            if item.probability > 0
        )
        uncertainty = entropy / math.log(count) if count > 1 else 0.0
        numeric_expected = [
            (_numeric_outcome(item.outcome), item.probability) for item in distribution
        ]
        expected_value = None
        if all(value is not None for value, _ in numeric_expected):
            expected_value = sum(float(value) * probability for value, probability in numeric_expected)

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

        realised = actual_outcome
        if realised is None and isinstance(event.actual_value, str):
            realised = event.actual_value
        return MarketExpectationAnalysis(
            available=True,
            expected_outcome=ExpectedOutcome(
                outcome=expected.outcome, probability=expected.probability
            ),
            distribution=distribution,
            probability_timestamp=event.probability_timestamp.isoformat(),
            degree_priced=expected.probability,
            uncertainty=uncertainty,
            asymmetry=asymmetry,
            surprise=self.calculate_surprise(distribution, realised) if realised else None,
            confidence=event.confidence,
            methodology=(
                "Distribution supplied by the named market-data source. Uncertainty is normalised "
                "Shannon entropy; confidence describes source/data quality, not scenario probability."
            ),
        )

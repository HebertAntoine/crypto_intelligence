"""Expected-versus-actual event surprise, kept separate from expectations."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from .market_expectation import MarketExpectation, MarketExpectationStatus, _numeric_outcome


class EventSurpriseStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class EventSurprise(BaseModel):
    """Surprise channels; signs are contextual, never inferred from rate verbs."""

    model_config = ConfigDict(frozen=True)

    event_id: str
    observed_at: datetime
    expected_outcome: str | None = None
    actual_outcome: str | None = None
    consensus_strength: float | None = Field(default=None, ge=0.0, le=1.0)
    expected_probability_of_actual: float | None = Field(default=None, ge=0.0, le=1.0)
    probability_surprise: float | None = Field(default=None, ge=0.0, le=1.0)
    numeric_surprise: float | None = None
    directional_surprise: float | None = None
    communication_surprise: float | None = None
    projections_surprise: float | None = None
    guidance_surprise: float | None = None
    overall_surprise: float | None = Field(default=None, ge=0.0, le=1.0)
    overall_direction: str | None = None
    status: EventSurpriseStatus
    unavailable_reason: str | None = None
    methodology: str


class EventSurpriseEngine:
    """Compare a realised outcome with a timestamped market distribution.

    ``outcome_direction`` is deliberately supplied by a domain adapter. This
    engine has no built-in mapping such as hike=bearish or cut=bullish.
    Communication/projection/guidance values must also be structured inputs on
    the common [-1, 1] convention: positive supports the analysed asset,
    negative opposes it, zero is neutral.
    """

    def analyze(
        self,
        expectation: MarketExpectation,
        *,
        actual_outcome: str | None,
        observed_at: datetime | None = None,
        actual_numeric: float | None = None,
        expected_numeric: float | None = None,
        numeric_scale: float | None = None,
        outcome_direction: dict[str, float] | None = None,
        expected_communication: float | None = None,
        actual_communication: float | None = None,
        projections_surprise: float | None = None,
        guidance_surprise: float | None = None,
    ) -> EventSurprise:
        now = observed_at or datetime.now(UTC)
        now = now.replace(tzinfo=UTC) if now.tzinfo is None else now.astimezone(UTC)
        methodology = (
            "Rate/numeric, directional, statement communication, projections and "
            "guidance are separate channels. No economic direction is inferred "
            "from words such as hike or cut."
        )
        if expectation.status is MarketExpectationStatus.UNAVAILABLE:
            return EventSurprise(
                event_id=expectation.event_id,
                observed_at=now,
                actual_outcome=actual_outcome,
                status=EventSurpriseStatus.UNAVAILABLE,
                unavailable_reason="UNAVAILABLE - no valid pre-event market expectation",
                methodology=methodology,
            )
        if not actual_outcome:
            return EventSurprise(
                event_id=expectation.event_id,
                observed_at=now,
                expected_outcome=(
                    expectation.expected_outcome.outcome
                    if expectation.expected_outcome
                    else None
                ),
                status=EventSurpriseStatus.UNAVAILABLE,
                unavailable_reason="UNAVAILABLE - event outcome has not been observed",
                methodology=methodology,
            )

        probabilities = {
            item.outcome: item.probability for item in expectation.outcome_distribution
        }
        actual_probability = probabilities.get(actual_outcome, 0.0)
        probability_surprise = 1.0 - actual_probability
        expected_label = (
            expectation.expected_outcome.outcome if expectation.expected_outcome else None
        )

        realised_number = (
            actual_numeric if actual_numeric is not None else _numeric_outcome(actual_outcome)
        )
        anticipated_number = expected_numeric
        if anticipated_number is None and expected_label:
            anticipated_number = _numeric_outcome(expected_label)
        numeric_surprise = (
            realised_number - anticipated_number
            if realised_number is not None and anticipated_number is not None
            else None
        )

        directional_surprise = None
        if outcome_direction and actual_outcome in outcome_direction and all(
            item.outcome in outcome_direction for item in expectation.outcome_distribution
        ):
            expected_direction = sum(
                outcome_direction[item.outcome] * item.probability
                for item in expectation.outcome_distribution
            )
            directional_surprise = outcome_direction[actual_outcome] - expected_direction

        communication_surprise = None
        if expected_communication is not None and actual_communication is not None:
            communication_surprise = max(
                -2.0,
                min(2.0, actual_communication - expected_communication),
            )

        magnitude_channels = [probability_surprise]
        signed_channels: list[float] = []
        if numeric_surprise is not None and numeric_scale is not None and numeric_scale > 0:
            normalized_numeric = max(-1.0, min(1.0, numeric_surprise / numeric_scale))
            magnitude_channels.append(abs(normalized_numeric))
            signed_channels.append(normalized_numeric)
        if directional_surprise is not None:
            normalized_direction = max(-1.0, min(1.0, directional_surprise / 2.0))
            magnitude_channels.append(abs(normalized_direction))
            signed_channels.append(normalized_direction)
        for value in (communication_surprise, projections_surprise, guidance_surprise):
            if value is not None:
                normalized = max(-1.0, min(1.0, value / 2.0))
                magnitude_channels.append(abs(normalized))
                signed_channels.append(normalized)

        net_direction = sum(signed_channels)
        overall_direction = (
            "POSITIVE" if net_direction > 0 else "NEGATIVE" if net_direction < 0 else None
        )
        return EventSurprise(
            event_id=expectation.event_id,
            observed_at=now,
            expected_outcome=expected_label,
            actual_outcome=actual_outcome,
            consensus_strength=expectation.market_probability,
            expected_probability_of_actual=actual_probability,
            probability_surprise=probability_surprise,
            numeric_surprise=numeric_surprise,
            directional_surprise=directional_surprise,
            communication_surprise=communication_surprise,
            projections_surprise=projections_surprise,
            guidance_surprise=guidance_surprise,
            overall_surprise=max(magnitude_channels),
            overall_direction=overall_direction,
            status=EventSurpriseStatus.AVAILABLE,
            methodology=methodology,
        )

"""Provenance and the four epistemic levels."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from crypto_intel.core.enums import Asset, DataQuality, EvidenceKind, Freshness
from crypto_intel.core.models import (
    Computation,
    Hypothesis,
    Interpretation,
    Observation,
    ProbabilityCalibrationMetadata,
    Provenance,
    ScoreCard,
)


def make_obs(**kwargs) -> Observation:
    defaults = {
        "asset": Asset.BTC, "metric": "price.close", "value": 64000.0, "unit": "USD",
        "timestamp": datetime(2026, 9, 4, 12, 0, tzinfo=UTC),
        "provenance": Provenance(source="Binance", provider="binance_spot",
                                 source_url="https://api.binance.com"),
        "freshness": Freshness.LIVE,
    }
    defaults.update(kwargs)
    return Observation(**defaults)


class TestObservation:
    def test_id_is_deterministic(self):
        """Re-fetching the same datapoint must not create a duplicate."""
        assert make_obs().id == make_obs().id

    def test_id_differs_per_metric(self):
        assert make_obs().id != make_obs(metric="price.open").id

    def test_provenance_is_mandatory(self):
        with pytest.raises(ValidationError):
            Observation(metric="x", value=1, timestamp=datetime.now(UTC))

    def test_naive_timestamp_becomes_utc(self):
        obs = make_obs(timestamp=datetime(2026, 9, 4, 12, 0))
        assert obs.timestamp.tzinfo is not None

    def test_kind_is_fact(self):
        assert make_obs().kind is EvidenceKind.FACT

    def test_numeric_value_none_for_text(self):
        """Text metrics must not silently become 0.0."""
        assert make_obs(value="bullish", unit="text").numeric_value is None

    def test_bool_normalised_to_number(self):
        """Flag metrics (unit='bool') are stored and consumed as 1.0/0.0."""
        assert make_obs(value=True, unit="bool").numeric_value == 1.0
        assert make_obs(value=False, unit="bool").numeric_value == 0.0

    def test_describe_includes_source_and_time(self):
        text = make_obs().describe()
        assert "Binance" in text and "LIVE" in text and "64000" in text

    def test_is_immutable(self):
        """A fact must not be editable after creation."""
        with pytest.raises(ValidationError):
            make_obs().value = 999


class TestEpistemicLevels:
    def test_computation_records_its_formula(self):
        c = Computation(
            name="ma_5d", value=122.0, unit="USD_M", engine="etf",
            formula="mean of the last 5 daily net flows",
            evidence_ids=["obs_a", "obs_b"],
        )
        assert c.kind is EvidenceKind.COMPUTATION
        assert c.quality is DataQuality.DERIVED
        assert c.formula

    def test_interpretation_links_back_to_evidence(self):
        i = Interpretation(
            analyst="etf_analyst", statement="Institutional demand is currently supportive",
            evidence_ids=["cmp_1"],
        )
        assert i.kind is EvidenceKind.INTERPRETATION
        assert i.evidence_ids == ["cmp_1"]

    def test_uncalibrated_numeric_probability_is_rejected(self):
        """Never present an uncalibrated estimate as a statistic."""
        with pytest.raises(ValidationError, match="requires calibrated=true"):
            Hypothesis(
                statement="Could support price",
                probability=55.0,
                calibrated=False,
            )

    def test_calibrated_probability_requires_documented_oos_evaluation(self):
        with pytest.raises(ValidationError, match="require calibration_metadata"):
            Hypothesis(statement="x", probability=55.0, calibrated=True)

        metadata = ProbabilityCalibrationMetadata(
            model_name="hypothesis_logit",
            model_version="1.0",
            target_definition="BTC closes above the observed resistance",
            target_horizon="8-30 days",
            calibration_method="isotonic regression",
            out_of_sample_tested=True,
            out_of_sample_sample_size=180,
            evaluation_metric="Brier score",
            evaluation_score=0.18,
            evaluated_at=datetime(2026, 9, 1, tzinfo=UTC),
            evidence_ids=["eval_hypothesis_logit_2026q3"],
        )
        h = Hypothesis(
            statement="x",
            probability=55.0,
            calibrated=True,
            calibration_metadata=metadata,
        )
        assert "calibr" in h.probability_label.lower()

    def test_probability_may_be_absent(self):
        assert Hypothesis(statement="x").probability_label == "non quantifiee"


class TestScoreCard:
    def test_unavailable_card_carries_zero_weight(self):
        card = ScoreCard.unavailable_card("whale", "UNAVAILABLE - provider not configured")
        assert card.available is False
        assert card.confidence == 0.0
        assert card.freshness is Freshness.UNAVAILABLE
        assert card.evidence_count == 0

    def test_score_bounds_enforced(self):
        with pytest.raises(ValidationError):
            ScoreCard(domain="x", score=150, confidence=50)
        with pytest.raises(ValidationError):
            ScoreCard(domain="x", score=0, confidence=150)

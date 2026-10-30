from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from crypto_intel.analysts.chief import ChiefMarketAnalyst
from crypto_intel.core.enums import Asset, Direction, Horizon, Timeframe
from crypto_intel.core.models import (
    Contradiction,
    Conviction,
    Scenario,
    ScenarioCalibrationMetadata,
)
from crypto_intel.engines.contradictions import ContradictionReport
from crypto_intel.engines.conviction import ConvictionResult


def _conviction() -> ConvictionResult:
    def reading(horizon: Horizon) -> Conviction:
        return Conviction(
            horizon=horizon,
            score=12.5,
            label="SLIGHTLY_BULLISH",
            confidence=48.0,
            direction=Direction.BULLISH,
        )

    return ConvictionResult(
        asset=Asset.BTC,
        short=reading(Horizon.SHORT),
        medium=reading(Horizon.MEDIUM),
        long=reading(Horizon.LONG),
    )


def _calibration(*, out_of_sample_tested: bool = True) -> ScenarioCalibrationMetadata:
    return ScenarioCalibrationMetadata(
        model_name="scenario_logit",
        model_version="1.2.0",
        target_definition="BTC closes above today's measured resistance",
        target_horizon="8-30 days",
        calibration_method="isotonic regression",
        out_of_sample_tested=out_of_sample_tested,
        out_of_sample_sample_size=180,
        evaluation_metric="Brier score",
        evaluation_score=0.18,
        evaluated_at=datetime(2026, 9, 1, tzinfo=UTC),
        evidence_ids=["eval_scenario_logit_2026q3"],
    )


def _base_context(*, with_daily: bool = True) -> dict:
    snapshots = {}
    if with_daily:
        snapshots[Timeframe.D1] = SimpleNamespace(
            has_data=True,
            price=64_000.0,
            levels_support=[SimpleNamespace(price=61_500.0)],
            levels_resistance=[SimpleNamespace(price=66_250.0)],
            volume_state="NORMAL",
        )
    return {
        "snapshots": snapshots,
        "etf": SimpleNamespace(available=False),
        "macro": SimpleNamespace(available=False, upcoming_events=[]),
        "liquidity": SimpleNamespace(available=False),
        "derivatives": SimpleNamespace(available=False),
    }


def test_probability_is_rejected_without_calibration() -> None:
    with pytest.raises(ValidationError, match="numeric probability requires calibrated=true"):
        Scenario(
            name="central",
            label="Central",
            probability=55.0,
            narrative="A properly conditional scenario narrative.",
        )


def test_calibrated_flag_requires_meaningful_metadata() -> None:
    with pytest.raises(ValidationError, match="require calibration_metadata"):
        Scenario(
            name="central",
            label="Central",
            probability=55.0,
            calibrated=True,
            narrative="A properly conditional scenario narrative.",
        )

    with pytest.raises(ValidationError, match="tested out of sample"):
        Scenario(
            name="central",
            label="Central",
            probability=55.0,
            calibrated=True,
            calibration_metadata=_calibration(out_of_sample_tested=False),
            narrative="A properly conditional scenario narrative.",
        )


def test_documented_out_of_sample_probability_is_admitted() -> None:
    scenario = Scenario(
        name="central",
        label="Central",
        probability=55.0,
        calibrated=True,
        calibration_metadata=_calibration(),
        narrative="A properly conditional scenario narrative.",
    )
    assert scenario.probability == 55.0
    assert scenario.probability_label == "55% (calibree)"
    assert scenario.calibration_metadata is not None
    assert scenario.calibration_metadata.evaluated_at.tzinfo is UTC


def test_deterministic_scenarios_have_complete_non_probabilistic_contract() -> None:
    scenarios = ChiefMarketAnalyst()._scenarios(
        Asset.BTC, _conviction(), _base_context()
    )

    assert [item.name for item in scenarios] == ["central", "bull", "bear"]
    for scenario in scenarios:
        assert scenario.probability is None
        assert scenario.calibrated is False
        assert scenario.calibration_metadata is None
        assert scenario.horizon == "8-30 days"
        assert scenario.affected_assets == [Asset.BTC]
        assert scenario.confirmed_evidence
        assert scenario.confirmation_signals
        assert scenario.uncertainties
        assert scenario.prudence_note

        asserted_context = " ".join([scenario.narrative, *scenario.conditions])
        assert "ETF" not in asserted_context
        assert "dollar" not in asserted_context.lower()
        assert "nearest support" not in asserted_context.lower()
        assert "nearest resistance" not in asserted_context.lower()


def test_etf_dollar_and_liquidity_conditions_require_available_inputs() -> None:
    context = _base_context()
    context.update(
        {
            "etf": SimpleNamespace(available=True, latest_total=25.0),
            "macro": SimpleNamespace(
                available=True,
                dollar_trend="STRENGTHENING",
                upcoming_events=[],
            ),
            "liquidity": SimpleNamespace(available=True, regime="CONTRACTION"),
        }
    )

    scenarios = ChiefMarketAnalyst()._scenarios(Asset.BTC, _conviction(), context)
    bull_text = " ".join(scenarios[1].conditions)
    bear_text = " ".join(scenarios[2].conditions)

    assert "ETF" in bull_text
    assert "dollar" in bull_text.lower()
    assert "stablecoin-liquidity" in bull_text
    assert "ETF" in bear_text
    assert "dollar" in bear_text.lower()


def test_contradictions_are_explicit_uncertainties_and_raise_prudence() -> None:
    report = ContradictionReport(
        contradictions=[
            Contradiction(
                description="ETF flows improve while daily structure weakens",
                signals=["ETF up", "structure down"],
                strength=78.0,
            )
        ],
        max_strength=78.0,
        is_high=True,
        summary="High contradiction",
    )
    scenarios = ChiefMarketAnalyst()._scenarios(
        Asset.BTC,
        _conviction(),
        _base_context(),
        report,
    )

    for scenario in scenarios:
        assert any("ETF flows improve" in item for item in scenario.uncertainties)
        assert "High signal contradiction" in scenario.prudence_note


def test_missing_context_does_not_create_placeholder_triggers_or_levels() -> None:
    scenarios = ChiefMarketAnalyst()._scenarios(
        Asset.BTC,
        _conviction(),
        _base_context(with_daily=False),
    )

    for scenario in scenarios:
        assert scenario.conditions == []
        assert scenario.confirmation_signals == []
        assert scenario.key_levels == {}
        assert "underspecified" in scenario.narrative
        assert scenario.invalidation.startswith("Cannot be specified")
        assert "nearest" not in scenario.narrative.lower()

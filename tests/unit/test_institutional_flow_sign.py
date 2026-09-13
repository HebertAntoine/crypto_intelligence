"""Non-regression on the ETF flow sign convention and on regime vs recent window.

The reported symptom was a family shown as POSITIF next to "cumul 5 séances
-288.09 M$". The trace showed the sign convention is correct on both figures:
positive means money entering the funds, and the twenty-session regime was
genuinely positive while the last sessions had genuinely turned negative. What
was wrong is that the engine computed the reversal and then dropped it, so the
positive label travelled to the UI unqualified.

These tests pin the convention and pin that a reversal is always stated.
"""

from datetime import UTC, datetime, timedelta

from crypto_intel.core.enums import Asset
from crypto_intel.engines.future_context import _institutional_summary
from crypto_intel.engines.institutional_flow import (
    FlowReversal,
    InstitutionalFlowEngine,
    InstitutionalFlowState,
)

NOW = datetime(2026, 9, 13, 12, tzinfo=UTC)


def records(values: list[float]) -> list[dict[str, object]]:
    """One fund, one session per day, oldest first."""

    return [
        {
            "date": NOW - timedelta(days=len(values) - index),
            "ticker": "IBIT",
            "flow_musd": value,
            "import_source": "farside",
            "source_url": "https://farside.co.uk/bitcoin-etf-flow-all-data/",
        }
        for index, value in enumerate(values)
    ]


def analyse(values: list[float]):
    return InstitutionalFlowEngine().analyze_records(
        Asset.BTC, records(values), now=NOW
    )


def test_a_positive_record_is_money_entering_the_funds() -> None:
    result = analyse([100.0] * 20)
    assert result.state is InstitutionalFlowState.STRONG_INFLOW
    assert result.regime_total_musd == 2000.0
    assert result.rolling_5_sessions_musd == 500.0


def test_a_negative_record_is_money_leaving_the_funds() -> None:
    result = analyse([-100.0] * 20)
    assert result.state is InstitutionalFlowState.STRONG_OUTFLOW
    assert result.regime_total_musd == -2000.0


def test_the_regime_window_and_the_five_session_window_are_not_the_same() -> None:
    """The reported case: positive over twenty sessions, negative over five."""

    values = [300.0] * 15 + [-60.0] * 5
    result = analyse(values)
    assert result.regime_sessions == 20
    assert result.regime_total_musd == 4200.0
    assert result.rolling_5_sessions_musd == -300.0
    assert result.state is InstitutionalFlowState.INFLOW


def test_a_reversal_is_detected_and_never_silently_dropped() -> None:
    values = [300.0] * 15 + [-60.0] * 5
    result = analyse(values)
    assert result.flow_reversal is FlowReversal.INFLOW_TO_OUTFLOW
    assert result.persistence_direction == "OUTFLOW"
    assert result.persistence_sessions == 5

    summary = _institutional_summary(result, result.state.value)
    assert "entrées nettes sur 20 séances" in summary
    assert "le sens s'est inversé" in summary
    assert "5 séance(s) consécutives de sorties" in summary


def test_a_steady_inflow_summary_carries_no_reversal_wording() -> None:
    summary = _institutional_summary(analyse([100.0] * 20), "INFLOW")
    assert "inversé" not in summary


def test_the_summary_never_pairs_a_label_with_a_window_it_did_not_measure() -> None:
    """The old sentence read "inflow ... -288 M$" with no window named."""

    result = analyse([300.0] * 15 + [-60.0] * 5)
    summary = _institutional_summary(result, result.state.value)
    assert "sur 20 séances" in summary
    assert "5 dernières séances" in summary

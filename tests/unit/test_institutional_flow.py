from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from crypto_intel.core.enums import Asset, Freshness
from crypto_intel.core.models import Observation, Provenance
from crypto_intel.engines.institutional_flow import (
    InstitutionalFlowEngine,
    InstitutionalFlowState,
)

NOW = datetime(2028, 9, 30, tzinfo=UTC)


def _flows(values: list[float], asset: Asset = Asset.BTC) -> list[Observation]:
    provenance = Provenance(
        source="Farside Investors",
        provider="farside",
        source_url="https://farside.co.uk/bitcoin-etf-flow-all-data/",
    )
    start = NOW - timedelta(days=len(values) - 1)
    return [
        Observation(
            asset=asset,
            metric="etf.flow",
            value=value,
            unit="USD_M",
            timestamp=start + timedelta(days=index),
            provenance=provenance,
            freshness=Freshness.TODAY,
            meta={"ticker": "IBIT"},
        )
        for index, value in enumerate(values)
    ]


def test_rolling_windows_use_reported_sessions_not_calendar_fill():
    values = [float(index) for index in range(1, 21)]
    result = InstitutionalFlowEngine().analyze(Asset.BTC, _flows(values), now=NOW)

    assert result.latest_flow_musd == 20
    assert result.rolling_3_sessions_musd == 57
    assert result.rolling_5_sessions_musd == 90
    assert result.rolling_20_sessions_musd == 210
    assert result.acceleration_musd_per_session == pytest.approx(3.0)


def test_one_negative_day_does_not_overwrite_twenty_session_inflow():
    values = [100.0] * 19 + [-50.0]
    result = InstitutionalFlowEngine().analyze(Asset.BTC, _flows(values), now=NOW)

    assert result.latest_flow_musd == -50.0
    assert result.state in {
        InstitutionalFlowState.INFLOW,
        InstitutionalFlowState.STRONG_INFLOW,
    }


def test_reversal_compares_recent_three_with_prior_five():
    values = [-80.0] * 5 + [120.0, 130.0, 140.0]
    result = InstitutionalFlowEngine().analyze(Asset.BTC, _flows(values), now=NOW)

    assert result.reversal is True
    assert result.acceleration_musd_per_session > 0


def test_missing_sol_flow_is_unavailable_not_neutral():
    result = InstitutionalFlowEngine().analyze(Asset.SOL, _flows([1, 2, 3]), now=NOW)

    assert result.available is False
    assert result.state is InstitutionalFlowState.INSUFFICIENT_DATA
    assert "UNAVAILABLE" in result.unavailable_reason


def test_per_fund_rows_are_summed_before_windows():
    rows = _flows([10.0, 20.0, 30.0])
    rows += [
        item.model_copy(update={"value": item.numeric_value / 2, "meta": {"ticker": "FBTC"}})
        for item in rows
    ]
    result = InstitutionalFlowEngine().analyze(Asset.BTC, rows, now=NOW)

    assert result.latest_flow_musd == 45.0
    assert result.rolling_3_sessions_musd == 90.0


def test_persisted_records_keep_provider_provenance_and_runtime_freshness():
    records = [
        {
            "id": f"BTC_IBIT_{index}",
            "date": NOW - timedelta(days=2 - index),
            "ticker": "IBIT",
            "flow_musd": float(index + 1),
            "import_source": "farside",
            "source_url": "https://farside.co.uk/bitcoin-etf-flow-all-data/",
        }
        for index in range(3)
    ]

    result = InstitutionalFlowEngine().analyze_records(Asset.BTC, records, now=NOW)

    assert result.available is True
    assert result.freshness != "UNAVAILABLE"
    assert result.evidence_ids == ["BTC_IBIT_0", "BTC_IBIT_1", "BTC_IBIT_2"]
    assert result.provenance[0]["source"] == "Farside Investors"

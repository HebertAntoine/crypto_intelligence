from datetime import UTC, datetime
from pathlib import Path

from crypto_intel.core.data_integrity import is_production_etf_source
from crypto_intel.core.enums import Asset, Freshness
from crypto_intel.core.models import Observation, Provenance
from crypto_intel.db import repo
from crypto_intel.providers.etf.csv_import import import_csv_file


def _row(source: str, ticker: str) -> dict[str, object]:
    return {
        "date": datetime(2026, 9, 3, tzinfo=UTC),
        "asset": "BTC",
        "ticker": ticker,
        "flow_musd": 100.0,
        "import_source": source,
    }


def test_non_production_names_are_rejected_semantically() -> None:
    for source in (
        "csv:example.csv",
        "csv:market_sample.csv",
        "fixture",
        "mock_etf",
        "test-data",
    ):
        assert is_production_etf_source(source) is False

    # Avoid substring false positives: a legitimate file named "latest" is
    # not a test fixture merely because its spelling contains "test".
    assert is_production_etf_source("csv:latest_verified.csv") is True


def test_example_csv_cannot_be_imported_into_production(tmp_path: Path) -> None:
    path = tmp_path / "example.csv"
    path.write_text(
        "date,asset,ticker,flow_musd\n2026-09-03,BTC,IBIT,500\n",
        encoding="utf-8",
    )

    imported, errors = import_csv_file(path)

    assert imported == 0
    assert errors and "rejected from production" in errors[0]


def test_repository_defence_prevents_example_from_reaching_aggregate() -> None:
    repo.save_etf_flows([_row("csv:example.csv", "BAD"), _row("farside", "GOOD")])

    rows = repo.get_etf_flows(Asset.BTC, days=4000)

    assert any(row["ticker"] == "GOOD" for row in rows)
    assert all(row["ticker"] != "BAD" for row in rows)


def test_purge_removes_only_non_production_rows() -> None:
    # Insert through the ORM boundary to reproduce legacy contamination; the
    # normal repository save path now rejects it.
    from crypto_intel.db.base import ETFFlowRow
    from crypto_intel.db.session import session_scope

    with session_scope() as session:
        session.merge(
            ETFFlowRow(
                id="BTC_MOCK_20260903",
                asset="BTC",
                ticker="MOCK",
                date=datetime(2026, 9, 3, tzinfo=UTC),
                flow_musd=999.0,
                import_source="csv:mock.csv",
            )
        )

    removed = repo.purge_non_production_etf_flows()
    all_rows = repo.get_etf_flows(Asset.BTC, days=4000, production_only=False)

    assert removed == 1
    assert all(row["ticker"] != "MOCK" for row in all_rows)


def test_fixture_row_does_not_discard_real_rows_beside_it() -> None:
    from crypto_intel.engines.analysis_context import _without_synthetic

    timestamp = datetime(2026, 9, 13, tzinfo=UTC)
    real = Observation(
        metric="stablecoin.supply.total",
        value=100.0,
        timestamp=timestamp,
        provenance=Provenance(source="DefiLlama", provider="defillama_stables"),
        freshness=Freshness.LIVE,
    )
    fixture = real.model_copy(
        update={
            "provenance": Provenance(
                source="MOCK FIXTURES (synthetic)", provider="fixtures"
            )
        }
    )

    assert _without_synthetic([fixture, real]) == [real]

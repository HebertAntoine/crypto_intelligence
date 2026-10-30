from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from crypto_intel.core.enums import Freshness
from crypto_intel.core.models import Observation, Provenance
from crypto_intel.db.base import MacroVintageRow
from crypto_intel.db.migrations import existing_columns
from crypto_intel.db.session import session_scope
from crypto_intel.engines.pit_view import DataCache, PointInTimeView
from crypto_intel.history import store
from crypto_intel.settings import get_settings


def _test_database_path() -> Path:
    return Path(get_settings().resolved_database_url.removeprefix("sqlite:///"))


def test_macro_vintage_schema_keeps_versioned_provenance() -> None:
    assert {
        "source",
        "provider",
        "unit",
        "source_url",
        "license_status",
        "meta",
        "release_time",
        "availability",
    } <= existing_columns("macro_vintages")


def test_provider_backfill_keeps_temporal_and_licence_metadata() -> None:
    fetched = datetime(2011, 2, 3, 12, tzinfo=UTC)
    available = datetime(2011, 2, 2, 5, tzinfo=UTC)
    observation = Observation(
        metric="macro.eurusd",
        value=1.365,
        unit="ratio",
        timestamp=datetime(2011, 2, 1, 5, tzinfo=UTC),
        provenance=Provenance(
            source="Twelve Data",
            provider="twelve_data",
            source_url="https://twelvedata.com/markets/EUR/USD",
            fetched_at=fetched,
            license_note="operator confirmed",
        ),
        freshness=Freshness.TODAY,
        meta={
            "series_id": "EUR/USD",
            "available_at": available.isoformat(),
            "publication_time": None,
            "license_status": "OPERATOR_CONFIRMED",
            "revision_number": 0,
        },
    )

    assert store.save_macro_observations([observation]) == 1
    record = next(
        item
        for item in store.load_macro_records("macro.eurusd")
        if item["timestamp"] == observation.timestamp
    )

    assert record["provider"] == "twelve_data"
    assert record["unit"] == "ratio"
    assert record["source_url"] == observation.provenance.source_url
    assert record["series_id"] == "EUR/USD"
    assert record["license_status"] == "OPERATOR_CONFIRMED"
    assert record["release_time"] == available
    assert record["availability"] == "RECONSTRUCTED_PIT"


def test_macro_revision_is_not_projected_before_its_vintage() -> None:
    observed = datetime(2010, 1, 1, tzinfo=UTC)
    released = datetime(2010, 1, 15, tzinfo=UTC)
    revised = datetime(2010, 2, 15, tzinfo=UTC)
    base = {
        "metric": "macro.cpi",
        "timestamp": observed,
        "source": "FRED (St. Louis Fed)",
        "provider": "fred_backfill",
        "unit": "index",
        "series_id": "CPIAUCSL",
        "source_url": "https://fred.stlouisfed.org/series/CPIAUCSL",
        "license_status": "FRED_TERMS",
        "release_time": released,
        "availability": "VINTAGE_AVAILABLE",
    }

    assert store.save_macro_records([{**base, "value": 100.0, "ingested_at": released}]) == 1
    assert store.save_macro_records([{**base, "value": 101.0, "ingested_at": revised}]) == 1

    records = [
        item
        for item in store.load_macro_records("macro.cpi")
        if item["timestamp"] == observed
    ]
    assert [(item["value"], item["revision_number"]) for item in records] == [
        (100.0, 0),
        (101.0, 1),
    ]

    cache = DataCache(_test_database_path())
    before_revision = PointInTimeView(
        cache, datetime(2010, 2, 1, tzinfo=UTC)
    ).latest("macro.cpi")
    after_revision = PointInTimeView(
        cache, datetime(2010, 2, 16, tzinfo=UTC)
    ).latest("macro.cpi")

    assert before_revision is not None and before_revision.value == 100.0
    assert after_revision is not None and after_revision.value == 101.0
    assert after_revision.meta["revision_number"] == 1


def test_macro_revision_keeps_each_vintages_own_provider_and_rights() -> None:
    observed = datetime(2001, 1, 1, tzinfo=UTC)
    released = datetime(2001, 1, 15, tzinfo=UTC)
    revised = datetime(2001, 2, 15, tzinfo=UTC)
    metric = "macro.core_pce"
    old = {
        "metric": metric,
        "timestamp": observed,
        "value": 90.0,
        "source": "Federal Reserve Economic Data archive",
        "provider": "fred_backfill",
        "unit": "index_2017_100",
        "series_id": "PCEPILFE",
        "source_url": "https://fred.stlouisfed.org/series/PCEPILFE",
        "license_status": "FRED_TERMS",
        "meta": {"provenance_version": "archive"},
        "release_time": released,
        "availability": "VINTAGE_AVAILABLE",
        "ingested_at": released,
    }
    new = {
        **old,
        "value": 90.4,
        "source": "Federal Reserve Bank of St. Louis API",
        "provider": "fred_api",
        "source_url": "https://api.stlouisfed.org/fred/series/observations",
        "license_status": "FEDERAL_RESERVE_PUBLIC",
        "meta": {"provenance_version": "api_revision"},
        "release_time": revised,
        "availability": "REVISION_AVAILABLE",
        "ingested_at": revised,
    }

    assert store.save_macro_records([old]) == 1

    # Simulate a database migrated from the schema that had values/vintages
    # but no provenance columns. The old fields must be copied before the
    # current macro_series row is overwritten by the new provider.
    with session_scope() as session:
        first_print = session.execute(
            select(MacroVintageRow).where(
                MacroVintageRow.metric == metric,
                MacroVintageRow.observation_time == observed,
            )
        ).scalar_one()
        for field in (
            "source",
            "provider",
            "unit",
            "source_url",
            "license_status",
            "meta",
            "release_time",
            "availability",
        ):
            setattr(first_print, field, None)

    assert store.save_macro_records([new]) == 1

    records = [
        item
        for item in store.load_macro_records(metric)
        if item["timestamp"] == observed
    ]
    assert [item["source"] for item in records] == [old["source"], new["source"]]
    assert [item["provider"] for item in records] == [old["provider"], new["provider"]]
    assert [item["source_url"] for item in records] == [
        old["source_url"],
        new["source_url"],
    ]
    assert [item["license_status"] for item in records] == [
        old["license_status"],
        new["license_status"],
    ]
    assert [item["meta"]["provenance_version"] for item in records] == [
        "archive",
        "api_revision",
    ]
    assert [item["ingested_at"] for item in records] == [released, revised]
    assert [item["release_time"] for item in records] == [released, revised]
    assert [item["availability"] for item in records] == [
        "VINTAGE_AVAILABLE",
        "REVISION_AVAILABLE",
    ]

    cache = DataCache(_test_database_path())
    before = PointInTimeView(cache, datetime(2001, 2, 1, tzinfo=UTC)).latest(metric)
    after = PointInTimeView(cache, datetime(2001, 2, 16, tzinfo=UTC)).latest(metric)

    assert before is not None
    assert before.value == 90.0
    assert before.source == old["source"]
    assert before.meta["provider"] == old["provider"]
    assert before.meta["license_status"] == old["license_status"]
    assert before.meta["provenance_version"] == "archive"
    assert after is not None
    assert after.value == 90.4
    assert after.source == new["source"]
    assert after.meta["provider"] == new["provider"]
    assert after.meta["license_status"] == new["license_status"]
    assert after.meta["provenance_version"] == "api_revision"

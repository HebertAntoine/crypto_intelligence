"""Regression tests for conservative point-in-time visibility."""

import sqlite3
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from crypto_intel.core.enums import Asset, Timeframe
from crypto_intel.core.models import Candle
from crypto_intel.engines.pit_view import (
    TIMEFRAME_SPAN,
    DataCache,
    PointInTimeView,
)
from crypto_intel.history import store


def _candle_frame(*timestamps: datetime) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": [100.0 + i for i in range(len(timestamps))],
            "high": [102.0 + i for i in range(len(timestamps))],
            "low": [99.0 + i for i in range(len(timestamps))],
            "close": [101.0 + i for i in range(len(timestamps))],
            "volume": [10.0 + i for i in range(len(timestamps))],
        },
        index=pd.DatetimeIndex(timestamps, name="timestamp"),
    )


@pytest.mark.parametrize("timeframe", list(Timeframe))
def test_every_timeframe_excludes_forming_bar_until_exact_close(
    tmp_path,
    timeframe: Timeframe,
) -> None:
    span = TIMEFRAME_SPAN[timeframe]
    current_open = datetime(2026, 10, 19, tzinfo=UTC)
    previous_open = current_open - span
    cache = DataCache(tmp_path / "no-database-needed.db")
    cache._candles[(Asset.BTC.value, timeframe.value)] = _candle_frame(
        previous_open,
        current_open,
    )

    just_before_close = PointInTimeView(
        cache,
        current_open + span - timedelta(microseconds=1),
    ).candles(Asset.BTC.value, timeframe)
    at_close = PointInTimeView(
        cache,
        current_open + span,
    ).candles(Asset.BTC.value, timeframe)

    assert list(just_before_close.index) == [pd.Timestamp(previous_open)]
    assert list(at_close.index) == [
        pd.Timestamp(previous_open),
        pd.Timestamp(current_open),
    ]


def test_candle_close_boundary_is_compared_in_utc_across_dst(tmp_path) -> None:
    """The European DST jump must not make an hourly bar close early or late."""

    opened_at = datetime(2026, 3, 29, 0, 0, tzinfo=UTC)
    closes_at = opened_at + timedelta(hours=1)
    paris = ZoneInfo("Europe/Paris")
    cache = DataCache(tmp_path / "no-database-needed.db")
    cache._candles[(Asset.BTC.value, Timeframe.H1.value)] = _candle_frame(opened_at)

    before = PointInTimeView(
        cache,
        (closes_at - timedelta(microseconds=1)).astimezone(paris),
    )
    exact = PointInTimeView(cache, closes_at.astimezone(paris))

    assert before.candles(Asset.BTC.value, Timeframe.H1).empty
    assert len(exact.candles(Asset.BTC.value, Timeframe.H1)) == 1
    assert exact.as_of == closes_at


def test_store_updates_forming_bar_but_never_loads_it_before_close() -> None:
    timeframe = Timeframe.M15
    opened_at = datetime(2042, 6, 2, 12, 0, tzinfo=UTC)
    previous_open = opened_at - timedelta(minutes=15)

    def candle(timestamp: datetime, close: float) -> Candle:
        return Candle(
            timestamp=timestamp,
            open=100.0,
            high=max(101.0, close),
            low=99.0,
            close=close,
            volume=10.0,
        )

    store.save_candles(
        Asset.GLOBAL,
        timeframe,
        [candle(previous_open, 100.0)],
        source="closed-source",
    )
    store.save_candles(
        Asset.GLOBAL,
        timeframe,
        [candle(opened_at, 101.0)],
        source="forming-source-v1",
    )
    # A subsequent tick replaces the same stored bar rather than duplicating
    # it, but still cannot make it visible before its scheduled close.
    assert store.save_candles(
        Asset.GLOBAL,
        timeframe,
        [candle(opened_at, 105.0)],
        source="forming-source-v2",
    ) == 0

    just_before = opened_at + timedelta(minutes=15, microseconds=-1)
    hidden = store.load_candles(
        Asset.GLOBAL,
        timeframe,
        start=previous_open,
        as_of=just_before,
    )
    visible = store.load_candles(
        Asset.GLOBAL,
        timeframe,
        start=previous_open,
        as_of=opened_at + timedelta(minutes=15),
    )

    assert list(hidden.index) == [pd.Timestamp(previous_open)]
    assert list(visible.index) == [
        pd.Timestamp(previous_open),
        pd.Timestamp(opened_at),
    ]
    assert visible.iloc[-1]["close"] == 105.0

    hidden_metadata = store.candle_metadata(
        Asset.GLOBAL,
        timeframe,
        as_of=just_before,
    )
    visible_metadata = store.candle_metadata(
        Asset.GLOBAL,
        timeframe,
        as_of=opened_at + timedelta(minutes=15),
    )
    assert hidden_metadata["end"] == previous_open
    assert hidden_metadata["source"] == "closed-source"
    assert visible_metadata["end"] == opened_at
    assert visible_metadata["source"] == "forming-source-v2"


def test_historical_end_is_the_visibility_time_when_as_of_is_omitted() -> None:
    timeframe = Timeframe.M15
    opened_at = datetime(2043, 7, 3, 9, 0, tzinfo=UTC)
    previous_open = opened_at - timedelta(minutes=15)
    candles = [
        Candle(
            timestamp=stamp,
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.5,
            volume=10.0,
        )
        for stamp in (previous_open, opened_at)
    ]
    store.save_candles(Asset.GLOBAL, timeframe, candles, source="historical-end-test")

    frame = store.load_candles(
        Asset.GLOBAL,
        timeframe,
        start=previous_open,
        end=opened_at + timedelta(minutes=5),
    )

    assert list(frame.index) == [pd.Timestamp(previous_open)]


def test_missing_publication_time_falls_back_to_collection_time(tmp_path) -> None:
    database = tmp_path / "observations.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TABLE observations (
                asset TEXT,
                metric TEXT NOT NULL,
                value_num REAL,
                timestamp TEXT NOT NULL,
                fetched_at TEXT,
                source TEXT NOT NULL,
                provider TEXT,
                unit TEXT,
                source_url TEXT,
                meta TEXT
            )
            """
        )
        connection.execute(
            """
            INSERT INTO observations (
                asset, metric, value_num, timestamp, fetched_at,
                source, provider, unit, source_url, meta
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                None,
                "macro.release_without_publication_time",
                101.2,
                "2026-08-01T00:00:00+00:00",
                "2026-09-15T13:30:00+00:00",
                "FRED",
                "fred",
                "index",
                "https://fred.stlouisfed.org/series/TEST",
                "{}",
            ),
        )

    cache = DataCache(database)
    before_collection = PointInTimeView(
        cache, datetime(2026, 9, 15, 13, 29, tzinfo=UTC)
    ).latest("macro.release_without_publication_time")
    after_collection = PointInTimeView(
        cache, datetime(2026, 9, 15, 13, 31, tzinfo=UTC)
    ).latest("macro.release_without_publication_time")

    assert before_collection is None
    assert after_collection is not None
    assert after_collection.timestamp == datetime(2026, 8, 1, tzinfo=UTC)
    assert after_collection.available_at == datetime(2026, 9, 15, 13, 30, tzinfo=UTC)
    assert after_collection.meta["availability_basis"] == "fetched_at_fallback"
    assert "available_at" not in after_collection.meta


def test_retained_rows_are_filtered_by_current_source_rights(tmp_path, monkeypatch) -> None:
    from crypto_intel.settings import reload_settings

    database = tmp_path / "licensed-observations.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TABLE observations (
                asset TEXT,
                metric TEXT NOT NULL,
                value_num REAL,
                timestamp TEXT NOT NULL,
                fetched_at TEXT,
                source TEXT NOT NULL,
                provider TEXT,
                unit TEXT,
                source_url TEXT,
                meta TEXT
            )
            """
        )
        rows = [
            ("macro.sp500", 5000.0, "Yahoo Finance", "yahoo_finance", "{}"),
            (
                "macro.sp500",
                5100.0,
                "Twelve Data",
                "twelve_data",
                '{"available_at":"2026-10-25T00:00:00+00:00"}',
            ),
            (
                "macro.hy_spread",
                3.2,
                "FRED",
                "fred_public_csv",
                '{"series_id":"BAMLH0A0HYM2","available_at":"2026-10-25T00:00:00+00:00"}',
            ),
            (
                "macro.fed_funds_rate",
                4.75,
                "Federal Reserve Bank of New York",
                "nyfed",
                '{"available_at":"2026-10-25T00:00:00+00:00"}',
            ),
            (
                "market.total_cap",
                2_500_000_000_000.0,
                "CoinGecko",
                "coingecko",
                '{"available_at":"2026-10-25T00:00:00+00:00",'
                '"license_status":"OPERATOR_CONFIRMED"}',
            ),
        ]
        connection.executemany(
            """
            INSERT INTO observations (
                asset, metric, value_num, timestamp, fetched_at, source,
                provider, unit, source_url, meta
            ) VALUES (NULL, ?, ?, '2026-10-24T00:00:00+00:00',
                      '2026-10-25T00:00:00+00:00', ?, ?, 'index', NULL, ?)
            """,
            rows,
        )

    monkeypatch.setenv("TWELVE_DATA_API_KEY", "")
    monkeypatch.setenv("TWELVE_DATA_REDISTRIBUTION_AUTHORIZED", "false")
    monkeypatch.setenv("FRED_THIRD_PARTY_REDISTRIBUTION_AUTHORIZED", "false")
    monkeypatch.setenv("FRED_CONTENT_USE_AUTHORIZED", "false")
    monkeypatch.setenv("COINGECKO_COMMERCIAL_USE_AUTHORIZED", "false")
    monkeypatch.setenv("COINGECKO_API_KEY", "")
    monkeypatch.setenv("COINGECKO_ATTRIBUTION_CONFIGURED", "false")
    reload_settings()
    try:
        cutoff = datetime(2026, 10, 26, tzinfo=UTC)
        restricted = PointInTimeView(DataCache(database), cutoff)
        assert restricted.points("macro.sp500") == []
        assert restricted.points("macro.hy_spread") == []
        assert restricted.points("market.total_cap") == []
        assert restricted.latest("macro.fed_funds_rate") is not None

        monkeypatch.setenv("TWELVE_DATA_API_KEY", "licensed-key")
        monkeypatch.setenv("TWELVE_DATA_REDISTRIBUTION_AUTHORIZED", "true")
        monkeypatch.setenv("FRED_THIRD_PARTY_REDISTRIBUTION_AUTHORIZED", "true")
        monkeypatch.setenv("FRED_CONTENT_USE_AUTHORIZED", "true")
        monkeypatch.setenv("COINGECKO_COMMERCIAL_USE_AUTHORIZED", "true")
        monkeypatch.setenv("COINGECKO_API_KEY", "paid-key")
        monkeypatch.setenv("COINGECKO_ATTRIBUTION_CONFIGURED", "true")
        reload_settings()
        authorized = PointInTimeView(DataCache(database), cutoff)
        assert [point.value for point in authorized.points("macro.sp500")] == [5100.0]
        assert [point.value for point in authorized.points("macro.hy_spread")] == [3.2]
        assert [point.value for point in authorized.points("market.total_cap")] == [
            2_500_000_000_000.0
        ]
    finally:
        monkeypatch.delenv("TWELVE_DATA_API_KEY", raising=False)
        monkeypatch.delenv("TWELVE_DATA_REDISTRIBUTION_AUTHORIZED", raising=False)
        monkeypatch.delenv("FRED_THIRD_PARTY_REDISTRIBUTION_AUTHORIZED", raising=False)
        monkeypatch.delenv("FRED_CONTENT_USE_AUTHORIZED", raising=False)
        monkeypatch.delenv("COINGECKO_COMMERCIAL_USE_AUTHORIZED", raising=False)
        monkeypatch.delenv("COINGECKO_API_KEY", raising=False)
        monkeypatch.delenv("COINGECKO_ATTRIBUTION_CONFIGURED", raising=False)
        reload_settings()

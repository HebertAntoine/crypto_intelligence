"""Offline contract tests for the chart's Binance top-up path."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pandas as pd
import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.parametrize(
    ("asset_name", "binance_symbol"),
    [("BTC", "BTCUSDT"), ("ETH", "ETHUSDT"), ("SOL", "SOLUSDT")],
)
@pytest.mark.parametrize(
    ("timeframe_name", "binance_interval"),
    [("15m", "15m"), ("1h", "1h"), ("4h", "4h"), ("1d", "1d"), ("1w", "1w")],
)
async def test_recent_refresh_supports_every_chart_pair_and_interval(
    monkeypatch,
    asset_name: str,
    binance_symbol: str,
    timeframe_name: str,
    binance_interval: str,
):
    """The test replaces the network and database boundaries, never Binance data."""
    from crypto_intel.core.enums import Asset, Timeframe
    from crypto_intel.history import backfill

    requested: dict = {}
    opened_at = datetime(2026, 9, 8, 20, 0, tzinfo=UTC)
    row = [
        int(opened_at.timestamp() * 1000),
        "100.0",
        "102.0",
        "99.0",
        "101.0",
        "12.5",
    ]

    class OfflineHTTP:
        async def get_json(self, url, **kwargs):
            requested.update(url=url, **kwargs)
            return SimpleNamespace(ok=True, data=[row])

    saved: dict = {}

    def save_candles(asset, timeframe, candles, source=""):
        saved.update(
            asset=asset,
            timeframe=timeframe,
            candles=candles,
            source=source,
        )
        return len(candles)

    monkeypatch.setattr(backfill, "get_settings", lambda: SimpleNamespace(mock_mode=False))
    monkeypatch.setattr(backfill, "get_http", lambda: OfflineHTTP())
    monkeypatch.setattr(backfill.store, "save_candles", save_candles)
    monkeypatch.setattr(
        backfill.store,
        "candle_coverage",
        lambda *_args: {"rows": 1, "start": opened_at, "end": opened_at, "days": 0},
    )
    monkeypatch.setattr(backfill.store, "record_backfill", lambda **_kwargs: None)

    asset = Asset(asset_name)
    timeframe = Timeframe(timeframe_name)
    result = await backfill.refresh_recent_ohlcv(asset, timeframe, limit=400)

    assert result["ok"] is True
    assert result["source"] == "binance"
    assert requested["url"].endswith("/api/v3/klines")
    assert requested["params"] == {
        "symbol": binance_symbol,
        "interval": binance_interval,
        "limit": 400,
    }
    assert requested["cache_ttl"] == 0
    assert requested["retries"] == 0
    assert saved["asset"] is asset
    assert saved["timeframe"] is timeframe
    assert saved["source"] == "binance"
    assert saved["candles"][0].timestamp == opened_at


async def test_chart_refresh_has_a_real_wall_clock_timeout(monkeypatch):
    from crypto_intel.api import routes_lot2
    from crypto_intel.core.enums import Asset, Timeframe

    monkeypatch.setattr(
        routes_lot2,
        "get_settings",
        lambda: SimpleNamespace(mock_mode=False),
    )
    monkeypatch.setattr(routes_lot2, "_CHART_REFRESH_TIMEOUT_SECONDS", 0.01)

    cancelled = asyncio.Event()

    async def never_returns(*_args, **_kwargs):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    monkeypatch.setattr(
        routes_lot2.backfill_module,
        "refresh_recent_ohlcv",
        never_returns,
    )

    result = await routes_lot2._refresh_chart_history(Asset.BTC, Timeframe.M15)

    assert result["status"] == "timeout"
    assert result["attempted"] is True
    assert result["source"] == "binance"
    assert cancelled.is_set(), "the timed-out request coroutine was left running"


async def test_chart_route_serves_local_rows_after_refresh_failure(monkeypatch):
    from crypto_intel.api import routes_lot2
    from crypto_intel.structure import history_scan

    end = datetime.now(UTC).replace(second=0, microsecond=0)
    index = pd.date_range(end=end, periods=80, freq="15min", tz=UTC)
    values = [100.0 + number for number in range(len(index))]
    frame = pd.DataFrame(
        {
            "open": values,
            "high": [value + 2 for value in values],
            "low": [value - 2 for value in values],
            "close": [value + 1 for value in values],
            "volume": [10.0] * len(index),
        },
        index=index,
    )

    async def offline(*_args, **_kwargs):
        raise OSError("offline")

    monkeypatch.setattr(
        routes_lot2,
        "get_settings",
        lambda: SimpleNamespace(mock_mode=False),
    )
    monkeypatch.setattr(routes_lot2.backfill_module, "refresh_recent_ohlcv", offline)
    monkeypatch.setattr(routes_lot2.store, "load_candles", lambda *_args: frame)
    monkeypatch.setattr(
        routes_lot2.store,
        "candle_metadata",
        lambda *_args: {
            "rows": len(frame),
            "start": frame.index[0].to_pydatetime(),
            "end": frame.index[-1].to_pydatetime(),
            "source": "binance",
            "sources": ["binance"],
        },
    )
    monkeypatch.setattr(routes_lot2, "_chart_markers", lambda *_args: [])
    monkeypatch.setattr(history_scan, "scan_cached", lambda *_args: [])

    from crypto_intel.main import create_app

    async with AsyncClient(
        transport=ASGITransport(app=create_app()),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/chart/BTC",
            params={
                "timeframe": "15m",
                "period": "7d",
                "indicators": "",
                "figures_bars": 80,
            },
        )

    assert response.status_code == 200
    body = response.json()

    assert body["available"] is True
    assert len(body["candles"]) == len(frame)
    assert body["refresh_status"] == "failed"
    assert body["fallback_used"] is True


def test_fallback_metadata_describes_stored_rows_not_the_failed_venue(monkeypatch):
    from crypto_intel.api import routes_lot2
    from crypto_intel.core.enums import Asset, Timeframe

    old = datetime.now(UTC) - timedelta(days=2)
    monkeypatch.setattr(
        routes_lot2.store,
        "candle_metadata",
        lambda *_args: {
            "rows": 250,
            "start": old - timedelta(days=10),
            "end": old,
            "source": "kraken",
            "sources": ["kraken"],
        },
    )

    metadata = routes_lot2._chart_market_metadata(
        Asset.ETH,
        Timeframe.M15,
        {
            "attempted": True,
            "status": "failed",
            "error": "network unavailable",
            "source": "binance",
            "fetched": 0,
            "new_rows": 0,
        },
    )

    assert metadata["exchange"] == "KRAKEN"
    assert metadata["source"] == "kraken"
    assert metadata["refresh_exchange"] == "BINANCE"
    assert metadata["refresh_source"] == "binance"
    assert metadata["storage_origin"] == "local_database"
    assert metadata["fallback_used"] is True
    assert metadata["freshness"] == "STALE"
    assert metadata["is_stale"] is True
    assert metadata["age_seconds"] >= 2 * 24 * 60 * 60


async def test_scheduler_tops_up_all_assets_on_all_chart_timeframes(monkeypatch):
    from crypto_intel import scheduler
    from crypto_intel.core.enums import Asset, Timeframe
    from crypto_intel.history import backfill

    calls: list[tuple[Asset, Timeframe, int]] = []

    async def refresh(asset: Asset, timeframe: Timeframe, limit: int):
        calls.append((asset, timeframe, limit))
        return {"ok": True, "status": "OK", "error": None}

    monkeypatch.setattr(backfill, "refresh_recent_ohlcv", refresh)

    await scheduler.job_ohlcv_sync()

    expected = {
        (asset, timeframe, 400)
        for asset in Asset.tradables()
        for timeframe in Timeframe
    }
    assert set(calls) == expected
    assert len(calls) == 15
    state = scheduler.scheduler_state()["runs"]["ohlcv_sync"]
    assert state["ok"] is True


async def test_scheduler_records_provider_failures_without_raising(monkeypatch):
    from crypto_intel import scheduler
    from crypto_intel.history import backfill

    async def unavailable(*_args, **_kwargs):
        return {
            "ok": False,
            "status": "NETWORK_ERROR",
            "error": "offline",
        }

    monkeypatch.setattr(backfill, "refresh_recent_ohlcv", unavailable)

    await scheduler.job_ohlcv_sync()

    state = scheduler.scheduler_state()["runs"]["ohlcv_sync"]
    assert state["ok"] is False
    assert "offline" in state["detail"]

"""On-demand chart refresh and market-data provenance.

These tests are deliberately offline.  Production mode means that the chart
route *tries* the bounded Binance refresh; the network boundary itself is
always replaced by a deterministic coroutine.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pandas as pd
import pytest
from fastapi.testclient import TestClient

os.environ["MOCK_MODE"] = "true"
os.environ["LLM_PROVIDER"] = "none"


@pytest.fixture(scope="module")
def client():
    from crypto_intel.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture
def chart_history() -> pd.DataFrame:
    """A real-shaped local series which remains usable when refresh fails."""
    end = datetime.now(UTC).replace(second=0, microsecond=0)
    index = pd.DatetimeIndex(
        [end - timedelta(minutes=15 * i) for i in reversed(range(320))],
        name="timestamp",
    )
    closes = [60_000.0 + i * 4.0 for i in range(len(index))]
    return pd.DataFrame(
        {
            "open": [value - 2.0 for value in closes],
            "high": [value + 8.0 for value in closes],
            "low": [value - 9.0 for value in closes],
            "close": closes,
            "volume": [100.0 + i for i in range(len(index))],
        },
        index=index,
    )


def _patch_local_history(monkeypatch, chart_history: pd.DataFrame) -> None:
    from crypto_intel.api import routes_lot2

    monkeypatch.setattr(routes_lot2.store, "load_candles", lambda *_args, **_kwargs: chart_history)
    monkeypatch.setattr(routes_lot2, "_chart_markers", lambda *_args, **_kwargs: [])

    # The endpoint obtains source names independently of the numeric frame, so
    # make that storage boundary deterministic as well.
    monkeypatch.setattr(
        routes_lot2.store,
        "candle_metadata",
        lambda *_args, **_kwargs: {
            "rows": len(chart_history),
            "start": chart_history.index[0],
            "end": chart_history.index[-1],
            "source": "binance",
            "sources": ["binance"],
        },
    )


def _set_mode(monkeypatch, *, mock_mode: bool) -> None:
    from crypto_intel.api import routes_lot2

    monkeypatch.setattr(
        routes_lot2,
        "get_settings",
        lambda: SimpleNamespace(mock_mode=mock_mode),
    )


class TestChartOnDemandRefresh:
    def test_production_get_attempts_one_bounded_recent_refresh(
        self, client, monkeypatch, chart_history
    ):
        from crypto_intel.api import routes_lot2
        from crypto_intel.core.enums import Asset, Timeframe

        _patch_local_history(monkeypatch, chart_history)
        _set_mode(monkeypatch, mock_mode=False)
        calls: list[tuple[tuple, dict]] = []

        async def refresh(*args, **kwargs):
            calls.append((args, kwargs))
            return {
                "ok": True,
                "status": "OK",
                "error": None,
                "source": "binance",
                "fetched": 7,
                "new_rows": 2,
                "last_candle_time": chart_history.index[-1],
            }

        monkeypatch.setattr(routes_lot2.backfill_module, "refresh_recent_ohlcv", refresh)

        response = client.get("/api/chart/BTC?timeframe=15m&period=7d")

        assert response.status_code == 200
        body = response.json()
        assert len(calls) == 1
        args, _kwargs = calls[0]
        assert args[:2] == (Asset.BTC, Timeframe.M15)
        assert body["available"] is True
        assert body["refresh_attempted"] is True
        assert body["refresh_status"] == "refreshed"
        assert body["refresh_fetched"] == 7
        assert body["refresh_new_rows"] == 2
        assert not body["refresh_error"]

    @pytest.mark.parametrize(
        ("failure", "expected_status"),
        [
            (TimeoutError("Binance took too long"), "timeout"),
            (RuntimeError("Binance unavailable"), "failed"),
        ],
    )
    def test_refresh_failure_never_hides_stored_candles(
        self, client, monkeypatch, chart_history, failure, expected_status
    ):
        from crypto_intel.api import routes_lot2

        _patch_local_history(monkeypatch, chart_history)
        _set_mode(monkeypatch, mock_mode=False)

        async def refresh(*_args, **_kwargs):
            raise failure

        monkeypatch.setattr(routes_lot2.backfill_module, "refresh_recent_ohlcv", refresh)

        response = client.get("/api/chart/ETH?timeframe=1h&period=7d")

        assert response.status_code == 200
        body = response.json()
        assert body["available"] is True
        assert body["candles"], "a provider failure must not discard valid stored history"
        assert body["refresh_attempted"] is True
        assert body["refresh_status"] == expected_status
        assert body["refresh_error"]

    def test_mock_mode_never_crosses_the_network_boundary(
        self, client, monkeypatch, chart_history
    ):
        from crypto_intel.api import routes_lot2

        _patch_local_history(monkeypatch, chart_history)
        _set_mode(monkeypatch, mock_mode=True)

        async def forbidden(*_args, **_kwargs):
            raise AssertionError("MOCK_MODE must not invoke the Binance refresh")

        monkeypatch.setattr(routes_lot2.backfill_module, "refresh_recent_ohlcv", forbidden)

        response = client.get("/api/chart/SOL?timeframe=4h&period=30d")

        assert response.status_code == 200
        body = response.json()
        assert body["available"] is True
        assert body["refresh_attempted"] is False
        assert body["refresh_status"] == "skipped_mock"
        assert body["refresh_fetched"] == 0
        assert body["refresh_new_rows"] == 0
        assert not body["refresh_error"]

    def test_zero_fetched_bars_is_reported_as_no_data(
        self, client, monkeypatch, chart_history
    ):
        from crypto_intel.api import routes_lot2

        _patch_local_history(monkeypatch, chart_history)
        _set_mode(monkeypatch, mock_mode=False)

        async def refresh(*_args, **_kwargs):
            return {
                "ok": False,
                "status": "NO_DATA",
                "error": "Binance returned no OHLCV rows.",
                "source": "binance",
                "fetched": 0,
                "new_rows": 0,
            }

        monkeypatch.setattr(routes_lot2.backfill_module, "refresh_recent_ohlcv", refresh)

        body = client.get("/api/chart/BTC?timeframe=1d&period=3m").json()

        assert body["available"] is True
        assert body["refresh_attempted"] is True
        assert body["refresh_status"] == "no_data"
        assert body["refresh_fetched"] == 0
        assert body["refresh_new_rows"] == 0


class TestChartMarketMetadata:
    def test_response_identifies_venue_pair_source_and_observation_time(
        self, client, monkeypatch, chart_history
    ):
        from crypto_intel.api import routes_lot2

        _patch_local_history(monkeypatch, chart_history)
        _set_mode(monkeypatch, mock_mode=True)

        async def forbidden(*_args, **_kwargs):
            raise AssertionError("no refresh is allowed in MOCK_MODE")

        monkeypatch.setattr(routes_lot2.backfill_module, "refresh_recent_ohlcv", forbidden)

        body = client.get("/api/chart/BTC?timeframe=15m&period=7d").json()

        assert body["exchange"].lower() == "binance"
        assert body["symbol"] == "BTCUSDT"
        assert body["pair"] == "BTC/USDT"
        assert body["quote"] == "USDT"
        assert "binance" in body["source"].lower()
        assert any("binance" in source.lower() for source in body["sources"])

        generated_at = datetime.fromisoformat(body["generated_at"])
        as_of = datetime.fromisoformat(body["as_of"])
        last_candle = datetime.fromisoformat(body["last_candle_time"])
        assert generated_at.tzinfo is not None
        assert as_of.tzinfo is not None
        assert last_candle.tzinfo is not None
        assert as_of == last_candle == chart_history.index[-1].to_pydatetime()

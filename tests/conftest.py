"""Test fixtures. Everything here runs offline - no network, no API key."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

os.environ.setdefault("MOCK_MODE", "true")
os.environ.setdefault("LLM_PROVIDER", "none")


@pytest.fixture(scope="session", autouse=True)
def _temp_database(tmp_path_factory):
    """Point every test at a throwaway SQLite file, never the real one."""
    db_path = tmp_path_factory.mktemp("db") / "test.db"
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"

    from crypto_intel.db.session import init_db, reset_engine
    from crypto_intel.settings import reload_settings

    reload_settings()
    reset_engine()
    init_db()
    yield
    reset_engine()


@pytest.fixture
def trending_up_df() -> pd.DataFrame:
    """A clean uptrend - indicators must read it as bullish."""
    n = 300
    base = 100.0
    rows = []
    start = datetime(2026, 1, 1, tzinfo=UTC)
    for i in range(n):
        price = base * (1.0 + i * 0.004)
        rows.append({
            "open": price * 0.998, "high": price * 1.012, "low": price * 0.99,
            "close": price, "volume": 1000 + (i % 7) * 40,
        })
    return pd.DataFrame(rows, index=pd.DatetimeIndex([start + timedelta(days=i) for i in range(n)]))


@pytest.fixture
def ranging_df() -> pd.DataFrame:
    """Sideways chop - must NOT be labelled a trend."""
    import math

    n = 300
    rows = []
    start = datetime(2026, 1, 1, tzinfo=UTC)
    for i in range(n):
        price = 100.0 + math.sin(i / 6.0) * 2.0
        rows.append({
            "open": price, "high": price * 1.006, "low": price * 0.994,
            "close": price, "volume": 1000,
        })
    return pd.DataFrame(rows, index=pd.DatetimeIndex([start + timedelta(days=i) for i in range(n)]))


@pytest.fixture
def wilder_closes() -> list[float]:
    """Wilder's own RSI reference series from 'New Concepts in Technical Trading'."""
    return [
        44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08,
        45.89, 46.03, 45.61, 46.28, 46.28, 46.00, 46.03, 46.41, 46.22, 45.64,
    ]


@pytest.fixture
def sample_series(trending_up_df):
    from crypto_intel.core.enums import Asset, Freshness, Timeframe
    from crypto_intel.core.models import Candle, OHLCVSeries, Provenance

    candles = [
        Candle(timestamp=ts, open=r.open, high=r.high, low=r.low, close=r.close, volume=r.volume)
        for ts, r in trending_up_df.iterrows()
    ]
    return OHLCVSeries(
        asset=Asset.BTC, timeframe=Timeframe.D1, candles=candles,
        provenance=Provenance(source="test", provider="test"),
        freshness=Freshness.LIVE,
    )


@pytest.fixture
def etf_observations():
    """Five days of ETF flows, accelerating upward."""
    from crypto_intel.core.enums import Asset, Freshness
    from crypto_intel.core.models import Observation, Provenance

    prov = Provenance(source="test", provider="test_etf")
    now = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    flows = [
        (4, "IBIT", 50.0), (4, "FBTC", 20.0),
        (3, "IBIT", 80.0), (3, "FBTC", 30.0),
        (2, "IBIT", 120.0), (2, "FBTC", 40.0),
        (1, "IBIT", 200.0), (1, "FBTC", 60.0),
        (0, "IBIT", 400.0), (0, "FBTC", 100.0),
    ]
    return [
        Observation(
            asset=Asset.BTC, metric="etf.flow", value=v, unit="USD_M",
            timestamp=now - timedelta(days=d), provenance=prov,
            freshness=Freshness.TODAY, meta={"ticker": t},
        )
        for d, t, v in flows
    ]


@pytest.fixture
def realistic_history() -> pd.DataFrame:
    """A multi-year daily series with regime changes, drawdowns and volatility
    clustering - closer to a real market than a random walk, so event studies
    and calibration are exercised against something with structure."""
    import numpy as np

    rng = np.random.default_rng(20260905)
    n = 1200
    start = datetime(2023, 1, 1, tzinfo=UTC)

    prices = [100.0]
    volatility = 0.02
    for i in range(1, n):
        # Regime blocks: trend up, chop, trend down, recover.
        block = i // 300
        drift = {0: 0.0016, 1: 0.0000, 2: -0.0014, 3: 0.0011}.get(block, 0.0005)
        # Volatility clusters rather than being constant.
        volatility = max(0.008, min(0.06, volatility * 0.94 + abs(rng.normal(0, 0.006))))
        prices.append(max(1.0, prices[-1] * (1.0 + drift + rng.normal(0, volatility))))

    closes = np.array(prices)
    highs = closes * (1 + np.abs(rng.normal(0, 0.008, n)))
    lows = closes * (1 - np.abs(rng.normal(0, 0.008, n)))
    opens = np.concatenate([[closes[0]], closes[:-1]])
    volumes = np.abs(rng.normal(1000, 300, n)) * (1 + np.abs(rng.normal(0, 0.5, n)))

    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes, "volume": volumes},
        index=pd.DatetimeIndex(
            [start + timedelta(days=i) for i in range(n)], name="timestamp"
        ),
    )


@pytest.fixture
def realistic_etf_flows(realistic_history) -> pd.Series:
    """Daily ETF flows loosely tied to recent returns, as real flows are.

    Deliberately NOT independent of price: real flows chase performance, which
    is exactly the confound the lag study has to see through.
    """
    import numpy as np

    rng = np.random.default_rng(7)
    closes = realistic_history["close"]
    returns = closes.pct_change().fillna(0.0)
    # Flows react to the PAST few days of return, plus noise.
    reactive = returns.rolling(3, min_periods=1).mean() * 8000
    noise = rng.normal(0, 90, len(closes))
    flows = pd.Series(reactive.to_numpy() + noise, index=closes.index, name="etf_net_flow")
    return flows.iloc[-700:]


@pytest.fixture(scope="session")
def seeded_market_history():
    """Enough real-shaped history for every engine to produce an answer.

    Guards that read a real payload are only guards when there is something in
    it. Without this, `/today` returned INSUFFICIENT_DATA and a test asserting
    "no raw enum reaches the user" passed by having almost no text to check —
    it only started failing when an unrelated module happened to run first and
    leave rows behind.
    """
    from crypto_intel.core.enums import Asset, Timeframe
    from crypto_intel.core.models import Candle
    from crypto_intel.engines import analysis_context
    from crypto_intel.history import store

    end = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)

    def candles(n: int, base: float, step_hours: int) -> list[Candle]:
        out = []
        for i in range(n):
            price = base * (1 + 0.001 * i) + (i % 11) * base * 0.002
            out.append(Candle(
                timestamp=end - timedelta(hours=step_hours * (n - 1 - i)),
                open=price * 0.998, high=price * 1.01, low=price * 0.99,
                close=price, volume=1000 + i,
            ))
        return out

    for asset, base in ((Asset.BTC, 60000.0), (Asset.ETH, 3000.0), (Asset.SOL, 120.0)):
        store.save_candles(asset, Timeframe.D1, candles(400, base, 24), "test")
        store.save_candles(asset, Timeframe.H4, candles(400, base, 4), "test")
        store.save_candles(asset, Timeframe.H1, candles(400, base, 1), "test")
        store.save_candles(asset, Timeframe.W1, candles(120, base, 168), "test")
        store.save_derivatives(asset, "funding.rate", [
            (end - timedelta(hours=8 * i), 0.0001 * (1 + (i % 5))) for i in range(300)
        ], "test")
        store.save_derivatives(asset, "oi.contracts_bybit", [
            (end - timedelta(hours=i), 1_000_000 + i * 100) for i in range(300)
        ], "test")
    analysis_context.reset_cache()
    yield
    analysis_context.reset_cache()

"""Hourly prices for any asset a video discusses.

BTC, ETH and SOL come from the candles the app already stores. Anything else
(XRP, for instance) is read from Binance's public klines for the USDT pair,
cached for a few minutes. No price means the levels are shown as not watched,
never guessed.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

import httpx
import pandas as pd

from ..logging_setup import get_logger

log = get_logger(__name__)

BINANCE_KLINES = "https://api.binance.com/api/v3/klines"
_CACHE: dict[str, tuple[float, pd.DataFrame]] = {}
CACHE_SECONDS = 300
STORED_ASSETS = {"BTC", "ETH", "SOL"}


def _stored(asset: str, since: datetime) -> pd.DataFrame:
    from ..core.enums import Asset, Timeframe
    from ..history import store

    frame = store.load_candles(Asset(asset), Timeframe.H1, start=since - timedelta(hours=2))
    if frame.empty:
        return frame
    if frame.index.tz is None:
        frame.index = frame.index.tz_localize(UTC)
    return frame


def _binance(asset: str, since: datetime) -> pd.DataFrame:
    rows: list[list] = []
    start = int(since.timestamp() * 1000)
    with httpx.Client(timeout=20) as client:
        for _ in range(12):  # at most ~500 days of hourly bars
            response = client.get(BINANCE_KLINES, params={
                "symbol": f"{asset}USDT", "interval": "1h", "startTime": start, "limit": 1000,
            })
            if response.status_code != 200:
                break
            batch = response.json()
            if not batch:
                break
            rows.extend(batch)
            if len(batch) < 1000:
                break
            start = int(batch[-1][0]) + 1
    if not rows:
        return pd.DataFrame(columns=["open", "high", "low", "close"])
    frame = pd.DataFrame(
        [[float(r[1]), float(r[2]), float(r[3]), float(r[4])] for r in rows],
        columns=["open", "high", "low", "close"],
        index=pd.DatetimeIndex([datetime.fromtimestamp(int(r[0]) / 1000, UTC) for r in rows]),
    )
    # Only closed bars: the hour in progress is not a fact yet.
    now = datetime.now(UTC)
    return frame.loc[frame.index + pd.Timedelta(hours=1) <= now]


def hourly_prices(asset: str, since: datetime) -> pd.DataFrame | None:
    asset = asset.upper()
    key = f"{asset}:{since.date()}"
    cached = _CACHE.get(key)
    if cached and time.time() - cached[0] < CACHE_SECONDS:
        return cached[1]
    try:
        frame = _stored(asset, since) if asset in STORED_ASSETS else _binance(asset, since)
    except Exception as exc:  # a missing price is shown as such, never invented
        log.warning("lexa_price_unavailable", asset=asset, error=str(exc))
        return None
    if frame is None or frame.empty:
        return None
    _CACHE[key] = (time.time(), frame)
    return frame

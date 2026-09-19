"""Who takes the initiative on spot: aggressive buyers or aggressive sellers.

Every trade has a buyer and a seller. What an exchange records is which side
crossed the spread - the taker. Summing taker-buy and taker-sell notional per
hour measures pressure, not money "in" or "out".

    Binance   1 h klines: quote volume and taker-buy quote volume (USDT).
    OKX       rubik taker-volume, 1 h, in coin units; converted to USD with the
              hour's close from our own candles, and the conversion is noted.
    Bybit     live publicTrade stream (see ``streams/bybit.py``).

Exchanges are separate venues, so their notionals add up without double
counting. Each is stored under its own metric so coverage stays visible.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pandas as pd

from ..core.enums import Asset, Timeframe
from ..logging_setup import get_logger
from ..providers.http import get_http
from . import store

log = get_logger(__name__)

BINANCE_SPOT = "https://api.binance.com/api/v3/klines"
OKX_TAKER = "https://www.okx.com/api/v5/rubik/stat/taker-volume"

EXCHANGES = ("binance", "okx", "bybit")


def buy_metric(exchange: str) -> str:
    return f"spot.flow.buy_usd.{exchange}"


def sell_metric(exchange: str) -> str:
    return f"spot.flow.sell_usd.{exchange}"


def parse_binance_hours(rows: Any) -> list[tuple[datetime, float, float]]:
    """(hour, taker-buy USDT, taker-sell USDT) for closed and open hours."""

    out: list[tuple[datetime, float, float]] = []
    for row in rows or []:
        try:
            hour = datetime.fromtimestamp(int(row[0]) / 1000, UTC)
            quote = float(row[7])
            taker_buy = float(row[10])
        except (IndexError, TypeError, ValueError):
            continue
        if quote <= 0:
            continue
        out.append((hour, taker_buy, quote - taker_buy))
    return out


def parse_okx_hours(payload: Any) -> list[tuple[datetime, float, float]]:
    """(hour, buy coins, sell coins). OKX rows are [ts, sellVol, buyVol]."""

    out: list[tuple[datetime, float, float]] = []
    for row in (payload or {}).get("data", []) or []:
        try:
            hour = datetime.fromtimestamp(int(row[0]) / 1000, UTC)
            sell, buy = float(row[1]), float(row[2])
        except (IndexError, TypeError, ValueError):
            continue
        out.append((hour, buy, sell))
    return out


async def collect_spot_flows(asset: Asset, hours: int = 48) -> dict[str, int]:
    http = get_http()
    written: dict[str, int] = {}

    res = await http.get_json(
        BINANCE_SPOT, provider="binance_spot_flow",
        params={"symbol": f"{asset.value}USDT", "interval": "1h", "limit": min(hours, 1000)},
        cache_ttl=0, rate_limit_per_min=60, retries=2,
    )
    if res.ok:
        rows = parse_binance_hours(res.data)
        store.upsert_derivatives(asset, buy_metric("binance"), [(h, b) for h, b, _ in rows],
                                 source="Binance spot (klines 1 h, USDT)")
        store.upsert_derivatives(asset, sell_metric("binance"), [(h, s) for h, _, s in rows],
                                 source="Binance spot (klines 1 h, USDT)")
        written["binance"] = len(rows)

    res = await http.get_json(
        OKX_TAKER, provider="okx_taker_volume",
        params={"ccy": asset.value, "instType": "SPOT", "period": "1H"},
        cache_ttl=0, rate_limit_per_min=20, retries=2,
    )
    if res.ok:
        closes = store.load_candles(
            asset, Timeframe.H1, start=datetime.now(UTC) - timedelta(days=40)
        )
        priced: list[tuple[datetime, float, float]] = []
        if not closes.empty:
            for hour, buy, sell in parse_okx_hours(res.data):
                # The hour's own close: never a later price applied backwards.
                stamp = pd.Timestamp(hour)
                if closes.index.tz is None:
                    stamp = stamp.tz_localize(None)
                if stamp not in closes.index:
                    continue
                price = float(closes.loc[stamp, "close"])
                priced.append((hour, buy * price, sell * price))
        source = "OKX spot (taker-volume 1 h, converti au prix de clôture horaire)"
        store.upsert_derivatives(asset, buy_metric("okx"), [(h, b) for h, b, _ in priced], source=source)
        store.upsert_derivatives(asset, sell_metric("okx"), [(h, s) for h, _, s in priced], source=source)
        written["okx"] = len(priced)
    return written


async def collect_all_spot_flows(hours: int = 48) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for asset in (Asset.BTC, Asset.ETH, Asset.SOL):
        try:
            out[asset.value] = await collect_spot_flows(asset, hours)
        except Exception as exc:  # one exchange down never stops the pass
            log.warning("spot_flow_collect_failed", asset=asset.value, error=str(exc))
            out[asset.value] = {}
    return out


def hourly_window(series_by_exchange: dict[str, tuple[list, list]], end: datetime,
                  span: timedelta) -> dict[str, tuple[float, float, int]]:
    """Sum (buy, sell, hours) per exchange over [end - span, end)."""

    start = end - span
    out: dict[str, tuple[float, float, int]] = {}
    for exchange, (buys, sells) in series_by_exchange.items():
        buy = sum(v for t, v in buys if start <= t < end)
        sell = sum(v for t, v in sells if start <= t < end)
        n = sum(1 for t, _ in buys if start <= t < end)
        out[exchange] = (buy, sell, n)
    return out

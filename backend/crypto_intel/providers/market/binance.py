"""Binance spot: OHLCV and 24h ticker. Primary market data source.

Read-only public endpoints only. No API key, no account, no order placement -
this project holds no exchange write credentials by design.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ...config_loader import asset_meta
from ...core.enums import Asset, DataQuality, FetchStatus, ProviderCategory, Timeframe
from ...core.freshness import compute_freshness
from ...core.models import Candle, Observation, OHLCVSeries
from ..base import BaseProvider, FetchRequest, FetchResult
from ..http import get_http

_INTERVAL = {
    Timeframe.M15: "15m",
    Timeframe.H1: "1h",
    Timeframe.H4: "4h",
    Timeframe.D1: "1d",
    Timeframe.W1: "1w",
}


class BinanceSpotProvider(BaseProvider):
    name = "binance_spot"
    source = "Binance"
    category = ProviderCategory.MARKET
    capabilities = ("market.ohlcv", "market.ticker")
    source_url = "https://api.binance.com"
    base_confidence = 92.0

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.base_url = self.config.get("base_url", "https://api.binance.com")
        self.rate = int(self.config.get("rate_limit_per_min", 100))
        self.ttl: dict[str, int] = self.config.get("cache_ttl", {}) or {}

    def _symbol(self, asset: Asset) -> str:
        return str(asset_meta(asset.value)["binance_symbol"])

    async def fetch(self, request: FetchRequest) -> FetchResult:
        if request.capability == "market.ohlcv":
            return await self._fetch_ohlcv(request)
        if request.capability == "market.ticker":
            return await self._fetch_ticker(request)
        return FetchResult.failure(FetchStatus.DISABLED, self.name, "capability not supported")

    async def _fetch_ohlcv(self, request: FetchRequest) -> FetchResult:
        if request.asset is None or request.timeframe is None:
            return FetchResult.failure(FetchStatus.NO_DATA, self.name, "asset and timeframe required")

        tf = request.timeframe
        url = f"{self.base_url}/api/v3/klines"
        params = {
            "symbol": self._symbol(request.asset),
            "interval": _INTERVAL[tf],
            "limit": min(request.limit, 1000),
        }
        res = await get_http().get_json(
            url,
            provider=self.name,
            params=params,
            cache_ttl=int(self.ttl.get(tf.value, 300)),
            rate_limit_per_min=self.rate,
        )
        if not res.ok:
            return FetchResult.failure(res.status, self.name, res.message)

        try:
            candles = [
                Candle(
                    timestamp=datetime.fromtimestamp(int(k[0]) / 1000, tz=UTC),
                    open=float(k[1]),
                    high=float(k[2]),
                    low=float(k[3]),
                    close=float(k[4]),
                    volume=float(k[5]),
                )
                for k in res.data
            ]
        except (KeyError, IndexError, ValueError, TypeError) as exc:
            return FetchResult.failure(FetchStatus.PARSE_ERROR, self.name, str(exc))

        if not candles:
            return FetchResult.failure(FetchStatus.NO_DATA, self.name)

        series = OHLCVSeries(
            asset=request.asset,
            timeframe=tf,
            candles=candles,
            provenance=self.provenance(url),
            freshness=compute_freshness(candles[-1].timestamp, "price", interval_minutes=tf.minutes),
        )
        last = candles[-1]
        obs = Observation(
            asset=request.asset,
            metric="price.close",
            value=last.close,
            unit="USD",
            timeframe=tf,
            timestamp=last.timestamp,
            provenance=self.provenance(url),
            freshness=series.freshness,
            confidence=self.base_confidence,
            quality=DataQuality.MEASURED,
            meta={"bars": len(candles), "interval": _INTERVAL[tf]},
        )
        return FetchResult.success([obs], self.name, raw=series)

    async def _fetch_ticker(self, request: FetchRequest) -> FetchResult:
        if request.asset is None:
            return FetchResult.failure(FetchStatus.NO_DATA, self.name, "asset required")

        url = f"{self.base_url}/api/v3/ticker/24hr"
        res = await get_http().get_json(
            url,
            provider=self.name,
            params={"symbol": self._symbol(request.asset)},
            cache_ttl=int(self.ttl.get("ticker", 60)),
            rate_limit_per_min=self.rate,
        )
        if not res.ok:
            return FetchResult.failure(res.status, self.name, res.message)

        d = res.data
        now = datetime.now(UTC)
        prov = self.provenance(url)
        fresh = compute_freshness(now, "price")

        def obs(metric: str, value: float, unit: str) -> Observation:
            return Observation(
                asset=request.asset,
                metric=metric,
                value=value,
                unit=unit,
                timestamp=now,
                provenance=prov,
                freshness=fresh,
                confidence=self.base_confidence,
                quality=DataQuality.MEASURED,
            )

        try:
            out = [
                obs("price.last", float(d["lastPrice"]), "USD"),
                obs("price.change_24h_pct", float(d["priceChangePercent"]), "pct"),
                obs("price.high_24h", float(d["highPrice"]), "USD"),
                obs("price.low_24h", float(d["lowPrice"]), "USD"),
                obs("price.volume_24h_base", float(d["volume"]), request.asset.value),
                obs("price.volume_24h_quote", float(d["quoteVolume"]), "USD"),
            ]
        except (KeyError, ValueError, TypeError) as exc:
            return FetchResult.failure(FetchStatus.PARSE_ERROR, self.name, str(exc))

        return FetchResult.success(out, self.name, raw=d)

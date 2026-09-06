"""Kraken OHLC - second fallback for candle data."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ...config_loader import asset_meta
from ...core.enums import DataQuality, FetchStatus, ProviderCategory, Timeframe
from ...core.freshness import compute_freshness
from ...core.models import Candle, Observation, OHLCVSeries
from ..base import BaseProvider, FetchRequest, FetchResult
from ..http import get_http

_INTERVAL_MIN = {
    Timeframe.M15: 15,
    Timeframe.H1: 60,
    Timeframe.H4: 240,
    Timeframe.D1: 1440,
    Timeframe.W1: 10080,
}


class KrakenSpotProvider(BaseProvider):
    name = "kraken_spot"
    source = "Kraken"
    category = ProviderCategory.MARKET
    capabilities = ("market.ohlcv", "market.ticker")
    source_url = "https://api.kraken.com"
    base_confidence = 88.0

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.base_url = self.config.get("base_url", "https://api.kraken.com")
        self.rate = int(self.config.get("rate_limit_per_min", 30))

    async def fetch(self, request: FetchRequest) -> FetchResult:
        if request.asset is None:
            return FetchResult.failure(FetchStatus.NO_DATA, self.name, "asset required")
        if request.capability == "market.ohlcv":
            return await self._ohlcv(request)
        if request.capability == "market.ticker":
            return await self._ticker(request)
        return FetchResult.failure(FetchStatus.DISABLED, self.name)

    async def _ohlcv(self, request: FetchRequest) -> FetchResult:
        tf = request.timeframe or Timeframe.H1
        pair = asset_meta(request.asset.value)["kraken_pair"]
        url = f"{self.base_url}/0/public/OHLC"
        res = await get_http().get_json(
            url,
            provider=self.name,
            params={"pair": pair, "interval": _INTERVAL_MIN[tf]},
            cache_ttl=300,
            rate_limit_per_min=self.rate,
        )
        if not res.ok:
            return FetchResult.failure(res.status, self.name, res.message)

        payload = res.data or {}
        if payload.get("error"):
            return FetchResult.failure(
                FetchStatus.PARSE_ERROR, self.name, str(payload["error"])
            )
        result = payload.get("result", {})
        # Kraken returns the pair under its own canonical name, plus "last".
        series_key = next((k for k in result if k != "last"), None)
        if not series_key:
            return FetchResult.failure(FetchStatus.NO_DATA, self.name)

        try:
            candles = [
                Candle(
                    timestamp=datetime.fromtimestamp(int(row[0]), tz=UTC),
                    open=float(row[1]),
                    high=float(row[2]),
                    low=float(row[3]),
                    close=float(row[4]),
                    volume=float(row[6]),
                )
                for row in result[series_key]
            ]
        except (IndexError, ValueError, TypeError) as exc:
            return FetchResult.failure(FetchStatus.PARSE_ERROR, self.name, str(exc))

        if not candles:
            return FetchResult.failure(FetchStatus.NO_DATA, self.name)

        candles = candles[-request.limit :]
        series = OHLCVSeries(
            asset=request.asset,
            timeframe=tf,
            candles=candles,
            provenance=self.provenance(url),
            freshness=compute_freshness(candles[-1].timestamp, "price", interval_minutes=tf.minutes),
        )
        obs = Observation(
            asset=request.asset,
            metric="price.close",
            value=candles[-1].close,
            unit="USD",
            timeframe=tf,
            timestamp=candles[-1].timestamp,
            provenance=self.provenance(url),
            freshness=series.freshness,
            confidence=self.base_confidence,
            quality=DataQuality.MEASURED,
            meta={"bars": len(candles)},
        )
        return FetchResult.success([obs], self.name, raw=series)

    async def _ticker(self, request: FetchRequest) -> FetchResult:
        pair = asset_meta(request.asset.value)["kraken_pair"]
        url = f"{self.base_url}/0/public/Ticker"
        res = await get_http().get_json(
            url, provider=self.name, params={"pair": pair}, cache_ttl=60,
            rate_limit_per_min=self.rate,
        )
        if not res.ok:
            return FetchResult.failure(res.status, self.name, res.message)
        result = (res.data or {}).get("result", {})
        key = next(iter(result), None)
        if not key:
            return FetchResult.failure(FetchStatus.NO_DATA, self.name)
        try:
            price = float(result[key]["c"][0])
        except (KeyError, IndexError, ValueError, TypeError) as exc:
            return FetchResult.failure(FetchStatus.PARSE_ERROR, self.name, str(exc))

        now = datetime.now(UTC)
        return FetchResult.success(
            [
                Observation(
                    asset=request.asset,
                    metric="price.last",
                    value=price,
                    unit="USD",
                    timestamp=now,
                    provenance=self.provenance(url),
                    freshness=compute_freshness(now, "price"),
                    confidence=self.base_confidence,
                )
            ],
            self.name,
        )

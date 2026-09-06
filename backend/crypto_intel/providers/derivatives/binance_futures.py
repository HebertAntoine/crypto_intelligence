"""Binance USD-M futures: funding, open interest, long/short ratio.

Public read-only endpoints. Covers BTC, ETH and SOL perpetuals equally.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ...config_loader import asset_meta
from ...core.enums import DataQuality, FetchStatus, ProviderCategory
from ...core.freshness import compute_freshness
from ...core.models import Observation
from ..base import BaseProvider, FetchRequest, FetchResult
from ..http import get_http


class BinanceFuturesProvider(BaseProvider):
    name = "binance_futures"
    source = "Binance Futures"
    category = ProviderCategory.DERIVATIVES
    capabilities = ("derivatives.funding", "derivatives.oi", "derivatives.ratio")
    source_url = "https://fapi.binance.com"
    base_confidence = 90.0

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.base_url = self.config.get("base_url", "https://fapi.binance.com")
        self.rate = int(self.config.get("rate_limit_per_min", 60))
        self.ttl = int((self.config.get("cache_ttl") or {}).get("default", 300))

    def _symbol(self, asset) -> str:
        return str(asset_meta(asset.value)["binance_symbol"])

    async def fetch(self, request: FetchRequest) -> FetchResult:
        if request.asset is None:
            return FetchResult.failure(FetchStatus.NO_DATA, self.name, "asset required")
        if request.capability == "derivatives.funding":
            return await self._funding(request)
        if request.capability == "derivatives.oi":
            return await self._open_interest(request)
        if request.capability == "derivatives.ratio":
            return await self._ratio(request)
        return FetchResult.failure(FetchStatus.DISABLED, self.name)

    async def _funding(self, request: FetchRequest) -> FetchResult:
        symbol = self._symbol(request.asset)
        http = get_http()
        prov = self.provenance(f"{self.base_url}/fapi/v1/premiumIndex")
        out: list[Observation] = []

        cur = await http.get_json(
            f"{self.base_url}/fapi/v1/premiumIndex", provider=self.name,
            params={"symbol": symbol}, cache_ttl=self.ttl, rate_limit_per_min=self.rate,
        )
        if not cur.ok:
            return FetchResult.failure(cur.status, self.name, cur.message)
        try:
            d = cur.data
            ts = datetime.fromtimestamp(int(d["time"]) / 1000, tz=UTC)
            fr = float(d["lastFundingRate"])
            mark = float(d["markPrice"])
            index = float(d["indexPrice"])
            out.append(Observation(
                asset=request.asset, metric="funding.rate", value=fr, unit="ratio",
                timestamp=ts, provenance=prov, freshness=compute_freshness(ts, "funding"),
                confidence=self.base_confidence, quality=DataQuality.MEASURED,
                meta={"symbol": symbol, "period_hours": 8},
            ))
            out.append(Observation(
                asset=request.asset, metric="funding.mark_price", value=mark, unit="USD",
                timestamp=ts, provenance=prov, freshness=compute_freshness(ts, "funding"),
                confidence=self.base_confidence,
            ))
            # Basis = premium of perp over spot index. Positive = leveraged longs paying up.
            if index:
                out.append(Observation(
                    asset=request.asset, metric="derivatives.basis_pct",
                    value=(mark - index) / index * 100.0, unit="pct", timestamp=ts,
                    provenance=prov, freshness=compute_freshness(ts, "funding"),
                    confidence=self.base_confidence, quality=DataQuality.DERIVED,
                    meta={"formula": "(markPrice - indexPrice) / indexPrice * 100"},
                ))
        except (KeyError, ValueError, TypeError) as exc:
            return FetchResult.failure(FetchStatus.PARSE_ERROR, self.name, str(exc))

        # Funding history lets the engine see whether funding is rising or cooling.
        hist = await http.get_json(
            f"{self.base_url}/fapi/v1/fundingRate", provider=self.name,
            params={"symbol": symbol, "limit": 100}, cache_ttl=self.ttl,
            rate_limit_per_min=self.rate,
        )
        if hist.ok and isinstance(hist.data, list):
            for row in hist.data:
                try:
                    ts = datetime.fromtimestamp(int(row["fundingTime"]) / 1000, tz=UTC)
                    out.append(Observation(
                        asset=request.asset, metric="funding.rate_history",
                        value=float(row["fundingRate"]), unit="ratio", timestamp=ts,
                        provenance=prov, freshness=compute_freshness(ts, "funding"),
                        confidence=self.base_confidence, meta={"symbol": symbol},
                    ))
                except (KeyError, ValueError, TypeError):
                    continue

        return FetchResult.success(out, self.name)

    async def _open_interest(self, request: FetchRequest) -> FetchResult:
        symbol = self._symbol(request.asset)
        http = get_http()
        prov = self.provenance(f"{self.base_url}/fapi/v1/openInterest")
        out: list[Observation] = []

        cur = await http.get_json(
            f"{self.base_url}/fapi/v1/openInterest", provider=self.name,
            params={"symbol": symbol}, cache_ttl=self.ttl, rate_limit_per_min=self.rate,
        )
        if not cur.ok:
            return FetchResult.failure(cur.status, self.name, cur.message)
        try:
            ts = datetime.fromtimestamp(int(cur.data["time"]) / 1000, tz=UTC)
            out.append(Observation(
                asset=request.asset, metric="oi.contracts", value=float(cur.data["openInterest"]),
                unit=request.asset.value, timestamp=ts, provenance=prov,
                freshness=compute_freshness(ts, "oi"), confidence=self.base_confidence,
                quality=DataQuality.MEASURED, meta={"symbol": symbol},
            ))
        except (KeyError, ValueError, TypeError) as exc:
            return FetchResult.failure(FetchStatus.PARSE_ERROR, self.name, str(exc))

        hist = await http.get_json(
            f"{self.base_url}/futures/data/openInterestHist", provider=self.name,
            params={"symbol": symbol, "period": "1h", "limit": 72},
            cache_ttl=self.ttl, rate_limit_per_min=self.rate,
        )
        if hist.ok and isinstance(hist.data, list):
            for row in hist.data:
                try:
                    ts = datetime.fromtimestamp(int(row["timestamp"]) / 1000, tz=UTC)
                    out.append(Observation(
                        asset=request.asset, metric="oi.value_history",
                        value=float(row["sumOpenInterestValue"]), unit="USD", timestamp=ts,
                        provenance=prov, freshness=compute_freshness(ts, "oi"),
                        confidence=self.base_confidence, meta={"symbol": symbol},
                    ))
                except (KeyError, ValueError, TypeError):
                    continue

        return FetchResult.success(out, self.name)

    async def _ratio(self, request: FetchRequest) -> FetchResult:
        symbol = self._symbol(request.asset)
        url = f"{self.base_url}/futures/data/globalLongShortAccountRatio"
        res = await get_http().get_json(
            url, provider=self.name, params={"symbol": symbol, "period": "1h", "limit": 48},
            cache_ttl=self.ttl, rate_limit_per_min=self.rate,
        )
        if not res.ok:
            return FetchResult.failure(res.status, self.name, res.message)
        if not isinstance(res.data, list) or not res.data:
            return FetchResult.failure(FetchStatus.NO_DATA, self.name)

        prov = self.provenance(url)
        out = []
        for row in res.data:
            try:
                ts = datetime.fromtimestamp(int(row["timestamp"]) / 1000, tz=UTC)
                out.append(Observation(
                    asset=request.asset, metric="long_short.ratio",
                    value=float(row["longShortRatio"]), unit="ratio", timestamp=ts,
                    provenance=prov, freshness=compute_freshness(ts, "long_short"),
                    confidence=80.0, meta={"symbol": symbol},
                ))
            except (KeyError, ValueError, TypeError):
                continue
        return FetchResult.success(out, self.name)

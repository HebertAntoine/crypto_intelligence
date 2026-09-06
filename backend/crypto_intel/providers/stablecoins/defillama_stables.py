"""Stablecoin supply and distribution - the liquidity backbone of crypto.

Tracks total supply, per-issuer supply (USDT/USDC/DAI) and per-chain
distribution, which is what tells us whether liquidity is entering or leaving
the ecosystem.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ...core.enums import DataQuality, FetchStatus, ProviderCategory
from ...core.freshness import compute_freshness
from ...core.models import Observation
from ..base import BaseProvider, FetchRequest, FetchResult
from ..http import get_http

_TRACKED = {"USDT", "USDC", "DAI", "USDE", "PYUSD", "FDUSD", "TUSD"}
_CHAINS = {"Ethereum", "Solana", "Tron", "BSC", "Arbitrum", "Base", "Polygon", "Avalanche"}


class DefiLlamaStablecoinsProvider(BaseProvider):
    name = "defillama_stables"
    source = "DeFiLlama Stablecoins"
    category = ProviderCategory.STABLECOINS
    capabilities = ("stablecoins.supply",)
    source_url = "https://defillama.com/stablecoins"
    base_confidence = 85.0

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.base_url = self.config.get("base_url", "https://stablecoins.llama.fi")
        self.ttl = int((self.config.get("cache_ttl") or {}).get("default", 3600))

    async def fetch(self, request: FetchRequest) -> FetchResult:
        url = f"{self.base_url}/stablecoins"
        res = await get_http().get_json(
            url, provider=self.name, params={"includePrices": "true"},
            cache_ttl=self.ttl, rate_limit_per_min=20,
        )
        if not res.ok:
            return FetchResult.failure(res.status, self.name, res.message)

        coins = (res.data or {}).get("peggedAssets") or []
        if not coins:
            return FetchResult.failure(FetchStatus.NO_DATA, self.name)

        now = datetime.now(UTC)
        prov = self.provenance(self.source_url)
        out: list[Observation] = []

        def mk(metric: str, value: float, unit: str, meta: dict | None = None) -> Observation:
            return Observation(
                asset=None, metric=metric, value=value, unit=unit, timestamp=now,
                provenance=prov, freshness=compute_freshness(now, "stablecoin"),
                confidence=self.base_confidence, quality=DataQuality.MEASURED, meta=meta or {},
            )

        total_now = 0.0
        total_prev_day = 0.0
        total_prev_week = 0.0

        for coin in coins:
            symbol = str(coin.get("symbol", "")).upper()
            circ = (coin.get("circulating") or {}).get("peggedUSD")
            if circ is None:
                continue
            circ = float(circ)
            total_now += circ
            prev_d = (coin.get("circulatingPrevDay") or {}).get("peggedUSD")
            prev_w = (coin.get("circulatingPrevWeek") or {}).get("peggedUSD")
            total_prev_day += float(prev_d) if prev_d is not None else circ
            total_prev_week += float(prev_w) if prev_w is not None else circ

            if symbol in _TRACKED:
                out.append(mk(f"stablecoin.supply.{symbol}", circ, "USD", {"symbol": symbol}))

            for chain, amounts in (coin.get("chainCirculating") or {}).items():
                if chain not in _CHAINS:
                    continue
                cur = (amounts.get("current") or {}).get("peggedUSD")
                if cur is None:
                    continue
                key = f"stablecoin.chain.{chain}"
                existing = next((o for o in out if o.metric == key), None)
                if existing:
                    out.remove(existing)
                    cur = float(cur) + (existing.numeric_value or 0.0)
                out.append(mk(key, float(cur), "USD", {"chain": chain}))

        out.append(mk("stablecoin.supply.total", total_now, "USD"))
        if total_prev_day:
            out.append(mk("stablecoin.supply.change_1d_pct",
                          (total_now - total_prev_day) / total_prev_day * 100.0, "pct"))
        if total_prev_week:
            out.append(mk("stablecoin.supply.change_7d_pct",
                          (total_now - total_prev_week) / total_prev_week * 100.0, "pct"))
        return FetchResult.success(out, self.name)

"""DeFiLlama: TVL, DEX volumes, protocol fees, RWA. No API key required."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ...config_loader import asset_meta
from ...core.enums import Asset, DataQuality, FetchStatus, ProviderCategory
from ...core.freshness import compute_freshness
from ...core.models import Observation
from ..base import BaseProvider, FetchRequest, FetchResult
from ..http import get_http


class DefiLlamaProvider(BaseProvider):
    name = "defillama"
    source = "DeFiLlama"
    category = ProviderCategory.DEFI
    capabilities = ("defi.tvl", "defi.dex", "defi.fees")
    source_url = "https://defillama.com"
    base_confidence = 86.0

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.base_url = self.config.get("base_url", "https://api.llama.fi")
        self.rate = int(self.config.get("rate_limit_per_min", 30))
        self.ttl = int((self.config.get("cache_ttl") or {}).get("default", 1800))

    def _chain(self, asset: Asset) -> str | None:
        try:
            return asset_meta(asset.value).get("defillama_chain")
        except Exception:
            return None

    async def fetch(self, request: FetchRequest) -> FetchResult:
        if request.asset is None:
            return FetchResult.failure(FetchStatus.NO_DATA, self.name, "asset required")
        chain = self._chain(request.asset)
        if not chain:
            return FetchResult.failure(
                FetchStatus.NO_DATA, self.name,
                f"No DeFiLlama chain mapping for {request.asset.value}",
            )
        if request.capability == "defi.tvl":
            return await self._tvl(request.asset, chain)
        if request.capability == "defi.dex":
            return await self._overview(request.asset, chain, "dexs", "defi.dex")
        if request.capability == "defi.fees":
            return await self._overview(request.asset, chain, "fees", "defi.fees")
        return FetchResult.failure(FetchStatus.DISABLED, self.name)

    async def _tvl(self, asset: Asset, chain: str) -> FetchResult:
        # Bitcoin has essentially no native DeFi TVL - reporting a chain TVL
        # for BTC would be misleading, so we say so instead of showing ~0.
        if asset is Asset.BTC:
            return FetchResult.failure(
                FetchStatus.NO_DATA, self.name,
                "TVL is not a meaningful metric for Bitcoin L1 (no native smart-contract DeFi)",
            )
        url = f"{self.base_url}/v2/historicalChainTvl/{chain}"
        res = await get_http().get_json(
            url, provider=self.name, cache_ttl=self.ttl, rate_limit_per_min=self.rate
        )
        if not res.ok:
            return FetchResult.failure(res.status, self.name, res.message)
        series = res.data or []
        if not isinstance(series, list) or not series:
            return FetchResult.failure(FetchStatus.NO_DATA, self.name)

        prov = self.provenance(f"https://defillama.com/chain/{chain}")
        out: list[Observation] = []
        # Keep ~120 days: enough for 7d/30d trends without bloating the DB.
        for point in series[-120:]:
            try:
                ts = datetime.fromtimestamp(int(point["date"]), tz=UTC)
                out.append(Observation(
                    asset=asset, metric="defi.tvl", value=float(point["tvl"]), unit="USD",
                    timestamp=ts, provenance=prov, freshness=compute_freshness(ts, "defi"),
                    confidence=self.base_confidence, quality=DataQuality.MEASURED,
                    meta={"chain": chain},
                ))
            except (KeyError, ValueError, TypeError):
                continue
        return FetchResult.success(out, self.name)

    async def _overview(self, asset: Asset, chain: str, kind: str, metric: str) -> FetchResult:
        url = f"{self.base_url}/overview/{kind}/{chain}"
        res = await get_http().get_json(
            url, provider=self.name,
            params={"excludeTotalDataChart": "true", "excludeTotalDataChartBreakdown": "true"},
            cache_ttl=self.ttl, rate_limit_per_min=self.rate,
        )
        if not res.ok:
            return FetchResult.failure(res.status, self.name, res.message)

        d = res.data or {}
        now = datetime.now(UTC)
        prov = self.provenance(f"https://defillama.com/{kind}/chain/{chain}")
        out: list[Observation] = []
        for field, suffix, unit in (
            ("total24h", "_24h", "USD"),
            ("total7d", "_7d", "USD"),
            ("total30d", "_30d", "USD"),
            ("change_1d", "_change_1d_pct", "pct"),
            ("change_7d", "_change_7d_pct", "pct"),
            ("change_1m", "_change_30d_pct", "pct"),
        ):
            val = d.get(field)
            if val is None:
                continue
            try:
                out.append(Observation(
                    asset=asset, metric=f"{metric}{suffix}", value=float(val), unit=unit,
                    timestamp=now, provenance=prov, freshness=compute_freshness(now, "defi"),
                    confidence=self.base_confidence, quality=DataQuality.MEASURED,
                    meta={"chain": chain},
                ))
            except (TypeError, ValueError):
                continue
        if not out:
            return FetchResult.failure(FetchStatus.NO_DATA, self.name)
        return FetchResult.success(out, self.name)


class DefiLlamaRWAProvider(BaseProvider):
    """Real-world assets: measures whether real economic activity is moving
    on-chain, via the RWA protocol category."""

    name = "defillama_rwa"
    source = "DeFiLlama (RWA)"
    category = ProviderCategory.RWA
    capabilities = ("defi.rwa",)
    source_url = "https://defillama.com/protocols/RWA"
    base_confidence = 78.0

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.base_url = self.config.get("base_url", "https://api.llama.fi")

    async def fetch(self, request: FetchRequest) -> FetchResult:
        res = await get_http().get_json(
            f"{self.base_url}/protocols", provider=self.name,
            cache_ttl=7200, rate_limit_per_min=20,
        )
        if not res.ok:
            return FetchResult.failure(res.status, self.name, res.message)
        protocols = res.data or []
        if not isinstance(protocols, list):
            return FetchResult.failure(FetchStatus.PARSE_ERROR, self.name)

        rwa = [p for p in protocols if str(p.get("category", "")).upper() == "RWA"]
        if not rwa:
            return FetchResult.failure(FetchStatus.NO_DATA, self.name, "No RWA protocols returned")

        now = datetime.now(UTC)
        prov = self.provenance(self.source_url)
        total = sum(float(p.get("tvl") or 0) for p in rwa)
        chain_totals: dict[str, float] = {}
        for p in rwa:
            for chain, tvl in (p.get("chainTvls") or {}).items():
                if isinstance(tvl, int | float):
                    chain_totals[chain] = chain_totals.get(chain, 0.0) + float(tvl)

        def mk(metric: str, value: float, unit: str, meta: dict | None = None) -> Observation:
            return Observation(
                asset=None, metric=metric, value=value, unit=unit, timestamp=now,
                provenance=prov, freshness=compute_freshness(now, "defi"),
                confidence=self.base_confidence, quality=DataQuality.MEASURED, meta=meta or {},
            )

        out = [
            mk("rwa.total_value", total, "USD", {"protocol_count": len(rwa)}),
            mk("rwa.protocol_count", float(len(rwa)), "count"),
        ]
        for change_field, metric in (("change_7d", "rwa.change_7d_pct"), ("change_1m", "rwa.change_30d_pct")):
            vals = [float(p[change_field]) for p in rwa if isinstance(p.get(change_field), int | float)]
            if vals:
                out.append(mk(metric, sum(vals) / len(vals), "pct", {"note": "unweighted mean across RWA protocols"}))
        for chain, val in sorted(chain_totals.items(), key=lambda kv: -kv[1])[:8]:
            out.append(mk(f"rwa.chain.{chain}", val, "USD", {"chain": chain}))
        return FetchResult.success(out, self.name)

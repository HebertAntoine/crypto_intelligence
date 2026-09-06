"""Optional paid ETF providers. Without a key: UNAVAILABLE, never invented."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ...core.enums import DataQuality, FetchStatus, ProviderCategory
from ...core.freshness import compute_freshness
from ...core.models import Observation
from ...settings import get_settings
from ..base import BaseProvider, FetchRequest, FetchResult
from ..http import get_http


class CoinglassETFProvider(BaseProvider):
    name = "coinglass_etf"
    source = "Coinglass"
    category = ProviderCategory.ETF
    capabilities = ("etf.flows",)
    requires_key = "COINGLASS_API_KEY"
    source_url = "https://www.coinglass.com"
    base_confidence = 85.0

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.base_url = self.config.get("base_url", "https://open-api-v3.coinglass.com")

    async def fetch(self, request: FetchRequest) -> FetchResult:
        settings = get_settings()
        if not settings.has_key(self.requires_key or ""):
            return FetchResult.failure(FetchStatus.NOT_CONFIGURED, self.name)
        if request.asset is None:
            return FetchResult.failure(FetchStatus.NO_DATA, self.name)

        endpoint = (
            "/api/bitcoin/etf/flow-history" if request.asset.value == "BTC"
            else "/api/ethereum/etf/flow-history"
        )
        res = await get_http().get_json(
            f"{self.base_url}{endpoint}", provider=self.name,
            headers={"CG-API-KEY": settings.coinglass_api_key},
            cache_ttl=3600, rate_limit_per_min=20,
        )
        if not res.ok:
            return FetchResult.failure(res.status, self.name, res.message)

        payload = res.data or {}
        rows = payload.get("data") or []
        if not rows:
            return FetchResult.failure(FetchStatus.NO_DATA, self.name)

        prov = self.provenance(f"{self.base_url}{endpoint}")
        out = []
        for row in rows:
            try:
                ts_raw = row.get("timestamp") or row.get("date")
                ts = (
                    datetime.fromtimestamp(int(ts_raw) / 1000, tz=UTC)
                    if isinstance(ts_raw, int | float) or str(ts_raw).isdigit()
                    else datetime.fromisoformat(str(ts_raw)).replace(tzinfo=UTC)
                )
                flow = row.get("changeUsd", row.get("flowUsd"))
                if flow is None:
                    continue
                out.append(Observation(
                    asset=request.asset, metric="etf.flow",
                    value=float(flow) / 1_000_000.0, unit="USD_M", timestamp=ts,
                    provenance=prov, freshness=compute_freshness(ts, "etf"),
                    confidence=self.base_confidence, quality=DataQuality.MEASURED,
                    meta={"ticker": row.get("ticker", "TOTAL")},
                ))
            except (KeyError, ValueError, TypeError):
                continue
        return FetchResult.success(out, self.name)


class SoSoValueProvider(BaseProvider):
    name = "sosovalue"
    source = "SoSoValue"
    category = ProviderCategory.ETF
    capabilities = ("etf.flows",)
    requires_key = "SOSOVALUE_API_KEY"
    source_url = "https://sosovalue.com"
    base_confidence = 82.0

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.base_url = self.config.get("base_url", "https://api.sosovalue.xyz")

    async def fetch(self, request: FetchRequest) -> FetchResult:
        if not get_settings().has_key(self.requires_key or ""):
            return FetchResult.failure(FetchStatus.NOT_CONFIGURED, self.name)
        # Endpoint shape depends on the subscription tier; kept explicit rather
        # than guessed, so nothing fabricates a response.
        return FetchResult.failure(
            FetchStatus.NOT_CONFIGURED, self.name,
            "SoSoValue connector present but endpoint mapping requires an active subscription.",
        )

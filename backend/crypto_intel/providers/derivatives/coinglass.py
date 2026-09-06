"""Coinglass aggregated liquidations. Paid key.

Binance closed its public aggregated liquidation stream, so without a
Coinglass subscription liquidation data is simply UNAVAILABLE. We do not
estimate it from other figures.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ...core.enums import DataQuality, FetchStatus, ProviderCategory
from ...core.freshness import compute_freshness
from ...core.models import Observation
from ...settings import get_settings
from ..base import BaseProvider, FetchRequest, FetchResult
from ..http import get_http


class CoinglassProvider(BaseProvider):
    name = "coinglass"
    source = "Coinglass"
    category = ProviderCategory.DERIVATIVES
    capabilities = ("derivatives.liquidations",)
    requires_key = "COINGLASS_API_KEY"
    source_url = "https://www.coinglass.com"
    base_confidence = 82.0

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.base_url = self.config.get("base_url", "https://open-api-v3.coinglass.com")

    async def fetch(self, request: FetchRequest) -> FetchResult:
        settings = get_settings()
        if not settings.coinglass_api_key.strip():
            return FetchResult.failure(
                FetchStatus.NOT_CONFIGURED, self.name,
                "UNAVAILABLE - provider not configured (COINGLASS_API_KEY missing). "
                "Liquidation data has no free source.",
            )
        if request.asset is None:
            return FetchResult.failure(FetchStatus.NO_DATA, self.name)

        url = f"{self.base_url}/api/futures/liquidation/v2/history"
        res = await get_http().get_json(
            url, provider=self.name,
            params={"symbol": request.asset.value, "interval": "h1"},
            headers={"CG-API-KEY": settings.coinglass_api_key},
            cache_ttl=600, rate_limit_per_min=20,
        )
        if not res.ok:
            return FetchResult.failure(res.status, self.name, res.message)

        rows = (res.data or {}).get("data") or []
        if not rows:
            return FetchResult.failure(FetchStatus.NO_DATA, self.name)

        prov = self.provenance(url)
        out: list[Observation] = []
        for row in rows[-72:]:
            try:
                ts = datetime.fromtimestamp(int(row["t"]) / 1000, tz=UTC)
                longs = float(row.get("longLiquidationUsd", 0))
                shorts = float(row.get("shortLiquidationUsd", 0))
            except (KeyError, ValueError, TypeError):
                continue
            f = compute_freshness(ts, "liquidations")
            for metric, val in (
                ("liquidations.long", longs),
                ("liquidations.short", shorts),
                ("liquidations.total", longs + shorts),
            ):
                out.append(Observation(
                    asset=request.asset, metric=metric, value=val, unit="USD", timestamp=ts,
                    provenance=prov, freshness=f, confidence=self.base_confidence,
                    quality=DataQuality.MEASURED,
                ))
        return FetchResult.success(out, self.name)

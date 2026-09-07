"""Coinbase spot price - fallback and cross-check for Binance.

Binance is restricted in some jurisdictions, so this fallback is wired into
the registry for real, not for decoration.
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


class CoinbaseSpotProvider(BaseProvider):
    name = "coinbase_spot"
    source = "Coinbase"
    category = ProviderCategory.MARKET
    capabilities = ("market.ticker",)
    source_url = "https://api.coinbase.com"
    base_confidence = 90.0

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.base_url = self.config.get("base_url", "https://api.coinbase.com")
        self.rate = int(self.config.get("rate_limit_per_min", 60))

    async def fetch(self, request: FetchRequest) -> FetchResult:
        if request.capability != "market.ticker" or request.asset is None:
            return FetchResult.failure(FetchStatus.DISABLED, self.name)

        quote = str(request.params.get("quote", "USD")).upper()
        pair = (
            asset_meta(request.asset.value)["coinbase_pair"]
            if quote == "USD"
            else f"{request.asset.value}-{quote}"
        )
        url = f"{self.base_url}/v2/prices/{pair}/spot"
        res = await get_http().get_json(
            url, provider=self.name, cache_ttl=60, rate_limit_per_min=self.rate
        )
        if not res.ok:
            return FetchResult.failure(res.status, self.name, res.message)
        try:
            price = float(res.data["data"]["amount"])
        except (KeyError, TypeError, ValueError) as exc:
            return FetchResult.failure(FetchStatus.PARSE_ERROR, self.name, str(exc))

        now = datetime.now(UTC)
        return FetchResult.success(
            [
                Observation(
                    asset=request.asset,
                    metric="price.last",
                    value=price,
                    unit=quote,
                    timestamp=now,
                    provenance=self.provenance(url),
                    freshness=compute_freshness(now, "price"),
                    confidence=self.base_confidence,
                    quality=DataQuality.MEASURED,
                )
            ],
            self.name,
        )

"""CoinGecko: market cap, supply, dominance.

Exchanges do not publish market cap, so this is the only source for it. The
API is heavily rate limited, hence the long cache TTL.  It remains disabled
until a paid-plan key, the applicable commercial-display right and CoinGecko's
required public attribution have all been confirmed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ...config_loader import asset_meta
from ...core.enums import Asset, DataQuality, FetchStatus, ProviderCategory
from ...core.freshness import compute_freshness
from ...core.models import Observation, Provenance
from ...settings import get_settings
from ..base import BaseProvider, FetchRequest, FetchResult, ProviderStatus
from ..http import get_http


def coingecko_rights_status(provider: str) -> ProviderStatus:
    """Return a local-only rights check shared by both CoinGecko adapters."""

    settings = get_settings()
    missing: list[str] = []
    if not settings.coingecko_api_key.strip():
        missing.append("COINGECKO_API_KEY")
    if not settings.coingecko_commercial_use_authorized:
        missing.append("COINGECKO_COMMERCIAL_USE_AUTHORIZED")
    if not settings.coingecko_attribution_configured:
        missing.append("COINGECKO_ATTRIBUTION_CONFIGURED")
    if missing:
        return ProviderStatus(
            name=provider,
            available=False,
            reason=(
                "UNAVAILABLE - CoinGecko paid-plan/display rights and attribution are not "
                f"fully configured; missing: {', '.join(missing)}"
            ),
            configured=False,
        )
    return ProviderStatus(name=provider, available=True)


def coingecko_request_config() -> tuple[str, dict[str, str]]:
    """Paid API endpoint and secret header, never a query-string credential."""

    settings = get_settings()
    return (
        "https://pro-api.coingecko.com/api/v3",
        {"x-cg-pro-api-key": settings.coingecko_api_key},
    )


def coingecko_provenance(provider: str, url: str) -> Provenance:
    return Provenance(
        source="CoinGecko",
        provider=provider,
        source_url=url,
        license_note=(
            "Paid-plan commercial display enabled only after operator confirmation; "
            "public clients must show the configured CoinGecko attribution."
        ),
    )


class CoinGeckoProvider(BaseProvider):
    name = "coingecko"
    source = "CoinGecko"
    category = ProviderCategory.MARKET
    capabilities = ("market.marketcap", "market.global")
    source_url = "https://www.coingecko.com"
    base_confidence = 85.0

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        default_url, self.headers = coingecko_request_config()
        self.base_url = self.config.get("base_url", default_url)
        self.rate = int(self.config.get("rate_limit_per_min", 8))
        self.ttl = int((self.config.get("cache_ttl") or {}).get("default", 600))

    async def available(self) -> ProviderStatus:
        return coingecko_rights_status(self.name)

    async def fetch(self, request: FetchRequest) -> FetchResult:
        status = await self.available()
        if not status.available:
            return FetchResult.failure(FetchStatus.NOT_CONFIGURED, self.name, status.reason)
        if request.capability == "market.marketcap":
            return await self._marketcap(request)
        if request.capability == "market.global":
            return await self._global()
        return FetchResult.failure(FetchStatus.DISABLED, self.name)

    async def _marketcap(self, request: FetchRequest) -> FetchResult:
        if request.asset is None:
            return FetchResult.failure(FetchStatus.NO_DATA, self.name, "asset required")
        cg_id = asset_meta(request.asset.value)["coingecko_id"]
        url = f"{self.base_url}/coins/markets"
        res = await get_http().get_json(
            url,
            provider=self.name,
            params={"vs_currency": "usd", "ids": cg_id, "price_change_percentage": "1h,24h,7d"},
            headers=self.headers,
            cache_ttl=self.ttl,
            rate_limit_per_min=self.rate,
        )
        if not res.ok:
            return FetchResult.failure(res.status, self.name, res.message)
        if not res.data:
            return FetchResult.failure(FetchStatus.NO_DATA, self.name)

        d = res.data[0]
        now = datetime.now(UTC)
        prov = coingecko_provenance(
            self.name, f"https://www.coingecko.com/en/coins/{cg_id}"
        )
        fresh = compute_freshness(now, "market")

        out: list[Observation] = []

        def add(metric: str, value: Any, unit: str) -> None:
            # Missing fields are skipped, never defaulted to 0.
            if value is None:
                return
            out.append(
                Observation(
                    asset=request.asset,
                    metric=metric,
                    value=float(value),
                    unit=unit,
                    timestamp=now,
                    provenance=prov,
                    freshness=fresh,
                    confidence=self.base_confidence,
                    quality=DataQuality.MEASURED,
                    meta={"license_status": "OPERATOR_CONFIRMED"},
                )
            )

        add("market.cap", d.get("market_cap"), "USD")
        add("market.volume_24h", d.get("total_volume"), "USD")
        add("market.circulating_supply", d.get("circulating_supply"), request.asset.value)
        add("market.total_supply", d.get("total_supply"), request.asset.value)
        add("market.change_1h_pct", d.get("price_change_percentage_1h_in_currency"), "pct")
        add("market.change_24h_pct", d.get("price_change_percentage_24h_in_currency"), "pct")
        add("market.change_7d_pct", d.get("price_change_percentage_7d_in_currency"), "pct")
        add("market.ath", d.get("ath"), "USD")
        add("market.ath_change_pct", d.get("ath_change_percentage"), "pct")

        return FetchResult.success(out, self.name, raw=d)

    async def _global(self) -> FetchResult:
        url = f"{self.base_url}/global"
        res = await get_http().get_json(
            url,
            provider=self.name,
            headers=self.headers,
            cache_ttl=self.ttl,
            rate_limit_per_min=self.rate,
        )
        if not res.ok:
            return FetchResult.failure(res.status, self.name, res.message)

        d = (res.data or {}).get("data", {})
        now = datetime.now(UTC)
        prov = coingecko_provenance(
            self.name, "https://www.coingecko.com/en/global-charts"
        )
        fresh = compute_freshness(now, "market")
        out: list[Observation] = []

        mcap = (d.get("total_market_cap") or {}).get("usd")
        if mcap is not None:
            out.append(
                Observation(
                    asset=Asset.GLOBAL, metric="market.total_cap", value=float(mcap), unit="USD",
                    timestamp=now, provenance=prov, freshness=fresh, confidence=self.base_confidence,
                    meta={"license_status": "OPERATOR_CONFIRMED"},
                )
            )
        pct = d.get("market_cap_percentage") or {}
        for sym, cg in (("BTC", "btc"), ("ETH", "eth")):
            if cg in pct:
                out.append(
                    Observation(
                        asset=Asset(sym), metric="market.dominance", value=float(pct[cg]), unit="pct",
                        timestamp=now, provenance=prov, freshness=fresh, confidence=self.base_confidence,
                        meta={"license_status": "OPERATOR_CONFIRMED"},
                    )
                )
        change = d.get("market_cap_change_percentage_24h_usd")
        if change is not None:
            out.append(
                Observation(
                    asset=Asset.GLOBAL, metric="market.total_cap_change_24h_pct",
                    value=float(change), unit="pct", timestamp=now, provenance=prov,
                    freshness=fresh, confidence=self.base_confidence,
                    meta={"license_status": "OPERATOR_CONFIRMED"},
                )
            )
        return FetchResult.success(out, self.name, raw=d)

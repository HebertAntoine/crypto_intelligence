from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from crypto_intel.core.enums import Asset, DataQuality, FetchStatus, Freshness
from crypto_intel.core.models import Observation, Provenance
from crypto_intel.engines import market_price
from crypto_intel.providers.base import BaseProvider, FetchRequest, FetchResult


class _Settings:
    mock_mode = False


class _Provider(BaseProvider):
    capabilities = ("market.ticker",)

    def __init__(
        self,
        name: str,
        source: str,
        price: float | None,
        *,
        unit: str = "USD",
        change: float | None = None,
        status: FetchStatus = FetchStatus.OK,
    ) -> None:
        super().__init__({})
        self.name = name
        self.source = source
        self.price = price
        self.unit = unit
        self.change = change
        self.status = status

    async def fetch(self, request: FetchRequest) -> FetchResult:
        if self.status is not FetchStatus.OK or self.price is None:
            return FetchResult.failure(self.status, self.name, self.status.user_message)
        now = datetime.now(UTC) - timedelta(seconds=30)
        provenance = Provenance(source=self.source, provider=self.name)
        observations = [
            Observation(
                asset=request.asset,
                metric="price.last",
                value=self.price,
                unit=self.unit,
                timestamp=now,
                provenance=provenance,
                freshness=Freshness.LIVE,
                quality=DataQuality.MEASURED,
            )
        ]
        if self.change is not None:
            observations.append(
                Observation(
                    asset=request.asset,
                    metric="price.change_24h_pct",
                    value=self.change,
                    unit="pct",
                    timestamp=now,
                    provenance=provenance,
                    freshness=Freshness.LIVE,
                    quality=DataQuality.MEASURED,
                )
            )
        return FetchResult.success(observations, self.name)


class _Registry:
    def __init__(self, providers: list[BaseProvider], coinbase: BaseProvider | None = None) -> None:
        self.providers = providers
        self.coinbase = coinbase

    def chain(self, capability: str) -> list[BaseProvider]:
        assert capability == "market.ticker"
        return self.providers

    def get(self, name: str) -> BaseProvider | None:
        assert name == "coinbase_spot"
        return self.coinbase


@pytest.mark.asyncio
async def test_market_price_uses_median_and_reports_provenance(monkeypatch):
    providers = [
        _Provider("binance_spot", "Binance", 100.0, change=1.2),
        _Provider("coinbase_spot", "Coinbase", 102.0),
        _Provider("kraken_spot", "Kraken", 101.0),
    ]
    eur = _Provider("coinbase_spot", "Coinbase", 92.0, unit="EUR")
    monkeypatch.setattr(market_price, "get_registry", lambda: _Registry(providers, eur))
    monkeypatch.setattr(market_price, "get_settings", lambda: _Settings())

    snapshot = await market_price.market_price_snapshot(Asset.BTC)

    assert snapshot.status == "LIVE"
    assert snapshot.price_usd == 101.0
    assert snapshot.price_eur == 92.0
    assert snapshot.fx_rate == pytest.approx(92.0 / 101.0)
    assert snapshot.change_24h_pct == 1.2
    assert snapshot.provider_count == 3
    assert snapshot.quality == "MEDIUM"
    assert {quote.source for quote in snapshot.providers if quote.price} == {
        "Binance",
        "Coinbase",
        "Kraken",
    }


@pytest.mark.asyncio
async def test_market_price_does_not_fabricate_when_providers_fail(monkeypatch):
    providers = [
        _Provider("binance_spot", "Binance", None, status=FetchStatus.NETWORK_ERROR),
        _Provider("kraken_spot", "Kraken", None, status=FetchStatus.NO_DATA),
    ]
    monkeypatch.setattr(market_price, "get_registry", lambda: _Registry(providers))
    monkeypatch.setattr(market_price, "get_settings", lambda: _Settings())

    snapshot = await market_price.market_price_snapshot(Asset.ETH)

    assert snapshot.status == "UNAVAILABLE"
    assert snapshot.price_usd is None
    assert snapshot.price_eur is None
    assert snapshot.change_24h_pct is None
    assert snapshot.provider_count == 0

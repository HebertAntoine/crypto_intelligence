from __future__ import annotations

import pytest

from crypto_intel.core.enums import Asset, FetchStatus
from crypto_intel.providers.base import FetchRequest
from crypto_intel.providers.events import official_regulation
from crypto_intel.providers.events.official_regulation import OfficialRegulatoryFeedProvider
from crypto_intel.providers.http import HTTPResult
from crypto_intel.providers.macro import fred, fred_public
from crypto_intel.providers.macro.fred import FredProvider
from crypto_intel.providers.macro.fred_public import FredPublicCsvProvider
from crypto_intel.providers.market.breadth import MarketBreadthProvider
from crypto_intel.providers.market.coingecko import (
    CoinGeckoProvider,
    coingecko_request_config,
)
from crypto_intel.providers.news import rss
from crypto_intel.providers.news.rss import RSSRegulationProvider
from crypto_intel.providers.regulation.sec_edgar import SecEdgarFilingsProvider
from crypto_intel.settings import get_settings, reload_settings


class _NoNetwork:
    async def get_json(self, *args, **kwargs):
        raise AssertionError("network must not be called")

    async def get_text(self, *args, **kwargs):
        raise AssertionError("network must not be called")


class _FredAPI:
    async def get_json(self, *args, **kwargs) -> HTTPResult:
        return HTTPResult(
            FetchStatus.OK,
            {"observations": [{"date": "2026-10-24", "value": "4.25"}]},
        )


class _FredCSV:
    def __init__(self) -> None:
        self.requested: list[str] = []

    async def get_text(self, *args, **kwargs) -> HTTPResult:
        self.requested.append(str(kwargs["params"]["id"]))
        return HTTPResult(FetchStatus.OK, "observation_date,VALUE\n2026-08-01,123.4\n")


@pytest.mark.asyncio
async def test_coingecko_is_off_by_default_until_rights_are_confirmed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COINGECKO_COMMERCIAL_USE_AUTHORIZED", "false")
    monkeypatch.setenv("COINGECKO_API_KEY", "")
    monkeypatch.setenv("COINGECKO_ATTRIBUTION_CONFIGURED", "false")
    reload_settings()
    try:
        providers = (CoinGeckoProvider(), MarketBreadthProvider())
        for provider in providers:
            status = await provider.available()
            assert not status.available
            assert "not fully configured" in status.reason

        result = await providers[0].fetch(
            FetchRequest(capability="market.marketcap", asset=Asset.BTC)
        )
        assert result.status is FetchStatus.NOT_CONFIGURED

        result = await providers[1].fetch(FetchRequest(capability="market.breadth"))
        assert result.status is FetchStatus.NOT_CONFIGURED

        monkeypatch.setenv("COINGECKO_COMMERCIAL_USE_AUTHORIZED", "true")
        monkeypatch.setenv("COINGECKO_API_KEY", "paid-key")
        monkeypatch.setenv("COINGECKO_ATTRIBUTION_CONFIGURED", "true")
        reload_settings()
        for provider in providers:
            assert (await provider.available()).available
        base_url, headers = coingecko_request_config()
        assert base_url == "https://pro-api.coingecko.com/api/v3"
        assert headers == {"x-cg-pro-api-key": "paid-key"}
    finally:
        monkeypatch.delenv("COINGECKO_COMMERCIAL_USE_AUTHORIZED", raising=False)
        monkeypatch.delenv("COINGECKO_API_KEY", raising=False)
        monkeypatch.delenv("COINGECKO_ATTRIBUTION_CONFIGURED", raising=False)
        reload_settings()


@pytest.mark.asyncio
async def test_fred_sources_fail_closed_without_documented_content_permission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FRED_API_KEY", "access-key-is-not-a-right")
    monkeypatch.setenv("FRED_CONTENT_USE_AUTHORIZED", "false")
    monkeypatch.setattr(fred, "get_http", lambda: _NoNetwork())
    monkeypatch.setattr(fred_public, "get_http", lambda: _NoNetwork())
    reload_settings()
    try:
        api = await FredProvider().fetch(FetchRequest(capability="macro.series"))
        csv = await FredPublicCsvProvider().fetch(
            FetchRequest(capability="macro.pce")
        )
        assert api.status is FetchStatus.NOT_CONFIGURED
        assert csv.status is FetchStatus.NOT_CONFIGURED
        assert "storage/AI-system use" in api.message
    finally:
        monkeypatch.delenv("FRED_API_KEY", raising=False)
        monkeypatch.delenv("FRED_CONTENT_USE_AUTHORIZED", raising=False)
        reload_settings()


@pytest.mark.asyncio
async def test_fred_api_surfaces_excluded_third_party_series_on_partial_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FRED_API_KEY", "test-key")
    monkeypatch.setenv("FRED_CONTENT_USE_AUTHORIZED", "true")
    monkeypatch.setenv("FRED_THIRD_PARTY_REDISTRIBUTION_AUTHORIZED", "false")
    monkeypatch.setattr(fred, "get_http", lambda: _FredAPI())
    reload_settings()
    try:
        result = await FredProvider().fetch(
            FetchRequest(
                capability="macro.series",
                params={"series": ["DFF", "BAMLH0A0HYM2", "VIXCLS"]},
            )
        )

        assert result.ok
        assert {item.metric for item in result.observations} == {"macro.fed_funds_rate"}
        excluded = result.raw["excluded_series"]
        assert {item["series_id"] for item in excluded} == {"BAMLH0A0HYM2", "VIXCLS"}
        assert {item["reason"] for item in excluded} == {
            "THIRD_PARTY_REDISTRIBUTION_NOT_AUTHORIZED"
        }
    finally:
        monkeypatch.delenv("FRED_API_KEY", raising=False)
        monkeypatch.delenv("FRED_CONTENT_USE_AUTHORIZED", raising=False)
        monkeypatch.delenv("FRED_THIRD_PARTY_REDISTRIBUTION_AUTHORIZED", raising=False)
        reload_settings()


@pytest.mark.asyncio
async def test_fred_public_csv_reports_and_does_not_request_excluded_series(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FredCSV()
    monkeypatch.setenv("FRED_CONTENT_USE_AUTHORIZED", "true")
    monkeypatch.setenv("FRED_THIRD_PARTY_REDISTRIBUTION_AUTHORIZED", "false")
    monkeypatch.setattr(fred_public, "get_http", lambda: fake)
    reload_settings()
    try:
        result = await FredPublicCsvProvider().fetch(FetchRequest(capability="macro.credit"))

        assert result.ok
        excluded = result.raw["excluded_series"]
        assert {item["series_id"] for item in excluded} == {
            "BAMLH0A0HYM2",
            "BAMLC0A0CM",
        }
        assert "BAMLH0A0HYM2" not in fake.requested
        assert "BAMLC0A0CM" not in fake.requested
    finally:
        monkeypatch.delenv("FRED_THIRD_PARTY_REDISTRIBUTION_AUTHORIZED", raising=False)
        monkeypatch.delenv("FRED_CONTENT_USE_AUTHORIZED", raising=False)
        reload_settings()


@pytest.mark.asyncio
async def test_sec_contact_must_be_real_and_is_never_sent_from_placeholder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEC_USER_AGENT", "CryptoIntelligence/1.0 (contact@example.com)")
    reload_settings()
    try:
        assert not get_settings().sec_user_agent_configured
        provider = SecEdgarFilingsProvider()
        assert not (await provider.available()).available
        assert provider._headers() is None

        result = await provider.fetch(FetchRequest(capability="events.regulation.sec_filings"))
        assert result.status is FetchStatus.NOT_CONFIGURED

        feeds = {
            "feeds": {
                "regulation": [
                    {
                        "name": "SEC",
                        "url": "https://www.sec.gov/news/pressreleases.rss",
                    }
                ]
            }
        }
        monkeypatch.setattr(rss, "providers_config", lambda: feeds)
        monkeypatch.setattr(rss, "get_http", lambda: _NoNetwork())
        rss_result = await RSSRegulationProvider().fetch(
            FetchRequest(capability="regulation.feed")
        )
        assert rss_result.status is FetchStatus.NO_DATA
        assert "NOT_CONFIGURED" in rss_result.message

        monkeypatch.setattr(official_regulation, "providers_config", lambda: feeds)
        monkeypatch.setattr(official_regulation, "get_http", lambda: _NoNetwork())
        official_result = await OfficialRegulatoryFeedProvider().fetch(
            FetchRequest(capability="events.regulation.feeds")
        )
        assert official_result.status is FetchStatus.NO_DATA
        assert "NOT_CONFIGURED" in official_result.message

        monkeypatch.setenv("SEC_USER_AGENT", "CryptoIntelligence/1.0 (operator@company.test)")
        reload_settings()
        assert not get_settings().sec_user_agent_configured

        agent = "CryptoIntelligence/1.0 (operator@company.fr)"
        monkeypatch.setenv("SEC_USER_AGENT", agent)
        reload_settings()
        assert get_settings().sec_user_agent_configured
        assert (await provider.available()).available
        assert provider._headers() == {"User-Agent": agent, "Accept": "application/json"}
    finally:
        monkeypatch.delenv("SEC_USER_AGENT", raising=False)
        reload_settings()

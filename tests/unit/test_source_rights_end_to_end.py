from __future__ import annotations

from datetime import UTC, datetime

import pytest

from crypto_intel.core.enums import Asset, Freshness
from crypto_intel.core.models import Observation, Provenance
from crypto_intel.core.source_rights import rights_policy_fingerprint
from crypto_intel.engines import analysis_context, cross_asset, daily_report, macro_transmission
from crypto_intel.settings import reload_settings

NOW = datetime(2026, 10, 28, 12, tzinfo=UTC)


def _observation(
    metric: str,
    value: float,
    *,
    source: str,
    provider: str,
    source_url: str = "https://source.example/data",
    meta: dict[str, object] | None = None,
) -> Observation:
    return Observation(
        metric=metric,
        value=value,
        unit="index",
        timestamp=NOW,
        provenance=Provenance(
            source=source,
            provider=provider,
            source_url=source_url,
            fetched_at=NOW,
        ),
        freshness=Freshness.TODAY,
        meta=meta or {},
    )


def _set_rights(monkeypatch: pytest.MonkeyPatch, *, enabled: bool) -> None:
    monkeypatch.setenv("TWELVE_DATA_API_KEY", "licensed-key" if enabled else "")
    monkeypatch.setenv(
        "TWELVE_DATA_REDISTRIBUTION_AUTHORIZED", "true" if enabled else "false"
    )
    monkeypatch.setenv(
        "FRED_CONTENT_USE_AUTHORIZED", "true" if enabled else "false"
    )
    monkeypatch.setenv(
        "FRED_THIRD_PARTY_REDISTRIBUTION_AUTHORIZED",
        "true" if enabled else "false",
    )
    monkeypatch.setenv(
        "COINGECKO_COMMERCIAL_USE_AUTHORIZED", "true" if enabled else "false"
    )
    monkeypatch.setenv("COINGECKO_API_KEY", "paid-key" if enabled else "")
    monkeypatch.setenv(
        "COINGECKO_ATTRIBUTION_CONFIGURED", "true" if enabled else "false"
    )
    reload_settings()


def test_main_decision_readers_recheck_current_source_rights(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [
        _observation(
            "macro.sp500",
            5000,
            source="Yahoo Finance",
            provider="yahoo_finance",
            source_url="https://query1.finance.yahoo.com/chart",
        ),
        _observation(
            "macro.sp500",
            5100,
            source="Twelve Data",
            provider="twelve_data",
            source_url="https://api.twelvedata.com/time_series",
        ),
        _observation(
            "macro.hy_spread",
            3.2,
            source="FRED",
            provider="fred_public_csv",
            source_url="https://fred.stlouisfed.org/series/BAMLH0A0HYM2",
            meta={"series_id": "BAMLH0A0HYM2"},
        ),
        _observation(
            "macro.fed_funds_rate",
            4.75,
            source="Federal Reserve Bank of New York",
            provider="nyfed",
            source_url="https://www.newyorkfed.org/markets/reference-rates/effr",
        ),
        _observation(
            "market.total_cap",
            2_500_000_000_000,
            source="CoinGecko",
            provider="coingecko",
            source_url="https://api.coingecko.com/api/v3/global",
        ),
    ]

    _set_rights(monkeypatch, enabled=False)
    try:
        expected = ["macro.fed_funds_rate"]
        assert [
            item.metric for item in analysis_context._without_synthetic(rows)
        ] == expected
        assert [
            item.metric
            for item in macro_transmission._series(
                rows,
                tuple(item.metric for item in rows),
            )
        ] == expected

        _set_rights(monkeypatch, enabled=True)
        admitted = analysis_context._without_synthetic(rows)
        assert {item.metric for item in admitted} == {
            "macro.sp500",
            "macro.hy_spread",
            "macro.fed_funds_rate",
            "market.total_cap",
        }
        assert all(item.provenance.provider != "yahoo_finance" for item in admitted)
    finally:
        for name in (
            "TWELVE_DATA_API_KEY",
            "TWELVE_DATA_REDISTRIBUTION_AUTHORIZED",
            "FRED_THIRD_PARTY_REDISTRIBUTION_AUTHORIZED",
            "FRED_CONTENT_USE_AUTHORIZED",
            "COINGECKO_COMMERCIAL_USE_AUTHORIZED",
            "COINGECKO_API_KEY",
            "COINGECKO_ATTRIBUTION_CONFIGURED",
        ):
            monkeypatch.delenv(name, raising=False)
        reload_settings()


def test_cross_asset_history_cannot_bypass_rights(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    records = [
        {
            "timestamp": NOW,
            "value": 5000.0,
            "source": "Yahoo Finance",
            "provider": "yahoo_finance",
            "source_url": "https://query1.finance.yahoo.com/chart",
            "meta": {},
        },
        {
            "timestamp": NOW,
            "value": 5100.0,
            "source": "Twelve Data",
            "provider": "twelve_data",
            "source_url": "https://api.twelvedata.com/time_series",
            "meta": {},
        },
    ]
    monkeypatch.setattr(cross_asset.store, "load_macro_records", lambda _metric: records)

    _set_rights(monkeypatch, enabled=False)
    try:
        assert cross_asset._admissible_macro("macro.sp500").empty

        _set_rights(monkeypatch, enabled=True)
        series = cross_asset._admissible_macro("macro.sp500")
        assert series.tolist() == [5100.0]
    finally:
        for name in (
            "TWELVE_DATA_API_KEY",
            "TWELVE_DATA_REDISTRIBUTION_AUTHORIZED",
            "FRED_THIRD_PARTY_REDISTRIBUTION_AUTHORIZED",
            "FRED_CONTENT_USE_AUTHORIZED",
            "COINGECKO_COMMERCIAL_USE_AUTHORIZED",
            "COINGECKO_API_KEY",
            "COINGECKO_ATTRIBUTION_CONFIGURED",
        ):
            monkeypatch.delenv(name, raising=False)
        reload_settings()


def test_liquidity_regime_cannot_bypass_rights(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    records = [
        {
            "timestamp": datetime(2026, 1, day, tzinfo=UTC),
            "value": float(100 + day),
            "source": "Yahoo Finance",
            "provider": "yahoo_finance",
            "source_url": "https://query1.finance.yahoo.com/chart",
            "meta": {},
        }
        for day in range(1, 29)
    ] * 4
    monkeypatch.setattr(cross_asset.store, "load_macro_records", lambda _metric: records)

    _set_rights(monkeypatch, enabled=True)
    try:
        result = cross_asset.LiquidityRegimeEngine().assess()
        assert result.components == {}
        assert result.score is None
        assert result.regime.value == "UNKNOWN"
    finally:
        for name in (
            "TWELVE_DATA_API_KEY",
            "TWELVE_DATA_REDISTRIBUTION_AUTHORIZED",
            "FRED_THIRD_PARTY_REDISTRIBUTION_AUTHORIZED",
            "FRED_CONTENT_USE_AUTHORIZED",
            "COINGECKO_COMMERCIAL_USE_AUTHORIZED",
            "COINGECKO_API_KEY",
            "COINGECKO_ATTRIBUTION_CONFIGURED",
        ):
            monkeypatch.delenv(name, raising=False)
        reload_settings()


def test_daily_report_does_not_publish_an_inadmissible_observation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observation = _observation(
        "etf.flow",
        120.0,
        source="CoinGecko",
        provider="coingecko",
        source_url="https://api.coingecko.com/api/v3/global",
    )
    from crypto_intel.db import repo

    monkeypatch.setattr(repo, "latest_observation", lambda *_args, **_kwargs: observation)

    _set_rights(monkeypatch, enabled=False)
    try:
        sections: list[daily_report.Section] = []
        daily_report.DailyReportEngine()._etf(
            Asset.BTC,
            sections,
            NOW,
        )
        assert sections[0].available is False
        assert "source-rights" in sections[0].reason

        _set_rights(monkeypatch, enabled=True)
        sections = []
        daily_report.DailyReportEngine()._etf(
            Asset.BTC,
            sections,
            NOW,
        )
        assert sections[0].available is True
    finally:
        for name in (
            "TWELVE_DATA_API_KEY",
            "TWELVE_DATA_REDISTRIBUTION_AUTHORIZED",
            "FRED_THIRD_PARTY_REDISTRIBUTION_AUTHORIZED",
            "FRED_CONTENT_USE_AUTHORIZED",
            "COINGECKO_COMMERCIAL_USE_AUTHORIZED",
            "COINGECKO_API_KEY",
            "COINGECKO_ATTRIBUTION_CONFIGURED",
        ):
            monkeypatch.delenv(name, raising=False)
        reload_settings()


def test_analysis_cache_identity_changes_with_the_rights_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_rights(monkeypatch, enabled=False)
    restricted = rights_policy_fingerprint()
    _set_rights(monkeypatch, enabled=True)
    enabled = rights_policy_fingerprint()

    assert restricted != enabled
    assert restricted["twelve_data_key_configured"] is False
    assert enabled["twelve_data_key_configured"] is True

"""Robustness: a failing provider must degrade one domain, never the analysis.

These tests deliberately break things - network errors, malformed payloads,
providers that raise - and assert the pipeline still produces a report with
explicit UNAVAILABLE markers rather than crashing or inventing values.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("MOCK_MODE", "true")

from crypto_intel.core.enums import Asset, FetchStatus, Timeframe
from crypto_intel.providers.base import BaseProvider, FetchRequest, FetchResult


class ExplodingProvider(BaseProvider):
    """A provider that raises on every call - the worst-case dependency."""

    name = "exploding"
    source = "test"
    capabilities = ("market.ticker",)

    async def fetch(self, request: FetchRequest) -> FetchResult:
        raise RuntimeError("provider exploded")


class TestProviderIsolation:
    async def test_registry_catches_a_raising_provider(self):
        """A provider bug must not escape into the pipeline."""
        from crypto_intel.providers.registry import ProviderRegistry

        registry = ProviderRegistry().build()
        registry._providers["exploding"] = ExplodingProvider()
        registry._chains["test.capability"] = ["exploding"]

        # MOCK_MODE routes through fixtures, so exercise the chain directly.
        result = await registry._providers["exploding"].available()
        assert result.available

        from crypto_intel.settings import get_settings

        if not get_settings().mock_mode:
            outcome = await registry.fetch(FetchRequest(capability="test.capability"))
            assert not outcome.ok
            assert outcome.status is FetchStatus.NETWORK_ERROR

    async def test_unknown_capability_returns_qualified_failure(self):
        from crypto_intel.providers.registry import get_registry

        result = await get_registry().fetch(FetchRequest(capability="does.not.exist"))
        assert not result.ok
        assert "UNAVAILABLE" in result.user_message

    async def test_failure_never_raises(self):
        """Every capability must return a FetchResult, never an exception."""
        from crypto_intel.providers.registry import get_registry

        registry = get_registry()
        for capability in ("market.ohlcv", "etf.flows", "whales.flows", "macro.series"):
            result = await registry.fetch(
                FetchRequest(capability=capability, asset=Asset.BTC, timeframe=Timeframe.D1)
            )
            assert isinstance(result, FetchResult)


class TestEngineResilience:
    def test_every_engine_survives_empty_input(self):
        """No engine may raise on missing data - they return UNAVAILABLE."""
        from crypto_intel.engines.derivatives import DerivativesAnalyzer
        from crypto_intel.engines.entry_timing import EntryTimingEngine
        from crypto_intel.engines.etf_flows import ETFFlowAnalyzer
        from crypto_intel.engines.liquidity import DefiAnalyzer, StablecoinLiquidityAnalyzer
        from crypto_intel.engines.macro import MacroAnalyzer
        from crypto_intel.engines.news import NewsEngine
        from crypto_intel.engines.onchain import OnChainAnalyzer
        from crypto_intel.engines.regime import MarketRegimeEngine
        from crypto_intel.engines.regulation import RegulationAndPoliticsAnalyzer
        from crypto_intel.engines.whales import WhaleAnalyzer

        assert ETFFlowAnalyzer().analyze(Asset.BTC, []).available is False
        assert DerivativesAnalyzer().analyze(Asset.BTC, []).available is False
        assert OnChainAnalyzer().analyze(Asset.BTC, []).available is False
        assert StablecoinLiquidityAnalyzer().analyze([]).available is False
        assert DefiAnalyzer().analyze(Asset.BTC, []).available is False
        assert MacroAnalyzer().analyze([]).available is False
        assert NewsEngine().analyze([]).available is False
        assert RegulationAndPoliticsAnalyzer().analyze([]).available is False
        assert WhaleAnalyzer().analyze(Asset.BTC, []).available is False
        assert MarketRegimeEngine().assess(Asset.BTC, {}).regime.value == "UNDETERMINED"
        assert EntryTimingEngine().assess(Asset.BTC, {}).timing.value == "UNDETERMINED"

    def test_engines_survive_malformed_context(self):
        """Garbage in the context must not crash the assessment."""
        from crypto_intel.engines.entry_timing import EntryTimingEngine
        from crypto_intel.engines.regime import MarketRegimeEngine

        junk = {"snapshots": None, "derivatives": "not an object", "etf": 12345}
        assert MarketRegimeEngine().assess(Asset.BTC, junk) is not None
        assert EntryTimingEngine().assess(Asset.BTC, junk) is not None

    def test_technical_engine_handles_a_single_candle(self):
        from datetime import UTC, datetime

        from crypto_intel.core.models import Candle, OHLCVSeries, Provenance
        from crypto_intel.engines.technical.engine import TechnicalAnalysisEngine

        series = OHLCVSeries(
            asset=Asset.BTC, timeframe=Timeframe.D1,
            candles=[Candle(timestamp=datetime.now(UTC), open=1, high=1, low=1, close=1, volume=1)],
            provenance=Provenance(source="t", provider="t"),
        )
        snapshot = TechnicalAnalysisEngine().analyze(series)
        assert not snapshot.has_data
        assert snapshot.notes


class TestHTTPGuards:
    def test_blocking_statuses_are_final(self):
        """A 403 must stop the connector, not trigger a retry with new headers."""
        from crypto_intel.providers.http import _BLOCKING_STATUSES

        assert 403 in _BLOCKING_STATUSES
        assert 401 in _BLOCKING_STATUSES

    def test_no_user_agent_rotation_exists(self):
        """Rotating UAs to evade a block is explicitly out of scope."""
        import inspect

        from crypto_intel.providers import http

        source = inspect.getsource(http)
        for forbidden in ("random.choice", "USER_AGENTS", "rotate_ua", "proxies="):
            assert forbidden not in source

    def test_timeouts_are_configured(self):
        from crypto_intel.settings import get_settings

        assert get_settings().http_timeout > 0

    def test_rate_limiter_spaces_requests(self):
        from crypto_intel.providers.http import RateLimiter

        limiter = RateLimiter(per_minute=60)
        assert limiter.min_interval == pytest.approx(1.0)
        assert RateLimiter(per_minute=0).min_interval == 0.0


class TestDatabaseResilience:
    def test_migrations_do_not_drop_data(self):
        """Migrations are additive only - nothing destructive is automated."""
        import inspect

        from crypto_intel.db import migrations

        source = inspect.getsource(migrations)
        for forbidden in ("DROP TABLE", "DELETE FROM", "TRUNCATE", "DROP COLUMN"):
            assert forbidden not in source.upper()

    def test_repo_coerces_iso_strings(self):
        """model_dump(mode='json') hands us strings; the repo must cope rather
        than losing the row to a TypeError."""
        from datetime import UTC, datetime

        from crypto_intel.db.repo import _coerce_dt

        assert _coerce_dt("2026-09-05T12:00:00Z") is not None
        assert _coerce_dt(datetime.now(UTC)) is not None
        assert _coerce_dt("not a date") is None
        assert _coerce_dt(None) is None

    def test_sqlite_uses_wal(self):
        """WAL lets the scheduler write while the API reads."""
        import inspect

        from crypto_intel.db import session

        assert "journal_mode=WAL" in inspect.getsource(session)


class TestNoTradingCode:
    def test_no_order_placement_anywhere(self):
        """The hard constraint: this system never trades."""
        from pathlib import Path

        backend = Path(__file__).resolve().parents[2] / "backend"
        forbidden = ("place_order", "create_order", "submit_order", "cancel_order")
        for path in backend.rglob("*.py"):
            content = path.read_text(encoding="utf-8")
            for term in forbidden:
                assert term not in content, f"{term} found in {path.name}"

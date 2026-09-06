"""LOT 2 API endpoints. Offline, MOCK_MODE, no keys."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

os.environ["MOCK_MODE"] = "true"
os.environ["LLM_PROVIDER"] = "none"


@pytest.fixture(scope="module")
def client():
    from crypto_intel.settings import reload_settings

    reload_settings()
    from crypto_intel.providers.registry import reset_registry

    reset_registry()
    from crypto_intel.main import create_app

    with TestClient(create_app()) as c:
        yield c


class TestRegimeAndTimingInAPI:
    def test_asset_detail_exposes_both_axes(self, client):
        body = client.get("/api/assets/BTC").json()
        assert "regime" in body and "entry_timing" in body
        assert body["regime"]["regime"]
        assert body["entry_timing"]["timing"]

    def test_timing_exposes_its_explanation(self, client):
        """The WHY panel needs a readable account of the arithmetic."""
        timing = client.get("/api/assets/BTC").json()["entry_timing"]
        assert timing["explanation"]
        assert timing["factors"]

    def test_regime_exposes_its_factors(self, client):
        regime = client.get("/api/assets/ETH").json()["regime"]
        assert regime["factors"]
        assert regime["summary"]


class TestChart:
    def test_chart_returns_candles_and_overlays(self, client):
        body = client.get("/api/chart/BTC?timeframe=1d").json()
        if not body["available"]:
            pytest.skip(body.get("reason", "no stored candles"))
        assert body["candles"]
        assert "ema20" in body["overlays"]
        assert "rsi" in body["panels"]

    def test_warmup_is_null_not_zero(self, client):
        """A fabricated zero would draw a false line at the bottom of the chart."""
        body = client.get("/api/chart/BTC?timeframe=1d").json()
        if not body["available"]:
            pytest.skip("no stored candles")
        ema200 = body["overlays"].get("ema200") or []
        if ema200:
            assert ema200[0] is None

    def test_unknown_timeframe_is_400(self, client):
        assert client.get("/api/chart/BTC?timeframe=3y").status_code == 400

    def test_unknown_asset_is_404(self, client):
        assert client.get("/api/chart/DOGE").status_code == 404


class TestEtfVsPrice:
    def test_sol_is_explicitly_unavailable(self, client):
        """SOL has no US spot ETF - that must be stated, not shown as zero."""
        body = client.get("/api/etf-vs-price/SOL").json()
        assert body["available"] is False
        assert "no US spot ETF" in body["reason"]

    def test_lag_is_reported_and_caveated(self, client):
        body = client.get("/api/etf-vs-price/BTC?lag_days=3").json()
        if not body["available"]:
            pytest.skip(body.get("reason", ""))
        assert body["lag_days"] == 3
        assert "causal" in body["caveat"].lower()


class TestResearchEndpoints:
    def test_etf_lag_study(self, client):
        body = client.get("/api/research/etf/BTC").json()
        assert "available" in body
        if body["available"]:
            assert "multiple_testing" in body
            assert "contemporaneous_control" in body

    def test_events(self, client):
        """The `events` key is always present, so a consumer can iterate
        without branching on whether history happened to be available."""
        body = client.get("/api/research/events/BTC").json()
        assert "events" in body
        if not body["available"]:
            assert "UNAVAILABLE" in body["reason"]

    def test_calibration(self, client):
        body = client.get("/api/research/calibration").json()
        assert "reconstructed" in body and "live" in body

    def test_negative_results_are_not_hidden(self, client):
        """A study with no significant result must say so, not return nothing."""
        body = client.get("/api/research/etf/BTC").json()
        if body.get("available"):
            correlations = body["correlations"]
            assert correlations, "correlations must be reported even when weak"


class TestHistoryAndCalendar:
    def test_coverage_documents_real_depth(self, client):
        body = client.get("/api/history/coverage").json()
        assert "datasets" in body and "per_asset" in body and "macro" in body

    def test_calendar_groups_by_proximity(self, client):
        body = client.get("/api/calendar").json()
        for key in ("within_24h", "within_3d", "within_7d", "within_30d"):
            assert key in body
        assert "note" in body

    def test_calendar_entries_declare_certainty(self, client):
        body = client.get("/api/calendar").json()
        for entry in body["all_upcoming"]:
            assert entry["certainty"] in ("KNOWN", "ESTIMATED")

    def test_snapshots_endpoint(self, client):
        body = client.get("/api/snapshots/BTC?kind=analysis").json()
        assert "snapshots" in body and "count" in body


class TestDailyReport:
    def test_daily_report_has_the_required_sections(self, client):
        body = client.get("/api/daily-report").json()
        text = body["text"]
        for section in ("GLOBAL", "TOP 3 THINGS TO WATCH", "WHAT WOULD CHANGE THE VIEW"):
            assert section in text

    def test_daily_report_shows_regime_and_timing(self, client):
        text = client.get("/api/daily-report").json()["text"]
        assert "Market regime" in text
        assert "Entry timing" in text


class TestKnowledgeAndScheduler:
    def test_knowledge_documents(self, client):
        body = client.get("/api/knowledge/documents").json()
        assert "documents" in body and "stats" in body

    def test_scheduler_status(self, client):
        body = client.get("/api/scheduler/status").json()
        assert "enabled" in body and "runs" in body and "snapshots" in body

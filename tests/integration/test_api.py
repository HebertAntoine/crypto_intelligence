"""API endpoint tests. Run entirely in MOCK_MODE - no network, no keys."""

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


class TestHealth:
    def test_health_reports_mode_and_llm(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert body["mock_mode"] is True
        assert "llm" in body

    def test_root(self, client):
        assert client.get("/").status_code == 200


class TestAssets:
    def test_lists_three_assets(self, client):
        r = client.get("/api/assets")
        assert r.status_code == 200
        body = r.json()
        assert {a["asset"] for a in body} == {"BTC", "ETH", "SOL"}

    def test_card_contains_convictions(self, client):
        card = client.get("/api/assets").json()[0]
        assert card["available"]
        for field in ("price", "conviction_short", "conviction_medium",
                      "conviction_long", "confidence", "market_regime"):
            assert field in card

    def test_detail_returns_full_analysis(self, client):
        body = client.get("/api/assets/BTC").json()
        for section in ("scores", "conviction", "analysts", "contradictions",
                        "scenarios", "synthesis", "technical", "domains", "sources"):
            assert section in body

    def test_unknown_asset_is_404(self, client):
        r = client.get("/api/assets/DOGE")
        assert r.status_code == 404
        assert "BTC" in r.json()["detail"]

    def test_case_insensitive(self, client):
        assert client.get("/api/assets/btc").status_code == 200


class TestDomainsAndReport:
    def test_technical_endpoint(self, client):
        body = client.get("/api/assets/ETH/technical").json()
        assert "timeframes" in body and "mtf" in body

    def test_technical_single_timeframe(self, client):
        body = client.get("/api/assets/ETH/technical?timeframe=1d").json()
        assert body["timeframe"] == "1d"

    def test_bad_timeframe_is_400(self, client):
        assert client.get("/api/assets/ETH/technical?timeframe=3y").status_code == 400

    def test_domain_endpoint(self, client):
        body = client.get("/api/assets/BTC/domain/etf").json()
        assert body["domain"] == "etf"
        assert "data" in body

    def test_unknown_domain_is_404(self, client):
        assert client.get("/api/assets/BTC/domain/nonsense").status_code == 404

    def test_report_is_text(self, client):
        body = client.get("/api/assets/SOL/report").json()
        assert "MARKET INTELLIGENCE" in body["text"]
        assert "CONVICTION" in body["text"]

    def test_report_shows_unavailable_explicitly(self, client):
        """SOL has no US spot ETF - the report must say so, not show zero."""
        text = client.get("/api/assets/SOL/report").json()["text"]
        assert "UNAVAILABLE" in text

    def test_sources_endpoint_lists_failures(self, client):
        body = client.get("/api/assets/BTC/sources").json()
        assert body["total"] > 0
        assert isinstance(body["sources"], list)


class TestGlobalAndAux:
    def test_global_market_view(self, client):
        body = client.get("/api/global").json()
        for section in ("risk_regime", "assets", "etf", "liquidity", "macro",
                        "news", "regulation", "geopolitics", "calendar", "alerts"):
            assert section in body

    def test_providers_shows_unconfigured(self, client):
        body = client.get("/api/providers").json()
        assert "providers" in body

    def test_alerts(self, client):
        assert isinstance(client.get("/api/alerts").json(), list)

    def test_events(self, client):
        body = client.get("/api/events").json()
        assert "upcoming" in body and "recent" in body

    def test_knowledge_stats(self, client):
        body = client.get("/api/knowledge/stats").json()
        assert "documents" in body and "chunks" in body

    def test_knowledge_search(self, client):
        r = client.get("/api/knowledge/search?q=divergence")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_evaluation_endpoint(self, client):
        body = client.get("/api/evaluation").json()
        assert "total_reports" in body

    def test_reports_list(self, client):
        assert isinstance(client.get("/api/reports").json(), list)


class TestExplainability:
    def test_why_returns_full_provenance(self, client):
        """Clicking a conclusion must reveal source, value and timestamp."""
        detail = client.get("/api/assets/BTC").json()
        evidence_ids = []
        for card in detail["scores"].values():
            evidence_ids.extend(card.get("evidence_ids") or [])
        if not evidence_ids:
            pytest.skip("no evidence ids in this run")

        r = client.post("/api/why/batch", json=evidence_ids[:5])
        assert r.status_code == 200
        for item in r.json():
            assert item["source"] and item["metric"]
            assert "timestamp" in item and "freshness" in item

    def test_unknown_evidence_is_404(self, client):
        assert client.get("/api/why/obs_doesnotexist").status_code == 404

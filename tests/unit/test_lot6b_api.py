"""LOT 6B endpoints.

The contract these guard is that a client can never render a negative result
without the context that bounds it: the funnel that produced it, and the
detection floor below which "nothing found" means nothing.
"""

from __future__ import annotations

import pytest
from backend.crypto_intel.main import create_app
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


class TestEvidenceEndpoints:
    def test_ladder_is_served_without_a_research_run(self, client):
        payload = client.get("/api/evidence/ladder").json()
        levels = [entry["level"] for entry in payload["levels"]]
        assert levels == sorted(levels)
        assert levels == list(range(8))
        assert payload["actionable_from"] == 6

    def test_evidence_always_carries_its_funnel(self, client):
        response = client.get("/api/evidence")
        if response.status_code == 404:
            pytest.skip("lot6b.json not generated in this environment")
        payload = response.json()
        assert "funnel" in payload
        assert payload["funnel"]["stages"], "a verdict without a funnel hides its denominator"

    def test_funnel_stages_never_grow(self, client):
        response = client.get("/api/evidence")
        if response.status_code == 404:
            pytest.skip("lot6b.json not generated in this environment")
        counts = [stage["count"] for stage in response.json()["funnel"]["stages"]]
        assert counts == sorted(counts, reverse=True)

    def test_power_reports_the_floor_against_the_meaningful_effect(self, client):
        response = client.get("/api/power")
        if response.status_code == 404:
            pytest.skip("lot6b.json not generated in this environment")
        payload = response.json()
        assert payload["detection_floors"], "power without a floor cannot be read"
        for entry in payload["detection_floors"]:
            assert "meaningful_effect_pct" in entry
            assert "floor_above_meaningful" in entry

    def test_pooling_names_sol_as_unavailable_rather_than_omitting_it(self, client):
        response = client.get("/api/pooling")
        if response.status_code == 404:
            pytest.skip("dvol_pooled.json not generated in this environment")
        payload = response.json()
        assert "SOL" not in payload["assets_pooled"]
        assert "SOL" in payload["assets_unavailable"]

    def test_hypotheses_expose_the_multiple_testing_denominator(self, client):
        payload = client.get("/api/hypotheses").json()
        assert "tested_ever" in payload["summary"]
        assert payload["summary"]["tested_ever"] >= 0

    def test_missing_research_files_explain_how_to_generate_them(self, client):
        response = client.get("/api/redundancy")
        if response.status_code == 404:
            assert "lot6b" in response.json()["detail"]

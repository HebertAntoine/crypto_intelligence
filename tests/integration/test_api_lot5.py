"""LOT 5 endpoints, and the invariants the UI depends on.

The recurring assertion here is the separation: any endpoint that exposes a
recognition confidence must also expose an edge state, so no consumer can
render the first without the second.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from crypto_intel.main import create_app


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


def test_structure_endpoint_returns_all_layers(client):
    body = client.get("/api/structure/BTC?timeframe=4h").json()
    assert body["asset"] == "BTC"
    for key in ("location", "market_structure", "patterns", "separation_note"):
        assert key in body


def test_every_pattern_carries_an_edge_state(client):
    """Recognition confidence must never be exposed alone."""
    for symbol in ("BTC", "ETH", "SOL"):
        body = client.get(f"/api/structure/{symbol}?timeframe=4h").json()
        for pattern in body["patterns"]:
            assert "recognition_confidence" in pattern
            assert "edge_state" in pattern
            assert "NOT a probability" in pattern["separation_note"]


def test_pattern_declares_its_reliability_class(client):
    body = client.get("/api/structure/BTC?timeframe=1d").json()
    for pattern in body["patterns"]:
        assert pattern["pattern_class"] in (
            "DETERMINISTIC", "HEURISTIC", "HUMAN_LIKE", "EXPERIMENTAL"
        )


def test_structure_rejects_unknown_timeframe(client):
    assert client.get("/api/structure/BTC?timeframe=3y").status_code == 400


def test_structure_rejects_unknown_asset(client):
    assert client.get("/api/structure/DOGE").status_code == 404


def test_multi_timeframe_names_conflicts(client):
    body = client.get("/api/structure/BTC/multi-timeframe").json()
    assert "location" in body and "market_structure" in body
    # A conflict field must exist even when it is null.
    assert "conflict" in body["location"]


def test_entry_opportunity_shows_edge_separately(client):
    body = client.get("/api/entry-opportunity/BTC").json()
    assert body["state"] in (
        "VERY_UNFAVORABLE", "UNFAVORABLE", "NEUTRAL",
        "FAVORABLE", "VERY_FAVORABLE", "INSUFFICIENT_DATA",
    )
    assert "measured_edge_state" in body
    assert "not a claim that this is a good price" in body["disclaimer"]


def test_entry_opportunity_states_invalidation_first(client):
    body = client.get("/api/entry-opportunity/BTC").json()
    assert body["invalidation"]


def test_entry_opportunity_never_emits_an_order(client):
    for symbol in ("BTC", "ETH", "SOL"):
        body = client.get(f"/api/entry-opportunity/{symbol}").json()
        text = f" {body['statement']} {body['disclaimer']} {' '.join(body['why_now'])} ".upper()
        for banned in (" BUY ", " SELL ", "GO LONG", "GO SHORT", "ACHETER", "VENDRE"):
            assert banned not in text


def test_educational_claims_are_marked_as_claims(client):
    body = client.get("/api/knowledge/educational-claims").json()
    assert body["count"] > 0
    assert "cannot override any measured value" in body["note"]
    for claim in body["claims"]:
        assert claim["source_tier"] == 4
        assert "not a market fact" in claim["status_note"]


def test_source_hierarchy_marks_human_sources_as_non_data(client):
    body = client.get("/api/sources/hierarchy").json()
    assert body["tiers"]["5"]["is_primary_data"] is False
    assert body["tiers"]["1"]["is_primary_data"] is True
    assert "never override" in body["rule"]


def test_dataset_quality_is_honest_when_empty(client):
    body = client.get("/api/knowledge/dataset-quality").json()
    assert body["status"] in ("EMPTY", "OK")
    if body["status"] == "EMPTY":
        assert "INSUFFICIENT_DATA" in body["note"]


def test_human_vs_algorithm_refuses_metrics_without_a_gold_dataset(client):
    body = client.get("/api/knowledge/human-vs-algorithm").json()
    if body["status"] == "INSUFFICIENT_DATA":
        assert "meaningless" in body["note"]
    else:
        assert "Precision, recall and F1 are NOT reported" in body["metrics_note"]


def test_annotation_queue_targets_uncertainty(client):
    body = client.get("/api/knowledge/annotation-queue?limit=5").json()
    assert "selection_rule" in body
    for item in body["queue"]:
        assert 40 <= item["recognition_confidence"] <= 62


def test_cache_status_reports_the_detector_version(client):
    body = client.get("/api/structure/cache/status").json()
    assert body["detector_version"]
    assert "not approximations" in body["note"]


# --- LOT 4: hardened detection, and the geometry it now publishes ----------

def test_pattern_payload_carries_drawable_geometry(client):
    """The chart must be able to redraw a figure from the API alone.

    Bar indices are deliberately absent: they mean nothing to a chart holding a
    different window of candles, and they shift the moment the store gains
    earlier history. Every geometric element carries a timestamp instead.
    """
    for timeframe in ("4h", "1d"):
        body = client.get(f"/api/structure/BTC?timeframe={timeframe}").json()
        for pattern in body["patterns"]:
            geometry = pattern["geometry"]
            assert {"points", "trend_lines", "zones", "neckline"} <= set(geometry)
            for point in geometry["points"]:
                assert isinstance(point["time"], str)
                assert "T" in point["time"], "a geometry point must carry a timestamp"


def test_no_pattern_is_published_below_the_confidence_floor(client):
    """§14: below the floor nothing is announced at all, not announced quietly."""
    from crypto_intel.structure.patterns import DEFAULT_MIN_CONFIDENCE

    for symbol in ("BTC", "ETH", "SOL"):
        for timeframe in ("4h", "1d"):
            body = client.get(f"/api/structure/{symbol}?timeframe={timeframe}").json()
            for pattern in body["patterns"]:
                assert pattern["recognition_confidence"] >= DEFAULT_MIN_CONFIDENCE, (
                    f"{pattern['name']} published at "
                    f"{pattern['recognition_confidence']} on {symbol} {timeframe}"
                )


def test_every_pattern_confidence_is_decomposable(client):
    """§22: a confidence nobody can take apart must not be published."""
    body = client.get("/api/structure/BTC?timeframe=4h").json()
    for pattern in body["patterns"]:
        numeric = [
            v for v in pattern["components"].values()
            if isinstance(v, (int, float)) and not isinstance(v, bool)
        ]
        assert numeric, f"{pattern['name']} publishes a confidence with no components"

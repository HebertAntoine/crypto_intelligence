"""Endpoints behind the Charts & Patterns page.

The availability endpoint is the one every other route on that page consults
before deciding what it may compute, so its contract is pinned here: the shape
never changes, an empty database is a valid answer rather than an error, and a
series is never reported as usable without saying why.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from crypto_intel.main import create_app

REQUIRED_GROUPS = {"candles", "derivatives", "macro", "etf", "live_observations"}


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


def test_availability_returns_every_group(client):
    body = client.get("/api/analysis/data-availability").json()

    assert set(body["groups"]) >= REQUIRED_GROUPS
    assert "summary" in body
    assert "generated_at" in body


def test_empty_database_is_a_valid_answer_not_an_error(client):
    """The test database holds no history. That must read as zero, not a 500."""
    response = client.get("/api/analysis/data-availability")

    assert response.status_code == 200
    assert response.json()["summary"]["series"] >= 0


def test_every_record_states_a_reason(client):
    body = client.get("/api/analysis/data-availability").json()

    for records in body["groups"].values():
        for record in records:
            assert record["reason"], "a series without a reason is an unexplained verdict"
            assert isinstance(record["usable_for_live"], bool)
            assert isinstance(record["usable_for_backtest"], bool)


def test_group_filter_narrows_the_payload(client):
    body = client.get("/api/analysis/data-availability?group=candles").json()

    assert set(body["groups"]) == {"candles"}


def test_unknown_group_is_reported_rather_than_guessed(client):
    body = client.get("/api/analysis/data-availability?group=nonsense").json()

    assert "error" in body
    assert body["groups"] == {}


def test_backtest_filter_keeps_only_matching_series(client):
    body = client.get(
        "/api/analysis/data-availability?usable_for_backtest=false"
    ).json()

    for records in body["groups"].values():
        assert all(r["usable_for_backtest"] is False for r in records)


def test_payload_explains_the_live_backtest_distinction(client):
    """A consumer must not have to infer that these are different questions."""
    body = client.get("/api/analysis/data-availability").json()

    assert "usable_for_live" in body["note"]
    assert "usable_for_backtest" in body["note"]

"""LOT 4 endpoints, including the invariants they must never break."""

from __future__ import annotations

import httpx
import pytest

from crypto_intel.main import create_app


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_edge_endpoint_lists_every_asset(client):
    response = await client.get("/api/edge")
    assert response.status_code == 200
    body = response.json()
    assert set(body["assets"]) == {"BTC", "ETH", "SOL"}
    # The note must keep stating the separation, since the UI surfaces it.
    assert "never from the current regime" in body["note"]


async def test_edge_state_is_one_of_the_declared_values(client):
    allowed = {
        "POSITIVE_EDGE", "NEGATIVE_EDGE", "NO_MEASURABLE_EDGE", "INSUFFICIENT_DATA",
    }
    for symbol in ("BTC", "ETH", "SOL"):
        body = (await client.get(f"/api/edge/{symbol}")).json()
        assert body["state"] in allowed


async def test_today_separates_direction_from_edge(client):
    body = (await client.get("/api/today/BTC")).json()
    summary = body["decision_summary"]
    assert "market_direction" in summary
    assert "edge_state" in summary
    # They must be distinct fields, never collapsed into one score.
    assert summary["market_direction"] != summary["edge_state"]
    assert any("independently" in c for c in summary["caveats"])


async def test_today_includes_fast_market_data_contract(client):
    body = (await client.get("/api/today/BTC")).json()
    market = body["market_data"]
    assert market["asset"] == "BTC"
    assert market["status"] in {"LIVE", "DELAYED", "SNAPSHOT", "STALE", "UNAVAILABLE"}
    assert "price_usd" in market
    assert "price_eur" in market
    assert "change_24h_pct" in market
    assert "providers" in market
    if market["price_usd"] is not None:
        assert market["price_usd"] > 0
        assert market["provider_count"] >= 1


async def test_today_never_emits_an_order(client):
    for symbol in ("BTC", "ETH", "SOL"):
        summary = (await client.get(f"/api/today/{symbol}")).json()["decision_summary"]
        text = f" {summary['statement']} {' '.join(summary['caveats'])} ".upper()
        for banned in (" BUY ", " SELL ", "GO LONG", "GO SHORT"):
            assert banned not in text


async def test_crowding_direction_is_always_unknown(client):
    for symbol in ("BTC", "ETH", "SOL"):
        body = (await client.get(f"/api/leverage/{symbol}")).json()
        assert body["crowding"]["direction"] == "UNKNOWN"


async def test_volatility_endpoint_is_directionless(client):
    body = (await client.get("/api/volatility/BTC")).json()
    assert "BULLISH" not in body["interpretation"].upper()
    assert "BEARISH" not in body["interpretation"].upper()


async def test_unknown_asset_is_rejected(client):
    for path in ("/api/edge/DOGE", "/api/today/DOGE", "/api/volatility/XRP"):
        assert (await client.get(path)).status_code == 404


# --- LOT 4 completion endpoints ----------------------------------------


async def test_cross_asset_endpoint(client):
    body = (await client.get("/api/cross-asset/BTC")).json()
    assert body["asset"] == "BTC"
    assert isinstance(body["correlations"], list)


async def test_market_endpoints(client):
    for path in ("/api/market/ratios", "/api/market/breadth", "/api/market/liquidity"):
        assert (await client.get(path)).status_code == 200


async def test_dominance_is_real_or_unavailable(client):
    """The removed 'proxy' must not come back under any name."""
    dominance = (await client.get("/api/market/ratios")).json()["btc_dominance"]
    assert "shares_pct" not in dominance
    assert "proxy" not in str(dominance).lower() or not dominance.get("available")


async def test_breakout_endpoint_disclaims_prediction(client):
    body = (await client.get("/api/breakout/BTC")).json()
    assert "NOT a probability" in body["edge_note"]


async def test_breakout_rejects_unknown_timeframe(client):
    assert (await client.get("/api/breakout/BTC?timeframe=3y")).status_code == 400


async def test_liquidations_never_fabricate(client):
    body = (await client.get("/api/liquidations/BTC")).json()
    if body["data_state"] != "AVAILABLE":
        assert body["liquidations_24h_usd"] is None
        assert "not estimated" in body["conditions_note"]


async def test_feature_registry_is_all_point_in_time(client):
    body = (await client.get("/api/research/features")).json()
    for feature in body["features"]:
        assert feature["usable_for_backtest"]
    assert len(body["backtest_safe"]) == len(body["features"])


async def test_drift_endpoint_reports_insufficient_data_honestly(client):
    body = (await client.get("/api/research/drift")).json()
    for value in body["assets"].values():
        assert value["drift"]["state"] in (
            "NO_DRIFT", "MILD_DRIFT", "SIGNIFICANT_DRIFT",
            "INSUFFICIENT_LIVE_DATA", "NO_EXPECTATION",
        )

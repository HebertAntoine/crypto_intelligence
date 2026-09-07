"""One decision, one identity, across every endpoint that describes it.

Before this, each endpoint recomputed what it needed. Two calls a second apart
could describe two different moments and nothing said so, which let a screen
show a regime from one run beside funding from the next. Every number was
right; the combination was not.

These tests hold three properties:

  * endpoints of the same analysis return the same `analysis_id` and the same
    underlying readings;
  * the id is content-addressed, so a cold process reproduces it and a change
    of inputs changes it;
  * the live price is deliberately outside the identity, because it moves
    every second and the analysis does not.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from crypto_intel.core.enums import Asset, Timeframe
from crypto_intel.core.models import Candle
from crypto_intel.engines import analysis_context as ac
from crypto_intel.history import store

ASSETS = (Asset.BTC, Asset.ETH, Asset.SOL)


def _candles(n: int, start_price: float, step_hours: int, end: datetime) -> list[Candle]:
    out = []
    for i in range(n):
        price = start_price * (1 + 0.001 * i) + (i % 11) * start_price * 0.002
        ts = end - timedelta(hours=step_hours * (n - 1 - i))
        out.append(Candle(
            timestamp=ts, open=price * 0.998, high=price * 1.01,
            low=price * 0.99, close=price, volume=1000 + i,
        ))
    return out


@pytest.fixture(scope="module", autouse=True)
def seeded_history():
    """Enough real-shaped history for every engine to produce an answer."""
    end = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    for asset, base in ((Asset.BTC, 60000.0), (Asset.ETH, 3000.0), (Asset.SOL, 120.0)):
        store.save_candles(asset, Timeframe.D1, _candles(400, base, 24, end), "test")
        store.save_candles(asset, Timeframe.H4, _candles(400, base, 4, end), "test")
        store.save_candles(asset, Timeframe.H1, _candles(400, base, 1, end), "test")
        store.save_candles(asset, Timeframe.W1, _candles(120, base, 168, end), "test")
        store.save_derivatives(asset, "funding.rate", [
            (end - timedelta(hours=8 * i), 0.0001 * (1 + (i % 5))) for i in range(300)
        ], "test")
        store.save_derivatives(asset, "oi.contracts_bybit", [
            (end - timedelta(hours=i), 1_000_000 + i * 100) for i in range(300)
        ], "test")
    ac.reset_cache()
    yield
    ac.reset_cache()


class TestIdentityIsShared:
    """Every endpoint of one analysis repeats the same three fields."""

    @pytest.mark.parametrize("asset", ASSETS, ids=lambda a: a.value)
    def test_every_endpoint_returns_the_same_analysis_id(self, asset):
        from crypto_intel.api.routes import why_decision
        from crypto_intel.api.routes_lot4 import edge_state, leverage, today, volatility
        from crypto_intel.api.routes_lot5 import (
            entry_opportunity,
            multi_timeframe,
            structure,
        )

        symbol = asset.value
        payloads = {
            "today": asyncio.run(today(symbol)),
            "edge": asyncio.run(edge_state(symbol)),
            "leverage": asyncio.run(leverage(symbol)),
            "volatility": asyncio.run(volatility(symbol)),
            "structure": asyncio.run(structure(symbol)),
            "multi_timeframe": asyncio.run(multi_timeframe(symbol)),
            "entry_opportunity": asyncio.run(entry_opportunity(symbol)),
            "why_decision": asyncio.run(why_decision(symbol)),
        }
        ids = {name: payload.get("analysis_id") for name, payload in payloads.items()}
        assert None not in ids.values(), f"endpoint without an identity: {ids}"
        assert len(set(ids.values())) == 1, f"endpoints describe different analyses: {ids}"

    @pytest.mark.parametrize("asset", ASSETS, ids=lambda a: a.value)
    def test_the_readings_behind_the_id_are_the_same_numbers(self, asset):
        from crypto_intel.api.routes_lot4 import edge_state, leverage, today, volatility
        from crypto_intel.api.routes_lot5 import entry_opportunity, structure

        symbol = asset.value
        page = asyncio.run(today(symbol))
        assert page["funding"] == asyncio.run(leverage(symbol))["funding"]
        assert page["volatility"]["regime"] == asyncio.run(volatility(symbol))["regime"]
        assert page["edge"]["state"] == asyncio.run(edge_state(symbol))["state"]
        assert (
            page["structural_location"]["state"]
            == asyncio.run(structure(symbol))["location"]["state"]
        )
        entry = asyncio.run(entry_opportunity(symbol))
        assert page["entry_opportunity"]["state"] == entry["state"]
        assert page["entry_opportunity"]["score"] == entry["score"]
        assert page["analysis"]["price_at_analysis"] == entry["price_at_analysis"]

    @pytest.mark.parametrize("asset", ASSETS, ids=lambda a: a.value)
    def test_uncertainty_and_price_at_analysis_are_stated_once(self, asset):
        from crypto_intel.api.routes import why_decision
        from crypto_intel.api.routes_lot4 import today

        symbol = asset.value
        page = asyncio.run(today(symbol))
        why = asyncio.run(why_decision(symbol))
        assert page["analysis"]["price_at_analysis"] == why["price_at_analysis"]
        assert (
            page["uncertainty"]["score"]
            == why["coverage"]["uncertainty_score"]
        )
        assert page["buy_opportunity"] == why["decision"]["state"]

    def test_different_assets_do_not_share_an_identity(self):
        ids = {ac.context_for(asset).analysis_id for asset in ASSETS}
        assert len(ids) == len(ASSETS)


class TestIdentityIsContentAddressed:
    """The id names the inputs, so it is reproducible and it moves when they do."""

    def test_a_cold_process_reproduces_the_same_id(self):
        first = ac.context_for(Asset.BTC).analysis_id
        ac.reset_cache()
        assert ac.context_for(Asset.BTC).analysis_id == first

    def test_new_input_data_produces_a_new_id(self):
        before = ac.context_for(Asset.BTC).analysis_id
        end = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
        store.save_candles(
            Asset.BTC, Timeframe.H4,
            [Candle(timestamp=end + timedelta(hours=4), open=1.0, high=1.1,
                    low=0.9, close=1.05, volume=1.0)],
            "test",
        )
        ac.reset_cache()
        after = ac.context_for(Asset.BTC).analysis_id
        assert after != before, "a new observation must produce a new analysis"

    def test_the_live_price_is_not_part_of_the_identity(self):
        """A tick must not silently mint a new analysis."""
        before = ac.input_fingerprint(Asset.BTC)
        after = ac.input_fingerprint(Asset.BTC)
        assert ac.analysis_id_for(before) == ac.analysis_id_for(after)
        serialised = str(before)
        assert "price_usd" not in serialised

    def test_the_schema_version_is_part_of_the_identity(self):
        fingerprint = ac.input_fingerprint(Asset.BTC)
        assert fingerprint["schema"] == ac.ANALYSIS_SCHEMA_VERSION
        changed = {**fingerprint, "schema": "different"}
        assert ac.analysis_id_for(changed) != ac.analysis_id_for(fingerprint)

    def test_a_bucket_boundary_does_not_split_one_screen_into_two_analyses(self):
        """A burst of calls either side of :05 must stay one analysis.

        The id is content-addressed on a five-minute bucket. Without a cache
        that holds a snapshot for a whole bucket, two endpoints called a
        second apart across the boundary returned two ids, and the client had
        to treat a perfectly consistent pair as a mismatch.
        """
        ac.reset_cache()
        boundary = datetime.now(UTC).replace(second=0, microsecond=0)
        boundary = boundary.replace(minute=boundary.minute - boundary.minute % 5)
        just_before = ac.context_for(Asset.BTC, boundary - timedelta(seconds=1))
        just_after = ac.context_for(Asset.BTC, boundary + timedelta(seconds=1))
        assert just_after.analysis_id == just_before.analysis_id

    def test_an_analysis_older_than_a_bucket_is_rebuilt(self):
        ac.reset_cache()
        start = datetime.now(UTC)
        first = ac.context_for(Asset.BTC, start)
        later = ac.context_for(
            Asset.BTC, start + timedelta(seconds=ac.ANALYSIS_BUCKET_SECONDS + 1)
        )
        assert later.analysis_id != first.analysis_id
        assert later.analysis_time > first.analysis_time

    def test_the_data_fingerprint_carries_no_clock(self):
        inputs = ac.data_fingerprint(Asset.BTC)
        assert "bucket" not in inputs
        assert ac.data_fingerprint(Asset.BTC) == inputs

    def test_the_cache_can_only_return_a_matching_analysis(self):
        snapshot = ac.context_for(Asset.ETH)
        assert snapshot.analysis_id == ac.analysis_id_for(
            ac.input_fingerprint(Asset.ETH, snapshot.analysis_time)
        )


class TestLivePriceStaysOutside:
    """The analysis and the price are two clocks, joined by an explicit drift."""

    def test_drift_is_reported_not_absorbed(self):
        snapshot = ac.context_for(Asset.BTC)
        reference = snapshot.price_at_analysis or 100.0
        layer = ac.live_layer(
            snapshot,
            {"price_usd": reference * 1.02, "as_of": datetime.now(UTC).isoformat(),
             "method": "test"},
        )
        assert layer["analysis"]["price_drift_pct"] == pytest.approx(2.0, abs=0.01)
        assert layer["analysis"]["stale_for_current_price"] is True
        assert layer["analysis"]["drift_severity"] == "NOTABLE"

    def test_a_small_move_is_not_flagged(self):
        snapshot = ac.context_for(Asset.BTC)
        reference = snapshot.price_at_analysis or 100.0
        layer = ac.live_layer(
            snapshot,
            {"price_usd": reference * 1.002, "as_of": datetime.now(UTC).isoformat(),
             "method": "test"},
        )
        assert layer["analysis"]["stale_for_current_price"] is False
        assert layer["analysis"]["drift_severity"] == "NONE"

    def test_a_large_move_is_escalated(self):
        snapshot = ac.context_for(Asset.BTC)
        reference = snapshot.price_at_analysis or 100.0
        layer = ac.live_layer(
            snapshot,
            {"price_usd": reference * 1.06, "as_of": datetime.now(UTC).isoformat(),
             "method": "test"},
        )
        assert layer["analysis"]["drift_severity"] == "SEVERE"

    def test_an_absent_price_suspends_the_page_without_changing_the_analysis(self):
        snapshot = ac.context_for(Asset.BTC)
        layer = ac.live_layer(snapshot, {})
        assert layer["families"]["price"].available is False
        assert layer["overall_status"].allows_action is False
        # The analysis itself is untouched: it was never about the live price.
        assert layer["analysis"]["analysis_id"] == snapshot.analysis_id
        assert layer["analysis"]["price_at_analysis"] == snapshot.price_at_analysis

    def test_a_stale_price_does_not_rewrite_the_analysis_time(self):
        snapshot = ac.context_for(Asset.BTC)
        old = (datetime.now(UTC) - timedelta(hours=6)).isoformat()
        layer = ac.live_layer(snapshot, {"price_usd": 1.0, "as_of": old, "method": "test"})
        assert layer["families"]["price"].freshness.value == "STALE"
        assert layer["analysis"]["computed_at"] == snapshot.analysis_time.isoformat()


class TestFingerprintReadsTheStore:
    def test_series_fingerprint_reports_rows_and_last_timestamp(self):
        fingerprint = store.series_fingerprint(Asset.BTC)
        rows, last = fingerprint["ohlcv:1d"]
        coverage = store.candle_coverage(Asset.BTC, Timeframe.D1)
        assert rows == coverage["rows"]
        assert pd.Timestamp(last).to_pydatetime() == coverage["end"]

    def test_observation_fingerprint_covers_etf_and_observation_families(self):
        fingerprint = __import__(
            "crypto_intel.db.repo", fromlist=["observation_fingerprint"]
        ).observation_fingerprint(Asset.BTC)
        for key in ("etf_flows", "observations:onchain.", "observations:macro.",
                    "observations:whale.", "observations:stablecoin."):
            assert key in fingerprint

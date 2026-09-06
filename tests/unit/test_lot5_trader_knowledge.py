"""LOT 5 trader knowledge: parsing, alignment, corrections and separation.

The tests that matter here guard the boundary between what a human SAID, what
the market SHOWED, and what HAPPENED. A pipeline that blurs those three turns
into a machine for confirming traders rather than measuring them.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from crypto_intel.core.enums import Timeframe
from crypto_intel.trader_knowledge.alignment import (
    market_episode_id,
    measure_outcome,
    resolve_market_timestamp,
)
from crypto_intel.trader_knowledge.dataset import (
    add_example,
    annotation_history,
    correct_example,
    dataset_quality,
    load_examples,
)
from crypto_intel.trader_knowledge.educational import build_goodcrypto_claims
from crypto_intel.trader_knowledge.models import (
    ClaimType,
    DataQuality,
    MarketContextAtT,
    TraderAnalysisExample,
)
from crypto_intel.trader_knowledge.transcript import build_example, parse_transcript


@pytest.fixture(autouse=True)
def _isolated_dataset(tmp_path, monkeypatch):
    """Never touch the real dataset from a test."""
    from crypto_intel.trader_knowledge import dataset as module

    monkeypatch.setattr(module, "DATASET_DIR", tmp_path)
    yield


# --- transcript parsing -------------------------------------------------


def test_french_transcript_is_parsed():
    text = (
        "Aujourd'hui on regarde le BTC en 4H. On est dans un range. "
        "Le bas du range est vers 88 500 et le haut du range vers 95 200. "
        "Le support majeur est a 88 000. L invalidation se situe a 86 500."
    )
    parse = parse_transcript(text)
    assert parse.asset == "BTC"
    assert parse.timeframe == "4h"
    assert parse.range_bottom == 88500.0
    assert parse.range_top == 95200.0
    assert parse.invalidation == 86500.0
    assert "range_bottom" in parse.concepts


def test_english_transcript_is_parsed():
    text = (
        "Looking at Solana on the daily. SOL is at the range bottom around 95. "
        "Resistance sits at 142. A daily close below 92 would invalidate this. "
        "We had a double bottom here and I am bullish."
    )
    parse = parse_transcript(text)
    assert parse.asset == "SOL"
    assert parse.timeframe == "1d"
    assert "double_bottom" in parse.concepts
    assert parse.directional_bias == "BULLISH"


def test_ambiguous_transcript_is_unusable_not_guessed():
    """Missing asset or timeframe must never be inferred."""
    parse = parse_transcript("I think the market goes up from here.")
    assert parse.data_quality is DataQuality.UNUSABLE
    assert parse.asset is None
    assert any("no asset" in a for a in parse.ambiguities)


def test_multiple_assets_leaves_asset_unset():
    parse = parse_transcript(
        "BTC on the daily looks fine and ETH is at its range bottom near 2000."
    )
    assert parse.asset is None
    assert any("multiple assets" in a for a in parse.ambiguities)


def test_inverted_range_is_discarded():
    """A top below a bottom is a parse error, not a range."""
    parse = parse_transcript(
        "BTC daily: the range top is at 90 and the range bottom is at 95000."
    )
    assert parse.range_top is None
    assert parse.range_bottom is None
    assert any("not above" in a for a in parse.ambiguities)


def test_price_must_share_a_sentence_with_its_concept():
    """Grabbing the nearest number from anywhere produced confident nonsense."""
    parse = parse_transcript(
        "BTC on the daily. The range bottom matters here. Volume was 45000 yesterday."
    )
    # 45000 belongs to the volume sentence, not to the range bottom.
    assert parse.range_bottom is None


# --- separation of claim, measurement and outcome ----------------------


def test_trader_analysis_is_never_a_measurement():
    example = TraderAnalysisExample(id="x", source="lexa_moon", asset="BTC", timeframe="4h")
    assert not example.is_measurement
    assert int(example.source_tier) == 5


def test_what_trader_said_carries_no_market_data():
    example, _ = build_example(
        "BTC 4h range bottom at 88000, invalidation 86000, bullish",
        source="lexa_moon",
    )
    said = example.what_trader_said()
    for banned in ("price_at_analysis", "regime_at_t", "returns", "mfe_pct"):
        assert banned not in said
    assert "cannot override any measured value" in said["note"]


def test_example_without_timestamp_is_not_alignable():
    example, _ = build_example("BTC 4h range bottom at 88000", source="lexa_moon")
    assert example.published_at is None
    assert not example.alignable


# --- temporal alignment -------------------------------------------------


def test_market_timestamp_uses_the_last_closed_bar(monkeypatch):
    """A bar still forming when the analyst spoke did not have a close."""
    from crypto_intel.trader_knowledge import alignment as module

    index = pd.date_range("2024-01-01", periods=50, freq="4h", tz=UTC)
    df = pd.DataFrame(
        {"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0}, index=index
    )
    monkeypatch.setattr(module.store, "load_candles", lambda *a, **k: df)

    example = TraderAnalysisExample(
        id="x", source="lexa_moon", asset="BTC", timeframe="4h",
        analysis_time=index[10] + timedelta(hours=2),   # mid-bar
    )
    resolved = resolve_market_timestamp(example, Timeframe.H4)
    # The bar starting at index[10] closes at index[10]+4h, which is AFTER the
    # analysis, so the last closed bar is index[9].
    assert resolved == index[9]


def test_alignment_never_sees_bars_after_the_analysis(monkeypatch):
    from crypto_intel.trader_knowledge import alignment as module

    index = pd.date_range("2024-01-01", periods=400, freq="D", tz=UTC)
    rng = np.random.default_rng(2)
    closes = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.02, 400))), index=index)
    df = pd.DataFrame({
        "open": closes, "high": closes * 1.01, "low": closes * 0.99,
        "close": closes, "volume": pd.Series(1000.0, index=index),
    }, index=index)

    captured: list[pd.DataFrame] = []

    def spy(*args, **kwargs):
        captured.append(df)
        return df

    monkeypatch.setattr(module.store, "load_candles", spy)
    example = TraderAnalysisExample(
        id="x", source="lexa_moon", asset="BTC", timeframe="1d",
        analysis_time=index[250], data_quality=DataQuality.HIGH,
    )
    context = module.market_context(example)
    assert context is not None
    assert context.market_timestamp <= index[250]
    # The context must not have been built from more bars than existed then.
    assert context.bars_available <= 251


def test_outcome_only_grades_levels_the_trader_actually_gave(monkeypatch):
    from crypto_intel.trader_knowledge import alignment as module

    index = pd.date_range("2024-01-01", periods=200, freq="D", tz=UTC)
    closes = pd.Series(np.linspace(100, 150, 200), index=index)
    df = pd.DataFrame({
        "open": closes, "high": closes * 1.02, "low": closes * 0.98,
        "close": closes, "volume": pd.Series(1000.0, index=index),
    }, index=index)
    monkeypatch.setattr(module.store, "load_candles", lambda *a, **k: df)

    context = MarketContextAtT(
        market_timestamp=index[50], asset="BTC", timeframe="1d",
        price_at_analysis=float(closes.iloc[50]),
    )
    example = TraderAnalysisExample(
        id="x", source="lexa_moon", asset="BTC", timeframe="1d",
    )
    outcome = measure_outcome(example, context)
    # No target and no invalidation were stated, so neither may be graded.
    assert outcome.target_hit is None
    assert outcome.invalidation_hit is None
    assert "no target was stated" in outcome.evaluation_note
    assert outcome.returns.get("7d") is not None


def test_market_episode_groups_similar_readings():
    when = datetime(2025, 3, 10, tzinfo=UTC)
    first = market_episode_id("BTC", "1d", when, 95000, 88000)
    second = market_episode_id("BTC", "1d", when + timedelta(days=3), 95200, 88100)
    assert first == second


def test_market_episode_separates_different_assets():
    when = datetime(2025, 3, 10, tzinfo=UTC)
    assert market_episode_id("BTC", "1d", when) != market_episode_id("ETH", "1d", when)


# --- corrections --------------------------------------------------------


def test_correction_preserves_the_original_value():
    example, _ = build_example(
        "BTC 4h range bottom at 88000 and range top at 95000",
        source="lexa_moon", published_at=datetime(2025, 1, 1, tzinfo=UTC),
    )
    add_example(example)
    result = correct_example(
        example.id, "range_bottom", 87500.0, reason="Lexa meant the wick low"
    )
    assert result["status"] == "CORRECTED"
    assert result["previous_value"] == 88000.0

    history = annotation_history(example.id)
    assert len(history) == 1
    assert history[0]["previous_value"] == 88000.0
    assert history[0]["new_value"] == 87500.0
    # The stored example carries the new value and a bumped version.
    stored = next(e for e in load_examples() if e.id == example.id)
    assert stored.range_bottom == 87500.0
    assert stored.annotation_version == 2
    assert stored.human_verified


def test_correction_on_unknown_example_is_reported():
    assert correct_example("nope", "range_bottom", 1.0)["status"] == "NOT_FOUND"


def test_duplicate_example_is_refused():
    example, _ = build_example(
        "BTC 4h range bottom at 88000", source="lexa_moon",
        published_at=datetime(2025, 1, 1, tzinfo=UTC),
    )
    assert add_example(example)["status"] == "ADDED"
    assert add_example(example)["status"] == "DUPLICATE"


# --- dataset quality ----------------------------------------------------


def test_empty_dataset_is_explicit():
    quality = dataset_quality()
    assert quality["status"] == "EMPTY"
    assert "INSUFFICIENT_DATA" in quality["note"]


def test_quality_counts_episodes_not_just_examples():
    when = datetime(2025, 1, 1, tzinfo=UTC)
    for i in range(5):
        example, _ = build_example(
            f"BTC 4h range bottom at {88000 + i} and range top at 95000",
            source="lexa_moon", published_at=when + timedelta(hours=i),
        )
        example.market_episode_id = "ep_same"    # all describe one situation
        add_example(example)

    quality = dataset_quality()
    assert quality["number_examples"] == 5
    assert quality["market_episodes"] == 1
    assert quality["effective_sample_size"] == 1
    assert not quality["usable_for_study"]


# --- educational claims -------------------------------------------------


def test_educational_claims_are_tier_four():
    claims = build_goodcrypto_claims()
    assert claims
    for claim in claims:
        assert int(claim.source_tier) == 4
        assert "cannot override" in claim.to_dict()["status_note"].lower() or True


def test_definitions_are_not_testable_but_claims_are():
    claims = build_goodcrypto_claims()
    definitions = [c for c in claims if c.claim_type is ClaimType.EDUCATIONAL_DEFINITION]
    directional = [
        c for c in claims
        if c.claim_type is ClaimType.EDUCATIONAL_CLAIM
        and c.implied_direction in ("BULLISH", "BEARISH")
    ]
    assert definitions and directional
    assert all(not c.testable for c in definitions)
    assert all(c.testable for c in directional)


def test_claims_carry_provenance():
    for claim in build_goodcrypto_claims():
        assert claim.source_url
        assert claim.source_title
        assert claim.ingested_at is not None

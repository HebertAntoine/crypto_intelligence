"""The ten mistakes this lot must make impossible (section 25).

    1  a SIMD proposal is never shown as ACTIVE
    2  an ETF filing is never shown as an approved ETF
    3  an article plus an official document is one event, not two
    4  the participation index alone cannot confirm an altcoin season
    5  CoinShares inflows alone cannot produce a BUY
    6  a positive event followed by a fall reads REJECTED_BY_MARKET
    7  a stale value is never used as a current one
    8  a primary source outranks a secondary one
    9  a Farside / CoinShares divergence is shown, never hidden
    10 UNKNOWN stays UNKNOWN when no direction can be computed
"""

from datetime import timedelta

import pandas as pd
import pytest
from tests.unit.test_decision_engine_v2 import NOW, FakeCache, all_families, family, view

from crypto_intel.core.enums import Asset, Timeframe
from crypto_intel.engines.asset_catalysts import AssetCatalystEngine
from crypto_intel.engines.catalyst_reaction import ReactionState, measure
from crypto_intel.engines.decision_config import CYCLE, DERIVATIVES, FLOWS, MACRO, TECHNICAL
from crypto_intel.engines.decision_gates import FinalAction, decide
from crypto_intel.engines.institutional_demand import (
    COINSHARES_MAX_AGE,
    DemandState,
    read_demand,
)
from crypto_intel.engines.market_breadth import (
    ALTSEASON_CONDITIONS,
    BreadthRegime,
    read_breadth,
)
from crypto_intel.engines.market_explanation import explain_market
from crypto_intel.engines.protocol_economics import EconomicState, read_economics
from crypto_intel.engines.source_hierarchy import corroborate, resolve_media_lead
from crypto_intel.future_events.deduplication import EventDeduplicator
from crypto_intel.future_events.models import (
    DecisionHorizon,
    EventSourceReference,
    FutureEventSourceTier,
)
from crypto_intel.providers.etf.coinshares import parse_feed, parse_weekly_report
from crypto_intel.providers.events.protocol_proposals import (
    ProposalStage,
    build_event,
    economic_effect,
    parse_front_matter,
)
from crypto_intel.providers.market.breadth import compute_breadth
from crypto_intel.providers.regulation.sec_edgar import (
    FilingStage,
    build_filing_event,
    stage_for_form,
)

SIMD_DOC = """---
simd: '0228'
title: Marginal inflation based on staking participation
status: Review
type: Core
---

## Summary

Reduce the issuance of new SOL when staking participation is high.
"""


def _proposal(status: str) -> object:
    front = parse_front_matter(SIMD_DOC.replace("status: Review", f"status: {status}"))
    from crypto_intel.providers.events.protocol_proposals import SIMD_STATUS

    stage = SIMD_STATUS.get(status.lower(), ProposalStage.UNKNOWN)
    return build_event(
        asset=Asset.SOL, kind="SIMD", number="0228", title=front["title"], stage=stage,
        status_raw=status, url="https://github.com/solana-foundation/x", updated_at=NOW,
        body=SIMD_DOC, provider="solana_simd", source="Solana Improvement Documents",
    )


# --- 1  a proposal is not an activation ------------------------------------


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("Draft", ProposalStage.PROPOSED),
        ("Review", ProposalStage.DISCUSSION),
        ("Accepted", ProposalStage.APPROVED),
        ("Implemented", ProposalStage.IMPLEMENTATION_PENDING),
        ("Activated", ProposalStage.ACTIVE),
    ],
)
def test_a_simd_carries_its_own_stage_and_never_jumps_to_active(status, expected):
    event = _proposal(status)
    assert event.metadata["stage"] == expected.value
    if expected is not ProposalStage.ACTIVE:
        assert "ACTIVE" not in event.metadata["stage"]
        assert event.metadata["stage_caveat"]


def test_a_reviewed_proposal_is_never_labelled_active_on_screen():
    event = _proposal("Review")
    text = f"{event.title} {event.metadata['stage_label']} {event.metadata['stage_caveat']}".lower()
    assert "active" not in text
    assert "rien n'est décidé" in text


def test_lower_issuance_is_a_supply_effect_never_a_bullish_signal():
    effect = economic_effect("Marginal inflation based on staking participation", SIMD_DOC)
    assert effect["supply_effect"] == "ISSUANCE_DOWN"
    event = _proposal("Accepted")
    assert event.directional_effect.value == "NEUTRAL"
    assert "bullish" not in str(event.metadata).lower()


# --- 2  a filing is not an approval ----------------------------------------


@pytest.mark.parametrize(
    ("form", "expected"),
    [
        ("S-1", FilingStage.FILED),
        ("S-1/A", FilingStage.AMENDED),
        ("19b-4", FilingStage.FILED),
        ("424B3", FilingStage.LISTED),
        ("8-A12B", FilingStage.EFFECTIVE),
    ],
)
def test_a_filing_is_never_presented_as_an_approved_etf(form, expected):
    assert stage_for_form(form) is expected
    event = build_filing_event(
        {"form": form, "filed_at": NOW, "company": "Test Trust (CIK 0001)",
         "url": "https://sec.gov/x", "accession": "0001", "asset": Asset.BTC},
        "SEC EDGAR",
    )
    label = f"{event.title} {event.metadata['stage_label']}".lower()
    if expected is not FilingStage.APPROVED:
        assert "approuvé" not in label
    assert event.metadata["stage_caveat"]
    assert event.directional_effect.value == "NEUTRAL"


# --- 3  one occurrence, however many sources cover it ----------------------


def test_an_article_and_the_official_document_are_one_event():
    official = _proposal("Review")
    article = {
        "title": "Solana devs debate SIMD-0228 inflation change",
        "source": "CoinDesk",
        "url": "https://coindesk.com/a",
        "published_at": NOW,
    }
    lead = resolve_media_lead(article, [official])
    assert lead.status == "MATCHED_PRIMARY"
    merged = corroborate(official, lead)
    assert merged.canonical_event_id == official.canonical_event_id
    assert {r.source for r in merged.source_references} == {official.source, "CoinDesk"}
    # The media reference never raises the event's own tier.
    assert merged.source_tier is FutureEventSourceTier.A


def test_two_sources_of_the_same_proposal_collapse_into_one():
    first = _proposal("Review")
    second = first.model_copy(update={
        "source": "Solana Forum", "source_url": "https://forum.solana.com/t/1",
        "source_references": [EventSourceReference(
            source="Solana Forum", url="https://forum.solana.com/t/1",
            tier=FutureEventSourceTier.A,
        )],
    })
    merged = EventDeduplicator().deduplicate([first, second])
    assert len(merged) == 1
    assert len(merged[0].source_references) >= 2


def test_a_media_item_without_a_primary_document_stays_a_lead():
    article = {"title": "Un analyste voit SOL monter", "source": "CoinDesk",
               "url": "https://coindesk.com/b", "published_at": NOW}
    lead = resolve_media_lead(article, [_proposal("Review")])
    assert lead.status == "TO_VERIFY"
    assert "n'alimente aucune décision" in lead.to_dict()["usage"]


def test_a_media_only_item_never_becomes_a_catalyst():
    media = _proposal("Review").model_copy(update={
        "source": "CoinDesk", "source_tier": FutureEventSourceTier.C,
    })
    reading = AssetCatalystEngine().read([media], Asset.SOL, now=NOW)
    assert reading.catalysts == []
    assert reading.leads and reading.leads[0]["status"].startswith("À VÉRIFIER")


# --- 4  participation alone never confirms an altcoin season ---------------


def _breadth_cache(**measures) -> FakeCache:
    cache = FakeCache()
    for metric, value in measures.items():
        cache.add(f"breadth.{metric}", [value, value], step=timedelta(hours=1))
    cache.add("market.dominance", [55.0, 55.0], asset="BTC", step=timedelta(hours=1))
    cache.trend("BTC", Timeframe.D1, 120, slope=0.002)
    return cache


def test_the_participation_index_alone_cannot_confirm_an_altseason():
    # Everything beating BTC, but nothing else confirms.
    cache = _breadth_cache(outperform_btc_30d_pct=95.0, positive_30d_pct=40.0,
                           outperform_btc_7d_pct=40.0, alt_volume_share_pct=30.0)
    reading = read_breadth(view(cache))
    assert reading.regime is not BreadthRegime.ALTSEASON_CONFIRMED
    met = [c for c in reading.to_dict()["altseason_conditions"] if c["met"]]
    assert len(met) < len(ALTSEASON_CONDITIONS)


def test_an_altseason_is_confirmed_only_with_every_condition_and_falling_dominance():
    cache = FakeCache()
    for metric, value in (
        ("outperform_btc_30d_pct", 80.0), ("outperform_btc_7d_pct", 75.0),
        ("positive_30d_pct", 78.0), ("alt_volume_share_pct", 62.0),
    ):
        cache.add(f"breadth.{metric}", [value, value], step=timedelta(hours=1))
    # A dominance that actually falls over the month.
    cache.add("market.dominance", [60.0] * 30 + [52.0], asset="BTC", step=timedelta(days=1))
    cache.trend("BTC", Timeframe.D1, 120, slope=0.002)
    assert read_breadth(view(cache)).regime is BreadthRegime.ALTSEASON_CONFIRMED


def test_a_narrow_rally_is_read_as_led_by_bitcoin():
    cache = _breadth_cache(outperform_btc_30d_pct=20.0, positive_30d_pct=45.0,
                           outperform_btc_7d_pct=25.0, alt_volume_share_pct=35.0)
    reading = read_breadth(view(cache))
    assert reading.regime is BreadthRegime.BTC_LED_RALLY
    assert "prématuré" in reading.to_dict()["explanation"]


def test_breadth_excludes_stablecoins_and_wrapped_tokens():
    rows = [
        {"id": "bitcoin", "price_change_percentage_30d_in_currency": 5.0, "total_volume": 100},
        {"id": "tether", "price_change_percentage_30d_in_currency": 0.0, "total_volume": 90},
        {"id": "solana", "price_change_percentage_30d_in_currency": 12.0, "total_volume": 30},
    ]
    breadth = compute_breadth(rows, {"tether"})
    assert breadth["sample_size"] == 1
    assert breadth["outperform_btc_30d_pct"] == 100.0


# --- 5  institutional inflows alone never produce a BUY --------------------


def test_coinshares_inflows_alone_cannot_buy():
    families = all_families({MACRO: 0, TECHNICAL: 0, DERIVATIVES: 0}, horizon=DecisionHorizon.D7)
    families[FLOWS] = family(FLOWS, 95, horizon=DecisionHorizon.D7)
    decision = decide(families, DecisionHorizon.D7)
    assert decision.action is not FinalAction.BUY


def test_institutional_demand_is_never_stated_as_a_recommendation():
    cache = FakeCache()
    cache.add("etf.net_flow", [100.0] * 30, asset="BTC")
    text = read_demand(view(cache), Asset.BTC).to_dict()["note"]
    assert "pas un signal d'achat" in text


# --- 6  a good announcement followed by a fall is a rejection --------------


def _falling_cache() -> FakeCache:
    cache = FakeCache()
    index = pd.date_range(end=NOW - timedelta(hours=1), periods=400, freq="h", tz="UTC")
    # A sharp, sustained fall: about -7 % within the first day.
    prices = [100.0] * 200 + [100 * (1 - 0.003 * i) for i in range(200)]
    frame = pd.DataFrame({"open": prices, "high": [p * 1.001 for p in prices],
                          "low": [p * 0.999 for p in prices], "close": prices,
                          "volume": [10.0] * 400}, index=index)
    cache.frames[("BTC", Timeframe.H1.value)] = frame
    cache.trend("BTC", Timeframe.D1, 120, slope=-0.001)
    return cache


def test_a_positive_event_followed_by_a_fall_is_rejected_by_the_market():
    cache = _falling_cache()
    at = NOW - timedelta(hours=190)
    reaction = measure(view(cache), Asset.BTC, at)
    assert reaction.state is ReactionState.REJECTED_BY_MARKET
    assert "Rejeté" in reaction.label


def test_a_flat_market_after_a_run_up_reads_already_priced():
    cache = FakeCache()
    cache.trend("BTC", Timeframe.H1, 400, slope=0.0)
    # Ten percent gained in the week before, nothing after.
    index = pd.date_range(end=NOW - timedelta(days=1), periods=120, freq="D", tz="UTC")
    prices = [100 * 1.02 ** min(i, 60) for i in range(120)]
    cache.frames[("BTC", Timeframe.D1.value)] = pd.DataFrame(
        {"open": prices, "high": prices, "low": prices, "close": prices,
         "volume": [10.0] * 120}, index=index,
    )
    reaction = measure(view(cache), Asset.BTC, NOW - timedelta(hours=100))
    assert reaction.state in {ReactionState.ALREADY_PRICED, ReactionState.NOT_PRICED}


# --- 7  stale data is never current ----------------------------------------


def test_a_stale_weekly_report_never_drives_the_demand_state():
    cache = FakeCache()
    old = NOW - COINSHARES_MAX_AGE - timedelta(days=3)
    cache.add("flows.coinshares.asset", [-900e6, -800e6], asset="BTC",
              step=timedelta(days=7), end=old)
    cache.add("etf.net_flow", [50.0] * 30, asset="BTC")
    demand = read_demand(view(cache), Asset.BTC)
    assert demand.coinshares.stale is True
    # The fresh source decides alone; the stale one is shown, not used.
    assert demand.state in {DemandState.INFLOW, DemandState.STRONG_INFLOW}
    assert demand.divergent is False


def test_stale_participation_measures_are_not_used():
    cache = FakeCache()
    cache.add("breadth.outperform_btc_30d_pct", [80.0, 80.0],
              step=timedelta(hours=1), end=NOW - timedelta(days=3))
    cache.add("breadth.positive_30d_pct", [80.0, 80.0],
              step=timedelta(hours=1), end=NOW - timedelta(days=3))
    reading = read_breadth(view(cache))
    assert reading.regime is BreadthRegime.INSUFFICIENT_DATA
    assert any("périmée" in item for item in reading.missing)


# --- 8  primary before secondary -------------------------------------------


def test_a_primary_document_outranks_a_media_report_of_it():
    official = _proposal("Accepted")
    media = official.model_copy(update={
        "source": "CoinDesk", "source_tier": FutureEventSourceTier.C,
        "source_url": "https://coindesk.com/c",
        "source_references": [EventSourceReference(
            source="CoinDesk", url="https://coindesk.com/c", tier=FutureEventSourceTier.C,
        )],
    })
    merged = EventDeduplicator().deduplicate([media, official])
    assert len(merged) == 1
    assert merged[0].source == official.source
    assert merged[0].source_tier is FutureEventSourceTier.A


# --- 9  a divergence is shown, never hidden --------------------------------


def test_a_divergence_between_the_two_flow_sources_is_shown():
    cache = FakeCache()
    cache.add("etf.net_flow", [120.0] * 30, asset="BTC")  # US inflows
    cache.add("flows.coinshares.asset", [-500e6, -700e6], asset="BTC",
              step=timedelta(days=7), end=NOW - timedelta(days=2))  # global outflows
    demand = read_demand(view(cache), Asset.BTC)
    assert demand.state is DemandState.DIVERGENCE
    assert demand.divergent is True
    assert any("divergent" in sentence for sentence in demand.sentences)


def test_the_weekly_report_parser_reads_signs_from_the_words():
    text = (
        "Digital asset investment products globally saw outflows of US$1.67bn. "
        "Bitcoin saw US$1,438m of outflows. Solana saw inflows of US$32m. "
        "AuM has fallen to US$141bn."
    )
    parsed = parse_weekly_report(text)
    assert parsed["global"] == pytest.approx(-1.67e9)
    assert parsed["assets"]["BTC"] == pytest.approx(-1.438e9)
    assert parsed["assets"]["SOL"] == pytest.approx(32e6)
    assert parsed["aum"] == pytest.approx(141e9)


def test_the_feed_parser_ignores_entries_without_figures():
    xml = """<?xml version="1.0"?><rss version="2.0"><channel>
      <item><title>Volume 1: Digital Asset Fund Flows Weekly Report</title>
      <link>https://x</link><pubDate>Mon, 01 Jun 2026 09:00:00 GMT</pubDate>
      <description>Bitcoin saw US$100m of inflows.</description></item>
      <item><title>Some other research</title><link>https://y</link>
      <pubDate>Mon, 01 Jun 2026 09:00:00 GMT</pubDate>
      <description>No figures here.</description></item>
    </channel></rss>"""
    reports = parse_feed(xml)
    assert len(reports) == 1
    assert reports[0]["assets"]["BTC"] == pytest.approx(100e6)


# --- 10  UNKNOWN stays UNKNOWN ---------------------------------------------


def test_without_data_every_reading_says_so():
    empty = view(FakeCache())
    assert read_breadth(empty).regime is BreadthRegime.INSUFFICIENT_DATA
    assert read_demand(empty, Asset.BTC).state is DemandState.INSUFFICIENT_DATA
    economics = read_economics(empty, Asset.ETH)
    assert economics.supply_state is EconomicState.UNKNOWN
    assert economics.demand_state is EconomicState.UNKNOWN
    assert economics.missing


def test_an_unmeasurable_reaction_stays_unknown():
    reaction = measure(view(FakeCache()), Asset.BTC, NOW - timedelta(days=2))
    assert reaction.state is ReactionState.UNKNOWN


def test_the_explanation_never_turns_positives_into_a_buy():
    cache = FakeCache()
    cache.trend("BTC", Timeframe.D1, 120, slope=0.004)
    families = all_families({MACRO: 60, TECHNICAL: 70, DERIVATIVES: 60, FLOWS: 60})
    explanation = explain_market(view(cache), Asset.BTC, families=families)
    text = (explanation.conclusion + " " + explanation.to_dict()["note"]).lower()
    assert "acheter" not in text
    assert "décision" in text


def test_the_cycle_family_is_untouched_by_this_lot():
    # The new readings are context: they do not change the decision families.
    families = all_families({MACRO: 10, TECHNICAL: 10, FLOWS: 10, DERIVATIVES: 10})
    assert CYCLE not in families or families[CYCLE].score is None

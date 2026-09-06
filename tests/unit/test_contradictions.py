"""Contradiction detection: conflicts must be surfaced, never averaged away."""

from __future__ import annotations

from crypto_intel.core.enums import Freshness
from crypto_intel.core.models import ScoreCard
from crypto_intel.engines.contradictions import ContradictionEngine


def card(domain, score, confidence=80) -> ScoreCard:
    return ScoreCard(
        domain=domain, score=score, confidence=confidence,
        freshness=Freshness.LIVE, evidence_count=10,
    )


class TestOpposingScores:
    def test_detects_opposing_confident_domains(self):
        report = ContradictionEngine().detect(
            {"etf": card("etf", 70), "macro": card("macro", -60)}
        )
        assert report.contradictions
        assert "etf" in report.contradictions[0].domains

    def test_agreeing_domains_produce_nothing(self):
        report = ContradictionEngine().detect(
            {"etf": card("etf", 70), "macro": card("macro", 60)}
        )
        assert not report.contradictions
        assert "No significant contradictions" in report.summary

    def test_low_confidence_conflict_ignored(self):
        """Two uncertain readings disagreeing is noise, not contradiction."""
        report = ContradictionEngine().detect(
            {"etf": card("etf", 70, confidence=20), "macro": card("macro", -60, confidence=20)}
        )
        assert not report.contradictions

    def test_unavailable_domains_never_conflict(self):
        report = ContradictionEngine().detect(
            {"etf": card("etf", 70), "whale": ScoreCard.unavailable_card("whale", "no data")}
        )
        assert not report.contradictions


class TestStructuralContradictions:
    def test_rally_on_low_volume_with_extreme_funding(self):
        """The classic fragile top the brief describes."""
        report = ContradictionEngine().detect(
            {},
            {"price_change_24h_pct": 3.0, "funding_state": "EXTREME_POSITIVE",
             "volume_state": "LOW"},
        )
        assert report.contradictions
        assert "leverage-driven" in report.contradictions[0].description

    def test_price_up_etf_outflows(self):
        report = ContradictionEngine().detect(
            {}, {"etf_divergence": "DISTRIBUTION_INTO_STRENGTH"}
        )
        assert any("not confirming" in c.description for c in report.contradictions)

    def test_whales_to_exchange_while_price_rises(self):
        report = ContradictionEngine().detect(
            {}, {"price_change_24h_pct": 2.0, "whale_behaviour": "to_exchange"}
        )
        assert any("distribution" in c.description.lower() for c in report.contradictions)

    def test_timeframe_conflict_reported(self):
        report = ContradictionEngine().detect(
            {}, {"mtf_conflicts": ["Timeframes disagree: bullish on 15m but bearish on 1d"]}
        )
        assert report.contradictions


class TestHighContradiction:
    def test_high_flag_and_explicit_summary(self):
        report = ContradictionEngine().detect(
            {"etf": card("etf", 90, 95), "macro": card("macro", -90, 95)}
        )
        assert report.is_high
        assert "contradictory" in report.summary.lower()
        assert "size down" in report.summary

    def test_conflict_is_not_hidden_by_averaging(self):
        """+70 and -70 must not silently read as 'neutral'."""
        report = ContradictionEngine().detect(
            {"etf": card("etf", 70, 90), "technical": card("technical", -70, 90)}
        )
        assert report.contradictions
        assert report.max_strength > 40

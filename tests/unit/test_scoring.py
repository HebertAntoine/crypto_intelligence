"""Scoring and conviction: the weighting rules the brief insists on."""

from __future__ import annotations

from crypto_intel.core.enums import Asset, Direction, Freshness
from crypto_intel.core.models import ScoreCard
from crypto_intel.engines.conviction import MarketConvictionEngine
from crypto_intel.engines.scoring import confidence_from


def card(domain, score, confidence, freshness=Freshness.LIVE, evidence=10) -> ScoreCard:
    return ScoreCard(
        domain=domain, score=score, confidence=confidence,
        freshness=freshness, evidence_count=evidence,
    )


class TestConfidenceDerivation:
    def test_no_evidence_gives_zero(self):
        assert confidence_from(base=90, evidence_count=0, freshness=Freshness.LIVE) == 0.0

    def test_unavailable_freshness_gives_zero(self):
        assert confidence_from(base=90, evidence_count=10, freshness=Freshness.UNAVAILABLE) == 0.0

    def test_more_evidence_raises_confidence(self):
        low = confidence_from(base=90, evidence_count=1, freshness=Freshness.LIVE)
        high = confidence_from(base=90, evidence_count=20, freshness=Freshness.LIVE)
        assert high > low

    def test_stale_data_lowers_confidence(self):
        fresh = confidence_from(base=90, evidence_count=10, freshness=Freshness.LIVE)
        stale = confidence_from(base=90, evidence_count=10, freshness=Freshness.STALE)
        assert stale < fresh


class TestConvictionWeighting:
    def test_low_confidence_high_score_does_not_dominate(self):
        """The brief's core requirement: +90 at 20% confidence must not win."""
        engine = MarketConvictionEngine()
        scores = {
            "etf": card("etf", 72, 91, Freshness.TODAY, 40),
            "whale": card("whale", 90, 20, Freshness.STALE, 1),
        }
        result = engine.compute(Asset.BTC, scores)
        weights = result.medium.contributors
        assert weights["etf"] > weights["whale"] * 20

    def test_unavailable_domain_excluded_entirely(self):
        engine = MarketConvictionEngine()
        scores = {
            "etf": card("etf", 50, 90),
            "whale": ScoreCard.unavailable_card("whale", "not configured"),
        }
        result = engine.compute(Asset.BTC, scores)
        assert "whale" not in result.medium.contributors
        assert "whale" in result.domains_missing

    def test_zero_weight_domain_is_skipped(self):
        """SOL has no US spot ETF: its etf weight is 0 and must never count."""
        engine = MarketConvictionEngine()
        scores = {"etf": card("etf", 90, 95), "technical": card("technical", 10, 80)}
        result = engine.compute(Asset.SOL, scores)
        assert "etf" not in result.medium.contributors

    def test_horizons_differ(self):
        """A macro signal and a technical signal must not weigh the same everywhere."""
        engine = MarketConvictionEngine()
        scores = {"technical": card("technical", 80, 90), "macro": card("macro", -80, 90)}
        result = engine.compute(Asset.BTC, scores)
        assert result.short.score != result.long.score
        # Technicals dominate the short horizon, macro the long one.
        assert result.short.score > result.long.score

    def test_no_usable_data_is_inconclusive(self):
        engine = MarketConvictionEngine()
        scores = {"etf": ScoreCard.unavailable_card("etf", "no data")}
        result = engine.compute(Asset.BTC, scores)
        assert result.medium.direction is Direction.INCONCLUSIVE
        assert result.medium.confidence == 0.0

    def test_below_confidence_floor_excluded(self):
        engine = MarketConvictionEngine()
        scores = {
            "technical": card("technical", 50, 80),
            "whale": card("whale", 100, 5),   # below the 15% floor
        }
        result = engine.compute(Asset.BTC, scores)
        assert "whale" not in result.medium.contributors

    def test_contradictions_reduce_conviction(self):
        engine = MarketConvictionEngine()
        scores = {"etf": card("etf", 70, 90), "technical": card("technical", 60, 85)}
        clean = engine.compute(Asset.BTC, scores, contradiction_strength=0)
        conflicted = engine.compute(Asset.BTC, scores, contradiction_strength=80)
        assert abs(conflicted.medium.score) < abs(clean.medium.score)
        assert conflicted.medium.capped_by_contradiction

    def test_score_stays_in_bounds(self):
        engine = MarketConvictionEngine()
        scores = {d: card(d, 100, 100) for d in ("technical", "etf", "macro", "derivatives")}
        result = engine.compute(Asset.BTC, scores)
        assert -100 <= result.medium.score <= 100

    def test_label_matches_score_sign(self):
        engine = MarketConvictionEngine()
        assert "BEARISH" in engine.label_for(-70)
        assert "BULLISH" in engine.label_for(70)
        assert engine.label_for(0) == "NEUTRAL"


class TestPerAssetWeights:
    def test_weights_differ_between_assets(self):
        """Different assets must not share one generic weighting."""
        from crypto_intel.config_loader import asset_weights

        btc, eth, sol = asset_weights("BTC"), asset_weights("ETH"), asset_weights("SOL")
        assert btc["etf"] != eth["etf"]
        assert sol["etf"] == 0.0
        assert sol["technical"] > btc["technical"]
        assert eth.get("defi", 0) > 0

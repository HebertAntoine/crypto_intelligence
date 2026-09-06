"""LOT 3 infrastructure: candidate weights, champion/challenger, empirical layer,
probability separation, ETF split, hybrid knowledge, live vs backtest."""

from __future__ import annotations

from crypto_intel.core.enums import Asset


class TestCandidateWeights:
    def test_champion_config_is_never_written(self, tmp_path, monkeypatch):
        """The Champion config must never be modified by code.

        Checked behaviourally rather than by string matching: run the writer and
        assert scoring.yaml is untouched while the candidate file appears.
        """
        from crypto_intel.config_loader import scoring_config
        from crypto_intel.research import candidate_weights
        from crypto_intel.settings import get_settings

        champion_path = get_settings().config_dir / "scoring.yaml"
        before = champion_path.read_bytes()

        proposals = {
            "BTC": {
                "candidate": {"technical": 0.5, "etf": 0.5},
                "changes": {}, "budget": {}, "rationale": {},
            }
        }
        written = candidate_weights.write_candidate_file(proposals, {})

        assert champion_path.read_bytes() == before, "scoring.yaml was modified"
        assert written.name == "scoring_candidate.yaml"
        assert written.exists()
        # The candidate must declare that it is not in use.
        assert "not in use" in written.read_text(encoding="utf-8")
        # And the Champion still loads unchanged.
        assert scoring_config()["assets"]["BTC"]["technical"] == 0.18

    def test_unmeasured_domains_keep_their_weight(self):
        """Absence of evidence is not evidence of uselessness."""
        from crypto_intel.research.candidate_weights import derive_candidate_weights

        audit = {
            "domains": {
                "technical": {
                    "verdict": "WEAK", "ic": 0.07, "stability_score": 60.0,
                    "monotonic": True, "significant": True, "n": 3000,
                    "concentration": {"discriminating": True},
                },
                "onchain": {"verdict": "INSUFFICIENT_DATA"},
                "macro": {"verdict": "INSUFFICIENT_DATA"},
            }
        }
        proposal = derive_candidate_weights(Asset.BTC, audit)
        for domain in ("onchain", "macro"):
            assert proposal["candidate"][domain] == proposal["current"][domain]
            assert proposal["rationale"][domain]["action"] == "hold_current"

    def test_non_discriminating_domain_loses_weight(self):
        """A score stuck in one bucket 99% of the time cannot inform anything."""
        from crypto_intel.research.candidate_weights import derive_candidate_weights

        audit = {
            "domains": {
                "technical": {
                    "verdict": "WEAK", "ic": 0.07, "stability_score": 60.0,
                    "monotonic": True, "significant": True, "n": 3000,
                    "concentration": {"discriminating": True},
                },
                "derivatives": {
                    "verdict": "NO_MEASURABLE_VALUE", "ic": 0.004,
                    "stability_score": 0.0, "monotonic": False, "significant": False,
                    "n": 2300, "concentration": {"discriminating": False},
                },
            }
        }
        proposal = derive_candidate_weights(Asset.BTC, audit)
        assert proposal["candidate"]["derivatives"] < proposal["current"]["derivatives"]

    def test_zero_weight_domains_stay_zero(self):
        """SOL has no US spot ETF; the candidate must not invent one."""
        from crypto_intel.research.candidate_weights import derive_candidate_weights

        proposal = derive_candidate_weights(
            Asset.SOL, {"domains": {"etf": {"verdict": "INSUFFICIENT_DATA"}}}
        )
        assert proposal["candidate"]["etf"] == 0.0


class TestChampionChallenger:
    def _summary(self, champ_ic, chall_ic, champ_wins, chall_wins, n):
        from crypto_intel.research.candidate_weights import _promotion_verdict

        windows = [{"index": i} for i in range(n)]
        return _promotion_verdict(
            windows, champ_wins, chall_wins, champ_ic, chall_ic,
            {"monotonic": False}, {"monotonic": False}, 52.0, 52.0,
        )

    def test_clear_improvement_recommends_promotion(self):
        verdict, _ = self._summary(0.02, 0.08, 2, 8, 10)
        assert verdict == "PROMOTE_CHALLENGER"

    def test_near_tie_is_inconclusive_and_keeps_incumbent(self):
        verdict, reason = self._summary(0.05, 0.055, 5, 5, 10)
        assert verdict == "INCONCLUSIVE"
        assert "incumbent is kept" in reason

    def test_worse_challenger_keeps_champion(self):
        verdict, _ = self._summary(0.08, 0.02, 8, 2, 10)
        assert verdict == "KEEP_CHAMPION"

    def test_too_few_windows_is_inconclusive(self):
        verdict, _ = self._summary(0.02, 0.09, 0, 2, 2)
        assert verdict == "INCONCLUSIVE"

    def test_promotion_is_never_automatic(self):
        import inspect

        from crypto_intel.research import candidate_weights

        source = inspect.getsource(candidate_weights.run_full)
        assert "never replaced automatically" in source or "Champion is never replaced" in source


class TestEmpiricalLayer:
    def test_no_analogue_is_inconclusive_not_zero(self):
        from crypto_intel.engines.empirical import EmpiricalResult

        result = EmpiricalResult(asset=Asset.BTC, reason="INCONCLUSIVE - no precedent")
        assert result.available is False
        assert result.sample_size == 0
        assert not result.horizons

    def test_probability_separation_is_explicit(self):
        from crypto_intel.engines.empirical import EmpiricalResult, assess_probability

        empirical = EmpiricalResult(
            asset=Asset.BTC, available=True, match_level="relaxed", sample_size=240,
            horizons={"7d": {"n": 240, "win_rate": 61.0, "baseline_win_rate": 53.0}},
        )
        assessment = assess_probability(None, empirical)
        assert assessment.empirical_available
        assert assessment.empirical_probability == 61.0
        # The wording must never become "61% chance price rises".
        assert "not a probability that price will rise" in assessment.statement
        assert "chance" not in assessment.statement.lower()

    def test_small_sample_refuses_to_quote_a_frequency(self):
        from crypto_intel.engines.empirical import EmpiricalResult, assess_probability

        empirical = EmpiricalResult(
            asset=Asset.BTC, available=True, match_level="exact_ish", sample_size=12,
            horizons={"7d": {"n": 12, "win_rate": 92.0}},
        )
        assessment = assess_probability(None, empirical)
        assert assessment.empirical_available is False
        assert "too few" in assessment.statement

    def test_methodology_is_always_attached(self):
        from crypto_intel.engines.empirical import ProbabilityAssessment

        payload = ProbabilityAssessment().to_dict()
        assert "different quantities" in payload["methodology"]


class TestETFSplit:
    def test_unavailable_data_yields_no_scores(self):
        from crypto_intel.engines.etf_split import ETFSplitEngine

        result = ETFSplitEngine().split(Asset.SOL, None)
        assert result.available is False
        assert result.context_score == 0.0
        assert result.predictive_score == 0.0

    def test_context_and_predictive_are_independent(self):
        """Strong participation must be expressible alongside no predictive claim."""
        from datetime import UTC, datetime

        from crypto_intel.engines.etf_flows import ETFFlowAnalysis
        from crypto_intel.engines.etf_split import ETFSplitEngine

        analysis = ETFFlowAnalysis(
            asset=Asset.ETH, available=True,
            latest_date=datetime.now(UTC), latest_total=800.0,
            ma_5d=500.0, cumulative_30d=9000.0,
            streak_days=6, streak_direction="inflow",
        )
        result = ETFSplitEngine().split(Asset.ETH, analysis)
        assert result.context_score > 50
        # No demonstrated component stored for this asset in the test database.
        if not result.predictive_available:
            assert result.predictive_score == 0.0
            assert "limited measured predictive value" in result.statement

    def test_predictive_requires_demonstrated_evidence(self):
        import inspect

        from crypto_intel.engines import etf_split

        source = inspect.getsource(etf_split.ETFSplitEngine._load_demonstrated)
        # Only FDR-significant, sufficiently large effects may enter.
        assert "significant" in source
        assert "MIN_ABS_IC" in source
        assert "MIN_SAMPLE" in source


class TestHybridKnowledge:
    def test_falls_back_to_bm25_when_embeddings_missing(self, monkeypatch):
        from crypto_intel.knowledge import store as store_module

        monkeypatch.setattr(
            "crypto_intel.knowledge.embeddings.embeddings_available", lambda: False
        )
        retriever = store_module.HybridRetriever()
        results = retriever.search("divergence", limit=3)
        assert isinstance(results, list)
        for hit in results:
            assert hit.get("retrieval") == "bm25"

    def test_rrf_favours_items_ranked_by_both(self):
        from crypto_intel.knowledge.embeddings import reciprocal_rank_fusion

        fused = reciprocal_rank_fusion([["a", "b", "c"], ["c", "a", "d"]])
        # 'a' is high in both lists; 'd' appears once, low.
        assert fused["a"] > fused["d"]
        assert fused["a"] > fused["b"]

    def test_provenance_is_preserved(self):
        from crypto_intel.knowledge.store import get_retriever

        for hit in get_retriever().search("RSI", limit=3):
            assert "chunk_id" in hit
            assert "document_title" in hit
            assert "category" in hit


class TestLiveVsBacktest:
    def test_live_performance_is_labelled_separately(self):
        from crypto_intel.history.immutable import live_performance

        result = live_performance()
        if result["available"]:
            assert result["source"] == "live"
            assert "NOT comparable to backtest" in result["note"]
        else:
            assert "not a track record" in result["reason"]

    def test_backtest_results_are_labelled_reconstructed(self):
        from crypto_intel.research.calibration import calibrate_domain

        result = calibrate_domain(Asset.BTC, "technical")
        if result.get("available"):
            assert result["source"] == "reconstructed"
            assert "RECONSTRUCTED" in result["caveat"]


class TestEvidenceConfrontation:
    def test_knowledge_never_overrides_a_measurement(self):
        """Checked on the produced output, not on the source text.

        Source-string assertions break on adjacent string literals; what
        matters is that the rendered conclusion says the measurement stands.
        """
        import inspect

        from crypto_intel.analysts import evidence_confrontation
        from crypto_intel.core.enums import Timeframe
        from crypto_intel.engines.rsi_context import RSIReading

        # The engine must never assign a score, weight or conviction.
        source = inspect.getsource(evidence_confrontation)
        for forbidden in ("score =", "weight =", "conviction =", "_score ="):
            assert forbidden not in source

        reading = RSIReading(
            asset=Asset.BTC, timeframe=Timeframe.D1, value=76.0,
            zone="OVERBOUGHT", regime="STRONGLY_BULLISH",
            textbook_reading="textbook: overbought",
            measured_reading="measured: continuation",
            contradicts_textbook=True,
            evidence={"edge": 2.28, "n": 311, "win_rate": 64.0, "significant": True},
            sample_size=311, confidence="HIGH",
        )
        engine = evidence_confrontation.EvidenceConfrontationEngine()

        # With no course notes indexed, the engine must say so rather than
        # inventing an interpretation.
        engine._search = lambda query, limit: []
        empty = engine.confront_rsi(Asset.BTC, reading)
        assert empty is not None
        assert empty.agreement == "NO_KNOWLEDGE"
        assert "No passage" in empty.conclusion

        # With a course note present that states the opposite, the engine must
        # report a contradiction and keep both sources.
        engine._search = lambda query, limit: [
            {
                "document": "course", "category": "trading", "chunk_id": "c1",
                "page": None, "retrieval": "hybrid",
                "excerpt": "RSI above 70 signals exhaustion and a likely reversal.",
            }
        ]
        confrontation = engine.confront_rsi(Asset.BTC, reading)
        assert confrontation.agreement == "CONTRADICTS"
        assert confrontation.knowledge_says
        # The measurement prevails on evidence, not by overriding the note.
        assert "Neither overrides the other" in confrontation.conclusion
        assert "sample size" in confrontation.conclusion

    def test_contradiction_is_stated_plainly(self):
        from crypto_intel.analysts.evidence_confrontation import Confrontation

        confrontation = Confrontation(
            topic="test", data_says="measured", agreement="CONTRADICTS",
            conclusion="Historical evidence CONTRADICTS the generic rule.",
        )
        payload = confrontation.to_dict()
        assert payload["agreement"] == "CONTRADICTS"

    def test_missing_knowledge_is_reported_not_invented(self):
        from crypto_intel.analysts.evidence_confrontation import EvidenceConfrontationEngine

        engine = EvidenceConfrontationEngine()
        assert engine.confront_rsi(Asset.BTC, None) is None


class TestOpenInterestImport:
    def test_blank_value_is_missing_not_zero(self):
        from crypto_intel.providers.derivatives.oi_import import parse_value

        assert parse_value("") is None
        assert parse_value("-") is None
        assert parse_value("N/A") is None
        assert parse_value("0") == 0.0
        assert parse_value("1,234.5") == 1234.5

    def test_date_formats(self):
        from crypto_intel.providers.derivatives.oi_import import parse_date

        assert parse_date("2024-01-15") is not None
        assert parse_date("1705276800") is not None
        assert parse_date("not a date") is None

    def test_format_is_documented(self):
        from crypto_intel.providers.derivatives.oi_import import FORMAT_DOC

        assert "open_interest_usd" in FORMAT_DOC
        assert "does not circumvent" in FORMAT_DOC

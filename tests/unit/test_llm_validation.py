"""LLM output validation and the anti-hallucination guard."""

from __future__ import annotations

import json

import pytest

from crypto_intel.core.errors import LLMValidationError
from crypto_intel.llm.base import extract_json
from crypto_intel.llm.providers import MockLLMProvider
from crypto_intel.llm.schemas import AnalystOutput, ChiefAnalystOutput, Finding
from crypto_intel.llm.validation import (
    find_evidence_reference_errors,
    find_unsupported_numbers,
)

CONTEXT = (
    "BTC price 64012.34 USD. ETF net flow 730.8 MUSD on 2026-09-03. "
    "Funding rate 0.000045 per 8h. Market cap 1260000000000 USD. RSI 66.9."
)


class TestJSONExtraction:
    def test_plain_json(self):
        assert json.loads(extract_json('{"a": 1}')) == {"a": 1}

    def test_markdown_fence(self):
        assert json.loads(extract_json('```json\n{"a": 1}\n```')) == {"a": 1}

    def test_surrounded_by_prose(self):
        assert json.loads(extract_json('Here it is: {"a": 1} hope that helps')) == {"a": 1}

    def test_braces_inside_strings(self):
        """Naive brace counting breaks on '}' inside a string value."""
        assert json.loads(extract_json('{"a": "x}y", "b": 2}')) == {"a": "x}y", "b": 2}

    def test_nested_objects(self):
        assert json.loads(extract_json('prefix {"a": {"b": [1,2]}} suffix')) == {"a": {"b": [1, 2]}}


class TestGrounding:
    def test_grounded_output_passes(self):
        text = "BTC trades near 64012 with ETF inflows of 730.8M and RSI at 66.9."
        assert find_unsupported_numbers(text, CONTEXT) == []

    def test_invented_price_is_caught(self):
        assert 71500.0 in find_unsupported_numbers("BTC trades at 71500.", CONTEXT)

    def test_invented_etf_flow_is_caught(self):
        """ETF flows are in the hundreds - the guard must not skip them."""
        assert 950.2 in find_unsupported_numbers("ETF inflows reached 950.2M.", CONTEXT)

    @pytest.mark.parametrize(
        ("text", "unsupported"),
        [
            ("Liquidity reached 500 units.", 500.0),
            ("Allocation rose to 42%.", 42.0),
            ("Reliability is 99.9%.", 99.9),
            ("Volume expanded to 1.8x normal.", 1.8),
        ],
    )
    def test_ungrounded_small_percentage_and_ratio_values_are_rejected(
        self, text: str, unsupported: float
    ):
        assert unsupported in find_unsupported_numbers(text, CONTEXT)

    def test_grounded_small_percentage_and_ratio_values_pass(self):
        context = CONTEXT + " Liquidity 500 units. Allocation 42%. Reliability 99.9%. Volume 1.8x."
        text = "Liquidity is 500, allocation 42%, reliability 99.9%, and volume 1.8x."
        assert find_unsupported_numbers(text, context) == []

    def test_unit_scaling_tolerated(self):
        """1.26 trillion for 1260000000000 is summarising, not inventing."""
        assert find_unsupported_numbers("Market cap is 1.26 trillion.", CONTEXT) == []

    def test_rounding_tolerated(self):
        assert find_unsupported_numbers("Price about 64000.", CONTEXT) == []

    @pytest.mark.parametrize(
        ("context", "claim", "unsupported"),
        [
            (
                "Confidence: 1%. Price: 64012 USD.",
                "The price is 1M USD.",
                1.0,
            ),
            (
                "BTC price is 99.9 USD.",
                "Confidence is 99.9%.",
                99.9,
            ),
            (
                "ETF net flow is 730.8 MUSD.",
                "ETF net flow is 730.8 USD.",
                730.8,
            ),
        ],
    )
    def test_same_digits_do_not_cross_metric_or_unit_boundaries(
        self, context: str, claim: str, unsupported: float
    ):
        assert unsupported in find_unsupported_numbers(claim, context)

    def test_explicit_compatible_currency_conversion_passes(self):
        context = "Market cap is 1260000000000 USD."
        assert find_unsupported_numbers("Market cap is 1.26 trillion USD.", context) == []

    def test_value_from_another_metric_cannot_ground_a_claim(self):
        context = "Price is 42 USD. Allocation is 10%."
        assert find_unsupported_numbers("Allocation is 42%.", context) == [42.0]

    def test_value_from_another_subject_cannot_ground_a_claim(self):
        context = "Technical score is 42. ETF score is 10."
        assert find_unsupported_numbers("The ETF score is 42.", context) == [42.0]


class TestEvidenceReferences:
    def test_findings_are_rejected_when_no_evidence_was_exposed(self):
        findings = [Finding(statement="ETF flows remain positive.")]
        errors = find_evidence_reference_errors(findings, set())
        assert errors == ["finding has no evidence reference: ETF flows remain positive."]

    def test_reference_is_unknown_when_no_evidence_was_exposed(self):
        findings = [
            Finding(
                statement="ETF flows remain positive.",
                evidence_refs=["obs_etf"],
            )
        ]
        errors = find_evidence_reference_errors(findings, set())
        assert errors == ["unknown evidence reference 'obs_etf'"]

    def test_unknown_reference_is_rejected(self):
        findings = [
            Finding(
                statement="ETF net flow is 730.8 MUSD.",
                evidence_refs=["obs_unknown"],
            )
        ]
        errors = find_evidence_reference_errors(findings, {"obs_etf"})
        assert errors == ["unknown evidence reference 'obs_unknown'"]

    def test_finding_requires_a_reference_when_evidence_is_available(self):
        findings = [Finding(statement="ETF flows remain positive.")]
        errors = find_evidence_reference_errors(findings, {"obs_etf"})
        assert errors == ["finding has no evidence reference: ETF flows remain positive."]

    def test_existing_reference_passes(self):
        findings = [
            Finding(
                statement="ETF net flow is 730.8 MUSD.",
                evidence_refs=["obs_etf"],
            )
        ]
        assert find_evidence_reference_errors(findings, {"obs_etf"}) == []


class TestSchemas:
    def test_analyst_output_requires_bounded_score(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            AnalystOutput(analyst="x", summary="long enough summary", score=500, confidence=50)

    def test_direction_is_normalised(self):
        assert Finding(statement="something happened", direction="bullish").direction == "BULLISH"
        assert Finding(statement="something happened", direction="weird").direction == "NEUTRAL"

    def test_evidence_references_are_normalised_and_deduplicated(self):
        finding = Finding(
            statement="something happened",
            evidence_refs=[" obs_1 ", "obs_1", "obs_2"],
        )
        assert finding.evidence_refs == ["obs_1", "obs_2"]

    def test_language_model_cannot_supply_scenario_probabilities(self):
        """Only a separately calibrated deterministic model may quantify them."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ChiefAnalystOutput(
                synthesis="A sufficiently long synthesis string for validation purposes here.",
                scenarios=[
                    {
                        "name": "central",
                        "label": "a",
                        "probability": 60,
                        "narrative": "n" * 20,
                    }
                ],
            )

    def test_scenario_name_normalised(self):
        out = ChiefAnalystOutput(
            synthesis="A sufficiently long synthesis string for validation purposes here.",
            scenarios=[{"name": "wildcard", "label": "a", "narrative": "n" * 20}],
        )
        assert out.scenarios[0].name == "central"


class TestValidatedCompletion:
    async def test_mock_returns_valid_schema(self):
        provider = MockLLMProvider(model="mock")
        out = await provider.complete_json("system", "chief synthesis", ChiefAnalystOutput)
        assert isinstance(out, ChiefAnalystOutput)
        assert out.scenarios == []

    async def test_invalid_output_eventually_raises(self):
        """Unvalidated output must never reach the pipeline."""

        class BrokenProvider(MockLLMProvider):
            async def complete(self, system: str, user: str) -> str:
                return "not json at all"

        with pytest.raises(LLMValidationError):
            await BrokenProvider(model="broken").complete_json(
                "s", "u", AnalystOutput, max_retries=1
            )

    async def test_retry_recovers_from_first_bad_answer(self):
        class FlakyProvider(MockLLMProvider):
            def __init__(self, **kw):
                super().__init__(**kw)
                self.calls = 0

            async def complete(self, system: str, user: str) -> str:
                self.calls += 1
                if self.calls == 1:
                    return "garbage"
                return json.dumps({
                    "analyst": "x", "summary": "a valid summary string", "score": 10,
                    "confidence": 50, "positives": [], "negatives": [],
                    "missing_data": [], "knowledge_citations": [],
                })

        provider = FlakyProvider(model="flaky")
        out = await provider.complete_json("s", "u", AnalystOutput, max_retries=2)
        assert out.score == 10
        assert provider.calls == 2

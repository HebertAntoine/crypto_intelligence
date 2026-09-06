"""LLM output validation and the anti-hallucination guard."""

from __future__ import annotations

import json

import pytest

from crypto_intel.core.errors import LLMValidationError
from crypto_intel.llm.base import extract_json
from crypto_intel.llm.providers import MockLLMProvider
from crypto_intel.llm.schemas import AnalystOutput, ChiefAnalystOutput
from crypto_intel.llm.validation import find_unsupported_numbers

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

    def test_derived_percentages_allowed(self):
        """The model may legitimately compute a percentage change."""
        assert find_unsupported_numbers("Price rose 3.2% on 1.8x volume.", CONTEXT) == []

    def test_small_counters_ignored(self):
        assert find_unsupported_numbers("The top 3 funds; 2 were large.", CONTEXT) == []

    def test_unit_scaling_tolerated(self):
        """1.26 trillion for 1260000000000 is summarising, not inventing."""
        assert find_unsupported_numbers("Market cap is 1.26 trillion.", CONTEXT) == []

    def test_rounding_tolerated(self):
        assert find_unsupported_numbers("Price about 64000.", CONTEXT) == []


class TestSchemas:
    def test_analyst_output_requires_bounded_score(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            AnalystOutput(analyst="x", summary="long enough summary", score=500, confidence=50)

    def test_direction_is_normalised(self):
        from crypto_intel.llm.schemas import Finding

        assert Finding(statement="something happened", direction="bullish").direction == "BULLISH"
        assert Finding(statement="something happened", direction="weird").direction == "NEUTRAL"

    def test_scenario_probabilities_renormalised(self):
        """Models commonly emit 60/30/20; rescale rather than reject."""
        out = ChiefAnalystOutput(
            synthesis="A sufficiently long synthesis string for validation purposes here.",
            scenarios=[
                {"name": "central", "label": "a", "probability": 60, "narrative": "n" * 20},
                {"name": "bull", "label": "b", "probability": 30, "narrative": "n" * 20},
                {"name": "bear", "label": "c", "probability": 20, "narrative": "n" * 20},
            ],
        )
        assert sum(s.probability for s in out.scenarios) == pytest.approx(100.0, abs=0.5)

    def test_scenario_name_normalised(self):
        out = ChiefAnalystOutput(
            synthesis="A sufficiently long synthesis string for validation purposes here.",
            scenarios=[{"name": "wildcard", "label": "a", "probability": 100, "narrative": "n" * 20}],
        )
        assert out.scenarios[0].name == "central"


class TestValidatedCompletion:
    async def test_mock_returns_valid_schema(self):
        provider = MockLLMProvider(model="mock")
        out = await provider.complete_json("system", "chief synthesis", ChiefAnalystOutput)
        assert isinstance(out, ChiefAnalystOutput)
        assert len(out.scenarios) == 3

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

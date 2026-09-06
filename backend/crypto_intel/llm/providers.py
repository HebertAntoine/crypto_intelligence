"""Concrete LLM backends: Anthropic, OpenAI-compatible, Ollama, Mock.

Selected purely from .env. Adding a vendor means adding a class here and one
entry in the factory - no business logic changes.
"""

from __future__ import annotations

import json

import httpx

from ..logging_setup import get_logger
from .base import LLMProvider

log = get_logger("llm.providers")


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    async def complete(self, system: str, user: str) -> str:
        url = (self.base_url or "https://api.anthropic.com") + "/v1/messages"
        payload = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        blocks = data.get("content") or []
        return "".join(b.get("text", "") for b in blocks if b.get("type") == "text")


class OpenAICompatibleProvider(LLMProvider):
    """OpenAI and any API that mirrors /v1/chat/completions."""

    name = "openai"

    async def complete(self, system: str, user: str) -> str:
        url = (self.base_url or "https://api.openai.com/v1") + "/chat/completions"
        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        return data["choices"][0]["message"]["content"]


class OllamaProvider(LLMProvider):
    """Local Ollama - no API key, keeps everything on the machine."""

    name = "ollama"

    async def complete(self, system: str, user: str) -> str:
        url = (self.base_url or "http://localhost:11434") + "/api/chat"
        payload = {
            "model": self.model,
            "stream": False,
            "format": "json",
            "options": {"temperature": self.temperature, "num_predict": self.max_tokens},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
        return (data.get("message") or {}).get("content", "")


class MockLLMProvider(LLMProvider):
    """Deterministic stand-in for MOCK_MODE and tests.

    Returns schema-shaped JSON built from the prompt so the full pipeline can be
    exercised offline. Its output is clearly labelled as mock and it never
    invents market numbers - it only restates that this is a mock run.
    """

    name = "mock"

    async def complete(self, system: str, user: str) -> str:
        lowered = user.lower()
        if "chief" in lowered or "synthesis" in lowered:
            return json.dumps({
                "synthesis": (
                    "MOCK MODE - this narrative is generated locally without a language model. "
                    "The numeric scores, indicators and data provenance shown elsewhere in this "
                    "report are produced by the deterministic Python engines and are real "
                    "(or fixture-based in mock mode). Configure LLM_PROVIDER to enable a real "
                    "narrative synthesis."
                ),
                "positives": ["See the computed domain scores above"],
                "negatives": ["Narrative synthesis unavailable: no LLM configured"],
                "contradictions": [],
                "key_catalysts": [],
                "key_risks": ["LLM narrative disabled - rely on the numeric sections"],
                "what_would_change_my_mind": [],
                "scenarios": [
                    {"name": "central", "label": "Mock central scenario", "probability": 60,
                     "narrative": "MOCK - configure an LLM provider for real scenarios.",
                     "conditions": [], "key_levels": {}, "catalysts": [], "invalidation": ""},
                    {"name": "bull", "label": "Mock bullish scenario", "probability": 20,
                     "narrative": "MOCK - configure an LLM provider for real scenarios.",
                     "conditions": [], "key_levels": {}, "catalysts": [], "invalidation": ""},
                    {"name": "bear", "label": "Mock bearish scenario", "probability": 20,
                     "narrative": "MOCK - configure an LLM provider for real scenarios.",
                     "conditions": [], "key_levels": {}, "catalysts": [], "invalidation": ""},
                ],
                "missing_data": [],
                "data_quality_note": "MOCK MODE - no language model was called.",
            })
        return json.dumps({
            "analyst": "mock_analyst",
            "summary": (
                "MOCK MODE - no language model configured. The numeric score and findings come "
                "from the deterministic engine, not from a model."
            ),
            "score": 0.0,
            "confidence": 0.0,
            "positives": [],
            "negatives": [],
            "missing_data": ["LLM narrative (set LLM_PROVIDER in .env)"],
            "knowledge_citations": [],
        })


def build_provider(
    provider: str, model: str, api_key: str, base_url: str,
    temperature: float, max_tokens: int, timeout: int,
) -> LLMProvider | None:
    key = provider.lower().strip()
    kwargs = {
        "model": model, "api_key": api_key, "base_url": base_url,
        "temperature": temperature, "max_tokens": max_tokens, "timeout": timeout,
    }
    if key == "anthropic":
        return AnthropicProvider(**kwargs)
    if key in ("openai", "openai_compatible", "openrouter", "groq", "together"):
        return OpenAICompatibleProvider(**kwargs)
    if key == "ollama":
        return OllamaProvider(**kwargs)
    if key == "mock":
        return MockLLMProvider(**kwargs)
    return None

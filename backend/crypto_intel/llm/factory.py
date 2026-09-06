"""LLM selection from settings. The system stays fully functional without one."""

from __future__ import annotations

from ..logging_setup import get_logger
from ..settings import get_settings
from .base import LLMProvider
from .providers import MockLLMProvider, build_provider

log = get_logger("llm.factory")

_cached: LLMProvider | None = None
_resolved = False


def get_llm() -> LLMProvider | None:
    """Return the configured provider, or None.

    None is a supported, first-class state: analysts fall back to rule-based
    output and the report is produced without a narrative section.
    """
    global _cached, _resolved
    if _resolved:
        return _cached

    settings = get_settings()
    _resolved = True

    if settings.mock_mode and settings.llm_provider in ("", "none"):
        _cached = MockLLMProvider(model="mock")
        return _cached

    if not settings.llm_enabled:
        log.info("llm_disabled", reason="LLM_PROVIDER not configured or API key missing")
        _cached = None
        return None

    _cached = build_provider(
        settings.llm_provider, settings.llm_model, settings.llm_api_key,
        settings.llm_base_url, settings.llm_temperature,
        settings.llm_max_tokens, settings.llm_timeout,
    )
    if _cached is None:
        log.warning("llm_unknown_provider", provider=settings.llm_provider)
    return _cached


def reset_llm() -> None:
    global _cached, _resolved
    _cached = None
    _resolved = False


def llm_status() -> dict:
    settings = get_settings()
    provider = get_llm()
    return {
        "enabled": provider is not None,
        "provider": settings.llm_provider,
        "model": settings.llm_model if provider else None,
        "is_mock": isinstance(provider, MockLLMProvider),
        "reason": None if provider else (
            "LLM_PROVIDER is 'none' or the API key is missing. The system runs fully "
            "without an LLM: all scores, indicators and data remain available; only the "
            "narrative synthesis is disabled."
        ),
    }

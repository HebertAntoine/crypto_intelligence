"""Exception hierarchy.

Providers are expected NOT to raise into business logic - they return a
qualified empty result instead. These exceptions exist for genuine programming
errors and for configuration problems that should stop startup.
"""

from __future__ import annotations


class CryptoIntelError(Exception):
    """Base for every error raised by this package."""


class ConfigurationError(CryptoIntelError):
    """Malformed or missing configuration - fatal at startup."""


class ProviderError(CryptoIntelError):
    """Internal provider failure. Must be caught inside the provider layer."""


class DataUnavailable(CryptoIntelError):
    """Requested data does not exist. Never satisfy this by inventing a value."""


class LLMValidationError(CryptoIntelError):
    """The model returned something that failed schema or grounding checks."""


class HallucinationDetected(LLMValidationError):
    """The model cited a number that does not appear in the supplied context."""

    def __init__(self, offending: list[str], context_hint: str = "") -> None:
        self.offending = offending
        super().__init__(
            f"Model produced values absent from the provided context: {offending}. {context_hint}"
        )

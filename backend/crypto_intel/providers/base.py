"""Provider interface.

Design rule that shapes the whole project: a provider NEVER raises into
business logic. It returns a FetchResult that is either OK with observations,
or a qualified failure explaining why there is no data. That is what lets the
report say "UNAVAILABLE - source blocks automated access" instead of silently
substituting a number.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from ..core.enums import Asset, FetchStatus, ProviderCategory, Timeframe
from ..core.models import Observation, Provenance


@dataclass(slots=True)
class FetchRequest:
    """What the caller wants. Providers ignore fields they do not support."""

    capability: str
    asset: Asset | None = None
    timeframe: Timeframe | None = None
    limit: int = 300
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class FetchResult:
    """What a provider returns. Never an exception."""

    status: FetchStatus
    observations: list[Observation] = field(default_factory=list)
    raw: Any = None
    message: str = ""
    provider: str = ""

    @property
    def ok(self) -> bool:
        return self.status is FetchStatus.OK and bool(self.observations)

    @property
    def user_message(self) -> str:
        return self.message or self.status.user_message

    @classmethod
    def success(cls, observations: list[Observation], provider: str, raw: Any = None) -> FetchResult:
        if not observations:
            return cls(status=FetchStatus.NO_DATA, provider=provider)
        return cls(status=FetchStatus.OK, observations=observations, provider=provider, raw=raw)

    @classmethod
    def failure(cls, status: FetchStatus, provider: str, message: str = "") -> FetchResult:
        return cls(status=status, provider=provider, message=message or status.user_message)


@dataclass(slots=True)
class ProviderStatus:
    name: str
    available: bool
    reason: str = ""
    requires_key: str | None = None
    configured: bool = True


class BaseProvider(ABC):
    """Every data source implements this.

    Subclasses declare which capabilities they serve; the registry uses that to
    build fallback chains, so swapping Binance for Kraken is a config edit.
    """

    name: str = "base"
    source: str = "unknown"
    category: ProviderCategory = ProviderCategory.MARKET
    capabilities: tuple[str, ...] = ()
    requires_key: str | None = None       # settings attribute name, e.g. "FRED_API_KEY"
    source_url: str = ""
    base_confidence: float = 80.0

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}

    # --- lifecycle --------------------------------------------------------

    async def available(self) -> ProviderStatus:
        """Cheap local check: is this provider usable at all?

        Deliberately does not hit the network - startup must stay fast and
        offline-safe.
        """
        if self.requires_key:
            from ..settings import get_settings

            if not get_settings().has_key(self.requires_key):
                return ProviderStatus(
                    name=self.name,
                    available=False,
                    reason=f"UNAVAILABLE - provider not configured ({self.requires_key} missing)",
                    requires_key=self.requires_key,
                    configured=False,
                )
        return ProviderStatus(name=self.name, available=True)

    @abstractmethod
    async def fetch(self, request: FetchRequest) -> FetchResult:
        """Fetch and normalize. Must catch its own exceptions."""

    # --- helpers for subclasses ------------------------------------------

    def provenance(self, url: str | None = None) -> Provenance:
        return Provenance(
            source=self.source,
            provider=self.name,
            source_url=url or self.source_url or None,
        )

    def supports(self, capability: str) -> bool:
        return capability in self.capabilities

    def __repr__(self) -> str:
        return f"<{type(self).__name__} name={self.name!r}>"

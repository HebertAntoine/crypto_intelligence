"""Common contract for attributed whale-transfer providers."""

from __future__ import annotations

from abc import abstractmethod
from typing import Any

from ...engines.whales import WhaleObservation
from ..base import BaseProvider


class WhaleProvider(BaseProvider):
    """A provider that can normalize its payload to ``WhaleObservation``.

    Fetching remains provider-specific because REST, WebSocket and aggregate
    metric APIs have different lifecycle semantics. The common boundary is the
    normalized observation, so the intelligence engine works with zero, one,
    or many provider feeds without provider-specific branches.
    """

    capabilities = ("whales.transfers",)

    @abstractmethod
    def normalize(self, payload: Any) -> list[WhaleObservation]:
        """Normalize provider payload; malformed rows are skipped, not guessed."""

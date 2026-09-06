"""Optional paid whale-data providers.

The project must work without any subscription. Each of these returns
NOT_CONFIGURED when its key is absent, which the analyst turns into
"UNAVAILABLE - provider not configured".

No whale signal is EVER synthesized from nothing: a fabricated whale signal is
one of the most dangerous outputs this kind of tool can produce, so the absence
of a reliable source produces an absence of signal, not a guess.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, ClassVar

from ...core.enums import DataQuality, FetchStatus, ProviderCategory
from ...core.freshness import compute_freshness
from ...core.models import Observation
from ...settings import get_settings
from ..base import BaseProvider, FetchRequest, FetchResult
from ..http import get_http


class GlassnodeProvider(BaseProvider):
    name = "glassnode"
    source = "Glassnode"
    category = ProviderCategory.WHALES
    capabilities = ("whales.flows",)
    requires_key = "GLASSNODE_API_KEY"
    source_url = "https://glassnode.com"
    base_confidence = 90.0

    # Exchange flows are the most decision-relevant whale metrics.
    METRICS: ClassVar[dict[str, tuple[str, str]]] = {
        "transactions/transfers_volume_to_exchanges_sum": ("whale.exchange_inflow", "USD"),
        "transactions/transfers_volume_from_exchanges_sum": ("whale.exchange_outflow", "USD"),
        "distribution/balance_exchanges": ("whale.exchange_balance", "native"),
    }

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.base_url = self.config.get("base_url", "https://api.glassnode.com/v1")

    async def fetch(self, request: FetchRequest) -> FetchResult:
        settings = get_settings()
        if not settings.glassnode_api_key.strip():
            return FetchResult.failure(FetchStatus.NOT_CONFIGURED, self.name)
        if request.asset is None:
            return FetchResult.failure(FetchStatus.NO_DATA, self.name)

        http = get_http()
        out: list[Observation] = []
        for path, (metric, unit) in self.METRICS.items():
            url = f"{self.base_url}/metrics/{path}"
            res = await http.get_json(
                url, provider=self.name,
                params={"a": request.asset.value, "api_key": settings.glassnode_api_key, "i": "24h"},
                cache_ttl=3600, rate_limit_per_min=20,
            )
            if not res.ok or not isinstance(res.data, list):
                continue
            prov = self.provenance(url)
            for row in res.data[-30:]:
                try:
                    ts = datetime.fromtimestamp(int(row["t"]), tz=UTC)
                    value = float(row["v"])
                except (KeyError, ValueError, TypeError):
                    continue
                out.append(Observation(
                    asset=request.asset, metric=metric, value=value, unit=unit, timestamp=ts,
                    provenance=prov, freshness=compute_freshness(ts, "whale"),
                    confidence=self.base_confidence, quality=DataQuality.MEASURED,
                    meta={"reliability": "HIGH"},
                ))
        if not out:
            return FetchResult.failure(FetchStatus.NO_DATA, self.name)
        return FetchResult.success(out, self.name)


class _UnconfiguredPaidProvider(BaseProvider):
    """Connector present, endpoints subscription-specific.

    Rather than guessing an API shape we cannot test, these report clearly that
    they need an active subscription. Guessing would risk silently producing
    wrong numbers - worse than no numbers.
    """

    category = ProviderCategory.WHALES
    capabilities = ("whales.flows",)

    async def fetch(self, request: FetchRequest) -> FetchResult:
        if not get_settings().has_key(self.requires_key or ""):
            return FetchResult.failure(FetchStatus.NOT_CONFIGURED, self.name)
        return FetchResult.failure(
            FetchStatus.NOT_CONFIGURED, self.name,
            f"{self.source} connector present; endpoint mapping requires an active subscription "
            "and has not been verified against a live account.",
        )


class CryptoQuantProvider(_UnconfiguredPaidProvider):
    name = "cryptoquant"
    source = "CryptoQuant"
    requires_key = "CRYPTOQUANT_API_KEY"
    source_url = "https://cryptoquant.com"


class NansenProvider(_UnconfiguredPaidProvider):
    name = "nansen"
    source = "Nansen"
    requires_key = "NANSEN_API_KEY"
    source_url = "https://nansen.ai"


class ArkhamProvider(_UnconfiguredPaidProvider):
    name = "arkham"
    source = "Arkham Intelligence"
    requires_key = "ARKHAM_API_KEY"
    source_url = "https://arkhamintelligence.com"

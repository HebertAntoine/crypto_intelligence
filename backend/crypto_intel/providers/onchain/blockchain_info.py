"""Bitcoin on-chain metrics from blockchain.info.

BTC-specific by design: hashrate, difficulty, mempool and UTXO matter here and
have no equivalent on Ethereum or Solana. Applying one metric set to all three
chains would be an analytical error, so each chain has its own provider.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ...core.enums import Asset, DataQuality, FetchStatus, ProviderCategory
from ...core.freshness import compute_freshness
from ...core.models import Observation
from ..base import BaseProvider, FetchRequest, FetchResult
from ..http import get_http

# endpoint -> (metric, unit, scale)
_QUERIES: dict[str, tuple[str, str, float]] = {
    "24hrtransactioncount": ("onchain.tx_count_24h", "count", 1.0),
    "hashrate": ("onchain.hashrate", "GH/s", 1.0),
    "getdifficulty": ("onchain.difficulty", "raw", 1.0),
    "24hrbtcsent": ("onchain.btc_sent_24h", "BTC", 1e-8),   # satoshis -> BTC
    "totalbc": ("onchain.circulating_supply", "BTC", 1e-8),
    "avgtxsize": ("onchain.avg_tx_size", "bytes", 1.0),
}


class BlockchainInfoProvider(BaseProvider):
    name = "blockchain_info"
    source = "Blockchain.com"
    category = ProviderCategory.ONCHAIN
    capabilities = ("onchain.btc",)
    source_url = "https://blockchain.info"
    base_confidence = 85.0

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.base_url = self.config.get("base_url", "https://blockchain.info")
        self.rate = int(self.config.get("rate_limit_per_min", 20))
        self.ttl = int((self.config.get("cache_ttl") or {}).get("default", 900))

    async def fetch(self, request: FetchRequest) -> FetchResult:
        if request.capability != "onchain.btc":
            return FetchResult.failure(FetchStatus.DISABLED, self.name)

        http = get_http()
        now = datetime.now(UTC)
        out: list[Observation] = []

        for endpoint, (metric, unit, scale) in _QUERIES.items():
            url = f"{self.base_url}/q/{endpoint}"
            res = await http.get_text(
                url, provider=self.name, cache_ttl=self.ttl, rate_limit_per_min=self.rate
            )
            if not res.ok:
                continue  # one missing metric must not void the others
            try:
                value = float(str(res.data).strip()) * scale
            except (ValueError, TypeError):
                continue
            out.append(Observation(
                asset=Asset.BTC, metric=metric, value=value, unit=unit, timestamp=now,
                provenance=self.provenance(url), freshness=compute_freshness(now, "onchain"),
                confidence=self.base_confidence, quality=DataQuality.MEASURED,
            ))

        if not out:
            return FetchResult.failure(FetchStatus.NO_DATA, self.name)
        return FetchResult.success(out, self.name)

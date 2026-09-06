"""Blockchair stats for Bitcoin and Ethereum.

Same endpoint shape, different metric sets: BTC exposes hashrate/difficulty/
UTXO, ETH exposes gas and burn. The mapping tables below encode that
difference explicitly rather than reusing one generic list.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, ClassVar

from ...core.enums import Asset, DataQuality, FetchStatus, ProviderCategory
from ...core.freshness import compute_freshness
from ...core.models import Observation
from ..base import BaseProvider, FetchRequest, FetchResult
from ..http import get_http


class _BlockchairBase(BaseProvider):
    category = ProviderCategory.ONCHAIN
    base_confidence = 84.0
    chain_asset: Asset = Asset.BTC
    field_map: ClassVar[dict[str, tuple[str, str, float]]] = {}

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.base_url = self.config.get("base_url", "https://api.blockchair.com/bitcoin")
        self.rate = int(self.config.get("rate_limit_per_min", 10))
        self.ttl = int((self.config.get("cache_ttl") or {}).get("default", 900))

    async def fetch(self, request: FetchRequest) -> FetchResult:
        url = f"{self.base_url}/stats"
        res = await get_http().get_json(
            url, provider=self.name, cache_ttl=self.ttl, rate_limit_per_min=self.rate
        )
        if not res.ok:
            return FetchResult.failure(res.status, self.name, res.message)

        data = (res.data or {}).get("data") or {}
        if not data:
            return FetchResult.failure(FetchStatus.NO_DATA, self.name)

        now = datetime.now(UTC)
        prov = self.provenance(url)
        out: list[Observation] = []
        for field, (metric, unit, scale) in self.field_map.items():
            raw = data.get(field)
            if raw is None:
                continue
            try:
                value = float(raw) * scale
            except (TypeError, ValueError):
                continue
            out.append(Observation(
                asset=self.chain_asset, metric=metric, value=value, unit=unit, timestamp=now,
                provenance=prov, freshness=compute_freshness(now, "onchain"),
                confidence=self.base_confidence, quality=DataQuality.MEASURED,
            ))
        if not out:
            return FetchResult.failure(FetchStatus.NO_DATA, self.name)
        return FetchResult.success(out, self.name)


class BlockchairBTCProvider(_BlockchairBase):
    name = "blockchair_btc"
    source = "Blockchair (Bitcoin)"
    capabilities = ("onchain.btc",)
    source_url = "https://blockchair.com/bitcoin"
    chain_asset = Asset.BTC
    field_map: ClassVar[dict[str, tuple[str, str, float]]] = {
        "transactions_24h": ("onchain.tx_count_24h", "count", 1.0),
        "volume_24h": ("onchain.tx_volume_24h", "BTC", 1e-8),
        "mempool_transactions": ("onchain.mempool_tx", "count", 1.0),
        "mempool_size": ("onchain.mempool_size", "bytes", 1.0),
        "hashrate_24h": ("onchain.hashrate", "H/s", 1.0),
        "difficulty": ("onchain.difficulty", "raw", 1.0),
        "average_transaction_fee_24h": ("onchain.avg_fee", "sat", 1.0),
        "median_transaction_fee_24h": ("onchain.median_fee", "sat", 1.0),
        "outputs": ("onchain.utxo_count", "count", 1.0),
        "blocks_24h": ("onchain.blocks_24h", "count", 1.0),
    }

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.base_url = self.config.get("base_url", "https://api.blockchair.com/bitcoin")


class BlockchairETHProvider(_BlockchairBase):
    name = "blockchair_eth"
    source = "Blockchair (Ethereum)"
    capabilities = ("onchain.eth",)
    source_url = "https://blockchair.com/ethereum"
    chain_asset = Asset.ETH
    # No hashrate/difficulty/UTXO here: Ethereum is proof-of-stake and
    # account-based. Gas and burn are the meaningful metrics instead.
    field_map: ClassVar[dict[str, tuple[str, str, float]]] = {
        "transactions_24h": ("onchain.tx_count_24h", "count", 1.0),
        "calls_24h": ("onchain.contract_calls_24h", "count", 1.0),
        "average_transaction_fee_24h_usd": ("onchain.avg_fee_usd", "USD", 1.0),
        "median_gas_price_24h": ("onchain.gas_price_median", "wei", 1.0),
        "mempool_transactions": ("onchain.mempool_tx", "count", 1.0),
        "blocks_24h": ("onchain.blocks_24h", "count", 1.0),
        "circulation": ("onchain.circulating_supply", "ETH", 1e-18),
        "uncles_24h": ("onchain.uncles_24h", "count", 1.0),
    }

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.base_url = self.config.get("base_url", "https://api.blockchair.com/ethereum")

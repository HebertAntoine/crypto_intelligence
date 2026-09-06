"""Solana network metrics via JSON-RPC.

Solana-specific reasoning built in: the raw transaction count is dominated by
validator vote transactions and is misleading as an activity measure. This
provider therefore reports `tps_non_vote` separately from `tps_total`, and the
analyst layer uses the non-vote figure for user activity.

The public RPC is rate limited, so calls are few and cached. A dedicated
endpoint (Helius, QuickNode, Triton) via SOLANA_RPC_URL is more reliable.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ...core.enums import Asset, DataQuality, FetchStatus, ProviderCategory
from ...core.freshness import compute_freshness
from ...core.models import Observation
from ...settings import get_settings
from ..base import BaseProvider, FetchRequest, FetchResult
from ..http import get_http


class SolanaRPCProvider(BaseProvider):
    name = "solana_rpc"
    source = "Solana RPC"
    category = ProviderCategory.ONCHAIN
    capabilities = ("onchain.sol",)
    source_url = "https://api.mainnet-beta.solana.com"
    base_confidence = 82.0

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        configured = str(self.config.get("base_url") or "").strip()
        if not configured or configured.startswith("${"):
            configured = get_settings().solana_rpc_url
        self.base_url = configured
        self.rate = int(self.config.get("rate_limit_per_min", 10))
        self.ttl = int((self.config.get("cache_ttl") or {}).get("default", 900))

    async def _rpc(self, method: str, params: list[Any] | None = None) -> Any | None:
        res = await get_http().post_json(
            self.base_url,
            provider=self.name,
            payload={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or []},
            cache_ttl=self.ttl,
            rate_limit_per_min=self.rate,
        )
        if not res.ok:
            return None
        return (res.data or {}).get("result")

    async def fetch(self, request: FetchRequest) -> FetchResult:
        if request.capability != "onchain.sol":
            return FetchResult.failure(FetchStatus.DISABLED, self.name)

        now = datetime.now(UTC)
        prov = self.provenance(self.base_url)
        out: list[Observation] = []

        def add(metric: str, value: float, unit: str, meta: dict | None = None) -> None:
            out.append(Observation(
                asset=Asset.SOL, metric=metric, value=value, unit=unit, timestamp=now,
                provenance=prov, freshness=compute_freshness(now, "onchain"),
                confidence=self.base_confidence, quality=DataQuality.MEASURED, meta=meta or {},
            ))

        samples = await self._rpc("getRecentPerformanceSamples", [10])
        if isinstance(samples, list) and samples:
            total_tx = sum(int(s.get("numTransactions", 0)) for s in samples)
            total_secs = sum(int(s.get("samplePeriodSecs", 0)) for s in samples)
            # numNonVoteTransactions is absent on older RPC versions - we skip
            # the metric rather than approximate it.
            has_non_vote = all("numNonVoteTransactions" in s for s in samples)
            if total_secs > 0:
                add("onchain.tps_total", total_tx / total_secs, "tps",
                    {"note": "includes validator vote transactions"})
                if has_non_vote:
                    non_vote = sum(int(s.get("numNonVoteTransactions", 0)) for s in samples)
                    add("onchain.tps_non_vote", non_vote / total_secs, "tps",
                        {"note": "user activity - excludes validator votes"})
                    if total_tx:
                        add("onchain.vote_share_pct",
                            (total_tx - non_vote) / total_tx * 100.0, "pct")
            slots = sum(int(s.get("numSlots", 0)) for s in samples)
            if total_secs > 0 and slots:
                add("onchain.slots_per_sec", slots / total_secs, "slots/s")

        supply = await self._rpc("getSupply", [{"excludeNonCirculatingAccountsList": True}])
        if isinstance(supply, dict):
            val = supply.get("value", {})
            if "circulating" in val:
                add("onchain.circulating_supply", float(val["circulating"]) / 1e9, "SOL")
            if "total" in val:
                add("onchain.total_supply", float(val["total"]) / 1e9, "SOL")

        epoch = await self._rpc("getEpochInfo")
        if isinstance(epoch, dict) and epoch.get("slotsInEpoch"):
            add("onchain.epoch", float(epoch.get("epoch", 0)), "count")
            add("onchain.epoch_progress",
                float(epoch.get("slotIndex", 0)) / float(epoch["slotsInEpoch"]) * 100.0, "pct")

        health = await self._rpc("getHealth")
        if health is not None:
            add("onchain.rpc_healthy", 1.0 if health == "ok" else 0.0, "bool")

        if not out:
            return FetchResult.failure(
                FetchStatus.NO_DATA, self.name,
                "Solana RPC returned no usable data (public endpoint is often rate limited; "
                "set SOLANA_RPC_URL to a dedicated endpoint for reliability)",
            )
        return FetchResult.success(out, self.name)

"""Bitcoin chain facts the cycle reading needs, from mempool.space (no key).

Only protocol rules are constants: a halving happens every 210 000 blocks.
Every date is read from the chain: the last halving is the timestamp of its
block; the next one is estimated from the observed pace of the last 2 016
blocks, and labelled as an estimate.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from ...core.enums import DataQuality, FetchStatus, ProviderCategory
from ...core.freshness import compute_freshness
from ...core.models import Observation
from ..base import BaseProvider, FetchRequest, FetchResult
from ..http import get_http

MEMPOOL = "https://mempool.space/api"
HALVING_INTERVAL = 210_000  # protocol rule
PACE_WINDOW = 2_016  # one difficulty period


def last_halving_height(tip: int) -> int:
    return (tip // HALVING_INTERVAL) * HALVING_INTERVAL


def next_halving_estimate(
    tip: int, tip_time: datetime, average_block_seconds: float
) -> tuple[int, datetime]:
    target = last_halving_height(tip) + HALVING_INTERVAL
    remaining = target - tip
    return target, tip_time + timedelta(seconds=remaining * average_block_seconds)


def _block_timestamp(payload: Any) -> datetime | None:
    # /v1/blocks/{height} lists blocks from that height downwards.
    if isinstance(payload, list) and payload:
        try:
            return datetime.fromtimestamp(int(payload[0]["timestamp"]), UTC)
        except (KeyError, TypeError, ValueError):
            return None
    return None


class BitcoinChainProvider(BaseProvider):
    name = "mempool_space_chain"
    source = "mempool.space"
    category = ProviderCategory.ONCHAIN
    capabilities = ("onchain.btc_cycle",)
    base_confidence = 92.0
    source_url = "https://mempool.space/"

    def _obs(self, metric: str, value: float, when: datetime, unit: str, label: str,
             endpoint: str, extra: dict[str, Any] | None = None) -> Observation:
        return Observation(
            metric=metric,
            value=value,
            unit=unit,
            timestamp=when,
            provenance=self.provenance(self.source_url),
            freshness=compute_freshness(when, "onchain"),
            confidence=self.base_confidence,
            quality=DataQuality.MEASURED,
            meta={"label": label, "source_tier": "OFFICIAL", "endpoint": endpoint, **(extra or {})},
        )

    async def fetch(self, request: FetchRequest) -> FetchResult:
        http = get_http()
        tip_res = await http.get_text(f"{MEMPOOL}/blocks/tip/height", provider=self.name,
                                      cache_ttl=300, rate_limit_per_min=20)
        if not tip_res.ok:
            return FetchResult.failure(FetchStatus.NETWORK_ERROR, self.name)
        try:
            tip = int(str(tip_res.data).strip())
        except ValueError:
            return FetchResult.failure(FetchStatus.PARSE_ERROR, self.name)

        heights = {"tip": tip, "past": tip - PACE_WINDOW, "halving": last_halving_height(tip)}
        stamps: dict[str, datetime] = {}
        for key, height in heights.items():
            res = await http.get_json(f"{MEMPOOL}/v1/blocks/{height}", provider=self.name,
                                      cache_ttl=300 if key == "tip" else 86_400,
                                      rate_limit_per_min=20)
            stamp = _block_timestamp(res.data) if res.ok else None
            if stamp is None:
                return FetchResult.failure(FetchStatus.NO_DATA, self.name)
            stamps[key] = stamp

        # Every past halving, each stamped at its own block time, so a study
        # dated in 2021 sees the 2020 halving and not the 2024 one.
        past_halvings: list[tuple[int, datetime]] = []
        for height in range(HALVING_INTERVAL, heights["halving"] + 1, HALVING_INTERVAL):
            if height == heights["halving"]:
                past_halvings.append((height, stamps["halving"]))
                continue
            res = await http.get_json(f"{MEMPOOL}/v1/blocks/{height}", provider=self.name,
                                      cache_ttl=7 * 86_400, rate_limit_per_min=20)
            stamp = _block_timestamp(res.data) if res.ok else None
            if stamp is not None:
                past_halvings.append((height, stamp))

        pace = (stamps["tip"] - stamps["past"]).total_seconds() / PACE_WINDOW
        target, eta = next_halving_estimate(tip, stamps["tip"], pace)
        now = stamps["tip"]
        endpoint = f"{MEMPOOL}/v1/blocks/{{height}}"
        out = [
            self._obs("btc.chain.height", tip, now, "blocks", "Hauteur de la chaîne Bitcoin", endpoint),
            self._obs("btc.chain.avg_block_seconds", pace, now, "s",
                      "Temps moyen par bloc (2 016 derniers)", endpoint),
            self._obs("btc.halving.last_epoch", stamps["halving"].timestamp(), now, "epoch_s",
                      "Date du dernier halving (horodatage du bloc)", endpoint,
                      {"height": heights["halving"]}),
            self._obs("btc.halving.next_epoch_estimate", eta.timestamp(), now, "epoch_s",
                      "Date estimée du prochain halving", endpoint,
                      {"height": target, "estimated": True, "pace_seconds": round(pace, 1)}),
        ]
        out.extend(
            self._obs("btc.halving.block_epoch", when.timestamp(), when, "epoch_s",
                      f"Halving du bloc {height:,}".replace(",", " "), endpoint, {"height": height})
            for height, when in past_halvings
        )
        return FetchResult.success(out, self.name)

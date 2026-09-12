"""Whale Alert attributed-transfer API (optional paid credential)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from ...core.enums import Asset, FetchStatus, ProviderCategory
from ...engines.whales import WhaleTransfer
from ...settings import get_settings
from ..base import BaseProvider, FetchRequest, FetchResult
from ..http import get_http

_ASSETS = {
    "BTC": Asset.BTC,
    "BITCOIN": Asset.BTC,
    "ETH": Asset.ETH,
    "ETHEREUM": Asset.ETH,
    "SOL": Asset.SOL,
    "SOLANA": Asset.SOL,
}


def parse_whale_alert_payload(payload: Any) -> list[WhaleTransfer]:
    if not isinstance(payload, dict) or not isinstance(payload.get("transactions"), list):
        return []
    transfers: list[WhaleTransfer] = []
    for row in payload["transactions"]:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol") or row.get("blockchain") or "").upper()
        asset = _ASSETS.get(symbol)
        if asset is None:
            continue
        try:
            amount_usd = float(row["amount_usd"])
            raw_timestamp = row["timestamp"]
            timestamp = (
                datetime.fromtimestamp(float(raw_timestamp), tz=UTC)
                if isinstance(raw_timestamp, int | float)
                else datetime.fromisoformat(str(raw_timestamp).replace("Z", "+00:00")).astimezone(UTC)
            )
        except (KeyError, TypeError, ValueError, OSError):
            continue
        origin = row.get("from") if isinstance(row.get("from"), dict) else {}
        destination = row.get("to") if isinstance(row.get("to"), dict) else {}
        transaction_id = str(row.get("id") or row.get("hash") or "").strip()
        if amount_usd <= 0 or not transaction_id:
            continue
        source_url = str(row.get("source_url") or "https://whale-alert.io/transaction")
        transfers.append(
            WhaleTransfer(
                id=transaction_id,
                asset=asset,
                timestamp=timestamp.isoformat(),
                amount_usd=amount_usd,
                from_entity=origin.get("owner"),
                from_entity_type=str(origin.get("owner_type") or "unknown"),
                to_entity=destination.get("owner"),
                to_entity_type=str(destination.get("owner_type") or "unknown"),
                transaction_type=str(row.get("transaction_type") or "transfer"),
                source="Whale Alert",
                source_url=source_url,
            )
        )
    return transfers


class WhaleAlertProvider(BaseProvider):
    name = "whale_alert"
    source = "Whale Alert"
    category = ProviderCategory.WHALES
    capabilities = ("whales.transfers",)
    requires_key = "WHALE_ALERT_API_KEY"
    source_url = "https://api.whale-alert.io/v1/transactions"
    base_confidence = 85.0

    async def fetch(self, request: FetchRequest) -> FetchResult:
        settings = get_settings()
        if not settings.whale_alert_api_key.strip():
            return FetchResult.failure(
                FetchStatus.NOT_CONFIGURED,
                self.name,
                "UNAVAILABLE - WHALE_ALERT_API_KEY not configured",
            )
        start = int((datetime.now(UTC) - timedelta(hours=1)).timestamp())
        result = await get_http().get_json(
            self.source_url,
            provider=self.name,
            params={
                "api_key": settings.whale_alert_api_key,
                "start": start,
                "min_value": int(self.config.get("min_value_usd", 1_000_000)),
            },
            cache_ttl=300,
            rate_limit_per_min=10,
            retries=1,
        )
        if not result.ok:
            return FetchResult.failure(result.status, self.name, result.message)
        transfers = parse_whale_alert_payload(result.data)
        if request.asset:
            transfers = [item for item in transfers if item.asset is request.asset]
        if not transfers:
            return FetchResult.failure(FetchStatus.NO_DATA, self.name)
        return FetchResult(
            status=FetchStatus.OK,
            raw={"transfers": [item.model_dump(mode="json") for item in transfers]},
            provider=self.name,
        )

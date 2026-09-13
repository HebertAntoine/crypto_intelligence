"""Whale Alert attributed-transfer API (optional paid credential)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ...core.enums import Asset, FetchStatus, ProviderCategory
from ...engines.whales import (
    WhaleObservation,
    WhaleProvenance,
    normalize_entity_type,
)
from ...settings import get_settings
from ..base import FetchRequest, FetchResult
from ..http import get_http
from .base import WhaleProvider

_ASSETS = {
    "BTC": Asset.BTC,
    "BITCOIN": Asset.BTC,
    "ETH": Asset.ETH,
    "ETHEREUM": Asset.ETH,
    "SOL": Asset.SOL,
    "SOLANA": Asset.SOL,
}


def _amount_rows(row: dict[str, Any]) -> list[dict[str, Any]]:
    if row.get("symbol"):
        return [row]
    amounts = row.get("amounts")
    if isinstance(amounts, list):
        return [
            {**item, "transaction_type": row.get("transaction_type", "transfer")}
            for item in amounts
            if isinstance(item, dict)
        ]
    raw_transaction = row.get("transaction")
    transaction: dict[str, Any] = raw_transaction if isinstance(raw_transaction, dict) else row
    sub_transactions = transaction.get("sub_transactions")
    if not isinstance(sub_transactions, list):
        return []
    output: list[dict[str, Any]] = []
    for item in sub_transactions:
        if not isinstance(item, dict):
            continue
        raw_inputs = item.get("inputs")
        raw_outputs = item.get("outputs")
        inputs: list[Any] = raw_inputs if isinstance(raw_inputs, list) else []
        outputs: list[Any] = raw_outputs if isinstance(raw_outputs, list) else []
        origin: dict[str, Any] = inputs[0] if inputs and isinstance(inputs[0], dict) else {}
        destination: dict[str, Any] = (
            outputs[0] if outputs and isinstance(outputs[0], dict) else {}
        )
        try:
            input_total: float = sum(
                abs(float(value.get("amount", 0)))
                for value in inputs
                if isinstance(value, dict)
            )
            output_total: float = sum(
                abs(float(value.get("amount", 0)))
                for value in outputs
                if isinstance(value, dict)
            )
            amount_asset = max(input_total, output_total)
            unit_price = float(item.get("unit_price_usd") or 0)
        except (TypeError, ValueError):
            continue
        output.append(
            {
                "symbol": item.get("symbol"),
                "amount": amount_asset,
                "amount_usd": amount_asset * unit_price if unit_price > 0 else None,
                "transaction_type": item.get("transaction_type", "transfer"),
                "from": origin,
                "to": destination,
            }
        )
    return output


def parse_whale_alert_payload(payload: Any) -> list[WhaleObservation]:
    if not isinstance(payload, dict) or not isinstance(payload.get("transactions"), list):
        return []
    transfers: list[WhaleObservation] = []
    for row in payload["transactions"]:
        if not isinstance(row, dict):
            continue
        try:
            raw_timestamp = row["timestamp"]
            timestamp = (
                datetime.fromtimestamp(float(raw_timestamp), tz=UTC)
                if isinstance(raw_timestamp, int | float)
                else datetime.fromisoformat(str(raw_timestamp).replace("Z", "+00:00")).astimezone(UTC)
            )
        except (KeyError, TypeError, ValueError, OSError):
            continue
        transaction_id = str(row.get("id") or row.get("hash") or "").strip()
        raw_transaction = row.get("transaction")
        transaction: dict[str, Any] = raw_transaction if isinstance(raw_transaction, dict) else {}
        transaction_id = transaction_id or str(transaction.get("hash") or "").strip()
        if not transaction_id:
            continue
        source_url = str(row.get("source_url") or "https://whale-alert.io/transaction")
        for index, amount_row in enumerate(_amount_rows(row)):
            symbol = str(
                amount_row.get("symbol") or row.get("blockchain") or ""
            ).upper()
            asset = _ASSETS.get(symbol)
            if asset is None:
                continue
            try:
                amount_usd_raw = amount_row.get("amount_usd", amount_row.get("value_usd"))
                amount_usd = float(amount_usd_raw) if amount_usd_raw is not None else None
                amount_asset_raw = amount_row.get("amount")
                # Legacy responses may only expose USD. Keep native quantity
                # unavailable rather than relabelling dollars as BTC/ETH/SOL.
                amount_asset = (
                    float(amount_asset_raw)
                    if amount_asset_raw is not None
                    else None
                )
            except (TypeError, ValueError):
                continue
            if (
                (amount_asset is not None and amount_asset <= 0)
                or (amount_usd is not None and amount_usd <= 0)
                or (amount_asset is None and amount_usd is None)
            ):
                continue
            raw_origin = amount_row.get("from")
            if not isinstance(raw_origin, dict):
                raw_origin = row.get("from")
            origin: dict[str, Any] = raw_origin if isinstance(raw_origin, dict) else {}
            raw_destination = amount_row.get("to")
            if not isinstance(raw_destination, dict):
                raw_destination = row.get("to")
            destination: dict[str, Any] = (
                raw_destination if isinstance(raw_destination, dict) else {}
            )
            transfers.append(
                WhaleObservation(
                    id=f"{transaction_id}:{symbol}:{index}",
                    asset=asset,
                    observed_at=timestamp,
                    amount_asset=amount_asset,
                    amount_usd=amount_usd,
                    from_entity=origin.get("owner"),
                    to_entity=destination.get("owner"),
                    from_type=normalize_entity_type(
                        origin.get("owner_type") or origin.get("address_type")
                    ),
                    to_type=normalize_entity_type(
                        destination.get("owner_type") or destination.get("address_type")
                    ),
                    transaction_type=str(
                        amount_row.get("transaction_type")
                        or row.get("transaction_type")
                        or "transfer"
                    ),
                    provider="Whale Alert",
                    confidence=0.85,
                    provenance=[
                        WhaleProvenance(
                            source="Whale Alert",
                            source_url=source_url,
                            transaction_hash=transaction_id,
                            evidence_ids=[transaction_id],
                        )
                    ],
                )
            )
    return transfers


class WhaleAlertProvider(WhaleProvider):
    name = "whale_alert"
    source = "Whale Alert"
    category = ProviderCategory.WHALES
    requires_key = "WHALE_ALERT_API_KEY"
    source_url = "https://leviathan.whale-alert.io"
    base_confidence = 85.0

    def normalize(self, payload: Any) -> list[WhaleObservation]:
        return parse_whale_alert_payload(payload)

    async def fetch(self, request: FetchRequest) -> FetchResult:
        settings = get_settings()
        if not settings.whale_alert_api_key.strip():
            return FetchResult.failure(
                FetchStatus.NOT_CONFIGURED,
                self.name,
                "UNAVAILABLE - WHALE_ALERT_API_KEY not configured",
            )
        if request.asset is None:
            return FetchResult.failure(FetchStatus.NO_DATA, self.name, "asset is required")
        blockchain = {
            Asset.BTC: "bitcoin",
            Asset.ETH: "ethereum",
            Asset.SOL: "solana",
        }.get(request.asset)
        if blockchain is None:
            return FetchResult.failure(FetchStatus.NO_DATA, self.name)
        http = get_http()
        status = await http.get_json(
            f"{self.source_url}/{blockchain}/status",
            provider=self.name,
            params={"api_key": settings.whale_alert_api_key},
            cache_ttl=60,
            rate_limit_per_min=10,
            retries=1,
        )
        if not status.ok or not isinstance(status.data, dict):
            return FetchResult.failure(status.status, self.name, status.message)
        try:
            end_height = int(status.data["end_height"])
            minimum_height = int(status.data.get("min_plan_height", 0))
        except (KeyError, TypeError, ValueError):
            return FetchResult.failure(
                FetchStatus.PARSE_ERROR, self.name, "Whale Alert status lacks block heights"
            )
        start_height = max(
            minimum_height,
            end_height - int(self.config.get("block_lookback", 100)),
        )
        result = await get_http().get_json(
            f"{self.source_url}/{blockchain}/transactions",
            provider=self.name,
            params={
                "api_key": settings.whale_alert_api_key,
                "start_height": start_height,
                "end_height": end_height,
                "symbol": request.asset.value,
                "limit": min(100, request.limit),
                "order": "desc",
            },
            cache_ttl=300,
            rate_limit_per_min=10,
            retries=1,
        )
        if not result.ok:
            return FetchResult.failure(result.status, self.name, result.message)
        transfers = self.normalize(result.data)
        if request.asset:
            transfers = [item for item in transfers if item.asset is request.asset]
        if not transfers:
            return FetchResult.failure(FetchStatus.NO_DATA, self.name)
        return FetchResult(
            status=FetchStatus.OK,
            raw={"whale_observations": [item.model_dump(mode="json") for item in transfers]},
            provider=self.name,
        )

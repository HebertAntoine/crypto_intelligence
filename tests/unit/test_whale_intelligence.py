from __future__ import annotations

from crypto_intel.core.enums import Asset
from crypto_intel.engines.whales import (
    WhaleIntelligenceEngine,
    WhaleState,
    WhaleTransfer,
    WhaleTransferKind,
)
from crypto_intel.providers.whales.whale_alert import parse_whale_alert_payload


def _transfer(
    origin: str,
    destination: str,
    *,
    amount: float = 100_000_000,
    identifier: str = "tx-1",
) -> WhaleTransfer:
    return WhaleTransfer(
        id=identifier,
        asset=Asset.BTC,
        timestamp="2028-09-10T10:00:00Z",
        amount_usd=amount,
        from_entity_type=origin,
        to_entity_type=destination,
        source="Whale Alert",
        source_url=f"https://whale-alert.io/{identifier}",
    )


def test_exchange_to_wallet_is_not_bearish():
    transfer = _transfer("exchange", "unknown wallet")
    result = WhaleIntelligenceEngine().analyze(Asset.BTC, [transfer])

    assert transfer.kind is WhaleTransferKind.EXCHANGE_TO_WALLET
    assert result.state is WhaleState.ACCUMULATION
    assert result.exchange_withdrawals_usd == transfer.amount_usd
    assert result.is_certainty is False


def test_wallet_to_exchange_adds_sell_pressure_but_not_certainty():
    transfer = _transfer("unknown wallet", "exchange")
    result = WhaleIntelligenceEngine().analyze(Asset.BTC, [transfer])

    assert transfer.kind is WhaleTransferKind.WALLET_TO_EXCHANGE
    assert result.state is WhaleState.DISTRIBUTION
    assert result.potential_sell_pressure == 1.0
    assert result.is_certainty is False
    assert any("potentielle" in factor for factor in result.factors)


def test_exchange_to_exchange_and_wallet_to_wallet_are_neutral():
    transfers = [
        _transfer("exchange", "exchange", identifier="internal"),
        _transfer("wallet", "custody", identifier="self-custody"),
    ]
    result = WhaleIntelligenceEngine().analyze(Asset.BTC, transfers)

    assert result.state is WhaleState.NEUTRAL
    assert result.potential_sell_pressure is None
    assert result.unknown_transfers == 2


def test_one_large_transfer_cannot_create_a_strong_state():
    transfer = _transfer("wallet", "exchange", amount=900_000_000)

    result = WhaleIntelligenceEngine().analyze(Asset.BTC, [transfer])

    assert result.state is WhaleState.DISTRIBUTION
    assert result.state is not WhaleState.STRONG_DISTRIBUTION


def test_missing_transfer_data_is_not_silently_neutral():
    result = WhaleIntelligenceEngine().analyze(Asset.SOL, [])

    assert result.available is False
    assert result.state is WhaleState.INSUFFICIENT_DATA
    assert "UNAVAILABLE" in result.unavailable_reason


def test_whale_alert_parser_preserves_entity_direction_and_provenance():
    payload = {
        "transactions": [
            {
                "id": "api-tx",
                "symbol": "BTC",
                "timestamp": 1_852_192_800,
                "amount_usd": 50_000_000,
                "from": {"owner": "Fund A", "owner_type": "wallet"},
                "to": {"owner": "Exchange B", "owner_type": "exchange"},
                "transaction_type": "transfer",
                "source_url": "https://whale-alert.io/transaction/api-tx",
            }
        ]
    }

    transfer = parse_whale_alert_payload(payload)[0]

    assert transfer.kind is WhaleTransferKind.WALLET_TO_EXCHANGE
    assert transfer.from_entity == "Fund A"
    assert transfer.to_entity == "Exchange B"
    assert transfer.source_url.endswith("api-tx")

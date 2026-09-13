"""WhaleAnalyzer.

Two rules govern this module:

  1. "Whale" is defined PER ASSET, in config/assets.yaml. 100 BTC, 1000 ETH and
     50000 SOL are different amounts of conviction; a single universal
     threshold would be meaningless.

  2. No reliable source -> NO SIGNAL. Not a weak signal, not a guess. A
     fabricated whale movement is among the most damaging things this tool
     could output, so absence of data produces absence of signal, and every
     emitted signal carries an explicit reliability level.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..config_loader import asset_meta
from ..core.enums import Asset, Direction, Freshness, Reliability
from ..core.freshness import worst_freshness
from ..core.models import Observation, WhaleSignal


class WhaleAnalysis(BaseModel):
    asset: Asset
    available: bool = False
    unavailable_reason: str | None = None
    threshold: float | None = None
    threshold_unit: str = ""
    signals: list[WhaleSignal] = Field(default_factory=list)
    exchange_netflow: float | None = None
    behaviour: str | None = None
    reliability: Reliability = Reliability.UNVERIFIED
    direction: Direction = Direction.INCONCLUSIVE
    strength: float = 0.0
    confidence: float = 0.0
    freshness: Freshness = Freshness.UNAVAILABLE
    evidence_ids: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    configured_providers: list[str] = Field(default_factory=list)


class WhaleAnalyzer:
    name = "whale_analyzer"

    def analyze(
        self,
        asset: Asset,
        observations: list[Observation],
        unavailable_reason: str | None = None,
        configured_providers: list[str] | None = None,
    ) -> WhaleAnalysis:
        try:
            meta = asset_meta(asset.value)
            threshold = float(meta.get("whale_threshold", 0))
            unit = str(meta.get("whale_threshold_unit", asset.value))
        except Exception:
            threshold, unit = 0.0, asset.value

        if unavailable_reason or not observations:
            return WhaleAnalysis(
                asset=asset,
                available=False,
                unavailable_reason=(
                    unavailable_reason
                    or "UNAVAILABLE - provider not configured. Whale flow data requires a "
                       "paid subscription (Glassnode, CryptoQuant, Nansen or Arkham). "
                       "No whale signal is inferred without a reliable source."
                ),
                threshold=threshold, threshold_unit=unit,
                confidence=0.0, freshness=Freshness.UNAVAILABLE,
                configured_providers=configured_providers or [],
                findings=[],
            )

        by_metric: dict[str, list[Observation]] = {}
        for o in observations:
            by_metric.setdefault(o.metric, []).append(o)
        for lst in by_metric.values():
            lst.sort(key=lambda o: o.timestamp)

        def latest(metric: str) -> float | None:
            lst = by_metric.get(metric)
            return lst[-1].numeric_value if lst else None

        inflow = latest("whale.exchange_inflow")
        outflow = latest("whale.exchange_outflow")
        signals: list[WhaleSignal] = []
        findings: list[str] = []
        netflow = None
        behaviour = None
        score = 0.0

        # Reliability comes from the provider, not from us.
        reliability = Reliability.UNVERIFIED
        for o in observations:
            declared = str(o.meta.get("reliability", "")).upper()
            if declared in Reliability.__members__:
                reliability = Reliability[declared]
                break

        if inflow is not None and outflow is not None:
            netflow = inflow - outflow
            avg_flow = (abs(inflow) + abs(outflow)) / 2.0 or 1.0
            ratio = netflow / avg_flow

            if ratio < -0.15:
                behaviour = "from_exchange"
                score = min(45.0, abs(ratio) * 120.0)
                findings.append(
                    f"Net {abs(netflow):,.0f} leaving exchanges - coins moving to self-custody, "
                    "historically associated with accumulation and reduced sell pressure"
                )
            elif ratio > 0.15:
                behaviour = "to_exchange"
                score = -min(45.0, ratio * 120.0)
                findings.append(
                    f"Net {netflow:,.0f} moving onto exchanges - typically a precursor to "
                    "selling, though it can also reflect collateral movements"
                )
            else:
                behaviour = "neutral"
                findings.append("Exchange flows broadly balanced - no clear whale direction")

            signals.append(WhaleSignal(
                asset=asset, behaviour=behaviour or "neutral", magnitude=netflow,
                unit="USD", reliability=reliability,
                threshold_used=threshold, threshold_unit=unit,
                source=observations[0].provenance.source,
                evidence_ids=[o.id for o in observations[:20]],
            ))

        balance_series = [o.numeric_value for o in by_metric.get("whale.exchange_balance", [])
                          if o.numeric_value is not None]
        if len(balance_series) >= 8:
            recent = float(np.mean(balance_series[-3:]))
            prior = float(np.mean(balance_series[-8:-3]))
            if prior:
                change = (recent - prior) / prior * 100.0
                if change < -1.0:
                    findings.append(
                        f"Exchange-held supply down {abs(change):.2f}% - supply is leaving "
                        "trading venues"
                    )
                    score += 12
                elif change > 1.0:
                    findings.append(f"Exchange-held supply up {change:.2f}%")
                    score -= 12

        whale_ratio = latest("whale.exchange_whale_ratio")
        if whale_ratio is not None:
            findings.append(
                f"Exchange whale ratio {whale_ratio:.3f}: concentration mesurée des dix "
                "plus gros dépôts, sans direction de prix déduite isolément."
            )

        if not signals and not findings:
            return WhaleAnalysis(
                asset=asset, available=False,
                unavailable_reason="UNAVAILABLE - source returned no usable whale metrics",
                threshold=threshold, threshold_unit=unit,
                configured_providers=configured_providers or [],
            )

        # Confidence is tied to the source's own reliability - a LOW-reliability
        # heuristic must never dominate the aggregate.
        confidence = {
            Reliability.HIGH: 85.0, Reliability.MEDIUM: 60.0,
            Reliability.LOW: 30.0, Reliability.UNVERIFIED: 15.0,
        }[reliability]

        direction = (
            Direction.BULLISH if score > 12
            else Direction.BEARISH if score < -12
            else Direction.NEUTRAL
        )
        return WhaleAnalysis(
            asset=asset, available=True, threshold=threshold, threshold_unit=unit,
            signals=signals, exchange_netflow=netflow, behaviour=behaviour,
            reliability=reliability, direction=direction,
            strength=round(max(-100.0, min(100.0, score)), 1), confidence=confidence,
            freshness=worst_freshness([o.freshness for o in observations]),
            evidence_ids=[o.id for o in observations[:30]],
            findings=findings, configured_providers=configured_providers or [],
        )


class WhaleTransferKind(StrEnum):
    WALLET_TO_EXCHANGE = "WALLET_TO_EXCHANGE"
    EXCHANGE_TO_WALLET = "EXCHANGE_TO_WALLET"
    EXCHANGE_TO_EXCHANGE = "EXCHANGE_TO_EXCHANGE"
    WALLET_TO_WALLET = "WALLET_TO_WALLET"
    MINT = "MINT"
    BURN = "BURN"
    UNKNOWN = "UNKNOWN"


class WhaleState(StrEnum):
    STRONG_ACCUMULATION = "STRONG_ACCUMULATION"
    ACCUMULATION = "ACCUMULATION"
    NEUTRAL = "NEUTRAL"
    DISTRIBUTION = "DISTRIBUTION"
    STRONG_DISTRIBUTION = "STRONG_DISTRIBUTION"
    UNAVAILABLE = "UNAVAILABLE"
    INSUFFICIENT_DATA = "UNAVAILABLE"  # backwards-compatible enum alias


class WhaleEntityType(StrEnum):
    WALLET = "WALLET"
    EXCHANGE = "EXCHANGE"
    CUSTODY = "CUSTODY"
    ETF = "ETF"
    MINER = "MINER"
    PROTOCOL = "PROTOCOL"
    UNKNOWN = "UNKNOWN"


class WhaleProvenance(BaseModel):
    model_config = ConfigDict(frozen=True)

    source: str
    source_url: str | None = None
    transaction_hash: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)


def normalize_entity_type(value: str | WhaleEntityType | None) -> WhaleEntityType:
    if isinstance(value, WhaleEntityType):
        return value
    raw = str(value or "").strip().lower()
    if not raw or raw == "unknown":
        return WhaleEntityType.UNKNOWN
    if "exchange" in raw:
        return WhaleEntityType.EXCHANGE
    if any(word in raw for word in ("custody", "custodian", "cold storage")):
        return WhaleEntityType.CUSTODY
    if "etf" in raw or "fund" in raw:
        return WhaleEntityType.ETF
    if "miner" in raw or "mining" in raw:
        return WhaleEntityType.MINER
    if any(word in raw for word in ("protocol", "bridge", "defi", "contract")):
        return WhaleEntityType.PROTOCOL
    if "wallet" in raw or "address" in raw:
        return WhaleEntityType.WALLET
    return WhaleEntityType.UNKNOWN


class WhaleObservation(BaseModel):
    """Provider-neutral attributed transfer. Interpretation remains potential."""

    model_config = ConfigDict(frozen=True)

    id: str
    asset: Asset
    observed_at: datetime
    amount_asset: float | None = Field(default=None, gt=0)
    amount_usd: float | None = Field(default=None, gt=0)
    from_entity: str | None = None
    to_entity: str | None = None
    from_type: WhaleEntityType = WhaleEntityType.UNKNOWN
    to_type: WhaleEntityType = WhaleEntityType.UNKNOWN
    transaction_type: str = "transfer"
    provider: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    provenance: list[WhaleProvenance] = Field(default_factory=list)

    @field_validator("observed_at")
    @classmethod
    def ensure_utc(cls, value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

    @property
    def transaction_hash(self) -> str | None:
        return next(
            (item.transaction_hash for item in self.provenance if item.transaction_hash),
            None,
        )

    @property
    def timestamp(self) -> str:
        return self.observed_at.isoformat()

    @property
    def source(self) -> str:
        return self.provider

    @property
    def source_url(self) -> str:
        return next((item.source_url for item in self.provenance if item.source_url), "") or ""

    @property
    def from_entity_type(self) -> str:
        return self.from_type.value

    @property
    def to_entity_type(self) -> str:
        return self.to_type.value

    @property
    def evidence_ids(self) -> list[str]:
        return list(
            dict.fromkeys(
                evidence
                for item in self.provenance
                for evidence in item.evidence_ids
            )
        )

    @property
    def kind(self) -> WhaleTransferKind:
        tx_type = self.transaction_type.lower()
        if tx_type == "mint":
            return WhaleTransferKind.MINT
        if tx_type == "burn":
            return WhaleTransferKind.BURN
        mapping = {
            (WhaleEntityType.WALLET, WhaleEntityType.EXCHANGE): (
                WhaleTransferKind.WALLET_TO_EXCHANGE
            ),
            (WhaleEntityType.EXCHANGE, WhaleEntityType.WALLET): (
                WhaleTransferKind.EXCHANGE_TO_WALLET
            ),
            (WhaleEntityType.EXCHANGE, WhaleEntityType.CUSTODY): (
                WhaleTransferKind.EXCHANGE_TO_WALLET
            ),
            (WhaleEntityType.EXCHANGE, WhaleEntityType.EXCHANGE): (
                WhaleTransferKind.EXCHANGE_TO_EXCHANGE
            ),
            (WhaleEntityType.WALLET, WhaleEntityType.WALLET): (
                WhaleTransferKind.WALLET_TO_WALLET
            ),
            (WhaleEntityType.WALLET, WhaleEntityType.CUSTODY): (
                WhaleTransferKind.WALLET_TO_WALLET
            ),
        }
        return mapping.get((self.from_type, self.to_type), WhaleTransferKind.UNKNOWN)

    @property
    def deduplication_key(self) -> str:
        transaction_hash = self.transaction_hash
        if transaction_hash:
            return f"{self.asset.value}:{transaction_hash.lower()}:{self.transaction_type.lower()}"
        minute = self.observed_at.replace(second=0, microsecond=0).isoformat()
        raw = "|".join(
            (
                self.asset.value,
                minute,
                (
                    f"{self.amount_asset:.8f}"
                    if self.amount_asset is not None
                    else "UNAVAILABLE"
                ),
                (self.from_entity or self.from_type.value).strip().lower(),
                (self.to_entity or self.to_type.value).strip().lower(),
                self.transaction_type.lower(),
            )
        )
        return "whale:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


class WhaleTransfer(BaseModel):
    """Legacy provider adapter; new integrations emit ``WhaleObservation``."""

    id: str
    asset: Asset
    timestamp: str
    amount_asset: float | None = Field(default=None, gt=0)
    amount_usd: float = Field(gt=0)
    from_entity: str | None = None
    from_entity_type: str = "unknown"
    to_entity: str | None = None
    to_entity_type: str = "unknown"
    transaction_type: str = "transfer"
    source: str
    source_url: str
    evidence_ids: list[str] = Field(default_factory=list)

    @property
    def kind(self) -> WhaleTransferKind:
        tx_type = self.transaction_type.lower()
        if tx_type == "mint":
            return WhaleTransferKind.MINT
        if tx_type == "burn":
            return WhaleTransferKind.BURN

        return self.to_observation().kind

    def to_observation(self) -> WhaleObservation:
        observed = datetime.fromisoformat(self.timestamp.replace("Z", "+00:00"))
        return WhaleObservation(
            id=self.id,
            asset=self.asset,
            observed_at=observed,
            # Legacy rows did not retain native amount. Null is the only
            # honest value: a USD amount must never masquerade as native units.
            amount_asset=self.amount_asset,
            amount_usd=self.amount_usd,
            from_entity=self.from_entity,
            to_entity=self.to_entity,
            from_type=normalize_entity_type(self.from_entity_type),
            to_type=normalize_entity_type(self.to_entity_type),
            transaction_type=self.transaction_type,
            provider=self.source,
            confidence=0.85,
            provenance=[
                WhaleProvenance(
                    source=self.source,
                    source_url=self.source_url,
                    transaction_hash=self.id,
                    evidence_ids=self.evidence_ids,
                )
            ],
        )


class WhaleIntelligenceAnalysis(BaseModel):
    available: bool
    asset: Asset
    state: WhaleState = WhaleState.UNAVAILABLE
    exchange_deposits_usd: float = 0.0
    exchange_withdrawals_usd: float = 0.0
    classified_transfers: int = 0
    unknown_transfers: int = 0
    duplicate_transfers: int = 0
    provider_count: int = 0
    potential_sell_pressure: float | None = None
    confidence: float = 0.0
    is_certainty: bool = False
    factors: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    provenance: list[dict[str, Any]] = Field(default_factory=list)
    unavailable_reason: str | None = None
    explanation: str = ""


class WhaleIntelligenceEngine:
    """Classify transfer direction before assigning any pressure signal."""

    @staticmethod
    def deduplicate(observations: list[WhaleObservation]) -> tuple[list[WhaleObservation], int]:
        grouped: dict[str, list[WhaleObservation]] = {}
        for observation in observations:
            grouped.setdefault(observation.deduplication_key, []).append(observation)
        merged: list[WhaleObservation] = []
        for duplicates in grouped.values():
            primary = max(duplicates, key=lambda item: item.confidence)
            provenance: dict[tuple[str, str | None, str | None], WhaleProvenance] = {}
            for item in duplicates:
                for source in item.provenance:
                    provenance[(source.source, source.source_url, source.transaction_hash)] = source
            merged.append(
                primary.model_copy(
                    update={
                        "provenance": list(provenance.values()),
                        "confidence": max(item.confidence for item in duplicates),
                    }
                )
            )
        return merged, len(observations) - len(merged)

    def analyze(
        self,
        asset: Asset,
        transfers: list[WhaleObservation | WhaleTransfer],
    ) -> WhaleIntelligenceAnalysis:
        normalized = [
            item.to_observation() if isinstance(item, WhaleTransfer) else item
            for item in transfers
        ]
        asset_observations = [item for item in normalized if item.asset is asset]
        provider_count = len({item.provider for item in asset_observations})
        relevant, duplicate_count = self.deduplicate(asset_observations)
        if not relevant:
            return WhaleIntelligenceAnalysis(
                available=False,
                asset=asset,
                unavailable_reason="UNAVAILABLE - no attributed whale transfer source",
                explanation="No whale state is inferred from missing transfers.",
            )

        deposits = sum(
            transfer.amount_usd or 0.0
            for transfer in relevant
            if transfer.kind is WhaleTransferKind.WALLET_TO_EXCHANGE
        )
        withdrawals = sum(
            transfer.amount_usd or 0.0
            for transfer in relevant
            if transfer.kind is WhaleTransferKind.EXCHANGE_TO_WALLET
        )
        classified = [
            transfer
            for transfer in relevant
            if transfer.kind in {
                WhaleTransferKind.WALLET_TO_EXCHANGE,
                WhaleTransferKind.EXCHANGE_TO_WALLET,
            }
            and transfer.amount_usd is not None
        ]
        unknown = sum(
            transfer.kind
            in {
                WhaleTransferKind.UNKNOWN,
                WhaleTransferKind.WALLET_TO_WALLET,
                WhaleTransferKind.EXCHANGE_TO_EXCHANGE,
            }
            for transfer in relevant
        )
        directional_total = deposits + withdrawals
        pressure = (
            (deposits - withdrawals) / directional_total if directional_total > 0 else None
        )
        if pressure is None:
            state = WhaleState.NEUTRAL
        elif pressure >= 0.6 and len(classified) >= 3:
            state = WhaleState.STRONG_DISTRIBUTION
        elif pressure > 0.15:
            state = WhaleState.DISTRIBUTION
        elif pressure <= -0.6 and len(classified) >= 3:
            state = WhaleState.STRONG_ACCUMULATION
        elif pressure < -0.15:
            state = WhaleState.ACCUMULATION
        else:
            state = WhaleState.NEUTRAL

        factors: list[str] = []
        if deposits:
            factors.append(
                "Des portefeuilles ont envoyé des actifs vers des exchanges : "
                "pression vendeuse potentielle, sans preuve de vente."
            )
        if withdrawals:
            factors.append(
                "Des exchanges ont envoyé des actifs vers des portefeuilles/custodies : "
                "signal compatible avec une accumulation."
            )
        if unknown:
            factors.append(
                f"{unknown} transfert(s) interne(s) ou non attribué(s) restent directionnellement neutres."
            )
        mean_source_confidence = sum(item.confidence for item in relevant) / len(relevant)
        confidence = (
            min(0.9, mean_source_confidence * len(classified) / max(3, len(relevant)))
            if classified
            else min(0.25, mean_source_confidence)
        )
        return WhaleIntelligenceAnalysis(
            available=True,
            asset=asset,
            state=state,
            exchange_deposits_usd=deposits,
            exchange_withdrawals_usd=withdrawals,
            classified_transfers=len(classified),
            unknown_transfers=unknown,
            duplicate_transfers=duplicate_count,
            provider_count=provider_count,
            potential_sell_pressure=pressure,
            confidence=confidence,
            is_certainty=False,
            factors=factors,
            evidence_ids=sorted(
                {
                    evidence
                    for transfer in relevant
                    for evidence in [
                        transfer.id,
                        *(
                            evidence_id
                            for source in transfer.provenance
                            for evidence_id in source.evidence_ids
                        ),
                    ]
                }
            ),
            provenance=[
                source.model_dump(mode="json")
                for source in {
                    (entry.source, entry.source_url, entry.transaction_hash): entry
                    for item in relevant
                    for entry in item.provenance
                }.values()
            ],
            explanation=(
                "Only wallet→exchange and exchange→wallet transfers contribute direction. "
                "The state describes potential pressure and is never proof of a trade."
            ),
        )

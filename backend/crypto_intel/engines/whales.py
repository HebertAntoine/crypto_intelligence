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

from enum import StrEnum

import numpy as np
from pydantic import BaseModel, Field

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
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class WhaleTransfer(BaseModel):
    id: str
    asset: Asset
    timestamp: str
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

        def group(value: str) -> str:
            lowered = value.lower()
            if "exchange" in lowered:
                return "exchange"
            if any(word in lowered for word in ("wallet", "custody", "custodian", "unknown")):
                return "wallet"
            return "unknown"

        origin = group(self.from_entity_type)
        destination = group(self.to_entity_type)
        mapping = {
            ("wallet", "exchange"): WhaleTransferKind.WALLET_TO_EXCHANGE,
            ("exchange", "wallet"): WhaleTransferKind.EXCHANGE_TO_WALLET,
            ("exchange", "exchange"): WhaleTransferKind.EXCHANGE_TO_EXCHANGE,
            ("wallet", "wallet"): WhaleTransferKind.WALLET_TO_WALLET,
        }
        return mapping.get((origin, destination), WhaleTransferKind.UNKNOWN)


class WhaleIntelligenceAnalysis(BaseModel):
    available: bool
    asset: Asset
    state: WhaleState = WhaleState.INSUFFICIENT_DATA
    exchange_deposits_usd: float = 0.0
    exchange_withdrawals_usd: float = 0.0
    classified_transfers: int = 0
    unknown_transfers: int = 0
    potential_sell_pressure: float | None = None
    confidence: float = 0.0
    is_certainty: bool = False
    factors: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    provenance: list[dict[str, str]] = Field(default_factory=list)
    unavailable_reason: str | None = None
    explanation: str = ""


class WhaleIntelligenceEngine:
    """Classify transfer direction before assigning any pressure signal."""

    def analyze(self, asset: Asset, transfers: list[WhaleTransfer]) -> WhaleIntelligenceAnalysis:
        relevant = [transfer for transfer in transfers if transfer.asset is asset]
        if not relevant:
            return WhaleIntelligenceAnalysis(
                available=False,
                asset=asset,
                unavailable_reason="UNAVAILABLE - no attributed whale transfer source",
                explanation="No whale state is inferred from missing transfers.",
            )

        deposits = sum(
            transfer.amount_usd
            for transfer in relevant
            if transfer.kind is WhaleTransferKind.WALLET_TO_EXCHANGE
        )
        withdrawals = sum(
            transfer.amount_usd
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
        confidence = min(0.9, len(classified) / max(3, len(relevant))) if classified else 0.25
        return WhaleIntelligenceAnalysis(
            available=True,
            asset=asset,
            state=state,
            exchange_deposits_usd=deposits,
            exchange_withdrawals_usd=withdrawals,
            classified_transfers=len(classified),
            unknown_transfers=unknown,
            potential_sell_pressure=pressure,
            confidence=confidence,
            is_certainty=False,
            factors=factors,
            evidence_ids=sorted(
                {
                    evidence
                    for transfer in relevant
                    for evidence in [transfer.id, *transfer.evidence_ids]
                }
            ),
            provenance=[
                {"source": source, "source_url": url}
                for source, url in sorted({(item.source, item.source_url) for item in relevant})
            ],
            explanation=(
                "Only wallet→exchange and exchange→wallet transfers contribute direction. "
                "The state describes potential pressure and is never proof of a trade."
            ),
        )

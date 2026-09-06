"""OnChainAnalyzer - metrics interpreted per blockchain, never generically.

Bitcoin, Ethereum and Solana have different architectures, so the same metric
name would mean different things (or nothing) across them:

  BTC  proof-of-work, UTXO   -> hashrate, difficulty, fees, mempool
  ETH  proof-of-stake, EVM   -> gas, burn, contract calls, staking
  SOL  PoH + PoS, high TPS   -> non-vote TPS, priority fees, epoch health

The class dispatches per asset. There is deliberately no shared "generic
on-chain score" that would average incomparable things together.
"""

from __future__ import annotations

import numpy as np
from pydantic import BaseModel, Field

from ..config_loader import asset_meta
from ..core.enums import Asset, Direction, Freshness
from ..core.freshness import worst_freshness
from ..core.models import Observation


class OnChainAnalysis(BaseModel):
    asset: Asset
    available: bool = True
    unavailable_reason: str | None = None
    chain_type: str = ""
    metrics: dict[str, float] = Field(default_factory=dict)
    units: dict[str, str] = Field(default_factory=dict)
    trends: dict[str, float] = Field(default_factory=dict)
    direction: Direction = Direction.INCONCLUSIVE
    strength: float = 0.0
    freshness: Freshness = Freshness.UNAVAILABLE
    evidence_ids: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    not_applicable: list[str] = Field(default_factory=list)


class OnChainAnalyzer:
    name = "onchain_analyzer"

    def analyze(
        self,
        asset: Asset,
        observations: list[Observation],
        unavailable_reason: str | None = None,
    ) -> OnChainAnalysis:
        if unavailable_reason or not observations:
            return OnChainAnalysis(
                asset=asset, available=False,
                unavailable_reason=unavailable_reason
                or f"UNAVAILABLE - no on-chain data for {asset.value}",
            )

        latest: dict[str, Observation] = {}
        series: dict[str, list[Observation]] = {}
        for o in observations:
            series.setdefault(o.metric, []).append(o)
        for metric, lst in series.items():
            lst.sort(key=lambda o: o.timestamp)
            latest[metric] = lst[-1]

        metrics = {m: o.numeric_value for m, o in latest.items() if o.numeric_value is not None}
        units = {m: o.unit for m, o in latest.items()}

        trends: dict[str, float] = {}
        for metric, lst in series.items():
            values = [o.numeric_value for o in lst if o.numeric_value is not None]
            if len(values) >= 8:
                recent = float(np.mean(values[-3:]))
                prior = float(np.mean(values[-8:-3]))
                if abs(prior) > 1e-12:
                    trends[metric] = (recent - prior) / abs(prior) * 100.0

        try:
            meta = asset_meta(asset.value)
        except Exception:
            meta = {}
        chain_type = str(meta.get("consensus", ""))
        not_applicable = list(meta.get("irrelevant_metrics", []))

        if asset is Asset.BTC:
            findings, strength = self._analyze_btc(metrics, trends)
        elif asset is Asset.ETH:
            findings, strength = self._analyze_eth(metrics, trends)
        elif asset is Asset.SOL:
            findings, strength = self._analyze_sol(metrics, trends)
        else:
            findings, strength = [], 0.0

        direction = (
            Direction.BULLISH if strength > 12
            else Direction.BEARISH if strength < -12
            else Direction.NEUTRAL
        )
        return OnChainAnalysis(
            asset=asset, available=True, chain_type=chain_type,
            metrics=metrics, units=units, trends=trends,
            direction=direction, strength=round(strength, 1),
            freshness=worst_freshness([o.freshness for o in latest.values()]),
            evidence_ids=[o.id for o in latest.values()],
            findings=findings, not_applicable=not_applicable,
        )

    # --- Bitcoin: security budget and settlement demand ----------------------

    def _analyze_btc(self, m: dict[str, float], t: dict[str, float]) -> tuple[list[str], float]:
        findings: list[str] = []
        score = 0.0

        hashrate = m.get("onchain.hashrate")
        hash_trend = t.get("onchain.hashrate")
        if hashrate is not None:
            if hash_trend is not None and hash_trend > 3:
                findings.append(
                    f"Hashrate rising ({hash_trend:+.1f}%): miners are committing more capital, "
                    "which reflects confidence in future revenue"
                )
                score += 10
            elif hash_trend is not None and hash_trend < -5:
                findings.append(
                    f"Hashrate falling ({hash_trend:.1f}%): miner capitulation is a stress signal"
                )
                score -= 12

        tx = m.get("onchain.tx_count_24h")
        tx_trend = t.get("onchain.tx_count_24h")
        if tx is not None:
            findings.append(f"{tx:,.0f} transactions in the last 24h")
            if tx_trend is not None and tx_trend > 8:
                findings.append(f"Transaction count up {tx_trend:+.1f}% - settlement demand rising")
                score += 8
            elif tx_trend is not None and tx_trend < -12:
                findings.append(f"Transaction count down {tx_trend:.1f}% - network activity cooling")
                score -= 8

        mempool = m.get("onchain.mempool_tx")
        if mempool is not None and mempool > 50_000:
            findings.append(
                f"Mempool congested ({mempool:,.0f} pending): block space demand is elevated"
            )
            score += 4

        if m.get("onchain.difficulty") is not None:
            findings.append(f"Difficulty {m['onchain.difficulty']:,.0f}")

        return findings, max(-100.0, min(100.0, score))

    # --- Ethereum: burn, gas, contract usage ---------------------------------

    def _analyze_eth(self, m: dict[str, float], t: dict[str, float]) -> tuple[list[str], float]:
        findings: list[str] = []
        score = 0.0

        calls = m.get("onchain.contract_calls_24h")
        calls_trend = t.get("onchain.contract_calls_24h")
        if calls is not None:
            findings.append(f"{calls:,.0f} contract calls in 24h")
            if calls_trend is not None and calls_trend > 10:
                findings.append(
                    f"Contract activity up {calls_trend:+.1f}% - real usage of the network is rising"
                )
                score += 12
            elif calls_trend is not None and calls_trend < -12:
                findings.append(f"Contract activity down {calls_trend:.1f}%")
                score -= 10

        tx = m.get("onchain.tx_count_24h")
        tx_trend = t.get("onchain.tx_count_24h")
        if tx is not None:
            findings.append(f"{tx:,.0f} transactions in 24h")
            if tx_trend is not None and abs(tx_trend) > 10:
                score += 6 if tx_trend > 0 else -6

        gas = m.get("onchain.gas_price_median")
        if gas is not None:
            gwei = gas / 1e9
            findings.append(f"Median gas price {gwei:.2f} gwei")
            # High gas = congestion = demand, but also a UX drag. Mildly positive.
            if gwei > 40:
                findings.append("Elevated gas: blockspace demand is high")
                score += 5
            elif gwei < 3:
                findings.append("Very low gas: little competition for blockspace")
                score -= 5

        fee = m.get("onchain.avg_fee_usd")
        if fee is not None:
            findings.append(f"Average transaction fee ${fee:.2f}")

        return findings, max(-100.0, min(100.0, score))

    # --- Solana: real user activity, excluding validator votes ---------------

    def _analyze_sol(self, m: dict[str, float], t: dict[str, float]) -> tuple[list[str], float]:
        findings: list[str] = []
        score = 0.0

        non_vote = m.get("onchain.tps_non_vote")
        total_tps = m.get("onchain.tps_total")

        if non_vote is not None:
            findings.append(f"{non_vote:,.0f} non-vote TPS (real user activity)")
            trend = t.get("onchain.tps_non_vote")
            if trend is not None and trend > 10:
                findings.append(f"User transactions up {trend:+.1f}%")
                score += 12
            elif trend is not None and trend < -12:
                findings.append(f"User transactions down {trend:.1f}%")
                score -= 12
        elif total_tps is not None:
            # Be explicit that the headline number overstates real usage.
            findings.append(
                f"{total_tps:,.0f} total TPS - note this includes validator vote transactions "
                "and overstates real user activity; the non-vote figure is unavailable from "
                "this RPC endpoint"
            )

        vote_share = m.get("onchain.vote_share_pct")
        if vote_share is not None:
            findings.append(f"{vote_share:.0f}% of transactions are validator votes")

        healthy = m.get("onchain.rpc_healthy")
        if healthy is not None and healthy < 1.0:
            findings.append("RPC endpoint reports unhealthy status - network conditions degraded")
            score -= 15

        epoch_progress = m.get("onchain.epoch_progress")
        if epoch_progress is not None:
            findings.append(f"Epoch {m.get('onchain.epoch', 0):.0f} at {epoch_progress:.0f}% complete")

        if m.get("onchain.circulating_supply") is not None:
            findings.append(f"Circulating supply {m['onchain.circulating_supply']:,.0f} SOL")

        return findings, max(-100.0, min(100.0, score))

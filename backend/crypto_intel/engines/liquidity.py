"""StablecoinLiquidityAnalyzer + DeFi/TVL analysis.

Stablecoin supply is the closest thing crypto has to a money-supply measure:
expanding supply means dry powder entering the ecosystem, contracting supply
means capital leaving. This is a slow, medium-to-long-horizon signal, which is
why the scoring config gives it little weight at the 1h-24h horizon.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..config_loader import threshold
from ..core.enums import Asset, Direction, Freshness
from ..core.freshness import worst_freshness
from ..core.models import Observation


class LiquidityAnalysis(BaseModel):
    available: bool = True
    unavailable_reason: str | None = None
    total_supply: float | None = None
    change_1d_pct: float | None = None
    change_7d_pct: float | None = None
    by_issuer: dict[str, float] = Field(default_factory=dict)
    by_chain: dict[str, float] = Field(default_factory=dict)
    regime: str = "UNKNOWN"          # EXPANSION | CONTRACTION | STABLE
    direction: Direction = Direction.INCONCLUSIVE
    strength: float = 0.0
    freshness: Freshness = Freshness.UNAVAILABLE
    evidence_ids: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)


class DefiAnalysis(BaseModel):
    asset: Asset
    available: bool = True
    unavailable_reason: str | None = None
    tvl: float | None = None
    tvl_change_7d_pct: float | None = None
    tvl_change_30d_pct: float | None = None
    dex_volume_24h: float | None = None
    dex_change_7d_pct: float | None = None
    fees_24h: float | None = None
    tvl_price_divergence: str | None = None
    direction: Direction = Direction.INCONCLUSIVE
    strength: float = 0.0
    freshness: Freshness = Freshness.UNAVAILABLE
    evidence_ids: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)


class StablecoinLiquidityAnalyzer:
    name = "liquidity_analyzer"

    def __init__(self) -> None:
        self.t = (threshold("liquidity", "stablecoin_supply", default={}) or {})

    def analyze(
        self, observations: list[Observation], unavailable_reason: str | None = None
    ) -> LiquidityAnalysis:
        if unavailable_reason or not observations:
            return LiquidityAnalysis(
                available=False,
                unavailable_reason=unavailable_reason or "UNAVAILABLE - no stablecoin data",
            )

        latest: dict[str, Observation] = {}
        for o in observations:
            prev = latest.get(o.metric)
            if prev is None or o.timestamp >= prev.timestamp:
                latest[o.metric] = o

        def val(metric: str) -> float | None:
            o = latest.get(metric)
            return o.numeric_value if o else None

        total = val("stablecoin.supply.total")
        d1 = val("stablecoin.supply.change_1d_pct")
        d7 = val("stablecoin.supply.change_7d_pct")

        by_issuer = {
            m.rsplit(".", 1)[-1]: o.numeric_value
            for m, o in latest.items()
            if m.startswith("stablecoin.supply.") and o.numeric_value is not None
            and not m.endswith(("total", "change_1d_pct", "change_7d_pct"))
        }
        by_chain = {
            m.rsplit(".", 1)[-1]: o.numeric_value
            for m, o in latest.items()
            if m.startswith("stablecoin.chain.") and o.numeric_value is not None
        }

        findings: list[str] = []
        regime = "STABLE"
        score = 0.0

        if d7 is not None:
            strong_exp = float(self.t.get("strong_expansion_7d_pct", 2.0))
            exp = float(self.t.get("expansion_7d_pct", 0.8))
            strong_con = float(self.t.get("strong_contraction_7d_pct", -2.0))
            con = float(self.t.get("contraction_7d_pct", -0.8))
            if d7 >= strong_exp:
                regime, score = "STRONG_EXPANSION", 45.0
                findings.append(
                    f"Stablecoin supply expanded {d7:+.2f}% over 7 days - significant new "
                    "liquidity is entering the crypto ecosystem"
                )
            elif d7 >= exp:
                regime, score = "EXPANSION", 22.0
                findings.append(f"Stablecoin supply expanding ({d7:+.2f}% / 7d) - liquidity returning")
            elif d7 <= strong_con:
                regime, score = "STRONG_CONTRACTION", -45.0
                findings.append(
                    f"Stablecoin supply contracted {d7:.2f}% over 7 days - capital is leaving "
                    "the crypto ecosystem"
                )
            elif d7 <= con:
                regime, score = "CONTRACTION", -22.0
                findings.append(f"Stablecoin supply contracting ({d7:.2f}% / 7d) - liquidity draining")
            else:
                findings.append(f"Stablecoin supply broadly flat ({d7:+.2f}% / 7d)")

        if total is not None:
            findings.append(f"Total tracked stablecoin supply ${total / 1e9:,.1f}B")
        if by_chain:
            top = sorted(by_chain.items(), key=lambda kv: -kv[1])[:3]
            findings.append(
                "Chain distribution: "
                + ", ".join(f"{c} ${v / 1e9:.1f}B" for c, v in top)
            )

        direction = (
            Direction.BULLISH if score > 12
            else Direction.BEARISH if score < -12
            else Direction.NEUTRAL
        )
        return LiquidityAnalysis(
            available=True, total_supply=total, change_1d_pct=d1, change_7d_pct=d7,
            by_issuer=by_issuer, by_chain=by_chain, regime=regime,
            direction=direction, strength=score,
            freshness=worst_freshness([o.freshness for o in latest.values()]),
            evidence_ids=[o.id for o in latest.values()], findings=findings,
        )


class DefiAnalyzer:
    name = "defi_analyzer"

    def __init__(self) -> None:
        self.t = (threshold("defi", "tvl", default={}) or {})

    def analyze(
        self,
        asset: Asset,
        observations: list[Observation],
        price_change_7d_pct: float | None = None,
        unavailable_reason: str | None = None,
    ) -> DefiAnalysis:
        if unavailable_reason or not observations:
            return DefiAnalysis(
                asset=asset, available=False,
                unavailable_reason=unavailable_reason
                or f"UNAVAILABLE - no DeFi data for {asset.value}",
            )

        tvl_series = sorted(
            [o for o in observations if o.metric == "defi.tvl" and o.numeric_value is not None],
            key=lambda o: o.timestamp,
        )
        latest_map: dict[str, Observation] = {}
        for o in observations:
            prev = latest_map.get(o.metric)
            if prev is None or o.timestamp >= prev.timestamp:
                latest_map[o.metric] = o

        def val(metric: str) -> float | None:
            o = latest_map.get(metric)
            return o.numeric_value if o else None

        tvl = tvl_series[-1].numeric_value if tvl_series else None
        change_7d = change_30d = None
        if len(tvl_series) >= 8:
            past = tvl_series[-8].numeric_value
            if past:
                change_7d = (tvl - past) / past * 100.0
        if len(tvl_series) >= 31:
            past = tvl_series[-31].numeric_value
            if past:
                change_30d = (tvl - past) / past * 100.0

        findings: list[str] = []
        score = 0.0

        if tvl is not None:
            findings.append(f"{asset.value} chain TVL ${tvl / 1e9:,.2f}B")
        if change_7d is not None:
            strong_g = float(self.t.get("strong_growth_7d_pct", 8.0))
            g = float(self.t.get("growth_7d_pct", 2.5))
            strong_d = float(self.t.get("strong_decline_7d_pct", -8.0))
            d = float(self.t.get("decline_7d_pct", -2.5))
            if change_7d >= strong_g:
                score += 30
                findings.append(f"TVL grew strongly ({change_7d:+.1f}% / 7d)")
            elif change_7d >= g:
                score += 15
                findings.append(f"TVL growing ({change_7d:+.1f}% / 7d)")
            elif change_7d <= strong_d:
                score -= 30
                findings.append(f"TVL fell sharply ({change_7d:.1f}% / 7d)")
            elif change_7d <= d:
                score -= 15
                findings.append(f"TVL declining ({change_7d:.1f}% / 7d)")

        dex = val("defi.dex_24h")
        dex_7d = val("defi.dex_change_7d_pct")
        if dex is not None:
            findings.append(f"DEX volume 24h ${dex / 1e9:,.2f}B")
        if dex_7d is not None:
            if dex_7d > 15:
                score += 10
                findings.append(f"DEX volume up {dex_7d:+.1f}% / 7d - trading activity rising")
            elif dex_7d < -15:
                score -= 10
                findings.append(f"DEX volume down {dex_7d:.1f}% / 7d")

        fees = val("defi.fees_24h")
        if fees is not None:
            findings.append(f"Protocol fees 24h ${fees / 1e6:,.1f}M")

        # TVL vs price: capital committed to the chain versus its token price.
        divergence = None
        if change_7d is not None and price_change_7d_pct is not None:
            if change_7d > 3 and price_change_7d_pct < -3:
                divergence = "TVL_UP_PRICE_DOWN"
                findings.append(
                    f"TVL rose {change_7d:+.1f}% while price fell {price_change_7d_pct:.1f}% - "
                    "capital keeps flowing to the chain despite weak price"
                )
                score += 12
            elif change_7d < -3 and price_change_7d_pct > 3:
                divergence = "TVL_DOWN_PRICE_UP"
                findings.append(
                    f"TVL fell {change_7d:.1f}% while price rose {price_change_7d_pct:+.1f}% - "
                    "the price move is not backed by on-chain capital"
                )
                score -= 12

        direction = (
            Direction.BULLISH if score > 12
            else Direction.BEARISH if score < -12
            else Direction.NEUTRAL
        )
        return DefiAnalysis(
            asset=asset, available=True, tvl=tvl,
            tvl_change_7d_pct=change_7d, tvl_change_30d_pct=change_30d,
            dex_volume_24h=dex, dex_change_7d_pct=dex_7d, fees_24h=fees,
            tvl_price_divergence=divergence,
            direction=direction, strength=max(-100.0, min(100.0, score)),
            freshness=worst_freshness([o.freshness for o in latest_map.values()]),
            evidence_ids=[o.id for o in latest_map.values()], findings=findings,
        )

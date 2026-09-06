"""DerivativesAnalyzer.

The brief is explicit: do not just print the numbers, contextualise them. The
combination of price direction and open-interest direction is what carries
meaning:

  price up   + OI up    -> new longs, genuine but leveraged demand
  price up   + OI down  -> short covering, a rally with weak foundations
  price down + OI up    -> new shorts building
  price down + OI down  -> long liquidation / deleveraging

Funding is read the same way: extreme positive funding means longs are paying
heavily to stay in, which is a crowding signal, not a bullish one.
"""

from __future__ import annotations

import numpy as np
from pydantic import BaseModel, Field

from ..config_loader import threshold
from ..core.enums import Asset, Direction, Freshness
from ..core.freshness import worst_freshness
from ..core.models import Observation


class DerivativesAnalysis(BaseModel):
    asset: Asset
    available: bool = True
    unavailable_reason: str | None = None

    funding_rate: float | None = None
    funding_annualized_pct: float | None = None
    funding_state: str = "UNAVAILABLE"
    funding_avg_7d: float | None = None
    funding_trend: str | None = None

    open_interest: float | None = None
    oi_change_24h_pct: float | None = None
    oi_state: str = "UNAVAILABLE"

    long_short_ratio: float | None = None
    ls_state: str = "UNAVAILABLE"

    basis_pct: float | None = None

    liquidations_24h: float | None = None
    liquidation_imbalance: str | None = None
    liquidations_available: bool = False
    liquidations_note: str = "UNAVAILABLE - provider not configured (no free liquidation source)"

    price_oi_regime: str | None = None
    regime_interpretation: str | None = None

    direction: Direction = Direction.INCONCLUSIVE
    strength: float = 0.0
    freshness: Freshness = Freshness.UNAVAILABLE
    evidence_ids: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class DerivativesAnalyzer:
    name = "derivatives_analyzer"

    def __init__(self) -> None:
        self.t = threshold("derivatives", default={}) or {}
        self.tf = self.t.get("funding", {})
        self.toi = self.t.get("open_interest", {})
        self.tls = self.t.get("long_short_ratio", {})

    def analyze(
        self,
        asset: Asset,
        observations: list[Observation],
        price_change_24h_pct: float | None = None,
        unavailable_reason: str | None = None,
    ) -> DerivativesAnalysis:
        if unavailable_reason or not observations:
            return DerivativesAnalysis(
                asset=asset, available=False,
                unavailable_reason=unavailable_reason
                or f"UNAVAILABLE - no derivatives data for {asset.value}",
            )

        by_metric: dict[str, list[Observation]] = {}
        for o in observations:
            by_metric.setdefault(o.metric, []).append(o)
        for lst in by_metric.values():
            lst.sort(key=lambda o: o.timestamp)

        def latest(metric: str) -> float | None:
            lst = by_metric.get(metric)
            return lst[-1].numeric_value if lst else None

        findings: list[str] = []
        warnings: list[str] = []

        # --- funding ---------------------------------------------------------
        funding = latest("funding.rate")
        funding_state = "UNAVAILABLE"
        funding_annual = None
        funding_avg7 = None
        funding_trend = None

        if funding is not None:
            # 3 funding payments per day, 365 days.
            funding_annual = funding * 3 * 365 * 100.0
            funding_state = self._funding_state(funding)
            if funding_state == "EXTREME_POSITIVE":
                findings.append(
                    f"Funding extremely positive ({funding * 100:.4f}% / 8h, "
                    f"{funding_annual:.1f}% annualised): longs are paying heavily to hold "
                    "positions - the market is crowded long"
                )
                warnings.append("Crowded long positioning raises long-squeeze risk")
            elif funding_state == "EXTREME_NEGATIVE":
                findings.append(
                    f"Funding extremely negative ({funding * 100:.4f}% / 8h): shorts are paying "
                    "to stay short - the market is crowded short"
                )
                warnings.append("Crowded short positioning raises short-squeeze risk")
            elif funding_state in ("ELEVATED_POSITIVE", "ELEVATED_NEGATIVE"):
                findings.append(
                    f"Funding {'elevated' if funding > 0 else 'negative'} "
                    f"({funding * 100:.4f}% / 8h) - leverage is building"
                )

            hist = [o.numeric_value for o in by_metric.get("funding.rate_history", [])
                    if o.numeric_value is not None]
            if len(hist) >= 21:
                funding_avg7 = float(np.mean(hist[-21:]))   # 21 payments = 7 days
                prior = float(np.mean(hist[-42:-21])) if len(hist) >= 42 else None
                if prior is not None:
                    if funding_avg7 > prior * 1.3 and funding_avg7 > 0:
                        funding_trend = "RISING"
                        findings.append("Funding trending higher - leverage is being added")
                    elif funding_avg7 < prior * 0.7 and prior > 0:
                        funding_trend = "COOLING"
                        findings.append("Funding cooling - leverage is unwinding")

        # --- open interest ---------------------------------------------------
        oi = latest("oi.contracts")
        oi_change = None
        oi_state = "UNAVAILABLE"
        oi_hist = [o.numeric_value for o in by_metric.get("oi.value_history", [])
                   if o.numeric_value is not None]
        if len(oi_hist) >= 24:
            past = oi_hist[-24]
            if past:
                oi_change = (oi_hist[-1] - past) / past * 100.0
                spike = float(self.toi.get("spike_pct_24h", 12))
                drop = float(self.toi.get("drop_pct_24h", -10))
                if oi_change >= spike:
                    oi_state = "SPIKE"
                    findings.append(f"Open interest jumped {oi_change:+.1f}% in 24h")
                elif oi_change <= drop:
                    oi_state = "DROP"
                    findings.append(f"Open interest fell {oi_change:+.1f}% in 24h - deleveraging")
                else:
                    oi_state = "STABLE"

        # --- price/OI regime, the contextual part ----------------------------
        regime, interpretation = self._price_oi_regime(price_change_24h_pct, oi_change)
        if interpretation:
            findings.append(interpretation)

        # --- long/short ------------------------------------------------------
        ls = latest("long_short.ratio")
        ls_state = "UNAVAILABLE"
        if ls is not None:
            crowded_long = float(self.tls.get("crowded_long", 2.0))
            crowded_short = float(self.tls.get("crowded_short", 0.55))
            if ls >= crowded_long:
                ls_state = "CROWDED_LONG"
                findings.append(f"Long/short account ratio {ls:.2f} - retail heavily positioned long")
            elif ls <= crowded_short:
                ls_state = "CROWDED_SHORT"
                findings.append(f"Long/short account ratio {ls:.2f} - retail heavily positioned short")
            else:
                ls_state = "BALANCED"

        basis = latest("derivatives.basis_pct")

        # --- liquidations: honest about absence ------------------------------
        liq_total = latest("liquidations.total")
        liq_long = latest("liquidations.long")
        liq_short = latest("liquidations.short")
        liq_available = liq_total is not None
        liq_imbalance = None
        if liq_available and liq_long is not None and liq_short is not None:
            if liq_long > liq_short * 2:
                liq_imbalance = "LONGS_LIQUIDATED"
            elif liq_short > liq_long * 2:
                liq_imbalance = "SHORTS_LIQUIDATED"
            else:
                liq_imbalance = "BALANCED"

        strength = self._score(funding, funding_state, oi_change, regime, ls, ls_state)
        direction = (
            Direction.BULLISH if strength > 12
            else Direction.BEARISH if strength < -12
            else Direction.NEUTRAL
        )

        return DerivativesAnalysis(
            asset=asset, available=True,
            funding_rate=funding, funding_annualized_pct=funding_annual,
            funding_state=funding_state, funding_avg_7d=funding_avg7, funding_trend=funding_trend,
            open_interest=oi, oi_change_24h_pct=oi_change, oi_state=oi_state,
            long_short_ratio=ls, ls_state=ls_state, basis_pct=basis,
            liquidations_24h=liq_total, liquidation_imbalance=liq_imbalance,
            liquidations_available=liq_available,
            price_oi_regime=regime, regime_interpretation=interpretation,
            direction=direction, strength=round(strength, 1),
            # Freshness reflects the CURRENT readings. Including the funding
            # history (which spans weeks by design) would mark a live snapshot
            # STALE and unfairly suppress this domain's confidence.
            freshness=worst_freshness([
                lst[-1].freshness for name, lst in by_metric.items()
                if not name.endswith("_history")
            ]),
            evidence_ids=[o.id for o in observations[:60]],
            findings=findings, warnings=warnings,
        )

    def _funding_state(self, funding: float) -> str:
        extreme = float(self.tf.get("extreme", 0.0025))
        extreme_neg = float(self.tf.get("extreme_negative", -0.0015))
        elevated = float(self.tf.get("elevated", 0.0010))
        neutral = float(self.tf.get("neutral_abs", 0.0005))
        if funding >= extreme:
            return "EXTREME_POSITIVE"
        if funding <= extreme_neg:
            return "EXTREME_NEGATIVE"
        if funding >= elevated:
            return "ELEVATED_POSITIVE"
        if funding <= -elevated:
            return "ELEVATED_NEGATIVE"
        if abs(funding) <= neutral:
            return "NEUTRAL"
        return "MILD_POSITIVE" if funding > 0 else "MILD_NEGATIVE"

    def _price_oi_regime(
        self, price_change: float | None, oi_change: float | None
    ) -> tuple[str | None, str | None]:
        """The four classic combinations, each with its meaning spelled out."""
        if price_change is None or oi_change is None:
            return None, None
        p_up, oi_up = price_change > 0.5, oi_change > 1.0
        p_down, oi_down = price_change < -0.5, oi_change < -1.0

        if p_up and oi_up:
            return "PRICE_UP_OI_UP", (
                f"Price {price_change:+.1f}% with open interest {oi_change:+.1f}%: new long "
                "positions are funding the move - real demand, but leveraged and therefore fragile"
            )
        if p_up and oi_down:
            return "PRICE_UP_OI_DOWN", (
                f"Price {price_change:+.1f}% while open interest fell {oi_change:+.1f}%: this "
                "looks like short covering rather than fresh buying - rallies built this way "
                "tend to stall once shorts are done"
            )
        if p_down and oi_up:
            return "PRICE_DOWN_OI_UP", (
                f"Price {price_change:+.1f}% with open interest {oi_change:+.1f}%: new short "
                "positions are being opened - bearish conviction is building"
            )
        if p_down and oi_down:
            return "PRICE_DOWN_OI_DOWN", (
                f"Price {price_change:+.1f}% with open interest {oi_change:+.1f}%: longs are "
                "closing out - deleveraging rather than aggressive selling, which often "
                "precedes a base"
            )
        return "NEUTRAL", None

    def _score(self, funding, funding_state, oi_change, regime, ls, ls_state) -> float:
        score = 0.0
        # Extreme funding is a contrarian signal, not a trend confirmation.
        score += {
            "EXTREME_POSITIVE": -30.0, "ELEVATED_POSITIVE": -12.0,
            "MILD_POSITIVE": 3.0, "NEUTRAL": 0.0, "MILD_NEGATIVE": -3.0,
            "ELEVATED_NEGATIVE": 12.0, "EXTREME_NEGATIVE": 28.0,
            "UNAVAILABLE": 0.0,
        }.get(funding_state, 0.0)

        score += {
            "PRICE_UP_OI_UP": 15.0,
            "PRICE_UP_OI_DOWN": -8.0,
            "PRICE_DOWN_OI_UP": -18.0,
            "PRICE_DOWN_OI_DOWN": 6.0,
        }.get(regime or "", 0.0)

        score += {"CROWDED_LONG": -15.0, "CROWDED_SHORT": 15.0}.get(ls_state, 0.0)
        return max(-100.0, min(100.0, score))

"""ETFFlowAnalyzer - one of the most decision-relevant modules for BTC/ETH.

Goes well beyond showing today's number. It looks for the patterns that
actually precede price moves:

  * institutions accumulating before price reacts (flows up, price flat/down);
  * price rising while institutional demand fades (price up, flows slowing).

Everything is computed from daily per-fund flows in millions of USD. When no
data has been imported and no API key is configured, the analyzer reports
UNAVAILABLE - it never fabricates a flow.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

import numpy as np
from pydantic import BaseModel, Field

from ..config_loader import threshold
from ..core.enums import Asset, Direction, Freshness
from ..core.freshness import compute_freshness
from ..core.models import Observation


class ETFDailyFlow(BaseModel):
    date: datetime
    total_musd: float
    by_ticker: dict[str, float] = Field(default_factory=dict)


class ETFFlowAnalysis(BaseModel):
    asset: Asset
    available: bool = True
    unavailable_reason: str | None = None

    latest_date: datetime | None = None
    latest_total: float | None = None
    latest_by_ticker: dict[str, float] = Field(default_factory=dict)

    ma_3d: float | None = None
    ma_5d: float | None = None
    ma_7d: float | None = None
    cumulative_30d: float | None = None
    cumulative_all: float | None = None

    acceleration_pct: float | None = None
    reversal: str | None = None            # POSITIVE_REVERSAL | NEGATIVE_REVERSAL
    streak_days: int = 0
    streak_direction: str | None = None    # inflow | outflow

    flow_price_divergence: str | None = None
    divergence_detail: str | None = None

    direction: Direction = Direction.INCONCLUSIVE
    strength: float = 0.0                  # -100..100
    freshness: Freshness = Freshness.UNAVAILABLE
    evidence_ids: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    history: list[ETFDailyFlow] = Field(default_factory=list)


class ETFFlowAnalyzer:
    name = "etf_flow_analyzer"

    def __init__(self) -> None:
        self.t = threshold("etf", default={}) or {}

    def _aggregate(self, observations: list[Observation]) -> list[ETFDailyFlow]:
        """Sum per-fund flows into a daily net flow."""
        by_day: dict[datetime, dict[str, float]] = defaultdict(dict)
        for obs in observations:
            if obs.metric != "etf.flow":
                continue
            value = obs.numeric_value
            if value is None:
                continue
            day = obs.timestamp.replace(hour=0, minute=0, second=0, microsecond=0)
            ticker = str(obs.meta.get("ticker", "UNKNOWN"))
            by_day[day][ticker] = value

        return [
            ETFDailyFlow(date=day, total_musd=sum(t.values()), by_ticker=dict(t))
            for day, t in sorted(by_day.items())
        ]

    def analyze(
        self,
        asset: Asset,
        observations: list[Observation],
        price_history: list[tuple[datetime, float]] | None = None,
        unavailable_reason: str | None = None,
    ) -> ETFFlowAnalysis:
        if unavailable_reason or not observations:
            return ETFFlowAnalysis(
                asset=asset, available=False,
                unavailable_reason=unavailable_reason
                or f"UNAVAILABLE - no ETF flow data for {asset.value}",
                freshness=Freshness.UNAVAILABLE,
            )

        history = self._aggregate(observations)
        if not history:
            return ETFFlowAnalysis(
                asset=asset, available=False,
                unavailable_reason="UNAVAILABLE - observations contained no usable ETF flows",
                freshness=Freshness.UNAVAILABLE,
            )

        totals = [d.total_musd for d in history]
        latest = history[-1]
        findings: list[str] = []

        def ma(n: int) -> float | None:
            # None, not 0.0, when there is not enough history.
            return float(np.mean(totals[-n:])) if len(totals) >= n else None

        ma3, ma5, ma7 = ma(3), ma(5), ma(7)
        cum_30 = float(np.sum(totals[-30:])) if totals else None
        cum_all = float(np.sum(totals))

        # --- acceleration: recent 3d mean vs the 3 days before that ----------
        acceleration = None
        if len(totals) >= 6:
            recent = float(np.mean(totals[-3:]))
            prior = float(np.mean(totals[-6:-3]))
            if abs(prior) > 1e-9:
                acceleration = (recent - prior) / abs(prior) * 100.0

        # --- reversal: sign flip between the two 3-day windows ---------------
        reversal = None
        if len(totals) >= 6:
            recent = float(np.mean(totals[-3:]))
            prior = float(np.mean(totals[-6:-3]))
            if prior < 0 <= recent:
                reversal = "POSITIVE_REVERSAL"
                findings.append(
                    f"Flows turned positive: 3d average moved from {prior:+.1f}M to {recent:+.1f}M"
                )
            elif prior > 0 >= recent:
                reversal = "NEGATIVE_REVERSAL"
                findings.append(
                    f"Flows turned negative: 3d average moved from {prior:+.1f}M to {recent:+.1f}M"
                )

        # --- consecutive streak ---------------------------------------------
        streak, streak_dir = 0, None
        if totals:
            sign = 1 if totals[-1] > 0 else (-1 if totals[-1] < 0 else 0)
            if sign != 0:
                streak_dir = "inflow" if sign > 0 else "outflow"
                for value in reversed(totals):
                    if (value > 0 and sign > 0) or (value < 0 and sign < 0):
                        streak += 1
                    else:
                        break
                if streak >= int(self.t.get("streak_significant", 3)):
                    findings.append(f"{streak} consecutive days of {streak_dir}s")

        # --- flow vs price divergence ---------------------------------------
        divergence, divergence_detail = None, None
        if price_history:
            divergence, divergence_detail = self._flow_price_divergence(history, price_history)
            if divergence_detail:
                findings.append(divergence_detail)

        strength = self._score(latest.total_musd, ma5, acceleration, streak, streak_dir, divergence)
        direction = (
            Direction.BULLISH if strength > 12
            else Direction.BEARISH if strength < -12
            else Direction.NEUTRAL
        )

        strong_in = float(self.t.get("strong_inflow_daily", 300))
        strong_out = float(self.t.get("strong_outflow_daily", -300))
        if latest.total_musd >= strong_in:
            findings.append(f"Strong daily inflow: {latest.total_musd:+.1f}M USD")
        elif latest.total_musd <= strong_out:
            findings.append(f"Strong daily outflow: {latest.total_musd:+.1f}M USD")

        if acceleration is not None and abs(acceleration) >= float(
            self.t.get("acceleration_significant_pct", 25)
        ):
            findings.append(
                f"Flow {'acceleration' if acceleration > 0 else 'deceleration'}: "
                f"{acceleration:+.0f}% vs the previous 3 days"
            )

        return ETFFlowAnalysis(
            asset=asset,
            available=True,
            latest_date=latest.date,
            latest_total=latest.total_musd,
            latest_by_ticker=latest.by_ticker,
            ma_3d=ma3, ma_5d=ma5, ma_7d=ma7,
            cumulative_30d=cum_30, cumulative_all=cum_all,
            acceleration_pct=acceleration,
            reversal=reversal,
            streak_days=streak, streak_direction=streak_dir,
            flow_price_divergence=divergence, divergence_detail=divergence_detail,
            direction=direction, strength=round(strength, 1),
            # Based on the most recent flow day - ETF flows are published daily,
            # so the age of 2023 rows says nothing about current freshness.
            freshness=compute_freshness(latest.date, "etf"),
            evidence_ids=[o.id for o in observations[-40:]],
            findings=findings,
            history=history[-60:],
        )

    def _flow_price_divergence(
        self, history: list[ETFDailyFlow], price_history: list[tuple[datetime, float]]
    ) -> tuple[str | None, str | None]:
        """The core question: are flows and price telling the same story?"""
        days = int(self.t.get("divergence_lookback_days", 7))
        if len(history) < days or len(price_history) < 2:
            return None, None

        recent_flows = [d.total_musd for d in history[-days:]]
        flow_sum = float(np.sum(recent_flows))

        cutoff = history[-days].date
        prices = [p for _, p in sorted(price_history) if _ >= cutoff] if price_history else []
        if len(prices) < 2:
            prices = [p for _, p in sorted(price_history)][-days:]
        if len(prices) < 2 or prices[0] == 0:
            return None, None
        price_change_pct = (prices[-1] - prices[0]) / prices[0] * 100.0

        # Thresholds keep small wobbles from being called a divergence.
        if flow_sum > 200 and price_change_pct < -1.5:
            return "ACCUMULATION_BEFORE_PRICE", (
                f"ETFs accumulated {flow_sum:+.0f}M over {days} days while price fell "
                f"{price_change_pct:.1f}% - institutional demand is not following price down"
            )
        if flow_sum < -200 and price_change_pct > 1.5:
            return "DISTRIBUTION_INTO_STRENGTH", (
                f"ETFs saw {flow_sum:+.0f}M of outflows over {days} days while price rose "
                f"{price_change_pct:+.1f}% - the rally is not backed by institutional buying"
            )
        if flow_sum > 200 and price_change_pct > 1.5:
            return "CONFIRMED_UPTREND", (
                f"Flows ({flow_sum:+.0f}M) and price ({price_change_pct:+.1f}%) both rising "
                f"over {days} days - institutional demand confirms the move"
            )
        if flow_sum < -200 and price_change_pct < -1.5:
            return "CONFIRMED_DOWNTREND", (
                f"Flows ({flow_sum:+.0f}M) and price ({price_change_pct:.1f}%) both falling "
                f"over {days} days - institutional selling confirms the weakness"
            )
        if abs(flow_sum) < 100 and abs(price_change_pct) > 4.0:
            return "PRICE_WITHOUT_FLOWS", (
                f"Price moved {price_change_pct:+.1f}% over {days} days on near-flat ETF flows "
                f"({flow_sum:+.0f}M) - the move is not ETF-driven"
            )
        return None, None

    def _score(
        self,
        latest: float,
        ma5: float | None,
        acceleration: float | None,
        streak: int,
        streak_dir: str | None,
        divergence: str | None,
    ) -> float:
        """Blend the components into -100..+100."""
        score = 0.0

        strong_in = float(self.t.get("strong_inflow_daily", 300))
        inflow = float(self.t.get("inflow_daily", 80))
        if latest >= strong_in:
            score += 35
        elif latest >= inflow:
            score += 18
        elif latest <= -strong_in:
            score -= 35
        elif latest <= -inflow:
            score -= 18

        if ma5 is not None:
            if ma5 >= inflow:
                score += 20
            elif ma5 <= -inflow:
                score -= 20
            else:
                score += max(-10.0, min(10.0, ma5 / inflow * 10.0))

        if acceleration is not None:
            score += max(-15.0, min(15.0, acceleration / 100.0 * 15.0))

        if streak >= 3 and streak_dir:
            bump = min(15.0, streak * 3.0)
            score += bump if streak_dir == "inflow" else -bump

        # A divergence is a leading signal and deserves real weight.
        score += {
            "ACCUMULATION_BEFORE_PRICE": 20.0,
            "DISTRIBUTION_INTO_STRENGTH": -20.0,
            "CONFIRMED_UPTREND": 10.0,
            "CONFIRMED_DOWNTREND": -10.0,
            "PRICE_WITHOUT_FLOWS": -5.0,
        }.get(divergence or "", 0.0)

        return max(-100.0, min(100.0, score))

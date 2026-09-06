"""Empirical layer: what actually happened in comparable past configurations.

Three things live here, all built on the same idea - describe history, never
forecast:

  * EmpiricalTimingLayer - forward-return distribution for configurations
    resembling the current one.
  * Risk/reward analytics - expected favourable and adverse excursion, derived
    from those same analogues. No invented price target.
  * Probability separation - ANALYTICAL_CONFIDENCE (how well the signals agree)
    is kept strictly apart from EMPIRICAL_PROBABILITY (how often comparable
    past days went up).

The matching strategy degrades deliberately: an exact-ish match first, then a
relaxed one, then a broad regime match. Sample size is reported at every step,
because a 92% win rate on 12 analogues is not a finding.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from ..core.enums import Asset
from ..engines.technical import indicators as ind
from ..logging_setup import get_logger

log = get_logger("engines.empirical")

HORIZONS = [1, 3, 7, 14, 30]
MIN_SAMPLE_STRICT = 30
MIN_SAMPLE_RELAXED = 60


@dataclass(slots=True)
class MatchLevel:
    """One rung of the matching ladder."""

    name: str
    description: str
    dimensions: list[str]
    n: int = 0
    used: bool = False


@dataclass(slots=True)
class EmpiricalResult:
    asset: Asset
    available: bool = False
    reason: str = ""
    match_level: str = ""
    match_description: str = ""
    dimensions_used: list[str] = field(default_factory=list)
    sample_size: int = 0
    horizons: dict[str, Any] = field(default_factory=dict)
    risk_reward: dict[str, Any] = field(default_factory=dict)
    ladder: list[dict[str, Any]] = field(default_factory=list)
    current_configuration: dict[str, Any] = field(default_factory=dict)
    caveat: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset": self.asset.value,
            "available": self.available,
            "reason": self.reason,
            "match_level": self.match_level,
            "match_description": self.match_description,
            "dimensions_used": self.dimensions_used,
            "sample_size": self.sample_size,
            "horizons": self.horizons,
            "risk_reward": self.risk_reward,
            "ladder": self.ladder,
            "current_configuration": self.current_configuration,
            "caveat": self.caveat,
        }


class EmpiricalTimingLayer:
    """Finds comparable historical configurations and describes what followed."""

    name = "empirical_timing_layer"

    def build_configuration_frame(self, asset: Asset) -> pd.DataFrame | None:
        """Discretised configuration per historical day.

        Every dimension is causal: computed from bars up to that day only.
        """
        from ..research.derivatives_study import daily_funding, trailing_rank
        from ..research.etf_study import build_flow_series, build_price_frame
        from ..research.regime_conditioned import reconstruct_regime

        df = build_price_frame(asset)
        if df.empty or len(df) < 300:
            return None

        close, high, low, volume = df["close"], df["high"], df["low"], df["volume"]
        frame = pd.DataFrame(index=df.index)
        frame["regime"] = reconstruct_regime(df)

        rsi = ind.rsi(close, 14)
        frame["rsi_bucket"] = pd.cut(
            rsi, [0, 30, 45, 55, 70, 100],
            labels=["oversold", "weak", "neutral", "strong", "overbought"],
        )

        atr_rank = trailing_rank(ind.atr_percent(high, low, close, 14))
        frame["vol_bucket"] = pd.cut(
            atr_rank, [-0.01, 25, 75, 100.01], labels=["low", "normal", "high"]
        )

        ema20, ema50 = ind.ema(close, 20), ind.ema(close, 50)
        stretch = (close - ema20) / close * 100.0
        frame["stretch_bucket"] = pd.cut(
            stretch, [-100, -5, -1, 1, 5, 100],
            labels=["far_below", "below", "at", "above", "far_above"],
        )
        frame["trend_bucket"] = pd.cut(
            (ema20 - ema50) / close * 100.0, [-100, -1, 1, 100],
            labels=["down", "flat", "up"],
        )

        rel_volume = ind.relative_volume(volume, 20)
        frame["volume_bucket"] = pd.cut(
            rel_volume, [0, 0.7, 1.5, 100], labels=["low", "normal", "high"]
        )

        funding = daily_funding(asset, df.index)
        if not funding.dropna().empty:
            frame["funding_bucket"] = pd.cut(
                trailing_rank(funding), [-0.01, 20, 80, 95, 100.01],
                labels=["low", "normal", "high", "extreme"],
            )

        flows = build_flow_series(asset)
        if not flows.empty:
            ma5 = flows.rolling(5, min_periods=3).mean().reindex(df.index)
            frame["etf_bucket"] = pd.cut(
                ma5, [-1e9, -50, 50, 1e9], labels=["outflow", "neutral", "inflow"]
            )

        frame["close"] = close
        frame["high"] = high
        frame["low"] = low
        return frame

    def _ladder(self, frame: pd.DataFrame) -> list[MatchLevel]:
        """Matching rungs, from specific to broad."""
        available = set(frame.columns)
        strict = [
            d for d in ("regime", "rsi_bucket", "vol_bucket", "stretch_bucket",
                        "funding_bucket", "etf_bucket")
            if d in available
        ]
        relaxed = [d for d in ("regime", "rsi_bucket", "stretch_bucket") if d in available]
        broad = [d for d in ("regime",) if d in available]
        return [
            MatchLevel("exact_ish", "Same regime, momentum, volatility, stretch, funding and ETF state", strict),
            MatchLevel("relaxed", "Same regime, momentum zone and distance from the 20-EMA", relaxed),
            MatchLevel("broad_regime", "Same market regime only", broad),
        ]

    def analyse(self, asset: Asset, current: dict[str, Any] | None = None) -> EmpiricalResult:
        """Describe what followed configurations like the current one."""
        frame = self.build_configuration_frame(asset)
        if frame is None:
            return EmpiricalResult(
                asset=asset,
                reason="UNAVAILABLE - not enough daily history; run `make backfill`",
            )

        # The current configuration is the most recent complete row.
        latest = frame.dropna(subset=["regime"]).iloc[-1] if len(frame) else None
        if latest is None:
            return EmpiricalResult(asset=asset, reason="UNAVAILABLE - no usable current row")

        if current:
            # Allow the caller (live pipeline) to override with live values.
            for key, value in current.items():
                if key in frame.columns:
                    latest[key] = value

        from ..research.stats import describe_returns, forward_returns

        fwd = forward_returns(frame["close"], HORIZONS)
        ladder = self._ladder(frame)
        chosen: MatchLevel | None = None
        matched_index: pd.Index | None = None

        # Exclude the most recent bars: they have no realised forward return yet.
        usable = frame.index[: -max(HORIZONS)] if len(frame) > max(HORIZONS) else frame.index

        for level in ladder:
            if not level.dimensions:
                continue
            mask = pd.Series(True, index=frame.index)
            for dimension in level.dimensions:
                mask &= frame[dimension] == latest[dimension]
            candidates = frame.index[mask & frame.index.isin(usable)]
            level.n = len(candidates)
            minimum = MIN_SAMPLE_STRICT if level.name == "exact_ish" else MIN_SAMPLE_RELAXED
            if chosen is None and level.n >= minimum:
                chosen = level
                level.used = True
                matched_index = candidates

        ladder_dicts = [
            {"level": lv.name, "description": lv.description,
             "dimensions": lv.dimensions, "n": lv.n, "used": lv.used}
            for lv in ladder
        ]

        configuration = {
            d: (str(latest[d]) if pd.notna(latest[d]) else None)
            for d in frame.columns if d not in ("close", "high", "low")
        }

        if chosen is None or matched_index is None or len(matched_index) == 0:
            return EmpiricalResult(
                asset=asset,
                reason=(
                    "INCONCLUSIVE - no matching level reached a usable sample size. "
                    "The current configuration has no close historical precedent."
                ),
                ladder=ladder_dicts,
                current_configuration=configuration,
            )

        horizons: dict[str, Any] = {}
        for h in HORIZONS:
            subset = fwd.loc[fwd.index.isin(matched_index), f"fwd_{h}"]
            stats = describe_returns(subset)
            baseline = describe_returns(fwd[f"fwd_{h}"])
            horizons[f"{h}d"] = {
                **stats.to_dict(),
                "baseline_mean": baseline.mean,
                "baseline_win_rate": baseline.win_rate,
                "edge_vs_baseline": (
                    round(stats.mean - baseline.mean, 4)
                    if stats.mean is not None and baseline.mean is not None else None
                ),
            }

        risk_reward = self._risk_reward(frame, matched_index, horizon=7)

        return EmpiricalResult(
            asset=asset,
            available=True,
            match_level=chosen.name,
            match_description=chosen.description,
            dimensions_used=chosen.dimensions,
            sample_size=len(matched_index),
            horizons=horizons,
            risk_reward=risk_reward,
            ladder=ladder_dicts,
            current_configuration=configuration,
            caveat=(
                "These are historical analogues, not a forecast. A distribution of past "
                "outcomes describes what happened in similar configurations; it does not "
                "constrain what happens next. Sample size is shown because small samples "
                "produce impressive-looking percentages that mean nothing."
            ),
        )

    def _risk_reward(
        self, frame: pd.DataFrame, matched: pd.Index, horizon: int = 7
    ) -> dict[str, Any]:
        """Expected favourable and adverse excursion from the analogues.

        The endpoint return hides the path: a +2% close that first fell 8% is a
        very different experience from one that never went red.
        """
        from ..research.stats import excursions

        mfe, mae = excursions(frame["high"], frame["low"], frame["close"], horizon)
        mfe_subset = mfe[mfe.index.isin(matched)].dropna()
        mae_subset = mae[mae.index.isin(matched)].dropna()

        if len(mfe_subset) < 20 or len(mae_subset) < 20:
            return {
                "available": False,
                "reason": f"INSUFFICIENT_DATA - {len(mfe_subset)} analogues with excursions",
            }

        mfe_median = float(mfe_subset.median())
        mae_median = float(mae_subset.median())
        ratio = abs(mfe_median / mae_median) if abs(mae_median) > 1e-9 else None

        return {
            "available": True,
            "horizon": f"{horizon}d",
            "n": len(mfe_subset),
            "mfe_median": round(mfe_median, 3),
            "mfe_mean": round(float(mfe_subset.mean()), 3),
            "mae_median": round(mae_median, 3),
            "mae_mean": round(float(mae_subset.mean()), 3),
            "reward_risk_ratio": round(ratio, 2) if ratio else None,
            "interpretation": (
                f"In {len(mfe_subset)} comparable past configurations, price typically "
                f"reached {mfe_median:+.1f}% in favour and {mae_median:+.1f}% against "
                f"within {horizon} days"
                + (f", a ratio of {ratio:.2f}." if ratio else ".")
                + " This is a historical distribution, not a target or a guarantee."
            ),
        }


@dataclass(slots=True)
class ProbabilityAssessment:
    """The separation the brief insists on.

    ANALYTICAL_CONFIDENCE says how well this system's own signals agree and how
    good the data behind them is. EMPIRICAL_PROBABILITY says how often
    comparable historical days ended higher. They answer different questions
    and must never be merged into a single "chance of going up".
    """

    analytical_confidence: float = 0.0
    analytical_basis: list[str] = field(default_factory=list)
    empirical_probability: float | None = None
    empirical_sample: int = 0
    empirical_horizon: str = "7d"
    empirical_available: bool = False
    empirical_reason: str = ""
    statement: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "analytical_confidence": round(self.analytical_confidence, 1),
            "analytical_basis": self.analytical_basis,
            "empirical_probability": self.empirical_probability,
            "empirical_sample": self.empirical_sample,
            "empirical_horizon": self.empirical_horizon,
            "empirical_available": self.empirical_available,
            "empirical_reason": self.empirical_reason,
            "statement": self.statement,
            "methodology": (
                "Analytical confidence measures signal agreement and data quality in "
                "this system. Empirical probability is the observed frequency of "
                "positive returns in comparable historical configurations. They are "
                "different quantities: neither is 'the probability that price rises'."
            ),
        }


def assess_probability(
    conviction: Any, empirical: EmpiricalResult, horizon: str = "7d"
) -> ProbabilityAssessment:
    """Combine the two - by reporting them side by side, never by merging them."""
    basis: list[str] = []
    analytical = 0.0

    if conviction is not None:
        analytical = float(getattr(conviction, "overall_confidence", 0.0) or 0.0)
        medium = getattr(conviction, "medium", None)
        if medium is not None:
            basis.append(
                f"Medium-horizon conviction {medium.score:+.1f} at "
                f"{medium.confidence:.0f}% confidence"
            )
        missing = getattr(conviction, "domains_missing", []) or []
        if missing:
            basis.append(f"{len(missing)} domain(s) unavailable: {', '.join(missing[:4])}")

    assessment = ProbabilityAssessment(
        analytical_confidence=analytical, analytical_basis=basis,
        empirical_horizon=horizon,
    )

    if not empirical.available:
        assessment.empirical_reason = empirical.reason
        assessment.statement = (
            f"Analytical confidence {analytical:.0f}/100. No comparable historical "
            "configuration has a usable sample, so no empirical frequency is offered."
        )
        return assessment

    cell = empirical.horizons.get(horizon, {})
    win_rate = cell.get("win_rate")
    n = cell.get("n", 0)

    if win_rate is None or n < MIN_SAMPLE_STRICT:
        assessment.empirical_reason = (
            f"INSUFFICIENT_DATA - {n} analogues at {horizon}"
        )
        assessment.statement = (
            f"Analytical confidence {analytical:.0f}/100. Only {n} historical analogues "
            "at this horizon - too few to quote a frequency."
        )
        return assessment

    assessment.empirical_available = True
    assessment.empirical_probability = win_rate
    assessment.empirical_sample = n
    baseline = cell.get("baseline_win_rate")

    assessment.statement = (
        f"Analytical confidence: {analytical:.0f}/100. "
        f"Historical positive-return frequency at {horizon}: {win_rate:.0f}% "
        f"(sample {n}"
        + (f", unconditional baseline {baseline:.0f}%" if baseline is not None else "")
        + f", match level '{empirical.match_level}'). "
        "This is the observed frequency in comparable past configurations, not a "
        "probability that price will rise."
    )
    return assessment

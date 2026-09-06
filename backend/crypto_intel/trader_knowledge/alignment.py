"""Align a human analysis to the market as it was at that instant.

This is the most dangerous part of the whole trader-knowledge pipeline. A
video published on 10 January must be evaluated against the market on 10
January - not against a chart that includes 11 January. Getting this wrong
does not produce an error; it produces a beautifully consistent dataset in
which humans appear prescient, and every downstream study inherits the lie.

So the rule is enforced mechanically: `market_context` slices every series at
`market_timestamp` before computing anything, and the outcome engine is a
separate function that cannot be called with the same frame.
"""

from __future__ import annotations

import hashlib
import math
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

from ..core.enums import Asset, Timeframe
from ..engines.technical import indicators as ind
from ..history import store
from ..logging_setup import get_logger
from ..structure.location import StructuralLocationEngine
from ..structure.market_structure import MarketStructureEngine
from .models import HumanOutcome, MarketContextAtT, TraderAnalysisExample

log = get_logger("trader_knowledge.alignment")

# Outcome horizons in hours. Which ones are usable depends on the bar size of
# the timeframe the analysis was about.
OUTCOME_HORIZONS_HOURS = {
    "15m": 0.25, "1h": 1, "4h": 4, "12h": 12, "24h": 24,
    "3d": 72, "7d": 168, "14d": 336, "30d": 720,
}


def resolve_market_timestamp(
    example: TraderAnalysisExample, timeframe: Timeframe
) -> datetime | None:
    """The last bar that had CLOSED when the analyst was speaking.

    Deliberately conservative. If someone speaks at 14:30 on a 4H chart, the
    14:00 bar is still forming - they could see it, but its close did not
    exist. Using the last CLOSED bar guarantees no forming-bar information
    leaks in, at the cost of being slightly behind what the analyst saw.
    """
    reference = example.analysis_time or example.published_at
    if reference is None:
        return None
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=UTC)

    df = store.load_candles(Asset(example.asset), timeframe)
    if df.empty:
        return None

    minutes = timeframe.minutes
    closed = df.index[df.index + timedelta(minutes=minutes) <= reference]
    if len(closed) == 0:
        return None
    return closed[-1]


def market_context(
    example: TraderAnalysisExample, market_timestamp: datetime | None = None
) -> MarketContextAtT | None:
    """Everything measurable at the analysis instant. Nothing after it."""
    if example.asset is None or example.timeframe is None:
        return None
    try:
        asset = Asset(example.asset)
        timeframe = Timeframe(example.timeframe)
    except ValueError:
        return None

    timestamp = market_timestamp or resolve_market_timestamp(example, timeframe)
    if timestamp is None:
        return None

    df = store.load_candles(asset, timeframe)
    # The single most important line in this module: everything after the
    # analysis instant is discarded before any computation happens.
    df = df[df.index <= timestamp]
    if df.empty or len(df) < 60:
        return None

    context = MarketContextAtT(
        market_timestamp=timestamp, asset=asset.value, timeframe=timeframe.value,
        bars_available=len(df),
    )
    last = df.iloc[-1]
    context.price_at_analysis = float(last["close"])
    context.ohlcv_at_t = {
        "open": float(last["open"]), "high": float(last["high"]),
        "low": float(last["low"]), "close": float(last["close"]),
        "volume": float(last["volume"]),
    }

    atr_series = ind.atr(df["high"], df["low"], df["close"], 14)
    if len(atr_series.dropna()):
        context.atr_at_t = round(float(atr_series.iloc[-1]), 6)

    try:
        location = StructuralLocationEngine().assess(asset, timeframe, as_of=timestamp)
        context.location_at_t = location.state.value
        detected = location.detected_range
        if detected and detected.valid and detected.top_zone and detected.bottom_zone:
            context.range_top_at_t = round(detected.top_zone.midpoint, 6)
            context.range_bottom_at_t = round(detected.bottom_zone.midpoint, 6)
            context.supports_at_t = [{
                "low": detected.bottom_zone.low, "high": detected.bottom_zone.high,
                "quality": detected.bottom_zone.quality.score,
            }]
            context.resistances_at_t = [{
                "low": detected.top_zone.low, "high": detected.top_zone.high,
                "quality": detected.top_zone.quality.score,
            }]
    except Exception as exc:
        log.debug("location_unavailable", error=str(exc))

    try:
        structure = MarketStructureEngine().assess(asset, timeframe, as_of=timestamp)
        context.structure_at_t = structure.state.value
    except Exception:
        pass

    try:
        from ..engines.leverage import LeverageCrowdingEngine
        from ..engines.volatility import VolatilityRegimeEngine

        leverage = LeverageCrowdingEngine()
        funding = leverage.funding_context(asset, as_of=timestamp)
        context.funding_at_t = funding.value
        context.funding_percentile_at_t = funding.percentile
        volatility = VolatilityRegimeEngine().assess(asset, as_of=timestamp)
        context.volatility_at_t = volatility.regime
    except Exception as exc:
        log.debug("derivatives_context_unavailable", error=str(exc))

    try:
        from ..research.regime_conditioned import reconstruct_regime

        daily = store.load_candles(asset, Timeframe.D1)
        daily = daily[daily.index <= timestamp]
        if len(daily) >= 200:
            regimes = reconstruct_regime(daily).dropna()
            if len(regimes):
                context.regime_at_t = str(regimes.iloc[-1])
    except Exception:
        pass

    return context


def measure_outcome(
    example: TraderAnalysisExample,
    context: MarketContextAtT,
    benchmark_asset: Asset = Asset.BTC,
) -> HumanOutcome:
    """What happened after - computed from bars strictly AFTER the analysis.

    Targets and invalidations are only evaluated when the analyst actually
    stated them. Reconstructing a target after the fact would let us grade an
    analysis against a goal it never set, which flatters or damns it at random.
    """
    asset = Asset(context.asset)
    timeframe = Timeframe(context.timeframe)
    outcome = HumanOutcome(
        example_id=example.id, market_timestamp=context.market_timestamp
    )

    df = store.load_candles(asset, timeframe)
    after = df[df.index > context.market_timestamp]
    if after.empty:
        outcome.evaluation_note = "no bars after the analysis timestamp yet"
        return outcome

    entry = context.price_at_analysis
    if not entry:
        outcome.evaluation_note = "no reference price at the analysis timestamp"
        return outcome

    minutes = timeframe.minutes
    benchmark = store.load_candles(benchmark_asset, timeframe)
    benchmark_after = benchmark[benchmark.index > context.market_timestamp]
    benchmark_entry = (
        float(benchmark[benchmark.index <= context.market_timestamp]["close"].iloc[-1])
        if len(benchmark[benchmark.index <= context.market_timestamp]) else None
    )

    for label, hours in OUTCOME_HORIZONS_HOURS.items():
        bars = int(hours * 60 / minutes)
        if bars < 1 or bars > len(after):
            outcome.returns[label] = None
            continue
        target_price = float(after["close"].iloc[bars - 1])
        outcome.returns[label] = round((target_price - entry) / entry * 100, 3)

        if benchmark_entry and bars <= len(benchmark_after):
            benchmark_price = float(benchmark_after["close"].iloc[bars - 1])
            benchmark_return = (benchmark_price - benchmark_entry) / benchmark_entry * 100
            outcome.benchmark_adjusted[label] = round(
                outcome.returns[label] - benchmark_return, 3
            )

    # Excursions over the longest horizon that actually exists.
    horizon_bars = min(len(after), int(720 * 60 / minutes))
    window = after.iloc[:horizon_bars]
    if len(window):
        highs = window["high"].to_numpy()
        lows = window["low"].to_numpy()
        outcome.mfe_pct = round(float((highs.max() - entry) / entry * 100), 3)
        outcome.mae_pct = round(float((lows.min() - entry) / entry * 100), 3)
        outcome.time_to_mfe_bars = int(np.argmax(highs)) + 1
        outcome.time_to_mae_bars = int(np.argmin(lows)) + 1
        running_max = np.maximum.accumulate(window["close"].to_numpy())
        drawdowns = (window["close"].to_numpy() - running_max) / running_max * 100
        outcome.max_drawdown_pct = round(float(drawdowns.min()), 3)
        returns = window["close"].pct_change().dropna()
        if len(returns) > 2:
            outcome.realised_volatility = round(float(returns.std() * 100), 3)

        # Only grade against levels the analyst actually gave.
        if example.target_if_mentioned is not None:
            target = example.target_if_mentioned
            hit = (
                (window["high"] >= target).any() if target > entry
                else (window["low"] <= target).any()
            )
            outcome.target_hit = bool(hit)
        if example.invalidation is not None:
            level = example.invalidation
            hit = (
                (window["low"] <= level).any() if level < entry
                else (window["high"] >= level).any()
            )
            outcome.invalidation_hit = bool(hit)

        if outcome.target_hit is not None and outcome.invalidation_hit is not None:
            outcome.target_before_invalidation = _first_hit_order(
                window, example.target_if_mentioned, example.invalidation, entry
            )
            outcome.invalidation_before_target = (
                None if outcome.target_before_invalidation is None
                else not outcome.target_before_invalidation
            )

    notes = []
    if example.target_if_mentioned is None:
        notes.append("no target was stated, so none was evaluated")
    if example.invalidation is None:
        notes.append("no invalidation was stated, so none was evaluated")
    outcome.evaluation_note = "; ".join(notes) or "target and invalidation both stated"
    return outcome


def _first_hit_order(
    window: pd.DataFrame, target: float | None, invalidation: float | None, entry: float
) -> bool | None:
    """True when the target was reached before the invalidation."""
    if target is None or invalidation is None:
        return None
    target_hits = (
        window.index[window["high"] >= target] if target > entry
        else window.index[window["low"] <= target]
    )
    invalidation_hits = (
        window.index[window["low"] <= invalidation] if invalidation < entry
        else window.index[window["high"] >= invalidation]
    )
    if len(target_hits) == 0:
        return False
    if len(invalidation_hits) == 0:
        return True
    return bool(target_hits[0] < invalidation_hits[0])


def market_episode_id(
    asset: str, timeframe: str, market_timestamp: datetime,
    range_top: float | None = None, range_bottom: float | None = None,
) -> str:
    """Group analyses that describe the same market situation.

    Twenty videos about the same BTC range are one observation, not twenty.

    When a range is known it IS the identity, and no time component enters the
    key. An earlier version bucketed time as well, and two analyses three days
    apart landed either side of a bucket boundary and counted as two
    independent episodes. Any bucket width has that edge; widening it only
    makes the split rarer, never impossible.

    Dropping time means the same price band revisited years later merges into
    one episode. That is the safe direction to err: merging understates the
    effective sample, and every study here is built to treat a smaller
    effective sample as less evidence, never more.

    Without a range there is nothing stable to key on, so a time bucket is the
    only option and its edge cases are accepted.
    """
    if range_top and range_bottom and range_top > range_bottom:
        midpoint = (range_top + range_bottom) / 2
        # Logarithmic bucketing at ~2% granularity, so slightly different
        # readings of the same levels collapse together.
        range_key = str(round(math.log(midpoint) / math.log(1.02)))
        payload = f"{asset}|{timeframe}|range|{range_key}"
    else:
        bucket_days = {"15m": 1, "1h": 3, "4h": 7, "1d": 14, "1w": 60}.get(timeframe, 14)
        epoch_bucket = int(market_timestamp.timestamp() // (bucket_days * 86400))
        payload = f"{asset}|{timeframe}|time|{epoch_bucket}"

    digest = hashlib.sha1(payload.encode()).hexdigest()[:12]
    return f"ep_{digest}"


def align_example(
    example: TraderAnalysisExample,
) -> dict[str, Any]:
    """Full alignment: claim, context at T, outcome after - kept separate."""
    if not example.alignable:
        return {
            "example_id": example.id, "status": "NOT_ALIGNABLE",
            "reason": (
                "asset, timeframe or timestamp missing; refusing to guess, since a "
                "wrongly aligned example silently contaminates every study built on it"
            ),
        }

    context = market_context(example)
    if context is None:
        return {
            "example_id": example.id, "status": "NO_MARKET_DATA",
            "reason": "no stored candles cover this analysis timestamp",
        }

    episode = market_episode_id(
        context.asset, context.timeframe, context.market_timestamp,
        context.range_top_at_t, context.range_bottom_at_t,
    )
    outcome = measure_outcome(example, context)

    return {
        "example_id": example.id,
        "status": "ALIGNED",
        "market_episode_id": episode,
        "what_trader_said": example.what_trader_said(),
        "what_market_data_showed_at_t": context.model_dump(mode="json"),
        "what_happened_after": outcome.model_dump(mode="json"),
        "separation_note": (
            "These three blocks are computed independently. The claim never informs "
            "the measurement, and the outcome never informs either."
        ),
    }

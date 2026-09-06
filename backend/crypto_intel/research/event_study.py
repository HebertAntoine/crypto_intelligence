"""Event studies: what has historically followed a given market condition?

An event is a boolean condition on a day, defined by a QUANTITATIVE threshold
(a percentile of the trailing distribution, not a hand-picked constant that
would silently encode hindsight). For each occurrence we measure the forward
path: return at several horizons, plus maximum favourable and adverse
excursion, which describe how the move actually unfolded.

Thresholds are computed on a trailing window, so the definition of "extreme"
at a given date only uses data available at that date. Using a full-history
percentile would leak the future into the event definition itself - a subtle
form of look-ahead that is easy to miss and fatal to the result.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pandas as pd

from ..core.enums import Asset
from ..engines.technical import indicators as ind
from ..history import store
from ..logging_setup import get_logger
from .etf_study import build_flow_series, build_price_frame, build_signals
from .stats import describe_returns, excursions, forward_returns

log = get_logger("research.events")

HORIZONS = [1, 3, 5, 7, 14, 30]
TRAILING_WINDOW = 252   # ~1 trading year for percentile thresholds


def _trailing_percentile(series: pd.Series, q: float, window: int = TRAILING_WINDOW) -> pd.Series:
    """Rolling percentile using only past observations.

    `.rolling()` looks backwards, so the threshold at day t is derived from
    days <= t. This is what keeps the event definition free of look-ahead.
    """
    return series.rolling(window, min_periods=60).quantile(q / 100.0)


class EventDefinition:
    """One named market condition, plus how to detect it."""

    def __init__(
        self,
        key: str,
        label: str,
        detector: Callable[[dict[str, pd.Series | pd.DataFrame]], pd.Series],
        description: str,
        requires: tuple[str, ...] = (),
    ) -> None:
        self.key = key
        self.label = label
        self.detector = detector
        self.description = description
        self.requires = requires


def _etf_high_inflow(data: dict) -> pd.Series:
    flow = data["etf_signals"]["flow"]
    return flow > _trailing_percentile(flow, 90)


def _etf_high_outflow(data: dict) -> pd.Series:
    flow = data["etf_signals"]["flow"]
    return flow < _trailing_percentile(flow, 10)


def _etf_streak_positive(data: dict) -> pd.Series:
    return (data["etf_signals"]["pos_streak"] >= 5).fillna(False)


def _etf_streak_negative(data: dict) -> pd.Series:
    return (data["etf_signals"]["neg_streak"] >= 3).fillna(False)


def _etf_flip_positive(data: dict) -> pd.Series:
    # fillna(False) before astype(bool): on days with no ETF data the signal is
    # NaN, and NaN casts to True, which previously counted every single day as
    # a flip event.
    return data["etf_signals"]["flip_to_positive"].fillna(False).astype(bool)


def _rsi_oversold(data: dict) -> pd.Series:
    return data["rsi"] <= 30


def _rsi_overbought(data: dict) -> pd.Series:
    return data["rsi"] >= 70


def _rsi_extreme_oversold(data: dict) -> pd.Series:
    return data["rsi"] <= 20


def _funding_extreme_positive(data: dict) -> pd.Series:
    funding = data.get("funding")
    if funding is None or funding.empty:
        return pd.Series(dtype=bool)
    return funding > _trailing_percentile(funding, 95)


def _funding_extreme_negative(data: dict) -> pd.Series:
    funding = data.get("funding")
    if funding is None or funding.empty:
        return pd.Series(dtype=bool)
    return funding < _trailing_percentile(funding, 5)


def _volatility_expansion(data: dict) -> pd.Series:
    atr = data["atr_pct"]
    return atr > _trailing_percentile(atr, 90)


def _volatility_compression(data: dict) -> pd.Series:
    atr = data["atr_pct"]
    return atr < _trailing_percentile(atr, 10)


def _volume_spike(data: dict) -> pd.Series:
    rel = data["rel_volume"]
    return rel > 2.5


def _price_above_ema200_cross(data: dict) -> pd.Series:
    close, ema200 = data["close"], data["ema200"]
    above = close > ema200
    return above & ~above.shift(1).fillna(False).astype(bool)


def _drawdown_20pct(data: dict) -> pd.Series:
    close = data["close"]
    peak = close.rolling(90, min_periods=30).max()
    return (close / peak - 1.0) <= -0.20


DEFINITIONS: list[EventDefinition] = [
    EventDefinition("etf_inflow_p90", "ETF inflow above the 90th percentile",
                    _etf_high_inflow,
                    "Daily net ETF flow in the top decile of the trailing year",
                    requires=("etf",)),
    EventDefinition("etf_outflow_p10", "ETF outflow below the 10th percentile",
                    _etf_high_outflow,
                    "Daily net ETF flow in the bottom decile of the trailing year",
                    requires=("etf",)),
    EventDefinition("etf_streak_pos5", "5 consecutive days of ETF inflows",
                    _etf_streak_positive, "Sustained institutional buying",
                    requires=("etf",)),
    EventDefinition("etf_streak_neg3", "3 consecutive days of ETF outflows",
                    _etf_streak_negative, "Sustained institutional selling",
                    requires=("etf",)),
    EventDefinition("etf_flip_positive", "ETF 3-day average turns positive",
                    _etf_flip_positive, "Flow reversal to the upside",
                    requires=("etf",)),
    EventDefinition("rsi_oversold", "Daily RSI <= 30", _rsi_oversold,
                    "Classic oversold reading on the daily timeframe"),
    EventDefinition("rsi_extreme_oversold", "Daily RSI <= 20", _rsi_extreme_oversold,
                    "Deeply oversold"),
    EventDefinition("rsi_overbought", "Daily RSI >= 70", _rsi_overbought,
                    "Classic overbought reading"),
    EventDefinition("funding_p95", "Funding above the 95th percentile",
                    _funding_extreme_positive,
                    "Crowded long positioning", requires=("funding",)),
    EventDefinition("funding_p5", "Funding below the 5th percentile",
                    _funding_extreme_negative,
                    "Crowded short positioning", requires=("funding",)),
    EventDefinition("vol_expansion_p90", "ATR above the 90th percentile",
                    _volatility_expansion, "Volatility expansion"),
    EventDefinition("vol_compression_p10", "ATR below the 10th percentile",
                    _volatility_compression, "Volatility compression / squeeze"),
    EventDefinition("volume_spike", "Volume above 2.5x its 20-day average",
                    _volume_spike, "Participation spike"),
    EventDefinition("cross_above_ema200", "Price crosses above the EMA200",
                    _price_above_ema200_cross, "Long-term trend flip"),
    EventDefinition("drawdown_20pct", "20% below the 90-day high",
                    _drawdown_20pct, "Deep drawdown"),
]


def _observable_window(
    definition: EventDefinition, ctx: dict[str, Any], fallback: pd.Index
) -> pd.Index:
    """Dates on which this event's inputs actually exist.

    Without this, an ETF event measured over 2024-2026 would be compared with a
    baseline spanning 2017-2026 - a comparison between market eras, not a
    measurement of the event.
    """
    index = fallback
    if "etf" in definition.requires and "etf_signals" in ctx:
        available = ctx["etf_signals"]["flow"].dropna().index
        if len(available):
            index = index.intersection(available)
    if "funding" in definition.requires and ctx.get("funding") is not None:
        available = ctx["funding"].dropna().index
        if len(available):
            index = index.intersection(available)
    return index if len(index) else fallback


def build_event_context(asset: Asset) -> dict[str, Any]:
    """Assemble every series an event detector may need, on a daily grid."""
    prices = build_price_frame(asset)
    if prices.empty:
        return {}

    close, high, low, volume = prices["close"], prices["high"], prices["low"], prices["volume"]
    context: dict[str, Any] = {
        "prices": prices, "close": close, "high": high, "low": low, "volume": volume,
        "rsi": ind.rsi(close, 14),
        "atr_pct": ind.atr_percent(high, low, close, 14),
        "rel_volume": ind.relative_volume(volume, 20),
        "ema200": ind.ema(close, 200),
    }

    flows = build_flow_series(asset)
    if not flows.empty:
        signals = build_signals(flows).reindex(prices.index)
        context["etf_signals"] = signals
        context["has_etf"] = True
    else:
        context["has_etf"] = False

    funding = store.load_derivatives(asset, "funding.rate")
    if not funding.empty:
        # Funding publishes every 8h; the daily mean is the right granularity
        # to line it up with daily bars.
        daily_funding = funding.resample("1D").mean()
        daily_funding.index = daily_funding.index.tz_convert("UTC") \
            if daily_funding.index.tz else daily_funding.index.tz_localize("UTC")
        context["funding"] = daily_funding.reindex(prices.index)
        context["has_funding"] = True
    else:
        context["has_funding"] = False

    return context


def run_event_study(
    asset: Asset, definition: EventDefinition, context: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Measure what followed every occurrence of one event."""
    ctx = context if context is not None else build_event_context(asset)
    if not ctx:
        return {
            "asset": asset.value, "event": definition.key, "available": False,
            "reason": "UNAVAILABLE - no price history; run `make backfill`",
        }

    if "etf" in definition.requires and not ctx.get("has_etf"):
        return {
            "asset": asset.value, "event": definition.key, "available": False,
            "reason": f"UNAVAILABLE - no ETF flow data for {asset.value}",
        }
    if "funding" in definition.requires and not ctx.get("has_funding"):
        return {
            "asset": asset.value, "event": definition.key, "available": False,
            "reason": f"UNAVAILABLE - no funding history for {asset.value}",
        }

    try:
        mask = definition.detector(ctx)
    except Exception as exc:
        return {
            "asset": asset.value, "event": definition.key, "available": False,
            "reason": f"detector failed: {exc}",
        }

    if mask is None or mask.empty:
        return {
            "asset": asset.value, "event": definition.key, "available": False,
            "reason": "INCONCLUSIVE - detector produced no observations",
        }

    mask = mask.fillna(False).astype(bool)
    close = ctx["close"]
    fwd = forward_returns(close, HORIZONS)

    occurrences = int(mask.sum())
    if occurrences < 5:
        return {
            "asset": asset.value, "event": definition.key, "label": definition.label,
            "available": False,
            "reason": f"INCONCLUSIVE - only {occurrences} occurrences in the available history",
            "occurrences": occurrences,
        }

    event_dates = mask[mask].index

    # The baseline MUST be restricted to the window in which the event could
    # occur at all. ETF events only exist from 2024 onward; comparing them
    # against a 2017-2026 baseline would measure the difference between two
    # market eras rather than the effect of the event.
    #
    # The window is derived from the REQUIRED underlying data, not from the
    # mask: detectors fill missing days with False, so the mask itself no
    # longer carries any trace of where its inputs actually existed.
    observable = _observable_window(definition, ctx, mask.index)
    window_start, window_end = observable.min(), observable.max()
    baseline_index = fwd.index[(fwd.index >= window_start) & (fwd.index <= window_end)]
    # Occurrences outside the observable window cannot be real events.
    event_dates = event_dates[(event_dates >= window_start) & (event_dates <= window_end)]

    per_horizon: dict[str, Any] = {}
    for h in HORIZONS:
        subset = fwd.loc[fwd.index.isin(event_dates), f"fwd_{h}"]
        stats = describe_returns(subset)
        baseline = describe_returns(fwd.loc[baseline_index, f"fwd_{h}"])
        mfe, mae = excursions(ctx["high"], ctx["low"], close, h)
        mfe_event = mfe[mfe.index.isin(event_dates)].dropna()
        mae_event = mae[mae.index.isin(event_dates)].dropna()

        edge = (
            round(stats.mean - baseline.mean, 4)
            if stats.mean is not None and baseline.mean is not None else None
        )
        per_horizon[f"{h}d"] = {
            **stats.to_dict(),
            "baseline_mean": baseline.mean,
            "baseline_win_rate": baseline.win_rate,
            "edge_vs_baseline": edge,
            "max_favorable_excursion_mean": (
                round(float(mfe_event.mean()), 3) if len(mfe_event) else None
            ),
            "max_adverse_excursion_mean": (
                round(float(mae_event.mean()), 3) if len(mae_event) else None
            ),
        }

    return {
        "asset": asset.value,
        "event": definition.key,
        "label": definition.label,
        "description": definition.description,
        "available": True,
        "occurrences": occurrences,
        "period": {
            "start": window_start.isoformat(),
            "end": window_end.isoformat(),
            "baseline_days": len(baseline_index),
        },
        "horizons": per_horizon,
        "note": (
            "Thresholds use a trailing 252-day percentile, so the definition of "
            "'extreme' at each date only uses data available at that date. "
            "`edge_vs_baseline` compares the event's mean return with the "
            "unconditional mean over THE SAME WINDOW in which the event is "
            "observable - that difference, not the raw return, is what would "
            "constitute an edge."
        ),
    }


def run_all_events(asset: Asset) -> dict[str, Any]:
    """Every defined event for one asset, computed once from a shared context."""
    ctx = build_event_context(asset)
    if not ctx:
        # Keep the `events` key present so consumers can iterate unconditionally
        # instead of branching on shape.
        return {
            "asset": asset.value, "available": False,
            "reason": "UNAVAILABLE - no price history; run `make backfill`",
            "events": [], "computed": 0, "skipped": len(DEFINITIONS),
        }

    results = []
    for definition in DEFINITIONS:
        results.append(run_event_study(asset, definition, ctx))

    usable = [r for r in results if r.get("available")]
    return {
        "asset": asset.value,
        "available": bool(usable),
        "events": results,
        "computed": len(usable),
        "skipped": len(results) - len(usable),
    }


def persist_events(asset: Asset, payload: dict[str, Any]) -> int:
    from ..db.base import ResearchResultRow
    from ..db.session import session_scope

    if not payload.get("available"):
        return 0
    written = 0
    now = datetime.now(UTC)
    with session_scope() as s:
        for event in payload.get("events", []):
            if not event.get("available"):
                continue
            period = event.get("period") or {}
            start = pd.Timestamp(period["start"]).to_pydatetime() if period.get("start") else None
            end = pd.Timestamp(period["end"]).to_pydatetime() if period.get("end") else None
            for horizon, metrics in event["horizons"].items():
                rid = f"event:{asset.value}:{event['event']}:{horizon}"[:80]
                row = s.get(ResearchResultRow, rid)
                if row is None:
                    row = ResearchResultRow(
                        id=rid, study="event_study", asset=asset.value,
                        signal=event["event"], horizon=horizon, split="full",
                    )
                    s.add(row)
                row.sample_size = int(metrics.get("n", 0))
                row.metrics = metrics
                row.computed_at = now
                row.data_start = start
                row.data_end = end
                written += 1
    return written

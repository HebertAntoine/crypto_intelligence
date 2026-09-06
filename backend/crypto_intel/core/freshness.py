"""Freshness is computed, never declared.

The thresholds depend on the *metric class*: a 30-minute-old price is stale,
a 30-minute-old ETF flow is perfectly fresh. Treating them identically is the
classic way to make a dashboard lie.
"""

from __future__ import annotations

from datetime import datetime

from .enums import Freshness
from .models import utcnow

# Fallback used when config is unavailable. config/thresholds.yaml overrides it.
DEFAULT_THRESHOLDS: dict[str, dict[str, int]] = {
    "price": {"live": 120, "min_15": 900, "hour_1": 3600, "today": 86400},
    "derivatives": {"live": 300, "min_15": 900, "hour_1": 3600, "today": 86400},
    "onchain": {"live": 900, "min_15": 3600, "hour_1": 14400, "today": 172800},
    "etf": {"live": 3600, "min_15": 21600, "hour_1": 86400, "today": 259200},
    "defi": {"live": 1800, "min_15": 7200, "hour_1": 21600, "today": 172800},
    "macro": {"live": 3600, "min_15": 21600, "hour_1": 86400, "today": 604800},
    "news": {"live": 900, "min_15": 3600, "hour_1": 21600, "today": 172800},
    "regulation": {"live": 3600, "min_15": 21600, "hour_1": 86400, "today": 604800},
    "default": {"live": 300, "min_15": 900, "hour_1": 3600, "today": 86400},
}

# Metric prefix -> class. Longest prefix wins.
_METRIC_CLASS_MAP: dict[str, str] = {
    "price": "price",
    "ohlcv": "price",
    "ticker": "price",
    "market": "price",
    "funding": "derivatives",
    "oi": "derivatives",
    "open_interest": "derivatives",
    "liquidations": "derivatives",
    "long_short": "derivatives",
    "derivatives": "derivatives",
    "etf": "etf",
    "onchain": "onchain",
    "hashrate": "onchain",
    "difficulty": "onchain",
    "gas": "onchain",
    "staking": "onchain",
    "defi": "defi",
    "tvl": "defi",
    "dex": "defi",
    "fees": "defi",
    "stablecoin": "defi",
    "rwa": "defi",
    "macro": "macro",
    "rates": "macro",
    "cpi": "macro",
    "index": "macro",
    "news": "news",
    "regulation": "regulation",
    "whale": "onchain",
}


def metric_class(metric: str) -> str:
    """Map a dotted metric name to its freshness class."""
    head = metric.split(".", 1)[0].lower()
    return _METRIC_CLASS_MAP.get(head, "default")


def compute_freshness(
    timestamp: datetime | None,
    metric: str = "",
    *,
    now: datetime | None = None,
    thresholds: dict[str, dict[str, int]] | None = None,
    interval_minutes: int | None = None,
) -> Freshness:
    """Age of `timestamp` translated into a Freshness level.

    A missing timestamp is UNAVAILABLE, not STALE: we distinguish "we have an
    old number" from "we have no number at all".

    `interval_minutes` scales the thresholds for bar-based series. Without it a
    weekly candle stamped at the period open looks days old and would be called
    STALE, when in fact it is the current bar. Freshness must be judged relative
    to the sampling interval, not against an absolute clock.
    """
    if timestamp is None:
        return Freshness.UNAVAILABLE

    now = now or utcnow()
    table = thresholds or DEFAULT_THRESHOLDS
    cfg = table.get(metric_class(metric), table.get("default", DEFAULT_THRESHOLDS["default"]))

    if interval_minutes and interval_minutes > 0:
        # One bar period is "live"; two is still current; beyond that it lags.
        period = interval_minutes * 60
        cfg = {
            "live": max(cfg["live"], int(period * 1.5)),
            "min_15": max(cfg["min_15"], int(period * 2.0)),
            "hour_1": max(cfg["hour_1"], int(period * 2.5)),
            "today": max(cfg["today"], int(period * 3.5)),
        }

    age = (now - timestamp).total_seconds()

    # Future timestamps happen with daily bars stamped at period open, or with
    # exchange clock skew. A small lead is treated as live rather than absurd.
    if age < -300:
        return Freshness.UNAVAILABLE
    age = max(age, 0.0)

    if age <= cfg["live"]:
        return Freshness.LIVE
    if age <= cfg["min_15"]:
        return Freshness.MIN_15
    if age <= cfg["hour_1"]:
        return Freshness.HOUR_1
    if age <= cfg["today"]:
        return Freshness.TODAY
    return Freshness.STALE


def worst_freshness(items: list[Freshness]) -> Freshness:
    """A conclusion is only as fresh as its weakest evidence."""
    if not items:
        return Freshness.UNAVAILABLE
    return min(items, key=lambda f: f.rank)


def freshness_factor(f: Freshness, table: dict[str, float] | None = None) -> float:
    """Multiplier applied to a score's weight. STALE data still counts a little;
    UNAVAILABLE counts for exactly nothing."""
    default = {
        "LIVE": 1.0,
        "MIN_15": 0.98,
        "HOUR_1": 0.92,
        "TODAY": 0.80,
        "STALE": 0.35,
        "UNAVAILABLE": 0.0,
    }
    return (table or default).get(f.value, 0.0)

"""Intraday event studies around scheduled macro releases.

Daily bars hide what happens around a release: a CPI print at 12:30 UTC that
moves price 2% and gives it all back by the close leaves no trace in a daily
candle. Yet that is exactly the risk of holding through the print.

This measures the path around known event times, on hourly bars. It does not
need a consensus - it asks what happens around the event, not what happens
after a surprise.

Direction is not assumed. Most of what is found here is about volatility and
volume, and saying so is the point.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from ..core.enums import Asset, Timeframe
from ..history import store
from ..logging_setup import get_logger
from .stats import describe_returns

log = get_logger("research.event_time")

# Offsets around the event, in hours. Negative is before.
WINDOWS: list[tuple[str, float]] = [
    ("T-24h", -24), ("T-4h", -4), ("T-1h", -1),
    ("T+1h", 1), ("T+4h", 4), ("T+24h", 24), ("T+3d", 72),
]

# 15-minute reactions need 15-minute bars. Reported as unavailable rather than
# approximated from hourly data.
SUB_HOURLY_WINDOWS = ["T+15m"]


def generate_nfp_dates(start_year: int = 2018, end_year: int | None = None) -> list[dict[str, Any]]:
    """US employment report dates, derived from their published rule.

    The BLS releases the Employment Situation on the first Friday of the month
    at 08:30 ET. That is a documented, stable rule, so deriving the dates is
    reproducing a fact rather than inventing data - and each entry is marked
    `certainty: DERIVED_FROM_RULE` so it can never be mistaken for an imported
    official schedule.

    CPI and FOMC dates do NOT follow a rule this clean (CPI drifts around
    mid-month, FOMC meetings are set year by year), so they are not generated -
    they require an import.
    """
    from calendar import monthrange

    end_year = end_year or datetime.now(UTC).year
    events: list[dict[str, Any]] = []

    for year in range(start_year, end_year + 1):
        for month in range(1, 13):
            first_weekday, _days = monthrange(year, month)
            # Monday=0 … Friday=4. Offset to the first Friday.
            offset = (4 - first_weekday) % 7
            day = 1 + offset
            # Convert the documented local release time with the IANA zone so
            # DST is correct for the historical date.
            when = datetime(
                year, month, day, 8, 30, tzinfo=ZoneInfo("America/New_York")
            ).astimezone(UTC)
            if when > datetime.now(UTC):
                continue
            events.append({
                "name": f"US Employment Situation ({when:%b %Y})",
                "kind": "NFP",
                "time": when,
                "importance": "CRITICAL",
                "certainty": "DERIVED_FROM_RULE",
                "source": "BLS release rule: first Friday, 08:30 ET",
            })
    return events


def historical_event_times(
    kinds: list[str] | None = None, include_derived: bool = False
) -> list[dict[str, Any]]:
    """Point-in-time-safe scheduled events from the rich event store.

    An event is eligible only when its source was observed no later than the
    event itself. This prevents a schedule imported after the fact from leaking
    into a historical validation. Rule-derived NFP dates remain an explicit
    opt-in calibration aid; they are never part of the production path.
    """
    events: list[dict[str, Any]] = []

    if include_derived:
        # The kind filter must apply to derived dates too, otherwise every
        # event type returns the same NFP set - which made CPI, FOMC and PCE
        # produce identical results.
        derived = generate_nfp_dates()
        if kinds:
            derived = [e for e in derived if e["kind"] in kinds]
        events.extend(derived)
    from ..db import repo

    now = datetime.now(UTC)
    for event in repo.list_future_events(
        end=now,
        include_expired=True,
        limit=5000,
    ):
        when = event.scheduled_at
        if when is None or when > now:
            continue
        if kinds and event.event_type not in kinds:
            continue
        observed_at = event.source_published_at or event.detected_at
        if observed_at > when:
            # The event may be valid for display today, but it was not known
            # at the historical decision boundary being studied.
            continue
        events.append({
            "name": event.title,
            "kind": event.event_type,
            "time": when,
            "importance": event.importance.value,
            "certainty": "SOURCE_OBSERVED_BEFORE_EVENT",
            "source": event.source,
            "source_url": event.source_url,
            "observed_at": observed_at,
            "event_id": event.id,
        })

    events.sort(key=lambda e: e["time"])
    return events


def measure_event_window(
    candles: pd.DataFrame, event_time: datetime
) -> dict[str, Any] | None:
    """Returns, volatility and volume around one event."""
    if candles.empty:
        return None

    before = candles[candles.index <= event_time]
    if before.empty:
        return None
    anchor_price = float(before["close"].iloc[-1])
    anchor_time = before.index[-1]
    if anchor_price <= 0:
        return None

    # The anchor must be close to the event, otherwise the "reaction" is
    # measured from a stale bar.
    if (event_time - anchor_time) > timedelta(hours=6):
        return None

    result: dict[str, Any] = {"event_time": event_time.isoformat(), "returns": {}}

    for label, offset_hours in WINDOWS:
        target = anchor_time + timedelta(hours=offset_hours)
        if offset_hours < 0:
            window = candles[(candles.index >= target) & (candles.index <= anchor_time)]
            if window.empty:
                result["returns"][label] = None
                continue
            start_price = float(window["close"].iloc[0])
            result["returns"][label] = (
                (anchor_price - start_price) / start_price * 100.0 if start_price else None
            )
        else:
            after = candles[candles.index >= target]
            if after.empty:
                result["returns"][label] = None
                continue
            result["returns"][label] = (
                float(after["close"].iloc[0]) - anchor_price
            ) / anchor_price * 100.0

    # Realised volatility and volume, before vs after: the clearest effect of
    # a scheduled release.
    pre = candles[
        (candles.index >= anchor_time - timedelta(hours=24)) & (candles.index <= anchor_time)
    ]
    post = candles[
        (candles.index > anchor_time) & (candles.index <= anchor_time + timedelta(hours=24))
    ]

    def realised_vol(frame: pd.DataFrame) -> float | None:
        if len(frame) < 4:
            return None
        returns = np.log(frame["close"] / frame["close"].shift(1)).dropna()
        return float(returns.std(ddof=1) * np.sqrt(24) * 100.0) if len(returns) > 2 else None

    pre_vol, post_vol = realised_vol(pre), realised_vol(post)
    result["volatility"] = {
        "pre_24h": round(pre_vol, 4) if pre_vol else None,
        "post_24h": round(post_vol, 4) if post_vol else None,
        "ratio": (
            round(post_vol / pre_vol, 3) if pre_vol and post_vol and pre_vol > 0 else None
        ),
    }

    pre_volume = float(pre["volume"].mean()) if len(pre) else None
    post_volume = float(post["volume"].mean()) if len(post) else None
    result["volume"] = {
        "pre_24h_mean": pre_volume, "post_24h_mean": post_volume,
        "ratio": (
            round(post_volume / pre_volume, 3)
            if pre_volume and post_volume and pre_volume > 0 else None
        ),
    }

    # Absolute move: direction-free measure of impact.
    move_24h = result["returns"].get("T+24h")
    result["absolute_move_24h"] = abs(move_24h) if move_24h is not None else None
    return result


def run_event_study(
    asset: Asset, kind: str, min_sample: int = 5
) -> dict[str, Any]:
    """Aggregate the path around every occurrence of one event kind."""
    events = list(historical_event_times([kind]))
    if not events:
        return {
            "asset": asset.value, "kind": kind, "available": False,
            "reason": f"No '{kind}' event in the calendar",
        }

    candles = store.load_candles(asset, Timeframe.H1)
    if candles.empty:
        return {
            "asset": asset.value, "kind": kind, "available": False,
            "reason": "UNAVAILABLE - no hourly candles; run `make backfill`",
        }

    measurements = []
    for event in events:
        measured = measure_event_window(candles, event["time"])
        if measured:
            measured["name"] = event["name"]
            measurements.append(measured)

    if len(measurements) < min_sample:
        return {
            "asset": asset.value, "kind": kind, "available": False,
            "reason": (
                f"INSUFFICIENT_DATA - {len(measurements)} occurrences covered by the "
                f"hourly history (need {min_sample}). The calendar only holds recent "
                "events and hourly candles go back roughly 400 days."
            ),
            "occurrences": len(measurements),
            "events_in_calendar": len(events),
        }

    by_window: dict[str, Any] = {}
    for label, _ in WINDOWS:
        values = [m["returns"].get(label) for m in measurements]
        values = [v for v in values if v is not None]
        if values:
            stats = describe_returns(values)
            by_window[label] = {
                **stats.to_dict(),
                "mean_absolute": round(float(np.mean([abs(v) for v in values])), 4),
            }

    for label in SUB_HOURLY_WINDOWS:
        by_window[label] = {
            "available": False,
            "reason": "Requires 15-minute candles; hourly data cannot resolve this window",
        }

    vol_ratios = [
        m["volatility"]["ratio"] for m in measurements
        if m["volatility"].get("ratio") is not None
    ]
    volume_ratios = [
        m["volume"]["ratio"] for m in measurements
        if m["volume"].get("ratio") is not None
    ]

    return {
        "asset": asset.value,
        "kind": kind,
        "available": True,
        "occurrences": len(measurements),
        "by_window": by_window,
        "volatility": {
            "n": len(vol_ratios),
            "median_post_pre_ratio": (
                round(float(np.median(vol_ratios)), 3) if vol_ratios else None
            ),
            "share_above_1": (
                round(sum(1 for r in vol_ratios if r > 1) / len(vol_ratios) * 100.0, 1)
                if vol_ratios else None
            ),
        },
        "volume": {
            "n": len(volume_ratios),
            "median_post_pre_ratio": (
                round(float(np.median(volume_ratios)), 3) if volume_ratios else None
            ),
        },
        "interpretation": _interpret(by_window, vol_ratios, len(measurements)),
        "caveat": (
            "Small sample: the maintained calendar holds a few dozen events and hourly "
            "candles cover roughly 400 days. These are descriptions, not estimates."
        ),
    }


def _interpret(by_window: dict[str, Any], vol_ratios: list[float], n: int) -> str:
    parts: list[str] = []

    after = by_window.get("T+24h", {})
    if after.get("mean") is not None:
        direction = (
            "no consistent direction"
            if abs(after["mean"]) < 0.5 else
            f"a mean move of {after['mean']:+.2f}%"
        )
        parts.append(
            f"24h after the event: {direction} "
            f"(mean absolute move {after.get('mean_absolute', 0):.2f}%, n={after.get('n', 0)})"
        )

    if vol_ratios:
        median = float(np.median(vol_ratios))
        if median > 1.15:
            parts.append(
                f"Realised volatility rises after the release (median post/pre ratio "
                f"{median:.2f})"
            )
        elif median < 0.85:
            parts.append(
                f"Volatility falls after the release (median ratio {median:.2f}) - "
                "consistent with uncertainty resolving"
            )
        else:
            parts.append(f"Volatility broadly unchanged (median ratio {median:.2f})")

    if n < 15:
        parts.append(
            f"Only {n} occurrences - descriptive at best, no significance claimed"
        )
    return ". ".join(parts) + "."


def run_all(assets: list[Asset] | None = None) -> dict[str, Any]:
    assets = assets or Asset.tradables()
    kinds = sorted({e["kind"] for e in historical_event_times()})

    results: dict[str, Any] = {}
    for asset in assets:
        results[asset.value] = {
            kind: run_event_study(asset, kind) for kind in kinds
        }

    return {
        "assets": results,
        "kinds": kinds,
        "calendar_events": len(historical_event_times()),
        "note": (
            "NFP dates are derived from the published BLS rule (first Friday, 08:30 ET) "
            "and marked DERIVED_FROM_RULE. CPI and FOMC dates do not follow a rule "
            "clean enough to derive and come only from the maintained calendar, which "
            "is short - that caps those samples."
        ),
    }

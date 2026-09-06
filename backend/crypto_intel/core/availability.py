"""What each series can honestly be used for.

The project already answers "how fresh is this number?" (`freshness.py`) and
"how much history is stored?" (`history/store.py` coverage helpers). Neither
answers the question that actually governs an analysis:

    can I put this series in a live read, and can I run a study on it?

Those are different tests. Open interest from Binance is perfectly good live
data and useless for a backtest, because the source publishes about thirty days
of it and no amount of waiting changes that. Stablecoin supply is the same story
with two days of local history. Meanwhile the macro series go back to 2016 and
carry both.

Conflating the two is how a system ends up computing a "historical base rate"
from eleven observations. Every consumer therefore asks this module first, and
a series that fails `usable_for_backtest` is excluded from statistics with the
reason shown to the user rather than quietly averaged in.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from .freshness import metric_class


class AvailabilityReason(StrEnum):
    """Why a series is or is not usable. Always stated, never implied."""

    OK = "OK"
    NO_DATA = "NO_DATA"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    INSUFFICIENT_POINTS = "INSUFFICIENT_POINTS"
    STALE = "STALE"
    SOURCE_LIMIT = "SOURCE_LIMIT"


#: Minimum depth before a series may support a historical study, by metric
#: class. These are floors on the *question being asked*, not on the data: a
#: daily pattern study needs years to produce a base rate that means anything,
#: while a funding regime study works on a shorter window because the series
#: prints three times a day.
MIN_BACKTEST_DAYS: dict[str, int] = {
    "price": 365,
    "derivatives": 365,
    "etf": 365,
    "macro": 730,
    "onchain": 365,
    "defi": 365,
    "default": 365,
}

#: A long window with almost nothing in it is not history. Guards against a
#: series with two points a year apart passing the coverage test.
MIN_BACKTEST_POINTS: dict[str, int] = {
    "price": 250,
    "derivatives": 200,
    "etf": 200,
    "macro": 400,
    "onchain": 200,
    "defi": 200,
    "default": 200,
}

#: How old the last point may be before the series stops counting as live, by
#: metric class, in hours. Wider than the freshness thresholds on purpose:
#: freshness grades a number for display, this decides whether a series may be
#: used at all.
MAX_LIVE_AGE_HOURS: dict[str, float] = {
    "price": 6.0,
    "derivatives": 24.0,
    "etf": 96.0,       # published on business days, with a lag
    "macro": 120.0,    # weekends and holidays leave real gaps
    "onchain": 24.0,
    "defi": 24.0,
    "default": 24.0,
}


def _lookup(table: dict[str, Any], metric: str) -> Any:
    return table.get(metric_class(metric), table["default"])


@dataclass(slots=True)
class DataAvailability:
    """One series, and what it may be used for.

    Built through `assess` rather than by hand, so `usable_for_live`,
    `usable_for_backtest` and `reason` always follow from the measurements
    instead of being asserted alongside them.
    """

    source: str
    metric: str
    symbol: str | None = None

    first_timestamp: datetime | None = None
    last_timestamp: datetime | None = None
    number_of_points: int = 0
    coverage_days: float = 0.0

    usable_for_live: bool = False
    usable_for_backtest: bool = False
    reason: AvailabilityReason = AvailabilityReason.NO_DATA
    detail: str = ""

    #: Set when the ceiling comes from the source rather than from our
    #: collection - Binance's ~30 days of open-interest history, for instance.
    #: Backfilling harder will not improve it, and the UI should say so.
    source_limited: bool = False

    required_days: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def age_hours(self) -> float | None:
        if self.last_timestamp is None:
            return None
        last = self.last_timestamp
        if last.tzinfo is None:
            last = last.replace(tzinfo=UTC)
        return (datetime.now(UTC) - last).total_seconds() / 3600.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "symbol": self.symbol,
            "metric": self.metric,
            "first_timestamp": (
                self.first_timestamp.isoformat() if self.first_timestamp else None
            ),
            "last_timestamp": (
                self.last_timestamp.isoformat() if self.last_timestamp else None
            ),
            "number_of_points": self.number_of_points,
            "coverage_days": round(self.coverage_days, 1),
            "usable_for_live": self.usable_for_live,
            "usable_for_backtest": self.usable_for_backtest,
            "reason": self.reason.value,
            "detail": self.detail,
            "source_limited": self.source_limited,
            "required_days": self.required_days,
            "age_hours": round(self.age_hours, 1) if self.age_hours is not None else None,
            "metadata": self.metadata,
        }


def assess(
    *,
    source: str,
    metric: str,
    symbol: str | None = None,
    first: datetime | None = None,
    last: datetime | None = None,
    points: int = 0,
    source_limited: bool = False,
    source_note: str = "",
    now: datetime | None = None,
    min_backtest_days: int | None = None,
) -> DataAvailability:
    """Measure one series and decide what it supports.

    `now` is injectable so the decision is testable without freezing the clock,
    and so a point-in-time study can ask "what was usable at date T".
    """
    now = now or datetime.now(UTC)
    required_days = min_backtest_days or _lookup(MIN_BACKTEST_DAYS, metric)
    required_points = _lookup(MIN_BACKTEST_POINTS, metric)
    max_age = _lookup(MAX_LIVE_AGE_HOURS, metric)

    record = DataAvailability(
        source=source, metric=metric, symbol=symbol,
        first_timestamp=first, last_timestamp=last, number_of_points=points,
        source_limited=source_limited, required_days=required_days,
    )

    if points == 0 or first is None or last is None:
        record.reason = AvailabilityReason.NO_DATA
        record.detail = "no stored points for this series"
        return record

    first_utc = first if first.tzinfo else first.replace(tzinfo=UTC)
    last_utc = last if last.tzinfo else last.replace(tzinfo=UTC)
    record.coverage_days = (last_utc - first_utc).total_seconds() / 86400.0

    age_hours = (now - last_utc).total_seconds() / 3600.0
    record.usable_for_live = age_hours <= max_age

    deep_enough = record.coverage_days >= required_days
    dense_enough = points >= required_points
    record.usable_for_backtest = deep_enough and dense_enough

    # The reason describes the binding constraint. Depth is reported before
    # staleness because a series that is both short and stale is short first -
    # waiting fixes staleness, nothing fixes missing history.
    if not deep_enough:
        record.reason = AvailabilityReason.SOURCE_LIMIT if source_limited else (
            AvailabilityReason.INSUFFICIENT_HISTORY
        )
        record.detail = (
            f"{record.coverage_days:.0f} days of history, {required_days} needed for a study"
            + (f" - {source_note}" if source_note else "")
        )
    elif not dense_enough:
        record.reason = AvailabilityReason.INSUFFICIENT_POINTS
        record.detail = (
            f"{points} points across {record.coverage_days:.0f} days, "
            f"{required_points} needed - the series is too sparse to study"
        )
    elif not record.usable_for_live:
        record.reason = AvailabilityReason.STALE
        record.detail = (
            f"last point is {age_hours:.0f}h old, beyond the {max_age:.0f}h "
            "limit for this kind of series"
        )
    else:
        record.reason = AvailabilityReason.OK
        record.detail = (
            f"{points} points over {record.coverage_days:.0f} days, last one "
            f"{age_hours:.0f}h ago"
        )

    return record


def summarise(records: list[DataAvailability]) -> dict[str, Any]:
    """Headline counts for a coverage panel."""
    return {
        "series": len(records),
        "usable_for_live": sum(1 for r in records if r.usable_for_live),
        "usable_for_backtest": sum(1 for r in records if r.usable_for_backtest),
        "by_reason": {
            reason.value: sum(1 for r in records if r.reason is reason)
            for reason in AvailabilityReason
            if any(r.reason is reason for r in records)
        },
    }

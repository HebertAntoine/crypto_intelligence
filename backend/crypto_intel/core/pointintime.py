"""Point-in-time data model.

Every historical study rests on one claim: this value was knowable at that
moment. Until now the project stored a single `timestamp` per datapoint, which
silently conflates several different things:

    event_time        when the thing happened (July's inflation)
    observation_time  the period the value describes
    release_time      when it was first published (mid-August)
    revision_time     when it was corrected (later, possibly several times)
    ingested_at       when this system first saw it

A backtest that reads July's CPI on 31 July is using a number nobody had. The
error is invisible, never raises, and makes every result look better.

This module gives one vocabulary for all sources, plus an explicit
availability classification so a study can refuse to use series that cannot be
reconstructed as-of a date.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any


class Availability(StrEnum):
    """How faithfully a series can be reconstructed as of a past date."""

    # Timestamp IS the moment the value became public. Market data: a candle
    # closing at 12:00 was knowable at 12:00.
    POINT_IN_TIME = "POINT_IN_TIME"

    # Publication lag is known and applied, so the as-of view is correct even
    # though the source only ships the observation date.
    RECONSTRUCTED_PIT = "RECONSTRUCTED_PIT"

    # The value has been revised since first publication and the original
    # print is not retrievable. Usable for context, NOT for backtests.
    NOT_POINT_IN_TIME = "NOT_POINT_IN_TIME"

    # First-print vintages available (ALFRED).
    VINTAGE_AVAILABLE = "VINTAGE_AVAILABLE"

    UNKNOWN = "UNKNOWN"

    @property
    def usable_for_backtest(self) -> bool:
        """Only series that can be viewed as-of a past date may drive a study."""
        return self in (
            Availability.POINT_IN_TIME,
            Availability.RECONSTRUCTED_PIT,
            Availability.VINTAGE_AVAILABLE,
        )


@dataclass(slots=True)
class PointInTimeValue:
    """One observation with its full temporal provenance."""

    metric: str
    value: float
    observation_time: datetime
    release_time: datetime | None = None
    revision_time: datetime | None = None
    ingested_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    availability: Availability = Availability.UNKNOWN
    source: str = ""
    is_first_print: bool = True
    revision_number: int = 0
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def known_from(self) -> datetime:
        """The earliest moment this value could have been used.

        Falls back to the observation time only when the source genuinely
        publishes without lag (market data); for anything else, a missing
        release time means the value is not point-in-time and callers must
        check `availability` rather than trust this.
        """
        return self.release_time or self.observation_time

    def was_known_at(self, when: datetime) -> bool:
        return self.known_from <= when

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "value": self.value,
            "observation_time": self.observation_time.isoformat(),
            "release_time": self.release_time.isoformat() if self.release_time else None,
            "revision_time": self.revision_time.isoformat() if self.revision_time else None,
            "ingested_at": self.ingested_at.isoformat(),
            "availability": self.availability.value,
            "source": self.source,
            "is_first_print": self.is_first_print,
            "revision_number": self.revision_number,
            "known_from": self.known_from.isoformat(),
        }


# Typical publication lag per macro series, used to reconstruct an as-of view
# when the source ships only the observation date.
#
# These are the standard schedules: CPI for month M is released mid-M+1, the
# employment report on the first Friday of M+1, and so on. Applying the lag is
# an approximation of the real release calendar - which is why series treated
# this way are marked RECONSTRUCTED_PIT rather than POINT_IN_TIME.
PUBLICATION_LAG: dict[str, timedelta] = {
    "macro.cpi": timedelta(days=13),
    "macro.core_cpi": timedelta(days=13),
    "macro.pce": timedelta(days=28),
    "macro.core_pce": timedelta(days=28),
    "macro.unemployment": timedelta(days=7),
    "macro.nonfarm_payrolls": timedelta(days=7),
    "macro.gdp": timedelta(days=30),
    # Daily market-derived series publish same-day, after the close.
    "macro.fed_funds_rate": timedelta(days=1),
    "macro.us2y": timedelta(days=1),
    "macro.us10y": timedelta(days=1),
    "macro.yield_curve_10y2y": timedelta(days=1),
    "macro.dxy_broad": timedelta(days=1),
}

# Series that are genuinely point-in-time: the quoted value at time t was
# observable at time t.
NATIVE_PIT_PREFIXES = (
    "price.", "ohlcv.", "market.", "funding.", "oi.", "long_short.",
    "derivatives.", "macro.sp500", "macro.nasdaq", "macro.dow", "macro.dxy",
    "macro.vix", "macro.gold", "macro.oil_wti", "macro.us10y_yahoo",
    "macro.us5y_yahoo", "macro.us13w_yahoo",
)

# Series that are revised and whose first print this project cannot retrieve
# without ALFRED.
REVISED_SERIES = {
    "macro.cpi", "macro.core_cpi", "macro.pce", "macro.core_pce",
    "macro.unemployment", "macro.nonfarm_payrolls", "macro.gdp",
}


def classify_metric(metric: str, has_vintage: bool = False) -> Availability:
    """Decide how a metric may be used in a historical study."""
    if has_vintage:
        return Availability.VINTAGE_AVAILABLE
    if any(metric.startswith(prefix) for prefix in NATIVE_PIT_PREFIXES):
        return Availability.POINT_IN_TIME
    if metric in REVISED_SERIES:
        return Availability.NOT_POINT_IN_TIME
    if metric in PUBLICATION_LAG:
        return Availability.RECONSTRUCTED_PIT
    return Availability.UNKNOWN


def estimated_release_time(metric: str, observation_time: datetime) -> datetime | None:
    """When a value for this observation period would typically have appeared."""
    lag = PUBLICATION_LAG.get(metric)
    if lag is None:
        return None
    return observation_time + lag


def as_of_filter(
    values: list[PointInTimeValue], when: datetime, allow_revised: bool = False
) -> list[PointInTimeValue]:
    """Only the values that were genuinely knowable at `when`.

    `allow_revised` exists for context views (a dashboard may legitimately show
    today's best estimate). It must stay False for anything feeding a study.
    """
    out: list[PointInTimeValue] = []
    for value in values:
        if not value.was_known_at(when):
            continue
        if not allow_revised and value.availability is Availability.NOT_POINT_IN_TIME:
            continue
        out.append(value)
    return out


@dataclass(slots=True)
class SeriesAudit:
    """What a series is, and whether a study may use it."""

    metric: str
    availability: Availability
    rows: int = 0
    earliest: datetime | None = None
    latest: datetime | None = None
    source: str = ""
    has_release_time: bool = False
    usable_for_backtest: bool = False
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "availability": self.availability.value,
            "rows": self.rows,
            "earliest": self.earliest.isoformat() if self.earliest else None,
            "latest": self.latest.isoformat() if self.latest else None,
            "source": self.source,
            "has_release_time": self.has_release_time,
            "usable_for_backtest": self.usable_for_backtest,
            "reason": self.reason,
        }


def audit_series(metric: str, rows: int, earliest, latest, source: str,
                 has_release_time: bool = False, has_vintage: bool = False) -> SeriesAudit:
    """Classify one stored series."""
    availability = classify_metric(metric, has_vintage=has_vintage)

    if availability is Availability.NOT_POINT_IN_TIME:
        reason = (
            "This series is revised after publication and the original print is not "
            "retrievable from the configured source. Usable as current context, "
            "excluded from studies that require as-of-date information."
        )
    elif availability is Availability.RECONSTRUCTED_PIT:
        lag = PUBLICATION_LAG.get(metric)
        reason = (
            f"Not revised, but published with a lag. An estimated release time of "
            f"observation + {lag.days} days is applied to reconstruct the as-of view."
        )
    elif availability is Availability.VINTAGE_AVAILABLE:
        reason = "First-print vintages retrieved from ALFRED; as-of views are exact."
    elif availability is Availability.POINT_IN_TIME:
        reason = "The quoted value at time t was observable at time t."
    else:
        reason = "Availability not classified; treated as unsafe for backtests."

    return SeriesAudit(
        metric=metric, availability=availability, rows=rows,
        earliest=earliest, latest=latest, source=source,
        has_release_time=has_release_time,
        usable_for_backtest=availability.usable_for_backtest,
        reason=reason,
    )

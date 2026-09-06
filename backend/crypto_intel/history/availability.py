"""Measure what is actually stored, series by series.

`store.py` already reports coverage per dataset, but each helper returns a
different shape and none of them says whether the depth is enough for anything.
This module runs one aggregate query per table and turns the results into
`DataAvailability` records, so a single call answers "what can I use right now,
and what can I study?" for every series in the database.

Everything here is measured. Nothing is declared: if a series is missing from
the output, it is missing from the database.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select

from ..core.availability import DataAvailability, assess, summarise
from ..db.base import (
    BackfillStateRow,
    DerivativesHistoryRow,
    ETFFlowRow,
    MacroSeriesRow,
    ObservationRow,
    OHLCVRow,
)
from ..db.session import session_scope
from ..logging_setup import get_logger

log = get_logger("history.availability")

#: Ceilings imposed by the data source itself. Recorded so the interface can
#: say "the source publishes no more" instead of "backfill it again", which
#: would send the user chasing data that does not exist.
SOURCE_LIMITS: dict[str, str] = {
    "oi.value": "Binance publishes only ~30 days of open-interest history",
    "oi.contracts": "exchange endpoint exposes a rolling window only",
}

#: Series a study is expected to reach for, with the depth that study needs.
#: Absent from this map means the class default in `core.availability` applies.
STUDY_DEPTH_OVERRIDES: dict[str, int] = {
    # A pattern base rate on the daily timeframe needs several market cycles,
    # not one. Two years of daily bars produces confident-looking nonsense.
    "ohlcv.1d": 1095,
    "ohlcv.1w": 1095,
    "ohlcv.4h": 730,
    "ohlcv.1h": 365,
    "ohlcv.15m": 180,
}


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _source_limit(metric: str) -> tuple[bool, str]:
    note = SOURCE_LIMITS.get(metric)
    return (note is not None), (note or "")


def candle_availability(now: datetime | None = None) -> list[DataAvailability]:
    """One record per (asset, timeframe) actually present in `ohlcv`."""
    with session_scope() as s:
        rows = s.execute(
            select(
                OHLCVRow.asset,
                OHLCVRow.timeframe,
                func.count(OHLCVRow.id),
                func.min(OHLCVRow.timestamp),
                func.max(OHLCVRow.timestamp),
                func.min(OHLCVRow.source),
            ).group_by(OHLCVRow.asset, OHLCVRow.timeframe)
        ).all()

    out: list[DataAvailability] = []
    for asset, timeframe, count, first, last, source in rows:
        metric = f"ohlcv.{timeframe}"
        out.append(
            assess(
                source=source or "unknown",
                metric=metric,
                symbol=asset,
                first=_as_utc(first),
                last=_as_utc(last),
                points=int(count),
                now=now,
                min_backtest_days=STUDY_DEPTH_OVERRIDES.get(metric),
            )
        )
    return sorted(out, key=lambda r: (r.symbol or "", r.metric))


def derivatives_availability(now: datetime | None = None) -> list[DataAvailability]:
    """One record per (asset, metric) in `derivatives_history`."""
    with session_scope() as s:
        rows = s.execute(
            select(
                DerivativesHistoryRow.asset,
                DerivativesHistoryRow.metric,
                func.count(DerivativesHistoryRow.id),
                func.min(DerivativesHistoryRow.timestamp),
                func.max(DerivativesHistoryRow.timestamp),
                func.min(DerivativesHistoryRow.source),
            ).group_by(DerivativesHistoryRow.asset, DerivativesHistoryRow.metric)
        ).all()

    out: list[DataAvailability] = []
    for asset, metric, count, first, last, source in rows:
        limited, note = _source_limit(metric)
        out.append(
            assess(
                source=source or "unknown", metric=metric, symbol=asset,
                first=_as_utc(first), last=_as_utc(last), points=int(count),
                source_limited=limited, source_note=note, now=now,
            )
        )
    return sorted(out, key=lambda r: (r.symbol or "", r.metric))


def macro_availability(now: datetime | None = None) -> list[DataAvailability]:
    """One record per macro series."""
    with session_scope() as s:
        rows = s.execute(
            select(
                MacroSeriesRow.metric,
                func.count(MacroSeriesRow.id),
                func.min(MacroSeriesRow.timestamp),
                func.max(MacroSeriesRow.timestamp),
                func.min(MacroSeriesRow.source),
            ).group_by(MacroSeriesRow.metric)
        ).all()

    return [
        assess(
            source=source or "unknown", metric=metric, symbol=None,
            first=_as_utc(first), last=_as_utc(last), points=int(count), now=now,
        )
        for metric, count, first, last, source in rows
    ]


def etf_availability(now: datetime | None = None) -> list[DataAvailability]:
    """One record per asset with ETF flows.

    Rows are per fund per day, so the point count is divided by the number of
    distinct funds - otherwise twelve BTC ETFs would look like twelve times the
    history the asset actually has.
    """
    with session_scope() as s:
        rows = s.execute(
            select(
                ETFFlowRow.asset,
                func.count(ETFFlowRow.id),
                func.count(func.distinct(ETFFlowRow.ticker)),
                func.min(ETFFlowRow.date),
                func.max(ETFFlowRow.date),
                func.min(ETFFlowRow.import_source),
            ).group_by(ETFFlowRow.asset)
        ).all()

    out: list[DataAvailability] = []
    for asset, count, funds, first, last, source in rows:
        trading_days = int(count) // max(1, int(funds))
        record = assess(
            source=source or "unknown", metric="etf.flow", symbol=asset,
            first=_as_utc(first), last=_as_utc(last), points=trading_days, now=now,
        )
        record.metadata["funds"] = int(funds)
        record.metadata["rows"] = int(count)
        out.append(record)
    return out


def observation_availability(
    now: datetime | None = None, min_points: int = 2
) -> list[DataAvailability]:
    """One record per (metric, asset) in `observations` - the live series.

    These are the polled metrics: on-chain, DeFi, stablecoins, long/short ratio,
    basis. Most carry days rather than years, which is precisely what the
    consumer needs to know before building a statistic on one.
    """
    with session_scope() as s:
        rows = s.execute(
            select(
                ObservationRow.metric,
                ObservationRow.asset,
                func.count(ObservationRow.id),
                func.min(ObservationRow.timestamp),
                func.max(ObservationRow.timestamp),
                func.min(ObservationRow.source),
            )
            .group_by(ObservationRow.metric, ObservationRow.asset)
            .having(func.count(ObservationRow.id) >= min_points)
        ).all()

    return sorted(
        (
            assess(
                source=source or "unknown", metric=metric, symbol=asset,
                first=_as_utc(first), last=_as_utc(last), points=int(count), now=now,
            )
            for metric, asset, count, first, last, source in rows
        ),
        key=lambda r: (r.metric, r.symbol or ""),
    )


def backfill_notes() -> dict[str, str]:
    """Notes recorded by the last backfill, keyed by dataset and asset.

    Surfacing these keeps a source's own admission ("only ~30 days available")
    attached to the series it constrains.
    """
    with session_scope() as s:
        rows = s.execute(
            select(
                BackfillStateRow.dataset, BackfillStateRow.asset,
                BackfillStateRow.timeframe, BackfillStateRow.note,
                BackfillStateRow.complete,
            )
        ).all()
    notes: dict[str, str] = {}
    for dataset, asset, timeframe, note, complete in rows:
        key = ".".join(part for part in (dataset, asset, timeframe) if part)
        notes[key] = note or ("complete" if complete else "incomplete")
    return notes


def full_report(now: datetime | None = None) -> dict[str, Any]:
    """Every series the database holds, grouped and summarised.

    This is what `/api/analysis/data-availability` returns and what the
    confluence engine consults before deciding which families it may score.
    """
    groups: dict[str, list[DataAvailability]] = {
        "candles": candle_availability(now),
        "derivatives": derivatives_availability(now),
        "macro": macro_availability(now),
        "etf": etf_availability(now),
        "live_observations": observation_availability(now),
    }
    everything = [record for records in groups.values() for record in records]

    return {
        "generated_at": (now or datetime.now(UTC)).isoformat(),
        "groups": {
            name: [record.to_dict() for record in records]
            for name, records in groups.items()
        },
        "summary": summarise(everything),
        "backfill_notes": backfill_notes(),
        "note": (
            "usable_for_live and usable_for_backtest are different questions. A "
            "series can be perfectly current and still carry too little history "
            "to support any statistic - open interest and stablecoin supply are "
            "both in that position today."
        ),
    }


def lookup(
    metric: str, symbol: str | None = None, now: datetime | None = None
) -> DataAvailability | None:
    """One series by name, for a caller that needs a single check."""
    for record in (
        candle_availability(now)
        + derivatives_availability(now)
        + macro_availability(now)
        + etf_availability(now)
        + observation_availability(now)
    ):
        if record.metric == metric and record.symbol == symbol:
            return record
    return None

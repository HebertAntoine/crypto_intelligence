"""Storage helpers for historical series (candles, macro, derivatives).

Kept apart from `db/repo.py` because these are bulk, research-oriented writes:
tens of thousands of rows at a time, upserted by deterministic id so a backfill
can be re-run safely.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

import pandas as pd
from sqlalchemy import select

from ..core.enums import Asset, Timeframe
from ..core.models import Candle
from ..db.base import BackfillStateRow, DerivativesHistoryRow, MacroSeriesRow, OHLCVRow
from ..db.session import session_scope
from ..logging_setup import get_logger

log = get_logger("history.store")


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _row_id(*parts: Any) -> str:
    return hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:32]


# --- OHLCV ----------------------------------------------------------------

def save_candles(
    asset: Asset, timeframe: Timeframe, candles: list[Candle], source: str = ""
) -> int:
    """Upsert candles. Idempotent: the id is a hash of asset|tf|timestamp."""
    if not candles:
        return 0

    written = 0
    with session_scope() as s:
        existing_ids = {
            r[0]
            for r in s.execute(
                select(OHLCVRow.id).where(
                    OHLCVRow.asset == asset.value, OHLCVRow.timeframe == timeframe.value
                )
            ).all()
        }
        for c in candles:
            rid = _row_id(asset.value, timeframe.value, c.timestamp.isoformat())
            if rid in existing_ids:
                # The most recent candle is still forming, so refresh it rather
                # than keeping a partial bar forever.
                row = s.get(OHLCVRow, rid)
                if row is not None:
                    row.open, row.high, row.low = c.open, c.high, c.low
                    row.close, row.volume = c.close, c.volume
                continue
            s.add(
                OHLCVRow(
                    id=rid, asset=asset.value, timeframe=timeframe.value,
                    timestamp=c.timestamp, open=c.open, high=c.high, low=c.low,
                    close=c.close, volume=c.volume, source=source,
                )
            )
            written += 1
    return written


def load_candles(
    asset: Asset,
    timeframe: Timeframe,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int | None = None,
) -> pd.DataFrame:
    """Return stored candles as a DataFrame indexed by timestamp."""
    with session_scope() as s:
        stmt = select(OHLCVRow).where(
            OHLCVRow.asset == asset.value, OHLCVRow.timeframe == timeframe.value
        )
        if start:
            stmt = stmt.where(OHLCVRow.timestamp >= start)
        if end:
            stmt = stmt.where(OHLCVRow.timestamp <= end)
        stmt = stmt.order_by(OHLCVRow.timestamp.asc())
        rows = s.execute(stmt).scalars().all()

    if not rows:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    if limit:
        rows = rows[-limit:]

    df = pd.DataFrame(
        {
            "open": [r.open for r in rows], "high": [r.high for r in rows],
            "low": [r.low for r in rows], "close": [r.close for r in rows],
            "volume": [r.volume for r in rows],
        },
        index=pd.DatetimeIndex([_as_utc(r.timestamp) for r in rows], name="timestamp"),
    )
    return df


def candle_coverage(asset: Asset, timeframe: Timeframe) -> dict[str, Any]:
    with session_scope() as s:
        rows = s.execute(
            select(OHLCVRow.timestamp).where(
                OHLCVRow.asset == asset.value, OHLCVRow.timeframe == timeframe.value
            ).order_by(OHLCVRow.timestamp.asc())
        ).all()
    if not rows:
        return {"rows": 0, "start": None, "end": None, "days": 0}
    start, end = _as_utc(rows[0][0]), _as_utc(rows[-1][0])
    return {
        "rows": len(rows), "start": start, "end": end,
        "days": round((end - start).total_seconds() / 86400.0, 1),
    }


# --- macro ----------------------------------------------------------------

def save_macro(metric: str, points: list[tuple[datetime, float]], source: str = "") -> int:
    if not points:
        return 0
    written = 0
    with session_scope() as s:
        for ts, value in points:
            ts = _as_utc(ts)
            rid = _row_id(metric, ts.isoformat())
            if s.get(MacroSeriesRow, rid) is not None:
                continue
            s.add(MacroSeriesRow(id=rid, metric=metric, timestamp=ts, value=float(value), source=source))
            written += 1
    return written


def load_macro(metric: str, start: datetime | None = None) -> pd.Series:
    with session_scope() as s:
        stmt = select(MacroSeriesRow).where(MacroSeriesRow.metric == metric)
        if start:
            stmt = stmt.where(MacroSeriesRow.timestamp >= start)
        rows = s.execute(stmt.order_by(MacroSeriesRow.timestamp.asc())).scalars().all()
    if not rows:
        return pd.Series(dtype=float)
    return pd.Series(
        [r.value for r in rows],
        index=pd.DatetimeIndex([_as_utc(r.timestamp) for r in rows]),
        name=metric,
    )


def macro_coverage() -> dict[str, dict[str, Any]]:
    with session_scope() as s:
        rows = s.execute(
            select(MacroSeriesRow.metric, MacroSeriesRow.timestamp)
            .order_by(MacroSeriesRow.metric, MacroSeriesRow.timestamp)
        ).all()
    out: dict[str, dict[str, Any]] = {}
    for metric, ts in rows:
        ts = _as_utc(ts)
        entry = out.setdefault(metric, {"rows": 0, "start": ts, "end": ts})
        entry["rows"] += 1
        entry["start"] = min(entry["start"], ts)
        entry["end"] = max(entry["end"], ts)
    for entry in out.values():
        entry["days"] = round((entry["end"] - entry["start"]).total_seconds() / 86400.0, 1)
    return out


# --- derivatives ----------------------------------------------------------

def save_derivatives(
    asset: Asset, metric: str, points: list[tuple[datetime, float]], source: str = ""
) -> int:
    if not points:
        return 0
    written = 0
    with session_scope() as s:
        for ts, value in points:
            ts = _as_utc(ts)
            rid = _row_id(asset.value, metric, ts.isoformat())
            if s.get(DerivativesHistoryRow, rid) is not None:
                continue
            s.add(
                DerivativesHistoryRow(
                    id=rid, asset=asset.value, metric=metric, timestamp=ts,
                    value=float(value), source=source,
                )
            )
            written += 1
    return written


def load_derivatives(asset: Asset, metric: str, start: datetime | None = None) -> pd.Series:
    with session_scope() as s:
        stmt = select(DerivativesHistoryRow).where(
            DerivativesHistoryRow.asset == asset.value, DerivativesHistoryRow.metric == metric
        )
        if start:
            stmt = stmt.where(DerivativesHistoryRow.timestamp >= start)
        rows = s.execute(stmt.order_by(DerivativesHistoryRow.timestamp.asc())).scalars().all()
    if not rows:
        return pd.Series(dtype=float)
    return pd.Series(
        [r.value for r in rows],
        index=pd.DatetimeIndex([_as_utc(r.timestamp) for r in rows]),
        name=metric,
    )


def derivatives_coverage(asset: Asset) -> dict[str, dict[str, Any]]:
    with session_scope() as s:
        rows = s.execute(
            select(DerivativesHistoryRow.metric, DerivativesHistoryRow.timestamp)
            .where(DerivativesHistoryRow.asset == asset.value)
        ).all()
    out: dict[str, dict[str, Any]] = {}
    for metric, ts in rows:
        ts = _as_utc(ts)
        entry = out.setdefault(metric, {"rows": 0, "start": ts, "end": ts})
        entry["rows"] += 1
        entry["start"] = min(entry["start"], ts)
        entry["end"] = max(entry["end"], ts)
    for entry in out.values():
        entry["days"] = round((entry["end"] - entry["start"]).total_seconds() / 86400.0, 1)
    return out


# --- backfill bookkeeping -------------------------------------------------

def record_backfill(
    dataset: str,
    asset: Asset | None,
    timeframe: Timeframe | None,
    earliest: datetime | None,
    latest: datetime | None,
    rows: int,
    source: str,
    complete: bool = True,
    note: str = "",
) -> None:
    rid = _row_id(dataset, asset.value if asset else "-", timeframe.value if timeframe else "-")
    with session_scope() as s:
        row = s.get(BackfillStateRow, rid)
        if row is None:
            row = BackfillStateRow(
                id=rid, dataset=dataset,
                asset=asset.value if asset else None,
                timeframe=timeframe.value if timeframe else None,
            )
            s.add(row)
        row.earliest = _as_utc(earliest)
        row.latest = _as_utc(latest)
        row.rows = rows
        row.source = source
        row.complete = complete
        row.note = note
        row.updated_at = datetime.now(UTC)


def backfill_report() -> list[dict[str, Any]]:
    """What history exists, per dataset. Powers the documented depth table."""
    with session_scope() as s:
        rows = s.execute(select(BackfillStateRow).order_by(BackfillStateRow.dataset)).scalars().all()
        return [
            {
                "dataset": r.dataset, "asset": r.asset, "timeframe": r.timeframe,
                "earliest": _as_utc(r.earliest), "latest": _as_utc(r.latest),
                "rows": r.rows, "source": r.source, "complete": r.complete,
                "note": r.note,
                "days": (
                    round((_as_utc(r.latest) - _as_utc(r.earliest)).total_seconds() / 86400.0, 1)
                    if r.earliest and r.latest else 0
                ),
            }
            for r in rows
        ]

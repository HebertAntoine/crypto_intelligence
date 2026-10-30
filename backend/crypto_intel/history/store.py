"""Storage helpers for historical series (candles, macro, derivatives).

Kept apart from `db/repo.py` because these are bulk, research-oriented writes:
tens of thousands of rows at a time, upserted by deterministic id so a backfill
can be re-run safely.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any, overload

import pandas as pd
from sqlalchemy import distinct, func, select

from ..core.enums import Asset, Timeframe
from ..core.models import Candle, Observation
from ..core.pointintime import Availability
from ..db.base import (
    BackfillStateRow,
    DerivativesHistoryRow,
    MacroSeriesRow,
    MacroVintageRow,
    OHLCVRow,
)
from ..db.session import session_scope
from ..logging_setup import get_logger

log = get_logger("history.store")


@overload
def _as_utc(dt: datetime) -> datetime: ...


@overload
def _as_utc(dt: None) -> None: ...


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.astimezone(UTC) if dt.tzinfo else dt.replace(tzinfo=UTC)


def _row_id(*parts: Any) -> str:
    return hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:32]


# --- OHLCV ----------------------------------------------------------------

def candle_span(timeframe: Timeframe) -> timedelta:
    """Wall-clock duration of one exchange candle."""

    return timedelta(minutes=timeframe.minutes)


def candle_close_time(opened_at: datetime, timeframe: Timeframe) -> datetime:
    """Return the first instant at which a bar's close is knowable."""

    return _as_utc(opened_at) + candle_span(timeframe)


def candle_is_closed(
    opened_at: datetime,
    timeframe: Timeframe,
    *,
    as_of: datetime | None = None,
) -> bool:
    """Whether a bar stamped at its open had closed by ``as_of``.

    Binance stamps every supported interval at its UTC open.  Equality is
    intentional: at exactly 12:15:00 UTC the bar opened at 12:00:00 on a 15m
    interval is closed and may be analysed.
    """

    known_at = _as_utc(as_of) if as_of is not None else datetime.now(UTC)
    return candle_close_time(opened_at, timeframe) <= known_at


def closed_candle_cutoff(
    timeframe: Timeframe,
    *,
    as_of: datetime | None = None,
) -> datetime:
    """Latest candle-open timestamp that is closed at ``as_of``."""

    known_at = _as_utc(as_of) if as_of is not None else datetime.now(UTC)
    return known_at - candle_span(timeframe)

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
                    if source:
                        # Provenance follows the values. Keeping an old source
                        # after replacing a forming candle would make the chart
                        # metadata claim that another venue supplied it.
                        row.source = source
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
    *,
    as_of: datetime | None = None,
) -> pd.DataFrame:
    """Return only candles that were closed at the requested instant.

    ``timestamp`` is the bar open, not its close.  Therefore filtering merely
    on ``timestamp <= end`` leaks the final, still-forming bar into indicators
    and pattern detectors.  When a historical ``end`` is supplied without an
    explicit ``as_of``, it is also the visibility instant, which keeps research
    calls point-in-time safe.  With neither argument, visibility is evaluated
    at the current UTC instant.

    Storage coverage deliberately uses :func:`candle_coverage` instead; that
    raw operational view may include a forming bar so a later refresh can
    update it in place.
    """

    visibility_at = _as_utc(as_of) if as_of is not None else _as_utc(end)
    cutoff = closed_candle_cutoff(timeframe, as_of=visibility_at)
    query_end = cutoff
    if end is not None:
        requested_end = _as_utc(end)
        query_end = min(query_end, requested_end)

    with session_scope() as s:
        stmt = select(OHLCVRow).where(
            OHLCVRow.asset == asset.value,
            OHLCVRow.timeframe == timeframe.value,
            OHLCVRow.timestamp <= query_end,
        )
        if start:
            stmt = stmt.where(OHLCVRow.timestamp >= _as_utc(start))
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


def candle_metadata(
    asset: Asset,
    timeframe: Timeframe,
    *,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    """Return cheap coverage and provenance metadata without loading candles.

    This describes the series safe to serve and analyse, so an in-progress bar
    is excluded just as it is by :func:`load_candles`.  Raw operational depth,
    including a forming bar, remains available through :func:`candle_coverage`.

    ``source`` is the source attached to the newest closed bar, while
    ``sources`` documents every source present in the closed series. The two
    are deliberately separate: a historical import can contain older rows from
    another provider even after current bars are refreshed by Binance.
    """
    cutoff = closed_candle_cutoff(timeframe, as_of=as_of)
    closed_rows = (
        OHLCVRow.asset == asset.value,
        OHLCVRow.timeframe == timeframe.value,
        OHLCVRow.timestamp <= cutoff,
    )
    with session_scope() as s:
        count, start, end = s.execute(
            select(
                func.count(OHLCVRow.id),
                func.min(OHLCVRow.timestamp),
                func.max(OHLCVRow.timestamp),
            ).where(*closed_rows)
        ).one()
        latest_source = s.execute(
            select(OHLCVRow.source)
            .where(*closed_rows)
            .order_by(OHLCVRow.timestamp.desc())
            .limit(1)
        ).scalar_one_or_none()
        sources = s.execute(
            select(distinct(OHLCVRow.source))
            .where(*closed_rows, OHLCVRow.source != "")
            .order_by(OHLCVRow.source)
        ).scalars().all()

    return {
        "rows": int(count or 0),
        "start": _as_utc(start),
        "end": _as_utc(end),
        "source": latest_source or None,
        "sources": list(sources),
    }


# --- macro ----------------------------------------------------------------

def _meta_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return _as_utc(value)
    if isinstance(value, str) and value:
        try:
            return _as_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
        except ValueError:
            return None
    return None


_VINTAGE_PROVENANCE_FIELDS = (
    "source",
    "provider",
    "unit",
    "source_url",
    "license_status",
    "meta",
    "release_time",
    "availability",
)


def _series_vintage_provenance(row: MacroSeriesRow) -> dict[str, Any]:
    """Snapshot the provenance that belongs to the current stored value."""

    return {
        "source": row.source,
        "provider": row.provider,
        "unit": row.unit,
        "source_url": row.source_url,
        "license_status": row.license_status,
        "meta": dict(row.meta) if row.meta is not None else None,
        "release_time": _as_utc(row.release_time),
        "availability": row.availability,
    }


def _fields_vintage_provenance(fields: dict[str, Any]) -> dict[str, Any]:
    """Extract an independent JSON-safe provenance snapshot for a vintage."""

    return {
        name: dict(fields[name]) if name == "meta" and fields[name] is not None else fields[name]
        for name in _VINTAGE_PROVENANCE_FIELDS
    }


def _fill_legacy_vintage_provenance(
    vintage: MacroVintageRow,
    provenance: dict[str, Any],
) -> None:
    """Fill only legacy NULLs before the current series row is overwritten."""

    for name in _VINTAGE_PROVENANCE_FIELDS:
        if getattr(vintage, name) is None:
            value = provenance[name]
            setattr(vintage, name, dict(value) if name == "meta" and value is not None else value)


def _provenance_changed(existing: MacroSeriesRow, fields: dict[str, Any]) -> bool:
    """A source/rights change is itself a point-in-time version boundary."""

    return any(
        getattr(existing, name) != fields[name]
        for name in (*_VINTAGE_PROVENANCE_FIELDS, "series_id")
    )


def save_macro_records(records: list[dict[str, Any]]) -> int:
    """Upsert rich macro records and preserve changed values/provenance as vintages.

    A provider refresh may legitimately revise a historical macro value.  The
    current row is updated, but both the former and replacement versions are
    appended to ``macro_vintages`` with their respective provenance and
    ingestion times. A provider or rights change with the same value is also a
    version boundary: otherwise a replay would project today's licence/source
    backwards.
    """

    if not records:
        return 0
    written = 0
    with session_scope() as s:
        for record in records:
            metric = str(record["metric"])
            ts = _as_utc(record["timestamp"])
            if ts is None:
                continue
            value = float(record["value"])
            ingested_at = _as_utc(record.get("ingested_at")) or datetime.now(UTC)
            release_time = _as_utc(record.get("release_time"))
            rid = _row_id(metric, ts.isoformat())
            existing = s.get(MacroSeriesRow, rid)
            fields = {
                "source": str(record.get("source") or ""),
                "provider": str(record.get("provider") or record.get("source") or ""),
                "unit": str(record.get("unit") or ""),
                "source_url": record.get("source_url"),
                "series_id": record.get("series_id"),
                "license_status": str(record.get("license_status") or "UNKNOWN"),
                "meta": dict(record.get("meta") or {}),
                "release_time": release_time,
                "availability": str(record.get("availability") or Availability.UNKNOWN.value),
                "ingested_at": ingested_at,
            }
            vintage_provenance = _fields_vintage_provenance(fields)
            if existing is None:
                s.add(MacroSeriesRow(
                    id=rid,
                    metric=metric,
                    timestamp=ts,
                    value=value,
                    revision_number=int(record.get("revision_number") or 0),
                    is_first_print=bool(record.get("is_first_print", True)),
                    vintage_date=_as_utc(record.get("vintage_date")) or ingested_at,
                    **fields,
                ))
                s.add(MacroVintageRow(
                    id=_row_id(metric, ts.isoformat(), ingested_at.isoformat()),
                    metric=metric,
                    series_id=str(record.get("series_id") or metric),
                    observation_time=ts,
                    vintage_date=ingested_at,
                    value=value,
                    is_first_print=bool(record.get("is_first_print", True)),
                    revision_number=int(record.get("revision_number") or 0),
                    ingested_at=ingested_at,
                    **vintage_provenance,
                ))
                written += 1
                continue

            changed = existing.value != value or _provenance_changed(existing, fields)
            if changed:
                existing_vintages = s.execute(
                    select(MacroVintageRow).where(
                        MacroVintageRow.metric == metric,
                        MacroVintageRow.observation_time == ts,
                    ).order_by(MacroVintageRow.vintage_date.asc())
                ).scalars().all()
                previous_provenance = _series_vintage_provenance(existing)
                if not existing_vintages:
                    original_vintage = (
                        _as_utc(existing.vintage_date)
                        or _as_utc(existing.ingested_at)
                        or _as_utc(existing.release_time)
                        or ingested_at
                    )
                    s.add(MacroVintageRow(
                        id=_row_id(metric, ts.isoformat(), original_vintage.isoformat()),
                        metric=metric,
                        series_id=str(existing.series_id or metric),
                        observation_time=ts,
                        vintage_date=original_vintage,
                        value=existing.value,
                        is_first_print=bool(existing.is_first_print),
                        revision_number=int(existing.revision_number or 0),
                        ingested_at=original_vintage,
                        **previous_provenance,
                    ))
                else:
                    # Rows created by the pre-provenance schema have NULLs.
                    # The latest vintage represents ``existing.value`` now, so
                    # this is the final safe moment to attach its old source and
                    # rights before the current row receives the new provider.
                    _fill_legacy_vintage_provenance(
                        existing_vintages[-1], previous_provenance
                    )
                revision_number = int(existing.revision_number or 0) + 1
                existing.value = value
                existing.revision_time = ingested_at
                existing.revision_number = revision_number
                existing.is_first_print = False
                existing.vintage_date = ingested_at
                vintage_id = _row_id(metric, ts.isoformat(), ingested_at.isoformat())
                if s.get(MacroVintageRow, vintage_id) is None:
                    s.add(MacroVintageRow(
                        id=vintage_id,
                        metric=metric,
                        series_id=str(record.get("series_id") or metric),
                        observation_time=ts,
                        vintage_date=ingested_at,
                        value=value,
                        is_first_print=False,
                        revision_number=revision_number,
                        ingested_at=ingested_at,
                        **vintage_provenance,
                    ))
                written += 1
            for name, field_value in fields.items():
                setattr(existing, name, field_value)
    return written


def save_macro_observations(observations: list[Observation]) -> int:
    """Persist provider observations without dropping temporal/licence metadata."""

    records: list[dict[str, Any]] = []
    for observation in observations:
        value = observation.numeric_value
        if value is None:
            continue
        meta = dict(observation.meta)
        release_time = _meta_datetime(meta.get("publication_time"))
        reconstructed = False
        if release_time is None:
            release_time = _meta_datetime(meta.get("available_at"))
            reconstructed = release_time is not None
        availability = str(meta.get("availability") or "")
        if not availability:
            availability = (
                Availability.RECONSTRUCTED_PIT.value
                if reconstructed
                else Availability.UNKNOWN.value
            )
        records.append({
            "metric": observation.metric,
            "timestamp": observation.timestamp,
            "value": value,
            "source": observation.provenance.source,
            "provider": observation.provenance.provider,
            "unit": observation.unit,
            "source_url": observation.provenance.source_url,
            "series_id": meta.get("series_id") or meta.get("source_document_id"),
            "license_status": meta.get("license_status") or "UNKNOWN",
            "meta": meta,
            "release_time": release_time,
            "availability": availability,
            "revision_number": meta.get("revision_number") or 0,
            "is_first_print": meta.get("is_first_print", True),
            "vintage_date": _meta_datetime(meta.get("vintage_time")),
            "ingested_at": observation.provenance.fetched_at,
        })
    return save_macro_records(records)


def save_macro(metric: str, points: list[tuple[datetime, float]], source: str = "") -> int:
    """Compatibility writer for legacy callers without rich provenance."""

    return save_macro_records([
        {
            "metric": metric,
            "timestamp": stamp,
            "value": value,
            "source": source,
            "provider": source,
            "availability": Availability.UNKNOWN.value,
        }
        for stamp, value in points
    ])


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


def load_macro_records(metric: str, start: datetime | None = None) -> list[dict[str, Any]]:
    """Macro rows with temporal provenance intact.

    ``load_macro`` remains for numerical research callers.  Decision views use
    this richer form so the stored provider and release time are not replaced
    by a hard-coded label or a guessed timestamp.
    """

    with session_scope() as session:
        statement = select(MacroSeriesRow).where(MacroSeriesRow.metric == metric)
        if start:
            statement = statement.where(MacroSeriesRow.timestamp >= start)
        rows = session.execute(statement.order_by(MacroSeriesRow.timestamp.asc())).scalars().all()
        vintages = session.execute(
            select(MacroVintageRow).where(MacroVintageRow.metric == metric).order_by(
                MacroVintageRow.observation_time.asc(), MacroVintageRow.vintage_date.asc()
            )
        ).scalars().all()
        vintages_by_observation: dict[datetime, list[MacroVintageRow]] = {}
        for vintage in vintages:
            stamp = _as_utc(vintage.observation_time)
            if stamp is not None:
                vintages_by_observation.setdefault(stamp, []).append(vintage)

        records: list[dict[str, Any]] = []
        for row in rows:
            timestamp = _as_utc(row.timestamp)
            if timestamp is None:
                continue
            common = {
                "timestamp": timestamp,
                "source": row.source,
                "provider": row.provider,
                "unit": row.unit,
                "source_url": row.source_url,
                "series_id": row.series_id,
                "license_status": row.license_status,
                "meta": row.meta or {},
                "availability": row.availability,
                "ingested_at": _as_utc(row.ingested_at) if row.ingested_at else None,
            }
            versions = vintages_by_observation.get(timestamp, [])
            if row.revision_number and versions:
                for version in versions:
                    revision_number = int(version.revision_number or 0)
                    # Vintage columns are nullable only for databases created
                    # before provenance snapshots existed. Preserve explicit
                    # empty values and fall back field-by-field only on NULL.
                    version_source = (
                        version.source if version.source is not None else row.source
                    )
                    version_provider = (
                        version.provider if version.provider is not None else row.provider
                    )
                    version_unit = version.unit if version.unit is not None else row.unit
                    version_source_url = (
                        version.source_url
                        if version.source_url is not None
                        else row.source_url
                    )
                    version_license = (
                        version.license_status
                        if version.license_status is not None
                        else row.license_status
                    )
                    version_meta = (
                        dict(version.meta)
                        if version.meta is not None
                        else dict(row.meta or {})
                    )
                    version_release = (
                        _as_utc(version.release_time)
                        if version.release_time is not None
                        else _as_utc(row.release_time)
                    )
                    version_availability = (
                        version.availability
                        if version.availability is not None
                        else row.availability
                    )
                    available = (
                        version_release
                        if revision_number == 0 and version_release
                        else _as_utc(version.vintage_date)
                    )
                    records.append({
                        **common,
                        "source": version_source,
                        "provider": version_provider,
                        "unit": version_unit,
                        "source_url": version_source_url,
                        "series_id": version.series_id or row.series_id,
                        "license_status": version_license,
                        "meta": version_meta,
                        "availability": version_availability,
                        "ingested_at": (
                            _as_utc(version.ingested_at)
                            if version.ingested_at
                            else common["ingested_at"]
                        ),
                        "value": version.value,
                        "release_time": available,
                        "revision_time": (
                            _as_utc(version.vintage_date) if revision_number else None
                        ),
                        "revision_number": revision_number,
                        "is_first_print": version.is_first_print,
                        "vintage_date": _as_utc(version.vintage_date),
                    })
            else:
                records.append({
                    **common,
                    "value": row.value,
                    "release_time": _as_utc(row.release_time) if row.release_time else None,
                    "revision_time": _as_utc(row.revision_time) if row.revision_time else None,
                    "revision_number": row.revision_number,
                    "is_first_print": row.is_first_print,
                    "vintage_date": _as_utc(row.vintage_date) if row.vintage_date else None,
                })
        return records


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


def upsert_derivatives(
    asset: Asset, metric: str, points: list[tuple[datetime, float]], source: str = ""
) -> int:
    """Insert or overwrite - for buckets that fill up over time (an hour of
    trades still in progress, an hourly total revised by its exchange)."""

    if not points:
        return 0
    with session_scope() as s:
        for ts, value in points:
            ts = _as_utc(ts)
            rid = _row_id(asset.value, metric, ts.isoformat())
            row = s.get(DerivativesHistoryRow, rid)
            if row is None:
                s.add(DerivativesHistoryRow(id=rid, asset=asset.value, metric=metric,
                                            timestamp=ts, value=float(value), source=source))
            else:
                row.value = float(value)
                row.source = source
    return len(points)


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


# --- input identity -------------------------------------------------------

def series_fingerprint(asset: Asset) -> dict[str, list[Any]]:
    """Cheap identity of every stored series that feeds an analysis.

    Aggregates only. An analysis has to be recomputed when a series gains rows
    or advances its last timestamp, so ``count`` and ``max(timestamp)`` say
    everything the caller needs; loading the rows to find that out would cost
    more than the analysis the check protects.
    """
    from sqlalchemy import func

    out: dict[str, list[Any]] = {}
    with session_scope() as s:
        for timeframe, rows, last in s.execute(
            select(
                OHLCVRow.timeframe, func.count(OHLCVRow.id), func.max(OHLCVRow.timestamp)
            )
            .where(OHLCVRow.asset == asset.value)
            .group_by(OHLCVRow.timeframe)
        ).all():
            observed = _as_utc(last)
            out[f"ohlcv:{timeframe}"] = [
                int(rows), observed.isoformat() if observed else None
            ]
        for metric, rows, last in s.execute(
            select(
                DerivativesHistoryRow.metric,
                func.count(DerivativesHistoryRow.id),
                func.max(DerivativesHistoryRow.timestamp),
            )
            .where(DerivativesHistoryRow.asset == asset.value)
            .group_by(DerivativesHistoryRow.metric)
        ).all():
            observed = _as_utc(last)
            out[f"derivatives:{metric}"] = [
                int(rows), observed.isoformat() if observed else None
            ]
        for metric, rows, last in s.execute(
            select(
                MacroSeriesRow.metric,
                func.count(MacroSeriesRow.id),
                func.max(MacroSeriesRow.timestamp),
            ).group_by(MacroSeriesRow.metric)
        ).all():
            observed = _as_utc(last)
            out[f"macro:{metric}"] = [
                int(rows), observed.isoformat() if observed else None
            ]
    return out

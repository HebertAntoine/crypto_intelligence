"""ALFRED - macro series as they were known at the time.

FRED serves the CURRENT value of every series. CPI, PCE, payrolls and GDP are
all revised after publication, so a FRED download gives numbers nobody had on
the day. Backtesting on them is a quiet, systematic look-ahead.

ALFRED (ArchivaL FRED) serves vintages: the value as it stood on a given real-
time date. Same API, same free key, plus `realtime_start` / `realtime_end`.

Two things this module provides:
  * first-print values (what was actually published), and
  * full revision history, so a study can see how much a number moved.

Without FRED_API_KEY it reports NOT_CONFIGURED and the affected series stay
marked NOT_POINT_IN_TIME - excluded from any study that needs as-of data rather
than silently approximated.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

from ...core.pointintime import Availability
from ...logging_setup import get_logger
from ...settings import get_settings
from ..http import get_http

log = get_logger("providers.alfred")

BASE_URL = "https://api.stlouisfed.org/fred"

# Series where the first print differs from the current value. Priority order
# follows the brief.
VINTAGE_SERIES: dict[str, tuple[str, str, bool]] = {
    # series_id: (metric, label, is_revised)
    "DFF": ("macro.fed_funds_rate", "Effective Federal Funds Rate", False),
    "CPIAUCSL": ("macro.cpi", "CPI All Urban Consumers", True),
    "CPILFESL": ("macro.core_cpi", "Core CPI", True),
    "PCEPI": ("macro.pce", "PCE Price Index", True),
    "PCEPILFE": ("macro.core_pce", "Core PCE Price Index", True),
    "UNRATE": ("macro.unemployment", "Unemployment Rate", True),
    "PAYEMS": ("macro.nonfarm_payrolls", "Nonfarm Payrolls", True),
    "GDPC1": ("macro.gdp", "Real GDP", True),
    "DGS2": ("macro.us2y", "US 2Y Treasury Yield", False),
    "DGS10": ("macro.us10y", "US 10Y Treasury Yield", False),
}


def _row_id(metric: str, observation: datetime, vintage: datetime) -> str:
    raw = f"{metric}|{observation.date()}|{vintage.date()}"
    return hashlib.sha1(raw.encode()).hexdigest()[:32]


async def fetch_vintages(
    series_id: str, start: str = "2015-01-01", max_vintages: int = 400
) -> dict[str, Any]:
    """Every vintage of one series.

    `realtime_start`/`realtime_end` spanning the full range makes FRED return
    one row per (observation, vintage) pair rather than only current values.
    """
    settings = get_settings()
    if not settings.fred_api_key.strip():
        return {
            "series_id": series_id,
            "available": False,
            "reason": (
                "UNAVAILABLE - FRED_API_KEY not set. ALFRED uses the same free key as "
                "FRED: https://fredaccount.stlouisfed.org/apikeys"
            ),
        }

    res = await get_http().get_json(
        f"{BASE_URL}/series/observations",
        provider="alfred",
        params={
            "series_id": series_id,
            "api_key": settings.fred_api_key,
            "file_type": "json",
            "observation_start": start,
            # A wide real-time window is what turns FRED into ALFRED.
            "realtime_start": start,
            "realtime_end": "9999-12-31",
            "output_type": "2",   # all vintages, one row per observation/vintage
        },
        cache_ttl=86400,
        rate_limit_per_min=40,
        retries=2,
    )

    if not res.ok:
        return {"series_id": series_id, "available": False, "reason": res.message[:200]}

    observations = (res.data or {}).get("observations") or []
    if not observations:
        return {
            "series_id": series_id, "available": False,
            "reason": "Source returned no observations",
        }

    return {
        "series_id": series_id,
        "available": True,
        "observations": observations[:max_vintages * 40],
        "count": len(observations),
    }


def parse_vintages(series_id: str, observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Turn ALFRED rows into (observation, vintage, value) records.

    With `output_type=2` each row carries the observation date plus one column
    per vintage, named `VALUE_YYYYMMDD`.
    """
    metric, _label, _revised = VINTAGE_SERIES.get(series_id, (series_id, series_id, True))
    records: list[dict[str, Any]] = []

    for row in observations:
        date_raw = row.get("date")
        if not date_raw:
            continue
        try:
            observation_time = datetime.strptime(date_raw, "%Y-%m-%d").replace(tzinfo=UTC)
        except ValueError:
            continue

        vintages: list[tuple[datetime, float]] = []
        for key, raw in row.items():
            if not key.startswith("VALUE_") or raw in (None, ".", ""):
                continue
            try:
                vintage_date = datetime.strptime(key[6:], "%Y%m%d").replace(tzinfo=UTC)
                value = float(raw)
            except ValueError:
                continue
            vintages.append((vintage_date, value))

        if not vintages:
            continue

        vintages.sort(key=lambda kv: kv[0])
        for revision_number, (vintage_date, value) in enumerate(vintages):
            records.append({
                "metric": metric,
                "series_id": series_id,
                "observation_time": observation_time,
                "vintage_date": vintage_date,
                "value": value,
                "is_first_print": revision_number == 0,
                "revision_number": revision_number,
            })

    return records


def save_vintages(records: list[dict[str, Any]]) -> int:
    from ...db.base import MacroVintageRow
    from ...db.session import session_scope

    if not records:
        return 0

    written = 0
    with session_scope() as s:
        for record in records:
            rid = _row_id(record["metric"], record["observation_time"], record["vintage_date"])
            if s.get(MacroVintageRow, rid) is not None:
                continue
            s.add(MacroVintageRow(id=rid, **record))
            written += 1
    return written


async def backfill_vintages(series: list[str] | None = None) -> dict[str, Any]:
    """Fetch and store vintages for every configured series."""
    series = series or list(VINTAGE_SERIES)
    results: list[dict[str, Any]] = []
    total = 0

    for series_id in series:
        payload = await fetch_vintages(series_id)
        if not payload.get("available"):
            results.append({
                "series_id": series_id, "rows": 0,
                "error": payload.get("reason", "")[:150],
            })
            continue
        records = parse_vintages(series_id, payload["observations"])
        written = save_vintages(records)
        total += written
        results.append({
            "series_id": series_id,
            "metric": VINTAGE_SERIES.get(series_id, (series_id,))[0],
            "records_parsed": len(records),
            "rows_written": written,
            "observations": payload["count"],
        })
        log.info("vintages_stored", series=series_id, written=written)

    return {"total_rows": total, "series": results}


def value_as_of(metric: str, observation_time: datetime, as_of: datetime) -> dict[str, Any] | None:
    """The value for a period, as it was known on a given date.

    Returns the latest vintage published at or before `as_of` - exactly what a
    market participant would have seen.
    """
    from sqlalchemy import select

    from ...db.base import MacroVintageRow
    from ...db.session import session_scope

    with session_scope() as s:
        stmt = (
            select(MacroVintageRow)
            .where(
                MacroVintageRow.metric == metric,
                MacroVintageRow.observation_time == observation_time,
                MacroVintageRow.vintage_date <= as_of,
            )
            .order_by(MacroVintageRow.vintage_date.desc())
            .limit(1)
        )
        row = s.execute(stmt).scalar_one_or_none()
        if row is None:
            return None
        return {
            "metric": row.metric,
            "value": row.value,
            "observation_time": row.observation_time,
            "vintage_date": row.vintage_date,
            "is_first_print": row.is_first_print,
            "revision_number": row.revision_number,
        }


def first_print(metric: str, observation_time: datetime) -> dict[str, Any] | None:
    """The originally published value - what the market reacted to."""
    from sqlalchemy import select

    from ...db.base import MacroVintageRow
    from ...db.session import session_scope

    with session_scope() as s:
        row = s.execute(
            select(MacroVintageRow).where(
                MacroVintageRow.metric == metric,
                MacroVintageRow.observation_time == observation_time,
                MacroVintageRow.is_first_print.is_(True),
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        return {
            "metric": row.metric, "value": row.value,
            "observation_time": row.observation_time,
            "release_date": row.vintage_date,
        }


def revision_magnitude(metric: str, limit: int = 100) -> dict[str, Any]:
    """How much this series typically moves between first print and latest.

    A large typical revision is the quantitative case for refusing to backtest
    on current values.
    """
    from sqlalchemy import select

    from ...db.base import MacroVintageRow
    from ...db.session import session_scope

    with session_scope() as s:
        rows = s.execute(
            select(MacroVintageRow)
            .where(MacroVintageRow.metric == metric)
            .order_by(MacroVintageRow.observation_time.desc())
        ).scalars().all()

    if not rows:
        return {"metric": metric, "available": False, "reason": "No vintages stored"}

    by_observation: dict[datetime, list[Any]] = {}
    for row in rows:
        by_observation.setdefault(row.observation_time, []).append(row)

    revisions: list[float] = []
    for versions in list(by_observation.values())[:limit]:
        versions.sort(key=lambda r: r.vintage_date)
        if len(versions) < 2:
            continue
        first, latest = versions[0].value, versions[-1].value
        if first:
            revisions.append(abs(latest - first) / abs(first) * 100.0)

    if not revisions:
        return {
            "metric": metric, "available": False,
            "reason": "No observation has more than one vintage",
        }

    import numpy as np

    return {
        "metric": metric,
        "available": True,
        "observations_with_revisions": len(revisions),
        "mean_revision_pct": round(float(np.mean(revisions)), 4),
        "median_revision_pct": round(float(np.median(revisions)), 4),
        "max_revision_pct": round(float(np.max(revisions)), 4),
        "interpretation": (
            f"{metric} moves a median of {np.median(revisions):.3f}% between its first "
            "print and its latest value. Backtesting on the current series uses numbers "
            "that did not exist at the time."
        ),
    }


def availability_for(metric: str) -> Availability:
    """Whether vintages exist for this metric in the local store."""
    from sqlalchemy import select

    from ...db.base import MacroVintageRow
    from ...db.session import session_scope

    with session_scope() as s:
        found = s.execute(
            select(MacroVintageRow.id).where(MacroVintageRow.metric == metric).limit(1)
        ).first()
    if found:
        return Availability.VINTAGE_AVAILABLE
    from ...core.pointintime import classify_metric

    return classify_metric(metric)


def status() -> dict[str, Any]:
    """What the vintage store currently holds - shown on the Sources page."""
    from sqlalchemy import func, select

    from ...db.base import MacroVintageRow
    from ...db.session import session_scope

    settings = get_settings()
    with session_scope() as s:
        rows = s.execute(
            select(
                MacroVintageRow.metric,
                func.count(MacroVintageRow.id),
                func.min(MacroVintageRow.observation_time),
                func.max(MacroVintageRow.observation_time),
            ).group_by(MacroVintageRow.metric)
        ).all()

    return {
        "configured": bool(settings.fred_api_key.strip()),
        "reason": (
            None if settings.fred_api_key.strip()
            else "UNAVAILABLE - FRED_API_KEY not set (free key, same one as FRED)"
        ),
        "series_configured": len(VINTAGE_SERIES),
        "series_stored": len(rows),
        "metrics": [
            {
                "metric": metric, "vintages": count,
                "earliest": earliest.isoformat() if earliest else None,
                "latest": latest.isoformat() if latest else None,
            }
            for metric, count, earliest, latest in rows
        ],
        "note": (
            "Series without stored vintages remain classified NOT_POINT_IN_TIME and are "
            "excluded from studies requiring as-of-date information."
        ),
    }

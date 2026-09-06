"""MacroSurpriseEngine - the gap between the print and what was expected.

A CPI of 3.2% is not information on its own. A CPI of 3.2% when 2.9% was
expected is. Markets price the consensus in advance; only the deviation is new.

Consensus is the hard part. There is no free, reliable, historical consensus
feed, so this engine:
  * reads consensus from a user-supplied CSV (data/imports/macro_consensus/);
  * computes surprises only where a consensus genuinely exists;
  * reports NO_CONSENSUS elsewhere.

It never estimates a consensus from the previous value or from a model. A
fabricated consensus would produce fabricated surprises, and every downstream
study would inherit the fiction.
"""

from __future__ import annotations

import csv
import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ..core.enums import Asset
from ..logging_setup import get_logger
from ..settings import get_settings

log = get_logger("research.macro_surprise")

# Reaction windows. Intraday matters: most of the move happens in minutes.
INTRADAY_WINDOWS = ["15m", "1h", "4h", "24h", "3d", "7d"]

CSV_COLUMNS = {"release_time", "metric", "actual", "consensus"}


def _release_id(metric: str, release_time: datetime) -> str:
    raw = f"{metric}|{release_time.isoformat()}"
    return hashlib.sha1(raw.encode()).hexdigest()[:32]


def import_consensus_csv(path: Path) -> tuple[int, list[str]]:
    """Load actual/consensus/previous from a user-supplied file.

    Expected columns: release_time, metric, actual, consensus[, previous, unit]
    """
    from ..db.base import MacroReleaseRow
    from ..db.session import session_scope

    errors: list[str] = []
    if not path.exists():
        return 0, [f"File not found: {path}"]

    rows: list[dict[str, Any]] = []
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames:
            return 0, [f"{path.name}: empty CSV"]
        columns = {c.strip().lower(): c for c in reader.fieldnames}
        missing = CSV_COLUMNS - columns.keys()
        if missing:
            return 0, [f"{path.name}: missing columns {sorted(missing)}"]

        for line, raw in enumerate(reader, start=2):
            release_time = _parse_time(raw[columns["release_time"]])
            if release_time is None:
                errors.append(f"{path.name}:{line} unparsable release_time")
                continue
            metric = raw[columns["metric"]].strip()
            actual = _parse_float(raw[columns["actual"]])
            consensus = _parse_float(raw[columns["consensus"]])
            previous = (
                _parse_float(raw[columns["previous"]]) if "previous" in columns else None
            )
            rows.append({
                "metric": metric,
                "event_name": raw.get(columns.get("event_name", ""), "") or metric,
                "observation_period": (
                    raw.get(columns.get("observation_period", ""), "") or ""
                ),
                "release_time": release_time,
                "actual": actual,
                "consensus": consensus,
                "previous": previous,
                "unit": raw.get(columns.get("unit", ""), "") or "",
                "source": f"csv:{path.name}",
            })

    written = 0
    with session_scope() as s:
        for row in rows:
            rid = _release_id(row["metric"], row["release_time"])
            existing = s.get(MacroReleaseRow, rid)
            surprise = None
            if row["actual"] is not None and row["consensus"] is not None:
                surprise = row["actual"] - row["consensus"]

            if existing is not None:
                existing.actual = row["actual"]
                existing.consensus = row["consensus"]
                existing.previous = row["previous"]
                existing.surprise = surprise
                continue
            s.add(MacroReleaseRow(id=rid, surprise=surprise, **row))
            written += 1

    return written, errors


def _parse_time(raw: str) -> datetime | None:
    raw = raw.strip().replace("Z", "")
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def _parse_float(raw: str | None) -> float | None:
    """Blank is missing, never zero - a zero consensus is a real number."""
    if raw is None:
        return None
    s = str(raw).strip().replace(",", "").replace("%", "")
    if s in ("", "-", "N/A", "n/a", "null"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def import_directory(directory: Path | None = None) -> dict[str, Any]:
    root = directory or (get_settings().data_dir / "imports" / "macro_consensus")
    if not root.exists():
        return {"status": "error", "reason": f"Directory missing: {root}", "rows": 0}

    total, errors, files = 0, [], []
    for path in sorted(root.glob("*.csv")):
        rows, file_errors = import_consensus_csv(path)
        total += rows
        errors.extend(file_errors)
        files.append({"file": path.name, "rows": rows})
    return {"status": "ok", "rows": total, "files": files, "errors": errors}


def compute_surprise_zscores(metric: str, lookback: int = 40) -> int:
    """Normalise surprises by the trailing dispersion of surprises.

    A 0.1pp CPI miss and a 50k payrolls miss are not comparable in raw units.
    The trailing window keeps the normalisation free of look-ahead.
    """
    from sqlalchemy import select

    from ..db.base import MacroReleaseRow
    from ..db.session import session_scope

    with session_scope() as s:
        rows = s.execute(
            select(MacroReleaseRow)
            .where(MacroReleaseRow.metric == metric)
            .order_by(MacroReleaseRow.release_time.asc())
        ).scalars().all()

        surprises: list[float] = []
        updated = 0
        for row in rows:
            if row.surprise is None:
                surprises.append(np.nan)
                continue
            window = [s_ for s_ in surprises[-lookback:] if s_ == s_]
            if len(window) >= 8:
                std = float(np.std(window, ddof=1))
                if std > 0:
                    row.surprise_zscore = round(
                        (row.surprise - float(np.mean(window))) / std, 4
                    )
                    updated += 1
            surprises.append(row.surprise)
    return updated


def load_releases(metric: str | None = None) -> list[dict[str, Any]]:
    from sqlalchemy import select

    from ..db.base import MacroReleaseRow
    from ..db.session import session_scope

    with session_scope() as s:
        stmt = select(MacroReleaseRow).order_by(MacroReleaseRow.release_time.asc())
        if metric:
            stmt = stmt.where(MacroReleaseRow.metric == metric)
        rows = s.execute(stmt).scalars().all()
        return [
            {
                "metric": r.metric, "event_name": r.event_name,
                "release_time": r.release_time if r.release_time.tzinfo
                else r.release_time.replace(tzinfo=UTC),
                "actual": r.actual, "consensus": r.consensus, "previous": r.previous,
                "surprise": r.surprise, "surprise_zscore": r.surprise_zscore,
                "source": r.source,
            }
            for r in rows
        ]


def analyse_surprise_reaction(
    metric: str, assets: list[Asset] | None = None, min_sample: int = 10
) -> dict[str, Any]:
    """How BTC/ETH/SOL moved after positive vs negative surprises.

    Reactions are measured from the closest bar at or before the release, so
    the entry point is one a participant could actually have used.
    """
    from ..core.enums import Timeframe
    from ..history import store
    from .stats import describe_returns

    assets = assets or Asset.tradables()
    releases = [r for r in load_releases(metric) if r["surprise"] is not None]

    if not releases:
        return {
            "metric": metric, "available": False,
            "reason": (
                f"NO_CONSENSUS - no release with both actual and consensus for {metric}. "
                "Import a consensus CSV into data/imports/macro_consensus/. "
                "Consensus is never estimated."
            ),
        }
    if len(releases) < min_sample:
        return {
            "metric": metric, "available": False,
            "reason": f"INSUFFICIENT_DATA - {len(releases)} releases with a consensus",
            "releases": len(releases),
        }

    results: dict[str, Any] = {}
    for asset in assets:
        hourly = store.load_candles(asset, Timeframe.H1)
        if hourly.empty:
            results[asset.value] = {
                "available": False,
                "reason": "UNAVAILABLE - no hourly candles; run `make backfill`",
            }
            continue

        positive: dict[str, list[float]] = {w: [] for w in INTRADAY_WINDOWS}
        negative: dict[str, list[float]] = {w: [] for w in INTRADAY_WINDOWS}

        for release in releases:
            reaction = _measure_reaction(hourly, release["release_time"])
            if not reaction:
                continue
            bucket = positive if release["surprise"] > 0 else negative
            for window, value in reaction.items():
                if value is not None:
                    bucket[window].append(value)

        results[asset.value] = {
            "available": True,
            "positive_surprise": {
                w: describe_returns(v).to_dict() for w, v in positive.items() if v
            },
            "negative_surprise": {
                w: describe_returns(v).to_dict() for w, v in negative.items() if v
            },
            "n_positive": len(positive["24h"]),
            "n_negative": len(negative["24h"]),
        }

    return {
        "metric": metric,
        "available": True,
        "releases": len(releases),
        "period": {
            "start": releases[0]["release_time"].isoformat(),
            "end": releases[-1]["release_time"].isoformat(),
        },
        "assets": results,
        "note": (
            "Reactions measured from the last hourly close at or before the release. "
            "Hourly granularity cannot resolve the 15-minute window; that column is "
            "reported only when finer data exists."
        ),
    }


def _measure_reaction(candles: pd.DataFrame, release_time: datetime) -> dict[str, float | None]:
    """Forward returns from the bar preceding a release."""
    before = candles[candles.index <= release_time]
    if before.empty:
        return {}
    entry_price = float(before["close"].iloc[-1])
    entry_time = before.index[-1]
    if entry_price <= 0:
        return {}

    offsets = {
        "15m": pd.Timedelta(minutes=15), "1h": pd.Timedelta(hours=1),
        "4h": pd.Timedelta(hours=4), "24h": pd.Timedelta(hours=24),
        "3d": pd.Timedelta(days=3), "7d": pd.Timedelta(days=7),
    }

    out: dict[str, float | None] = {}
    for window, offset in offsets.items():
        target = entry_time + offset
        after = candles[candles.index >= target]
        if after.empty:
            out[window] = None
            continue
        # Hourly bars cannot resolve a 15-minute window; report it as missing
        # rather than pretending the hourly close is a 15-minute reaction.
        if window == "15m":
            out[window] = None
            continue
        out[window] = (float(after["close"].iloc[0]) - entry_price) / entry_price * 100.0
    return out


def status() -> dict[str, Any]:
    """What consensus data exists - and what is missing."""
    releases = load_releases()
    with_consensus = [r for r in releases if r["consensus"] is not None]
    by_metric: dict[str, dict[str, int]] = {}
    for r in releases:
        entry = by_metric.setdefault(r["metric"], {"total": 0, "with_consensus": 0})
        entry["total"] += 1
        if r["consensus"] is not None:
            entry["with_consensus"] += 1

    return {
        "releases": len(releases),
        "with_consensus": len(with_consensus),
        "by_metric": by_metric,
        "available": bool(with_consensus),
        "reason": (
            None if with_consensus else
            "NO_CONSENSUS - no historical consensus imported. There is no reliable free "
            "source, so surprises cannot be computed. Import a CSV into "
            "data/imports/macro_consensus/ (see docs/data-imports.md). "
            "Consensus is never estimated from the previous value."
        ),
    }

"""Open-interest history from manually imported CSV files.

Binance publishes roughly 30 days of open-interest history through
`openInterestHist`. That is a hard limit of the source, not something to work
around: paginating further returns nothing, and no free alternative in this
project's provider set goes deeper.

So deeper history has to be imported. This module reads CSVs the user supplies -
exported from a data vendor they have legitimate access to - and merges them
into the same `derivatives_history` table the live provider writes to, so every
study reads one series regardless of origin.

No provider limitation is circumvented. `import_source` records where each row
came from, so a study can tell vendor data from Binance data.
"""

from __future__ import annotations

import csv
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ...core.enums import Asset
from ...history import store
from ...logging_setup import get_logger
from ...settings import get_settings

log = get_logger("providers.oi_import")

_DATE_FORMATS = (
    "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S",
    "%d/%m/%Y", "%m/%d/%Y",
)

EXPECTED_COLUMNS = {"date", "asset", "open_interest_usd"}


def parse_date(raw: str) -> datetime | None:
    raw = raw.strip().replace("Z", "")
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    try:
        # Epoch seconds or milliseconds.
        value = float(raw)
        if value > 1e11:
            value /= 1000.0
        return datetime.fromtimestamp(value, tz=UTC)
    except (ValueError, OSError, OverflowError):
        return None


def parse_value(raw: str) -> float | None:
    """Blank means missing, never zero - a zero open interest is not a gap."""
    s = raw.strip().replace(",", "").replace("$", "").replace(" ", "")
    if s in ("", "-", "N/A", "n/a", "null", "None"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def import_csv_file(path: Path) -> tuple[int, list[str]]:
    """Import one CSV. Returns (rows_written, errors)."""
    errors: list[str] = []
    if not path.exists():
        return 0, [f"File not found: {path}"]

    by_asset: dict[Asset, list[tuple[datetime, float]]] = {}

    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames:
            return 0, [f"{path.name}: empty or headerless CSV"]

        columns = {c.strip().lower(): c for c in reader.fieldnames}
        missing = EXPECTED_COLUMNS - columns.keys()
        if missing:
            return 0, [
                f"{path.name}: missing column(s) {sorted(missing)}. "
                f"Expected {sorted(EXPECTED_COLUMNS)}"
            ]

        for line, row in enumerate(reader, start=2):
            timestamp = parse_date(row[columns["date"]])
            value = parse_value(row[columns["open_interest_usd"]])
            symbol = row[columns["asset"]].strip().upper()

            if timestamp is None:
                errors.append(f"{path.name}:{line} unparsable date {row[columns['date']]!r}")
                continue
            if value is None:
                continue     # a blank cell is missing data, not a zero
            try:
                asset = Asset(symbol)
            except ValueError:
                errors.append(f"{path.name}:{line} unknown asset {symbol!r}")
                continue
            by_asset.setdefault(asset, []).append((timestamp, value))

    written = 0
    for asset, points in by_asset.items():
        written += store.save_derivatives(
            asset, "oi.value", points, source=f"csv:{path.name}"
        )
        log.info("oi_imported", asset=asset.value, rows=len(points), file=path.name)

    return written, errors


def import_directory(directory: Path | None = None) -> dict[str, Any]:
    """Import every CSV in data/imports/open_interest/."""
    root = directory or (get_settings().data_dir / "imports" / "open_interest")
    if not root.exists():
        return {
            "status": "error",
            "reason": f"Import directory missing: {root}",
            "rows": 0,
        }

    total = 0
    errors: list[str] = []
    files: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.csv")):
        rows, file_errors = import_csv_file(path)
        total += rows
        errors.extend(file_errors)
        files.append({"file": path.name, "rows": rows, "errors": len(file_errors)})

    coverage = {
        asset.value: store.derivatives_coverage(asset).get("oi.value", {})
        for asset in Asset.tradables()
    }

    return {
        "status": "ok",
        "rows": total,
        "files": files,
        "errors": errors,
        "coverage_after_import": coverage,
    }


FORMAT_DOC = """\
# Open interest CSV import

Binance publishes roughly 30 days of open-interest history, which is not enough
for the event studies and interaction analysis in this project. Deeper history
has to come from a vendor you have legitimate access to.

Place CSV files in `data/imports/open_interest/` and run:

    make import-oi

## Expected format

    date,asset,open_interest_usd
    2024-01-15,BTC,18420000000
    2024-01-16,BTC,18755000000
    2024-01-15,ETH,7210000000

* `date` - YYYY-MM-DD, ISO timestamp, or epoch seconds/milliseconds
* `asset` - BTC, ETH or SOL
* `open_interest_usd` - notional open interest in USD

A blank value is treated as missing data, never as zero. Rows are upserted by
(asset, metric, timestamp), so re-importing the same file corrects rather than
duplicates.

## Provenance

Imported rows carry `source = "csv:<filename>"`, while live rows carry
`source = "binance_futures"`. Studies can therefore distinguish vendor data
from exchange data.

## What this does not do

It does not circumvent any provider limitation. Binance's 30-day window is
respected as published; this path exists so you can supply history you already
have the right to use.
"""

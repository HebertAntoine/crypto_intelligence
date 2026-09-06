"""ETF flows from manually imported CSV files.

This is the RELIABLE path for ETF data, because the reference site blocks
automated access and we do not bypass such protection.

Expected format (data/imports/etf/*.csv):

    date,asset,ticker,flow_musd
    2026-09-03,BTC,IBIT,412.5
    2026-09-03,BTC,GBTC,-96.4

Values are net flows in millions of USD. Negative means outflow.
"""

from __future__ import annotations

import csv
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ...core.enums import Asset, DataQuality, FetchStatus, ProviderCategory
from ...core.freshness import compute_freshness
from ...core.models import Observation
from ...db import repo
from ...settings import get_settings
from ..base import BaseProvider, FetchRequest, FetchResult, ProviderStatus

_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d %b %Y", "%d-%b-%Y")


def parse_date(raw: str) -> datetime | None:
    raw = raw.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def parse_flow(raw: str) -> float | None:
    """Handle the formats these tables actually use: 1,234.5 / (96.4) / -96.4.

    Returns None for blanks - a missing cell is missing data, never 0.0.
    """
    s = raw.strip().replace(",", "").replace("$", "")
    if s in ("", "-", "N/A", "n/a", "—"):
        return None
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    try:
        return float(s)
    except ValueError:
        return None


def import_csv_file(path: Path) -> tuple[int, list[str]]:
    """Import one CSV into the database. Returns (rows_imported, errors)."""
    errors: list[str] = []
    if not path.exists():
        return 0, [f"File not found: {path}"]

    rows: list[dict[str, Any]] = []
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames:
            return 0, [f"{path.name}: empty or headerless CSV"]
        cols = {c.strip().lower(): c for c in reader.fieldnames}
        required = {"date", "asset", "ticker", "flow_musd"}
        missing = required - cols.keys()
        if missing:
            return 0, [f"{path.name}: missing columns {sorted(missing)}. Expected {sorted(required)}"]

        for i, row in enumerate(reader, start=2):
            date = parse_date(row[cols["date"]])
            flow = parse_flow(row[cols["flow_musd"]])
            asset_raw = row[cols["asset"]].strip().upper()
            ticker = row[cols["ticker"]].strip().upper()
            if date is None:
                errors.append(f"{path.name}:{i} unparsable date {row[cols['date']]!r}")
                continue
            if flow is None:
                continue  # blank cell = no data for that fund that day
            if asset_raw not in ("BTC", "ETH", "SOL"):
                errors.append(f"{path.name}:{i} unknown asset {asset_raw!r}")
                continue
            if not ticker:
                continue
            rows.append({
                "date": date, "asset": asset_raw, "ticker": ticker,
                "flow_musd": flow, "import_source": f"csv:{path.name}",
            })

    return repo.save_etf_flows(rows), errors


def import_directory(directory: Path | None = None) -> tuple[int, list[str]]:
    d = directory or get_settings().etf_import_dir
    if not d.exists():
        return 0, [f"Import directory missing: {d}"]
    total, errors = 0, []
    for csv_path in sorted(d.glob("*.csv")):
        n, errs = import_csv_file(csv_path)
        total += n
        errors.extend(errs)
    return total, errors


class ETFCSVProvider(BaseProvider):
    """Serves ETF flows already imported into the database."""

    name = "etf_csv"
    source = "Manual CSV import"
    category = ProviderCategory.ETF
    capabilities = ("etf.flows",)
    source_url = "local://data/imports/etf"
    base_confidence = 95.0     # the user vouched for these numbers themselves

    async def available(self) -> ProviderStatus:
        return ProviderStatus(name=self.name, available=True)

    async def fetch(self, request: FetchRequest) -> FetchResult:
        if request.asset is None:
            return FetchResult.failure(FetchStatus.NO_DATA, self.name, "asset required")

        # Pick up any newly dropped CSV without a separate command.
        import_directory()

        days = int(request.params.get("days", 120))
        flows = repo.get_etf_flows(request.asset, days=days)
        if not flows:
            return FetchResult.failure(
                FetchStatus.NO_DATA,
                self.name,
                (
                    f"UNAVAILABLE - no ETF flow data imported for {request.asset.value}. "
                    "Add a CSV to data/imports/etf/ then run `make import-etf`."
                ),
            )

        prov = self.provenance()
        out = [
            Observation(
                asset=request.asset, metric="etf.flow", value=float(f["flow_musd"]),
                unit="USD_M", timestamp=f["date"], provenance=prov,
                freshness=compute_freshness(f["date"], "etf"),
                confidence=self.base_confidence, quality=DataQuality.MEASURED,
                meta={"ticker": f["ticker"], "import_source": f["import_source"]},
            )
            for f in flows
        ]
        return FetchResult.success(out, self.name, raw=flows)


def asset_from_str(value: str) -> Asset | None:
    try:
        return Asset(value.upper())
    except ValueError:
        return None

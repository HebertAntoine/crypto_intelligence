"""US macro and liquidity series from the primary official sources, no key.

FRED republishes these series but its API needs a key and its public CSV is not
reachable from this server. Every series below comes from the institution that
produces it:

    U.S. Treasury   daily par yield curve (2Y, 10Y, 30Y) and real yield curve
    U.S. Treasury   Daily Treasury Statement - Treasury General Account balance
    New York Fed    effective fed funds rate (EFFR) and reverse repo (RRP)
    Federal Reserve H.4.1 - total assets of the Reserve Banks (WALCL)
    BLS             CPI, core CPI, unemployment, payrolls, hourly earnings

Each point carries two times: ``timestamp`` is the period the value describes;
``meta["available_at"]`` is when it became public. A study reading this data as
of a date must use the second - a CPI for August is not knowable in August.
"""

from __future__ import annotations

import csv
import io
import re
from datetime import UTC, date, datetime, timedelta
from typing import Any, ClassVar

from bs4 import BeautifulSoup

from ...core.enums import DataQuality, FetchStatus, ProviderCategory
from ...core.freshness import compute_freshness
from ...core.models import Observation
from ..base import BaseProvider, FetchRequest, FetchResult
from ..http import get_http

TREASURY_CURVE_URL = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
    "daily-treasury-rates.csv/{year}/all?type={kind}&field_tdr_date_value={year}"
    "&page&_format=csv"
)
TGA_URL = (
    "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/"
    "accounting/dts/operating_cash_balance"
)
NYFED_RRP_URL = "https://markets.newyorkfed.org/api/rp/reverserepo/propositions/search.json"
NYFED_EFFR_URL = "https://markets.newyorkfed.org/api/rates/unsecured/effr/last/{n}.json"
H41_URL = "https://www.federalreserve.gov/releases/h41/current/"
BLS_URL = "https://api.bls.gov/publicAPI/v1/timeseries/data/{series}"

#: BLS series id -> (metric, unit, label). Seasonally adjusted where the BLS
#: publishes both, because month-on-month changes are what the reading uses.
BLS_SERIES: dict[str, tuple[str, str, str]] = {
    "CUSR0000SA0": ("macro.cpi", "index", "CPI (toutes composantes, CVS)"),
    "CUSR0000SA0L1E": ("macro.core_cpi", "index", "CPI sous-jacent (hors énergie et alimentation)"),
    "LNS14000000": ("macro.unemployment", "pct", "Taux de chômage"),
    "CES0000000001": ("macro.nonfarm_payrolls", "thousands", "Emplois non agricoles"),
    "CES0500000003": ("macro.avg_hourly_earnings", "usd", "Salaire horaire moyen"),
}

#: When each release becomes public, relative to the period it describes.
#: Conservative: a study must never see a value earlier than it existed.
RELEASE_DELAY: dict[str, timedelta] = {
    "macro.us2y": timedelta(hours=22),  # curve published after the close
    "macro.us10y": timedelta(hours=22),
    "macro.us30y": timedelta(hours=22),
    "macro.real10y": timedelta(hours=22),
    "macro.yield_curve_10y2y": timedelta(hours=22),
    "liquidity.tga": timedelta(days=1, hours=21),  # DTS: next business day, 4 pm ET
    "liquidity.rrp": timedelta(hours=18),  # operation results, early afternoon ET
    "macro.fed_funds_rate": timedelta(days=1, hours=14),  # EFFR: next day, 9 am ET
    "liquidity.fed_total_assets": timedelta(days=1, hours=21),  # H.4.1: Thursday 4:30 pm ET
    # Monthly releases: the month's first day plus the typical publication lag.
    "macro.cpi": timedelta(days=45),
    "macro.core_cpi": timedelta(days=45),
    "macro.unemployment": timedelta(days=38),
    "macro.nonfarm_payrolls": timedelta(days=38),
    "macro.avg_hourly_earnings": timedelta(days=38),
}


def _available_at(metric: str, observed: datetime) -> datetime:
    return observed + RELEASE_DELAY.get(metric, timedelta(days=1))


def _day(value: str, fmt: str) -> datetime:
    return datetime.strptime(value.strip(), fmt).replace(tzinfo=UTC)


def _observation(
    provider: BaseProvider,
    *,
    metric: str,
    value: float,
    unit: str,
    observed: datetime,
    url: str,
    label: str,
    extra: dict[str, Any] | None = None,
) -> Observation:
    available = _available_at(metric, observed)
    return Observation(
        metric=metric,
        value=value,
        unit=unit,
        timestamp=observed,
        provenance=provider.provenance(url),
        freshness=compute_freshness(available, "macro"),
        confidence=provider.base_confidence,
        quality=DataQuality.MEASURED,
        meta={
            "label": label,
            "available_at": available.isoformat(),
            "source_tier": "OFFICIAL",
            **(extra or {}),
        },
    )


# ---------------------------------------------------------------------------
# Pure parsers - fed real responses in the tests
# ---------------------------------------------------------------------------


def parse_treasury_curve(text: str, columns: dict[str, str]) -> list[tuple[str, datetime, float]]:
    """Rows of the Treasury CSV as (metric, day, value) for the wanted columns."""

    out: list[tuple[str, datetime, float]] = []
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        raw_day = row.get("Date") or ""
        if not raw_day:
            continue
        try:
            day = _day(raw_day, "%m/%d/%Y")
        except ValueError:
            continue
        for column, metric in columns.items():
            raw = (row.get(column) or "").strip()
            if not raw or raw.upper() == "N/A":
                continue
            try:
                out.append((metric, day, float(raw)))
            except ValueError:
                continue
    return out


def parse_tga(payload: dict[str, Any]) -> list[tuple[datetime, float]]:
    """Closing TGA balance per day, in millions of dollars.

    Two formats. Until April 2022: a "Federal Reserve Account" line with the
    closing balance in ``close_today_bal``. Since then the statement reports the
    closing balance under
    ``open_today_bal`` on the "Closing Balance" line; ``close_today_bal`` is
    null. The field name is the Treasury's, not a mistake here.
    """

    out: list[tuple[datetime, float]] = []
    for row in payload.get("data") or []:
        account = str(row.get("account_type", ""))
        if "Closing Balance" in account:
            raw = row.get("open_today_bal")
            if raw in (None, "null", ""):
                raw = row.get("close_today_bal")
        elif account == "Federal Reserve Account":
            # Before April 2022 the statement had one line per account, with
            # the closing balance in its own field.
            raw = row.get("close_today_bal")
        else:
            continue
        try:
            out.append((_day(row["record_date"], "%Y-%m-%d"), float(raw)))
        except (KeyError, TypeError, ValueError):
            continue
    return out


def parse_rrp(payload: dict[str, Any]) -> list[tuple[datetime, float]]:
    """Overnight reverse repo accepted per operation day, in dollars."""

    out: dict[datetime, float] = {}
    for op in (payload.get("repo") or {}).get("operations") or []:
        if str(op.get("operationType", "")).lower() != "reverse repo":
            continue
        try:
            day = _day(op["operationDate"], "%Y-%m-%d")
            out[day] = out.get(day, 0.0) + float(op["totalAmtAccepted"])
        except (KeyError, TypeError, ValueError):
            continue
    return sorted(out.items())


def parse_effr(payload: dict[str, Any]) -> list[tuple[datetime, float]]:
    out: list[tuple[datetime, float]] = []
    for row in payload.get("refRates") or []:
        if row.get("type") != "EFFR":
            continue
        try:
            out.append((_day(row["effectiveDate"], "%Y-%m-%d"), float(row["percentRate"])))
        except (KeyError, TypeError, ValueError):
            continue
    return sorted(out)


_H41_DAY = re.compile(r"\b([A-Z][a-z]{2}) (\d{1,2}), (20\d{2})\b")


def parse_h41(html: str) -> dict[str, Any] | None:
    """Total assets of the Reserve Banks, the Wednesday level and its changes.

    Values are millions of dollars. The first abbreviated date in the tables is
    the Wednesday the level describes; the release itself comes on Thursday.
    """

    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    match = _H41_DAY.search(text)
    if match is None:
        return None
    try:
        level_day = datetime.strptime(" ".join(match.groups()), "%b %d %Y").replace(tzinfo=UTC)
    except ValueError:
        return None
    for tr in soup.find_all("tr"):
        cells = [cell.get_text(" ", strip=True) for cell in tr.find_all(["th", "td"])]
        if not cells or not cells[0].startswith("Total assets"):
            continue
        numbers = [c for c in cells[1:] if re.fullmatch(r"[+-]?\s?[\d,]+", c)]
        if len(numbers) < 2:
            continue

        def as_float(raw: str) -> float:
            return float(raw.replace(",", "").replace(" ", ""))

        return {
            "day": level_day,
            "total_assets_musd": as_float(numbers[0]),
            "change_week_musd": as_float(numbers[1]),
            "change_year_musd": as_float(numbers[2]) if len(numbers) > 2 else None,
        }
    return None


def parse_bls(payload: dict[str, Any]) -> list[tuple[datetime, float]]:
    """Monthly BLS values as (first day of the month, value)."""

    out: list[tuple[datetime, float]] = []
    for series in (payload.get("Results") or {}).get("series") or []:
        for row in series.get("data") or []:
            period = str(row.get("period", ""))
            if not period.startswith("M") or period == "M13":
                continue
            try:
                month = date(int(row["year"]), int(period[1:]), 1)
                out.append(
                    (datetime(month.year, month.month, 1, tzinfo=UTC), float(row["value"]))
                )
            except (KeyError, TypeError, ValueError):
                continue
    return sorted(out)


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------


class _OfficialProvider(BaseProvider):
    category = ProviderCategory.MACRO
    base_confidence = 97.0


class TreasuryYieldsProvider(_OfficialProvider):
    name = "us_treasury_yields"
    source = "U.S. Department of the Treasury"
    capabilities = ("macro.rates",)
    source_url = "https://home.treasury.gov/resource-center/data-chart-center/interest-rates"

    NOMINAL: ClassVar[dict[str, str]] = {"2 Yr": "macro.us2y", "10 Yr": "macro.us10y", "30 Yr": "macro.us30y"}
    REAL: ClassVar[dict[str, str]] = {"10 YR": "macro.real10y"}
    LABELS: ClassVar[dict[str, tuple[str, str]]] = {
        "macro.us2y": ("pct", "Rendement du Trésor US à 2 ans"),
        "macro.us10y": ("pct", "Rendement du Trésor US à 10 ans"),
        "macro.us30y": ("pct", "Rendement du Trésor US à 30 ans"),
        "macro.real10y": ("pct", "Rendement réel du Trésor US à 10 ans (TIPS)"),
        "macro.yield_curve_10y2y": ("pct", "Pente de la courbe 10 ans - 2 ans"),
    }

    async def fetch(self, request: FetchRequest) -> FetchResult:
        http = get_http()
        year = datetime.now(UTC).year
        points: list[tuple[str, datetime, float]] = []
        for kind, columns in (
            ("daily_treasury_yield_curve", self.NOMINAL),
            ("daily_treasury_real_yield_curve", self.REAL),
        ):
            res = await http.get_text(
                TREASURY_CURVE_URL.format(year=year, kind=kind),
                provider=self.name, cache_ttl=3600, rate_limit_per_min=10,
            )
            if res.ok:
                points.extend(parse_treasury_curve(res.data, columns))
        if not points:
            return FetchResult.failure(FetchStatus.NO_DATA, self.name)

        by_day: dict[datetime, dict[str, float]] = {}
        for metric, day, value in points:
            by_day.setdefault(day, {})[metric] = value
        for day, values in by_day.items():
            if "macro.us10y" in values and "macro.us2y" in values:
                points.append(
                    ("macro.yield_curve_10y2y", day, values["macro.us10y"] - values["macro.us2y"])
                )
        out = [
            _observation(
                self, metric=metric, value=value, unit=self.LABELS[metric][0],
                observed=day, url=self.source_url, label=self.LABELS[metric][1],
            )
            for metric, day, value in points
        ]
        return FetchResult.success(out, self.name)


class TreasuryGeneralAccountProvider(_OfficialProvider):
    name = "us_treasury_tga"
    source = "U.S. Treasury - Daily Treasury Statement"
    capabilities = ("liquidity.tga",)
    source_url = "https://fiscaldata.treasury.gov/datasets/daily-treasury-statement/"

    async def fetch(self, request: FetchRequest) -> FetchResult:
        since = (datetime.now(UTC) - timedelta(days=75)).date().isoformat()
        res = await get_http().get_json(
            TGA_URL, provider=self.name,
            params={
                "filter": f"record_date:gte:{since}",
                "page[size]": "500",
                "sort": "record_date",
            },
            cache_ttl=3600, rate_limit_per_min=10,
        )
        if not res.ok:
            return FetchResult.failure(res.status, self.name, res.message)
        out = [
            _observation(
                self, metric="liquidity.tga", value=value, unit="musd", observed=day,
                url=self.source_url, label="Compte du Trésor à la Fed (TGA)",
            )
            for day, value in parse_tga(res.data or {})
        ]
        if not out:
            return FetchResult.failure(FetchStatus.NO_DATA, self.name)
        return FetchResult.success(out, self.name)


class NewYorkFedProvider(_OfficialProvider):
    name = "nyfed_markets"
    source = "Federal Reserve Bank of New York"
    capabilities = ("liquidity.rrp", "macro.effr")
    source_url = "https://markets.newyorkfed.org/"

    async def fetch(self, request: FetchRequest) -> FetchResult:
        http = get_http()
        since = (datetime.now(UTC) - timedelta(days=75)).date().isoformat()
        out: list[Observation] = []
        rrp = await http.get_json(
            NYFED_RRP_URL, provider=self.name, params={"startDate": since},
            cache_ttl=3600, rate_limit_per_min=10,
        )
        if rrp.ok:
            out.extend(
                _observation(
                    self, metric="liquidity.rrp", value=value / 1e6, unit="musd",
                    observed=day, url=self.source_url,
                    label="Prises en pension inversées de la Fed (RRP)",
                )
                for day, value in parse_rrp(rrp.data or {})
            )
        effr = await http.get_json(
            NYFED_EFFR_URL.format(n=60), provider=self.name,
            cache_ttl=3600, rate_limit_per_min=10,
        )
        if effr.ok:
            out.extend(
                _observation(
                    self, metric="macro.fed_funds_rate", value=value, unit="pct",
                    observed=day, url=self.source_url,
                    label="Taux effectif des fonds fédéraux (EFFR)",
                )
                for day, value in parse_effr(effr.data or {})
            )
        if not out:
            return FetchResult.failure(FetchStatus.NO_DATA, self.name)
        return FetchResult.success(out, self.name)


class FedBalanceSheetProvider(_OfficialProvider):
    name = "fed_h41"
    source = "Federal Reserve - H.4.1"
    capabilities = ("liquidity.fed_balance_sheet",)
    source_url = H41_URL

    async def fetch(self, request: FetchRequest) -> FetchResult:
        res = await get_http().get_text(
            H41_URL, provider=self.name, cache_ttl=6 * 3600, rate_limit_per_min=6,
        )
        if not res.ok:
            return FetchResult.failure(res.status, self.name, res.message)
        parsed = parse_h41(res.data or "")
        if parsed is None:
            return FetchResult.failure(FetchStatus.PARSE_ERROR, self.name, "Total assets introuvable")
        obs = _observation(
            self, metric="liquidity.fed_total_assets", value=parsed["total_assets_musd"],
            unit="musd", observed=parsed["day"], url=H41_URL,
            label="Actif total de la Fed (bilan, WALCL)",
            extra={
                "change_week_musd": parsed["change_week_musd"],
                "change_year_musd": parsed["change_year_musd"],
            },
        )
        return FetchResult.success([obs], self.name)


class BlsProvider(_OfficialProvider):
    name = "bls"
    source = "U.S. Bureau of Labor Statistics"
    capabilities = ("macro.inflation", "macro.employment")
    source_url = "https://www.bls.gov/"

    async def fetch(self, request: FetchRequest) -> FetchResult:
        http = get_http()
        out: list[Observation] = []
        for series_id, (metric, unit, label) in BLS_SERIES.items():
            # The keyless v1 API allows 25 requests a day; a 12 h cache keeps
            # two refreshes a day well inside it.
            res = await http.get_json(
                BLS_URL.format(series=series_id), provider=self.name,
                cache_ttl=12 * 3600, rate_limit_per_min=5,
            )
            if not res.ok or (res.data or {}).get("status") != "REQUEST_SUCCEEDED":
                continue
            out.extend(
                _observation(
                    self, metric=metric, value=value, unit=unit, observed=day,
                    url=f"https://data.bls.gov/timeseries/{series_id}", label=label,
                    extra={"series_id": series_id},
                )
                for day, value in parse_bls(res.data or {})
            )
        if not out:
            return FetchResult.failure(FetchStatus.NO_DATA, self.name)
        return FetchResult.success(out, self.name)

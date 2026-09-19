"""Policy rates of the Fed, the ECB and the Bank of Japan, from each bank.

    Fed   New York Fed markets API: the daily EFFR record carries the FOMC
          target range in force that day (``targetRateFrom`` / ``targetRateTo``).
    ECB   ECB Data Portal: deposit facility rate, the rate that steers euro
          money markets since 2019 (series FM.D.U2.EUR.4F.KR.DFR.LEV).
    BoJ   BoJ Time-Series Data Search API: the uncollateralised overnight call
          rate (the operating target) and the basic loan rate, which moves by
          decision and dates each change.

A decision is read from the series itself: the day the rate in force changed.
No expected rate is produced here. What the market prices for the next meeting
needs a pricing source (futures, OIS); none is connected, so the engine says
"anticipation indisponible" rather than guessing.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from itertools import pairwise
from typing import Any

from ...core.enums import DataQuality, FetchStatus, ProviderCategory
from ...core.freshness import compute_freshness
from ...core.models import Observation
from ..base import BaseProvider, FetchRequest, FetchResult
from ..http import get_http

NYFED_EFFR_SEARCH = "https://markets.newyorkfed.org/api/rates/unsecured/effr/search.json"
ECB_DFR_URL = "https://data-api.ecb.europa.eu/service/data/FM/D.U2.EUR.4F.KR.DFR.LEV"
BOJ_API = "https://www.stat-search.boj.or.jp/api/v1/getDataCode"

#: metric -> (label, publication delay after the day it describes)
CB_METRICS: dict[str, tuple[str, timedelta]] = {
    "cb.fed.target_upper": ("Fed - borne haute de la fourchette cible", timedelta(days=1, hours=14)),
    "cb.fed.target_lower": ("Fed - borne basse de la fourchette cible", timedelta(days=1, hours=14)),
    "cb.ecb.deposit_rate": ("BCE - taux de la facilité de dépôt", timedelta(hours=12)),
    "cb.boj.call_rate": ("BoJ - taux au jour le jour non garanti (moyenne)", timedelta(days=1)),
    "cb.boj.basic_loan_rate": ("BoJ - taux d'escompte de base", timedelta(days=1)),
}


def parse_nyfed_targets(payload: dict[str, Any]) -> list[tuple[datetime, float, float]]:
    out: list[tuple[datetime, float, float]] = []
    for row in payload.get("refRates", []) or []:
        try:
            day = datetime.strptime(str(row["effectiveDate"]), "%Y-%m-%d").replace(tzinfo=UTC)
            low, high = float(row["targetRateFrom"]), float(row["targetRateTo"])
        except (KeyError, TypeError, ValueError):
            continue
        out.append((day, low, high))
    return sorted(out)


def parse_ecb_series(payload: dict[str, Any]) -> list[tuple[datetime, float]]:
    """SDMX-JSON: observation index -> TIME_PERIOD value."""

    try:
        series = next(iter(payload["dataSets"][0]["series"].values()))
        observations = series["observations"]
        periods = payload["structure"]["dimensions"]["observation"][0]["values"]
    except (KeyError, IndexError, StopIteration, TypeError):
        return []
    out: list[tuple[datetime, float]] = []
    for index, values in observations.items():
        try:
            day = datetime.strptime(periods[int(index)]["id"], "%Y-%m-%d").replace(tzinfo=UTC)
            value = float(values[0])
        except (KeyError, IndexError, TypeError, ValueError):
            continue
        out.append((day, value))
    return sorted(out)


def parse_boj_series(payload: dict[str, Any]) -> list[tuple[datetime, float]]:
    out: list[tuple[datetime, float]] = []
    for result in payload.get("RESULTSET", []) or []:
        values = result.get("VALUES") or {}
        for stamp, value in zip(values.get("SURVEY_DATES", []), values.get("VALUES", []), strict=False):
            if value in (None, ""):
                continue
            try:
                day = datetime.strptime(str(stamp), "%Y%m%d").replace(tzinfo=UTC)
                out.append((day, float(value)))
            except (TypeError, ValueError):
                continue
    return sorted(out)


def rate_changes(points: list[tuple[datetime, float]]) -> list[tuple[datetime, float, float]]:
    """(day, previous, new) for every change of the rate in force."""

    out: list[tuple[datetime, float, float]] = []
    for (_, before), (day, after) in pairwise(points):
        if abs(after - before) > 1e-9:
            out.append((day, before, after))
    return out


class CentralBankRatesProvider(BaseProvider):
    name = "central_bank_rates"
    source = "Fed (New York Fed), BCE, Banque du Japon"
    category = ProviderCategory.MACRO
    capabilities = ("macro.central_banks",)
    base_confidence = 97.0
    source_url = "https://markets.newyorkfed.org/"

    def _obs(self, metric: str, day: datetime, value: float, url: str, endpoint: str) -> Observation:
        label, delay = CB_METRICS[metric]
        available = day + delay
        return Observation(
            metric=metric,
            value=value,
            unit="pct",
            timestamp=day,
            provenance=self.provenance(url),
            freshness=compute_freshness(available, "macro"),
            confidence=self.base_confidence,
            quality=DataQuality.MEASURED,
            meta={
                "label": label,
                "available_at": available.isoformat(),
                "source_tier": "OFFICIAL",
                "endpoint": endpoint,
                "currency": None,
            },
        )

    async def fetch(self, request: FetchRequest) -> FetchResult:
        http = get_http()
        now = datetime.now(UTC)
        since = now - timedelta(days=int(request.limit or 0) or 3 * 365)
        out: list[Observation] = []

        fed = await http.get_json(
            NYFED_EFFR_SEARCH, provider=self.name,
            params={"startDate": since.date().isoformat(), "endDate": now.date().isoformat()},
            cache_ttl=3600, rate_limit_per_min=10,
        )
        if fed.ok:
            for day, low, high in parse_nyfed_targets(fed.data or {}):
                out.append(self._obs("cb.fed.target_lower", day, low,
                                     "https://markets.newyorkfed.org/", NYFED_EFFR_SEARCH))
                out.append(self._obs("cb.fed.target_upper", day, high,
                                     "https://markets.newyorkfed.org/", NYFED_EFFR_SEARCH))

        ecb = await http.get_json(
            ECB_DFR_URL, provider=self.name,
            params={"startPeriod": since.date().isoformat(), "format": "jsondata"},
            cache_ttl=3600, rate_limit_per_min=10,
        )
        if ecb.ok:
            for day, value in parse_ecb_series(ecb.data or {}):
                out.append(self._obs("cb.ecb.deposit_rate", day, value,
                                     "https://data.ecb.europa.eu/", ECB_DFR_URL))

        for metric, db, code in (
            ("cb.boj.call_rate", "FM01", "STRDCLUCON"),
            ("cb.boj.basic_loan_rate", "IR01", "MADR1Z@D"),
        ):
            boj = await http.get_json(
                BOJ_API, provider=self.name,
                params={"format": "json", "lang": "en", "db": db, "code": code,
                        "startDate": since.strftime("%Y%m")},
                cache_ttl=3600, rate_limit_per_min=10,
            )
            if boj.ok:
                points = parse_boj_series(boj.data or {})
                # The call rate is published every business day; weekends
                # carry no value and are simply absent.
                out.extend(
                    self._obs(metric, day, value, "https://www.stat-search.boj.or.jp/", BOJ_API)
                    for day, value in points
                )

        if not out:
            return FetchResult.failure(FetchStatus.NO_DATA, self.name)
        return FetchResult.success(out, self.name)

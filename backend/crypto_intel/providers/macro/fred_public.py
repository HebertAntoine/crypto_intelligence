"""The FRED series that no other connected source publishes, without a key.

``fred.py`` reads the FRED API, which needs a key. This reads the same data
through the public CSV export the St. Louis Fed serves at
``fred.stlouisfed.org/graph/fredgraph.csv?id=...``: no account, no token, no
authentication, and explicitly allowed by the site's robots.txt (only the
PNG graph, the landing page and the search results are disallowed). The
declared crawl-delay of one second is respected by spacing the requests.

Only series that nothing else here provides:

    credit     ICE BofA high-yield and investment-grade option-adjusted
               spreads. Equities falling with calm spreads is a drawdown;
               equities falling while spreads widen is systemic stress, and
               without these two the difference cannot be measured at all.
    inflation  PCE and core PCE - the gauge the Fed actually targets, which
               the BLS does not publish (it is the BEA's).
    labour     weekly initial jobless claims, the only labour reading that
               arrives between two monthly payroll reports.
    liquidity  total assets of the Reserve Banks. The H.4.1 page is scraped
               for the current week only; this carries the history behind it.

Each point keeps the period it describes (``timestamp``) and when it became
public (``meta["available_at"]``): a core PCE for August is not knowable in
August, and a study reading this data must use the second.
"""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime, timedelta
from typing import ClassVar

from ...core.enums import DataQuality, FetchStatus, ProviderCategory
from ...core.freshness import compute_freshness
from ...core.models import Observation
from ..base import BaseProvider, FetchRequest, FetchResult
from ..http import get_http

CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"

#: series id -> (metric, unit, label, publication lag after the period)
#:
#: The lags are deliberately conservative: a value must never appear to have
#: been knowable before it was published.
SERIES: dict[str, tuple[str, str, str, timedelta]] = {
    "BAMLH0A0HYM2": ("macro.hy_spread", "pct",
                     "Prime de risque des obligations à haut rendement (ICE BofA)",
                     timedelta(days=1)),
    "BAMLC0A0CM": ("macro.ig_spread", "pct",
                   "Prime de risque des obligations de qualité (ICE BofA)",
                   timedelta(days=1)),
    "PCEPI": ("macro.pce", "index", "Indice des prix PCE", timedelta(days=58)),
    "PCEPILFE": ("macro.core_pce", "index",
                 "Indice des prix PCE sous-jacent (hors énergie et alimentation)",
                 timedelta(days=58)),
    "ICSA": ("macro.jobless_claims", "count",
             "Nouvelles inscriptions hebdomadaires au chômage", timedelta(days=5)),
    "WALCL": ("liquidity.fed_total_assets", "musd",
              "Total des actifs de la Réserve fédérale (H.4.1)", timedelta(days=5)),
}


def parse_csv(text: str) -> list[tuple[datetime, float]]:
    """``observation_date,VALUE`` rows, skipping the dots FRED writes for gaps.

    A missing observation is written as ``.`` - a holiday, or a series that
    has not been updated yet. It is a hole in the data, not a zero.
    """

    out: list[tuple[datetime, float]] = []
    reader = csv.reader(io.StringIO(text))
    header = next(reader, None)
    if header is None or len(header) < 2:
        return out
    for row in reader:
        if len(row) < 2:
            continue
        raw = row[1].strip()
        if not raw or raw == ".":
            continue
        try:
            day = datetime.strptime(row[0].strip(), "%Y-%m-%d").replace(tzinfo=UTC)
            out.append((day, float(raw)))
        except ValueError:
            continue
    return out


class FredPublicCsvProvider(BaseProvider):
    """Public CSV export, no key. See the module docstring for why it exists."""

    name = "fred_public_csv"
    source = "Federal Reserve Bank of St. Louis (FRED)"
    category = ProviderCategory.MACRO
    capabilities: ClassVar[tuple[str, ...]] = ("macro.credit", "macro.pce", "macro.claims")
    source_url = "https://fred.stlouisfed.org/"
    base_confidence = 95.0

    #: Enough history for a percentile to mean something, without pulling
    #: decades on every cycle.
    HISTORY_DAYS: ClassVar[int] = 1100

    async def fetch(self, request: FetchRequest) -> FetchResult:
        http = get_http()
        start = (datetime.now(UTC) - timedelta(days=self.HISTORY_DAYS)).date().isoformat()
        out: list[Observation] = []
        failures: list[str] = []
        for series_id, (metric, unit, label, lag) in SERIES.items():
            result = await http.get_text(
                CSV_URL, provider=self.name,
                params={"id": series_id, "cosd": start},
                # One request per minute per series at most: the site asks for
                # a one-second crawl delay and these series move daily at best.
                cache_ttl=3600, rate_limit_per_min=30,
            )
            if not result.ok or not result.data:
                failures.append(series_id)
                continue
            for day, value in parse_csv(result.data):
                available = day + lag
                out.append(Observation(
                    metric=metric,
                    value=value,
                    unit=unit,
                    timestamp=day,
                    provenance=self.provenance(f"{CSV_URL}?id={series_id}"),
                    freshness=compute_freshness(available, "macro"),
                    confidence=self.base_confidence,
                    quality=DataQuality.MEASURED,
                    meta={
                        "label": label,
                        "series_id": series_id,
                        "available_at": available.isoformat(),
                        "source_tier": "OFFICIAL",
                    },
                ))
        if not out:
            return FetchResult.failure(
                FetchStatus.NO_DATA, self.name,
                f"aucune série lue ({', '.join(failures)})" if failures else "",
            )
        return FetchResult.success(out, self.name)

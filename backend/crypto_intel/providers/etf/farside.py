"""Farside Investors - US spot ETF daily flows (BTC, ETH).

ACCESS NOTE, verified 2026-09-04:
Farside answers HTTP 403 to requests carrying a default tool User-Agent (e.g.
bare curl), but serves the page normally when the client identifies itself
descriptively - which is what this project does via HTTP_USER_AGENT.

That is NOT an anti-bot bypass. We send one honest User-Agent naming the tool,
exactly as the SEC requires for its own feeds. We never impersonate a browser,
never rotate User-Agents, never use proxies, never run a headless browser, and
never solve a challenge. If the site ever answers with 403 or a challenge page
for this honest identification, the connector marks itself BLOCKED_BY_SOURCE
and stops permanently - the CSV import path then takes over.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ...core.enums import Asset, DataQuality, FetchStatus, ProviderCategory
from ...core.freshness import compute_freshness
from ...core.models import Observation
from ...db import repo
from ...logging_setup import get_logger
from ..base import BaseProvider, FetchRequest, FetchResult, ProviderStatus
from ..http import get_http

log = get_logger("providers.farside")

_PATHS = {"BTC": "/bitcoin-etf-flow-all-data/", "ETH": "/ethereum-etf-flow-all-data/"}
_DATE_FORMATS = ("%d %b %Y", "%d %B %Y", "%Y-%m-%d")
# Column labels that are aggregates or noise rather than an individual fund.
_NON_TICKER = {"total", "", "date", "average", "maximum", "minimum", "sum"}


class FarsideProvider(BaseProvider):
    name = "farside"
    source = "Farside Investors"
    category = ProviderCategory.ETF
    capabilities = ("etf.flows",)
    source_url = "https://farside.co.uk"
    base_confidence = 88.0

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.base_url = self.config.get("base_url", "https://farside.co.uk")
        self.ttl = int((self.config.get("cache_ttl") or {}).get("default", 21600))
        self._blocked = False

    async def available(self) -> ProviderStatus:
        if self._blocked:
            return ProviderStatus(
                name=self.name, available=False,
                reason=(
                    "UNAVAILABLE - Farside refused automated access. No bypass attempted. "
                    "Use CSV import: place a file in data/imports/etf/ and run `make import-etf`."
                ),
            )
        return ProviderStatus(name=self.name, available=True)

    async def fetch(self, request: FetchRequest) -> FetchResult:
        if request.asset is None or request.asset.value not in _PATHS:
            return FetchResult.failure(
                FetchStatus.NO_DATA, self.name,
                f"Farside publishes BTC and ETH spot ETF flows; no page for "
                f"{request.asset.value if request.asset else 'unknown'}",
            )
        if self._blocked:
            return self._blocked_result()

        url = f"{self.base_url}{_PATHS[request.asset.value]}"
        res = await get_http().get_text(
            url, provider=self.name, cache_ttl=self.ttl, rate_limit_per_min=4, retries=0
        )

        if res.status is FetchStatus.BLOCKED_BY_SOURCE:
            self._blocked = True
            log.info("farside_blocked_no_bypass", url=url)
            return self._blocked_result()
        if not res.ok:
            return FetchResult.failure(res.status, self.name, res.message)

        try:
            rows = parse_farside_table(res.data, request.asset.value)
        except Exception as exc:
            return FetchResult.failure(FetchStatus.PARSE_ERROR, self.name, str(exc))

        if not rows:
            return FetchResult.failure(
                FetchStatus.NO_DATA, self.name,
                "Page retrieved but no flow table could be parsed (site layout may have changed)",
            )

        # Persist so history survives even if the page becomes unreachable later.
        repo.save_etf_flows(
            [{**r, "import_source": "farside", "source_url": url} for r in rows]
        )

        prov = self.provenance(url)
        observations = [
            Observation(
                asset=request.asset, metric="etf.flow", value=r["flow_musd"], unit="USD_M",
                timestamp=r["date"], provenance=prov,
                freshness=compute_freshness(r["date"], "etf"),
                confidence=self.base_confidence, quality=DataQuality.MEASURED,
                meta={"ticker": r["ticker"]},
            )
            for r in rows
        ]
        return FetchResult.success(observations, self.name, raw={"rows": rows, "source_url": url})

    def _blocked_result(self) -> FetchResult:
        return FetchResult.failure(
            FetchStatus.BLOCKED_BY_SOURCE, self.name,
            (
                "UNAVAILABLE - Farside refused automated access. Policy: no anti-bot bypass. "
                "Import manually: place a CSV in data/imports/etf/ then `make import-etf`."
            ),
        )


def _parse_date(raw: str) -> datetime | None:
    raw = raw.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def _parse_flow(raw: str) -> float | None:
    """Blank / '-' means the fund reported nothing that day -> None, not 0.0.

    That distinction matters: a zero flow is a real observation, a missing cell
    is not, and averaging them together would quietly bias every mean.
    """
    s = raw.strip().replace(",", "").replace("$", "").replace("\xa0", "")
    if s in ("", "-", "–", "—", "N/A", "n/a"):
        return None
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    try:
        return float(s)
    except ValueError:
        return None


def parse_farside_table(html: str, asset: str) -> list[dict[str, Any]]:
    """Extract per-fund daily flows.

    Handles the two layouts the site actually uses: a single header row of
    tickers (BTC page), and a two-row header where issuer names sit above the
    ticker row (ETH page). Rather than assuming a layout, we take the last
    header row that looks like tickers, and treat any row whose first cell
    parses as a date as data.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    out: list[dict[str, Any]] = []

    for table in soup.find_all("table"):
        header: list[str] = []
        rows_found = 0

        for tr in table.find_all("tr"):
            cells = tr.find_all(["th", "td"])
            if not cells:
                continue
            texts = [c.get_text(strip=True).replace("\xa0", " ") for c in cells]

            date = _parse_date(texts[0])
            if date is None:
                # Header candidate: keep the row that carries ticker symbols.
                # Tickers are short and uppercase; issuer names are not.
                candidates = texts[1:]
                if candidates and sum(
                    1 for t in candidates if t and t.isupper() and 2 <= len(t) <= 6
                ) >= max(2, len(candidates) // 3):
                    header = texts
                continue

            if not header:
                continue
            rows_found += 1
            for i, raw in enumerate(texts[1:], start=1):
                if i >= len(header):
                    break
                ticker = header[i].strip().upper()
                if ticker.lower() in _NON_TICKER:
                    continue
                flow = _parse_flow(raw)
                if flow is None:
                    continue
                out.append(
                    {"date": date, "asset": asset, "ticker": ticker, "flow_musd": flow}
                )

        if rows_found:
            break   # first table carrying dated rows is the flow table

    return out


def asset_supported(asset: Asset) -> bool:
    return asset.value in _PATHS

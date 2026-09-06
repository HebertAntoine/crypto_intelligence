"""FRED macro series (St. Louis Fed). Free API key required.

Without FRED_API_KEY these series are UNAVAILABLE - never approximated.
Get one in a minute: https://fredaccount.stlouisfed.org/apikeys
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ...core.enums import DataQuality, FetchStatus, ProviderCategory
from ...core.freshness import compute_freshness
from ...core.models import Observation
from ...settings import get_settings
from ..base import BaseProvider, FetchRequest, FetchResult
from ..http import get_http

# series id -> (metric, unit, label)
#
# Covers every series the analysis layer consumes. Where a better free source
# exists, it is noted: FRED's DTWEXBGS is a BROAD trade-weighted dollar index,
# which is not the same instrument as the DXY quoted by markets - Yahoo's
# DX-Y.NYB is the tradable one, so both are collected under distinct metric
# names and never conflated.
SERIES: dict[str, tuple[str, str, str]] = {
    # Policy rate
    "DFF":        ("macro.fed_funds_rate", "pct", "Effective Federal Funds Rate"),
    "FEDFUNDS":   ("macro.fed_funds_monthly", "pct", "Federal Funds Rate (monthly avg)"),
    # Treasury curve
    "DGS2":       ("macro.us2y", "pct", "US 2Y Treasury Yield"),
    "DGS10":      ("macro.us10y", "pct", "US 10Y Treasury Yield"),
    "T10Y2Y":     ("macro.yield_curve_10y2y", "pct", "10Y-2Y Spread"),
    # Inflation
    "CPIAUCSL":   ("macro.cpi", "index", "CPI All Urban Consumers"),
    "CPILFESL":   ("macro.core_cpi", "index", "Core CPI (ex food and energy)"),
    "PCEPI":      ("macro.pce", "index", "PCE Price Index"),
    "PCEPILFE":   ("macro.core_pce", "index", "Core PCE Price Index"),
    # Labour
    "UNRATE":     ("macro.unemployment", "pct", "US Unemployment Rate"),
    "PAYEMS":     ("macro.nonfarm_payrolls", "thousands", "Total Nonfarm Payrolls"),
    # Dollar - broad trade-weighted index, NOT the tradable DXY
    "DTWEXBGS":   ("macro.dxy_broad", "index", "Broad Trade-Weighted Dollar Index"),
}

# Series available from a better or more timely free source. Documented so the
# choice is explicit rather than accidental.
BETTER_ELSEWHERE: dict[str, str] = {
    "DXY (tradable)": (
        "Yahoo Finance DX-Y.NYB - the market-quoted dollar index. FRED's DTWEXBGS "
        "is a broader trade-weighted basket and is not interchangeable."
    ),
    "Equity indices": "Yahoo Finance (^GSPC, ^IXIC, ^DJI) - FRED lags and is less granular.",
    "VIX": "Yahoo Finance ^VIX - same data, no key required.",
    "Intraday yields": (
        "Yahoo Finance ^TNX for a live 10Y proxy; FRED DGS10 is end-of-day only."
    ),
}


class FredProvider(BaseProvider):
    name = "fred"
    source = "FRED (St. Louis Fed)"
    category = ProviderCategory.MACRO
    capabilities = ("macro.series",)
    requires_key = "FRED_API_KEY"
    source_url = "https://fred.stlouisfed.org"
    base_confidence = 95.0

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.base_url = self.config.get("base_url", "https://api.stlouisfed.org/fred")
        self.ttl = int((self.config.get("cache_ttl") or {}).get("default", 3600))

    async def fetch(self, request: FetchRequest) -> FetchResult:
        settings = get_settings()
        if not settings.fred_api_key.strip():
            return FetchResult.failure(
                FetchStatus.NOT_CONFIGURED, self.name,
                "UNAVAILABLE - FRED_API_KEY not set (free key: https://fredaccount.stlouisfed.org/apikeys)",
            )

        wanted: list[str] = request.params.get("series") or list(SERIES)
        http = get_http()
        out: list[Observation] = []

        for sid in wanted:
            if sid not in SERIES:
                continue
            metric, unit, label = SERIES[sid]
            url = f"{self.base_url}/series/observations"
            res = await http.get_json(
                url, provider=self.name,
                params={
                    "series_id": sid, "api_key": settings.fred_api_key, "file_type": "json",
                    "sort_order": "desc", "limit": 60,
                },
                cache_ttl=self.ttl, rate_limit_per_min=40,
            )
            if not res.ok:
                continue
            rows = (res.data or {}).get("observations") or []
            prov = self.provenance(f"https://fred.stlouisfed.org/series/{sid}")
            for row in rows:
                raw = row.get("value")
                # FRED uses "." for missing observations. Skip, never zero-fill.
                if raw in (None, ".", ""):
                    continue
                try:
                    ts = datetime.strptime(row["date"], "%Y-%m-%d").replace(tzinfo=UTC)
                    value = float(raw)
                except (KeyError, ValueError, TypeError):
                    continue
                out.append(Observation(
                    metric=metric, value=value, unit=unit, timestamp=ts, provenance=prov,
                    freshness=compute_freshness(ts, "macro"), confidence=self.base_confidence,
                    quality=DataQuality.MEASURED, meta={"series_id": sid, "label": label},
                ))

        if not out:
            return FetchResult.failure(FetchStatus.NO_DATA, self.name)
        return FetchResult.success(out, self.name)

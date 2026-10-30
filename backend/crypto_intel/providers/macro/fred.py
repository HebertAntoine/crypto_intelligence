"""FRED macro series (St. Louis Fed). Free API key required.

Without FRED_API_KEY these series are UNAVAILABLE - never approximated.
Get one in a minute: https://fredaccount.stlouisfed.org/apikeys
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ...core.enums import DataQuality, FetchStatus, ProviderCategory
from ...core.freshness import compute_freshness
from ...core.models import Observation, Provenance
from ...settings import get_settings
from ..base import BaseProvider, FetchRequest, FetchResult, ProviderStatus
from ..http import get_http

# series id -> (metric, unit, label)
#
# Covers every series the analysis layer consumes. Where a better free source
# exists, it is noted: FRED's DTWEXBGS is a BROAD trade-weighted dollar index,
# which is not the same instrument as DXY.  They therefore remain distinct
# metrics and are never silently substituted.
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
    "PPIACO":     ("macro.ppi", "index", "Producer Price Index, All Commodities"),
    # Dollar - broad trade-weighted index, NOT the tradable DXY
    "DTWEXBGS":   ("macro.dxy_broad", "index", "Broad Trade-Weighted Dollar Index"),
    # Long end of the curve. The 2Y prices policy expectations and the 10Y
    # prices financial conditions; the 30Y carries long-run inflation and
    # fiscal risk, which the other two do not.
    "DGS30":      ("macro.us30y", "pct", "US 30Y Treasury Yield"),
    # Energy. Oil enters the analysis as an inflation input, never as a direct
    # crypto signal: the chain runs through inflation, policy and yields.
    "DCOILBRENTEU": ("macro.brent", "usd", "Crude Oil Prices: Brent - Europe"),
    "DCOILWTICO":   ("macro.wti", "usd", "Crude Oil Prices: WTI - Cushing"),
    # Credit. Equities falling with calm spreads is a drawdown; equities falling
    # while spreads widen is systemic stress. Without these two series the
    # difference cannot be measured at all.
    "BAMLH0A0HYM2": ("macro.hy_spread", "pct", "ICE BofA US High Yield OAS"),
    "BAMLC0A0CM":   ("macro.ig_spread", "pct", "ICE BofA US Corporate OAS"),
    # Composite financial-stress measures produced by Federal Reserve Banks.
    "STLFSI4":      ("macro.stlfsi4", "index", "St. Louis Fed Financial Stress Index"),
    "NFCI":         ("macro.nfci", "index", "Chicago Fed National Financial Conditions Index"),
    # Liquidity and weekly labour readings.
    "WALCL":        ("liquidity.fed_total_assets", "musd", "Federal Reserve Total Assets"),
    "ICSA":         ("macro.jobless_claims", "count", "Initial Jobless Claims"),
    # Cboe owns the underlying series; it is gated separately below.
    "VIXCLS":       ("macro.vix", "index", "CBOE Volatility Index: VIX"),
}

THIRD_PARTY_SERIES = frozenset({"BAMLH0A0HYM2", "BAMLC0A0CM", "VIXCLS"})


def rights_exclusion(series_id: str) -> dict[str, str]:
    """Machine-readable explanation for a licensed series that was not read."""

    owner = "Cboe" if series_id == "VIXCLS" else "ICE BofA"
    return {
        "series_id": series_id,
        "metric": SERIES[series_id][0],
        "owner": owner,
        "reason": "THIRD_PARTY_REDISTRIBUTION_NOT_AUTHORIZED",
        "required_setting": "FRED_THIRD_PARTY_REDISTRIBUTION_AUTHORIZED=true",
    }

# Series available from a better or more timely free source. Documented so the
# choice is explicit rather than accidental.
BETTER_ELSEWHERE: dict[str, str] = {
    "DXY (tradable)": (
        "A separately licensed market-data feed is required. FRED's DTWEXBGS is a broader "
        "trade-weighted basket and is not interchangeable."
    ),
    "Equity indices": "Twelve Data when the configured plan and display rights allow it.",
    "VIX": "Twelve Data when the configured plan includes the index and display rights.",
    "Intraday yields": "A separately licensed feed is required; FRED DGS10 is end-of-day.",
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

    async def available(self) -> ProviderStatus:
        settings = get_settings()
        if not settings.fred_content_use_authorized:
            return ProviderStatus(
                name=self.name,
                available=False,
                configured=False,
                reason="FRED storage/AI-system use is not documented as authorized",
                requires_key=self.requires_key,
            )
        if not settings.fred_api_key.strip():
            return ProviderStatus(
                name=self.name,
                available=False,
                configured=False,
                reason="FRED_API_KEY not set",
                requires_key=self.requires_key,
            )
        return ProviderStatus(
            name=self.name,
            available=True,
            configured=True,
            requires_key=self.requires_key,
        )

    async def fetch(self, request: FetchRequest) -> FetchResult:
        settings = get_settings()
        status = await self.available()
        if not status.available:
            return FetchResult.failure(
                FetchStatus.NOT_CONFIGURED,
                self.name,
                f"UNAVAILABLE - {status.reason}",
            )

        wanted: list[str] = request.params.get("series") or list(SERIES)
        http = get_http()
        out: list[Observation] = []
        excluded_series: list[dict[str, str]] = []

        for sid in wanted:
            if sid not in SERIES:
                continue
            if (
                sid in THIRD_PARTY_SERIES
                and not settings.fred_third_party_redistribution_authorized
            ):
                excluded_series.append(rights_exclusion(sid))
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
            prov = Provenance(
                source=self.source,
                provider=self.name,
                source_url=f"https://fred.stlouisfed.org/series/{sid}",
                license_note=(
                    "Third-party FRED series enabled after operator rights confirmation."
                    if sid in THIRD_PARTY_SERIES
                    else "Subject to FRED Terms of Use and any source-specific series notes."
                ),
            )
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
                    quality=DataQuality.MEASURED,
                    meta={
                        "series_id": sid,
                        "label": label,
                        "license_status": (
                            "OPERATOR_CONFIRMED" if sid in THIRD_PARTY_SERIES else "FRED_TERMS"
                        ),
                    },
                ))

        rights_summary = {
            "requested_series": [sid for sid in wanted if sid in SERIES],
            "excluded_series": excluded_series,
        }
        if not out:
            message = "No FRED observations returned"
            if excluded_series:
                ids = ", ".join(item["series_id"] for item in excluded_series)
                message += f"; excluded for unconfirmed third-party rights: {ids}"
            return FetchResult(
                status=FetchStatus.NO_DATA,
                provider=self.name,
                raw=rights_summary,
                message=message,
            )
        return FetchResult.success(out, self.name, raw=rights_summary)

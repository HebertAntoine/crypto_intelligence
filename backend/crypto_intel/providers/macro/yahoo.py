"""Legacy Yahoo chart adapter, retained only for historical compatibility.

It is deliberately absent from the production provider chain: a public web
endpoint is not treated as a redistribution licence.  Existing installations
can still identify old rows by the ``yahoo_finance`` provider name.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ...core.enums import DataQuality, FetchStatus, ProviderCategory
from ...core.freshness import compute_freshness
from ...core.models import Observation
from ..base import BaseProvider, FetchRequest, FetchResult
from ..http import get_http

# yahoo symbol -> (metric, unit, label)
SYMBOLS: dict[str, tuple[str, str, str]] = {
    "^GSPC": ("macro.sp500", "index", "S&P 500"),
    "^IXIC": ("macro.nasdaq", "index", "Nasdaq Composite"),
    "^DJI": ("macro.dow", "index", "Dow Jones Industrial Average"),
    "DX-Y.NYB": ("macro.dxy", "index", "US Dollar Index (DXY)"),
    "^VIX": ("macro.vix", "index", "CBOE Volatility Index"),
    "CL=F": ("macro.oil_wti", "USD", "WTI Crude Oil"),
    "GC=F": ("macro.gold", "USD", "Gold Futures"),
    "^TNX": ("macro.us10y_yahoo", "pct", "US 10Y Treasury Yield"),
}


class YahooFinanceProvider(BaseProvider):
    name = "yahoo_finance"
    source = "Yahoo Finance"
    category = ProviderCategory.MACRO
    capabilities = ("macro.indices",)
    source_url = "https://finance.yahoo.com"
    base_confidence = 82.0

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.base_url = self.config.get("base_url", "https://query1.finance.yahoo.com")
        self.ttl = int((self.config.get("cache_ttl") or {}).get("default", 1800))

    async def fetch(self, request: FetchRequest) -> FetchResult:
        http = get_http()
        out: list[Observation] = []

        for symbol, (metric, unit, label) in SYMBOLS.items():
            url = f"{self.base_url}/v8/finance/chart/{symbol}"
            res = await http.get_json(
                url, provider=self.name, params={"interval": "1d", "range": "3mo"},
                cache_ttl=self.ttl, rate_limit_per_min=30,
            )
            if not res.ok:
                continue

            try:
                result = (res.data or {}).get("chart", {}).get("result") or []
                if not result:
                    continue
                block = result[0]
                stamps = block.get("timestamp") or []
                closes = (block.get("indicators", {}).get("quote") or [{}])[0].get("close") or []
            except (KeyError, IndexError, TypeError):
                continue

            prov = self.provenance(f"https://finance.yahoo.com/quote/{symbol}")
            for ts_raw, close in zip(stamps, closes, strict=False):
                # Yahoo returns null for market holidays - skip, never carry forward.
                if close is None:
                    continue
                try:
                    ts = datetime.fromtimestamp(int(ts_raw), tz=UTC)
                except (TypeError, ValueError, OSError):
                    continue
                out.append(Observation(
                    metric=metric, value=float(close), unit=unit, timestamp=ts, provenance=prov,
                    freshness=compute_freshness(ts, "macro"), confidence=self.base_confidence,
                    quality=DataQuality.MEASURED, meta={"symbol": symbol, "label": label},
                ))

        if not out:
            return FetchResult.failure(FetchStatus.NO_DATA, self.name)
        return FetchResult.success(out, self.name)

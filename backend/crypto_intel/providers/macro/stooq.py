"""Stooq CSV - kept as a secondary macro source.

STATUS, verified 2026-09-04: Stooq now answers non-browser clients with a
JavaScript proof-of-work challenge page. Solving it would be an anti-bot
bypass, which this project forbids, so this provider detects the challenge and
reports BLOCKED_BY_SOURCE. Yahoo Finance is the working no-key alternative.

The code stays because the site's policy may change again.
"""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime
from typing import Any

from ...core.enums import DataQuality, FetchStatus, ProviderCategory
from ...core.freshness import compute_freshness
from ...core.models import Observation
from ..base import BaseProvider, FetchRequest, FetchResult
from ..http import get_http

SYMBOLS: dict[str, tuple[str, str]] = {
    "^spx": ("macro.sp500", "S&P 500"),
    "^ndq": ("macro.nasdaq", "Nasdaq Composite"),
    "^dji": ("macro.dow", "Dow Jones"),
    "dx.f": ("macro.dxy", "US Dollar Index"),
    "cl.f": ("macro.oil_wti", "WTI Crude Oil"),
    "gc.f": ("macro.gold", "Gold"),
}


class StooqProvider(BaseProvider):
    name = "stooq"
    source = "Stooq"
    category = ProviderCategory.MACRO
    capabilities = ("macro.indices",)
    source_url = "https://stooq.com"
    base_confidence = 80.0

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.base_url = self.config.get("base_url", "https://stooq.com")
        self.ttl = int((self.config.get("cache_ttl") or {}).get("default", 1800))

    async def fetch(self, request: FetchRequest) -> FetchResult:
        http = get_http()
        out: list[Observation] = []

        for symbol, (metric, label) in SYMBOLS.items():
            url = f"{self.base_url}/q/d/l/"
            res = await http.get_text(
                url, provider=self.name, params={"s": symbol, "i": "d"},
                cache_ttl=self.ttl, rate_limit_per_min=20,
            )
            if res.status is FetchStatus.BLOCKED_BY_SOURCE:
                # Surface the real reason rather than a vague "no data".
                return FetchResult.failure(
                    FetchStatus.BLOCKED_BY_SOURCE, self.name,
                    "UNAVAILABLE - Stooq serves a JavaScript anti-bot challenge to "
                    "non-browser clients. No bypass attempted; Yahoo Finance is used instead.",
                )
            if not res.ok or not isinstance(res.data, str):
                continue
            rows = list(csv.DictReader(io.StringIO(res.data)))
            if not rows:
                continue
            prov = self.provenance(f"https://stooq.com/q/?s={symbol}")
            # Last 40 sessions is enough for the trend calculations we do.
            for row in rows[-40:]:
                try:
                    ts = datetime.strptime(row["Date"], "%Y-%m-%d").replace(tzinfo=UTC)
                    close = float(row["Close"])
                except (KeyError, ValueError, TypeError):
                    continue
                out.append(Observation(
                    metric=metric, value=close, unit="index", timestamp=ts, provenance=prov,
                    freshness=compute_freshness(ts, "macro"), confidence=self.base_confidence,
                    quality=DataQuality.MEASURED, meta={"symbol": symbol, "label": label},
                ))

        if not out:
            return FetchResult.failure(FetchStatus.NO_DATA, self.name)
        return FetchResult.success(out, self.name)

"""Bitcoin daily history before the exchange we normally read existed.

Our candles start in August 2017 (BTCUSDT). A cycle reading that wants to
compare 2012, 2016, 2020 and 2024 needs the years before that, so the daily
bars from 2011 to 2017 are taken from Bitstamp's public BTC/USD endpoint and
stored with their own source name. They are a different pair on a different
venue: fine for a cycle read in orders of magnitude, and labelled as such.

Nothing overwrites a bar we already have: the loader stops where the live
history begins.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from ..core.enums import Asset, Timeframe
from ..core.models import Candle
from ..logging_setup import get_logger
from ..providers.http import get_http
from . import store

log = get_logger(__name__)

BITSTAMP_OHLC = "https://www.bitstamp.net/api/v2/ohlc/btcusd/"
SOURCE = "bitstamp_btcusd_daily"
#: Bitstamp's own history starts here; asking earlier returns nothing.
FIRST_DAY = datetime(2011, 8, 18, tzinfo=UTC)


def parse_bitstamp(payload: Any) -> list[Candle]:
    rows = ((payload or {}).get("data") or {}).get("ohlc") or []
    out: list[Candle] = []
    for row in rows:
        try:
            out.append(Candle(
                timestamp=datetime.fromtimestamp(int(row["timestamp"]), UTC),
                open=float(row["open"]), high=float(row["high"]),
                low=float(row["low"]), close=float(row["close"]),
                volume=float(row["volume"]),
            ))
        except (KeyError, TypeError, ValueError):
            continue
    return sorted(out, key=lambda c: c.timestamp)


async def backfill_btc_daily(until: datetime | None = None) -> dict[str, Any]:
    """Fill daily BTC bars from 2011 up to where our own history begins."""

    existing = store.load_candles(Asset.BTC, Timeframe.D1)
    if until is None:
        until = (
            existing.index[0].to_pydatetime().replace(tzinfo=UTC)
            if len(existing) else datetime.now(UTC)
        )
    http = get_http()
    start = FIRST_DAY
    written = 0
    requests = 0
    while start < until and requests < 12:
        res = await http.get_json(
            BITSTAMP_OHLC, provider="bitstamp_history",
            params={"step": 86_400, "limit": 1000, "start": int(start.timestamp())},
            cache_ttl=86_400, rate_limit_per_min=30, retries=2,
        )
        requests += 1
        if not res.ok:
            break
        candles = [c for c in parse_bitstamp(res.data) if c.timestamp < until]
        if not candles:
            break
        written += store.save_candles(Asset.BTC, Timeframe.D1, candles, source=SOURCE)
        newest = max(c.timestamp for c in candles)
        if newest <= start:
            break
        start = newest + timedelta(days=1)
    coverage = store.load_candles(Asset.BTC, Timeframe.D1)
    return {
        "new_rows": written,
        "requests": requests,
        "earliest": coverage.index[0].isoformat() if len(coverage) else None,
        "rows": len(coverage),
        "source": SOURCE,
    }

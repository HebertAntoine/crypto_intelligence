"""Deribit DVOL: the options market's expectation of future volatility.

This is the most genuinely orthogonal series available to the project. Every
other family - price, funding, open interest, chart structure - is derived from
the spot or perpetual market. DVOL comes from a different market entirely: what
options buyers are willing to pay for protection.

The economically meaningful quantity is not the level but the **variance risk
premium**: implied volatility minus the volatility that subsequently occurs.
That spread is the price of insurance, and it reflects positioning and fear
that the price series does not show.

Public endpoint, no key. BTC and ETH only - Deribit lists no SOL volatility
index, so SOL is UNAVAILABLE rather than approximated from something else.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ...core.enums import Asset
from ...logging_setup import get_logger
from ..http import get_http

log = get_logger("providers.deribit")

DERIBIT = "https://www.deribit.com/api/v2"

# Deribit publishes a volatility index for these currencies only.
SUPPORTED: dict[str, str] = {"BTC": "BTC", "ETH": "ETH"}

# One point per day. Finer resolutions exist but theresearch horizon is daily and
# a 12-hour series would double the sample without adding independent
# observations.
RESOLUTION_SECONDS = 86400


async def fetch_window(
    currency: str, start_ms: int, end_ms: int
) -> list[tuple[datetime, float]]:
    """One page of the volatility index."""
    result = await get_http().get_json(
        f"{DERIBIT}/public/get_volatility_index_data",
        provider="deribit",
        params={
            "currency": currency,
            "start_timestamp": start_ms,
            "end_timestamp": end_ms,
            "resolution": str(RESOLUTION_SECONDS),
        },
        cache_ttl=3600,
        rate_limit_per_min=30,
        retries=2,
    )
    if not result.ok:
        return []

    rows = (result.data or {}).get("result", {}).get("data") or []
    points: list[tuple[datetime, float]] = []
    for row in rows:
        try:
            # [timestamp, open, high, low, close]
            timestamp = datetime.fromtimestamp(int(row[0]) / 1000, tz=UTC)
            points.append((timestamp, float(row[4])))
        except (IndexError, ValueError, TypeError):
            continue
    return points


async def backfill_dvol(
    asset: Asset, max_pages: int = 12, window_days: int = 500
) -> dict[str, Any]:
    """Page backwards through the index until Deribit stops returning data.

    Each request is capped at 1000 points, so a multi-year history needs
    pagination. The loop stops when a page returns nothing new, which is how
    the real start of the series is found rather than assumed.
    """
    from ...history import store

    currency = SUPPORTED.get(asset.value)
    if currency is None:
        return {
            "asset": asset.value,
            "status": "UNAVAILABLE",
            "reason": (
                "Deribit lists no volatility index for this asset. It is not "
                "approximated from another series."
            ),
        }

    end_ms = int(datetime.now(UTC).timestamp() * 1000)
    collected: dict[datetime, float] = {}
    pages = 0

    while pages < max_pages:
        start_ms = end_ms - window_days * 86400_000
        points = await fetch_window(currency, start_ms, end_ms)
        pages += 1
        if not points:
            break

        before = len(collected)
        collected.update(dict(points))
        if len(collected) == before:
            break                      # no progress: we have reached the start

        oldest = min(t for t, _ in points)
        end_ms = int(oldest.timestamp() * 1000) - 1

    if not collected:
        return {"asset": asset.value, "status": "NO_DATA", "requests": pages}

    ordered = sorted(collected.items())
    written = store.save_derivatives(asset, "dvol.index", ordered, source="deribit")
    coverage = store.derivatives_coverage(asset).get("dvol.index", {})

    store.record_backfill(
        dataset="dvol", asset=asset, timeframe=None,
        earliest=coverage.get("start"), latest=coverage.get("end"),
        rows=coverage.get("rows", 0), source="deribit",
        note=f"{pages} requests, {written} new rows - public endpoint, no key",
    )
    log.info("dvol_backfilled", asset=asset.value, new=written, total=coverage.get("rows"))
    return {
        "asset": asset.value, "status": "OK",
        "new_rows": written, "requests": pages, **coverage,
    }


async def backfill_all(assets: list[Asset] | None = None) -> dict[str, Any]:
    assets = assets or Asset.tradables()
    return {a.value: await backfill_dvol(a) for a in assets}

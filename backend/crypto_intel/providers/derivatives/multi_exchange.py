"""Multi-exchange derivatives: Binance, Bybit, OKX.

Two reasons this exists.

First, depth. Binance publishes ~30 days of open-interest history, which made
every OI study in LOT 3 return INSUFFICIENT_DATA. Bybit's public endpoint
paginates by `endTime` and reaches back years. Same public API, no key, no
limitation circumvented - the data was simply on a different exchange.

Second, breadth. A funding spike on one venue is a venue anomaly; a spike
across three is a market condition. Aggregating lets the system tell those
apart instead of treating Binance as the market.

All endpoints used are public and unauthenticated.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from ...core.enums import Asset
from ...logging_setup import get_logger
from ..http import get_http

log = get_logger("providers.multi_exchange")

# Per-exchange symbol mapping. Kept explicit rather than derived, because the
# naming conventions genuinely differ and a wrong guess returns silence.
SYMBOLS: dict[str, dict[str, str]] = {
    "binance": {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT"},
    "bybit": {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT"},
    "okx": {"BTC": "BTC-USDT-SWAP", "ETH": "ETH-USDT-SWAP", "SOL": "SOL-USDT-SWAP"},
}

BINANCE_FUTURES = "https://fapi.binance.com"
BYBIT = "https://api.bybit.com"
OKX = "https://www.okx.com"


@dataclass(slots=True)
class ExchangeSnapshot:
    """Current derivatives state on one venue."""

    exchange: str
    asset: str
    funding_rate: float | None = None
    funding_interval_hours: int = 8
    open_interest: float | None = None          # in base units
    open_interest_usd: float | None = None
    mark_price: float | None = None
    index_price: float | None = None
    basis_pct: float | None = None
    available: bool = False
    reason: str = ""
    fetched_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        return {
            "exchange": self.exchange, "asset": self.asset,
            "funding_rate": self.funding_rate,
            "funding_interval_hours": self.funding_interval_hours,
            "open_interest": self.open_interest,
            "open_interest_usd": self.open_interest_usd,
            "mark_price": self.mark_price, "index_price": self.index_price,
            "basis_pct": self.basis_pct,
            "available": self.available, "reason": self.reason,
            "fetched_at": self.fetched_at.isoformat(),
        }


@dataclass(slots=True)
class AggregatedDerivativesSnapshot:
    """The derivatives market across venues, not one exchange's view of it."""

    asset: str
    exchanges: list[ExchangeSnapshot] = field(default_factory=list)
    funding_weighted: float | None = None
    funding_simple_mean: float | None = None
    funding_dispersion: float | None = None
    open_interest_total_usd: float | None = None
    exchange_concentration: float | None = None
    dominant_exchange: str | None = None
    venue_anomaly: str | None = None
    available_venues: int = 0
    total_venues: int = 0
    captured_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset": self.asset,
            "exchanges": [e.to_dict() for e in self.exchanges],
            "funding_weighted": self.funding_weighted,
            "funding_simple_mean": self.funding_simple_mean,
            "funding_dispersion": self.funding_dispersion,
            "open_interest_total_usd": self.open_interest_total_usd,
            "exchange_concentration": self.exchange_concentration,
            "dominant_exchange": self.dominant_exchange,
            "venue_anomaly": self.venue_anomaly,
            "available_venues": self.available_venues,
            "total_venues": self.total_venues,
            "captured_at": self.captured_at.isoformat(),
        }


async def fetch_binance(asset: Asset) -> ExchangeSnapshot:
    symbol = SYMBOLS["binance"][asset.value]
    snapshot = ExchangeSnapshot(exchange="binance", asset=asset.value)
    http = get_http()

    premium, oi = await asyncio.gather(
        http.get_json(f"{BINANCE_FUTURES}/fapi/v1/premiumIndex", provider="binance_futures",
                      params={"symbol": symbol}, cache_ttl=300, rate_limit_per_min=60),
        http.get_json(f"{BINANCE_FUTURES}/fapi/v1/openInterest", provider="binance_futures",
                      params={"symbol": symbol}, cache_ttl=300, rate_limit_per_min=60),
    )

    if not premium.ok:
        snapshot.reason = premium.message[:120]
        return snapshot

    try:
        data = premium.data
        snapshot.funding_rate = float(data["lastFundingRate"])
        snapshot.mark_price = float(data["markPrice"])
        snapshot.index_price = float(data["indexPrice"])
        if snapshot.index_price:
            snapshot.basis_pct = (
                (snapshot.mark_price - snapshot.index_price) / snapshot.index_price * 100.0
            )
        if oi.ok:
            snapshot.open_interest = float(oi.data["openInterest"])
            if snapshot.mark_price:
                snapshot.open_interest_usd = snapshot.open_interest * snapshot.mark_price
        snapshot.available = True
    except (KeyError, ValueError, TypeError) as exc:
        snapshot.reason = f"parse error: {exc}"
    return snapshot


async def fetch_bybit(asset: Asset) -> ExchangeSnapshot:
    symbol = SYMBOLS["bybit"][asset.value]
    snapshot = ExchangeSnapshot(exchange="bybit", asset=asset.value)

    res = await get_http().get_json(
        f"{BYBIT}/v5/market/tickers", provider="bybit",
        params={"category": "linear", "symbol": symbol},
        cache_ttl=300, rate_limit_per_min=60,
    )
    if not res.ok:
        snapshot.reason = res.message[:120]
        return snapshot

    try:
        rows = (res.data or {}).get("result", {}).get("list") or []
        if not rows:
            snapshot.reason = "no ticker returned"
            return snapshot
        row = rows[0]
        snapshot.funding_rate = float(row["fundingRate"]) if row.get("fundingRate") else None
        snapshot.mark_price = float(row["markPrice"]) if row.get("markPrice") else None
        snapshot.index_price = float(row["indexPrice"]) if row.get("indexPrice") else None
        snapshot.open_interest = float(row["openInterest"]) if row.get("openInterest") else None
        if row.get("openInterestValue"):
            snapshot.open_interest_usd = float(row["openInterestValue"])
        elif snapshot.open_interest and snapshot.mark_price:
            snapshot.open_interest_usd = snapshot.open_interest * snapshot.mark_price
        if snapshot.mark_price and snapshot.index_price:
            snapshot.basis_pct = (
                (snapshot.mark_price - snapshot.index_price) / snapshot.index_price * 100.0
            )
        snapshot.available = True
    except (KeyError, ValueError, TypeError) as exc:
        snapshot.reason = f"parse error: {exc}"
    return snapshot


async def fetch_okx(asset: Asset) -> ExchangeSnapshot:
    inst_id = SYMBOLS["okx"][asset.value]
    snapshot = ExchangeSnapshot(exchange="okx", asset=asset.value)
    http = get_http()

    funding, oi, mark = await asyncio.gather(
        http.get_json(f"{OKX}/api/v5/public/funding-rate", provider="okx",
                      params={"instId": inst_id}, cache_ttl=300, rate_limit_per_min=40),
        http.get_json(f"{OKX}/api/v5/public/open-interest", provider="okx",
                      params={"instType": "SWAP", "instId": inst_id},
                      cache_ttl=300, rate_limit_per_min=40),
        http.get_json(f"{OKX}/api/v5/public/mark-price", provider="okx",
                      params={"instType": "SWAP", "instId": inst_id},
                      cache_ttl=300, rate_limit_per_min=40),
    )

    if not funding.ok:
        snapshot.reason = funding.message[:120]
        return snapshot

    try:
        rows = (funding.data or {}).get("data") or []
        if rows:
            snapshot.funding_rate = float(rows[0]["fundingRate"])
        if mark.ok:
            mark_rows = (mark.data or {}).get("data") or []
            if mark_rows:
                snapshot.mark_price = float(mark_rows[0]["markPx"])
        if oi.ok:
            oi_rows = (oi.data or {}).get("data") or []
            if oi_rows:
                snapshot.open_interest = float(oi_rows[0]["oi"])
                if oi_rows[0].get("oiCcy"):
                    base_units = float(oi_rows[0]["oiCcy"])
                    snapshot.open_interest = base_units
                    if snapshot.mark_price:
                        snapshot.open_interest_usd = base_units * snapshot.mark_price
        snapshot.available = snapshot.funding_rate is not None
        if not snapshot.available:
            snapshot.reason = "no funding rate returned"
    except (KeyError, ValueError, TypeError, IndexError) as exc:
        snapshot.reason = f"parse error: {exc}"
    return snapshot


async def aggregate(asset: Asset) -> AggregatedDerivativesSnapshot:
    """One market-wide view, plus a flag when a venue disagrees with the rest."""
    snapshots = await asyncio.gather(
        fetch_binance(asset), fetch_bybit(asset), fetch_okx(asset),
        return_exceptions=True,
    )

    resolved: list[ExchangeSnapshot] = []
    for name, result in zip(("binance", "bybit", "okx"), snapshots, strict=True):
        if isinstance(result, BaseException):
            resolved.append(
                ExchangeSnapshot(exchange=name, asset=asset.value, reason=str(result)[:120])
            )
        else:
            resolved.append(result)

    aggregated = AggregatedDerivativesSnapshot(
        asset=asset.value, exchanges=resolved, total_venues=len(resolved)
    )
    usable = [s for s in resolved if s.available and s.funding_rate is not None]
    aggregated.available_venues = len(usable)

    if not usable:
        return aggregated

    import numpy as np

    rates = [s.funding_rate for s in usable]
    aggregated.funding_simple_mean = round(float(np.mean(rates)), 8)
    aggregated.funding_dispersion = (
        round(float(np.std(rates, ddof=1)), 8) if len(rates) > 1 else 0.0
    )

    # Weight funding by open interest: a venue holding 5% of the market should
    # not move the aggregate as much as one holding 60%.
    weighted_pairs = [
        (s.funding_rate, s.open_interest_usd)
        for s in usable if s.open_interest_usd and s.open_interest_usd > 0
    ]
    if weighted_pairs:
        total_oi = sum(w for _, w in weighted_pairs)
        aggregated.funding_weighted = round(
            sum(r * w for r, w in weighted_pairs) / total_oi, 8
        )
        aggregated.open_interest_total_usd = round(total_oi, 2)
        shares = {
            s.exchange: (s.open_interest_usd or 0) / total_oi
            for s in usable if s.open_interest_usd
        }
        if shares:
            dominant = max(shares.items(), key=lambda kv: kv[1])
            aggregated.dominant_exchange = dominant[0]
            # Herfindahl index: 1.0 means a single venue holds everything.
            aggregated.exchange_concentration = round(
                sum(share ** 2 for share in shares.values()), 4
            )
    else:
        aggregated.funding_weighted = aggregated.funding_simple_mean

    # A venue whose funding sits far from the others is an anomaly, not a
    # market signal. Flagging it prevents one exchange driving the read.
    if len(rates) >= 3 and aggregated.funding_dispersion:
        median = float(np.median(rates))
        for snapshot in usable:
            deviation = abs(snapshot.funding_rate - median)
            if deviation > max(4 * aggregated.funding_dispersion, 0.0004):
                aggregated.venue_anomaly = (
                    f"{snapshot.exchange} funding {snapshot.funding_rate:.6f} deviates "
                    f"from the cross-venue median {median:.6f} - likely a venue-specific "
                    "condition rather than a market-wide one"
                )
                break

    return aggregated


async def backfill_bybit_open_interest(
    asset: Asset, depth_days: int = 900, max_requests: int = 30
) -> dict[str, Any]:
    """Deep open-interest history from Bybit's public endpoint.

    Binance serves ~30 days; Bybit paginates by `endTime` and reaches back
    years. This is the same kind of public data, simply from a venue that keeps
    more of it - no limitation is bypassed.
    """
    from ...history import store

    symbol = SYMBOLS["bybit"][asset.value]
    http = get_http()
    end_ms = int(datetime.now(UTC).timestamp() * 1000)
    floor_ms = int((datetime.now(UTC) - timedelta(days=depth_days)).timestamp() * 1000)

    points: list[tuple[datetime, float]] = []
    seen: set[int] = set()
    requests = 0

    while requests < max_requests:
        res = await http.get_json(
            f"{BYBIT}/v5/market/open-interest", provider="bybit_backfill",
            params={
                "category": "linear", "symbol": symbol,
                "intervalTime": "1d", "limit": 200, "endTime": end_ms,
            },
            cache_ttl=0, rate_limit_per_min=60, retries=2,
        )
        requests += 1
        if not res.ok:
            break

        rows = (res.data or {}).get("result", {}).get("list") or []
        if not rows:
            break

        added = 0
        for row in rows:
            try:
                ts_ms = int(row["timestamp"])
                if ts_ms in seen:
                    continue
                seen.add(ts_ms)
                points.append(
                    (datetime.fromtimestamp(ts_ms / 1000, tz=UTC), float(row["openInterest"]))
                )
                added += 1
            except (KeyError, ValueError, TypeError):
                continue

        oldest = min(int(r["timestamp"]) for r in rows)
        if added == 0 or oldest >= end_ms:
            break
        end_ms = oldest - 1
        if oldest <= floor_ms:
            break

    written = store.save_derivatives(asset, "oi.contracts_bybit", points, source="bybit")
    coverage = store.derivatives_coverage(asset).get("oi.contracts_bybit", {})

    store.record_backfill(
        dataset="open_interest_bybit", asset=asset, timeframe=None,
        earliest=coverage.get("start"), latest=coverage.get("end"),
        rows=coverage.get("rows", 0), source="bybit",
        note=f"{requests} requests, {written} new rows - public endpoint",
    )
    log.info("bybit_oi_backfilled", asset=asset.value, new=written, total=coverage.get("rows", 0))
    return {"asset": asset.value, "new_rows": written, "requests": requests, **coverage}


async def backfill_all_open_interest(assets: list[Asset] | None = None) -> dict[str, Any]:
    assets = assets or Asset.tradables()
    return {
        asset.value: await backfill_bybit_open_interest(asset) for asset in assets
    }

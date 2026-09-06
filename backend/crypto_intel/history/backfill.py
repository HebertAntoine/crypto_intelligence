"""Historical backfill - build years of history instead of waiting months for it.

Every fetch here is paginated backwards from now until the source runs out of
data. Nothing is ever synthesised: when a source has no data for a period, that
period simply does not exist in our database, and `backfill_report()` shows the
real depth per metric.

The whole thing is idempotent - rows are upserted by deterministic id, so
re-running `make backfill` costs API calls but never duplicates or corrupts.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from ..config_loader import asset_meta
from ..core.enums import Asset, Timeframe
from ..core.models import Candle
from ..logging_setup import get_logger
from ..providers.http import get_http
from ..settings import get_settings
from . import store

log = get_logger("history.backfill")

BINANCE_SPOT = "https://api.binance.com"
BINANCE_FUTURES = "https://fapi.binance.com"
YAHOO = "https://query1.finance.yahoo.com"

_INTERVAL = {
    Timeframe.M15: "15m", Timeframe.H1: "1h", Timeframe.H4: "4h",
    Timeframe.D1: "1d", Timeframe.W1: "1w",
}

# How far back it is worth going per timeframe. 15m candles for five years
# would be ~175k rows per asset for very little analytical value, so the
# short timeframes are deliberately capped.
DEFAULT_DEPTH_DAYS: dict[Timeframe, int] = {
    Timeframe.M15: 120,
    Timeframe.H1: 400,
    Timeframe.H4: 900,
    Timeframe.D1: 3600,   # ~10 years: back to the Binance listing date for each pair
    Timeframe.W1: 3600,
}


async def backfill_ohlcv(
    asset: Asset,
    timeframe: Timeframe,
    depth_days: int | None = None,
    max_requests: int = 60,
) -> dict[str, Any]:
    """Page backwards through Binance klines until the source is exhausted."""
    depth = depth_days or DEFAULT_DEPTH_DAYS.get(timeframe, 400)
    symbol = str(asset_meta(asset.value)["binance_symbol"])
    http = get_http()

    end_ms = int(datetime.now(UTC).timestamp() * 1000)
    floor_ms = int((datetime.now(UTC) - timedelta(days=depth)).timestamp() * 1000)

    all_candles: list[Candle] = []
    seen: set[int] = set()
    requests = 0

    while requests < max_requests and end_ms > floor_ms:
        res = await http.get_json(
            f"{BINANCE_SPOT}/api/v3/klines",
            provider="binance_backfill",
            params={
                "symbol": symbol, "interval": _INTERVAL[timeframe],
                "endTime": end_ms, "limit": 1000,
            },
            cache_ttl=0,               # backfill must not read a stale cache
            rate_limit_per_min=110,
            retries=2,
        )
        requests += 1
        if not res.ok or not isinstance(res.data, list) or not res.data:
            break

        batch: list[Candle] = []
        for k in res.data:
            try:
                open_ms = int(k[0])
                if open_ms in seen:
                    continue
                seen.add(open_ms)
                batch.append(
                    Candle(
                        timestamp=datetime.fromtimestamp(open_ms / 1000, tz=UTC),
                        open=float(k[1]), high=float(k[2]), low=float(k[3]),
                        close=float(k[4]), volume=float(k[5]),
                    )
                )
            except (IndexError, ValueError, TypeError):
                continue

        if not batch:
            break
        all_candles.extend(batch)

        oldest_ms = min(int(k[0]) for k in res.data)
        if oldest_ms >= end_ms:
            break                       # no progress: the source has no more history
        end_ms = oldest_ms - 1
        if oldest_ms <= floor_ms:
            break                       # requested depth reached

    all_candles.sort(key=lambda c: c.timestamp)
    written = store.save_candles(asset, timeframe, all_candles, source="binance")
    coverage = store.candle_coverage(asset, timeframe)

    store.record_backfill(
        dataset="ohlcv", asset=asset, timeframe=timeframe,
        earliest=coverage["start"], latest=coverage["end"],
        rows=coverage["rows"], source="binance",
        complete=requests < max_requests,
        note=f"{requests} requests, {written} new rows",
    )
    log.info(
        "backfill_ohlcv", asset=asset.value, timeframe=timeframe.value,
        fetched=len(all_candles), new=written, total=coverage["rows"],
    )
    return {
        "asset": asset.value, "timeframe": timeframe.value,
        "fetched": len(all_candles), "new_rows": written, **coverage,
    }


async def backfill_funding(
    asset: Asset, max_requests: int = 60, depth_days: int = 2200
) -> dict[str, Any]:
    """Funding rate history (one point per 8h) from Binance futures.

    Paginates backwards with `endTime`. Binance serves 500 rows per page here
    even when 1000 are requested, so pagination stops on lack of progress
    rather than on page size.
    """
    symbol = str(asset_meta(asset.value)["binance_symbol"])
    http = get_http()
    end_ms = int(datetime.now(UTC).timestamp() * 1000)
    floor_ms = int((datetime.now(UTC) - timedelta(days=depth_days)).timestamp() * 1000)
    points: list[tuple[datetime, float]] = []
    seen: set[int] = set()
    requests = 0

    while requests < max_requests:
        res = await http.get_json(
            f"{BINANCE_FUTURES}/fapi/v1/fundingRate",
            provider="binance_backfill",
            params={"symbol": symbol, "endTime": end_ms, "limit": 1000},
            cache_ttl=0, rate_limit_per_min=110, retries=2,
        )
        requests += 1
        if not res.ok or not isinstance(res.data, list) or not res.data:
            break

        added = 0
        for row in res.data:
            try:
                ts_ms = int(row["fundingTime"])
                if ts_ms in seen:
                    continue
                seen.add(ts_ms)
                points.append(
                    (datetime.fromtimestamp(ts_ms / 1000, tz=UTC), float(row["fundingRate"]))
                )
                added += 1
            except (KeyError, ValueError, TypeError):
                continue

        oldest = min(int(r["fundingTime"]) for r in res.data)
        # Binance caps this endpoint at 500 rows per page regardless of `limit`,
        # so "page smaller than requested" is NOT a signal that history ended.
        # Only a lack of forward progress (or an empty page) means we are done.
        if added == 0 or oldest >= end_ms:
            break
        end_ms = oldest - 1
        if floor_ms and oldest <= floor_ms:
            break

    written = store.save_derivatives(asset, "funding.rate", points, source="binance_futures")
    coverage = store.derivatives_coverage(asset).get("funding.rate", {})
    store.record_backfill(
        dataset="funding", asset=asset, timeframe=None,
        earliest=coverage.get("start"), latest=coverage.get("end"),
        rows=coverage.get("rows", 0), source="binance_futures",
        note=f"{requests} requests, {written} new rows",
    )
    return {"asset": asset.value, "metric": "funding.rate", "new_rows": written, **coverage}


async def backfill_open_interest(asset: Asset) -> dict[str, Any]:
    """Open interest history.

    Binance's `openInterestHist` only serves roughly the last 30 days - that is
    a hard limit of the source, not of this code. The shallow depth is recorded
    so no study silently assumes years of OI history it does not have.
    """
    symbol = str(asset_meta(asset.value)["binance_symbol"])
    http = get_http()
    points: list[tuple[datetime, float]] = []

    for period, limit in (("1d", 500), ("4h", 500)):
        res = await http.get_json(
            f"{BINANCE_FUTURES}/futures/data/openInterestHist",
            provider="binance_backfill",
            params={"symbol": symbol, "period": period, "limit": limit},
            cache_ttl=0, rate_limit_per_min=110, retries=2,
        )
        if not res.ok or not isinstance(res.data, list):
            continue
        for row in res.data:
            try:
                ts = datetime.fromtimestamp(int(row["timestamp"]) / 1000, tz=UTC)
                points.append((ts, float(row["sumOpenInterestValue"])))
            except (KeyError, ValueError, TypeError):
                continue
        if points:
            break     # daily granularity is enough; do not double-fetch

    written = store.save_derivatives(asset, "oi.value", points, source="binance_futures")
    coverage = store.derivatives_coverage(asset).get("oi.value", {})
    store.record_backfill(
        dataset="open_interest", asset=asset, timeframe=None,
        earliest=coverage.get("start"), latest=coverage.get("end"),
        rows=coverage.get("rows", 0), source="binance_futures",
        complete=False,
        note="Binance publishes only ~30 days of open-interest history (source limit)",
    )
    return {"asset": asset.value, "metric": "oi.value", "new_rows": written, **coverage}


# Yahoo symbol -> our metric name. These are the macro series the analysis uses.
_YAHOO_SERIES = {
    "^GSPC": "macro.sp500", "^IXIC": "macro.nasdaq", "^DJI": "macro.dow",
    "DX-Y.NYB": "macro.dxy", "^VIX": "macro.vix", "CL=F": "macro.oil_wti",
    "GC=F": "macro.gold", "^TNX": "macro.us10y_yahoo", "^FVX": "macro.us5y_yahoo",
    "^IRX": "macro.us13w_yahoo",
}


async def backfill_macro(years: int = 8) -> list[dict[str, Any]]:
    """Daily macro history from Yahoo Finance (no key required)."""
    http = get_http()
    out: list[dict[str, Any]] = []

    for symbol, metric in _YAHOO_SERIES.items():
        res = await http.get_json(
            f"{YAHOO}/v8/finance/chart/{symbol}",
            provider="yahoo_backfill",
            params={"interval": "1d", "range": f"{years}y"},
            cache_ttl=0, rate_limit_per_min=30, retries=2,
        )
        if not res.ok:
            out.append({"metric": metric, "rows": 0, "error": res.message[:80]})
            continue
        try:
            block = ((res.data or {}).get("chart", {}).get("result") or [{}])[0]
            stamps = block.get("timestamp") or []
            closes = (block.get("indicators", {}).get("quote") or [{}])[0].get("close") or []
        except (KeyError, IndexError, TypeError):
            out.append({"metric": metric, "rows": 0, "error": "unparsable response"})
            continue

        points = []
        for ts_raw, close in zip(stamps, closes, strict=False):
            # Yahoo returns null on market holidays - skip, never carry forward.
            if close is None:
                continue
            try:
                points.append((datetime.fromtimestamp(int(ts_raw), tz=UTC), float(close)))
            except (TypeError, ValueError, OSError):
                continue

        written = store.save_macro(metric, points, source="yahoo_finance")
        cov = store.macro_coverage().get(metric, {})
        store.record_backfill(
            dataset="macro", asset=None, timeframe=None,
            earliest=cov.get("start"), latest=cov.get("end"),
            rows=cov.get("rows", 0), source="yahoo_finance",
            note=f"{metric}: {written} new rows",
        )
        out.append({"metric": metric, "new_rows": written, **cov})

    return out


async def backfill_fred(years: int = 12) -> list[dict[str, Any]]:
    """FRED macro series. Requires the free FRED_API_KEY.

    Without a key this returns an explicit not-configured entry per series
    rather than an empty success.
    """
    settings = get_settings()
    if not settings.fred_api_key.strip():
        return [{
            "metric": "fred.*", "rows": 0,
            "error": "UNAVAILABLE - FRED_API_KEY not set (free: https://fredaccount.stlouisfed.org/apikeys)",
        }]

    from ..providers.macro.fred import SERIES

    http = get_http()
    start = (datetime.now(UTC) - timedelta(days=365 * years)).strftime("%Y-%m-%d")
    out: list[dict[str, Any]] = []

    for series_id, (metric, _unit, _label) in SERIES.items():
        res = await http.get_json(
            "https://api.stlouisfed.org/fred/series/observations",
            provider="fred_backfill",
            params={
                "series_id": series_id, "api_key": settings.fred_api_key,
                "file_type": "json", "observation_start": start,
            },
            cache_ttl=0, rate_limit_per_min=50, retries=2,
        )
        if not res.ok:
            out.append({"metric": metric, "rows": 0, "error": res.message[:80]})
            continue

        points = []
        for row in (res.data or {}).get("observations", []):
            raw = row.get("value")
            if raw in (None, ".", ""):
                continue          # FRED marks missing observations with "."
            try:
                points.append(
                    (datetime.strptime(row["date"], "%Y-%m-%d").replace(tzinfo=UTC), float(raw))
                )
            except (KeyError, ValueError, TypeError):
                continue

        written = store.save_macro(metric, points, source="fred")
        cov = store.macro_coverage().get(metric, {})
        store.record_backfill(
            dataset="macro_fred", asset=None, timeframe=None,
            earliest=cov.get("start"), latest=cov.get("end"),
            rows=cov.get("rows", 0), source="fred",
            note=f"{series_id} -> {metric}",
        )
        out.append({"metric": metric, "series_id": series_id, "new_rows": written, **cov})

    return out


async def backfill_etf() -> dict[str, Any]:
    """ETF flows already have their own storage; refresh and report depth."""
    from ..db import repo
    from ..providers.base import FetchRequest
    from ..providers.registry import get_registry

    registry = get_registry()
    out: dict[str, Any] = {}
    # Only BTC and ETH have US spot ETFs; SOL is deliberately absent.
    for asset in (Asset.BTC, Asset.ETH):
        res = await registry.fetch(FetchRequest(capability="etf.flows", asset=asset))
        flows = repo.get_etf_flows(asset, days=4000)
        if flows:
            earliest = min(f["date"] for f in flows)
            latest = max(f["date"] for f in flows)
            store.record_backfill(
                dataset="etf_flows", asset=asset, timeframe=None,
                earliest=earliest, latest=latest, rows=len(flows),
                source=flows[-1].get("import_source", "unknown"),
                note=f"{len({f['ticker'] for f in flows})} funds",
            )
            out[asset.value] = {
                "rows": len(flows), "start": earliest, "end": latest,
                "funds": sorted({f["ticker"] for f in flows}),
                "days": round((latest - earliest).total_seconds() / 86400.0, 1),
            }
        else:
            out[asset.value] = {"rows": 0, "error": res.user_message}
    return out


async def run_backfill(
    assets: list[Asset] | None = None,
    timeframes: list[Timeframe] | None = None,
    depth_days: int | None = None,
    skip_macro: bool = False,
) -> dict[str, Any]:
    """Full backfill. Idempotent and resumable."""
    assets = assets or Asset.tradables()
    timeframes = timeframes or [Timeframe.D1, Timeframe.H4, Timeframe.H1, Timeframe.W1]

    summary: dict[str, Any] = {"ohlcv": [], "funding": [], "open_interest": [], "macro": [], "etf": {}}

    for asset in assets:
        for tf in timeframes:
            try:
                summary["ohlcv"].append(await backfill_ohlcv(asset, tf, depth_days))
            except Exception as exc:
                log.warning("backfill_ohlcv_failed", asset=asset.value, tf=tf.value, error=str(exc))
                summary["ohlcv"].append({"asset": asset.value, "timeframe": tf.value, "error": str(exc)[:100]})

        try:
            summary["funding"].append(await backfill_funding(asset))
        except Exception as exc:
            summary["funding"].append({"asset": asset.value, "error": str(exc)[:100]})

        try:
            summary["open_interest"].append(await backfill_open_interest(asset))
        except Exception as exc:
            summary["open_interest"].append({"asset": asset.value, "error": str(exc)[:100]})

    if not skip_macro:
        try:
            summary["macro"] = await backfill_macro()
        except Exception as exc:
            summary["macro"] = [{"error": str(exc)[:100]}]
        try:
            summary["macro_fred"] = await backfill_fred()
        except Exception as exc:
            summary["macro_fred"] = [{"error": str(exc)[:100]}]

    try:
        summary["etf"] = await backfill_etf()
    except Exception as exc:
        summary["etf"] = {"error": str(exc)[:100]}

    summary["coverage"] = store.backfill_report()
    return summary


def coverage_table() -> list[dict[str, Any]]:
    """Documented historical depth per dataset - the honest answer to
    'how much history do we actually have?'."""
    return store.backfill_report()

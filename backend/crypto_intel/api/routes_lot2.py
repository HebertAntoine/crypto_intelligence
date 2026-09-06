"""LOT 2 endpoints: history, research, charts, calendar, knowledge, daily report."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from ..core.enums import Asset, Timeframe
from ..db import repo
from ..engines.technical import indicators as ind
from ..history import backfill as backfill_module
from ..history import snapshots, store
from ..knowledge.store import knowledge_stats
from ..logging_setup import get_logger
from ..reports.daily import render_daily_report
from ..research import calibration, etf_study, event_study
from ..scheduler import scheduler_state

log = get_logger("api.lot2")
router = APIRouter()


def _parse_asset(symbol: str) -> Asset:
    try:
        return Asset(symbol.upper())
    except ValueError:
        raise HTTPException(404, f"Unknown asset '{symbol}'. Supported: BTC, ETH, SOL.") from None


# --- charts ---------------------------------------------------------------

@router.get("/chart/{symbol}")
async def chart(
    symbol: str,
    timeframe: str = Query("1d"),
    limit: int = Query(400, le=2000),
    indicators: str = Query("ema20,ema50,ema200,bb,rsi,macd"),
) -> dict[str, Any]:
    """Candles plus overlays, served from the local history store.

    Reading from storage rather than re-fetching keeps chart navigation instant
    and means the chart shows exactly the data the analysis used.
    """
    asset = _parse_asset(symbol)
    try:
        tf = Timeframe(timeframe)
    except ValueError:
        raise HTTPException(400, f"Unknown timeframe '{timeframe}'") from None

    df = store.load_candles(asset, tf, limit=limit)
    if df.empty:
        return {
            "asset": asset.value, "timeframe": tf.value, "available": False,
            "reason": (
                "UNAVAILABLE - no stored candles for this timeframe. "
                "Run `make backfill` to populate history."
            ),
            "candles": [],
        }

    wanted = {name.strip().lower() for name in indicators.split(",") if name.strip()}
    close = df["close"]

    def series(values) -> list[float | None]:
        # None (not 0) for the warm-up region, so the chart draws a gap rather
        # than a fabricated line at zero.
        return [None if v != v else round(float(v), 8) for v in values]

    overlays: dict[str, Any] = {}
    if "ema20" in wanted:
        overlays["ema20"] = series(ind.ema(close, 20))
    if "ema50" in wanted:
        overlays["ema50"] = series(ind.ema(close, 50))
    if "ema200" in wanted:
        overlays["ema200"] = series(ind.ema(close, 200))
    if "bb" in wanted:
        upper, middle, lower = ind.bollinger_bands(close, 20, 2.0)
        overlays["bb_upper"] = series(upper)
        overlays["bb_middle"] = series(middle)
        overlays["bb_lower"] = series(lower)

    panels: dict[str, Any] = {}
    if "rsi" in wanted:
        panels["rsi"] = series(ind.rsi(close, 14))
    if "macd" in wanted:
        macd_line, signal_line, histogram = ind.macd(close)
        panels["macd"] = series(macd_line)
        panels["macd_signal"] = series(signal_line)
        panels["macd_hist"] = series(histogram)

    # Levels and patterns come from the live engine so the chart matches the
    # analysis rather than recomputing them differently.
    levels: dict[str, Any] = {"support": [], "resistance": []}
    patterns: list[dict[str, Any]] = []
    try:
        from ..core.models import Candle, OHLCVSeries, Provenance
        from ..engines.technical.engine import TechnicalAnalysisEngine

        candles = [
            Candle(timestamp=ts, open=r.open, high=r.high, low=r.low, close=r.close, volume=r.volume)
            for ts, r in df.iterrows()
        ]
        snapshot = TechnicalAnalysisEngine().analyze(
            OHLCVSeries(
                asset=asset, timeframe=tf, candles=candles,
                provenance=Provenance(source="local history", provider="ohlcv_store"),
            )
        )
        levels = {
            "support": [
                {"price": lv.price, "touches": lv.touches, "strength": lv.strength}
                for lv in snapshot.levels_support
            ],
            "resistance": [
                {"price": lv.price, "touches": lv.touches, "strength": lv.strength}
                for lv in snapshot.levels_resistance
            ],
        }
        patterns = [
            {
                "pattern": p.pattern, "confidence": p.confidence,
                "state": p.confirmation_state.value, "direction": p.direction.value,
                "invalidation": p.invalidation_level,
                "start_index": p.start_index, "end_index": p.end_index,
                "notes": p.notes,
            }
            for p in snapshot.patterns
        ]
    except Exception as exc:
        log.debug("chart_overlay_failed", error=str(exc))

    return {
        "asset": asset.value, "timeframe": tf.value, "available": True,
        "candles": [
            {
                "time": ts.isoformat(),
                "open": round(float(r.open), 8), "high": round(float(r.high), 8),
                "low": round(float(r.low), 8), "close": round(float(r.close), 8),
                "volume": round(float(r.volume), 4),
            }
            for ts, r in df.iterrows()
        ],
        "overlays": overlays,
        "panels": panels,
        "levels": levels,
        "patterns": patterns,
        "markers": _chart_markers(asset, df.index.min(), df.index.max()),
    }


def _chart_markers(asset: Asset, start, end) -> list[dict[str, Any]]:
    """Event markers: macro releases, regulatory items and large ETF flows."""
    markers: list[dict[str, Any]] = []
    start_dt = start.to_pydatetime() if hasattr(start, "to_pydatetime") else start
    end_dt = end.to_pydatetime() if hasattr(end, "to_pydatetime") else end

    for event in repo.recent_events(days=3650, limit=200):
        scheduled = event["scheduled_at"]
        if start_dt <= scheduled <= end_dt:
            markers.append({
                "time": scheduled.isoformat(), "kind": event["kind"],
                "label": event["name"], "importance": event["importance"],
                "category": "MACRO" if event["kind"] in ("FOMC", "CPI", "NFP", "PCE") else "OTHER",
            })

    for event in repo.upcoming_events(days=60):
        markers.append({
            "time": event["scheduled_at"].isoformat(), "kind": event["kind"],
            "label": event["name"], "importance": event["importance"],
            "category": "MACRO", "upcoming": True,
        })

    if asset in (Asset.BTC, Asset.ETH):
        flows = repo.get_etf_flows(asset, days=4000)
        by_day: dict[Any, float] = {}
        for row in flows:
            day = row["date"].replace(hour=0, minute=0, second=0, microsecond=0)
            by_day[day] = by_day.get(day, 0.0) + row["flow_musd"]
        for day, total in by_day.items():
            if start_dt <= day <= end_dt and abs(total) >= 500:
                markers.append({
                    "time": day.isoformat(), "kind": "ETF",
                    "label": f"ETF net {total:+.0f}M USD",
                    "importance": "IMPORTANT",
                    "category": "ETF",
                    "direction": "in" if total > 0 else "out",
                })
    return markers[:200]


# --- ETF vs price ----------------------------------------------------------

@router.get("/etf-vs-price/{symbol}")
async def etf_vs_price(
    symbol: str,
    days: int = Query(365, le=1200),
    lag_days: int = Query(0, ge=0, le=14),
) -> dict[str, Any]:
    """Aligned price and ETF flow series, with an optional visual lag.

    The lag shifts flows forward so the eye can check whether flows move before
    price. It is a visual aid only - the measured relationship lives in
    /api/research/etf, and a visual lead proves nothing on its own.
    """
    asset = _parse_asset(symbol)
    if asset is Asset.SOL:
        return {
            "asset": asset.value, "available": False,
            "reason": "UNAVAILABLE - SOL has no US spot ETF",
        }

    flows = etf_study.build_flow_series(asset)
    prices = etf_study.build_price_frame(asset)
    if flows.empty or prices.empty:
        return {
            "asset": asset.value, "available": False,
            "reason": "UNAVAILABLE - missing ETF flows or price history (run `make backfill`)",
        }

    signals = etf_study.build_signals(flows)
    cutoff = datetime.now(UTC) - timedelta(days=days)
    signals = signals[signals.index >= cutoff]
    price_slice = prices[prices.index >= cutoff]

    if lag_days:
        # Shift the flow series forward in time: a flow on day t is drawn at
        # t+lag, so a visual match means flows moved first.
        signals = signals.copy()
        signals.index = signals.index + timedelta(days=lag_days)

    joined = price_slice[["close"]].join(signals, how="left")

    def clean(values) -> list[float | None]:
        return [None if v != v else round(float(v), 4) for v in values]

    return {
        "asset": asset.value, "available": True, "lag_days": lag_days,
        "dates": [ts.isoformat() for ts in joined.index],
        "price": clean(joined["close"]),
        "flow": clean(joined.get("flow", [])),
        "ma3": clean(joined.get("ma3", [])),
        "ma5": clean(joined.get("ma5", [])),
        "ma7": clean(joined.get("ma7", [])),
        "cumulative": clean(joined.get("cum30", [])),
        "caveat": (
            "A visual lead does NOT establish causality. The measured forward "
            "relationship is in /api/research/etf, where it is corrected for "
            "multiple comparisons and validated out of sample."
        ),
    }


# --- research --------------------------------------------------------------

@router.get("/research/etf/{symbol}")
async def research_etf(symbol: str) -> dict[str, Any]:
    asset = _parse_asset(symbol)
    return await asyncio.to_thread(etf_study.run_lag_study, asset)


@router.get("/research/etf/{symbol}/buckets")
async def research_etf_buckets(symbol: str, signal: str = Query("ma7")) -> dict[str, Any]:
    asset = _parse_asset(symbol)
    return await asyncio.to_thread(etf_study.run_bucket_study, asset, signal)


@router.get("/research/etf/{symbol}/validation")
async def research_etf_validation(
    symbol: str, signal: str = Query("ma7"), horizon: int = Query(14)
) -> dict[str, Any]:
    asset = _parse_asset(symbol)
    return await asyncio.to_thread(etf_study.run_split_validation, asset, signal, horizon)


@router.get("/research/events/{symbol}")
async def research_events(symbol: str) -> dict[str, Any]:
    asset = _parse_asset(symbol)
    return await asyncio.to_thread(event_study.run_all_events, asset)


@router.get("/research/calibration")
async def research_calibration(asset: str | None = None) -> dict[str, Any]:
    assets = [_parse_asset(asset)] if asset else None
    return await asyncio.to_thread(calibration.run_full_calibration, assets)


@router.post("/research/run")
async def research_run() -> dict[str, Any]:
    """Run every study and persist results. Slow; intended to be occasional."""
    from ..research.runner import run_all

    result = await asyncio.to_thread(run_all)
    return {
        "started_at": result["started_at"], "finished_at": result["finished_at"],
        "duration_seconds": result["duration_seconds"],
        "persisted": result["persisted"], "summary": result["summary"],
    }


# --- history ---------------------------------------------------------------

@router.get("/history/coverage")
async def history_coverage() -> dict[str, Any]:
    """Documented historical depth per dataset - the honest answer to
    'how much history do we actually have?'."""
    coverage = backfill_module.coverage_table()
    per_asset: dict[str, Any] = {}
    for asset in Asset.tradables():
        per_asset[asset.value] = {
            "candles": {
                tf.value: store.candle_coverage(asset, tf)
                for tf in (Timeframe.D1, Timeframe.H4, Timeframe.H1, Timeframe.W1)
            },
            "derivatives": store.derivatives_coverage(asset),
        }
    return {
        "datasets": coverage,
        "per_asset": per_asset,
        "macro": store.macro_coverage(),
        "snapshots": snapshots.snapshot_stats(),
    }


@router.post("/history/backfill")
async def history_backfill(
    asset: str | None = None, timeframe: str | None = None
) -> dict[str, Any]:
    """Trigger a backfill. Idempotent - safe to call repeatedly."""
    assets = [_parse_asset(asset)] if asset else None
    timeframes = [Timeframe(timeframe)] if timeframe else None
    return await backfill_module.run_backfill(assets=assets, timeframes=timeframes)


@router.get("/snapshots/{symbol}")
async def asset_snapshots(
    symbol: str, kind: str = Query("analysis"), hours: int = Query(168, le=8760)
) -> dict[str, Any]:
    """The system's recorded memory for one asset."""
    asset = _parse_asset(symbol)
    since = datetime.now(UTC) - timedelta(hours=hours)
    rows = snapshots.load_snapshots(kind, asset, since=since, limit=1000)
    return {
        "asset": asset.value, "kind": kind, "count": len(rows),
        "snapshots": [
            {
                "captured_at": r["captured_at"].isoformat(),
                "price": r["price"], "payload": r["payload"],
            }
            for r in rows
        ],
    }


# --- calendar --------------------------------------------------------------

@router.get("/calendar")
async def calendar(days: int = Query(30, le=180)) -> dict[str, Any]:
    """Catalyst calendar, grouped by proximity.

    Categories are explicit, and each entry states whether the date is KNOWN
    (scheduled and published) or ESTIMATED - a distinction that matters when
    planning around an event.
    """
    now = datetime.now(UTC)
    upcoming = repo.upcoming_events(days=days, limit=100)

    entries: list[dict[str, Any]] = []
    for event in upcoming:
        kind = event["kind"]
        category = (
            "FED" if kind == "FOMC"
            else "MACRO" if kind in ("CPI", "PCE", "NFP", "GDP")
            else "REGULATION" if kind in ("REGULATION", "SEC", "CFTC")
            else "OTHER"
        )
        entries.append({
            "id": event["id"],
            "name": event["name"],
            "category": category,
            "kind": kind,
            "scheduled_at": event["scheduled_at"].isoformat(),
            "hours_until": event["hours_until"],
            "importance": event["importance"],
            "assets": event["assets"] or ["BTC", "ETH", "SOL"],
            # Calendar entries come from officially published schedules.
            "certainty": "KNOWN",
            "source_name": event.get("source_name") or "config/macro_calendar.yaml",
            "source_url": event.get("source_url"),
        })

    # Regulatory items already published are context, not upcoming catalysts,
    # so they are returned separately rather than mixed into the timeline.
    recent_regulation = [
        {
            "name": e["name"], "category": "REGULATION", "kind": e["kind"],
            "scheduled_at": e["scheduled_at"].isoformat(),
            "hours_until": e["hours_until"], "importance": e["importance"],
            "legal_status": e.get("legal_status"),
            "source_url": e.get("source_url"), "certainty": "KNOWN",
        }
        for e in repo.recent_events(days=14, limit=30)
        if e["kind"] not in ("FOMC", "CPI", "PCE", "NFP")
    ]

    def within(hours: float) -> list[dict[str, Any]]:
        return [e for e in entries if 0 <= (e["hours_until"] or 0) <= hours]

    return {
        "generated_at": now.isoformat(),
        "within_24h": within(24),
        "within_3d": within(72),
        "within_7d": within(168),
        "within_30d": within(720),
        "all_upcoming": entries,
        "recent_regulation": recent_regulation,
        "note": (
            "Macro dates come from config/macro_calendar.yaml, maintained from official "
            "publication schedules. Protocol and token events are not yet tracked - "
            "they are absent rather than estimated."
        ),
    }


# --- daily report ----------------------------------------------------------

@router.get("/daily-report")
async def daily_report() -> dict[str, Any]:
    """The two-minute market read."""
    from .routes import get_analysis, global_market

    analyses = await asyncio.gather(
        *(get_analysis(a) for a in Asset.tradables()), return_exceptions=True
    )
    valid = [a for a in analyses if not isinstance(a, BaseException)]
    if not valid:
        raise HTTPException(503, "No asset analysis could be produced")

    try:
        gv = await global_market()
    except Exception as exc:
        log.warning("daily_global_failed", error=str(exc))
        gv = {}

    text = render_daily_report(valid, gv)
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "text": text,
        "assets": [a.asset.value for a in valid],
    }


# --- knowledge -------------------------------------------------------------

@router.get("/knowledge/documents")
async def knowledge_documents() -> dict[str, Any]:
    """Indexed documents, for the Knowledge page."""
    from sqlalchemy import select

    from ..db.base import KnowledgeDocumentRow
    from ..db.session import session_scope

    with session_scope() as s:
        rows = s.execute(
            select(KnowledgeDocumentRow).order_by(KnowledgeDocumentRow.ingested_at.desc())
        ).scalars().all()
        documents = [
            {
                "id": r.id, "title": r.title, "category": r.category,
                "file_type": r.file_type, "pages": r.pages,
                "chunks": r.chunk_count,
                "ingested_at": (
                    r.ingested_at if r.ingested_at.tzinfo
                    else r.ingested_at.replace(tzinfo=UTC)
                ).isoformat(),
                "path": r.path,
            }
            for r in rows
        ]

    return {"documents": documents, "stats": knowledge_stats()}


# --- scheduler -------------------------------------------------------------

@router.get("/scheduler/status")
async def scheduler_status() -> dict[str, Any]:
    state = scheduler_state()
    from ..settings import get_settings

    return {
        "enabled": get_settings().scheduler_enabled,
        "started_at": state.get("started_at"),
        "runs": state.get("runs", {}),
        "last_error": state.get("last_error"),
        "snapshots": snapshots.snapshot_stats(),
    }

"""HTTP API. The frontend talks only to this."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from ..core.enums import Asset, Timeframe
from ..db import repo
from ..evaluation.outcomes import OutcomeEvaluator
from ..knowledge.ingest import ingest_directory
from ..knowledge.store import get_retriever, knowledge_stats
from ..llm.factory import llm_status
from ..logging_setup import get_logger
from ..pipeline.orchestrator import AssetAnalysis, get_pipeline
from ..providers.base import FetchRequest
from ..providers.registry import get_registry
from ..reports.renderer import render_report
from ..settings import get_settings

log = get_logger("api")
router = APIRouter()

# Analyses are cached briefly: a full run hits ~20 endpoints, so re-running it
# on every dashboard tab switch would be wasteful and rate-limit us.
_CACHE: dict[str, tuple[datetime, AssetAnalysis]] = {}
_CACHE_TTL_SECONDS = 180
_LOCKS: dict[str, asyncio.Lock] = {}


def _parse_asset(symbol: str) -> Asset:
    try:
        return Asset(symbol.upper())
    except ValueError:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown asset '{symbol}'. Supported: BTC, ETH, SOL.",
        ) from None


async def get_analysis(asset: Asset, refresh: bool = False) -> AssetAnalysis:
    key = asset.value
    now = datetime.now(UTC)

    if not refresh:
        cached = _CACHE.get(key)
        if cached and (now - cached[0]).total_seconds() < _CACHE_TTL_SECONDS:
            return cached[1]

    lock = _LOCKS.setdefault(key, asyncio.Lock())
    async with lock:
        # Another request may have populated the cache while we waited.
        cached = _CACHE.get(key)
        if not refresh and cached and (datetime.now(UTC) - cached[0]).total_seconds() < _CACHE_TTL_SECONDS:
            return cached[1]

        pipeline = get_pipeline()
        analysis = await pipeline.analyze_asset(asset)
        _CACHE[key] = (datetime.now(UTC), analysis)

        # Persist so the evaluation engine can score it later.
        try:
            conv = analysis.conviction
            repo.save_report(
                report_id=analysis.report_id, asset=asset,
                payload=analysis.model_dump(mode="json"),
                text_report=render_report(analysis),
                price=analysis.price,
                convictions={
                    "short": conv["short"]["score"],
                    "medium": conv["medium"]["score"],
                    "long": conv["long"]["score"],
                },
                scores=analysis.scores,
                confidence=conv.get("overall_confidence", 0.0),
                market_regime=analysis.market_regime,
                llm_used=analysis.llm_used,
            )
        except Exception as exc:
            log.warning("report_persist_failed", error=str(exc))

        return analysis


@router.get("/health")
async def health() -> dict[str, Any]:
    s = get_settings()
    return {
        "status": "ok",
        "version": "0.1.0",
        "mock_mode": s.mock_mode,
        "llm": llm_status(),
        "time": datetime.now(UTC).isoformat(),
    }


@router.get("/assets")
async def list_assets() -> list[dict[str, Any]]:
    """Dashboard cards for BTC / ETH / SOL."""
    out = []
    analyses = await asyncio.gather(
        *(get_analysis(a) for a in Asset.tradables()), return_exceptions=True
    )
    for asset, res in zip(Asset.tradables(), analyses, strict=True):
        if isinstance(res, BaseException):
            log.warning("asset_analysis_failed", asset=asset.value, error=str(res))
            out.append({
                "asset": asset.value, "available": False,
                "error": f"Analysis failed: {res}",
            })
            continue
        conv = res.conviction
        out.append({
            "asset": asset.value,
            "available": True,
            "price": res.price,
            "change_24h_pct": res.change_24h_pct,
            "change_7d_pct": res.change_7d_pct,
            "market_cap": res.market_cap,
            "market_regime": res.market_regime,
            "conviction_short": conv["short"]["score"],
            "conviction_medium": conv["medium"]["score"],
            "conviction_long": conv["long"]["score"],
            "label_short": conv["short"]["label"],
            "label_medium": conv["medium"]["label"],
            "confidence": conv.get("overall_confidence", 0.0),
            "domains_available": conv.get("domains_available", 0),
            "domains_missing": conv.get("domains_missing", []),
            "contradiction_strength": res.contradictions.get("max_strength", 0.0),
            "generated_at": res.generated_at.isoformat(),
            "alerts": len(res.alerts),
            "llm_used": res.llm_used,
        })
    return out


@router.get("/assets/{symbol}")
async def asset_detail(symbol: str, refresh: bool = Query(False)) -> dict[str, Any]:
    analysis = await get_analysis(_parse_asset(symbol), refresh=refresh)
    return analysis.model_dump(mode="json")


@router.get("/assets/{symbol}/report")
async def asset_report(symbol: str, refresh: bool = Query(False)) -> dict[str, Any]:
    analysis = await get_analysis(_parse_asset(symbol), refresh=refresh)
    return {
        "asset": analysis.asset.value,
        "report_id": analysis.report_id,
        "generated_at": analysis.generated_at.isoformat(),
        "text": render_report(analysis),
    }


@router.get("/assets/{symbol}/technical")
async def asset_technical(symbol: str, timeframe: str | None = None) -> dict[str, Any]:
    analysis = await get_analysis(_parse_asset(symbol))
    if timeframe:
        try:
            tf = Timeframe(timeframe)
        except ValueError:
            raise HTTPException(400, f"Unknown timeframe '{timeframe}'") from None
        snap = analysis.technical.get(tf.value)
        if not snap:
            raise HTTPException(404, f"No data for timeframe {tf.value}")
        return snap
    return {"timeframes": analysis.technical, "mtf": analysis.domains.get("mtf")}


@router.get("/assets/{symbol}/domain/{domain}")
async def asset_domain(symbol: str, domain: str) -> dict[str, Any]:
    analysis = await get_analysis(_parse_asset(symbol))
    data = analysis.domains.get(domain)
    if data is None:
        raise HTTPException(
            404,
            f"Unknown domain '{domain}'. Available: {sorted(k for k in analysis.domains)}",
        )
    return {"domain": domain, "data": data, "score": analysis.scores.get(domain)}


@router.get("/assets/{symbol}/sources")
async def asset_sources(symbol: str) -> dict[str, Any]:
    analysis = await get_analysis(_parse_asset(symbol))
    return {
        "asset": analysis.asset.value,
        "sources": [s.model_dump(mode="json") for s in analysis.sources],
        "ok": sum(1 for s in analysis.sources if s.ok),
        "total": len(analysis.sources),
    }


@router.get("/why/{evidence_id}")
async def why(evidence_id: str) -> dict[str, Any]:
    """Explainability: unroll a conclusion back to the raw observations."""
    observations = repo.observations_by_ids([evidence_id])
    if observations:
        o = observations[0]
        return {
            "kind": "FACT",
            "id": o.id,
            "metric": o.metric,
            "asset": o.asset.value if o.asset else None,
            "value": o.value,
            "unit": o.unit,
            "timestamp": o.timestamp.isoformat(),
            "freshness": o.freshness.value,
            "confidence": o.confidence,
            "quality": o.quality.value,
            "source": o.provenance.source,
            "provider": o.provenance.provider,
            "source_url": o.provenance.source_url,
            "fetched_at": o.provenance.fetched_at.isoformat(),
            "description": o.describe(),
        }
    raise HTTPException(404, f"No evidence found with id '{evidence_id}'")


@router.post("/why/batch")
async def why_batch(evidence_ids: list[str]) -> list[dict[str, Any]]:
    """Evidence behind a whole conclusion, in one call."""
    observations = repo.observations_by_ids(evidence_ids[:100])
    return [
        {
            "id": o.id, "metric": o.metric,
            "asset": o.asset.value if o.asset else None,
            "value": o.value, "unit": o.unit,
            "timestamp": o.timestamp.isoformat(),
            "freshness": o.freshness.value,
            "source": o.provenance.source,
            "provider": o.provenance.provider,
            "source_url": o.provenance.source_url,
            "description": o.describe(),
        }
        for o in observations
    ]


@router.get("/global")
async def global_market() -> dict[str, Any]:
    """GLOBAL MARKET view."""
    pipeline = get_pipeline()
    gdata = await pipeline.collect_global()

    analyses = await asyncio.gather(
        *(get_analysis(a) for a in Asset.tradables()), return_exceptions=True
    )
    valid = [a for a in analyses if not isinstance(a, BaseException)]

    liquidity = None
    stables = gdata.get("stablecoins")
    if stables and stables.ok:
        liquidity = pipeline.liquidity.analyze(stables.observations).model_dump(mode="json")

    macro_obs = []
    for key in ("macro_series", "macro_indices"):
        r = gdata.get(key)
        if r and r.ok:
            macro_obs.extend(r.observations)
    macro = pipeline.macro.analyze(
        macro_obs, unavailable_reason=None if macro_obs else "UNAVAILABLE - no macro data"
    ).model_dump(mode="json")

    news_res = gdata.get("news")
    news_items = (news_res.raw or {}).get("items", []) if news_res and news_res.raw else []
    reg_res = gdata.get("regulation")
    reg_items = (reg_res.raw or {}).get("items", []) if reg_res and reg_res.raw else []

    news = pipeline.news.analyze(
        news_items, unavailable_reason=None if news_items else "UNAVAILABLE - no news feed"
    ).model_dump(mode="json")
    regulation = pipeline.regulation.analyze(
        reg_items, unavailable_reason=None if reg_items else "UNAVAILABLE - no regulatory feed"
    ).model_dump(mode="json")
    geo = pipeline.geo.analyze(
        news_items + reg_items,
        unavailable_reason=None if (news_items or reg_items) else "UNAVAILABLE - no feeds",
    ).model_dump(mode="json")

    rwa = None
    rwa_res = gdata.get("rwa")
    if rwa_res and rwa_res.ok:
        rwa = {
            o.metric: {"value": o.value, "unit": o.unit, "source": o.provenance.source}
            for o in rwa_res.observations
        }

    etf_summary = {}
    for a in valid:
        etf = a.domains.get("etf") or {}
        if etf.get("available"):
            etf_summary[a.asset.value] = {
                "latest_total": etf.get("latest_total"),
                "latest_date": etf.get("latest_date"),
                "ma_5d": etf.get("ma_5d"),
                "cumulative_30d": etf.get("cumulative_30d"),
                "streak_days": etf.get("streak_days"),
                "streak_direction": etf.get("streak_direction"),
            }
        else:
            etf_summary[a.asset.value] = {"available": False, "reason": etf.get("unavailable_reason")}

    avg_conviction = (
        sum(a.conviction["medium"]["score"] for a in valid) / len(valid) if valid else 0.0
    )
    risk_regime = (
        "RISK ON" if avg_conviction > 20
        else "RISK OFF" if avg_conviction < -20
        else "NEUTRAL"
    )

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "risk_regime": risk_regime,
        "average_conviction": round(avg_conviction, 1),
        "assets": [
            {
                "asset": a.asset.value, "price": a.price,
                "change_24h_pct": a.change_24h_pct,
                "conviction_medium": a.conviction["medium"]["score"],
                "regime": a.market_regime,
            }
            for a in valid
        ],
        "etf": etf_summary,
        "liquidity": liquidity,
        "macro": macro,
        "news": news,
        "regulation": regulation,
        "geopolitics": geo,
        "rwa": rwa,
        "calendar": repo.upcoming_events(days=30),
        "alerts": repo.recent_alerts(limit=25),
    }


@router.get("/alerts")
async def alerts(limit: int = Query(50, le=200), asset: str | None = None) -> list[dict[str, Any]]:
    return repo.recent_alerts(limit=limit, asset=_parse_asset(asset) if asset else None)


@router.get("/events")
async def events(days: int = Query(30, le=365)) -> dict[str, Any]:
    return {
        "upcoming": repo.upcoming_events(days=days),
        "recent": repo.recent_events(days=14),
    }


@router.get("/providers")
async def providers() -> dict[str, Any]:
    registry = get_registry()
    statuses = await registry.statuses()
    return {
        "mock_mode": get_settings().mock_mode,
        "providers": [
            {
                "name": s.name, "available": s.available, "reason": s.reason,
                "requires_key": s.requires_key, "configured": s.configured,
            }
            for s in statuses
        ],
    }


@router.get("/knowledge/stats")
async def knowledge_statistics() -> dict[str, Any]:
    return knowledge_stats()


@router.get("/knowledge/search")
async def knowledge_search(
    q: str = Query(..., min_length=2), limit: int = Query(5, le=20), category: str | None = None
) -> list[dict[str, Any]]:
    return get_retriever().search(q, limit=limit, category=category)


@router.post("/knowledge/ingest")
async def knowledge_ingest() -> dict[str, Any]:
    return await asyncio.to_thread(ingest_directory)


@router.get("/reports")
async def reports(asset: str | None = None, limit: int = Query(20, le=100)) -> list[dict[str, Any]]:
    rows = repo.list_reports(_parse_asset(asset) if asset else None, limit=limit)
    return [
        {
            "id": r["id"], "asset": r["asset"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            "price_at_report": r["price_at_report"],
            "conviction_medium": r["conviction_medium"],
            "confidence": r["confidence"],
            "market_regime": r["market_regime"],
            "llm_used": r["llm_used"],
        }
        for r in rows
    ]


@router.get("/reports/{report_id}")
async def report_detail(report_id: str) -> dict[str, Any]:
    r = repo.get_report(report_id)
    if not r:
        raise HTTPException(404, f"Report '{report_id}' not found")
    if r.get("created_at"):
        r["created_at"] = r["created_at"].isoformat()
    return r


@router.get("/evaluation")
async def evaluation(asset: str | None = None) -> dict[str, Any]:
    stats = OutcomeEvaluator().stats(_parse_asset(asset) if asset else None)
    return stats.model_dump(mode="json")


@router.post("/evaluation/run")
async def run_evaluation() -> dict[str, Any]:
    """Score past reports against what actually happened since."""
    registry = get_registry()

    async def price_at(asset: Asset, at: datetime) -> float | None:
        res = await registry.fetch(
            FetchRequest(capability="market.ohlcv", asset=asset, timeframe=Timeframe.H1, limit=500)
        )
        if not res.ok or res.raw is None:
            return None
        best = None
        for candle in res.raw.candles:
            if candle.timestamp <= at:
                best = candle.close
            else:
                break
        return best

    # Pre-fetch each asset's series once, then look up in memory.
    series: dict[Asset, list] = {}
    for asset in Asset.tradables():
        res = await registry.fetch(
            FetchRequest(capability="market.ohlcv", asset=asset, timeframe=Timeframe.H1, limit=500)
        )
        series[asset] = res.raw.candles if (res.ok and res.raw) else []

    def lookup(asset: Asset, at: datetime) -> float | None:
        best = None
        for candle in series.get(asset, []):
            if candle.timestamp <= at:
                best = candle.close
            else:
                break
        return best

    written = await asyncio.to_thread(OutcomeEvaluator().evaluate_pending, lookup)
    return {"outcomes_written": written}


@router.post("/etf/import")
async def etf_import() -> dict[str, Any]:
    """Import any CSV files dropped into data/imports/etf/."""
    from ..providers.etf.csv_import import import_directory

    imported, errors = await asyncio.to_thread(import_directory)
    return {"rows_imported": imported, "errors": errors}

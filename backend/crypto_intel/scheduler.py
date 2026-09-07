"""Periodic collection, snapshotting and evaluation.

Design constraints that shaped this module:

  * Cadences match how fast each source actually changes. Polling ETF flows
    every minute would only get us rate-limited.
  * Every job is wrapped so a failing provider degrades one job rather than
    killing the scheduler.
  * `max_instances=1` plus `coalesce=True` means a slow run is never stacked on
    top of itself, and a backlog after a pause collapses into a single run.
  * Restart safety comes from snapshot bucketing: a run repeated inside the
    same bucket updates rather than duplicates, so a crash-restart loop cannot
    corrupt history.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from .core.enums import Asset, Timeframe
from .history import snapshots
from .logging_setup import get_logger

log = get_logger("scheduler")

# Guards against two jobs writing the same rows at once. SQLite tolerates
# concurrent readers, but concurrent writers on the same tables deserve a lock.
_ANALYSIS_LOCK = asyncio.Lock()

_STATE: dict[str, Any] = {
    "started_at": None,
    "runs": {},
    "last_error": None,
}


def _record(job: str, ok: bool, detail: str = "") -> None:
    _STATE["runs"][job] = {
        "at": datetime.now(UTC).isoformat(),
        "ok": ok,
        "detail": detail[:300],
    }
    if not ok:
        _STATE["last_error"] = {"job": job, "at": _STATE["runs"][job]["at"], "detail": detail[:300]}


def scheduler_state() -> dict[str, Any]:
    return dict(_STATE)


async def job_analysis() -> None:
    """Full analysis for every asset, snapshotted at each domain's own cadence.

    This is the job that builds the system's memory: it produces the same
    analysis the API serves, then persists it so the evaluation layer has
    something to score later.
    """
    if _ANALYSIS_LOCK.locked():
        log.info("analysis_job_skipped", reason="previous run still in progress")
        return

    async with _ANALYSIS_LOCK:
        from .db import repo
        from .pipeline.orchestrator import get_pipeline
        from .reports.renderer import render_report

        pipeline = get_pipeline()
        created_total = 0
        errors: list[str] = []

        try:
            gdata = await pipeline.collect_global()
            pipeline.persist(gdata)
        except Exception as exc:
            log.warning("global_collection_failed", error=str(exc))
            errors.append(f"global: {exc}")
            gdata = {}

        for asset in Asset.tradables():
            try:
                analysis = await pipeline.analyze_asset(asset, gdata or None)
                created = snapshots.capture_analysis(analysis)
                created_total += sum(1 for v in created.values() if v)

                conviction = analysis.conviction
                repo.save_report(
                    report_id=analysis.report_id, asset=asset,
                    payload=analysis.model_dump(mode="json"),
                    text_report=render_report(analysis),
                    price=analysis.price,
                    convictions={
                        "short": conviction["short"]["score"],
                        "medium": conviction["medium"]["score"],
                        "long": conviction["long"]["score"],
                    },
                    scores=analysis.scores,
                    confidence=conviction.get("overall_confidence", 0.0),
                    market_regime=analysis.market_regime,
                    llm_used=analysis.llm_used,
                )
                log.info(
                    "analysis_snapshot", asset=asset.value,
                    regime=(analysis.regime or {}).get("regime"),
                    timing=(analysis.entry_timing or {}).get("timing"),
                )
            except Exception as exc:
                log.warning("analysis_failed", asset=asset.value, error=str(exc))
                errors.append(f"{asset.value}: {exc}")

        _record("analysis", not errors, "; ".join(errors) or f"{created_total} new snapshots")


async def job_decision_track() -> None:
    """Record what the decision engine concludes, so "last change" is a fact.

    The page can only say "timing moved from watch to wait at 21:00" if the
    earlier verdict was written down while it was current. Re-deriving it later
    from today's candles would answer a different question, so the reading is
    recorded on a cadence instead.
    """
    from .core.enums import Asset as _Asset
    from .engines.analysis_context import context_for
    from .history.decisions import record_decision

    recorded = 0
    errors: list[str] = []
    for asset in _Asset.tradables():
        try:
            record_decision(context_for(asset))
            recorded += 1
        except Exception as exc:
            log.warning("decision_track_failed", asset=asset.value, error=str(exc))
            errors.append(f"{asset.value}: {exc}")
    _record("decision_track", not errors, "; ".join(errors) or f"{recorded} readings")


async def job_market_only() -> None:
    """Fast price-only refresh between full analyses.

    Cheap enough to run often, which keeps the market snapshot series dense
    without re-running the whole pipeline.
    """
    from .providers.base import FetchRequest
    from .providers.registry import get_registry

    registry = get_registry()
    errors: list[str] = []

    for asset in Asset.tradables():
        try:
            res = await registry.fetch(
                FetchRequest(capability="market.ticker", asset=asset)
            )
            if not res.ok:
                continue
            values = {o.metric: o.numeric_value for o in res.observations}
            snapshots.save_snapshot(
                "market", asset,
                {
                    "price": values.get("price.last"),
                    "change_24h_pct": values.get("price.change_24h_pct"),
                    "high_24h": values.get("price.high_24h"),
                    "low_24h": values.get("price.low_24h"),
                    "volume_24h": values.get("price.volume_24h_quote"),
                    "source": "ticker",
                },
                price=values.get("price.last"),
            )
        except Exception as exc:
            errors.append(f"{asset.value}: {exc}")

    _record("market", not errors, "; ".join(errors))


async def job_ohlcv_sync() -> None:
    """Keep the local candle store current, so research never runs on stale bars."""
    from .history.backfill import backfill_ohlcv

    errors: list[str] = []
    for asset in Asset.tradables():
        for timeframe in (Timeframe.D1, Timeframe.H4, Timeframe.H1):
            try:
                # Small depth: this tops up recent bars rather than re-fetching
                # years of history on every cycle.
                await backfill_ohlcv(asset, timeframe, depth_days=5, max_requests=2)
            except Exception as exc:
                errors.append(f"{asset.value}/{timeframe.value}: {exc}")
    _record("ohlcv_sync", not errors, "; ".join(errors))


async def job_derivatives_sync() -> None:
    """Keep funding, open interest and DVOL current.

    These three had no job at all. The history was deep - 7006 funding points,
    2223 open-interest points - and stopped moving, so the page showed a
    perfectly valid percentile computed over a series whose last observation
    was a day old. Depth is not freshness, and nothing was refreshing it.
    """
    from .history.backfill import backfill_funding, backfill_open_interest
    from .providers.derivatives.multi_exchange import backfill_bybit_open_interest
    from .providers.volatility.deribit import backfill_dvol

    errors: list[str] = []
    for asset in Asset.tradables():
        try:
            # Peu de requetes: on complete le recent, pas l'historique.
            await backfill_funding(asset, max_requests=3, depth_days=3)
        except Exception as exc:
            errors.append(f"funding/{asset.value}: {exc}")
        # Deux series d'open interest coexistent et ne sont jamais fusionnees:
        # Binance publie une valeur notionnelle sur ~30 jours, Bybit un nombre
        # de contrats sur plusieurs annees. Les moteurs lisent la plus longue,
        # donc rafraichir uniquement la Binance laissait la serie consommee
        # figee - c'est exactement ce qui se passait.
        try:
            await backfill_open_interest(asset)
        except Exception as exc:
            errors.append(f"oi_binance/{asset.value}: {exc}")
        try:
            await backfill_bybit_open_interest(asset, max_requests=1)
        except Exception as exc:
            errors.append(f"oi_bybit/{asset.value}: {exc}")

    # Deribit publishes DVOL for BTC and ETH only; SOL has no series and none
    # is invented for it.
    for asset in (Asset.BTC, Asset.ETH):
        try:
            await backfill_dvol(asset, max_pages=1, window_days=7)
        except Exception as exc:
            errors.append(f"dvol/{asset.value}: {exc}")

    _record("derivatives_sync", not errors, "; ".join(errors))


async def job_etf_sync() -> None:
    """ETF flows publish once a day; check a few times, not continuously."""
    from .providers.base import FetchRequest
    from .providers.registry import get_registry

    registry = get_registry()
    errors: list[str] = []
    for asset in (Asset.BTC, Asset.ETH):
        try:
            res = await registry.fetch(FetchRequest(capability="etf.flows", asset=asset))
            if not res.ok:
                errors.append(f"{asset.value}: {res.user_message[:80]}")
        except Exception as exc:
            errors.append(f"{asset.value}: {exc}")
    _record("etf_sync", not errors, "; ".join(errors))


async def job_evaluate() -> None:
    """Score past reports against prices that have since been realised."""
    from .evaluation.outcomes import OutcomeEvaluator
    from .history import store

    try:
        series: dict[Asset, Any] = {}
        for asset in Asset.tradables():
            df = store.load_candles(asset, Timeframe.H1)
            series[asset] = df if not df.empty else None

        def lookup(asset: Asset, at: datetime) -> float | None:
            df = series.get(asset)
            if df is None or df.empty:
                return None
            subset = df[df.index <= at]
            return float(subset["close"].iloc[-1]) if len(subset) else None

        written = await asyncio.to_thread(OutcomeEvaluator().evaluate_pending, lookup)
        _record("evaluate", True, f"{written} outcomes written")
        if written:
            log.info("outcomes_evaluated", count=written)
    except Exception as exc:
        log.warning("evaluation_failed", error=str(exc))
        _record("evaluate", False, str(exc))


async def job_purge() -> None:
    """Keep the database from growing without bound."""
    from .db import repo

    try:
        removed = repo.purge_old_observations(days=400)
        for kind in ("market", "derivatives", "news"):
            removed += snapshots.purge_old(kind, keep_days=400)
        _record("purge", True, f"{removed} rows removed")
    except Exception as exc:
        _record("purge", False, str(exc))


def start_scheduler(run_immediately: bool = True) -> AsyncIOScheduler:
    """Start every periodic job.

    `coalesce=True` collapses a backlog into one run after a pause, and
    `misfire_grace_time` keeps a job that was late from being dropped silently
    - both matter for a laptop that sleeps.
    """
    scheduler = AsyncIOScheduler(
        timezone="UTC",
        job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 300},
    )

    jobs = [
        ("market", job_market_only, 5),
        ("analysis", job_analysis, 30),
        ("decision_track", job_decision_track, 30),
        ("ohlcv_sync", job_ohlcv_sync, 60),
        ("derivatives_sync", job_derivatives_sync, 60),
        ("etf_sync", job_etf_sync, 240),
        ("evaluate", job_evaluate, 60),
        ("purge", job_purge, 1440),
    ]

    now = datetime.now(UTC)
    for job_id, func, minutes in jobs:
        # Stagger first runs so startup does not fire every job at once.
        offset = {"market": 1, "analysis": 2, "decision_track": 3,
                  "ohlcv_sync": 5, "derivatives_sync": 6, "etf_sync": 8,
                  "evaluate": 11, "purge": 20}[job_id]
        scheduler.add_job(
            func,
            IntervalTrigger(minutes=minutes),
            id=job_id,
            next_run_time=now + timedelta(minutes=offset) if run_immediately else None,
        )

    scheduler.start()
    _STATE["started_at"] = now.isoformat()
    log.info("scheduler_started", jobs=[j[0] for j in jobs])
    return scheduler

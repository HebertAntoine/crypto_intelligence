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
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from .core.enums import Asset, Timeframe
from .history import snapshots
from .logging_setup import get_logger

log = get_logger("scheduler")

# Guards against two jobs writing the same rows at once. SQLite tolerates
# concurrent readers, but concurrent writers on the same tables deserve a lock.
_ANALYSIS_LOCK = asyncio.Lock()

# Every timeframe exposed by ``/api/chart`` must have a scheduled top-up.
# Keeping the tuple public makes that contract directly testable instead of
# relying on a source-code-string assertion.
OHLCV_SYNC_TIMEFRAMES: tuple[Timeframe, ...] = (
    Timeframe.M15,
    Timeframe.H1,
    Timeframe.H4,
    Timeframe.D1,
    Timeframe.W1,
)

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


async def job_analysis(
    global_data: dict[str, Any] | None = None,
    assets: Sequence[Asset] | None = None,
) -> None:
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

        if global_data is not None:
            gdata = global_data
            pipeline.persist(gdata)
        else:
            try:
                gdata = await pipeline.collect_global()
                pipeline.persist(gdata)
            except Exception as exc:
                log.warning("global_collection_failed", error=str(exc))
                errors.append(f"global: {exc}")
                gdata = {}

        targets = tuple(assets) if assets is not None else tuple(Asset.tradables())
        for asset in targets:
            try:
                # An explicitly empty mapping means that no global source was
                # due in this cycle.  Preserve it: turning it into ``None``
                # would make each asset recollect every global provider and
                # bypass the persisted cadence policy.
                analysis = await pipeline.analyze_asset(asset, gdata)
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


def _future_readings(snapshot: Any) -> dict[str, Any]:
    """The verdict and its first reason, per horizon, as the page shows them."""
    from .api.routes_future import _decision
    from .future_events.models import DecisionHorizon

    out: dict[str, Any] = {}
    for horizon in DecisionHorizon:
        try:
            summary = ((_decision(snapshot, horizon).to_dict().get("analysis") or {})
                       .get("summary") or {})
            reading = summary.get("reading") or {}
            waiting = reading.get("waiting_for") or []
            out[horizon.value] = {
                "action": (reading.get("verdict") or {}).get("action"),
                "reason": reading.get("headline", ""),
                "waiting": waiting[0]["text"] if waiting else "",
            }
        except Exception as exc:
            log.warning("future_reading_failed", horizon=horizon.value, error=str(exc))
    return out


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
            snapshot = context_for(asset)
            record_decision(snapshot, _future_readings(snapshot))
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
    from .db import repo
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
            # The fast job used to update only ``market_snapshots``.  The
            # decision layer reads canonical observations, so it continued to
            # report the price family as missing until the much slower full
            # analysis ran.  Persist the same sourced observations here; their
            # deterministic ids keep the operation idempotent.
            repo.save_observations(res.observations)
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
    from .history.backfill import refresh_recent_ohlcv

    errors: list[str] = []
    for asset in Asset.tradables():
        # Les cinq unités, pas trois. La profondeur était bonne — neuf ans en
        # hebdomadaire, quatre mois en quinze minutes — mais rien ne les
        # rafraîchissait: la bougie hebdomadaire accusait huit jours et la
        # quinze minutes quarante-trois heures. Une unité qu'on affiche et
        # qu'aucun travail ne met à jour vieillit en silence.
        for timeframe in OHLCV_SYNC_TIMEFRAMES:
            try:
                # One request is enough for a top-up. Historical depth remains
                # the explicit backfill command's responsibility.
                result = await refresh_recent_ohlcv(asset, timeframe, limit=400)
                status = str(result.get("status") or "UNKNOWN")
                if not result.get("ok") and status != "SKIPPED_MOCK":
                    detail = str(result.get("error") or status)[:120]
                    errors.append(f"{asset.value}/{timeframe.value}: {detail}")
            except Exception as exc:
                errors.append(f"{asset.value}/{timeframe.value}: {exc}")
    _record("ohlcv_sync", not errors, "; ".join(errors))


async def job_pattern_experiments() -> None:
    """Accumulate prospective pattern evidence without blocking the event loop."""
    try:
        from .pattern_learning.prospective import update_pattern_experiment

        result = await asyncio.to_thread(update_pattern_experiment)
        maturity = result["maturity"]
        _record(
            "pattern_experiments",
            True,
            f"{maturity['observations_settled']}/"
            f"{maturity['observations_required']} observations settled",
        )
    except Exception as exc:
        log.warning("pattern_experiment_failed", error=str(exc))
        _record("pattern_experiments", False, str(exc))


async def job_derivatives_sync(selected_sources: set[str] | None = None) -> None:
    """Keep funding, open interest and DVOL current.

    These three had no job at all. The history was deep - 7006 funding points,
    2223 open-interest points - and stopped moving, so the page showed a
    perfectly valid percentile computed over a series whose last observation
    was a day old. Depth is not freshness, and nothing was refreshing it.
    """
    from .history.backfill import (
        backfill_funding,
        backfill_long_short_accounts,
        backfill_open_interest,
        backfill_spot_taker_flow,
    )
    from .providers.derivatives.multi_exchange import backfill_bybit_open_interest
    from .providers.volatility.deribit import backfill_dvol

    selected = (
        selected_sources
        if selected_sources is not None
        else {
            "derivatives_funding",
            "derivatives_oi",
            "spot_pressure",
            "implied_volatility",
        }
    )
    errors: list[str] = []
    for asset in Asset.tradables():
        if "derivatives_funding" in selected:
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
        if "derivatives_oi" in selected:
            try:
                await backfill_open_interest(asset)
            except Exception as exc:
                errors.append(f"oi_binance/{asset.value}: {exc}")
            try:
                await backfill_bybit_open_interest(asset, max_requests=1)
            except Exception as exc:
                errors.append(f"oi_bybit/{asset.value}: {exc}")
        # Le côté agresseur du volume spot et la répartition des comptes: deux
        # familles de la carte de pression qui n'avaient aucune source, alors
        # que Binance publie les deux gratuitement et que nous appelions déjà
        # l'endpoint qui porte la première.
        if "spot_pressure" in selected:
            try:
                await backfill_spot_taker_flow(asset, depth_days=10, max_requests=1)
            except Exception as exc:
                errors.append(f"spot_flow/{asset.value}: {exc}")
        if "derivatives_funding" in selected:
            try:
                await backfill_long_short_accounts(asset, max_requests=1)
            except Exception as exc:
                errors.append(f"long_short/{asset.value}: {exc}")

    # Deribit publishes DVOL for BTC and ETH only; SOL has no series and none
    # is invented for it.
    if "implied_volatility" in selected:
        for asset in (Asset.BTC, Asset.ETH):
            try:
                await backfill_dvol(asset, max_pages=1, window_days=7)
            except Exception as exc:
                errors.append(f"dvol/{asset.value}: {exc}")

    _record("derivatives_sync", not errors, "; ".join(errors))


async def job_etf_sync() -> None:
    """ETF flows publish once a day; check a few times, not continuously."""
    from .db import repo
    from .providers.base import FetchRequest
    from .providers.registry import get_registry

    registry = get_registry()
    errors: list[str] = []
    persisted = 0
    for asset in (Asset.BTC, Asset.ETH):
        try:
            res = await registry.fetch(FetchRequest(capability="etf.flows", asset=asset))
            if not res.ok:
                errors.append(f"{asset.value}: {res.user_message[:80]}")
            else:
                # Fetching without writing made a successful ETF refresh
                # invisible to every downstream engine.
                persisted += repo.save_observations(res.observations)
        except Exception as exc:
            errors.append(f"{asset.value}: {exc}")
    _record("etf_sync", not errors, "; ".join(errors) or f"{persisted} observations")


async def job_future_events_sync() -> None:
    """Refresh primary-source calendars; partial outages stay visible."""
    from .future_events.collector import FutureEventCollector

    try:
        report = await FutureEventCollector().collect()
        detail = f"{report.saved} events; {len(report.failures)} source failures"
        _record("future_events_sync", not report.failures, detail)
        if report.failures:
            log.warning("future_event_sources_unavailable", failures=report.failures)
    except Exception as exc:
        log.warning("future_events_sync_failed", error=str(exc))
        _record("future_events_sync", False, str(exc))


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


async def job_lexa_watch() -> None:
    """Follow the member's Lexa plans: statuses, closes, notifications (local only)."""
    try:
        from .lexa.notifier import evaluate_all

        sent = await asyncio.to_thread(evaluate_all)
        _record("lexa_watch", True, f"{len(sent)} notification(s)")
    except Exception as exc:
        _record("lexa_watch", False, str(exc)[:200])


#: A macro release that lands between two cycles is re-read immediately rather
#: than waiting up to three hours: an FOMC decision does not keep office hours.
URGENT_WORDS = ("fomc", "monetary policy", "cpi", "consumer price", "personal income",
                "employment situation", "nonfarm", "bce", "ecb", "boj")
URGENT_WINDOW = timedelta(minutes=90)


def _macro_radar(now: datetime, *, persist: bool) -> dict[str, Any]:
    """Build the radar without recursively starting the complete 3 h cycle."""

    from .engines.macro_drivers import build
    from .engines.pit_view import DataCache, PointInTimeView
    from .history.macro_cycles import previous_cycle, record_cycle

    view = PointInTimeView(DataCache(), now)
    radar = build(view, now=now, previous=previous_cycle(now))
    if persist:
        record_cycle(radar, when=now)
    return radar


def _revision_watermarks() -> dict[str, dict[str, Any]]:
    """Compact store-derived watermark used to detect newly ingested revisions."""

    from .history import store

    output: dict[str, dict[str, Any]] = {}
    for metric in store.macro_coverage():
        revised = [
            row
            for row in store.load_macro_records(metric)
            if int(row.get("revision_number") or 0) > 0
        ]
        if not revised:
            output[metric] = {"count": 0, "latest_vintage": None, "max_revision": 0}
            continue
        vintages = [
            row.get("vintage_date") or row.get("revision_time")
            for row in revised
            if row.get("vintage_date") or row.get("revision_time")
        ]
        output[metric] = {
            "count": len(revised),
            "latest_vintage": max(vintages).isoformat() if vintages else None,
            "max_revision": max(int(row.get("revision_number") or 0) for row in revised),
        }
    return output


def _decision_state(asset: Asset) -> dict[str, Any]:
    rows = snapshots.load_snapshots("decision", asset, limit=1)
    payload = (rows[0].get("payload") or {}) if rows else {}
    return {
        "analysis_id": payload.get("analysis_id"),
        "state": payload.get("state"),
        "regime": payload.get("regime"),
        "future": payload.get("future") or {},
    }


async def _cycle_read_latest(context: Any) -> Any:
    """1. Read durable inputs before making any external request."""

    from .db import repo
    from .engines.analysis_context import data_fingerprint
    from .history import store
    from .pipeline.three_hour_cycle import StepResult

    input_before = {
        asset.value: data_fingerprint(asset) for asset in Asset.tradables()
    }
    decisions_before = {
        asset.value: _decision_state(asset) for asset in Asset.tradables()
    }
    reports_before: dict[str, dict[str, Any] | None] = {}
    candle_ends: dict[str, dict[str, str | None]] = {}
    for asset in Asset.tradables():
        latest = repo.latest_report(asset)
        reports_before[asset.value] = (
            {
                "id": latest.get("id"),
                "created_at": latest["created_at"].isoformat(),
            }
            if latest
            else None
        )
        candle_ends[asset.value] = {}
        for timeframe in OHLCV_SYNC_TIMEFRAMES:
            end = store.candle_coverage(asset, timeframe).get("end")
            candle_ends[asset.value][timeframe.value] = end.isoformat() if end else None

    event_before = repo.future_event_fingerprint()
    revision_before = await asyncio.to_thread(_revision_watermarks)
    return StepResult.success(
        "état durable lu avant collecte",
        input_before=input_before,
        decisions_before=decisions_before,
        reports_before=reports_before,
        event_before=event_before,
        revision_before=revision_before,
        candle_ends_before=candle_ends,
    )


async def _cycle_plan_due_sources(context: Any) -> Any:
    """2. Apply persisted source cadences and circuit breakers."""

    from .pipeline.source_policy import Criticality, POLICIES, which_sources_are_due
    from .pipeline.source_state_store import load, save
    from .pipeline.three_hour_cycle import StepResult

    states = await asyncio.to_thread(load)
    due = which_sources_are_due(states, context.now)
    # ``which_sources_are_due`` may move a cooled breaker to HALF_OPEN.  That
    # transition has to survive a process restart too.
    await asyncio.to_thread(save, states)
    due_ids = [policy.source_id for policy in due]
    blocked_all = sorted(
        source_id
        for source_id, state in states.items()
        if source_id in POLICIES
        and POLICIES[source_id].enabled
        and state.circuit == "OPEN"
        and state.consecutive_failures > 0
    )
    blocked = [
        source_id
        for source_id in blocked_all
        if POLICIES[source_id].criticality is not Criticality.OPTIONAL
    ]
    blocked_optional = [
        source_id
        for source_id in blocked_all
        if POLICIES[source_id].criticality is Criticality.OPTIONAL
    ]
    skipped = [
        source_id
        for source_id, policy in POLICIES.items()
        if policy.enabled and source_id not in due_ids
    ]
    data = {
        "due_sources": due_ids,
        "skipped_by_cadence": skipped,
        "blocked_sources": blocked,
        "blocked_optional": blocked_optional,
        "source_plan_at": context.now.isoformat(),
    }
    if blocked:
        return StepResult.degraded(
            "certaines sources restent bloquées après échec",
            errors=[f"{source_id}: circuit ouvert" for source_id in blocked],
            **data,
        )
    return StepResult.success(
        f"{len(due_ids)} source(s) due(s), {len(skipped)} non interrogée(s)",
        **data,
    )


def _job_result(name: str) -> tuple[bool, str]:
    result = (_STATE.get("runs") or {}).get(name) or {}
    return bool(result.get("ok")), str(result.get("detail") or "")


async def _cycle_collect_publications(context: Any) -> Any:
    """3. Collect only due market, OHLCV, derivatives, ETF and event inputs."""

    from .db import repo
    from .future_events.collector import (
        GEOPOLITICAL_CAPABILITIES,
        MARKET_EXPECTATION_CAPABILITIES,
        OFFICIAL_MACRO_CAPABILITIES,
        OFFICIAL_PROTOCOL_CAPABILITIES,
        OFFICIAL_REGULATORY_CAPABILITIES,
        FutureEventCollector,
    )
    from .pipeline.orchestrator import get_pipeline
    from .pipeline.source_policy import (
        POLICIES,
        Criticality,
        SourceState,
        record_attempt,
        record_failure,
        record_success,
        which_sources_are_due,
    )
    from .pipeline.source_state_store import load, save
    from .pipeline.three_hour_cycle import StepResult
    from .providers.base import FetchRequest
    from .providers.registry import get_registry

    planned_due = set(context.shared.get("due_sources") or [])
    # If a process died after planning but before collection, the durable due
    # list is hydrated by the runner.  A legacy report without it fails closed:
    # it recollects nothing rather than bypassing provider limits.
    states = await asyncio.to_thread(load)
    # A degraded step can be retried in the same bucket.  Re-evaluate the
    # persisted source state so sources that already succeeded are not called
    # a second time merely because another source failed.
    currently_due = {
        policy.source_id for policy in which_sources_are_due(states, context.now)
    }
    plan_value = context.shared.get("source_plan_at")
    try:
        plan_at = datetime.fromisoformat(str(plan_value)) if plan_value else context.now
    except ValueError:
        plan_at = context.now
    if plan_at.tzinfo is None:
        plan_at = plan_at.replace(tzinfo=UTC)
    else:
        plan_at = plan_at.astimezone(UTC)
    already_succeeded = {
        source_id
        for source_id in planned_due
        if (state := states.get(source_id)) is not None
        and state.last_success_at is not None
        and state.last_success_at >= plan_at
    }
    blocked_after_failure = planned_due - currently_due - already_succeeded
    due = (planned_due & currently_due) - already_succeeded
    source_results: dict[str, dict[str, Any]] = {
        source_id: {
            "ok": False,
            "detail": "collecte suspendue après échec; aucun succès frais",
            "errors": [
                (
                    f"circuit={states[source_id].circuit}; "
                    f"last_error={states[source_id].last_error_kind or 'UNKNOWN'}"
                    if source_id in states
                    else "source state unavailable"
                )
            ],
        }
        for source_id in sorted(blocked_after_failure)
    }

    async def run_job(
        job_name: str,
        source_ids: tuple[str, ...],
        function: Any,
    ) -> None:
        selected = [source_id for source_id in source_ids if source_id in due]
        if not selected:
            return
        for source_id in selected:
            state = states.setdefault(source_id, SourceState(source_id=source_id))
            record_attempt(state, context.now)
        await function()
        ok, detail = _job_result(job_name)
        for source_id in selected:
            state = states[source_id]
            if ok:
                record_success(state, context.now, fingerprint=detail)
            else:
                kind = "HTTP_429" if "429" in detail else "COLLECTION_ERROR"
                record_failure(state, context.now, error_kind=kind)
            source_results[source_id] = {"ok": ok, "detail": detail}

    await run_job("market", ("market_price",), job_market_only)
    await run_job("ohlcv_sync", ("ohlcv",), job_ohlcv_sync)
    selected_derivatives = due & {
        "derivatives_oi",
        "derivatives_funding",
        "spot_pressure",
        "implied_volatility",
    }
    await run_job(
        "derivatives_sync",
        (
            "derivatives_oi",
            "derivatives_funding",
            "spot_pressure",
            "implied_volatility",
        ),
        lambda: job_derivatives_sync(selected_derivatives),
    )
    await run_job("etf_sync", ("etf_flows",), job_etf_sync)

    event_sources = {
        "event_calendars",
        "regulation",
        "protocol_proposals",
        "sec_filings",
    }
    selected_events = sorted(due & event_sources)
    if selected_events:
        for source_id in selected_events:
            state = states.setdefault(source_id, SourceState(source_id=source_id))
            record_attempt(state, context.now)
        sec_capability = "events.regulation.sec_filings"
        event_capabilities: dict[str, tuple[str, ...]] = {
            "event_calendars": (
                OFFICIAL_MACRO_CAPABILITIES
                + MARKET_EXPECTATION_CAPABILITIES
                + GEOPOLITICAL_CAPABILITIES
            ),
            "regulation": tuple(
                item
                for item in OFFICIAL_REGULATORY_CAPABILITIES
                if item != sec_capability
            ),
            "sec_filings": (sec_capability,),
            "protocol_proposals": OFFICIAL_PROTOCOL_CAPABILITIES,
        }
        capabilities = tuple(
            dict.fromkeys(
                capability
                for source_id in selected_events
                for capability in event_capabilities[source_id]
            )
        )
        report = await FutureEventCollector().collect(capabilities)
        event_ok = not report.failures
        detail = f"{report.saved} événements; {len(report.failures)} capacité(s) en échec"
        _record("future_events_sync", event_ok, detail)
        for source_id in selected_events:
            state = states[source_id]
            source_failures = {
                capability: report.failures[capability]
                for capability in event_capabilities[source_id]
                if capability in report.failures
            }
            source_ok = not source_failures
            source_detail = (
                f"{len(event_capabilities[source_id]) - len(source_failures)}/"
                f"{len(event_capabilities[source_id])} capacités"
            )
            if source_ok:
                record_success(state, context.now, fingerprint=source_detail)
            else:
                record_failure(state, context.now, error_kind="COLLECTION_ERROR")
            source_results[source_id] = {
                "ok": source_ok,
                "detail": source_detail,
                "errors": list(source_failures.values()),
            }

    global_capabilities: dict[str, tuple[str, ...]] = {
        "stablecoins": ("stablecoins.supply",),
        "macro_series": (
            "macro.series",
            "macro.rates",
            "macro.inflation",
            "macro.central_banks",
            "macro.indices",
        ),
        "macro_credit": ("macro.credit",),
        "liquidity_official": (
            "liquidity.tga",
            "liquidity.rrp",
            "liquidity.fed_balance_sheet",
        ),
        "market_breadth": ("market.breadth", "market.global"),
        "coinshares_weekly": ("flows.institutional_weekly",),
    }
    registry = get_registry()
    pipeline = get_pipeline()
    if "whales" in due:
        state = states.setdefault("whales", SourceState(source_id="whales"))
        record_attempt(state, context.now)
        whale_results = await asyncio.gather(
            *(
                registry.fetch(
                    FetchRequest(capability="whales.flows", asset=asset)
                )
                for asset in Asset.tradables()
            ),
            return_exceptions=True,
        )
        valid_results = {
            f"whales_{asset.value}": result
            for asset, result in zip(Asset.tradables(), whale_results, strict=True)
            if not isinstance(result, BaseException)
        }
        pipeline.persist(valid_results)
        whale_errors = [
            (
                f"{asset.value}: {type(result).__name__}: {result}"
                if isinstance(result, BaseException)
                else f"{asset.value}: {result.status.value}"
            )
            for asset, result in zip(Asset.tradables(), whale_results, strict=True)
            if isinstance(result, BaseException) or not result.ok
        ]
        whale_ok = not whale_errors
        detail = f"{len(whale_results) - len(whale_errors)}/{len(whale_results)} actifs"
        if whale_ok:
            record_success(state, context.now, fingerprint=detail)
        else:
            whale_error_kind = (
                "HTTP_429"
                if any(
                    not isinstance(result, BaseException)
                    and result.status.value == "RATE_LIMITED"
                    for result in whale_results
                )
                else "COLLECTION_ERROR"
            )
            record_failure(state, context.now, error_kind=whale_error_kind)
        source_results["whales"] = {
            "ok": whale_ok,
            "detail": detail,
            "errors": whale_errors,
        }
    global_data: dict[str, Any] = {}
    for source_id, capabilities in global_capabilities.items():
        if source_id not in due or not POLICIES[source_id].enabled or not capabilities:
            continue
        state = states.setdefault(source_id, SourceState(source_id=source_id))
        record_attempt(state, context.now)
        results = await asyncio.gather(
            *(registry.fetch(FetchRequest(capability=capability)) for capability in capabilities)
        )
        keyed = dict(zip(capabilities, results, strict=True))
        global_data.update(keyed)
        pipeline.persist(keyed)
        failures = [
            f"{capability}: {result.status.value}"
            for capability, result in keyed.items()
            if not result.ok
        ]
        ok = not failures
        detail = f"{len(capabilities) - len(failures)}/{len(capabilities)} capacités"
        if ok:
            record_success(state, context.now, fingerprint=detail)
        else:
            error_kind = (
                "HTTP_429"
                if any(result.status.value == "RATE_LIMITED" for result in results)
                else "COLLECTION_ERROR"
            )
            record_failure(state, context.now, error_kind=error_kind)
        source_results[source_id] = {
            "ok": ok,
            "detail": detail,
            "errors": failures,
        }

    await asyncio.to_thread(save, states)
    context.shared["global_data"] = global_data
    event_after = repo.future_event_fingerprint()
    errors = [
        f"{source_id}: {item.get('detail') or 'échec'}"
        for source_id, item in source_results.items()
        if not item.get("ok")
        and POLICIES[source_id].criticality is not Criticality.OPTIONAL
    ]
    optional_errors = [
        f"{source_id}: {item.get('detail') or 'échec'}"
        for source_id, item in source_results.items()
        if not item.get("ok")
        and POLICIES[source_id].criticality is Criticality.OPTIONAL
    ]
    blocked_required = {
        source_id
        for source_id in blocked_after_failure
        if POLICIES[source_id].criticality is not Criticality.OPTIONAL
    }
    blocked_optional = blocked_after_failure - blocked_required
    data = {
        "source_results": source_results,
        "event_after": event_after,
        # A source held behind a breaker is reported above, but it was not
        # contacted during this attempt and must not be labelled collected.
        "collected_sources": sorted(set(source_results) - blocked_after_failure),
        "already_succeeded": sorted(already_succeeded),
        "blocked_sources": sorted(blocked_required),
        "blocked_optional": sorted(blocked_optional),
        "optional_errors": optional_errors,
    }
    if errors:
        return StepResult.degraded(
            "collecte partielle; les indisponibilités restent explicites",
            errors=errors,
            **data,
        )
    optional_detail = (
        f"; {len(optional_errors)} échec(s) optionnel(s) signalé(s)"
        if optional_errors
        else ""
    )
    return StepResult.success(
        f"{len(source_results)} source(s) traitée(s) selon leur cadence{optional_detail}",
        **data,
    )


async def _cycle_detect_revisions(context: Any) -> Any:
    """4. Compare store vintages before/after collection."""

    from .pipeline.three_hour_cycle import StepResult

    before = context.shared.get("revision_before") or {}
    after = await asyncio.to_thread(_revision_watermarks)
    changed = sorted(
        metric for metric in set(before) | set(after) if before.get(metric) != after.get(metric)
    )
    context.shared["revision_after"] = after
    context.shared["revised_metrics"] = changed
    return StepResult.success(
        f"{len(changed)} série(s) révisée(s)",
        revision_after=after,
        revised_metrics=changed,
    )


async def _cycle_recompute_indicators(context: Any) -> Any:
    """5. Recompute deterministic indicators from the refreshed stores."""

    from .engines.analysis_context import context_for, reset_cache
    from .pipeline.three_hour_cycle import StepResult

    reset_cache()
    computed: dict[str, Any] = {}
    input_after: dict[str, Any] = {}
    errors: list[str] = []
    for asset in Asset.tradables():
        try:
            snapshot = await asyncio.to_thread(
                context_for, asset, context.now, refresh=True
            )
            computed[asset.value] = snapshot
            input_after[asset.value] = {
                key: value for key, value in snapshot.fingerprint.items() if key != "bucket"
            }
        except Exception as exc:
            errors.append(f"{asset.value}: {exc}")
    context.shared["asset_snapshots"] = computed
    data = {
        "analysis_ids": {
            asset: snapshot.analysis_id for asset, snapshot in computed.items()
        },
        "input_after": input_after,
    }
    if errors:
        return StepResult.degraded(
            "certains indicateurs n'ont pas pu être recalculés", errors=errors, **data
        )
    return StepResult.success(f"{len(computed)} actif(s) recalculé(s)", **data)


async def _cycle_asset_snapshots(
    context: Any,
) -> tuple[dict[str, Any], list[str]]:
    """Restore non-JSON analysis objects after a process restart.

    Step 5 persists the compact fingerprints and analysis ids, not the large
    Python snapshot objects.  Steps 6, 7, 9 and 10 still need those objects.
    Rebuilding only missing assets from the durable stores keeps resume honest
    without repeating provider calls.
    """

    from .engines.analysis_context import context_for

    snapshots_by_asset = context.shared.setdefault("asset_snapshots", {})
    errors: list[str] = []
    for asset in Asset.tradables():
        if asset.value in snapshots_by_asset:
            continue
        try:
            snapshots_by_asset[asset.value] = await asyncio.to_thread(
                context_for, asset, context.now, refresh=True
            )
        except Exception as exc:
            errors.append(f"{asset.value}: {exc}")
    return snapshots_by_asset, errors


async def _cycle_evaluate_events(context: Any) -> Any:
    """6. Evaluate currently active/surprise/decaying events."""

    from .future_events.models import FutureEventStatus
    from .pipeline.three_hour_cycle import StepResult

    snapshots_by_asset, errors = await _cycle_asset_snapshots(context)
    active_statuses = {
        FutureEventStatus.ACTIVE,
        FutureEventStatus.SURPRISE,
        FutureEventStatus.DECAYING,
    }
    active: dict[str, list[str]] = {}
    for asset, snapshot in snapshots_by_asset.items():
        active[asset] = [
            event.id
            for event in snapshot.future_events
            if event.runtime_status(context.now) in active_statuses
        ]
    data = {"active_events": active}
    if errors:
        return StepResult.degraded(
            "évaluation partielle des événements actifs", errors=errors, **data
        )
    return StepResult.success(
        f"{sum(len(items) for items in active.values())} événement(s) actif(s)", **data
    )


def _current_decision_state(snapshot: Any) -> dict[str, Any]:
    return {
        "analysis_id": snapshot.analysis_id,
        "state": snapshot.opportunity.state.value,
        "regime": str(getattr(getattr(snapshot.regime, "regime", None), "value", "")),
    }


async def _cycle_compare_diagnosis(context: Any) -> Any:
    """7. Compare current diagnosis with the last actually recorded reading."""

    from .pipeline.three_hour_cycle import StepResult

    snapshots_by_asset, errors = await _cycle_asset_snapshots(context)
    before = context.shared.get("decisions_before") or {}
    current = {
        asset: _current_decision_state(snapshot)
        for asset, snapshot in snapshots_by_asset.items()
    }
    changes: dict[str, dict[str, Any]] = {}
    for asset, state in current.items():
        prior = before.get(asset) or {}
        fields = {
            key: {"before": prior.get(key), "after": state.get(key)}
            for key in ("state", "regime")
            if prior.get(key) != state.get(key)
        }
        if fields:
            changes[asset] = fields
    data = {"current_diagnosis": current, "diagnosis_changes": changes}
    if errors:
        return StepResult.degraded(
            "comparaison partielle des diagnostics", errors=errors, **data
        )
    return StepResult.success(f"{len(changes)} diagnostic(s) modifié(s)", **data)


async def _cycle_reclassify_signals(context: Any) -> Any:
    """8. Rebuild and rank the exact macro signal catalogue."""

    from .pipeline.three_hour_cycle import StepResult

    radar = await asyncio.to_thread(_macro_radar, context.now, persist=False)
    context.shared["macro_radar"] = radar
    top = [str(item.get("key") or "") for item in (radar.get("top") or [])]
    return StepResult.success(
        f"{radar.get('watched', 0)} moteur(s), top {len(top)}",
        macro_top=top,
        macro_watched=int(radar.get("watched") or 0),
    )


async def _cycle_reevaluate_scenarios(context: Any) -> Any:
    """9. Re-evaluate scenario and decision contracts for every horizon."""

    from .api.routes_future import _decision
    from .future_events.models import DecisionHorizon
    from .pipeline.three_hour_cycle import StepResult

    snapshots_by_asset, errors = await _cycle_asset_snapshots(context)
    readings: dict[str, dict[str, Any]] = {}
    for asset, snapshot in snapshots_by_asset.items():
        readings[asset] = {}
        for horizon in DecisionHorizon:
            try:
                payload = _decision(snapshot, horizon).to_dict()
                readings[asset][horizon.value] = {
                    "decision": payload.get("decision"),
                    "scenario_count": len(payload.get("scenarios") or []),
                    "scenarios": [
                        item.get("kind") for item in payload.get("scenarios") or []
                    ],
                }
            except Exception as exc:
                errors.append(f"{asset}/{horizon.value}: {exc}")
    context.shared["scenario_readings"] = readings
    if errors:
        return StepResult.degraded(
            "réévaluation partielle des scénarios",
            errors=errors,
            scenario_readings=readings,
        )
    return StepResult.success("scénarios réévalués", scenario_readings=readings)


async def _cycle_reevaluate_assets(context: Any) -> Any:
    """10. Persist the new per-asset state/decision reading."""

    from .history.decisions import record_decision
    from .pipeline.three_hour_cycle import StepResult

    snapshots_by_asset, errors = await _cycle_asset_snapshots(context)
    states: dict[str, Any] = {}
    for asset, snapshot in snapshots_by_asset.items():
        try:
            future = _future_readings(snapshot)
            created = await asyncio.to_thread(record_decision, snapshot, future)
            states[asset] = {
                **_current_decision_state(snapshot),
                "record_created": created,
                "future": future,
            }
        except Exception as exc:
            errors.append(f"{asset}: {exc}")
    if errors:
        return StepResult.degraded(
            "certains états d'actifs n'ont pas été enregistrés",
            errors=errors,
            asset_states=states,
        )
    return StepResult.success(f"{len(states)} état(s) enregistré(s)", asset_states=states)


def _report_is_stale(report: dict[str, Any] | None, now: datetime) -> bool:
    if not report or not report.get("created_at"):
        return True
    try:
        created = datetime.fromisoformat(str(report["created_at"]))
    except ValueError:
        return True
    created = created.replace(tzinfo=UTC) if created.tzinfo is None else created.astimezone(UTC)
    return now - created >= timedelta(hours=6)


async def _cycle_generate_if_needed(context: Any) -> Any:
    """11. Generate a full report only for changed inputs or a stale baseline."""

    from .pipeline.three_hour_cycle import StepResult

    before = context.shared.get("input_before") or {}
    after = context.shared.get("input_after") or {}
    reports = context.shared.get("reports_before") or {}
    changed_assets = sorted(
        asset
        for asset in {item.value for item in Asset.tradables()}
        if before.get(asset) != after.get(asset)
        or _report_is_stale(reports.get(asset), context.now)
    )
    if not changed_assets:
        return StepResult.success(
            "entrées inchangées et rapports récents; aucune analyse dupliquée",
            analysis_generated=False,
            changed_assets=[],
        )

    if _ANALYSIS_LOCK.locked():
        return StepResult.degraded(
            "analyse différée: une analyse est déjà en cours",
            errors=["analysis lock already held"],
            analysis_generated=False,
            changed_assets=changed_assets,
        )
    # ``global_data`` is intentionally ephemeral (FetchResult contains rich
    # objects that do not belong in the orchestration JSON).  After a process
    # restart use an explicit empty mapping so the analysis cannot silently
    # recollect providers outside their due cadence.
    await job_analysis(
        context.shared.get("global_data", {}),
        assets=[Asset(asset) for asset in changed_assets],
    )
    ok, detail = _job_result("analysis")
    data = {
        "analysis_generated": True,
        "changed_assets": changed_assets,
        "analysis_detail": detail,
    }
    if not ok:
        return StepResult.degraded(
            "analyse générée partiellement", errors=[detail or "analysis failed"], **data
        )
    return StepResult.success("nouvelle analyse générée", **data)


async def _cycle_record_report(context: Any) -> Any:
    """12. Persist the macro reading; workflow status is persisted by the runner."""

    from .history.macro_cycles import record_cycle
    from .pipeline.three_hour_cycle import StepResult

    radar = context.shared.get("macro_radar")
    if radar is None:
        radar = await asyncio.to_thread(_macro_radar, context.now, persist=False)
    created = await asyncio.to_thread(record_cycle, radar, context.now)
    return StepResult.success(
        "rapport de cycle et radar persistés",
        macro_cycle_created=created,
        cycle_report_kind="server_cycle_3h",
    )


async def _cycle_notify(context: Any) -> Any:
    """13. Emit only notifications already admitted by domain cooldown rules."""

    from .db import repo
    from .pipeline.three_hour_cycle import StepResult

    await job_lexa_watch()
    ok, detail = _job_result("lexa_watch")
    recent = repo.recent_alerts(limit=200)
    admitted = [
        item
        for item in recent
        if item.get("triggered_at") is not None
        and item["triggered_at"] >= context.now
    ]
    data = {
        "admitted_alerts": len(admitted),
        "lexa_notifications": detail,
    }
    if not ok:
        return StepResult.degraded(
            "notifications générales enregistrées; surveillance Lexa en échec",
            errors=[detail or "lexa watch failed"],
            **data,
        )
    return StepResult.success(
        f"{len(admitted)} alerte(s) admissible(s); {detail}", **data
    )


def three_hour_cycle_steps() -> tuple[Any, ...]:
    """The prompt's 13 steps, in their required order, as executable specs."""

    from .pipeline.three_hour_cycle import CycleStep

    return (
        CycleStep(1, "read_latest", "Lire les dernières données disponibles", _cycle_read_latest),
        CycleStep(2, "provider_limits", "Respecter les limites fournisseur", _cycle_plan_due_sources),
        CycleStep(3, "new_publications", "Vérifier les publications nouvelles", _cycle_collect_publications),
        CycleStep(4, "revisions", "Détecter les révisions", _cycle_detect_revisions),
        CycleStep(5, "indicators", "Recalculer les indicateurs concernés", _cycle_recompute_indicators),
        CycleStep(6, "active_events", "Évaluer les événements encore actifs", _cycle_evaluate_events),
        CycleStep(7, "compare", "Comparer le diagnostic précédent", _cycle_compare_diagnosis),
        CycleStep(8, "signals", "Reclasser les signaux", _cycle_reclassify_signals),
        CycleStep(9, "scenarios", "Réévaluer les scénarios", _cycle_reevaluate_scenarios),
        CycleStep(10, "asset_states", "Réévaluer les états des actifs", _cycle_reevaluate_assets),
        CycleStep(11, "analysis", "Produire une analyse seulement si nécessaire", _cycle_generate_if_needed),
        CycleStep(12, "cycle_report", "Enregistrer un rapport de cycle", _cycle_record_report),
        CycleStep(13, "notifications", "Déclencher les notifications admissibles", _cycle_notify),
    )


_THREE_HOUR_RUNNER: Any = None


def _cycle_runner() -> Any:
    global _THREE_HOUR_RUNNER
    if _THREE_HOUR_RUNNER is None:
        from .pipeline.three_hour_cycle import DurableCycleRunner

        _THREE_HOUR_RUNNER = DurableCycleRunner()
    return _THREE_HOUR_RUNNER


async def job_macro_cycle() -> None:
    """Run the durable 13-step server cycle for this UTC three-hour bucket."""

    try:
        report = await _cycle_runner().run(
            three_hour_cycle_steps(), when=datetime.now(UTC), trigger="CRON_3H"
        )
        status = str(report.get("status") or "FAILED")
        ok = status == "SUCCESS"
        detail = f"{report.get('cycle_id', '')} · {status}"
        if report.get("errors"):
            detail += " · " + "; ".join(report["errors"][:2])
        _record("macro_cycle", ok, detail)
    except Exception as exc:
        _record("macro_cycle", False, str(exc)[:200])


async def job_macro_watch() -> None:
    """Between two cycles: re-read only when a major release has just landed."""

    try:
        from .db import repo

        now = datetime.now(UTC)
        recent = await asyncio.to_thread(
            repo.list_future_events, start=now - URGENT_WINDOW, end=now, limit=50
        )
        landed = [
            event for event in recent
            if getattr(event, "scheduled_at", None) is not None
            and now - URGENT_WINDOW <= event.scheduled_at <= now
            and any(word in (event.title or "").lower() for word in URGENT_WORDS)
        ]
        if not landed:
            _record("macro_watch", True, "aucune publication majeure")
            return
        # Event-driven refresh is deliberately a radar refresh, not a recursive
        # invocation of the full scheduled cycle.  It therefore cannot overlap
        # or duplicate the 13-step run while still reacting before the next 3 h.
        await asyncio.to_thread(_macro_radar, now, persist=True)
        _record("macro_watch", True,
                f"réévaluation après {landed[0].title[:60]}")
    except Exception as exc:
        _record("macro_watch", False, str(exc)[:200])


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
        ("pattern_experiments", job_pattern_experiments, 60),
        ("derivatives_sync", job_derivatives_sync, 60),
        ("etf_sync", job_etf_sync, 240),
        ("future_events_sync", job_future_events_sync, 360),
        ("evaluate", job_evaluate, 60),
        ("lexa_watch", job_lexa_watch, 5),
        ("macro_watch", job_macro_watch, 15),
        ("purge", job_purge, 1440),
    ]

    now = datetime.now(UTC)
    for job_id, func, minutes in jobs:
        # Stagger first runs so startup does not fire every job at once.
        # On process start, collect the inputs before taking the first
        # analytical snapshot.  Previously analysis ran at +2 minutes while
        # OHLCV and derivatives first ran at +5/+6, guaranteeing one stale
        # baseline after every restart.
        offset = {"market": 1, "ohlcv_sync": 2, "derivatives_sync": 3,
                  "etf_sync": 4, "future_events_sync": 5,
                  "analysis": 6, "decision_track": 7,
                  "pattern_experiments": 9,
                  "evaluate": 11, "lexa_watch": 8, "macro_watch": 12,
                  "purge": 20}[job_id]
        scheduler.add_job(
            func,
            IntervalTrigger(minutes=minutes),
            id=job_id,
            next_run_time=now + timedelta(minutes=offset) if run_immediately else None,
        )

    # The macro cycle runs on the clock, not on an interval: 00:00, 03:00,
    # 06:00 ... UTC, so « actualisé à 18:00, prochaine vérification 21:00 »
    # means the same thing on every restart.
    from .engines.macro_drivers import CYCLE_HOURS

    scheduler.add_job(
        job_macro_cycle,
        CronTrigger(hour=",".join(str(h) for h in CYCLE_HOURS), minute=0, timezone="UTC"),
        id="macro_cycle",
        next_run_time=now + timedelta(minutes=10) if run_immediately else None,
    )

    scheduler.start()
    _STATE["started_at"] = now.isoformat()
    log.info("scheduler_started", jobs=[j[0] for j in jobs] + ["macro_cycle"])
    return scheduler

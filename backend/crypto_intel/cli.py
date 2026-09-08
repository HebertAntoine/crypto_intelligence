"""Command line interface.

    python -m crypto_intel.cli <command>

Commands: serve, collect, analyze, report, ingest-knowledge, import-etf,
          evaluate, providers, init-db
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import sys
from datetime import UTC
from pathlib import Path
from typing import Any

from .core.enums import Asset, Timeframe
from .db.session import init_db
from .logging_setup import setup_logging
from .settings import get_settings


def _asset(value: str) -> Asset:
    try:
        return Asset(value.upper())
    except ValueError:
        print(f"Unknown asset '{value}'. Supported: BTC, ETH, SOL.", file=sys.stderr)
        raise SystemExit(2) from None


async def cmd_collect(args) -> int:
    from .pipeline.orchestrator import get_pipeline
    from .providers.http import get_http

    init_db()
    pipeline = get_pipeline()
    total = 0
    gdata = await pipeline.collect_global()
    total += pipeline.persist(gdata)
    for name, res in gdata.items():
        print(f"  {'OK ' if res.ok else '-- '} {name:<16} {len(res.observations):>4} obs"
              + ("" if res.ok else f"  {res.user_message[:60]}"))

    assets = [_asset(args.asset)] if args.asset else Asset.tradables()
    for asset in assets:
        data = await pipeline.collect_asset(asset)
        n = pipeline.persist(data)
        total += n
        print(f"\n{asset.value}: {n} observations")
        for name, res in data.items():
            print(f"  {'OK ' if res.ok else '-- '} {name:<16} {len(res.observations):>4} obs"
                  + ("" if res.ok else f"  {res.user_message[:60]}"))

    print(f"\nTotal observations stored: {total}")
    await get_http().close()
    return 0


async def cmd_analyze(args) -> int:
    from .pipeline.orchestrator import get_pipeline
    from .providers.http import get_http

    init_db()
    pipeline = get_pipeline()
    gdata = await pipeline.collect_global()
    assets = [_asset(args.asset)] if args.asset else Asset.tradables()

    for asset in assets:
        analysis = await pipeline.analyze_asset(asset, gdata)
        if args.json:
            print(json.dumps(analysis.model_dump(mode="json"), indent=2, default=str))
        else:
            c = analysis.conviction
            print(f"\n{asset.value}  {analysis.price:,.2f} USD  "
                  f"({analysis.change_24h_pct:+.2f}% 24h)  {analysis.market_regime}")
            for horizon in ("short", "medium", "long"):
                h = c[horizon]
                print(f"  {horizon:<7} {h['score']:+7.1f}  {h['label']:<18} conf {h['confidence']:.0f}%")
            for domain, card in analysis.scores.items():
                if card["available"]:
                    print(f"    {domain:<12} {card['score']:+7.1f}  conf {card['confidence']:5.1f}%  {card['freshness']}")
                else:
                    print(f"    {domain:<12} UNAVAILABLE  {card['unavailable_reason'][:50]}")
    await get_http().close()
    return 0


async def cmd_report(args) -> int:
    from .db import repo
    from .pipeline.orchestrator import get_pipeline
    from .providers.http import get_http
    from .reports.renderer import render_report

    init_db()
    pipeline = get_pipeline()
    gdata = await pipeline.collect_global()
    assets = [_asset(args.asset)] if args.asset else Asset.tradables()

    for asset in assets:
        analysis = await pipeline.analyze_asset(asset, gdata)
        text = render_report(analysis)
        print(text)
        print()
        conv = analysis.conviction
        try:
            repo.save_report(
                report_id=analysis.report_id, asset=asset,
                payload=analysis.model_dump(mode="json"), text_report=text,
                price=analysis.price,
                convictions={
                    "short": conv["short"]["score"],
                    "medium": conv["medium"]["score"],
                    "long": conv["long"]["score"],
                },
                scores=analysis.scores,
                confidence=conv.get("overall_confidence", 0.0),
                market_regime=analysis.market_regime, llm_used=analysis.llm_used,
            )
        except Exception as exc:
            print(f"(report not saved: {exc})", file=sys.stderr)

        if args.out:
            path = Path(args.out)
            if len(assets) > 1:
                path = path.with_name(f"{path.stem}_{asset.value}{path.suffix}")
            path.write_text(text, encoding="utf-8")
            print(f"Saved to {path}")

    await get_http().close()
    return 0


def cmd_ingest(args) -> int:
    from .knowledge.ingest import ingest_directory
    from .knowledge.store import knowledge_stats

    init_db()
    directory = Path(args.path) if args.path else None
    result = ingest_directory(directory)
    if result.get("status") != "ok":
        print(f"Error: {result.get('reason')}", file=sys.stderr)
        return 1
    print(f"Processed {result['files_processed']} file(s), ingested {result['files_ingested']}, "
          f"{result['chunks_created']} chunks")
    for f in result["files"]:
        status = f["status"]
        marker = {"ingested": "OK ", "unchanged": "== ", "skipped": "-- ", "error": "!! "}.get(status, "?? ")
        detail = f.get("reason") or f"{f.get('chunks', 0)} chunks"
        print(f"  {marker}{Path(f['path']).name:<48} {detail}")
    print(f"\nKnowledge base: {knowledge_stats()}")
    return 0


def cmd_import_etf(args) -> int:
    from .providers.etf.csv_import import import_csv_file, import_directory

    init_db()
    if args.file:
        imported, errors = import_csv_file(Path(args.file))
    else:
        imported, errors = import_directory()
    print(f"Imported {imported} ETF flow rows")
    for e in errors:
        print(f"  warning: {e}", file=sys.stderr)
    return 0 if imported or not errors else 1


async def cmd_evaluate(args) -> int:
    from .core.enums import Timeframe
    from .evaluation.outcomes import OutcomeEvaluator
    from .providers.base import FetchRequest
    from .providers.http import get_http
    from .providers.registry import get_registry

    init_db()
    registry = get_registry()
    series: dict[Asset, list] = {}
    for asset in Asset.tradables():
        res = await registry.fetch(
            FetchRequest(capability="market.ohlcv", asset=asset, timeframe=Timeframe.H1, limit=500)
        )
        series[asset] = res.raw.candles if (res.ok and res.raw) else []

    def lookup(asset: Asset, at):
        best = None
        for candle in series.get(asset, []):
            if candle.timestamp <= at:
                best = candle.close
            else:
                break
        return best

    evaluator = OutcomeEvaluator()
    written = evaluator.evaluate_pending(lookup)
    print(f"Outcomes written: {written}")
    stats = evaluator.stats()
    print(json.dumps(stats.model_dump(mode="json"), indent=2, default=str))
    await get_http().close()
    return 0


async def cmd_providers(args) -> int:
    from .providers.http import get_http
    from .providers.registry import get_registry

    statuses = await get_registry().statuses()
    print(f"MOCK_MODE={get_settings().mock_mode}\n")
    for s in sorted(statuses, key=lambda x: (not x.available, x.name)):
        mark = "OK " if s.available else "-- "
        print(f"{mark}{s.name:<22} {s.reason[:80]}")
    await get_http().close()
    return 0


async def cmd_backfill(args) -> int:
    """Import as much reliable history as each source will give us."""
    from .history.backfill import run_backfill
    from .providers.http import get_http

    init_db()
    assets = [_asset(args.asset)] if args.asset else None
    timeframes = None
    if args.timeframe:
        from .core.enums import Timeframe

        timeframes = [Timeframe(args.timeframe)]

    print("Backfilling history (idempotent - safe to re-run)...\n")
    summary = await run_backfill(
        assets=assets, timeframes=timeframes,
        depth_days=args.days, skip_macro=args.skip_macro,
    )

    print(f"{'dataset':14s}{'asset':6s}{'tf':5s}{'rows':>8s}  period")
    for row in summary.get("ohlcv", []):
        if "error" in row:
            print(f"  OHLCV {row.get('asset')} {row.get('timeframe')}: ERROR {row['error'][:60]}")
            continue
        print(f"{'ohlcv':14s}{row['asset']:6s}{row['timeframe']:5s}{row['rows']:>8}"
              f"  {str(row['start'])[:10]} -> {str(row['end'])[:10]} ({row['days']:.0f}d)")
    for row in summary.get("funding", []):
        if "error" not in row:
            print(f"{'funding':14s}{row['asset']:6s}{'-':5s}{row.get('rows', 0):>8}"
                  f"  {str(row.get('start'))[:10]} -> {str(row.get('end'))[:10]}")
    for row in summary.get("open_interest", []):
        if "error" not in row:
            print(f"{'open_interest':14s}{row['asset']:6s}{'-':5s}{row.get('rows', 0):>8}"
                  f"  {str(row.get('start'))[:10]} -> {str(row.get('end'))[:10]}")
    for row in summary.get("macro", []) or []:
        if "error" in row:
            print(f"  MACRO {row.get('metric')}: {row['error'][:60]}")
        else:
            print(f"{'macro':14s}{'-':6s}{'-':5s}{row.get('rows', 0):>8}"
                  f"  {row.get('metric')} {str(row.get('start'))[:10]} -> {str(row.get('end'))[:10]}")
    for row in summary.get("macro_fred", []) or []:
        if "error" in row:
            print(f"  FRED: {row['error'][:90]}")
    for asset_value, info in (summary.get("etf") or {}).items():
        if info.get("rows"):
            print(f"{'etf_flows':14s}{asset_value:6s}{'-':5s}{info['rows']:>8}"
                  f"  {str(info['start'])[:10]} -> {str(info['end'])[:10]} "
                  f"({len(info['funds'])} funds)")
        else:
            print(f"  ETF {asset_value}: {info.get('error', 'no data')[:70]}")

    await get_http().close()
    return 0


def cmd_research(args) -> int:
    """Run the historical studies and print the findings, negative ones included."""
    from .research.runner import format_text_report, run_all

    init_db()
    assets = [_asset(args.asset)] if args.asset else None
    results = run_all(
        assets=assets,
        persist=not args.no_persist,
        include_lot3=not args.quick,
        run_walk_forward=not args.quick,
    )
    text = format_text_report(results)
    print(text)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"\nSaved to {args.out}")
    if getattr(args, "export", False):
        from .research.export import export_all

        paths = export_all(results)
        print("\nExported:")
        for key, value in paths.items():
            print(f"  {key}: {value}")
    return 0


def cmd_research_export(args) -> int:
    """Run the studies and export CSV / JSON / Markdown."""
    from .research.export import export_all
    from .research.runner import run_all

    init_db()
    assets = [_asset(args.asset)] if args.asset else None
    results = run_all(assets=assets, persist=True, include_lot3=True)
    paths = export_all(results, Path(args.out) if args.out else None)
    print("Research exported:")
    for key, value in paths.items():
        print(f"  {key:18s} {value}")
    return 0


def cmd_audit(args) -> int:
    """Audit every domain score against forward returns."""
    from .research.audit import audit_all, format_audit_table

    init_db()
    assets = [_asset(args.asset)] if args.asset else None
    results = audit_all(assets)
    text = format_audit_table(results)
    print(text)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"\nSaved to {args.out}")
    return 0


def cmd_import_oi(args) -> int:
    """Import open-interest history from CSV."""
    from .providers.derivatives.oi_import import import_directory

    init_db()
    result = import_directory(Path(args.path) if args.path else None)
    if result["status"] != "ok":
        print(f"Error: {result.get('reason')}", file=sys.stderr)
        return 1
    print(f"Imported {result['rows']} open-interest rows")
    for entry in result["files"]:
        print(f"  {entry['file']:40s} {entry['rows']:>6} rows, {entry['errors']} errors")
    for error in result["errors"][:10]:
        print(f"  warning: {error}", file=sys.stderr)
    print("\nCoverage after import:")
    for asset_value, coverage in result["coverage_after_import"].items():
        if coverage:
            print(f"  {asset_value}: {coverage['rows']} rows, "
                  f"{str(coverage['start'])[:10]} -> {str(coverage['end'])[:10]} "
                  f"({coverage['days']:.0f}d)")
    return 0


async def cmd_daily(args) -> int:
    """Generate the daily intelligence report."""
    from .db import repo
    from .pipeline.orchestrator import get_pipeline
    from .providers.http import get_http
    from .reports.daily import render_daily_report

    init_db()
    pipeline = get_pipeline()
    gdata = await pipeline.collect_global()
    analyses = [await pipeline.analyze_asset(a, gdata) for a in Asset.tradables()]

    first = analyses[0].domains if analyses else {}
    average = (
        sum(a.conviction["medium"]["score"] for a in analyses) / len(analyses)
        if analyses else 0.0
    )
    global_view = {
        "risk_regime": (
            "RISK ON" if average > 20 else "RISK OFF" if average < -20 else "NEUTRAL"
        ),
        "average_conviction": round(average, 1),
        "macro": first.get("macro"),
        "liquidity": first.get("liquidity"),
        "geopolitics": first.get("geopolitics"),
        "calendar": repo.upcoming_events(days=30),
    }

    text = render_daily_report(analyses, global_view)
    print(text)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"\nSaved to {args.out}")
    await get_http().close()
    return 0


def cmd_scheduler(args) -> int:
    """Run the scheduler in the foreground (Ctrl+C to stop)."""
    import asyncio as _asyncio

    from .scheduler import start_scheduler

    init_db()

    async def run() -> None:
        scheduler = start_scheduler()
        print("Scheduler running. Jobs:")
        for job in scheduler.get_jobs():
            print(f"  {job.id:14s} next run {job.next_run_time}")
        print("\nCtrl+C to stop.")
        try:
            while True:
                await _asyncio.sleep(3600)
        except (KeyboardInterrupt, _asyncio.CancelledError):
            scheduler.shutdown(wait=False)

    try:
        _asyncio.run(run())
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


def cmd_coverage(args) -> int:
    """Show the historical depth actually available per dataset."""
    from .core.enums import Timeframe
    from .history import snapshots as snap_module
    from .history import store

    init_db()
    print(f"{'asset':6s}{'tf':5s}{'rows':>8s}  period")
    for asset in Asset.tradables():
        for tf in (Timeframe.D1, Timeframe.H4, Timeframe.H1, Timeframe.W1):
            cov = store.candle_coverage(asset, tf)
            if cov["rows"]:
                print(f"{asset.value:6s}{tf.value:5s}{cov['rows']:>8}"
                      f"  {str(cov['start'])[:10]} -> {str(cov['end'])[:10]} ({cov['days']:.0f}d)")
        for metric, cov in store.derivatives_coverage(asset).items():
            print(f"{asset.value:6s}{'-':5s}{cov['rows']:>8}  {metric} "
                  f"{str(cov['start'])[:10]} -> {str(cov['end'])[:10]} ({cov['days']:.0f}d)")

    print()
    for metric, cov in store.macro_coverage().items():
        print(f"{'macro':6s}{'-':5s}{cov['rows']:>8}  {metric} "
              f"{str(cov['start'])[:10]} -> {str(cov['end'])[:10]} ({cov['days']:.0f}d)")

    print()
    for kind, stats in snap_module.snapshot_stats().items():
        print(f"snapshot {kind:14s} {stats['count']:>6} rows, "
              f"cadence {stats['cadence_minutes']}min, span {stats['span_hours']:.1f}h")
    return 0


def cmd_data_health(args) -> int:
    """Chaque source, actif par actif: utilisable maintenant, ou pourquoi non.

    La profondeur d'une série ne dit rien de sa fraîcheur. Sept mille points de
    funding immobiles depuis un jour se présentaient exactement comme sept
    mille points à jour, et rien ne faisait la différence.
    """
    import json

    from .core.data_health import report

    init_db()
    payload = report()
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0 if payload["healthy"] else 1

    for asset, rows in payload["assets"].items():
        print(f"\n{asset}")
        for row in rows:
            age = "—" if row["age_hours"] is None else f"{row['age_hours']:.1f}h"
            depth = "" if not row["history_days"] else f" {row['history_days']:.0f}j"
            detail = f"  {row['detail']}" if row["detail"] else ""
            print(
                f"  {row['source']:16s}{row['status']:16s}"
                f"{row['rows']:>7} lignes  âge {age:>8}{depth}{detail}"
            )
    counts = payload["counts"]
    print(
        f"\n{counts['OK']} à jour · {counts['STALE']} en retard · "
        f"{counts['UNAVAILABLE']} indisponibles · "
        f"{counts['NOT_APPLICABLE']} sans objet · {counts['ERROR']} en erreur"
    )
    print(payload["note"])
    # Sortie non nulle quand quelque chose est réellement à corriger, pour que
    # ce contrôle serve aussi de garde dans un cron ou une CI.
    return 0 if payload["healthy"] else 1


def cmd_serve(args) -> int:
    import uvicorn

    settings = get_settings()
    init_db()
    uvicorn.run(
        "crypto_intel.main:app",
        host=args.host or settings.api_host,
        port=args.port or settings.api_port,
        reload=args.reload,
        log_level=settings.log_level.lower(),
    )
    return 0


def cmd_init_db(args) -> int:
    from .knowledge.store import ensure_fts

    init_db()
    ensure_fts()
    print(f"Database ready: {get_settings().resolved_database_url}")
    return 0


def cmd_today(args) -> int:
    """The one-paragraph answer: direction, edge, crowding, uncertainty."""
    from .engines.analysis_context import reconstructed_regime
    from .engines.edge import EdgeEngine, UncertaintyEngine, build_decision_summary
    from .engines.leverage import LeverageCrowdingEngine
    from .engines.volatility import VolatilityRegimeEngine

    assets = [_asset(args.asset)] if args.asset else Asset.tradables()
    leverage_engine = LeverageCrowdingEngine()
    edge_engine = EdgeEngine()
    vol_engine = VolatilityRegimeEngine()
    uncertainty_engine = UncertaintyEngine()

    for asset in assets:
        crowding = leverage_engine.crowding(asset)
        edge = edge_engine.assess(asset)
        vol = vol_engine.assess(asset)
        uncertainty = uncertainty_engine.assess(asset, edge, crowding=crowding)
        summary = build_decision_summary(
            asset, edge, uncertainty, regime=reconstructed_regime(asset),
            crowding=crowding, volatility=vol,
        )
        state = leverage_engine.leverage_state(asset)
        funding = leverage_engine.funding_context(asset)

        print(f"\n=== {asset.value} ===")
        print(f"  {summary.statement}")
        print(f"  Direction     : {summary.market_direction} (held {summary.direction_confidence}% of last 20 days)")
        print(f"  Measured edge : {edge.state.value} ({edge.admitted_count} admitted, {edge.rejected_count} rejected)")
        print(f"  Crowding      : {crowding.level.value}"
              + (f" ({crowding.score}/100)" if crowding.score is not None else "")
              + f", direction {crowding.direction}")
        print(f"  Leverage state: {state.state.value}")
        print(f"  Funding       : {funding.band.value}"
              + (f" (p{funding.percentile})" if funding.percentile is not None else ""))
        print(f"  Volatility    : {vol.regime} {vol.direction.lower()}")
        print(f"  Uncertainty   : {uncertainty.level} ({uncertainty.score}/100)")
        print(f"  Actionable    : {summary.actionable}")
        for caveat in summary.caveats:
            print(f"    - {caveat}")
    return 0


async def cmd_backfill_oi(args) -> int:
    """Deep open-interest history from Bybit's public endpoint."""
    from .providers.derivatives.multi_exchange import backfill_bybit_open_interest
    from .providers.http import get_http

    assets = [_asset(args.asset)] if args.asset else Asset.tradables()
    try:
        for asset in assets:
            result = await backfill_bybit_open_interest(
                asset, depth_days=args.days, max_requests=args.max_requests
            )
            print(
                f"{asset.value}: {result.get('rows', 0)} rows "
                f"({str(result.get('start'))[:10]} -> {str(result.get('end'))[:10]}), "
                f"+{result['new_rows']} new in {result['requests']} requests"
            )
    finally:
        await get_http().close()
    return 0


def cmd_funding_study(args) -> int:
    """Funding bands versus forward returns, with FDR and a stability check."""
    import json
    import pathlib as _pathlib

    from .research.funding_conditioned import run_all

    assets = [_asset(args.asset)] if args.asset else None
    result = run_all(assets)

    for name, res in result["assets"].items():
        if res.get("status") != "OK":
            print(f"{name}: {res.get('status')}")
            continue
        conclusion = res["conclusion"]
        testing = res["multiple_testing"]
        print(f"\n=== {name} ===")
        print(f"  {testing['hypotheses_tested']} cells tested, "
              f"{testing['raw_significant']} raw, {testing['survives_fdr']} after FDR")
        print(f"  Contrarian hypothesis: {conclusion['contrarian_hypothesis']}")
        print(f"  {conclusion['contrarian_note']}")
        print(f"  Action: {conclusion['action']}")

    out = _pathlib.Path("data/research/funding_conditioned.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, default=str))
    print(f"\nWritten to {out}")
    return 0


def cmd_ml_dataset(args) -> int:
    """Export the point-in-time feature matrix plus its manifest."""
    from .research.registry import export_dataset

    assets = [_asset(args.asset)] if args.asset else Asset.tradables()
    for asset in assets:
        manifest = export_dataset(asset, out_dir=args.out or "data/datasets")
        if manifest.get("status") != "OK":
            print(f"{asset.value}: {manifest.get('status')}")
            continue
        print(
            f"{asset.value}: {manifest['rows']} rows, "
            f"{len(manifest['features_built'])} features, "
            f"hash {manifest['definition_hash']} -> {manifest['csv_path']}"
        )
    return 0


def cmd_research_patterns(args) -> int:
    """Measure whether detected chart patterns carry forward information."""
    import json
    import pathlib as _pathlib

    from .research.pattern_validation import run_all

    assets = [_asset(args.asset)] if args.asset else None
    result = run_all(assets)

    for key, res in result["results"].items():
        if res.get("status") != "OK":
            print(f"{key}: {res.get('status')}")
            continue
        testing = res["multiple_testing"]
        print(f"\n=== {key} ===")
        print(
            f"  {testing['hypotheses_tested']} hypotheses, "
            f"{testing['raw_significant']} raw, {testing['survives_fdr']} after FDR "
            f"({testing['expected_false_positives']} false positives expected)"
        )
        for name, entry in res["patterns"].items():
            print(f"  {name:28s} n={entry['raw_occurrences']:5d} -> {entry.get('verdict')}")
            if entry.get("verdict") == "MEASURABLE_EDGE":
                print(f"      {entry.get('note')}")

    out = _pathlib.Path("data/research/pattern_validation.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, default=str))
    print(f"\nWritten to {out}")
    return 0


def cmd_baselines(args) -> int:
    """The trivial strategies every signal must beat."""
    from .research.baselines import run_all

    assets = [_asset(args.asset)] if args.asset else None
    for name, res in run_all(assets)["assets"].items():
        if res.get("status") != "OK":
            print(f"{name}: {res.get('status')}")
            continue
        print(f"\n=== {name} ===")
        for horizon, rows in res["by_horizon"].items():
            print(f"  {horizon}:")
            for row in sorted(rows, key=lambda r: -(r["mean_return_pct"] or -999)):
                mean = row["mean_return_pct"]
                if mean is None:
                    continue
                print(
                    f"    {row['baseline']:26s} active {row['coverage_pct']:5.1f}% "
                    f"mean {mean:+7.3f}% win {row['win_rate']}%"
                )
    return 0


def cmd_structure(args) -> int:
    """Range, location, market structure and patterns for one asset."""
    from .engines.entry_opportunity import EntryOpportunityEngine
    from .history import store
    from .structure.location import StructuralLocationEngine
    from .structure.market_structure import MarketStructureEngine
    from .structure.patterns import build_context, detect_all

    assets = [_asset(args.asset)] if args.asset else Asset.tradables()
    timeframe = Timeframe(args.timeframe) if args.timeframe else Timeframe.H4

    for asset in assets:
        location = StructuralLocationEngine().assess(asset, timeframe)
        structure = MarketStructureEngine().assess(asset, timeframe)
        opportunity = EntryOpportunityEngine().assess(asset, timeframe)
        df = store.load_candles(asset, timeframe)
        ctx = build_context(df, timeframe)
        patterns = detect_all(ctx) if ctx is not None else []

        print(f"\n=== {asset.value} {timeframe.value} ===")
        print(f"  Structure      : {structure.state.value} [{' '.join(structure.labels)}]")
        print(f"  Location       : {location.state.value}")
        print(f"  Range          : {location.range_summary[:110]}")
        print(f"  Invalidation   : {location.invalidation[:110]}")
        print(f"  Entry opportunity: {opportunity.state.value} ({opportunity.score})")
        print(f"  Measured edge  : {opportunity.measured_edge_state}")
        if patterns:
            print("  Patterns:")
            for pattern in patterns:
                print(
                    f"    {pattern.name:28s} {pattern.state.value:10s} "
                    f"recognition {pattern.recognition_confidence:5.1f} "
                    f"[{pattern.pattern_class.value}] edge {pattern.edge_state.value}"
                )
        else:
            print("  Patterns       : none detected")
        if location.explanation:
            print("  Why:")
            for line in location.explanation[:6]:
                print(f"    - {line}")
    return 0


def cmd_research_structural(args) -> int:
    """Measure whether structural readings carry forward information."""
    import json
    import pathlib as _pathlib

    from .research.structural_research import run_all

    assets = [_asset(args.asset)] if args.asset else None
    timeframes = [Timeframe(args.timeframe)] if args.timeframe else None
    result = run_all(assets, timeframes, step=args.step)

    for key, res in result["results"].items():
        if res.get("status") != "OK":
            print(f"{key}: {res.get('status')}")
            continue
        testing = res["multiple_testing"]
        print(f"\n=== {key} ===")
        print(
            f"  {testing['hypotheses_tested']} hypotheses, "
            f"{testing['raw_significant']} raw, {testing['fdr_significant']} after FDR"
        )
        for label, entry in sorted(res["labels"].items()):
            print(
                f"  {label:40s} n={entry['raw_occurrences']:5d} -> {entry.get('edge_state')}"
            )

    out = _pathlib.Path("data/research/structural_research.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, default=str))
    print(f"\nWritten to {out}")
    return 0


def cmd_research_marginal(args) -> int:
    """The two central questions: does chart reading add anything?"""
    import json
    import pathlib as _pathlib

    from .research.marginal_value import run_all

    assets = [_asset(args.asset)] if args.asset else None
    result = run_all(assets, horizon=args.horizon)

    for name, res in result["assets"].items():
        if res.get("status") == "ERROR":
            print(f"{name}: ERROR {res.get('error')}")
            continue
        layers = res["layers"]
        marginal = res["location_marginal_value"]
        print(f"\n=== {name} ===")
        for layer_name, layer in layers.get("layers", {}).items():
            if layer.get("status") != "OK":
                continue
            print(
                f"  {layer_name:20s} OOS R2 {layer['oos_r2']:+.4f} "
                f"AUC {layer.get('oos_auc')}"
            )
        print(f"  Layer verdict: {layers.get('verdict', {}).get('answer')}")
        if marginal.get("status") == "OK":
            print(f"  Range location: {marginal['answer']['verdict']}")
            print(f"    {marginal['answer']['statement']}")

    out = _pathlib.Path("data/research/marginal_value.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, default=str))
    print(f"\nWritten to {out}")
    return 0


def cmd_research_replicate(args) -> int:
    """Do the LOT 4 findings survive the LOT 5 detectors?"""
    import json
    import pathlib as _pathlib

    from .research.replication import run_all

    result = run_all()
    for key, res in result["findings"].items():
        print(f"\n=== {key} ===")
        if res.get("status") != "OK":
            print(f"  {res.get('status')}")
            comparison = res.get("comparison")
            if comparison:
                print(f"  {comparison['statement']}")
            continue
        lot5 = res.get("lot5", {})
        comparison = res.get("comparison", {})
        print(
            f"  LOT4 excess {res['lot4']['lot4_excess_pct']:+.2f}% "
            f"(effective_n {res['lot4'].get('lot4_effective_n')})"
        )
        print(
            f"  LOT5 excess {lot5.get('excess_vs_same_regime_pct')}% "
            f"(raw_n {lot5.get('raw_n')}, effective_n {lot5.get('effective_n')})"
        )
        print(f"  Verdict: {comparison.get('verdict')}")
        print(f"  {comparison.get('statement', '')}")

    out = _pathlib.Path("data/research/replication.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, default=str))
    print(f"\nWritten to {out}")
    return 0


def cmd_research_claims(args) -> int:
    """Test educational claims against measured data."""
    import json
    import pathlib as _pathlib

    from .research.claim_validation import run_all

    assets = [_asset(args.asset)] if args.asset else None
    result = run_all(assets)
    if result.get("status") == "NO_CLAIMS":
        print(result["note"])
        return 1

    print(f"{result['claims_tested']} claims tested")
    print(f"Verdicts: {result['verdict_counts']}")
    testing = result["multiple_testing"]
    print(
        f"FDR: {testing['hypotheses_tested']} hypotheses, "
        f"{testing['raw_significant']} raw, {testing['fdr_significant']} survive"
    )
    for asset_name, asset_result in result["results"].items():
        if asset_result.get("status") != "OK":
            continue
        print(f"\n=== {asset_name} ===")
        for claim in asset_result["claims"]:
            if claim["verdict"] in ("UNTESTABLE",):
                continue
            print(f"  {claim['concept']:30s} {claim['verdict']}")
            if claim["verdict"] in ("CONTRADICTED", "SUPPORTED"):
                print(f"      {claim.get('note', '')[:160]}")

    out = _pathlib.Path("data/research/claim_validation.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, default=str))
    print(f"\nWritten to {out}")
    return 0


def cmd_import_transcript(args) -> int:
    """Import a trader transcript the user already holds. Nothing is fetched."""
    import pathlib as _pathlib
    from datetime import datetime as _datetime

    from .trader_knowledge.dataset import add_example
    from .trader_knowledge.transcript import build_example

    path = _pathlib.Path(args.file)
    if not path.exists():
        print(f"File not found: {path}")
        return 1
    text = path.read_text(encoding="utf-8", errors="replace")

    published = None
    if args.date:
        try:
            published = _datetime.fromisoformat(args.date).replace(tzinfo=UTC)
        except ValueError:
            print(f"Could not parse --date '{args.date}'; expected ISO format")
            return 1

    example, parse = build_example(
        text, source=args.source or "lexa_moon", author=args.author or "",
        source_url=args.url, published_at=published, analysis_time=published,
        asset_override=args.asset, timeframe_override=args.timeframe,
    )

    print(f"Parsed: asset={example.asset} timeframe={example.timeframe} "
          f"quality={example.data_quality.value}")
    print(f"Concepts: {', '.join(parse.concepts) or 'none'}")
    print(f"Levels: range {parse.range_bottom} - {parse.range_top}, "
          f"supports {parse.supports}, invalidation {parse.invalidation}")
    if parse.ambiguities:
        print("Ambiguities (nothing was guessed):")
        for item in parse.ambiguities:
            print(f"  - {item}")

    if example.data_quality.value == "UNUSABLE":
        print("\nNot stored: the example cannot be aligned to market data.")
        return 1

    result = add_example(example)
    print(f"\n{result['status']}: {result.get('id')}")
    if result["status"] == "ADDED":
        from .trader_knowledge.alignment import align_example

        aligned = align_example(example)
        print(f"Alignment: {aligned['status']}")
        if aligned["status"] == "ALIGNED":
            context = aligned["what_market_data_showed_at_t"]
            print(f"  Market at {context['market_timestamp'][:10]}: "
                  f"regime {context['regime_at_t']}, location {context['location_at_t']}")
    return 0


def cmd_annotate(args) -> int:
    """Correct an annotation. The previous value is preserved."""
    from .trader_knowledge.dataset import annotation_history, correct_example

    if args.history:
        for entry in annotation_history(args.example_id):
            print(
                f"v{entry['annotation_version']} {entry['corrected_at'][:19]} "
                f"{entry['field_name']}: {entry['previous_value']} -> {entry['new_value']}"
            )
            if entry.get("correction_reason"):
                print(f"    reason: {entry['correction_reason']}")
        return 0

    if not args.field or args.value is None:
        print("Provide --field and --value, or --history")
        return 1

    value: Any = args.value
    with contextlib.suppress(TypeError, ValueError):
        value = float(value)

    result = correct_example(
        args.example_id, args.field, value, reason=args.reason or ""
    )
    print(result)
    return 0 if result["status"] == "CORRECTED" else 1


def cmd_dataset_quality(args) -> int:
    from .trader_knowledge.dataset import dataset_quality

    quality = dataset_quality()
    if quality["status"] == "EMPTY":
        print(quality["note"])
        print(f"Target: {quality['target']}")
        return 0
    for key in (
        "number_examples", "human_verified", "market_episodes",
        "effective_sample_size", "examples_per_episode", "usable_for_study",
    ):
        print(f"  {key}: {quality[key]}")
    print(f"  per asset: {quality['examples_per_asset']}")
    print(f"  per structure: {quality['examples_per_structure']}")
    for gap in quality["gaps"]:
        print(f"  GAP: {gap}")
    return 0


def cmd_export(args) -> int:
    """Export research artefacts with full provenance."""
    from .research.export_lot5 import export_all

    result = export_all(out_dir=args.out or "data/exports", fmt=args.format or "json")
    for name, info in result["exports"].items():
        print(f"  {name}: {info}")
    return 0


def cmd_daily_v2(args) -> int:
    """The full daily read for each asset."""
    from .engines.daily_report import DailyReportEngine

    assets = [_asset(args.asset)] if args.asset else Asset.tradables()
    engine = DailyReportEngine()
    for asset in assets:
        print(engine.build(asset)["text"])
        print()
    return 0


def cmd_revalidate(args) -> int:
    """Re-test the pre-registered candidates under the LOT 6A framework."""
    import json
    import pathlib as _pathlib

    from .research.revalidation import run_all

    result = run_all()
    print(f"verdicts: {result['verdict_counts']}")
    for entry in result["results"]:
        if entry.get("status") != "OK":
            print(f"  {entry['id']:34s} {entry.get('status')}")
            continue
        strat = entry.get("stratified", {})
        sample = entry.get("effective_sample", {})
        print(
            f"  {entry['id']:34s} {entry.get('verdict', '?'):18s} "
            f"LOT5 {entry['lot5_excess_pct']:+.2f}% -> "
            f"strat {strat.get('excess_pct')}% / resid {entry.get('residual_excess_pct')}% "
            f"(eff_n {sample.get('effective_n')})"
        )
        print(f"      {entry.get('binding_reason', '')}")

    out = _pathlib.Path("data/research/revalidation.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, default=str))
    print(f"\nWritten to {out}")
    return 0


def cmd_lot6b(args: argparse.Namespace) -> int:
    """Run every LOT 6B stage and print what survived."""
    from .research.lot6b import run_and_save

    result = run_and_save()

    calibration = result["calibration"]
    print(f"pipeline: {calibration.get('verdict')}")
    for key, floor in sorted(calibration.get("detection_floors", {}).items()):
        print(
            f"  {key:4s} detection floor {floor.get('empirical_floor_pct')}% "
            f"vs meaningful {floor.get('meaningful_effect_pct')}%"
        )

    ablation = result["ablation"]
    print(f"\nablation: {ablation.get('verdict')} "
          f"(full-model out-of-sample R2 {ablation.get('full_model', {}).get('r2')})")

    print("\nfunnel:")
    for stage in result["evidence"]["funnel"]["stages"]:
        print(f"  {stage['stage']:42s} {stage['count']:3d}")

    print("\nshortlist:")
    for entry in result["shortlist"]["shortlist"]:
        print(
            f"  L{entry['evidence_level']} {entry['level_name']:18s} "
            f"{entry['claim'][:46]:46s} {entry['effect_pct']:+.2f}% "
            f"blocked at {entry['blocked_at']}"
        )

    print(f"\nVERDICT: {result['verdict']}")
    print("Written to data/research/lot6b.json")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="crypto-intel",
        description="Personal crypto market intelligence. Analysis only - never trades.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("serve", help="Run the API server")
    p.add_argument("--host")
    p.add_argument("--port", type=int)
    p.add_argument("--reload", action="store_true")
    p.set_defaults(func=cmd_serve, is_async=False)

    p = sub.add_parser("collect", help="Fetch and store data")
    p.add_argument("--asset")
    p.set_defaults(func=cmd_collect, is_async=True)

    p = sub.add_parser("analyze", help="Run the full analysis")
    p.add_argument("--asset")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_analyze, is_async=True)

    p = sub.add_parser("report", help="Generate the text report")
    p.add_argument("--asset")
    p.add_argument("--out")
    p.set_defaults(func=cmd_report, is_async=True)

    p = sub.add_parser("ingest-knowledge", help="Ingest documents from knowledge/")
    p.add_argument("--path")
    p.set_defaults(func=cmd_ingest, is_async=False)

    p = sub.add_parser("import-etf", help="Import ETF flow CSV files")
    p.add_argument("--file")
    p.set_defaults(func=cmd_import_etf, is_async=False)

    p = sub.add_parser("evaluate", help="Score past reports against realised prices")
    p.set_defaults(func=cmd_evaluate, is_async=True)

    p = sub.add_parser("providers", help="Show provider availability")
    p.set_defaults(func=cmd_providers, is_async=True)

    p = sub.add_parser("today", help="What do we actually know today?")
    p.add_argument("--asset")
    p.set_defaults(func=cmd_today, is_async=False)

    p = sub.add_parser("backfill-oi", help="Deep open-interest history from Bybit")
    p.add_argument("--asset")
    p.add_argument("--days", type=int, default=4000)
    p.add_argument("--max-requests", type=int, default=40, dest="max_requests")
    p.set_defaults(func=cmd_backfill_oi, is_async=True)

    p = sub.add_parser("funding-study", help="Funding bands versus forward returns")
    p.add_argument("--asset")
    p.set_defaults(func=cmd_funding_study, is_async=False)

    p = sub.add_parser("ml-dataset", help="Export the point-in-time feature matrix")
    p.add_argument("--asset")
    p.add_argument("--out")
    p.set_defaults(func=cmd_ml_dataset, is_async=False)

    p = sub.add_parser("research-patterns", help="Do chart patterns carry information?")
    p.add_argument("--asset")
    p.set_defaults(func=cmd_research_patterns, is_async=False)

    p = sub.add_parser("baselines", help="Trivial strategies every signal must beat")
    p.add_argument("--asset")
    p.set_defaults(func=cmd_baselines, is_async=False)

    p = sub.add_parser("structure", help="Range, location, structure and patterns")
    p.add_argument("--asset")
    p.add_argument("--timeframe", default="4h")
    p.set_defaults(func=cmd_structure, is_async=False)

    p = sub.add_parser("research-structural", help="Do structures carry information?")
    p.add_argument("--asset")
    p.add_argument("--timeframe")
    p.add_argument("--step", type=int, default=1)
    p.set_defaults(func=cmd_research_structural, is_async=False)

    p = sub.add_parser("research-marginal", help="Does chart reading add anything?")
    p.add_argument("--asset")
    p.add_argument("--horizon", type=int, default=7)
    p.set_defaults(func=cmd_research_marginal, is_async=False)

    p = sub.add_parser("research-replicate", help="Replicate the LOT 4 findings")
    p.set_defaults(func=cmd_research_replicate, is_async=False)

    p = sub.add_parser("research-claims", help="Test educational claims against data")
    p.add_argument("--asset")
    p.set_defaults(func=cmd_research_claims, is_async=False)

    p = sub.add_parser("import-transcript", help="Import a transcript you already hold")
    p.add_argument("--file", required=True)
    p.add_argument("--source", default="lexa_moon")
    p.add_argument("--author")
    p.add_argument("--url")
    p.add_argument("--date", help="ISO date of the analysis")
    p.add_argument("--asset")
    p.add_argument("--timeframe")
    p.set_defaults(func=cmd_import_transcript, is_async=False)

    p = sub.add_parser("annotate", help="Correct an annotation (versioned)")
    p.add_argument("example_id")
    p.add_argument("--field")
    p.add_argument("--value")
    p.add_argument("--reason")
    p.add_argument("--history", action="store_true")
    p.set_defaults(func=cmd_annotate, is_async=False)

    p = sub.add_parser("dataset-quality", help="Human-example dataset coverage")
    p.set_defaults(func=cmd_dataset_quality, is_async=False)

    p = sub.add_parser("export", help="Export research artefacts")
    p.add_argument("--out")
    p.add_argument("--format", choices=["json", "csv", "parquet"], default="json")
    p.set_defaults(func=cmd_export, is_async=False)

    p = sub.add_parser("daily-v2", help="Full daily read, sixteen sections")
    p.add_argument("--asset")
    p.set_defaults(func=cmd_daily_v2, is_async=False)

    p = sub.add_parser("lot6b", help="Evidence, power and pooling (LOT 6B)")
    p.set_defaults(func=cmd_lot6b)

    p = sub.add_parser("revalidate", help="Re-test candidates under LOT 6A rules")
    p.set_defaults(func=cmd_revalidate, is_async=False)

    p = sub.add_parser("init-db", help="Create database tables")
    p.set_defaults(func=cmd_init_db, is_async=False)

    p = sub.add_parser("backfill", help="Import historical data (idempotent)")
    p.add_argument("--asset")
    p.add_argument("--timeframe")
    p.add_argument("--days", type=int)
    p.add_argument("--skip-macro", action="store_true")
    p.set_defaults(func=cmd_backfill, is_async=True)

    p = sub.add_parser("research", help="Run the historical studies")
    p.add_argument("--asset")
    p.add_argument("--out")
    p.add_argument("--no-persist", action="store_true")
    p.add_argument("--quick", action="store_true", help="Skip the slower LOT 3 layers")
    p.add_argument("--export", action="store_true", help="Also export CSV/JSON/Markdown")
    p.set_defaults(func=cmd_research, is_async=False)

    p = sub.add_parser("research-export", help="Run the studies and export the results")
    p.add_argument("--asset")
    p.add_argument("--out", help="Output directory")
    p.set_defaults(func=cmd_research_export, is_async=False)

    p = sub.add_parser("audit", help="Audit each domain score against forward returns")
    p.add_argument("--asset")
    p.add_argument("--out")
    p.set_defaults(func=cmd_audit, is_async=False)

    p = sub.add_parser("import-oi", help="Import open-interest history from CSV")
    p.add_argument("--path")
    p.set_defaults(func=cmd_import_oi, is_async=False)

    p = sub.add_parser("daily", help="Generate the daily intelligence report")
    p.add_argument("--out")
    p.set_defaults(func=cmd_daily, is_async=True)

    p = sub.add_parser("scheduler", help="Run the scheduler in the foreground")
    p.set_defaults(func=cmd_scheduler, is_async=False)

    p = sub.add_parser("coverage", help="Show available historical depth")
    p.set_defaults(func=cmd_coverage, is_async=False)

    p = sub.add_parser(
        "data-health",
        help="Per-source freshness for BTC/ETH/SOL; non-zero exit when stale",
    )
    p.add_argument("--json", action="store_true", help="Machine-readable output")
    p.set_defaults(func=cmd_data_health, is_async=False)

    args = parser.parse_args()
    setup_logging(get_settings().log_level)

    if getattr(args, "is_async", False):
        return asyncio.run(args.func(args))
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

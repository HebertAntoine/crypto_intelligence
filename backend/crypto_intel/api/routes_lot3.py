"""LOT 3 endpoints: audit, asymmetry, derivatives, regimes, features,
walk-forward, champion/challenger, live performance."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from ..core.enums import Asset
from ..logging_setup import get_logger

log = get_logger("api.lot3")
router = APIRouter()


def _parse_asset(symbol: str) -> Asset:
    try:
        return Asset(symbol.upper())
    except ValueError:
        raise HTTPException(404, f"Unknown asset '{symbol}'. Supported: BTC, ETH, SOL.") from None


@router.get("/research/audit")
async def research_audit(asset: str | None = None) -> dict[str, Any]:
    """Per-domain verdicts: is each score worth its weight?"""
    from ..research.audit import audit_all

    assets = [_parse_asset(asset)] if asset else None
    return await asyncio.to_thread(audit_all, assets)


@router.get("/research/asymmetry/{symbol}")
async def research_asymmetry(symbol: str) -> dict[str, Any]:
    from ..research.etf_asymmetry import analyse_asymmetry

    return await asyncio.to_thread(analyse_asymmetry, _parse_asset(symbol))


@router.get("/research/derivatives/{symbol}")
async def research_derivatives(symbol: str) -> dict[str, Any]:
    from ..research.derivatives_study import (
        analyse_percentile_bands,
        analyse_price_oi_funding,
        suggest_thresholds,
    )

    asset = _parse_asset(symbol)
    bands, interactions, thresholds = await asyncio.gather(
        asyncio.to_thread(analyse_percentile_bands, asset),
        asyncio.to_thread(analyse_price_oi_funding, asset),
        asyncio.to_thread(suggest_thresholds, asset),
    )
    return {
        "asset": asset.value,
        "percentile_bands": bands,
        "price_oi_funding": interactions,
        "suggested_thresholds": thresholds,
    }


@router.get("/research/regimes/{symbol}")
async def research_regimes(symbol: str, horizon: int = Query(7)) -> dict[str, Any]:
    from ..research.regime_conditioned import analyse_all_signals

    return await asyncio.to_thread(analyse_all_signals, _parse_asset(symbol), horizon)


@router.get("/research/features/{symbol}")
async def research_features(
    symbol: str, walk_forward: bool = Query(True)
) -> dict[str, Any]:
    """Feature importance. Slow when walk-forward is enabled."""
    from ..research.features import analyse_features

    return await asyncio.to_thread(
        analyse_features, _parse_asset(symbol), None, walk_forward
    )


@router.get("/research/candidate-weights")
async def research_candidate_weights(asset: str | None = None) -> dict[str, Any]:
    """Candidate weights and the champion/challenger verdict.

    Never writes scoring.yaml - promotion stays a human action.
    """
    from ..research.candidate_weights import run_full

    assets = [_parse_asset(asset)] if asset else None
    return await asyncio.to_thread(run_full, assets, False)


@router.get("/research/live-performance")
async def research_live_performance(asset: str | None = None) -> dict[str, Any]:
    """Live accuracy from immutable prediction snapshots.

    Deliberately separate from backtest figures: one is a track record, the
    other is a replay of current logic over old data.
    """
    from ..history.immutable import live_performance

    return await asyncio.to_thread(
        live_performance, _parse_asset(asset) if asset else None
    )


@router.get("/research/snapshots/integrity")
async def snapshots_integrity() -> dict[str, Any]:
    """Verify no recorded prediction has been altered after the fact."""
    from ..history.immutable import verify_all

    return await asyncio.to_thread(verify_all)


@router.post("/research/evaluate-live")
async def evaluate_live() -> dict[str, Any]:
    """Score elapsed horizons against realised prices."""
    from datetime import datetime

    from ..core.enums import Timeframe
    from ..history import store
    from ..history.immutable import evaluate_pending

    series = {asset: store.load_candles(asset, Timeframe.H1) for asset in Asset.tradables()}

    def lookup(asset: Asset, at: datetime) -> float | None:
        df = series.get(asset)
        if df is None or df.empty:
            return None
        subset = df[df.index <= at]
        return float(subset["close"].iloc[-1]) if len(subset) else None

    return await asyncio.to_thread(evaluate_pending, lookup)


@router.get("/research/export")
async def research_export() -> dict[str, Any]:
    """Run every study and export CSV / JSON / Markdown."""
    from ..research.export import export_all
    from ..research.runner import run_all

    results = await asyncio.to_thread(run_all, None, True, True, True)
    paths = await asyncio.to_thread(export_all, results)
    return {"paths": paths, "summary": results.get("summary", {})}


@router.get("/assets/{symbol}/empirical")
async def asset_empirical(symbol: str) -> dict[str, Any]:
    """Historical analogues for the current configuration."""
    from .routes import get_analysis

    analysis = await get_analysis(_parse_asset(symbol))
    return {
        "asset": analysis.asset.value,
        "empirical": analysis.empirical,
        "probability": analysis.probability,
        "rsi_context": analysis.rsi_context,
        "etf_split": analysis.etf_split,
        "confrontations": analysis.confrontations,
    }

"""LOT 4 endpoints: edge, uncertainty, leverage, volatility, multi-exchange.

The endpoints here answer "what do we actually know", which is a different
question from the scoring endpoints and is deliberately reachable without
going through them.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from ..core.enums import Asset
from ..logging_setup import get_logger

log = get_logger("api.lot4")
router = APIRouter()


def _parse_asset(symbol: str) -> Asset:
    try:
        return Asset(symbol.upper())
    except ValueError:
        raise HTTPException(404, f"Unknown asset '{symbol}'. Supported: BTC, ETH, SOL.") from None


@router.get("/edge/{symbol}")
async def edge_state(symbol: str) -> dict[str, Any]:
    """Has any predictive edge actually been measured for this asset?"""
    from ..engines.edge import EdgeEngine

    asset = _parse_asset(symbol)
    return (await asyncio.to_thread(EdgeEngine().assess, asset)).model_dump()


@router.get("/edge")
async def edge_all() -> dict[str, Any]:
    from ..engines.edge import EdgeEngine

    engine = EdgeEngine()
    results = await asyncio.to_thread(
        lambda: {a.value: engine.assess(a).model_dump() for a in Asset.tradables()}
    )
    return {
        "assets": results,
        "note": (
            "EdgeState is computed from research output alone and never from the current "
            "regime. A bullish market with NO_MEASURABLE_EDGE is a coherent and common "
            "result, not a contradiction."
        ),
    }


@router.get("/leverage/{symbol}")
async def leverage(symbol: str) -> dict[str, Any]:
    """Funding percentile, OI/price state and crowding."""
    from ..engines.leverage import LeverageCrowdingEngine

    asset = _parse_asset(symbol)
    return await asyncio.to_thread(LeverageCrowdingEngine().assess, asset)


@router.get("/volatility/{symbol}")
async def volatility(symbol: str) -> dict[str, Any]:
    from ..engines.volatility import VolatilityRegimeEngine

    asset = _parse_asset(symbol)
    return (await asyncio.to_thread(VolatilityRegimeEngine().assess, asset)).model_dump()


@router.get("/derivatives/aggregate/{symbol}")
async def derivatives_aggregate(symbol: str) -> dict[str, Any]:
    """Funding and OI across Binance, Bybit and OKX."""
    from ..providers.derivatives.multi_exchange import aggregate

    asset = _parse_asset(symbol)
    return (await aggregate(asset)).to_dict()


class _ReconstructedRegime:
    """Minimal stand-in carrying the same attributes the summary reads."""

    def __init__(self, label: str, confidence: float) -> None:
        self.regime = type("R", (), {"value": label})()
        self.confidence = confidence


def _reconstructed_regime(asset: Asset) -> _ReconstructedRegime:
    from ..core.enums import Timeframe
    from ..history import store
    from ..research.regime_conditioned import reconstruct_regime

    df = store.load_candles(asset, Timeframe.D1)
    if df.empty or len(df) < 200:
        return _ReconstructedRegime("UNDETERMINED", 0.0)
    labels = reconstruct_regime(df).dropna()
    if labels.empty:
        return _ReconstructedRegime("UNDETERMINED", 0.0)

    label = str(labels.iloc[-1])
    # Confidence from persistence: a label that just flipped is less settled
    # than one that has held for weeks.
    recent = labels.iloc[-20:]
    agreement = float((recent == label).mean() * 100)
    return _ReconstructedRegime(label, round(agreement, 1))


@router.get("/today/{symbol}")
async def today(symbol: str) -> dict[str, Any]:
    """The decision summary: direction, timing, edge, crowding, uncertainty.

    Assembled without running the LLM analysts, so it stays cheap enough to
    poll and returns the same separation of concerns the reports use.
    """
    from ..engines.edge import EdgeEngine, UncertaintyEngine, build_decision_summary
    from ..engines.leverage import LeverageCrowdingEngine
    from ..engines.volatility import VolatilityRegimeEngine

    asset = _parse_asset(symbol)

    def build() -> dict[str, Any]:
        leverage_engine = LeverageCrowdingEngine()
        crowding = leverage_engine.crowding(asset)
        edge = EdgeEngine().assess(asset)
        vol = VolatilityRegimeEngine().assess(asset)
        uncertainty = UncertaintyEngine().assess(asset, edge, crowding=crowding)

        # Direction from the causal reconstruction used in research, so this
        # endpoint stays independent of an LLM run. It uses trend, structure
        # and momentum only - the domains present over the whole history.
        regime = _reconstructed_regime(asset)
        summary = build_decision_summary(
            asset, edge, uncertainty, regime=regime, crowding=crowding, volatility=vol
        )
        return {
            "asset": asset.value,
            "decision_summary": summary.model_dump(mode="json"),
            "direction_source": (
                "reconstructed from price structure (trend, EMA position, momentum, ADX); "
                "not the full multi-domain regime engine, which needs a pipeline run"
            ),
            "edge": edge.model_dump(),
            "uncertainty": uncertainty.model_dump(),
            "crowding": crowding.model_dump(),
            "leverage_state": leverage_engine.leverage_state(asset).model_dump(),
            "funding": leverage_engine.funding_context(asset).model_dump(),
            "volatility": vol.model_dump(),
        }

    return await asyncio.to_thread(build)


@router.get("/research/funding-conditioned")
async def funding_conditioned(
    asset: str | None = None,
    recompute: bool = Query(False, description="Recompute instead of reading the stored run"),
) -> dict[str, Any]:
    """Funding bands versus forward returns, conditioned on regime and momentum."""
    import json
    import pathlib

    from ..research.funding_conditioned import run_all

    if not recompute:
        path = pathlib.Path("data/research/funding_conditioned.json")
        if path.exists():
            try:
                stored = json.loads(path.read_text())
                if asset:
                    key = _parse_asset(asset).value
                    assets = stored.get("assets", stored)
                    return {"asset": key, "result": assets.get(key, {}), "source": "stored"}
                return {**stored, "source": "stored"}
            except (json.JSONDecodeError, OSError) as exc:
                log.warning("stored_study_unreadable", error=str(exc))

    assets = [_parse_asset(asset)] if asset else None
    return await asyncio.to_thread(run_all, assets)


@router.get("/cross-asset/{symbol}")
async def cross_asset(symbol: str, window: int = Query(90, ge=30, le=365)) -> dict[str, Any]:
    """Rolling correlation and beta against macro series."""
    from ..engines.cross_asset import CrossAssetAnalyzer

    asset = _parse_asset(symbol)
    return (
        await asyncio.to_thread(CrossAssetAnalyzer(window=window).assess, asset)
    ).model_dump()


@router.get("/market/ratios")
async def market_ratios() -> dict[str, Any]:
    """ETH/BTC, SOL/BTC, SOL/ETH and BTC dominance."""
    from ..engines.cross_asset import MarketRatiosEngine

    return await asyncio.to_thread(MarketRatiosEngine().assess)


@router.get("/market/breadth")
async def market_breadth() -> dict[str, Any]:
    from ..engines.cross_asset import CryptoBreadthEngine

    return (await asyncio.to_thread(CryptoBreadthEngine().assess)).model_dump()


@router.get("/market/liquidity")
async def market_liquidity() -> dict[str, Any]:
    from ..engines.cross_asset import LiquidityRegimeEngine

    return (await asyncio.to_thread(LiquidityRegimeEngine().assess)).model_dump()


@router.get("/breakout/{symbol}")
async def breakout(symbol: str, timeframe: str = "1d") -> dict[str, Any]:
    """How convincing the most recent level break is - not what follows it."""
    from ..core.enums import Timeframe
    from ..engines.breakout import BreakoutQualityEngine

    asset = _parse_asset(symbol)
    try:
        tf = Timeframe(timeframe)
    except ValueError:
        raise HTTPException(400, f"Unknown timeframe '{timeframe}'") from None
    return (
        await asyncio.to_thread(BreakoutQualityEngine().assess, asset, tf)
    ).model_dump()


@router.get("/liquidations/{symbol}")
async def liquidations(symbol: str) -> dict[str, Any]:
    """Liquidation data when a connector exists, cascade CONDITIONS always."""
    from ..engines.liquidation import LiquidationRiskEngine

    asset = _parse_asset(symbol)
    return (await LiquidationRiskEngine().assess(asset)).model_dump()


@router.get("/research/baselines")
async def research_baselines(asset: str | None = None) -> dict[str, Any]:
    """The trivial strategies any signal must beat."""
    from ..research.baselines import run_all

    assets = [_parse_asset(asset)] if asset else None
    return await asyncio.to_thread(run_all, assets)


@router.get("/research/patterns")
async def research_patterns(asset: str | None = None, recompute: bool = False) -> dict[str, Any]:
    """Do the detected chart patterns carry forward information?"""
    import json
    import pathlib

    if not recompute:
        path = pathlib.Path("data/research/pattern_validation.json")
        if path.exists():
            try:
                return {**json.loads(path.read_text()), "source": "stored"}
            except (json.JSONDecodeError, OSError):
                pass

    from ..research.pattern_validation import run_all

    assets = [_parse_asset(asset)] if asset else None
    return await asyncio.to_thread(run_all, assets)


@router.get("/research/drift")
async def research_drift(asset: str | None = None) -> dict[str, Any]:
    """Shadow-model live performance against backtest expectation."""
    from ..research.drift import run_all

    assets = [_parse_asset(asset)] if asset else None
    return await asyncio.to_thread(run_all, assets)


@router.get("/research/features")
async def research_feature_registry() -> dict[str, Any]:
    """Declared features, their point-in-time status and definition hashes."""
    from ..research.registry import FEATURE_VERSION, get_registry

    registry = get_registry()
    return {
        "feature_version": FEATURE_VERSION,
        "features": registry.describe(),
        "backtest_safe": registry.names(backtest_safe_only=True),
    }

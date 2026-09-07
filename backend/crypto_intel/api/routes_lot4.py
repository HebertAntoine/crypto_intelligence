"""LOT 4 endpoints: edge, uncertainty, leverage, volatility, multi-exchange.

The endpoints here answer "what do we actually know", which is a different
question from the scoring endpoints and is deliberately reachable without
going through them.
"""

from __future__ import annotations

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
    from ..engines.analysis_context import context_for

    asset = _parse_asset(symbol)
    snapshot = context_for(asset)
    return {**snapshot.edge.model_dump(), **snapshot.identity()}


@router.get("/edge")
async def edge_all() -> dict[str, Any]:
    from ..engines.edge import EdgeEngine

    engine = EdgeEngine()
    results = {a.value: engine.assess(a).model_dump() for a in Asset.tradables()}
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
    from ..engines.analysis_context import context_for
    from ..engines.leverage import LeverageCrowdingEngine

    asset = _parse_asset(symbol)
    snapshot = context_for(asset)
    payload = LeverageCrowdingEngine().assess(asset)
    # The percentile-heavy report is rebuilt here, but the three readings the
    # decision actually used are served from the analysis so the two agree.
    payload.update({
        **snapshot.identity(),
        "funding": snapshot.funding.model_dump(),
        "crowding": snapshot.crowding.model_dump(),
        "leverage_state": snapshot.leverage_state.model_dump(),
    })
    return payload


@router.get("/volatility/{symbol}")
async def volatility(symbol: str) -> dict[str, Any]:
    from ..engines.analysis_context import context_for

    asset = _parse_asset(symbol)
    snapshot = context_for(asset)
    return {**snapshot.volatility.model_dump(), **snapshot.identity()}


@router.get("/derivatives/aggregate/{symbol}")
async def derivatives_aggregate(symbol: str) -> dict[str, Any]:
    """Funding and OI across Binance, Bybit and OKX."""
    from ..providers.derivatives.multi_exchange import aggregate

    asset = _parse_asset(symbol)
    return (await aggregate(asset)).to_dict()


@router.get("/market/price/{symbol}")
async def market_price(symbol: str) -> dict[str, Any]:
    """Fast spot price consensus, separate from slower analytical data."""
    from ..engines.market_price import market_price_snapshot

    asset = _parse_asset(symbol)
    return (await market_price_snapshot(asset)).model_dump(mode="json")


@router.get("/today/{symbol}")
async def today(symbol: str) -> dict[str, Any]:
    """The decision summary: direction, timing, edge, crowding, uncertainty.

    Everything analytical comes from one `AnalysisContextSnapshot`, so the
    regime, the funding and the structure on this page describe the same
    moment and say so with the same `analysis_id`. Only the price is live, and
    it is joined on explicitly rather than merged in.
    """
    from ..engines.analysis_context import context_for, live_layer
    from ..engines.market_price import market_price_snapshot
    from ..engines.today_view import render

    asset = _parse_asset(symbol)
    market = (await market_price_snapshot(asset)).model_dump(mode="json")
    snapshot = context_for(asset)
    live = live_layer(snapshot, market)
    opportunity = snapshot.opportunity

    payload: dict[str, Any] = {
        "asset": asset.value,
        "analysis_id": snapshot.analysis_id,
        "analysis": live["analysis"],
        # The compact page: every block derived from the snapshot above and
        # carrying its id, so no two blocks can describe different moments.
        "page": render(snapshot, market.get("price_usd")),
        "buy_opportunity": opportunity.state.value,
        "buy_opportunity_explanation": opportunity.to_dict(),
        "entry_opportunity": snapshot.entry.to_dict(),
        "entry_timing": snapshot.timing.model_dump(mode="json"),
        "upcoming_macro": snapshot.macro_events,
        "market_pressure": snapshot.pressure.to_dict(),
        "overall_status": live["overall_status"].value,
        "overall_status_reason": live["overall_status_reason"],
        "allows_action": live["overall_status"].allows_action,
        "families": {name: state.to_dict() for name, state in live["families"].items()},
        "engines": {name: state.to_dict() for name, state in live["engines"].items()},
        "data_coverage": snapshot.coverage.to_dict() if snapshot.coverage else None,
        "decision_summary": snapshot.decision_summary.model_dump(mode="json"),
        "direction_source": (
            "reconstructed from price structure (trend, EMA position, momentum, ADX); "
            "not the full multi-domain regime engine, which needs a pipeline run"
        ),
        "direction_mode": "PRICE_ONLY_FALLBACK",
        "edge": snapshot.edge.model_dump(),
        "uncertainty": snapshot.uncertainty.model_dump(),
        "crowding": snapshot.crowding.model_dump(),
        "leverage_state": snapshot.leverage_state.model_dump(),
        "funding": snapshot.funding.model_dump(),
        "volatility": snapshot.volatility.model_dump(),
        "structural_location": snapshot.location.to_dict(),
        "multi_timeframe_structure": snapshot.structure,
        "breakout": snapshot.breakout,
        "patterns": snapshot.patterns,
        "implied_volatility": snapshot.implied_volatility.model_dump(mode="json"),
        "historical_analogs": snapshot.analogs,
        "live_track_record": snapshot.live_track_record,
        "onchain": snapshot.onchain,
        "liquidity": snapshot.liquidity,
        "macro_context": snapshot.macro_context,
        "cross_asset": snapshot.cross_asset,
        "provenance": snapshot.provenance,
        "market_data": market,
    }
    log.info(
        "today_assembled",
        asset=asset.value,
        analysis_id=snapshot.analysis_id,
        overall_status=payload["overall_status"],
        unusable=[n for n, e in payload["engines"].items() if not e["usable"]],
        stale_families=[n for n, f in payload["families"].items() if not f["usable"]],
    )
    return payload


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
    return run_all(assets)


@router.get("/cross-asset/{symbol}")
async def cross_asset(symbol: str, window: int = Query(90, ge=30, le=365)) -> dict[str, Any]:
    """Rolling correlation and beta against macro series."""
    from ..engines.cross_asset import CrossAssetAnalyzer

    asset = _parse_asset(symbol)
    return CrossAssetAnalyzer(window=window).assess(asset).model_dump()


@router.get("/market/ratios")
async def market_ratios() -> dict[str, Any]:
    """ETH/BTC, SOL/BTC, SOL/ETH and BTC dominance."""
    from ..engines.cross_asset import MarketRatiosEngine

    return MarketRatiosEngine().assess()


@router.get("/market/breadth")
async def market_breadth() -> dict[str, Any]:
    from ..engines.cross_asset import CryptoBreadthEngine

    return CryptoBreadthEngine().assess().model_dump()


@router.get("/market/liquidity")
async def market_liquidity() -> dict[str, Any]:
    from ..engines.cross_asset import LiquidityRegimeEngine

    return LiquidityRegimeEngine().assess().model_dump()


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
    return BreakoutQualityEngine().assess(asset, tf).model_dump()


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
    return run_all(assets)


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
    return run_all(assets)


@router.get("/research/drift")
async def research_drift(asset: str | None = None) -> dict[str, Any]:
    """Shadow-model live performance against backtest expectation."""
    from ..research.drift import run_all

    assets = [_parse_asset(asset)] if asset else None
    return run_all(assets)


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

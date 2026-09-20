"""Market participation, institutional demand and per-asset catalysts.

Three readings the decision already uses internally, exposed so the app can
show *why* the market is moving before showing what to do about it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException

from ..core.enums import Asset
from ..engines.asset_catalysts import catalysts_for
from ..engines.decision_families import build_families
from ..engines.institutional_demand import read_demand
from ..engines.market_breadth import read_breadth
from ..engines.market_explanation import explain_market
from ..engines.pit_view import DataCache, PointInTimeView
from ..engines.protocol_economics import read_economics
from ..future_events.models import DecisionHorizon

router = APIRouter(tags=["market intelligence"])


def _asset(symbol: str) -> Asset:
    try:
        asset = Asset(symbol.upper())
    except ValueError:
        raise HTTPException(404, f"Unknown asset '{symbol}'. Supported: BTC, ETH, SOL.") from None
    if asset not in Asset.tradables():
        raise HTTPException(404, f"Unknown asset '{symbol}'. Supported: BTC, ETH, SOL.")
    return asset


def _view() -> PointInTimeView:
    return PointInTimeView(DataCache(), datetime.now(UTC))


def market_state(symbol: str = "BTC") -> dict[str, Any]:
    """Participation of the market, and the reading that follows from it."""

    asset = _asset(symbol)
    view = _view()
    breadth = read_breadth(view)
    demand = read_demand(view, asset)
    catalysts = catalysts_for(asset, view=view)
    families = build_families(view, asset, DecisionHorizon.D7)
    explanation = explain_market(
        view, asset, demand=demand, breadth=breadth, catalysts=catalysts, families=families,
    )
    return {
        "asset": asset.value,
        "as_of": view.as_of.isoformat(),
        "breadth": breadth.to_dict(),
        "explanation": explanation.to_dict(),
        "dominance": breadth.measures.get("btc_dominance"),
    }


def institutions(symbol: str) -> dict[str, Any]:
    """The two independent measures of institutional demand, side by side."""

    asset = _asset(symbol)
    view = _view()
    demand = read_demand(view, asset)
    others = {
        other.value: read_demand(view, other).to_dict()
        for other in Asset.tradables() if other is not asset
    }
    return {
        "asset": asset.value,
        "as_of": view.as_of.isoformat(),
        "demand": demand.to_dict(),
        "others": others,
    }


def catalysts(symbol: str) -> dict[str, Any]:
    """Asset-specific catalysts, their stage, and what the market did with them."""

    asset = _asset(symbol)
    view = _view()
    reading = catalysts_for(asset, view=view)
    demand = read_demand(view, asset)
    economics = read_economics(view, asset, catalysts=reading, demand=demand)
    return {
        "asset": asset.value,
        "as_of": view.as_of.isoformat(),
        "catalysts": reading.to_dict(),
        "economics": economics.to_dict(),
    }


@router.get("/market/state")
def get_market_state(asset: str = "BTC") -> dict[str, Any]:
    return market_state(asset)


@router.get("/institutions/{symbol}")
def get_institutions(symbol: str) -> dict[str, Any]:
    return institutions(symbol)


@router.get("/catalysts/{symbol}")
def get_catalysts(symbol: str) -> dict[str, Any]:
    return catalysts(symbol)

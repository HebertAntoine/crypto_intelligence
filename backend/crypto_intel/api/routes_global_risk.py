"""Global risk API using three exact, non-overlapping future windows."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from fastapi import APIRouter, HTTPException

from ..core.enums import Asset
from ..db import repo
from ..engines.analysis_context import context_for
from ..engines.future_context import build_five_family_snapshot
from ..engines.global_risk import (
    GlobalRiskEngine,
    GlobalRiskHorizon,
    authorized_events_for_window,
)
from ..future_events.models import DecisionHorizon, FutureEvent

router = APIRouter(tags=["future intelligence"])


def _asset(symbol: str) -> Asset:
    try:
        asset = Asset(symbol.upper())
    except ValueError:
        raise HTTPException(
            404, f"Unknown asset '{symbol}'. Supported: BTC, ETH, SOL."
        ) from None
    if asset not in Asset.tradables():
        raise HTTPException(404, f"Unknown asset '{symbol}'. Supported: BTC, ETH, SOL.")
    return asset


def _events(snapshot: Any, asset: Asset) -> list[FutureEvent]:
    as_of = snapshot.analysis_time
    stored = repo.list_future_events(
        asset=asset,
        start=as_of - timedelta(days=7),
        end=as_of + timedelta(days=90),
        include_expired=True,
        limit=500,
    )
    by_id = {
        event.id: event
        for event in [*list(getattr(snapshot, "future_events", []) or []), *stored]
    }
    return list(by_id.values())


def _family_snapshot(
    snapshot: Any,
    events: list[FutureEvent],
    horizon: DecisionHorizon,
) -> Any:
    """Rebuild event-backed families from this window's events only."""

    return build_five_family_snapshot(
        analysis_id=snapshot.analysis_id,
        as_of=snapshot.analysis_time,
        states=snapshot.families,
        events=events,
        macro_context=snapshot.macro_context,
        liquidity=snapshot.liquidity,
        pressure=snapshot.pressure,
        institutional_flow=snapshot.institutional_flow,
        structure=snapshot.structure,
        regime=snapshot.regime,
        volatility=snapshot.volatility,
        implied_volatility=snapshot.implied_volatility,
        leverage_state=str(getattr(snapshot.leverage_state, "state", "") or ""),
        funding_state=str(getattr(snapshot.funding, "state", "") or ""),
        horizon=horizon,
        whales=snapshot.whales,
    )


@router.get("/future/{symbol}/global-risk")
def global_risk(symbol: str) -> dict[str, Any]:
    """Risk amplitude for 1-7d, 8-30d and 31-90d, never return odds."""

    asset = _asset(symbol)
    snapshot = context_for(asset)
    events = _events(snapshot, asset)
    short_events = authorized_events_for_window(
        events,
        GlobalRiskHorizon.SHORT,
        as_of=snapshot.analysis_time,
    )
    medium_events = authorized_events_for_window(
        events,
        GlobalRiskHorizon.MEDIUM,
        as_of=snapshot.analysis_time,
    )
    # There is no validated five-family projection beyond 30 days.  Passing
    # None is intentional: the engine exposes actual 31-90d events but refuses
    # to relabel the 30d family snapshot as a long-horizon diagnosis.
    families = {
        GlobalRiskHorizon.SHORT: _family_snapshot(
            snapshot, short_events, DecisionHorizon.D7
        ),
        GlobalRiskHorizon.MEDIUM: _family_snapshot(
            snapshot, medium_events, DecisionHorizon.D30
        ),
        GlobalRiskHorizon.LONG: None,
    }
    diagnoses = GlobalRiskEngine().assess(
        events,
        families,
        as_of=snapshot.analysis_time,
    )
    return {
        "asset": asset.value,
        "analysis_id": snapshot.analysis_id,
        "assessment_time": snapshot.analysis_time.isoformat(),
        "risk_horizons": [item.to_dict() for item in diagnoses],
        "methodology": (
            "Amplitude de risque issue des cinq familles Future et du moteur "
            "événementiel existants; fenêtres disjointes; aucune probabilité "
            "de rendement ni score directionnel."
        ),
    }


"""Future-first decision, explanation and timeline API."""

from __future__ import annotations

import asyncio
from datetime import UTC, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from ..core.enums import Asset
from ..engines.analysis_context import context_for
from ..engines.future_decision import FutureDecisionEngine
from ..future_events.models import DecisionHorizon

router = APIRouter(tags=["future intelligence"])

_HORIZON_DURATION = {
    DecisionHorizon.H24: timedelta(hours=24),
    DecisionHorizon.D7: timedelta(days=7),
    DecisionHorizon.D30: timedelta(days=30),
}


def _asset(symbol: str) -> Asset:
    try:
        asset = Asset(symbol.upper())
    except ValueError:
        raise HTTPException(404, f"Unknown asset '{symbol}'. Supported: BTC, ETH, SOL.") from None
    if asset not in Asset.tradables():
        raise HTTPException(404, f"Unknown asset '{symbol}'. Supported: BTC, ETH, SOL.")
    return asset


def _horizon(value: str) -> DecisionHorizon:
    try:
        return DecisionHorizon(value.lower())
    except ValueError:
        raise HTTPException(400, "Unknown horizon. Supported: 24h, 7d, 30d.") from None


def _uncertainty(snapshot: Any) -> float | None:
    raw = getattr(getattr(snapshot, "uncertainty", None), "score", None)
    return min(1.0, max(0.0, float(raw) / 100.0)) if raw is not None else None


def _decision(snapshot: Any, horizon: DecisionHorizon) -> Any:
    cutoff = snapshot.analysis_time + _HORIZON_DURATION[horizon]
    events = [
        event
        for event in snapshot.future_events
        if event.scheduled_at is None or event.scheduled_at <= cutoff
    ]
    return FutureDecisionEngine().decide(
        Asset(snapshot.asset),
        events,
        snapshot.future_families,
        horizon=horizon,
        as_of=snapshot.analysis_time,
        analysis_uncertainty=_uncertainty(snapshot),
    )


@router.get("/future/{symbol}")
async def future_decision(
    symbol: str,
    horizon: str = Query("7d", description="24h, 7d or 30d"),
) -> dict[str, Any]:
    """The complete source-backed decision contract for one asset."""
    asset = _asset(symbol)
    selected_horizon = _horizon(horizon)
    snapshot = await asyncio.to_thread(context_for, asset)
    result = _decision(snapshot, selected_horizon).to_dict()
    result["horizons"] = snapshot.future_horizons
    result["analysis_id"] = snapshot.analysis_id
    result["price_at_analysis"] = snapshot.price_at_analysis
    return result


@router.get("/future/{symbol}/why")
async def future_why(
    symbol: str,
    horizon: str = Query("7d", description="24h, 7d or 30d"),
) -> dict[str, Any]:
    """Compact click-through for 'why buy/wait/sell'."""
    asset = _asset(symbol)
    selected_horizon = _horizon(horizon)
    snapshot = await asyncio.to_thread(context_for, asset)
    result = _decision(snapshot, selected_horizon)
    payload = result.to_dict()
    return {
        "asset": asset.value,
        "analysis_id": snapshot.analysis_id,
        "as_of": result.as_of.isoformat(),
        "horizon": selected_horizon.value,
        "decision": result.decision.value,
        "title": f"Pourquoi {result.decision.value.lower()} ?",
        "reasons": payload["reasons"],
        "counter_signals": payload["counter_signals"],
        "what_could_change_decision": payload["what_could_change_decision"],
        "provenance": payload["provenance"],
    }


@router.get("/future/{symbol}/timeline")
async def future_timeline(
    symbol: str,
    days: int = Query(30, ge=1, le=30),
) -> dict[str, Any]:
    """Short upcoming-event timeline, with no generated announcements."""
    asset = _asset(symbol)
    snapshot = await asyncio.to_thread(context_for, asset)
    now = snapshot.analysis_time.astimezone(UTC)
    cutoff = now + timedelta(days=days)
    events = sorted(
        (
            event
            for event in snapshot.future_events
            if event.scheduled_at is None or now <= event.scheduled_at <= cutoff
        ),
        key=lambda event: (event.scheduled_at or event.detected_at, -event.importance.rank),
    )
    timeline = []
    for event in events:
        moment = event.scheduled_at or event.detected_at
        timeline.append(
            {
                "id": event.id,
                "title": event.title,
                "event_type": event.event_type,
                "scheduled_at": event.scheduled_at.isoformat() if event.scheduled_at else None,
                "detected_at": event.detected_at.isoformat(),
                "countdown_seconds": (
                    max(0, int((event.scheduled_at - now).total_seconds()))
                    if event.scheduled_at
                    else None
                ),
                "importance": event.importance.value,
                "directional_bias": event.directional_effect.value,
                "expected_movement": event.magnitude_effect.value,
                "uncertainty": (
                    "UNKNOWN"
                    if not event.market_probabilities
                    else "MARKET_DISTRIBUTION_AVAILABLE"
                ),
                "assets": [item.value for item in event.affected_assets],
                "source": event.source,
                "source_tier": event.source_tier.value,
                "source_url": event.source_url,
                "freshness": event.to_public_dict(now)["freshness_status"],
                "sort_time": moment.isoformat(),
            }
        )
    return {
        "asset": asset.value,
        "analysis_id": snapshot.analysis_id,
        "as_of": now.isoformat(),
        "days": days,
        "events": timeline,
    }

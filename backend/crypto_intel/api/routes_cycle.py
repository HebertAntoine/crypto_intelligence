"""The market cycle page: one phase, one chart, and the history behind it.

Everything served here is measured: the phases are computed from the daily
bars, the halvings come from the chain, the previous cycles are counted on the
same bars. The page shows history and the present. It carries no schedule for
the next top or bottom, because no such model has been validated here.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException

from ..core.enums import Asset, Timeframe
from ..engines.cycle_history import (
    annotations,
    current_low,
    cycle_stats,
    normalised_cycles,
    price_series,
)
from ..engines.cycle_regime import BitcoinCycleRegimeEngine, next_step
from ..engines.cycle_snapshots import list_snapshots
from ..engines.pit_view import DataCache, PointInTimeView

router = APIRouter(tags=["cycle"])

DISCLAIMER = (
    "Comparaison historique, non prédictive : les cycles passés ne fixent ni la date "
    "d'un sommet ni celle d'un creux."
)


def _asset(symbol: str) -> Asset:
    try:
        asset = Asset(symbol.upper())
    except ValueError:
        raise HTTPException(404, f"Unknown asset '{symbol}'. Supported: BTC, ETH, SOL.") from None
    if asset not in Asset.tradables():
        raise HTTPException(404, f"Unknown asset '{symbol}'. Supported: BTC, ETH, SOL.")
    return asset


def _relative_strength(view: PointInTimeView, asset: Asset, days: int = 30) -> dict[str, Any] | None:
    """How the asset fares against BTC - context for ETH and SOL, no cycle."""

    if asset is Asset.BTC:
        return None
    own = view.candles(asset.value, Timeframe.D1)
    btc = view.candles("BTC", Timeframe.D1)
    if len(own) <= days or len(btc) <= days:
        return None
    ratio_now = float(own["close"].iloc[-1]) / float(btc["close"].iloc[-1])
    ratio_then = float(own["close"].iloc[-days - 1]) / float(btc["close"].iloc[-days - 1])
    change = (ratio_now / ratio_then - 1) * 100
    state = "OUTPERFORM" if change >= 2 else "UNDERPERFORM" if change <= -2 else "NEUTRAL"
    return {
        "asset": asset.value,
        "window_days": days,
        "change_pct": round(change, 1),
        "state": state,
        "emoji": {"OUTPERFORM": "↗️", "UNDERPERFORM": "↘️", "NEUTRAL": "➡️"}[state],
        "label": {
            "OUTPERFORM": f"{asset.value} surperforme BTC",
            "UNDERPERFORM": f"{asset.value} sous-performe BTC",
            "NEUTRAL": f"{asset.value} suit BTC",
        }[state],
        "note": f"{asset.value} n'a pas de halving : son cycle propre n'est pas inventé.",
    }


def cycle_page(symbol: str) -> dict[str, Any]:
    asset = _asset(symbol)
    now = datetime.now(UTC)
    view = PointInTimeView(DataCache(), now)
    halvings = [
        datetime.fromtimestamp(point.value, UTC)
        for point in view.points("btc.halving.block_epoch")
    ]
    estimate = view.latest("btc.halving.next_epoch_estimate")
    daily = view.candles("BTC", Timeframe.D1)
    regime = BitcoinCycleRegimeEngine().read(daily, halvings, as_of=now)
    if regime is None or daily.empty:
        raise HTTPException(503, "Historique BTC insuffisant pour lire le cycle.")

    payload = regime.to_dict()
    stats = cycle_stats(daily, halvings, as_of=now)
    last_high = regime.dimensions.ath_date
    chart_halvings = [
        {"date": h.date().isoformat(), "label": f"Halving {h.year}", "emoji": "⚡", "estimated": False}
        for h in sorted(halvings)
    ]
    if estimate is not None:
        eta = datetime.fromtimestamp(estimate.value, UTC)
        chart_halvings.append({
            "date": eta.date().isoformat(),
            "label": f"Halving suivant estimé ({eta:%m/%Y})",
            "emoji": "📅",
            "estimated": True,
        })
    price = float(daily["close"].iloc[-1])
    return {
        "asset": asset.value,
        "as_of": now.isoformat(),
        "title": "🔄 Cycle Bitcoin" if asset is Asset.BTC else "🔄 Régime crypto",
        "is_btc": asset is Asset.BTC,
        "phase": {
            **payload,
            "summary": regime.evidence[0] if regime.evidence else regime.label,
            "reasons": regime.evidence[:3],
        },
        "figures": {
            "days_since_halving": regime.dimensions.days_since_halving,
            "drawdown_pct": round(regime.dimensions.drawdown_pct, 1),
            "days_in_phase": regime.days_in_phase,
            "price": round(price, 2),
            "ath": round(regime.dimensions.ath, 2),
            "ath_date": regime.dimensions.ath_date.date().isoformat(),
        },
        "next_step": next_step(regime),
        "chart": {
            "log_scale": True,
            "currency": "USD",
            "points": price_series(daily),
            "phases": [run.to_dict() for run in regime.runs],
            "halvings": chart_halvings,
            "annotations": annotations(daily, halvings, stats, as_of=now),
            "today": {"date": now.date().isoformat(), "price": round(price, 2),
                      "label": "📍 Aujourd'hui"},
            "local_low": current_low(daily, last_high),
        },
        "cycles": [c.to_dict() for c in stats],
        "normalised": normalised_cycles(daily, halvings, as_of=now),
        "snapshots": list_snapshots("BTC", limit=18),
        "relative_strength": _relative_strength(view, asset),
        "disclaimer": DISCLAIMER,
        "engine_version": BitcoinCycleRegimeEngine.version,
    }


@router.get("/cycle/{symbol}")
def get_cycle(symbol: str) -> dict[str, Any]:
    return cycle_page(symbol)

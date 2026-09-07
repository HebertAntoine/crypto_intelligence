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
    from ..engines.edge import EdgeEngine

    asset = _parse_asset(symbol)
    return EdgeEngine().assess(asset).model_dump()


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
    from ..engines.leverage import LeverageCrowdingEngine

    asset = _parse_asset(symbol)
    return LeverageCrowdingEngine().assess(asset)


@router.get("/volatility/{symbol}")
async def volatility(symbol: str) -> dict[str, Any]:
    from ..engines.volatility import VolatilityRegimeEngine

    asset = _parse_asset(symbol)
    return VolatilityRegimeEngine().assess(asset).model_dump()


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


def _family_states(asset: Asset, market: dict[str, Any] | None) -> dict[str, Any]:
    """Every input family, answered four ways from its real last observation.

    The timestamps come from the store rather than from the engines, because an
    engine will happily compute on whatever it was given: the question here is
    not what came out but how old what went in actually is.
    """
    from datetime import datetime

    from ..core.enums import Timeframe
    from ..core.usability import FamilyState, Freshness, freshness_for
    from ..history import store

    states: dict[str, FamilyState] = {}

    # Price: the only family whose timestamp arrives with the payload.
    observed = None
    if market:
        raw = market.get("as_of") or market.get("timestamp")
        if isinstance(raw, str):
            try:
                observed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                observed = None
    price_value = (market or {}).get("price_usd")
    states["price"] = FamilyState(
        family="price",
        available=price_value is not None,
        valid=isinstance(price_value, int | float) and price_value > 0,
        freshness=freshness_for("price", observed),
        observed_at=observed,
        source=(market or {}).get("method", "") or "market price engine",
        points=(market or {}).get("provider_count"),
    )

    coverage = store.candle_coverage(asset, Timeframe.D1)
    end = coverage.get("end")
    states["ohlcv_daily"] = FamilyState(
        family="ohlcv_daily",
        available=coverage.get("rows", 0) > 0,
        valid=coverage.get("rows", 0) >= 200,
        freshness=freshness_for("ohlcv_daily", end),
        observed_at=end,
        source="candle store",
        points=coverage.get("rows"),
        reason=(
            "" if coverage.get("rows", 0) >= 200
            else f"{coverage.get('rows', 0)} bougies, moins que les 200 "
                 "nécessaires à une reconstruction de régime"
        ),
    )

    derivatives = store.derivatives_coverage(asset)
    for metric, family in (
        ("funding.rate", "funding"),
        ("oi.contracts_bybit", "open_interest"),
        ("dvol.index", "dvol"),
    ):
        entry = derivatives.get(metric)
        if entry is None and family == "open_interest":
            entry = derivatives.get("oi.value")
        if entry is None:
            states[family] = FamilyState(
                family=family, available=False, valid=False,
                freshness=Freshness.UNAVAILABLE, source=metric,
                reason=(
                    "aucune série DVOL n'existe pour cet actif; la volatilité "
                    "repose sur l'ATR réalisé"
                    if family == "dvol" else "aucune observation stockée"
                ),
            )
            continue
        states[family] = FamilyState(
            family=family,
            available=entry["rows"] > 0,
            valid=entry["rows"] >= 30,
            freshness=freshness_for(family, entry["end"]),
            observed_at=entry["end"],
            source=metric,
            points=entry["rows"],
        )

    return states


def _timing_context(asset: Asset) -> dict[str, Any]:
    """Snapshots techniques nécessaires au moteur de timing d'entrée.

    Le moteur existe et calcule un score de -100 à +100 avec ses facteurs
    nommés. `/today` ne le lui demandait simplement jamais: il appelait
    `build_decision_summary` sans `timing=`, donc l'entrée restait
    UNDETERMINED alors que le calcul était disponible. Même famille d'oubli que
    le régime, corrigée plus tôt.
    """
    from ..core.enums import Timeframe
    from ..core.models import Candle, OHLCVSeries, Provenance
    from ..engines.technical.engine import TechnicalAnalysisEngine
    from ..history import store

    engine = TechnicalAnalysisEngine()
    snapshots: dict[Timeframe, Any] = {}
    for timeframe in (Timeframe.D1, Timeframe.H4, Timeframe.H1):
        df = store.load_candles(asset, timeframe)
        if df.empty or len(df) < 60:
            continue
        candles = [
            Candle(
                timestamp=ts, open=row.open, high=row.high, low=row.low,
                close=row.close, volume=row.volume,
            )
            for ts, row in df.tail(400).iterrows()
        ]
        try:
            snapshots[timeframe] = engine.analyze(
                OHLCVSeries(
                    asset=asset, timeframe=timeframe, candles=candles,
                    provenance=Provenance(
                        source="local history", provider="ohlcv_store"
                    ),
                )
            )
        except (ValueError, KeyError) as exc:
            log.warning("timing_snapshot_failed", timeframe=timeframe.value, error=str(exc))
    return {"snapshots": snapshots}


def _upcoming_macro(asset: Asset, days: int = 14) -> list[dict[str, Any]]:
    """Événements macro programmés qui touchent cet actif.

    Le calendrier est maintenu dans `config/macro_calendar.yaml`: des dates
    publiées à l'avance, pas une estimation. Une échéance proche ne prédit
    rien, mais elle explique pourquoi attendre peut être raisonnable.
    """
    from ..db import repo

    out: list[dict[str, Any]] = []
    for event in repo.upcoming_events(days=days):
        assets = event.get("assets") or []
        if isinstance(assets, str):
            assets = [a.strip(" '\"[]") for a in assets.split(",")]
        if assets and asset.value not in assets:
            continue
        hours = float(event.get("hours_until") or 0.0)
        out.append({
            "kind": event.get("kind"),
            "name": event.get("name"),
            "scheduled_at": str(event.get("scheduled_at")),
            "importance": event.get("importance"),
            "hours_until": round(hours, 1),
            "days_until": round(hours / 24.0, 1),
        })
    return out[:5]


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

    from ..core.usability import assess_engine, page_status
    from ..engines.market_price import market_price_snapshot

    market = (await market_price_snapshot(asset)).model_dump(mode="json")
    families = _family_states(asset, market)

    def build() -> dict[str, Any]:
        leverage_engine = LeverageCrowdingEngine()
        crowding = leverage_engine.crowding(asset)
        edge = EdgeEngine().assess(asset)
        vol = VolatilityRegimeEngine().assess(asset)
        funding = leverage_engine.funding_context(asset)
        leverage_state = leverage_engine.leverage_state(asset)

        # Direction from the causal reconstruction used in research, so this
        # endpoint stays independent of an LLM run. It uses trend, structure
        # and momentum only - the domains present over the whole history.
        regime = _reconstructed_regime(asset)

        # Every engine is judged against the freshness of the inputs it
        # actually requires. A result can be computed and still not describe
        # the present: that is the distinction the page kept losing when it
        # reported one word, "OK", for four different questions.
        engines = {
            name: assess_engine(
                name, families,
                mode="price_only_fallback" if name == "direction" else "full",
            )
            for name in (
                "price", "direction", "persistence", "volatility", "funding",
                "positioning", "crowding", "edge", "action",
            )
        }
        status, status_reason = page_status(families, engines)

        # The uncertainty engine reads the same family states, so a stale input
        # widens uncertainty instead of passing unnoticed.
        freshness_map = {
            name: ("OK" if state.usable else state.freshness.value)
            for name, state in families.items()
        }
        uncertainty = UncertaintyEngine().assess(
            asset, edge, regime=regime, crowding=crowding, freshness=freshness_map,
        )
        # Le moteur de timing reçoit enfin ses entrées: sans elles il
        # renvoyait UNDETERMINED, ce que l'écran affichait comme si la question
        # n'avait pas de réponse alors qu'elle n'avait pas été posée.
        from ..engines.entry_timing import EntryTimingEngine

        timing = EntryTimingEngine().assess(asset, _timing_context(asset))
        summary = build_decision_summary(
            asset, edge, uncertainty, regime=regime, timing=timing,
            crowding=crowding, volatility=vol,
        )

        from ..engines.market_pressure import assess_pressure

        pressure = assess_pressure(
            asset,
            funding_percentile=funding.percentile,
            funding_usable=families["funding"].usable if "funding" in families else False,
            leverage_state=str(getattr(leverage_state, "state", "")),
            positioning_usable=(
                families["open_interest"].usable
                if "open_interest" in families else False
            ),
        )

        return {
            "asset": asset.value,
            "entry_timing": timing.model_dump(mode="json"),
            "upcoming_macro": _upcoming_macro(asset),
            "market_pressure": pressure.to_dict(),
            "overall_status": status.value,
            "overall_status_reason": status_reason,
            "allows_action": status.allows_action,
            "families": {name: state.to_dict() for name, state in families.items()},
            "engines": {name: state.to_dict() for name, state in engines.items()},
            "decision_summary": summary.model_dump(mode="json"),
            "direction_source": (
                "reconstructed from price structure (trend, EMA position, momentum, ADX); "
                "not the full multi-domain regime engine, which needs a pipeline run"
            ),
            "direction_mode": "PRICE_ONLY_FALLBACK",
            "edge": edge.model_dump(),
            "uncertainty": uncertainty.model_dump(),
            "crowding": crowding.model_dump(),
            "leverage_state": leverage_state.model_dump(),
            "funding": funding.model_dump(),
            "volatility": vol.model_dump(),
        }

    payload = build()
    payload["market_data"] = market
    log.info(
        "today_assembled",
        asset=asset.value,
        overall_status=payload["overall_status"],
        unusable=[n for n, e in payload["engines"].items() if not e["usable"]],
        stale_families=[
            n for n, f in payload["families"].items() if not f["usable"]
        ],
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

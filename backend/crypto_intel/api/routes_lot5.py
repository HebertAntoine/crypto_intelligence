"""LOT 5 endpoints: structure, patterns, trader knowledge and their research.

Every endpoint that returns a pattern or a structure also returns its edge
state, so no consumer can render a recognition confidence without the verdict
that says whether it predicts anything.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from ..core.enums import Asset, Timeframe
from ..logging_setup import get_logger

log = get_logger("api.lot5")
router = APIRouter()


def _parse_asset(symbol: str) -> Asset:
    try:
        return Asset(symbol.upper())
    except ValueError:
        raise HTTPException(404, f"Unknown asset '{symbol}'. Supported: BTC, ETH, SOL.") from None


def _parse_timeframe(value: str) -> Timeframe:
    try:
        return Timeframe(value)
    except ValueError:
        raise HTTPException(400, f"Unknown timeframe '{value}'") from None


def _stored(name: str) -> dict[str, Any] | None:
    path = pathlib.Path("data/research") / name
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


@router.get("/structure/{symbol}")
async def structure(symbol: str, timeframe: str = "4h") -> dict[str, Any]:
    """Range, location, market structure and patterns for one timeframe.

    Serves the current analysis rather than a fresh computation whenever the
    requested timeframe is one the analysis already covers, so this endpoint
    and `/today` cannot disagree about where price sits. A timeframe outside
    the analysis is computed on demand and says so by returning no
    `analysis_id`: it belongs to no analysis, and pretending otherwise would
    let the screen combine it with blocks that do.
    """
    from ..engines.analysis_context import context_for
    from ..history import store
    from ..pattern_learning.quality_gate import apply_independent_live_gate
    from ..structure.location import StructuralLocationEngine
    from ..structure.market_structure import MarketStructureEngine
    from ..structure.patterns import build_context, detect_all

    asset = _parse_asset(symbol)
    tf = _parse_timeframe(timeframe)
    snapshot = context_for(asset)

    df = store.load_candles(asset, tf)
    ctx = build_context(df, tf)
    detected = detect_all(ctx) if ctx is not None else []
    gate = apply_independent_live_gate(detected, df["close"])
    patterns = [
        {**pattern.to_dict(), "independent_quality_gate": gate["decisions"][index]}
        for index, pattern in enumerate(detected)
    ]

    covered = (
        (snapshot.location_by_timeframe.get("timeframes") or {}).get(tf.value) is not None
        and (snapshot.structure.get("timeframes") or {}).get(tf.value) is not None
    )
    if covered:
        location = snapshot.location_by_timeframe["timeframes"][tf.value]
        structure_reading = snapshot.structure["timeframes"][tf.value]
    else:
        location = StructuralLocationEngine().assess(asset, tf).to_dict()
        structure_reading = MarketStructureEngine().assess(asset, tf).to_dict()

    return {
        "asset": asset.value, "timeframe": tf.value,
        "analysis_id": snapshot.analysis_id if covered else None,
        "analysis_time": snapshot.analysis_time.isoformat() if covered else None,
        "price_at_analysis": snapshot.price_at_analysis if covered else None,
        "from_analysis": covered,
        "location": location,
        "market_structure": structure_reading,
        "patterns": patterns,
        "pattern_quality_gate": {
            **gate["summary"],
            "edge_claim": gate["edge_claim"],
        },
        "separation_note": (
            "recognition_confidence measures shape match only. Read edge_state "
            "for whether the pattern predicts anything."
        ),
    }


@router.get("/structure/{symbol}/multi-timeframe")
async def multi_timeframe(symbol: str) -> dict[str, Any]:
    """Structure across timeframes, with conflicts stated explicitly."""

    asset = _parse_asset(symbol)

    from ..engines.analysis_context import context_for

    snapshot = context_for(asset)
    return {
        **snapshot.identity(),
        "location": snapshot.location_by_timeframe,
        "market_structure": snapshot.structure,
    }


@router.get("/entry-opportunity/{symbol}")
async def entry_opportunity(symbol: str, timeframe: str = "4h") -> dict[str, Any]:
    """How favourable the configuration looks, with the edge shown separately."""
    from ..engines.analysis_context import context_for
    from ..engines.entry_opportunity import EntryOpportunityEngine

    asset = _parse_asset(symbol)
    tf = _parse_timeframe(timeframe)
    snapshot = context_for(asset)
    if tf is Timeframe.H4:
        # The analysis is assessed on 4H; returning it verbatim keeps this
        # endpoint and the decision it feeds from drifting apart.
        return {**snapshot.entry.to_dict(), **snapshot.identity(), "from_analysis": True}
    return {
        **EntryOpportunityEngine().assess(asset, tf).to_dict(),
        "analysis_id": None, "from_analysis": False,
    }


@router.get("/knowledge/educational-claims")
async def educational_claims() -> dict[str, Any]:
    """Testable claims drawn from educational material."""
    from ..trader_knowledge.educational import GOODCRYPTO, load_claims

    claims = load_claims()
    return {
        "sources": [GOODCRYPTO],
        "claims": claims,
        "count": len(claims),
        "note": (
            "These are EDUCATIONAL CLAIMS - hypotheses about how to read charts. They "
            "sit at source tier 4 and cannot override any measured value."
        ),
    }


@router.get("/knowledge/dataset-quality")
async def dataset_quality() -> dict[str, Any]:
    from ..trader_knowledge.dataset import dataset_quality as quality

    return quality()


@router.get("/knowledge/annotation-queue")
async def annotation_queue(limit: int = Query(20, ge=1, le=100)) -> dict[str, Any]:
    """Cases where the detector is genuinely uncertain."""
    from ..trader_knowledge.dataset import active_learning_queue

    return active_learning_queue(limit)


@router.get("/knowledge/examples")
async def examples() -> dict[str, Any]:
    from ..trader_knowledge.dataset import load_examples

    stored = load_examples()
    return {
        "examples": [e.model_dump(mode="json") for e in stored],
        "count": len(stored),
    }


@router.get("/knowledge/human-vs-algorithm")
async def human_vs_algorithm() -> dict[str, Any]:
    from ..trader_knowledge.dataset import human_vs_algorithm as compare

    return compare()


@router.get("/research/structural")
async def research_structural(recompute: bool = False) -> dict[str, Any]:
    """Do structural readings carry forward information?"""
    if not recompute:
        stored = _stored("structural_research.json")
        if stored:
            return {**stored, "source": "stored"}
    from ..research.structural_research import run_all

    return run_all()


@router.get("/research/marginal-value")
async def research_marginal_value(recompute: bool = False) -> dict[str, Any]:
    """The two central questions: does chart reading add anything?"""
    if not recompute:
        stored = _stored("marginal_value.json")
        if stored:
            return {**stored, "source": "stored"}
    from ..research.marginal_value import run_all

    return run_all()


@router.get("/research/replication")
async def research_replication(recompute: bool = False) -> dict[str, Any]:
    """Do the LOT 4 findings survive the LOT 5 detectors?"""
    if not recompute:
        stored = _stored("replication.json")
        if stored:
            return {**stored, "source": "stored"}
    from ..research.replication import run_all

    return run_all()


@router.get("/research/claim-validation")
async def research_claim_validation(recompute: bool = False) -> dict[str, Any]:
    """Theory versus data, claim by claim."""
    if not recompute:
        stored = _stored("claim_validation.json")
        if stored:
            return {**stored, "source": "stored"}
    from ..research.claim_validation import run_all

    return run_all()


@router.get("/structure/cache/status")
async def cache_status() -> dict[str, Any]:
    from ..structure.cache import cache_status as status

    return status()


@router.get("/sources/hierarchy")
async def source_hierarchy() -> dict[str, Any]:
    """Which sources may override which."""
    from ..core.sources import PROVIDER_TIERS, SourceTier

    tiers: dict[str, Any] = {}
    for tier in SourceTier:
        tiers[str(int(tier))] = {
            "label": tier.label,
            "is_primary_data": tier.is_primary_data,
            "providers": sorted(p for p, t in PROVIDER_TIERS.items() if t == tier),
        }
    return {
        "tiers": tiers,
        "rule": (
            "A source may only override one of a strictly higher tier number. Equal "
            "tiers disagreeing is reported, never silently resolved. Educational and "
            "human sources (tiers 4-6) can never override measured data (tiers 1-3)."
        ),
    }


# --- LOT 6A ---------------------------------------------------------------


@router.get("/multi-timeframe/{symbol}")
async def multi_timeframe_reading(symbol: str) -> dict[str, Any]:
    """One reading per timeframe, plus what they say together."""
    from ..engines.multi_timeframe import MultiTimeframeEngine

    asset = _parse_asset(symbol)
    return MultiTimeframeEngine().assess(asset).to_dict()


@router.get("/daily-report-v2")
async def daily_report_v2(asset: str | None = None) -> dict[str, Any]:
    """The full daily read: sixteen sections in reading order, then a conclusion."""
    from ..engines.daily_report import build_all

    assets = [_parse_asset(asset)] if asset else None
    return build_all(assets)


@router.get("/research/revalidation")
async def research_revalidation(recompute: bool = False) -> dict[str, Any]:
    """The ten pre-registered candidates, re-tested under the LOT 6A framework."""
    if not recompute:
        stored = _stored("revalidation.json")
        if stored:
            return {**stored, "source": "stored"}
    from ..research.revalidation import run_all

    return run_all()


@router.get("/volatility/implied/{symbol}")
async def implied_volatility(symbol: str) -> dict[str, Any]:
    """DVOL and the variance risk premium.

    The only family in the project sourced from a market other than spot or
    perpetuals. Returns UNAVAILABLE for SOL rather than substituting a proxy.
    """
    from ..engines.implied_volatility import ImpliedVolatilityEngine

    asset = _parse_asset(symbol)
    return ImpliedVolatilityEngine().assess(asset).to_dict()


@router.get("/research/dvol")
async def research_dvol(recompute: bool = False) -> dict[str, Any]:
    """The 24 pre-registered implied-volatility hypotheses."""
    if not recompute:
        stored = _stored("dvol_study.json")
        if stored:
            return {**stored, "source": "stored"}
    from ..research.dvol_study import run_all

    return run_all()

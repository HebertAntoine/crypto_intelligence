"""LOT 5 endpoints: structure, patterns, trader knowledge and their research.

Every endpoint that returns a pattern or a structure also returns its edge
state, so no consumer can render a recognition confidence without the verdict
that says whether it predicts anything.
"""

from __future__ import annotations

import asyncio
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
    """Range, location, market structure and patterns for one timeframe."""
    from ..history import store
    from ..structure.location import StructuralLocationEngine
    from ..structure.market_structure import MarketStructureEngine
    from ..structure.patterns import build_context, detect_all

    asset = _parse_asset(symbol)
    tf = _parse_timeframe(timeframe)

    def build() -> dict[str, Any]:
        location = StructuralLocationEngine().assess(asset, tf)
        structure_reading = MarketStructureEngine().assess(asset, tf)
        df = store.load_candles(asset, tf)
        ctx = build_context(df, tf)
        patterns = [p.to_dict() for p in detect_all(ctx)] if ctx is not None else []
        return {
            "asset": asset.value, "timeframe": tf.value,
            "location": location.to_dict(),
            "market_structure": structure_reading.to_dict(),
            "patterns": patterns,
            "separation_note": (
                "recognition_confidence measures shape match only. Read edge_state "
                "for whether the pattern predicts anything."
            ),
        }

    return await asyncio.to_thread(build)


@router.get("/structure/{symbol}/multi-timeframe")
async def multi_timeframe(symbol: str) -> dict[str, Any]:
    """Structure across timeframes, with conflicts stated explicitly."""
    from ..structure.location import StructuralLocationEngine
    from ..structure.market_structure import MarketStructureEngine

    asset = _parse_asset(symbol)

    def build() -> dict[str, Any]:
        return {
            "location": StructuralLocationEngine().multi_timeframe(asset),
            "market_structure": MarketStructureEngine().multi_timeframe(asset),
        }

    return await asyncio.to_thread(build)


@router.get("/entry-opportunity/{symbol}")
async def entry_opportunity(symbol: str, timeframe: str = "4h") -> dict[str, Any]:
    """How favourable the configuration looks, with the edge shown separately."""
    from ..engines.entry_opportunity import EntryOpportunityEngine

    asset = _parse_asset(symbol)
    tf = _parse_timeframe(timeframe)
    return (
        await asyncio.to_thread(EntryOpportunityEngine().assess, asset, tf)
    ).to_dict()


@router.get("/knowledge/educational-claims")
async def educational_claims() -> dict[str, Any]:
    """Testable claims drawn from educational material."""
    from ..trader_knowledge.educational import GOODCRYPTO, load_claims

    claims = await asyncio.to_thread(load_claims)
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

    return await asyncio.to_thread(quality)


@router.get("/knowledge/annotation-queue")
async def annotation_queue(limit: int = Query(20, ge=1, le=100)) -> dict[str, Any]:
    """Cases where the detector is genuinely uncertain."""
    from ..trader_knowledge.dataset import active_learning_queue

    return await asyncio.to_thread(active_learning_queue, limit)


@router.get("/knowledge/examples")
async def examples() -> dict[str, Any]:
    from ..trader_knowledge.dataset import load_examples

    stored = await asyncio.to_thread(load_examples)
    return {
        "examples": [e.model_dump(mode="json") for e in stored],
        "count": len(stored),
    }


@router.get("/knowledge/human-vs-algorithm")
async def human_vs_algorithm() -> dict[str, Any]:
    from ..trader_knowledge.dataset import human_vs_algorithm as compare

    return await asyncio.to_thread(compare)


@router.get("/research/structural")
async def research_structural(recompute: bool = False) -> dict[str, Any]:
    """Do structural readings carry forward information?"""
    if not recompute:
        stored = _stored("structural_research.json")
        if stored:
            return {**stored, "source": "stored"}
    from ..research.structural_research import run_all

    return await asyncio.to_thread(run_all)


@router.get("/research/marginal-value")
async def research_marginal_value(recompute: bool = False) -> dict[str, Any]:
    """The two central questions: does chart reading add anything?"""
    if not recompute:
        stored = _stored("marginal_value.json")
        if stored:
            return {**stored, "source": "stored"}
    from ..research.marginal_value import run_all

    return await asyncio.to_thread(run_all)


@router.get("/research/replication")
async def research_replication(recompute: bool = False) -> dict[str, Any]:
    """Do the LOT 4 findings survive the LOT 5 detectors?"""
    if not recompute:
        stored = _stored("replication.json")
        if stored:
            return {**stored, "source": "stored"}
    from ..research.replication import run_all

    return await asyncio.to_thread(run_all)


@router.get("/research/claim-validation")
async def research_claim_validation(recompute: bool = False) -> dict[str, Any]:
    """Theory versus data, claim by claim."""
    if not recompute:
        stored = _stored("claim_validation.json")
        if stored:
            return {**stored, "source": "stored"}
    from ..research.claim_validation import run_all

    return await asyncio.to_thread(run_all)


@router.get("/structure/cache/status")
async def cache_status() -> dict[str, Any]:
    from ..structure.cache import cache_status as status

    return await asyncio.to_thread(status)


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
    return (await asyncio.to_thread(MultiTimeframeEngine().assess, asset)).to_dict()


@router.get("/daily-report-v2")
async def daily_report_v2(asset: str | None = None) -> dict[str, Any]:
    """The full daily read: sixteen sections in reading order, then a conclusion."""
    from ..engines.daily_report import build_all

    assets = [_parse_asset(asset)] if asset else None
    return await asyncio.to_thread(build_all, assets)


@router.get("/research/revalidation")
async def research_revalidation(recompute: bool = False) -> dict[str, Any]:
    """The ten pre-registered candidates, re-tested under the LOT 6A framework."""
    if not recompute:
        stored = _stored("revalidation.json")
        if stored:
            return {**stored, "source": "stored"}
    from ..research.revalidation import run_all

    return await asyncio.to_thread(run_all)

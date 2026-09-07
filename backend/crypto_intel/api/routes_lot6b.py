"""LOT 6B endpoints: evidence, power and what the pipeline can actually see.

These endpoints exist to make the negative results legible. Every payload
carries the funnel that produced it and the detection floor that bounds it, so
a client cannot render "no signal found" without also having the reason.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

from fastapi import APIRouter, HTTPException

from ..logging_setup import get_logger

log = get_logger("api.lot6b")
router = APIRouter()

RESEARCH_DIR = pathlib.Path("data/research")


def _stored(name: str) -> dict[str, Any] | None:
    path = RESEARCH_DIR / name
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("research_file_unreadable", name=name, error=str(exc))
        return None


def _require(name: str, hint: str) -> dict[str, Any]:
    payload = _stored(name)
    if payload is None:
        raise HTTPException(
            404,
            f"{name} has not been generated yet. Run `crypto-intel {hint}` first.",
        )
    return payload


@router.get("/evidence")
async def evidence() -> dict[str, Any]:
    """Every claim placed on the evidence ladder, with the funnel behind it."""
    payload = _require("lot6b.json", "lot6b")
    ladder = payload.get("evidence", {})
    return {
        "generated_at": payload.get("generated_at"),
        "verdict": payload.get("verdict"),
        "assessments": ladder.get("assessments", []),
        "by_level": ladder.get("by_level", {}),
        "highest_level_reached": ladder.get("highest_level_reached", 0),
        "n_actionable": ladder.get("n_actionable", 0),
        "funnel": ladder.get("funnel", {}),
        "shortlist": payload.get("shortlist", {}),
        "reproducibility": payload.get("reproducibility", {}),
    }


@router.get("/evidence/ladder")
async def ladder_definition() -> dict[str, Any]:
    """The ladder itself, so a client can render levels it has never seen."""
    from ..research.evidence import ACTIONABLE_LEVEL, LADDER

    return {
        "levels": LADDER,
        "actionable_from": ACTIONABLE_LEVEL,
        "note": (
            "Rungs are cumulative and strictly ordered. A claim that survives a "
            "harder test while failing an easier one stops at the easier one, "
            "because that pattern nearly always means the harder test was "
            "misapplied rather than that the claim is strong."
        ),
    }


@router.get("/power")
async def power() -> dict[str, Any]:
    """Detection floor, control results, and what more data would be needed."""
    payload = _require("lot6b.json", "lot6b")
    calibration = payload.get("calibration", {})
    floors = calibration.get("detection_floors", {})
    summary = [
        {
            "horizon_days": int(key.lstrip("h")),
            "empirical_floor_pct": value.get("empirical_floor_pct"),
            "analytic_mde_pct": value.get("analytic_mde_pct"),
            "meaningful_effect_pct": value.get("meaningful_effect_pct"),
            "floor_above_meaningful": value.get("floor_above_meaningful"),
            "note": value.get("note"),
        }
        for key, value in sorted(floors.items(), key=lambda kv: int(kv[0].lstrip("h")))
    ]
    return {
        "generated_at": payload.get("generated_at"),
        "verdict": calibration.get("verdict"),
        "detection_floors": summary,
        "control_suite": calibration.get("control_suite", {}),
        "note": calibration.get("note", ""),
    }


@router.get("/pooling")
async def pooling() -> dict[str, Any]:
    """BTC and ETH pooled four ways, with the cross-asset correlation."""
    payload = _require("dvol_pooled.json", "lot6b")
    return {
        "generated_at": payload.get("generated_at"),
        "assets_pooled": payload.get("assets_pooled", []),
        "assets_unavailable": payload.get("assets_unavailable", {}),
        "mean_cross_asset_correlation": payload.get("mean_cross_asset_correlation"),
        "verdict_counts": payload.get("verdict_counts", {}),
        "multiple_testing": payload.get("multiple_testing", {}),
        "results": payload.get("results", []),
    }


@router.get("/hypotheses")
async def hypotheses() -> dict[str, Any]:
    """The frozen hypothesis registry and its multiple-testing denominator."""
    from ..research.hypothesis_registry import get_registry

    registry = get_registry()
    return {
        "summary": registry.summary(),
        "hypotheses": [h.to_dict() for h in registry.all()],
    }


@router.get("/live-experiments")
async def live_experiments() -> dict[str, Any]:
    """Claims registered for prospective test, and how far from mature."""
    from ..research.live_experiments import get_live_registry

    return get_live_registry().report()


@router.get("/redundancy")
async def redundancy() -> dict[str, Any]:
    """How many independent questions the feature set actually contains."""
    payload = _require("lot6b.json", "lot6b")
    return {
        "generated_at": payload.get("generated_at"),
        "redundancy": payload.get("redundancy", {}),
        "ablation": payload.get("ablation", {}),
    }

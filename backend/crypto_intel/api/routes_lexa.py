"""Lexa analyses - served to this machine only.

The content comes from a personal subscription whose terms forbid any
redistribution. So:

  - every route answers only to a loopback client (127.0.0.1 / ::1), even if
    the server were ever exposed by mistake;
  - no route is part of the static export (the export script refuses them,
    and a test pins it);
  - a Lexa analysis never feeds BUY / WAIT / SELL. The comparison route puts
    the two readings side by side and changes neither.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..lexa import test_run
from ..lexa.repository import (
    AssetInput,
    LevelInput,
    LexaInputError,
    asset_history,
    asset_report,
    correct_level,
    create_video,
    get_capital,
    list_by_date,
    set_capital,
)

router = APIRouter(prefix="/lexa", tags=["lexa (local)"])

LOOPBACK = {"127.0.0.1", "::1", "localhost", "testclient"}


def _local_only(request: Request) -> None:
    host = request.client.host if request.client else ""
    if host not in LOOPBACK:
        raise HTTPException(403, "Lexa n'est accessible que depuis cette machine.")


class LevelBody(BaseModel):
    kind: str
    value: float
    allocation_pct: float | None = None
    timestamp: str | None = None
    source_text: str = ""
    condition: str = "UNKNOWN"
    confidence: str = "HIGH"
    label: str = ""


class AssetBody(BaseModel):
    asset: str
    price_at_video: float | None = None
    stance: str = "UNSPECIFIED"
    summary: str = ""
    levels: list[LevelBody] = Field(default_factory=list)


class VideoBody(BaseModel):
    title: str
    published_at: datetime
    duration_s: int | None = None
    source_ref: str = ""
    assets: list[AssetBody]


class CorrectionBody(BaseModel):
    value: float


class CapitalBody(BaseModel):
    value: float
    asset: str | None = None


def _bad(exc: LexaInputError) -> HTTPException:
    return HTTPException(422, str(exc))


@router.get("/videos")
def get_videos(request: Request) -> dict[str, Any]:
    _local_only(request)
    return {"videos": list_by_date(), "capital_default_eur": get_capital("default")}


@router.post("/videos")
def post_video(body: VideoBody, request: Request) -> dict[str, Any]:
    _local_only(request)
    try:
        video_id = create_video(
            title=body.title, published_at=body.published_at, duration_s=body.duration_s,
            source_ref=body.source_ref,
            assets=[
                AssetInput(
                    asset=a.asset, price_at_video=a.price_at_video, stance=a.stance,
                    summary=a.summary,
                    levels=[LevelInput(**level.model_dump()) for level in a.levels],
                )
                for a in body.assets
            ],
        )
    except LexaInputError as exc:
        raise _bad(exc) from exc
    return {"video_id": video_id}


@router.get("/analyses/{analysis_id}")
def get_analysis(analysis_id: int, request: Request) -> dict[str, Any]:
    _local_only(request)
    try:
        return asset_report(analysis_id)
    except LexaInputError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/history/{asset}")
def get_history(asset: str, request: Request) -> dict[str, Any]:
    _local_only(request)
    return {"asset": asset.upper(), "analyses": asset_history(asset)}


@router.post("/levels/{level_id}/correction")
def post_correction(level_id: int, body: CorrectionBody, request: Request) -> dict[str, Any]:
    _local_only(request)
    try:
        return correct_level(level_id, body.value)
    except LexaInputError as exc:
        raise _bad(exc) from exc


@router.put("/settings/capital")
def put_capital(body: CapitalBody, request: Request) -> dict[str, Any]:
    _local_only(request)
    try:
        return {"capital_eur": set_capital(body.value, body.asset), "asset": body.asset}
    except LexaInputError as exc:
        raise _bad(exc) from exc


@router.get("/compare/{analysis_id}")
def get_comparison(analysis_id: int, request: Request) -> dict[str, Any]:
    """Lexa beside our own reading. Neither is adjusted to the other."""

    _local_only(request)
    try:
        lexa = asset_report(analysis_id)
    except LexaInputError as exc:
        raise HTTPException(404, str(exc)) from exc
    ours: dict[str, Any] | None = None
    if lexa["asset"] in {"BTC", "ETH", "SOL"}:
        from .routes_future import future_decision

        decision = future_decision(lexa["asset"], "7d")
        summary = ((decision.get("analysis") or {}).get("summary") or {})
        ours = {
            "action": decision.get("decision"),
            "sentence": summary.get("sentence"),
            "trend": summary.get("trend"),
            "risk": summary.get("risk"),
            "home_families": summary.get("home_families"),
            "horizon": "7d",
        }
    return {
        "lexa": lexa,
        "ours": ours,
        "ours_note": (
            None if ours is not None
            else f"L'application n'analyse pas {lexa['asset']} : aucune comparaison possible."
        ),
        "rule": "Les deux lectures restent indépendantes : aucune ne corrige l'autre.",
    }


class TestRunBody(BaseModel):
    transcript: str
    title: str
    published_at: str | None = None
    source: str = "Transcription collée par le membre"
    capital: float = 100.0


@router.post("/test-runs")
def post_test_run(body: TestRunBody, request: Request) -> dict[str, Any]:
    """One video's transcript through the whole chain. Nothing is imported."""

    _local_only(request)
    if not body.title.strip():
        raise HTTPException(422, "Le titre de la vidéo est obligatoire.")
    try:
        run_id = test_run.start(body.transcript, title=body.title.strip(),
                                published_at=body.published_at or None,
                                source=body.source, capital=body.capital)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"run_id": run_id}


@router.get("/test-runs")
def get_test_runs(request: Request) -> dict[str, Any]:
    _local_only(request)
    return {"runs": test_run.list_runs()}


@router.get("/test-runs/{run_id}")
def get_test_run(run_id: str, request: Request) -> dict[str, Any]:
    _local_only(request)
    run = test_run.get(run_id)
    if run is None:
        raise HTTPException(404, "Test introuvable.")
    return run

"""Lexa analyses - served to this machine only.

The content comes from a personal subscription whose terms forbid any
redistribution. So:

  - every route answers only to this machine (127.0.0.1 / ::1) or to the
    member's own devices on their private Tailscale network (100.64.0.0/10),
    even if the server were ever exposed by mistake;
  - no route is part of the static export (the export script refuses them,
    and a test pins it);
  - a Lexa analysis never feeds BUY / WAIT / SELL. The comparison route puts
    the two readings side by side and changes neither.
"""

from __future__ import annotations

import ipaddress
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..lexa import test_run
from ..lexa.repository import (
    AssetInput,
    ConditionInput,
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
from ..logging_setup import get_logger

log = get_logger(__name__)
router = APIRouter(prefix="/lexa", tags=["lexa (local)"])

LOOPBACK = {"127.0.0.1", "::1", "localhost", "testclient"}
#: The member's private Tailscale network. `tailscale serve` (tailnet only,
#: never Funnel) forwards their devices here with their 100.x address.
TAILNET = (ipaddress.ip_network("100.64.0.0/10"), ipaddress.ip_network("fd7a:115c:a1e0::/48"))


def _origin_allowed(origin: str) -> bool:
    import re

    from ..settings import get_settings

    settings = get_settings()
    return origin in settings.cors_list or bool(
        settings.cors_origin_regex and re.fullmatch(settings.cors_origin_regex, origin))


def _local_only(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin and not _origin_allowed(origin):
        # The browser will drop this answer: say which page asked, so the
        # member's app address can be added to CORS_ORIGINS on purpose.
        log.warning("lexa_origin_not_allowed", origin=origin)
    host = request.client.host if request.client else ""
    if host in LOOPBACK:
        return
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is None or not any(address in net for net in TAILNET):
        raise HTTPException(403, "Lexa n'est accessible que depuis tes appareils (PC ou Tailscale).")


class ConditionBody(BaseModel):
    condition_type: str = "CLOSE"
    timeframe: str | None = None
    operator: str = "ABOVE"
    required_closes: int = 1
    confirmation_window: int | None = None
    description: str = ""
    basis: str = "EXPLICIT"


class LevelBody(BaseModel):
    kind: str
    value: float
    allocation_pct: float | None = None
    timestamp: str | None = None
    source_text: str = ""
    condition: str = "UNKNOWN"
    confidence: str = "HIGH"
    label: str = ""
    basis: str = "EXPLICIT"
    conditions: list[ConditionBody] = Field(default_factory=list)


class AssetBody(BaseModel):
    asset: str
    price_at_video: float | None = None
    stance: str = "UNSPECIFIED"
    summary: str = ""
    market_context: str = ""
    review_at: datetime | None = None
    expires_at: datetime | None = None
    levels: list[LevelBody] = Field(default_factory=list)


class VideoBody(BaseModel):
    title: str
    published_at: datetime
    duration_s: int | None = None
    source_ref: str = ""
    video_url: str = ""
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
            source_ref=body.source_ref, video_url=body.video_url,
            assets=[
                AssetInput(
                    asset=a.asset, price_at_video=a.price_at_video, stance=a.stance,
                    summary=a.summary, market_context=a.market_context,
                    review_at=a.review_at, expires_at=a.expires_at,
                    levels=[LevelInput(**{**level.model_dump(exclude={"conditions"}),
                                          "conditions": [ConditionInput(**c.model_dump())
                                                         for c in level.conditions]})
                            for level in a.levels],
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


# --- the Lexa tab: plans, calendar, history, notifications ---------------------------

from ..lexa import notifier as lexa_notifier  # noqa: E402
from ..lexa import repository as lexa_repo  # noqa: E402
from ..lexa import service as lexa_service  # noqa: E402
from ..lexa.market import default_market  # noqa: E402


@router.get("/overview")
def get_overview(request: Request) -> dict[str, Any]:
    _local_only(request)
    return lexa_service.overview()


@router.get("/plans/{asset}")
def get_plan_for_asset(asset: str, request: Request) -> dict[str, Any]:
    """The plan the tab follows for this crypto: its latest analysis."""

    _local_only(request)
    analysis_id = lexa_service.current_ids().get(asset.upper())
    if analysis_id is None:
        raise HTTPException(404, f"Aucune analyse Lexa pour {asset.upper()}.")
    return lexa_service.plan_for(analysis_id)


@router.get("/analyses/{analysis_id}/plan")
def get_plan(analysis_id: int, request: Request) -> dict[str, Any]:
    _local_only(request)
    plan = lexa_service.plan_for(analysis_id)
    if plan is None:
        raise HTTPException(404, "Analyse introuvable.")
    return plan


@router.get("/calendar")
def get_calendar(request: Request) -> dict[str, Any]:
    _local_only(request)
    return lexa_service.calendar()


@router.get("/plans-history")
def get_plans_history(request: Request, asset: str | None = None) -> dict[str, Any]:
    _local_only(request)
    return lexa_service.history(asset)


@router.get("/notifications")
def get_notifications(request: Request) -> dict[str, Any]:
    _local_only(request)
    return {"notifications": lexa_notifier.listing(), "unread": lexa_notifier.unread_count()}


@router.post("/notifications/read")
def post_notifications_read(request: Request) -> dict[str, Any]:
    _local_only(request)
    lexa_notifier.mark_read()
    return {"unread": 0}


@router.post("/evaluate")
def post_evaluate(request: Request) -> dict[str, Any]:
    """Run the watcher now (it also runs every 5 minutes)."""

    _local_only(request)
    return {"sent": lexa_notifier.evaluate_all()}


class PlanItem(BaseModel):
    level_id: int
    amount_type: str = "EURO"
    amount: float | None = None
    action: str | None = None


class UserPlanBody(BaseModel):
    budget_eur: float | None = None
    items: list[PlanItem] = Field(default_factory=list)


@router.put("/analyses/{analysis_id}/user-plan")
def put_user_plan(analysis_id: int, body: UserPlanBody, request: Request) -> dict[str, Any]:
    """OUR budget and amounts. Stored as USER_PLAN, never as something Lexa said."""

    _local_only(request)
    try:
        if body.budget_eur is not None:
            bundle = lexa_service.plans.load(analysis_id)
            if bundle is None:
                raise LexaInputError("Analyse introuvable.")
            lexa_repo.set_capital(body.budget_eur, bundle.analysis.asset)
        lexa_repo.set_user_plan(analysis_id, [item.model_dump() for item in body.items])
    except LexaInputError as exc:
        raise _bad(exc) from exc
    return lexa_service.plan_for(analysis_id)


class FillBody(BaseModel):
    side: str
    price_usd: float
    amount_eur: float | None = None
    quantity: float | None = None
    level_id: int | None = None
    executed_at: datetime | None = None
    note: str = ""


@router.post("/analyses/{analysis_id}/fills")
def post_fill(analysis_id: int, body: FillBody, request: Request) -> dict[str, Any]:
    """A purchase or sale the member made themselves. The app never places orders."""

    _local_only(request)
    try:
        eurusd = default_market().eurusd() if body.quantity is None else None
        lexa_repo.add_fill(analysis_id, side=body.side, price_usd=body.price_usd,
                           amount_eur=body.amount_eur, quantity=body.quantity, eurusd=eurusd,
                           level_id=body.level_id, executed_at=body.executed_at, note=body.note)
    except LexaInputError as exc:
        raise _bad(exc) from exc
    return lexa_service.plan_for(analysis_id)


@router.delete("/fills/{fill_id}")
def delete_fill(fill_id: int, request: Request) -> dict[str, Any]:
    _local_only(request)
    try:
        lexa_repo.delete_fill(fill_id)
    except LexaInputError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"deleted": fill_id}


class StatusBody(BaseModel):
    status: str | None = None
    reason: str = ""
    review_at: datetime | None = None
    expires_at: datetime | None = None


@router.post("/analyses/{analysis_id}/status")
def post_status(analysis_id: int, body: StatusBody, request: Request) -> dict[str, Any]:
    """Invalidate, complete, reopen or re-evaluate (new review / expiry dates)."""

    _local_only(request)
    try:
        if body.review_at or body.expires_at:
            lexa_repo.set_dates(analysis_id, body.review_at, body.expires_at)
        else:
            lexa_repo.set_status(analysis_id, body.status, body.reason)
    except LexaInputError as exc:
        raise _bad(exc) from exc
    return lexa_service.plan_for(analysis_id)


@router.post("/test-runs/{run_id}/import")
def post_import_test_run(run_id: str, request: Request) -> dict[str, Any]:
    """After the member checked a test run: its verified content becomes analyses."""

    _local_only(request)
    try:
        video_id = test_run.import_run(run_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"video_id": video_id, "current": lexa_service.current_ids()}

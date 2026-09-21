"""Reading and writing Lexa analyses - immutable, dated, traceable.

Writes create; they never overwrite. A new video is a new scenario, kept beside
the previous one. The only later change allowed is a correction of a value,
which keeps the original.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from .levels import CONDITIONS, track
from .simulation import SimLevel, simulate
from .store import (
    LexaActionRow,
    LexaAnalysisRow,
    LexaConditionRow,
    LexaFillRow,
    LexaLevelRow,
    LexaSettingRow,
    LexaVideoRow,
    lexa_session,
)

LEVEL_KINDS = {
    "CURRENT_PRICE", "SUPPORT", "RESISTANCE", "BUY_ZONE", "REINFORCEMENT", "CONFIRMATION",
    "INVALIDATION", "TARGET", "TAKE_PROFIT", "MACRO", "TECHNICAL", "WARNING", "OTHER",
    "BREAKOUT",
}
KIND_FR = {
    "CURRENT_PRICE": ("💲", "Prix observé"),
    "SUPPORT": ("🧱", "Support"),
    "RESISTANCE": ("🧱", "Résistance"),
    "BUY_ZONE": ("🟢", "Zone d'achat Lexa"),
    "REINFORCEMENT": ("🟢", "Renforcement Lexa"),
    "CONFIRMATION": ("🚀", "Confirmation"),
    "BREAKOUT": ("🚀", "Cassure"),
    "INVALIDATION": ("❌", "Invalidation"),
    "TARGET": ("🎯", "Objectif"),
    "TAKE_PROFIT": ("🎯", "Prise de profit"),
    "MACRO": ("🏛️", "Macro"),
    "TECHNICAL": ("📊", "Technique"),
    "WARNING": ("⚠️", "Avertissement"),
    "OTHER": ("📝", "Autre"),
}
STANCES = {
    "WAIT": ("🟠", "Attente"),
    "BUY": ("🟢", "Achat"),
    "SELL": ("🔴", "Vente"),
    "NEUTRAL": ("⚪", "Neutre"),
    "UNSPECIFIED": ("⚪", "Non précisé"),
}
DEFAULT_CAPITAL_EUR = 100.0


class LexaInputError(ValueError):
    pass


def parse_timestamp(value: str | int | None) -> int | None:
    """"18:42" -> 1122 s, "1:02:05" -> 3725 s. Anything else is rejected."""

    if value is None or value == "":
        return None
    if isinstance(value, int):
        return value
    parts = str(value).strip().split(":")
    if not 1 <= len(parts) <= 3 or not all(re.fullmatch(r"\d{1,2}", p) for p in parts):
        raise LexaInputError(f"Horodatage illisible : « {value} » (format attendu 18:42).")
    seconds = 0
    for part in parts:
        seconds = seconds * 60 + int(part)
    return seconds


def format_timestamp(seconds: int | None) -> str | None:
    if seconds is None:
        return None
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


CONDITION_TYPES = {"CLOSE", "TOUCH", "HOLD", "RETEST", "VOLUME", "OTHER"}
TIMEFRAMES = {"1H", "4H", "1D", "1W"}


@dataclass(slots=True)
class ConditionInput:
    """How the video says the level counts. Only what was said."""

    condition_type: str = "CLOSE"
    timeframe: str | None = None
    operator: str = "ABOVE"
    required_closes: int = 1
    confirmation_window: int | None = None
    description: str = ""
    basis: str = "EXPLICIT"


@dataclass(slots=True)
class LevelInput:
    kind: str
    value: float
    #: Only a share Lexa herself stated. Our own amounts go to the user plan.
    allocation_pct: float | None = None
    timestamp: str | int | None = None
    source_text: str = ""
    condition: str = "UNKNOWN"
    confidence: str = "HIGH"
    label: str = ""
    basis: str = "EXPLICIT"
    conditions: list[ConditionInput] = field(default_factory=list)


@dataclass(slots=True)
class AssetInput:
    asset: str
    price_at_video: float | None = None
    stance: str = "UNSPECIFIED"
    summary: str = ""
    levels: list[LevelInput] = field(default_factory=list)
    market_context: str = ""
    review_at: datetime | None = None
    expires_at: datetime | None = None
    timestamp_start: str | int | None = None
    timestamp_end: str | int | None = None
    source_type: str = "MANUAL_NOTES"


def _legacy_condition(level: LevelInput) -> list[ConditionInput]:
    """« CLOSE_4H_ABOVE » from older entries, as a condition row."""

    if level.conditions or level.condition in ("", "UNKNOWN"):
        return list(level.conditions)
    _, tf, side = level.condition.split("_")
    return [ConditionInput(condition_type="CLOSE", timeframe=tf, operator=side)]


def _validate_level(level: LevelInput) -> None:
    if level.kind not in LEVEL_KINDS:
        raise LexaInputError(f"Type de niveau inconnu : {level.kind}.")
    if level.value is None or level.value <= 0:
        raise LexaInputError("Un niveau doit avoir une valeur positive.")
    if level.condition not in CONDITIONS:
        raise LexaInputError(f"Condition inconnue : {level.condition}.")
    if level.allocation_pct is not None and not 0 < level.allocation_pct <= 100:
        raise LexaInputError("Une allocation est un pourcentage entre 0 et 100.")
    if level.confidence not in {"HIGH", "MEDIUM", "LOW"}:
        raise LexaInputError("Confiance attendue : HIGH, MEDIUM ou LOW.")
    if level.basis not in {"EXPLICIT", "INFERRED"}:
        raise LexaInputError("Origine attendue : EXPLICIT (dit) ou INFERRED (déduit).")
    for cond in level.conditions:
        if cond.condition_type not in CONDITION_TYPES:
            raise LexaInputError(f"Type de condition inconnu : {cond.condition_type}.")
        if cond.timeframe is not None and cond.timeframe not in TIMEFRAMES:
            raise LexaInputError(f"Unité de temps inconnue : {cond.timeframe}.")
        if cond.operator not in {"ABOVE", "BELOW"}:
            raise LexaInputError("Sens attendu : ABOVE ou BELOW.")
        if cond.required_closes < 1 or (cond.confirmation_window or 0) < 0:
            raise LexaInputError("Nombre de clôtures ou fenêtre de confirmation invalide.")
        if cond.condition_type == "CLOSE" and cond.timeframe is None:
            raise LexaInputError("Une condition de clôture a besoin d'une unité de temps "
                                 "(1H, 4H, 1D, 1W). Si la vidéo ne la donne pas, ne mets pas de condition.")


def create_video(*, title: str, published_at: datetime, assets: list[AssetInput],
                 duration_s: int | None = None, source_ref: str = "", video_url: str = "",
                 source_kind: str = "MANUAL_NOTES") -> int:
    """Store one video and its per-asset scenarios. Never updates an existing one."""

    if not title.strip():
        raise LexaInputError("Le titre de la vidéo est obligatoire.")
    if not assets:
        raise LexaInputError("Au moins une crypto doit être renseignée.")
    for asset in assets:
        for level in asset.levels:
            _validate_level(level)
        if asset.stance not in STANCES:
            raise LexaInputError(f"Position inconnue : {asset.stance}.")
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=UTC)
    created: list[int] = []
    with lexa_session() as session:
        video = LexaVideoRow(title=title.strip(), published_at=published_at,
                             duration_s=duration_s, source_ref=source_ref,
                             video_url=video_url.strip(),
                             source_kind=source_kind, status="ANALYSED")
        session.add(video)
        session.flush()
        for asset in assets:
            analysis = LexaAnalysisRow(
                video_id=video.id, asset=asset.asset.upper().strip(),
                published_at=published_at, price_at_video=asset.price_at_video,
                stance=asset.stance, summary=asset.summary.strip(),
                market_context=asset.market_context.strip(),
                source_type=asset.source_type,
                review_at=_aware(asset.review_at), expires_at=_aware(asset.expires_at),
                timestamp_start_s=parse_timestamp(asset.timestamp_start),
                timestamp_end_s=parse_timestamp(asset.timestamp_end),
            )
            session.add(analysis)
            session.flush()
            created.append(analysis.id)
            for level in asset.levels:
                row = LexaLevelRow(
                    analysis_id=analysis.id, kind=level.kind, original_value=float(level.value),
                    allocation_pct=level.allocation_pct,
                    timestamp_s=parse_timestamp(level.timestamp),
                    source_text=level.source_text.strip(), condition=level.condition,
                    confidence=level.confidence, label=level.label.strip(), basis=level.basis,
                )
                session.add(row)
                session.flush()
                for cond in _legacy_condition(level):
                    session.add(LexaConditionRow(
                        level_id=row.id, condition_type=cond.condition_type,
                        timeframe=cond.timeframe, operator=cond.operator,
                        required_closes=cond.required_closes,
                        confirmation_window=cond.confirmation_window,
                        description=cond.description.strip(), basis=cond.basis))
        video_id = video.id
    from .service import record_supersession

    record_supersession(created)
    return video_id


def _aware(moment: datetime | None) -> datetime | None:
    if moment is None:
        return None
    return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment


def correct_level(level_id: int, corrected_value: float) -> dict[str, Any]:
    """Fix a misheard value. The original is kept, forever."""

    if corrected_value is None or corrected_value <= 0:
        raise LexaInputError("La valeur corrigée doit être positive.")
    with lexa_session() as session:
        row = session.get(LexaLevelRow, level_id)
        if row is None:
            raise LexaInputError("Niveau introuvable.")
        row.corrected_value = float(corrected_value)
        row.corrected_at = datetime.now(UTC)
        return {"id": row.id, "original_value": row.original_value,
                "corrected_value": row.corrected_value,
                "corrected_at": row.corrected_at.isoformat()}


def get_capital(asset: str) -> float:
    with lexa_session() as session:
        row = session.get(LexaSettingRow, f"capital:{asset.upper()}")
        default = session.get(LexaSettingRow, "capital:default")
    for candidate in (row, default):
        if candidate is not None:
            try:
                return float(candidate.value)
            except ValueError:
                continue
    return DEFAULT_CAPITAL_EUR


def set_capital(value: float, asset: str | None = None) -> float:
    if value is None or value <= 0:
        raise LexaInputError("Le capital simulé doit être positif.")
    key = f"capital:{asset.upper()}" if asset else "capital:default"
    with lexa_session() as session:
        row = session.get(LexaSettingRow, key)
        if row is None:
            session.add(LexaSettingRow(key=key, value=str(float(value))))
        else:
            row.value = str(float(value))
    return float(value)


def _level_dict(row: LexaLevelRow, state: dict[str, Any] | None,
                allocation_eur: float | None) -> dict[str, Any]:
    emoji, label = KIND_FR.get(row.kind, ("📝", row.kind))
    value = row.corrected_value if row.corrected_value is not None else row.original_value
    return {
        "id": row.id,
        "kind": row.kind,
        "emoji": emoji,
        "kind_label": row.label or label,
        "value": value,
        "original_value": row.original_value,
        "corrected_value": row.corrected_value,
        "corrected_at": _utc(row.corrected_at).isoformat() if row.corrected_at else None,
        "unit": row.unit,
        "allocation_pct": row.allocation_pct,
        "allocation_eur": round(allocation_eur, 2) if allocation_eur is not None else None,
        "timestamp_s": row.timestamp_s,
        "timestamp": format_timestamp(row.timestamp_s),
        "source_text": row.source_text,
        "condition": row.condition,
        "condition_label": CONDITIONS.get(row.condition, ("",))[0] or "Condition non précisée",
        "confidence": row.confidence,
        "to_verify": row.confidence == "LOW",
        "state": state,
    }


def _utc(moment: datetime) -> datetime:
    """SQLite hands datetimes back without their zone; they were stored as UTC."""

    return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment


def _price_frame(asset: str, published_at: datetime):
    from .prices import hourly_prices

    return hourly_prices(asset, published_at)


def asset_report(analysis_id: int, *, with_market: bool = True) -> dict[str, Any]:
    """One crypto, one video: levels, their states, and the simulation."""

    with lexa_session() as session:
        analysis = session.get(LexaAnalysisRow, analysis_id)
        if analysis is None:
            raise LexaInputError("Analyse introuvable.")
        video = session.get(LexaVideoRow, analysis.video_id)
        levels = session.execute(
            select(LexaLevelRow).where(LexaLevelRow.analysis_id == analysis_id)
            .order_by(LexaLevelRow.id)
        ).scalars().all()

    published_at = _utc(analysis.published_at)
    capital = get_capital(analysis.asset)
    frame = _price_frame(analysis.asset, published_at) if with_market else None
    sim_levels = [
        SimLevel(id=row.id, kind=row.kind,
                 value=row.corrected_value if row.corrected_value is not None else row.original_value,
                 allocation_pct=row.allocation_pct, label=row.label)
        for row in levels
    ]
    invalidation = next(
        (lv.value for lv in sim_levels if lv.kind == "INVALIDATION"), None,
    )
    simulation = simulate(sim_levels, frame, capital_eur=capital,
                          published_at=published_at, invalidation=invalidation)
    stance_emoji, stance_label = STANCES.get(analysis.stance, STANCES["UNSPECIFIED"])
    return {
        "analysis_id": analysis.id,
        "asset": analysis.asset,
        "video": {
            "id": video.id,
            "title": video.title,
            "published_at": _utc(video.published_at).isoformat(),
            "duration_s": video.duration_s,
            "source_ref": video.source_ref,
            "source": "Lexa Moon",
        },
        "published_at": published_at.isoformat(),
        "processed_at": _utc(analysis.processed_at).isoformat(),
        "price_at_video": analysis.price_at_video,
        "quote": analysis.quote,
        "stance": analysis.stance,
        "stance_emoji": stance_emoji,
        "stance_label": stance_label,
        "summary": analysis.summary,
        "capital_eur": capital,
        "current_price": simulation.current_price,
        "levels": [
            _level_dict(
                row,
                track(row.kind,
                      row.corrected_value if row.corrected_value is not None else row.original_value,
                      row.condition, frame, analysis.published_at).to_dict()
                if row.kind not in {"MACRO", "TECHNICAL", "WARNING", "OTHER", "CURRENT_PRICE"}
                else None,
                simulation.allocations_eur.get(row.id),
            )
            for row in levels
        ],
        "simulation": simulation.to_dict(),
        "origin": "LEXA",
        "note": "Ce que dit Lexa - distinct de ce que montrent les données de l'application.",
    }


def list_by_date(limit: int = 60) -> list[dict[str, Any]]:
    """Videos, newest first, each with the cryptos it covers."""

    with lexa_session() as session:
        videos = session.execute(
            select(LexaVideoRow).order_by(LexaVideoRow.published_at.desc()).limit(limit)
        ).scalars().all()
        analyses = session.execute(
            select(LexaAnalysisRow).where(LexaAnalysisRow.video_id.in_([v.id for v in videos]))
        ).scalars().all() if videos else []
    per_video: dict[int, list[LexaAnalysisRow]] = {}
    for row in analyses:
        per_video.setdefault(row.video_id, []).append(row)
    return [
        {
            "video_id": video.id,
            "title": video.title,
            "published_at": _utc(video.published_at).isoformat(),
            "date": video.published_at.date().isoformat(),
            "duration_s": video.duration_s,
            "status": video.status,
            "assets": [
                {"asset": a.asset, "analysis_id": a.id, "stance": a.stance}
                for a in sorted(per_video.get(video.id, []), key=lambda a: a.asset)
            ],
        }
        for video in videos
    ]


def asset_history(asset: str, limit: int = 30) -> list[dict[str, Any]]:
    """Every scenario for one crypto, newest first - nothing overwritten."""

    with lexa_session() as session:
        rows = session.execute(
            select(LexaAnalysisRow).where(LexaAnalysisRow.asset == asset.upper())
            .order_by(LexaAnalysisRow.published_at.desc()).limit(limit)
        ).scalars().all()
    return [asset_report(row.id) for row in rows]


# --- USER_PLAN, fills, status: what WE decide and do --------------------------------

PLAN_ACTIONS = {"BUY", "BUY_PARTIAL", "HOLD", "TAKE_PROFIT", "SELL", "WAIT", "WAIT_CLOSE", "WATCH"}


def set_user_plan(analysis_id: int, items: list[dict[str, Any]]) -> None:
    """Replace our own amounts for this analysis. Never touches Lexa's values."""

    with lexa_session() as session:
        if session.get(LexaAnalysisRow, analysis_id) is None:
            raise LexaInputError("Analyse introuvable.")
        levels = {row.id: row for row in session.execute(select(LexaLevelRow).where(
            LexaLevelRow.analysis_id == analysis_id)).scalars()}
        for item in items:
            level_id = item.get("level_id")
            if level_id not in levels:
                raise LexaInputError("Niveau inconnu pour cette analyse.")
            amount_type = item.get("amount_type", "NONE")
            amount = item.get("amount")
            if amount_type not in ("EURO", "PERCENT", "NONE"):
                raise LexaInputError("Type de montant attendu : EURO, PERCENT ou NONE.")
            if amount is not None and (amount < 0 or (amount_type == "PERCENT" and amount > 100)):
                raise LexaInputError("Montant invalide.")
        for row in session.execute(select(LexaActionRow).where(
                LexaActionRow.analysis_id == analysis_id,
                LexaActionRow.origin == "USER_PLAN")).scalars():
            session.delete(row)
        for item in items:
            level = levels[item["level_id"]]
            action = item.get("action") or ("TAKE_PROFIT" if level.kind in ("TARGET", "TAKE_PROFIT")
                                            else "BUY")
            if action not in PLAN_ACTIONS:
                raise LexaInputError(f"Action inconnue : {action}.")
            session.add(LexaActionRow(analysis_id=analysis_id, level_id=level.id, action=action,
                                      amount_type=item.get("amount_type", "NONE"),
                                      amount=item.get("amount"), origin="USER_PLAN"))


def add_fill(analysis_id: int, *, side: str, price_usd: float, amount_eur: float | None = None,
             quantity: float | None = None, eurusd: float | None = None,
             level_id: int | None = None, executed_at: datetime | None = None,
             note: str = "") -> int:
    """Record a purchase or a sale the member made. The app never places one."""

    if side not in ("BUY", "SELL"):
        raise LexaInputError("Sens attendu : BUY ou SELL.")
    if price_usd is None or price_usd <= 0:
        raise LexaInputError("Le prix d'exécution doit être positif.")
    if quantity is None:
        if amount_eur is None or amount_eur <= 0 or not eurusd:
            raise LexaInputError("Indique la quantité, ou le montant en euros (taux €/$ requis).")
        quantity = amount_eur * eurusd / price_usd
    if quantity <= 0:
        raise LexaInputError("La quantité doit être positive.")
    with lexa_session() as session:
        if session.get(LexaAnalysisRow, analysis_id) is None:
            raise LexaInputError("Analyse introuvable.")
        row = LexaFillRow(analysis_id=analysis_id, level_id=level_id, side=side,
                          price_usd=price_usd, quantity=quantity, amount_eur=amount_eur,
                          eurusd=eurusd, executed_at=_aware(executed_at) or datetime.now(UTC),
                          note=note)
        session.add(row)
        session.flush()
        return row.id


def delete_fill(fill_id: int) -> None:
    with lexa_session() as session:
        row = session.get(LexaFillRow, fill_id)
        if row is None:
            raise LexaInputError("Exécution introuvable.")
        session.delete(row)


def set_status(analysis_id: int, status: str | None, reason: str = "") -> None:
    """The member closes a plan: INVALIDATED or COMPLETED. None reopens it."""

    if status not in (None, "INVALIDATED", "COMPLETED"):
        raise LexaInputError("Statut attendu : INVALIDATED, COMPLETED ou vide.")
    with lexa_session() as session:
        row = session.get(LexaAnalysisRow, analysis_id)
        if row is None:
            raise LexaInputError("Analyse introuvable.")
        row.status_override, row.status_reason = status, reason.strip()
        row.status_changed_at = datetime.now(UTC)


def set_dates(analysis_id: int, review_at: datetime | None, expires_at: datetime | None) -> None:
    """Re-evaluated by the member: move the review and the expiry."""

    with lexa_session() as session:
        row = session.get(LexaAnalysisRow, analysis_id)
        if row is None:
            raise LexaInputError("Analyse introuvable.")
        if review_at is not None:
            row.review_at = _aware(review_at)
        if expires_at is not None:
            row.expires_at = _aware(expires_at)

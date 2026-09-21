"""A Lexa analysis turned into a followed plan.

Four blocks that never mix (section 36 of the brief):

    lexa        EXPLICIT / INFERRED  what the video said: levels, conditions, quotes
    user_plan   USER_PLAN            budget and amounts WE decided
    market      MARKET_VALIDATION    live price, candles, our own engine
    app         interpretation       status, next action, rules - computed here,
                                     deterministic, explained, never an order

The status answers « que faire maintenant ? » in a few words (ACHETER /
ATTENDRE / PRENDRE DES PROFITS / PLAN INVALIDÉ ...) with its reason just
below. A level reached is not an action: the action stays pending while a
condition is missing (close not done, major event, overdue review, our data
contradicting the plan).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from .closes import CloseCondition, CloseEvaluation, evaluate
from .market import SOURCE_FR, TIMEFRAME_FR, Bar, MarketData
from .store import (
    LexaActionRow,
    LexaAnalysisRow,
    LexaConditionRow,
    LexaFillRow,
    LexaLevelRow,
    LexaPlanEventRow,
    LexaVideoRow,
    lexa_session,
)

DEFAULT_REVIEW_DAYS = 7
DEFAULT_EXPIRY_DAYS = 21
NEAR_PCT = 3.0          # « à surveiller » when a level is this close
IN_ZONE_PCT = 0.5       # an entry counts as « in zone » up to this far above it

ENTRY = ("BUY_ZONE", "REINFORCEMENT")
TARGETS = ("TARGET", "TAKE_PROFIT")
BREAKOUTS = ("CONFIRMATION", "BREAKOUT")
FROM_ABOVE = {"BUY_ZONE", "REINFORCEMENT", "SUPPORT", "INVALIDATION"}

#: The level types of the brief, from the stored kinds.
TYPE_OF = {"BUY_ZONE": "BUY", "REINFORCEMENT": "STRONG_BUY", "SUPPORT": "SUPPORT",
           "RESISTANCE": "RESISTANCE", "BREAKOUT": "BREAKOUT", "CONFIRMATION": "CONFIRMATION",
           "TARGET": "TAKE_PROFIT", "TAKE_PROFIT": "TAKE_PROFIT", "INVALIDATION": "INVALIDATION"}

STATUS = {
    "BUY_PLANNED": ("🟢", "ACHAT PLANIFIÉ"),
    "BUY_ZONE_REACHED": ("🟢", "ZONE D'ACHAT ATTEINTE"),
    "BULLISH_CONFIRMATION": ("🟢", "CONFIRMATION HAUSSIÈRE"),
    "WAIT": ("🟠", "ATTENDRE"),
    "WAIT_CLOSE": ("🟠", "ATTENDRE CLÔTURE"),
    "WATCH": ("🟠", "À SURVEILLER"),
    "CONFIRMATION_MISSING": ("🟠", "CONFIRMATION MANQUANTE"),
    "BETWEEN_LEVELS": ("🟠", "ENTRE DEUX NIVEAUX"),
    "TAKE_PROFIT": ("🔴", "PRISE DE PROFIT"),
    "SELL_PLANNED": ("🔴", "VENTE PLANIFIÉE"),
    "INVALIDATION": ("🔴", "INVALIDATION"),
    "ACTIVE": ("🔵", "PLAN ACTIF"),
    "COMPLETED": ("⚪", "PLAN TERMINÉ"),
    "EXPIRED": ("⚫", "PLAN EXPIRÉ"),
    "SUPERSEDED": ("⚪", "PLAN REMPLACÉ"),
    "NO_PRICE": ("⚪", "PRIX INDISPONIBLE"),
}
TONE = {"🟢": "GREEN", "🟠": "ORANGE", "🔴": "RED", "🔵": "BLUE", "⚪": "WHITE", "⚫": "BLACK"}
LIFECYCLE_FR = {
    "ACTIVE": "Active", "WATCHING": "Sous surveillance", "TRIGGERED": "Déclenchée",
    "COMPLETED": "Terminée", "INVALIDATED": "Invalidée", "SUPERSEDED": "Remplacée",
    "EXPIRED": "Expirée",
}
BASIS_FR = {"EXPLICIT": "🎬 Dit par Lexa", "INFERRED": "🟡 Interprétation du contexte"}


def utc(moment: datetime | None) -> datetime | None:
    if moment is None:
        return None
    return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment.astimezone(UTC)


def fr_price(value: float | None) -> str:
    if value is None:
        return "—"
    text = f"{value:,.8f}".rstrip("0").rstrip(".")
    text = text.replace(",", " ").replace(".", ",")
    return f"{text} $"


def fr_eur(value: float | None) -> str:
    return "—" if value is None else f"{value:,.2f} €".replace(",", " ").replace(".", ",")


def fr_pct(value: float | None, signed: bool = True) -> str:
    if value is None:
        return "—"
    sign = "+" if signed and value > 0 else ""
    return f"{sign}{value:.1f} %".replace(".", ",")


def fr_day(moment: datetime | None) -> str:
    if moment is None:
        return "—"
    from .market import PARIS

    local = moment.astimezone(PARIS)
    months = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.",
              "oct.", "nov.", "déc."]
    return f"{local.day} {months[local.month - 1]} {local.year} à {local:%H:%M}"


# --- loading ---------------------------------------------------------------------------


@dataclass
class Bundle:
    analysis: LexaAnalysisRow
    video: LexaVideoRow
    levels: list[LexaLevelRow]
    conditions: dict[int, list[LexaConditionRow]]
    actions: list[LexaActionRow]
    fills: list[LexaFillRow]
    events: list[LexaPlanEventRow]
    versions: list[LexaAnalysisRow] = field(default_factory=list)


def load(analysis_id: int) -> Bundle | None:
    with lexa_session() as s:
        analysis = s.get(LexaAnalysisRow, analysis_id)
        if analysis is None:
            return None
        video = s.get(LexaVideoRow, analysis.video_id)
        levels = list(s.execute(select(LexaLevelRow).where(
            LexaLevelRow.analysis_id == analysis_id).order_by(LexaLevelRow.id)).scalars())
        ids = [lv.id for lv in levels]
        conditions: dict[int, list[LexaConditionRow]] = {}
        if ids:
            for row in s.execute(select(LexaConditionRow).where(
                    LexaConditionRow.level_id.in_(ids))).scalars():
                conditions.setdefault(row.level_id, []).append(row)
        actions = list(s.execute(select(LexaActionRow).where(
            LexaActionRow.analysis_id == analysis_id)).scalars())
        fills = list(s.execute(select(LexaFillRow).where(
            LexaFillRow.analysis_id == analysis_id).order_by(LexaFillRow.executed_at)).scalars())
        events = list(s.execute(select(LexaPlanEventRow).where(
            LexaPlanEventRow.analysis_id == analysis_id)).scalars())
        versions = list(s.execute(select(LexaAnalysisRow).where(
            LexaAnalysisRow.asset == analysis.asset).order_by(
            LexaAnalysisRow.published_at, LexaAnalysisRow.id)).scalars())
    return Bundle(analysis, video, levels, conditions, actions, fills, events, versions)


def value_of(level: LexaLevelRow) -> float:
    return level.corrected_value if level.corrected_value is not None else level.original_value


# --- versions --------------------------------------------------------------------------


def _same(a: float | None, b: float | None, tol: float = 0.003) -> bool:
    return a is not None and b is not None and abs(a - b) <= max(abs(a), abs(b)) * tol


def _key_levels(levels: list[LexaLevelRow]) -> dict[str, list[float]]:
    out: dict[str, list[float]] = {"entry": [], "target": [], "invalidation": [], "breakout": []}
    for lv in levels:
        group = ("entry" if lv.kind in ENTRY else "target" if lv.kind in TARGETS else
                 "invalidation" if lv.kind == "INVALIDATION" else
                 "breakout" if lv.kind in BREAKOUTS else None)
        if group:
            out[group].append(value_of(lv))
    return {k: sorted(v) for k, v in out.items()}


def compare_versions(old: LexaAnalysisRow, old_levels: list[LexaLevelRow],
                     new: LexaAnalysisRow, new_levels: list[LexaLevelRow]) -> dict[str, Any]:
    """REPLACES | UPDATES | CONFIRMS | CONTRADICTS, with what changed."""

    a, b = _key_levels(old_levels), _key_levels(new_levels)
    labels = {"entry": "Zone d'achat", "target": "Objectif", "invalidation": "Invalidation",
              "breakout": "Confirmation"}
    changes = []
    for group, label in labels.items():
        olds, news = a[group], b[group]
        if len(olds) == len(news) and all(_same(x, y) for x, y in zip(olds, news, strict=True)):
            continue
        if olds or news:
            changes.append({"what": label, "old": [fr_price(v) for v in olds] or ["—"],
                            "new": [fr_price(v) for v in news] or ["—"]})
    if old.stance != new.stance:
        changes.append({"what": "Position", "old": [old.stance], "new": [new.stance]})
    shared = sum(1 for g in a for x in a[g] if any(_same(x, y) for y in b[g]))
    opposite = {old.stance, new.stance} == {"BUY", "SELL"}
    long_broken = bool(b["invalidation"] and a["entry"] and max(b["invalidation"]) >= max(a["entry"]))
    if opposite or (long_broken and new.stance != "BUY"):
        relation = "CONTRADICTS"
    elif not changes:
        relation = "CONFIRMS"
    elif shared == 0:
        relation = "REPLACES"
    else:
        relation = "UPDATES"
    reason = (new.market_context or new.summary or "").strip()
    return {"relation": relation, "changes": changes,
            "reason": reason or "Raison non précisée dans la nouvelle analyse."}


RELATION_FR = {"REPLACES": "🔄 Remplace l'analyse précédente",
               "UPDATES": "🔄 Plan mis à jour", "CONFIRMS": "✅ Confirme l'analyse précédente",
               "CONTRADICTS": "⚠️ Contredit l'analyse précédente"}


# --- the plan --------------------------------------------------------------------------


def _close_condition(level: LexaLevelRow, row: LexaConditionRow) -> CloseCondition | None:
    if row.condition_type != "CLOSE" or row.timeframe not in ("1H", "4H", "1D", "1W"):
        return None
    return CloseCondition(level=value_of(level), operator=row.operator or "ABOVE",
                          timeframe=row.timeframe, required_closes=max(1, row.required_closes or 1),
                          confirmation_window=row.confirmation_window or None)


def _touch(kind: str, value: float, hourly: list[Bar] | None, since: datetime,
           price: float | None) -> tuple[datetime | None, datetime | None, bool]:
    """First/last touch on hourly candles after the video, and « there now »."""

    first = last = None
    for bar in hourly or []:
        if bar.close_time <= since:
            continue
        hit = bar.low <= value if kind in FROM_ABOVE else bar.high >= value
        if hit:
            moment = max(bar.open_time, since)
            first = first or moment
            last = moment
    now_there = price is not None and (price <= value if kind in FROM_ABOVE else price >= value)
    return first, last, now_there


def _labels(levels: list[LexaLevelRow]) -> dict[int, str]:
    labels: dict[int, str] = {}
    targets = sorted((lv for lv in levels if lv.kind in TARGETS), key=value_of)
    for n, lv in enumerate(targets, 1):
        labels[lv.id] = f"TP{n}"
    for lv in levels:
        default = {"BUY_ZONE": "Achat principal", "REINFORCEMENT": "Achat renforcé",
                   "CONFIRMATION": "Confirmation", "BREAKOUT": "Cassure",
                   "INVALIDATION": "Invalidation", "SUPPORT": "Support",
                   "RESISTANCE": "Résistance"}.get(lv.kind)
        if default and lv.id not in labels:
            labels[lv.id] = lv.label or default
    return labels


EMOJI = {"BUY_ZONE": "🟢", "REINFORCEMENT": "🟢", "CONFIRMATION": "🚀", "BREAKOUT": "🚀",
         "INVALIDATION": "❌", "TARGET": "🔴", "TAKE_PROFIT": "🔴", "SUPPORT": "🧱",
         "RESISTANCE": "🧱", "CURRENT_PRICE": "💲", "WARNING": "⚠️"}


def _budget(bundle: Bundle, budget_eur: float, price: float | None, eurusd: float | None,
            labels: dict[int, str]) -> dict[str, Any]:
    """USER_PLAN: our money. Lexa's percentages only seed the default split."""

    entries = [lv for lv in bundle.levels if lv.kind in ENTRY]
    planned_rows = {a.level_id: a for a in bundle.actions if a.origin == "USER_PLAN"}
    lexa_pcts = [lv.allocation_pct for lv in entries]
    lines = []
    for lv in entries:
        own = planned_rows.get(lv.id)
        if own is not None and own.amount_type == "EURO" and own.amount is not None:
            amount, origin = own.amount, "USER_PLAN"
            note = "Montant décidé par toi"
        elif entries and all(p is not None for p in lexa_pcts):
            amount, origin = budget_eur * lv.allocation_pct / 100, "APP_FROM_LEXA_PCT"
            note = f"Ton budget réparti selon les {lv.allocation_pct:g} % cités par Lexa"
        else:
            amount, origin = budget_eur / len(entries), "APP_EQUAL_SPLIT"
            note = "Réparti à parts égales par l'app (Lexa ne donne pas de montant)"
        lines.append({"level_id": lv.id, "label": labels.get(lv.id, ""), "value": value_of(lv),
                      "amount_eur": round(amount, 2), "origin": origin, "note": note})
    exits = []
    for lv in sorted((lv for lv in bundle.levels if lv.kind in TARGETS), key=value_of):
        own = planned_rows.get(lv.id)
        if own is not None and own.amount_type == "PERCENT" and own.amount is not None:
            pct, origin = own.amount, "USER_PLAN"
        elif lv.allocation_pct is not None:
            pct, origin = lv.allocation_pct, "LEXA"
        else:
            pct, origin = None, "UNSET"
        exits.append({"level_id": lv.id, "label": labels.get(lv.id, ""), "value": value_of(lv),
                      "pct": pct, "origin": origin})

    bought = [f for f in bundle.fills if f.side == "BUY"]
    sold = [f for f in bundle.fills if f.side == "SELL"]

    def eur_of(fill: LexaFillRow) -> float | None:
        if fill.amount_eur is not None:
            return fill.amount_eur
        rate = fill.eurusd or eurusd
        return fill.quantity * fill.price_usd / rate if rate else None

    deployed = sum(eur_of(f) or 0 for f in bought)
    realised = sum(eur_of(f) or 0 for f in sold)
    quantity = sum(f.quantity for f in bought) - sum(f.quantity for f in sold)
    value_now = quantity * price / eurusd if (price and eurusd and quantity > 0) else None
    for line in exits:
        if line["pct"] is not None and quantity > 0:
            line["quantity"] = quantity * line["pct"] / 100
            line["value_eur"] = (line["quantity"] * line["value"] / eurusd) if eurusd else None
    planned = sum(line["amount_eur"] for line in lines)
    return {
        "budget_eur": budget_eur, "planned_eur": round(planned, 2),
        "deployed_eur": round(deployed, 2), "available_eur": round(budget_eur - deployed, 2),
        "realised_eur": round(realised, 2), "quantity": quantity,
        "average_price": (sum(f.quantity * f.price_usd for f in bought) / sum(f.quantity for f in bought)
                          if bought else None),
        "position_value_eur": round(value_now, 2) if value_now is not None else None,
        "eurusd": eurusd, "entries": lines, "exits": exits,
        "fills": [{"id": f.id, "side": f.side, "level_id": f.level_id, "price_usd": f.price_usd,
                   "quantity": f.quantity, "amount_eur": eur_of(f),
                   "executed_at": utc(f.executed_at).isoformat(), "note": f.note} for f in bundle.fills],
        "rule": "Le budget et les montants sont les tiens. Lexa donne des niveaux ; "
                "elle ne décide pas du montant. Aucun ordre n'est jamais passé par l'application.",
    }


def compute(bundle: Bundle, market: MarketData, *, budget_eur: float = 100.0,
            ours: dict[str, Any] | None = None, macro: list[dict[str, Any]] | None = None
            ) -> dict[str, Any]:
    a, video = bundle.analysis, bundle.video
    now = market.now()
    published = utc(a.published_at)
    processed = utc(a.processed_at)
    review_at = utc(a.review_at) or published + timedelta(days=DEFAULT_REVIEW_DAYS)
    expires_at = utc(a.expires_at) or published + timedelta(days=DEFAULT_EXPIRY_DAYS)
    price = market.price(a.asset)
    eurusd = market.eurusd()
    hourly = market.bars(a.asset, "1H", published)
    labels = _labels(bundle.levels)
    version_index = next((n for n, v in enumerate(bundle.versions, 1) if v.id == a.id), 1)
    newer = [v for v in bundle.versions if (utc(v.published_at), v.id) > (published, a.id)]

    budget = _budget(bundle, budget_eur, price, eurusd, labels)
    fills_by_level = {f.level_id for f in bundle.fills if f.side == "BUY"}
    sold_levels = {f.level_id for f in bundle.fills if f.side == "SELL"}

    # --- per level: touch, closes, distance ---------------------------------------
    levels_out: list[dict[str, Any]] = []
    evaluations: dict[int, CloseEvaluation] = {}
    market_invalidation: tuple[LexaLevelRow, CloseEvaluation] | None = None
    invalidation_touched: LexaLevelRow | None = None
    plan_amounts = {line["level_id"]: line for line in budget["entries"]}
    exit_plans = {line["level_id"]: line for line in budget["exits"]}
    for lv in bundle.levels:
        if lv.kind in ("CURRENT_PRICE",):
            continue
        value = value_of(lv)
        first, last, there_now = _touch(lv.kind, value, hourly, published, price)
        distance = (value / price - 1) * 100 if price else None
        conds = bundle.conditions.get(lv.id, [])
        cond_out = []
        for row in conds:
            cc = _close_condition(lv, row)
            entry: dict[str, Any] = {
                "type": row.condition_type, "timeframe": row.timeframe,
                "timeframe_fr": TIMEFRAME_FR.get(row.timeframe or "", None),
                "operator": row.operator, "required_closes": row.required_closes,
                "confirmation_window": row.confirmation_window,
                "description": row.description, "basis": row.basis,
                "rule": cc.describe() if cc else (row.description or "Condition non évaluable automatiquement"),
                "evaluable": cc is not None,
            }
            if cc is not None:
                bars = market.bars(a.asset, cc.timeframe, published)
                if bars is not None:
                    ev = evaluate(cc, bars, since=published, now=now, price=price)
                    evaluations[lv.id] = ev
                    entry["evaluation"] = ev.to_dict()
                    if lv.kind == "INVALIDATION" and ev.status == "CONFIRMED":
                        market_invalidation = (lv, ev)
                else:
                    entry["evaluation"] = None
            cond_out.append(entry)
        if lv.kind == "INVALIDATION" and first and not conds:
            invalidation_touched = lv

        # State shown on the card.
        ev = evaluations.get(lv.id)
        if hourly is None:
            state = ("⚪", "Non surveillé (prix indisponible)", "NOT_WATCHED")
        elif ev is not None:
            from .closes import STATUS_FR
            e, t = STATUS_FR[ev.status]
            if lv.kind == "INVALIDATION" and ev.status == "CONFIRMED":
                e, t = "❌", "Invalidation confirmée"
            state = (e, t, ev.status)
        elif lv.kind in TARGETS:
            state = (("🔴", "Objectif atteint", "TARGET_REACHED") if first
                     else ("⏳", "Pas encore atteint", "WAITING"))
        elif lv.kind in BREAKOUTS and not conds:
            state = (("🟢", "Touché — la vidéo ne précise pas la condition de confirmation", "TOUCHED")
                     if first else ("⏳", "Pas encore atteint", "WAITING"))
        elif lv.kind == "INVALIDATION":
            state = (("⚠️", "Invalidation touchée — condition non précisée", "TOUCHED")
                     if first else ("⏳", "Pas atteinte", "WAITING"))
        elif first:
            state = ("🟢", "Niveau atteint" + (" — le prix y est encore" if there_now else ""), "REACHED")
        else:
            state = ("⏳", "Pas encore atteint", "WAITING")

        arrow = "↓" if distance is not None and distance < 0 else "↑"
        purpose = {"BUY_ZONE": "avant la zone d'achat", "REINFORCEMENT": "avant l'achat renforcé",
                   "CONFIRMATION": "avant la confirmation", "BREAKOUT": "avant la cassure",
                   "INVALIDATION": "avant l'invalidation", "SUPPORT": "avant le support",
                   "RESISTANCE": "avant la résistance"}.get(lv.kind, "avant l'objectif")
        levels_out.append({
            "id": lv.id, "kind": lv.kind, "type": TYPE_OF.get(lv.kind, "OTHER"),
            "emoji": EMOJI.get(lv.kind, "📝"), "label": labels.get(lv.id, lv.label or lv.kind),
            "value": value, "original_value": lv.original_value,
            "corrected_value": lv.corrected_value,
            "corrected_at": utc(lv.corrected_at).isoformat() if lv.corrected_at else None,
            "basis": lv.basis or "EXPLICIT", "basis_fr": BASIS_FR.get(lv.basis or "EXPLICIT"),
            "to_verify": lv.confidence == "LOW",
            "lexa_allocation_pct": lv.allocation_pct,
            "timestamp_s": lv.timestamp_s, "source_text": lv.source_text,
            "distance_pct": round(distance, 2) if distance is not None else None,
            "distance_fr": (f"{arrow} {abs(distance):.1f} % {purpose}".replace(".", ",")
                            if distance is not None and not first else None),
            "first_touched_at": first.isoformat() if first else None,
            "last_touched_at": last.isoformat() if last else None,
            "reached_now": there_now, "state": {"emoji": state[0], "label": state[1], "code": state[2]},
            "conditions": cond_out,
            "user_plan": ({"amount_eur": plan_amounts[lv.id]["amount_eur"],
                           "origin": plan_amounts[lv.id]["origin"], "note": plan_amounts[lv.id]["note"]}
                          if lv.id in plan_amounts else
                          {"pct": exit_plans[lv.id]["pct"], "origin": exit_plans[lv.id]["origin"]}
                          if lv.id in exit_plans else None),
            "filled": lv.id in fills_by_level or lv.id in sold_levels,
        })

    # --- lifecycle -------------------------------------------------------------------
    targets = [lv for lv in levels_out if lv["kind"] in TARGETS]
    entries = [lv for lv in levels_out if lv["kind"] in ENTRY]
    breakouts = [lv for lv in levels_out if lv["kind"] in BREAKOUTS]
    any_triggered = any(lv["first_touched_at"] for lv in entries + targets) or any(
        evaluations.get(lv["id"]) and evaluations[lv["id"]].status == "CONFIRMED" for lv in breakouts)
    pending_close = [lv for lv in levels_out if (ev := evaluations.get(lv["id"])) is not None
                     and ev.status in ("TOUCHED_NOT_CLOSED", "CLOSED_ABOVE", "CLOSED_BELOW")
                     and lv["kind"] != "INVALIDATION"]
    near = [lv for lv in levels_out if lv["distance_pct"] is not None
            and abs(lv["distance_pct"]) <= NEAR_PCT and not lv["first_touched_at"]]

    reason_status = ""
    if newer:
        lifecycle = "SUPERSEDED"
        n = bundle.versions.index(newer[0]) + 1
        reason_status = f"Remplacée par l'analyse Lexa #{n} du {fr_day(utc(newer[0].published_at))}."
    elif a.status_override == "INVALIDATED":
        lifecycle, reason_status = "INVALIDATED", a.status_reason or "Invalidée par toi."
    elif market_invalidation is not None:
        lv, ev = market_invalidation
        lifecycle = "INVALIDATED"
        reason_status = f"{labels.get(lv.id, 'Invalidation')} {fr_price(value_of(lv))} : {ev.message}"
    elif a.status_override == "COMPLETED" or (targets and all(t["first_touched_at"] for t in targets)):
        lifecycle = "COMPLETED"
        reason_status = a.status_reason or "Tous les objectifs du scénario ont été atteints."
    elif now > expires_at:
        lifecycle = "EXPIRED"
        reason_status = (f"Analyse du {fr_day(published)} sans réévaluation depuis "
                         f"{(now - published).days} jours : ses niveaux ne sont plus suivis.")
    elif any_triggered:
        lifecycle = "TRIGGERED"
    elif pending_close or near:
        lifecycle = "WATCHING"
    else:
        lifecycle = "ACTIVE"

    # --- our own data, beside it ---------------------------------------------------------
    validation = concordance_block(a.asset, ours, None)

    # --- gates: what can hold an action back ------------------------------------------
    gates: list[dict[str, str]] = []
    for event in macro or []:
        at = datetime.fromisoformat(event["scheduled_at"])
        if event.get("importance") == "CRITICAL" and now <= at <= now + timedelta(hours=24):
            gates.append({"emoji": "📅", "text": f"{event['title']} dans "
                          f"{int((at - now).total_seconds() // 3600)} h (événement majeur)"})
    if now > review_at:
        gates.append({"emoji": "📅", "text": f"Réévaluation prévue le {fr_day(review_at)} : "
                      "l'analyse n'a pas été revue depuis."})
    if invalidation_touched is not None:
        gates.append({"emoji": "❌", "text": f"Niveau d'invalidation {fr_price(value_of(invalidation_touched))} "
                      "touché ; Lexa n'a pas précisé la condition."})

    # --- status -------------------------------------------------------------------------
    status, verdict, reason, pending = _status(
        a, lifecycle, reason_status, price, levels_out, evaluations, entries, breakouts, targets,
        near, pending_close, gates, validation, budget, now, invalidation_touched)
    emoji, label = STATUS[status]

    return {
        "analysis_id": a.id, "asset": a.asset, "version": version_index,
        "versions": [{"analysis_id": v.id, "version": n,
                      "published_at": utc(v.published_at).isoformat(), "current": v.id == a.id}
                     for n, v in enumerate(bundle.versions, 1)],
        "lifecycle": lifecycle, "lifecycle_fr": LIFECYCLE_FR[lifecycle], "lifecycle_reason": reason_status,
        "now": {"status": status, "emoji": emoji, "label": label, "tone": TONE[emoji],
                "verdict": verdict, "reason": reason, "action_pending": pending,
                "gates": gates},
        "price": {"value": price, "source": SOURCE_FR.format(asset=a.asset),
                  "at_video": a.price_at_video,
                  "move_since_video_pct": (round((price / a.price_at_video - 1) * 100, 2)
                                           if price and a.price_at_video else None)},
        "next_actions": _next_actions(levels_out, evaluations, price, budget),
        "levels": sorted(levels_out, key=_level_order),
        "rules": _rules(a.asset, levels_out, evaluations, budget),
        "why": _why(status, reason, levels_out, evaluations, gates, validation, a),
        "lexa": {
            "stance": a.stance, "summary": a.summary, "market_context": a.market_context,
            "quotes": [{"text": lv["source_text"], "timestamp_s": lv["timestamp_s"],
                        "level": lv["value"], "label": lv["label"], "basis": lv["basis"]}
                       for lv in levels_out if lv["source_text"]],
            "video": {"id": video.id, "title": video.title, "url": video.video_url or video.source_ref,
                      "published_at": published.isoformat(),
                      "timestamp_start_s": a.timestamp_start_s, "timestamp_end_s": a.timestamp_end_s},
            "analysis_added_at": processed.isoformat(), "source": "Lexa",
            "source_type": a.source_type,
        },
        "app_interpretation": _interpretation(status, reason, pending, price, levels_out, evaluations),
        "validation": validation,
        "budget": budget,
        "dates": {"published_at": published.isoformat(), "analysis_added_at": processed.isoformat(),
                  "review_at": review_at.isoformat(), "expires_at": expires_at.isoformat(),
                  "review_due": now > review_at},
        "timeline": _timeline(bundle, levels_out, evaluations, status, now),
        "calendar": _calendar(a, levels_out, evaluations, published, processed, review_at, expires_at,
                              status),
        "revision": None,
        "no_order": "Aide à la décision uniquement : aucun ordre n'est jamais passé.",
    }


def _level_order(lv: dict[str, Any]) -> tuple:
    order = ["BUY_ZONE", "REINFORCEMENT", "CONFIRMATION", "BREAKOUT", "TARGET", "TAKE_PROFIT",
             "INVALIDATION", "SUPPORT", "RESISTANCE"]
    rank = order.index(lv["kind"]) if lv["kind"] in order else len(order)
    return (rank, -lv["value"] if lv["kind"] in ENTRY else lv["value"])


def _status(a, lifecycle, reason_status, price, levels, evaluations, entries, breakouts, targets,
            near, pending_close, gates, validation, budget, now, invalidation_touched):
    asset = a.asset
    if lifecycle == "SUPERSEDED":
        return "SUPERSEDED", "PLAN REMPLACÉ", reason_status, False
    if lifecycle == "INVALIDATED":
        return "INVALIDATION", "PLAN INVALIDÉ", reason_status, False
    if lifecycle == "COMPLETED":
        return "COMPLETED", "PLAN TERMINÉ", reason_status, False
    if lifecycle == "EXPIRED":
        return "EXPIRED", "PLAN EXPIRÉ", reason_status, False
    if price is None:
        return ("NO_PRICE", "ATTENDRE",
                f"Prix de {asset} indisponible : le plan ne peut pas être situé, rien n'est déduit.",
                True)
    if invalidation_touched is not None:
        return ("INVALIDATION", "ATTENDRE",
                f"Le niveau d'invalidation {fr_price(value_of(invalidation_touched))} a été touché. "
                "Lexa n'a pas précisé la condition (clôture ?) : à toi de juger si le scénario tient.",
                True)

    # Profit-taking: a target reached recently, with something bought.
    holding = budget["quantity"] > 0 or any(lv["first_touched_at"] for lv in entries)
    fresh_targets = [t for t in targets if t["first_touched_at"] and not t["filled"]
                     and (price >= t["value"] * 0.98 or
                          now - datetime.fromisoformat(t["last_touched_at"]) <= timedelta(hours=72))]
    if fresh_targets and holding:
        t = max(fresh_targets, key=lambda x: x["value"])
        plan = t["user_plan"] or {}
        pct = plan.get("pct")
        how = (f"plan : vendre {pct:g} %" + (" (dit par Lexa)" if plan.get("origin") == "LEXA" else
                                             " (ton plan)")) if pct is not None else \
            "part à vendre non définie"
        return ("TAKE_PROFIT", "PRENDRE DES PROFITS",
                f"Objectif {t['label']} {fr_price(t['value'])} atteint — {how}.", False)

    for b in breakouts:
        ev = evaluations.get(b["id"])
        if ev and ev.status == "CONFIRMED":
            planned = (b["user_plan"] or {}).get("amount_eur")
            nxt = min((t for t in targets if not t["first_touched_at"]), key=lambda t: t["value"],
                      default=None)
            tail = f" Prochain objectif : {fr_price(nxt['value'])}." if nxt else ""
            if planned:
                return ("BULLISH_CONFIRMATION", "ACHETER",
                        f"Confirmation {fr_price(b['value'])} validée ({ev.message}){tail}", False)
            return ("BULLISH_CONFIRMATION", "ATTENDRE",
                    f"Confirmation {fr_price(b['value'])} validée : scénario haussier activé. "
                    f"Aucun achat n'est prévu sur la cassure dans le plan.{tail}", False)
    for b in pending_close:
        ev = evaluations[b["id"]]
        cd = f" Clôture dans {ev.to_dict()['countdown']} ({ev.to_dict()['next_close_paris']})." \
            if ev.seconds_to_close is not None else ""
        return ("WAIT_CLOSE", "ATTENDRE", f"{b['label']} {fr_price(b['value'])} : {ev.message}{cd}", True)

    in_zone = [e for e in entries if price <= e["value"] * (1 + IN_ZONE_PCT / 100) and not e["filled"]]
    if in_zone:
        e = min(in_zone, key=lambda x: x["value"])
        amount = (e["user_plan"] or {}).get("amount_eur")
        held_back = list(gates)
        ours = validation.get("ours") or {}
        reds = sum(1 for f in validation.get("families", []) if f["emoji"] == "🔴")
        greens = sum(1 for f in validation.get("families", []) if f["emoji"] == "🟢")
        if ours.get("action") == "SELL" or reds > greens + 1:
            held_back.append({"emoji": "🔬", "text": "nos données contredisent le plan "
                              f"(moteur : {ours.get('action')}, {reds} familles 🔴)"})
        what = f"{asset} est dans la zone « {e['label']} » ({fr_price(e['value'])})"
        if amount:
            what += f" — montant prévu {fr_eur(amount)}"
        if held_back:
            return ("BUY_ZONE_REACHED", "ATTENDRE",
                    f"{what}. 🟠 Action en attente : " + " ; ".join(g["text"] for g in held_back), True)
        return ("BUY_ZONE_REACHED", "ACHETER", f"{what}. Le scénario reste valide. "
                "À toi de décider : aucun ordre n'est passé.", False)

    for b in breakouts:
        ev = evaluations.get(b["id"])
        if ev and ev.status == "FAILED" and ev.failed_at and \
                now - ev.failed_at <= timedelta(days=3):
            return ("CONFIRMATION_MISSING", "ATTENDRE",
                    f"{b['label']} {fr_price(b['value'])} : {ev.message} Retour de l'autre côté du niveau.",
                    False)

    below = [e for e in entries if e["value"] < price and not e["first_touched_at"]]
    above = [b for b in breakouts + [lv for lv in levels if lv["kind"] == "RESISTANCE"]
             if b["value"] > price]
    if below and above:
        e, b = max(below, key=lambda x: x["value"]), min(above, key=lambda x: x["value"])
        return ("BETWEEN_LEVELS", "ATTENDRE",
                f"Le prix ({fr_price(price)}) est entre la zone d'achat ({fr_price(e['value'])}) et "
                f"la {b['label'].lower()} ({fr_price(b['value'])}). Ce n'est pas la zone d'entrée prévue "
                "dans le scénario analysé.", False)
    if near:
        n = min(near, key=lambda x: abs(x["distance_pct"]))
        return ("WATCH", "ATTENDRE", f"{n['label']} {fr_price(n['value'])} est à "
                f"{abs(n['distance_pct']):.1f} % du prix actuel.".replace(".", ",", 1), False)
    if below:
        e = max(below, key=lambda x: x["value"])
        return ("BUY_PLANNED", "ATTENDRE", f"Achat prévu plus bas : {e['label']} "
                f"{fr_price(e['value'])} ({e['distance_fr']}).", False)
    if a.stance == "SELL":
        return "SELL_PLANNED", "ATTENDRE", "Lexa prévoit une vente sur les niveaux indiqués.", False
    if a.stance == "WAIT":
        return "WAIT", "ATTENDRE", "Lexa conseille d'attendre ; aucun niveau d'action n'est proche.", False
    return "ACTIVE", "ATTENDRE", "Plan suivi : aucun niveau n'est atteint ni proche.", False


def _next_actions(levels, evaluations, price, budget) -> list[dict[str, Any]]:
    if price is None:
        return []
    out = []
    below = [lv for lv in levels if lv["kind"] in ENTRY and lv["value"] < price and not lv["filled"]]
    if below:
        e = max(below, key=lambda x: x["value"])
        out.append({"direction": "↓", "emoji": "🟢", "value": e["value"], "label": e["label"],
                    "detail": (f"{fr_eur((e['user_plan'] or {}).get('amount_eur'))} prévus"
                               if (e["user_plan"] or {}).get("amount_eur") else ""),
                    "distance_pct": e["distance_pct"]})
    pending = ("TOUCHED_NOT_CLOSED", "CLOSED_ABOVE", "CLOSED_BELOW")
    for b in (lv for lv in levels if lv["kind"] in BREAKOUTS and (
            lv["value"] > price or (evaluations.get(lv["id"]) and
                                    evaluations[lv["id"]].status in pending))):
        ev = evaluations.get(b["id"])
        cond = next((c for c in b["conditions"] if c["evaluable"]), None)
        label = f"{b['label']} (condition non précisée)"
        if cond:
            closes = f" ×{cond['required_closes']}" if cond["required_closes"] > 1 else ""
            sign = ">" if cond["operator"] == "ABOVE" else "<"
            label = f"Clôture {cond['timeframe_fr']}{closes} {sign} {fr_price(b['value'])}"
        out.append({"direction": "↑", "emoji": "⏳" if cond else "🚀", "value": b["value"],
                    "label": label,
                    "detail": ev.message if ev else "", "distance_pct": b["distance_pct"]})
        break
    tgt = [t for t in levels if t["kind"] in TARGETS and not t["first_touched_at"]]
    if tgt and not out:
        t = min(tgt, key=lambda x: x["value"])
        out.append({"direction": "↑", "emoji": "🎯", "value": t["value"], "label": t["label"],
                    "detail": "", "distance_pct": t["distance_pct"]})
    return out


def _rules(asset, levels, evaluations, budget) -> list[dict[str, Any]]:
    rules = []
    for lv in levels:
        v = fr_price(lv["value"])
        done = lv["first_touched_at"]
        ev = evaluations.get(lv["id"])
        if lv["kind"] in ENTRY:
            amount = (lv["user_plan"] or {}).get("amount_eur")
            cond = f"{asset} ≤ {v} ET scénario toujours valide ET invalidation non déclenchée"
            then = f"{lv['label'].lower()} atteint" + (f" — {fr_eur(amount)} prévus" if amount else "")
        elif lv["kind"] in BREAKOUTS:
            rule = next((c["rule"] for c in lv["conditions"] if c["evaluable"]), None)
            cond = f"{rule} ({v})" if rule else f"{asset} ≥ {v} (condition de confirmation non précisée)"
            then = "confirmation validée → scénario haussier activé" if rule else \
                "niveau touché — pas une confirmation"
            done = ev.confirmed_at.isoformat() if ev and ev.confirmed_at else (None if rule else done)
        elif lv["kind"] in TARGETS:
            pct = (lv["user_plan"] or {}).get("pct")
            cond = f"{asset} ≥ {v}"
            then = f"{lv['label']} atteint — prise de bénéfice prévue" + (f" ({pct:g} %)" if pct else "")
        elif lv["kind"] == "INVALIDATION":
            rule = next((c["rule"] for c in lv["conditions"] if c["evaluable"]), None)
            cond = f"{rule} ({v})" if rule else f"{asset} ≤ {v} (condition non précisée)"
            then = "scénario invalidé : les niveaux ne sont plus suivis"
            done = ev.confirmed_at.isoformat() if ev and ev.confirmed_at else (None if rule else done)
        else:
            continue
        rules.append({"if": cond, "then": then, "triggered_at": done,
                      "state": "✅ Déclenchée" if done else "⏳ Pas encore"})
    return rules


def _why(status, reason, levels, evaluations, gates, validation, a) -> list[dict[str, str]]:
    items = [{"emoji": STATUS[status][0], "title": STATUS[status][1], "text": reason}]
    for lv in levels:
        if lv["kind"] in (*BREAKOUTS, "RESISTANCE"):
            items.append({"emoji": "🧱", "title": f"{lv['label']} {fr_price(lv['value'])}",
                          "text": lv["distance_fr"] or lv["state"]["label"]})
            ev = evaluations.get(lv["id"])
            if ev:
                items.append({"emoji": "🕯️", "title": "Clôture", "text": ev.message})
    if a.market_context:
        items.append({"emoji": "📊", "title": "Structure (selon Lexa)", "text": a.market_context})
    entries = [lv for lv in levels if lv["kind"] in ENTRY]
    if entries:
        items.append({"emoji": "💰", "title": "Achat",
                      "text": "Zones prévues : " + " / ".join(fr_price(e["value"]) for e in entries)})
    targets = [lv for lv in levels if lv["kind"] in TARGETS]
    if targets:
        items.append({"emoji": "🎯", "title": "Si cassure validée",
                      "text": "Objectifs : " + " / ".join(fr_price(t["value"]) for t in targets)})
    for inv in (lv for lv in levels if lv["kind"] == "INVALIDATION"):
        items.append({"emoji": "❌", "title": "Invalidation", "text": f"{fr_price(inv['value'])} — "
                      + next((c["rule"] for c in inv["conditions"]), "condition non précisée")})
    for g in gates:
        items.append({"emoji": g["emoji"], "title": "Condition manquante", "text": g["text"]})
    items.append({"emoji": "🔬", "title": "Nos données", "text": validation.get("explanation", "")})
    return items


def _interpretation(status, reason, pending, price, levels, evaluations) -> dict[str, Any]:
    lines = []
    for lv in levels:
        ev = evaluations.get(lv["id"])
        if ev and ev.status in ("TOUCHED_NOT_CLOSED", "CLOSED_ABOVE", "CLOSED_BELOW", "FAILED") \
                and ev.message not in reason:
            lines.append(f"{lv['label']} {fr_price(lv['value'])} : {ev.message}")
    return {"status": STATUS[status][1], "text": reason, "details": lines,
            "action_pending": pending,
            "note": "Lecture de l'application à partir des prix — pas une citation de Lexa."}


def _timeline(bundle, levels, evaluations, status, now) -> list[dict[str, Any]]:
    a = bundle.analysis
    items: list[tuple[datetime, str, str]] = [
        (utc(a.published_at), "🎬", "Vidéo publiée"),
        (utc(a.processed_at), "📝", "Analyse ajoutée"),
    ]
    for lv in levels:
        ev = evaluations.get(lv["id"])
        if ev is not None:
            for h in ev.to_dict()["history"]:
                emoji = {"TOUCHED": "📍", "CLOSED_BEYOND": "🕯️", "CONFIRMED": "🚀",
                         "FAILED": "❌", "RETURNED": "🟠"}.get(h["event"], "•")
                items.append((datetime.fromisoformat(h["at"]), emoji,
                              f"{fr_price(lv['value'])} — {h['text']}"))
        elif lv["first_touched_at"]:
            text = ("Objectif atteint" if lv["kind"] in TARGETS else "touché")
            items.append((datetime.fromisoformat(lv["first_touched_at"]),
                          "🎯" if lv["kind"] in TARGETS else "📍",
                          f"{fr_price(lv['value'])} {lv['label'].lower()} — {text}"))
    for f in bundle.fills:
        items.append((utc(f.executed_at), "💶",
                      f"{'Achat' if f.side == 'BUY' else 'Vente'} enregistré : "
                      f"{f.quantity:g} à {fr_price(f.price_usd)}"))
    for e in bundle.events:
        items.append((utc(e.triggered_at or e.scheduled_at), "🔄", e.description))
    items.sort(key=lambda x: x[0])
    out, last = [], None
    for at, emoji, text in items:
        if (emoji, text) == last:
            continue
        last = (emoji, text)
        out.append({"at": at.isoformat(), "emoji": emoji, "text": text})
    out = out[-30:]
    e, label = STATUS[status]
    out.append({"at": now.isoformat(), "emoji": e, "text": f"Maintenant — {label}", "now": True})
    return out


def _calendar(a, levels, evaluations, published, processed, review_at, expires_at, status):
    items = [
        {"at": published.isoformat(), "kind": "VIDEO", "emoji": "🎬", "title": "Vidéo publiée",
         "category": "INFO"},
        {"at": processed.isoformat(), "kind": "ANALYSIS", "emoji": "📝", "title": "Analyse ajoutée",
         "category": "INFO"},
        {"at": review_at.isoformat(), "kind": "REVIEW", "emoji": "📅",
         "title": "Réévaluation du scénario", "category": "INFO"},
        {"at": expires_at.isoformat(), "kind": "EXPIRY", "emoji": "⌛",
         "title": "Fin de validité du scénario", "category": "INFO"},
    ]
    seen = set()
    for lv in levels:
        ev = evaluations.get(lv["id"])
        if ev is None:
            if lv["first_touched_at"]:
                items.append({"at": lv["first_touched_at"], "kind": "TRIGGERED",
                              "emoji": "🎯" if lv["kind"] in TARGETS else "📍",
                              "title": f"{lv['label']} atteint", "level": lv["value"],
                              "category": "TARGET" if lv["kind"] in TARGETS else
                              "BUY" if lv["kind"] in ENTRY else "INFO"})
            continue
        d = ev.to_dict()
        close_pending = ev.status in ("TOUCHED_NOT_CLOSED", "CLOSED_ABOVE", "CLOSED_BELOW") or (
            ev.status == "WAITING" and lv["distance_pct"] is not None and abs(lv["distance_pct"]) <= 2)
        if close_pending and ev.next_close_at and (lv["value"], d["next_close_at"]) not in seen:
            seen.add((lv["value"], d["next_close_at"]))
            items.append({"at": d["next_close_at"], "kind": "CLOSE_DUE", "emoji": "🕯️",
                          "title": f"Attendre clôture {TIMEFRAME_FR.get(_tf(lv), '')}".strip(),
                          "level": lv["value"], "detail": d["next_close_paris"], "category": "CLOSE"})
        for key, emoji, title in (("confirmed_at", "🚀", "Confirmation validée"),
                                  ("failed_at", "❌", "Clôture non confirmée")):
            if d[key]:
                items.append({"at": d[key], "kind": "TRIGGERED", "emoji": emoji, "title": title,
                              "level": lv["value"], "category": "CLOSE"})
    return items


def _tf(level: dict[str, Any]) -> str:
    return next((c["timeframe"] for c in level["conditions"] if c["timeframe"]), "")


# --- our engine, beside Lexa ------------------------------------------------------------

FAMILY_FR = [("technical", "Technique"), ("flows", "Flux spot"), ("derivatives", "Dérivés"),
             ("etf", "ETF"), ("macro", "Macro"), ("cycle", "Cycle")]
TONE_EMOJI = {"GREEN": "🟢", "ORANGE": "🟠", "RED": "🔴"}


def concordance_block(asset: str, ours: dict[str, Any] | None, lexa_bias: str | None) -> dict[str, Any]:
    """Our reading next to Lexa's. Described, never a probability."""

    if not ours:
        return {"available": False, "level": "INSUFFICIENT", "emoji": "⚪",
                "label": "Données insuffisantes",
                "explanation": f"L'application n'analyse pas {asset} : aucune validation par nos données.",
                "families": [], "ours": None}
    fams = []
    by_family = {f.get("family"): f for f in ours.get("home_families") or []}
    for key, name in FAMILY_FR:
        if key == "etf":
            etf = ours.get("etf")
            if etf is None:
                fams.append({"family": key, "name": name, "emoji": "⚪", "status": "Données insuffisantes"})
            else:
                fams.append({"family": key, "name": name, **etf})
            continue
        f = by_family.get(key)
        if f is None:
            fams.append({"family": key, "name": name, "emoji": "⚪", "status": "Données insuffisantes"})
        else:
            fams.append({"family": key, "name": name,
                         "emoji": TONE_EMOJI.get(f.get("tone"), "⚪"),
                         "status": f.get("status") or "", "key_info": f.get("key_info") or ""})
    return {"available": True, "families": fams, "ours": {
        "action": ours.get("action"), "sentence": ours.get("sentence"), "horizon": "7 jours"}}


def finish_concordance(plan: dict[str, Any]) -> None:
    """Compare the plan's status with our engine's decision. Descriptive only."""

    v = plan["validation"]
    if not v.get("available"):
        return
    ours = v["ours"]["action"]
    verdict = plan["now"]["verdict"]
    bias = ("BULL" if plan["now"]["status"] in ("BUY_ZONE_REACHED", "BULLISH_CONFIRMATION",
                                                "BUY_PLANNED") else
            "BEAR" if plan["now"]["status"] in ("SELL_PLANNED", "INVALIDATION") else "WAIT")
    engine = {"BUY": "BULL", "SELL": "BEAR"}.get(ours, "WAIT")
    greens = sum(1 for f in v["families"] if f["emoji"] == "🟢")
    reds = sum(1 for f in v["families"] if f["emoji"] == "🔴")
    ours_fr = {"BUY": "ACHETER", "SELL": "VENDRE", "WAIT": "ATTENDRE"}.get(ours, ours or "—")
    if bias == engine and (bias != "BULL" or greens >= reds):
        level, emoji, label = "STRONG", "🟢", "Forte"
    elif {bias, engine} == {"BULL", "BEAR"} or (bias == "BULL" and reds > greens + 1):
        level, emoji, label = "WEAK", "🔴", "Faible"
    else:
        level, emoji, label = "PARTIAL", "🟠", "Partielle"
    explanation = (f"Plan Lexa : {plan['now']['label'].lower()} ({verdict}). "
                   f"Notre moteur (7 j) : {ours_fr}. Familles : {greens} 🟢, {reds} 🔴.")
    if v["ours"].get("sentence"):
        explanation += f" {v['ours']['sentence']}"
    v.update({"level": level, "emoji": emoji, "label": label, "explanation": explanation,
              "divergence": verdict == "ACHETER" and ours != "BUY"})

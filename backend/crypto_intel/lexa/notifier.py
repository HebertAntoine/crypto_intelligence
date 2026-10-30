"""Lexa notifications: say what changed, once.

Same discipline as the app's AlertEngine (engines/alerts.py), stored in the
Lexa database because the content is private:

  * dedup_key - « the same notification ». Keys carry the crypto and the LEVEL,
    not the analysis: two videos on the same level give one notification.
    Close-related keys carry the candle, so each close is its own event.
  * cooldown - a key stays silent this long after firing.
  * cap - at most MAX_PER_ASSET_PER_DAY per crypto, most important first.
  * only plans still followed (not expired, replaced, invalidated or done),
    and only facts that happened after the analysis was added: importing an
    old video never fires « vient de toucher » for last week's candle.

Delivery goes through sinks. In-app is the one wired today; a push sink plugs
in without touching the rules.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from sqlalchemy import func, select, update

from ..logging_setup import get_logger
from .market import MarketData, default_market
from .plans import BREAKOUTS, ENTRY, TARGETS, fr_price
from .store import LexaNotificationRow, lexa_session

log = get_logger(__name__)

APPROACH_PCT = 1.5
MAX_PER_ASSET_PER_DAY = 8
COOLDOWN = {  # minutes
    "APPROACH": 24 * 60, "TOUCHED": 30 * 24 * 60, "CLOSE_SOON": 10 ** 7,
    "CLOSED_BEYOND": 10 ** 7, "CONFIRMATION_MISSING": 10 ** 7, "CONFIRMED": 10 ** 7,
    "TARGET": 10 ** 7, "PLAN_UPDATED": 10 ** 7, "INVALIDATED": 10 ** 7, "EXPIRED": 10 ** 7,
}
PRIORITY = ["INVALIDATED", "PLAN_UPDATED", "CONFIRMED", "TARGET", "CLOSED_BEYOND",
            "CONFIRMATION_MISSING", "TOUCHED", "CLOSE_SOON", "APPROACH", "EXPIRED"]
FOLLOWED = {"ACTIVE", "WATCHING", "TRIGGERED"}


class NotificationSink(Protocol):
    def send(self, asset: str, kind: str, message: str, key: str,
             analysis_id: int | None, *, now: datetime,
             source_snapshot: dict[str, Any]) -> bool: ...


class InAppSink:
    def send(self, asset: str, kind: str, message: str, key: str,
             analysis_id: int | None, *, now: datetime,
             source_snapshot: dict[str, Any]) -> bool:
        """Atomically reserve and persist one in-app delivery.

        A deferred SQLite transaction permits two workers to both observe that
        a key is absent. ``BEGIN IMMEDIATE`` serializes that small check/insert
        window, so the second worker sees the first worker's committed row.
        """

        delivered_at = datetime.now(UTC)
        with lexa_session(immediate=True) as s:
            if _fired_within(s, key, COOLDOWN[kind], now):
                return False
            delivered_today = s.execute(
                select(func.count()).select_from(LexaNotificationRow).where(
                    LexaNotificationRow.asset == asset,
                    LexaNotificationRow.created_at >= now - timedelta(days=1),
                )
            ).scalar_one()
            if delivered_today >= MAX_PER_ASSET_PER_DAY:
                log.info("lexa_notification_capped", asset=asset, kind=kind)
                return False
            s.add(LexaNotificationRow(
                dedup_key=key,
                asset=asset,
                kind=kind,
                message=message,
                analysis_id=analysis_id,
                created_at=now,
                delivered_at=delivered_at,
                delivery_status="DELIVERED",
                reason="Persistée dans la boîte de réception interne Lexa.",
                source_snapshot=source_snapshot,
            ))
        return True


SINKS: list[NotificationSink] = [InAppSink()]


def _after(moment: str | None, since: datetime) -> bool:
    return moment is not None and datetime.fromisoformat(moment) >= since


def candidates(plan: dict[str, Any], now: datetime) -> list[tuple[str, str, str]]:
    """(kind, key, message) for one plan. Pure: same plan, same list."""

    asset, out = plan["asset"], []
    added = datetime.fromisoformat(plan["lexa"]["analysis_added_at"])
    if plan["revision"] and plan["revision"]["relation"] != "CONFIRMS":
        out.append(("PLAN_UPDATED", f"updated:{plan['analysis_id']}",
                    f"🔔 Une nouvelle analyse Lexa modifie le plan {asset} "
                    f"({plan['revision']['label']})."))
    if plan["lifecycle"] == "INVALIDATED":
        out.append(("INVALIDATED", f"invalid:{plan['analysis_id']}",
                    f"🔔 Plan {asset} invalidé : {plan['lifecycle_reason']}"))
    if plan["lifecycle"] not in FOLLOWED:
        return out
    for lv in plan["levels"]:
        v, value = fr_price(lv["value"]), f"{lv['value']:g}"
        group = ("entry" if lv["kind"] in ENTRY else "target" if lv["kind"] in TARGETS else
                 "breakout" if lv["kind"] in BREAKOUTS else lv["kind"].lower())
        if lv["first_touched_at"] is None and lv["distance_pct"] is not None and \
                abs(lv["distance_pct"]) <= APPROACH_PCT and lv["kind"] != "INVALIDATION":
            out.append(("APPROACH", f"approach:{asset}:{group}:{value}",
                        f"🔔 {asset} approche de {v} ({lv['label']})"))
        if lv["kind"] in TARGETS and _after(lv["first_touched_at"], added):
            out.append(("TARGET", f"target:{asset}:{value}",
                        f"🔔 Objectif {v} atteint ({asset} {lv['label']})"))
        elif lv["kind"] in ENTRY and _after(lv["first_touched_at"], added):
            out.append(("TOUCHED", f"touch:{asset}:{group}:{value}",
                        f"🔔 {asset} vient de toucher {v} ({lv['label']})"))
        for cond in lv["conditions"]:
            ev = cond.get("evaluation")
            if not ev:
                continue
            tf = cond.get("timeframe_fr") or ""
            if ev["status"] == "TOUCHED_NOT_CLOSED" and ev["next_close_at"] and \
                    datetime.fromisoformat(ev["next_close_at"]) - now <= timedelta(hours=1):
                out.append(("CLOSE_SOON", f"close_soon:{asset}:{value}:{ev['next_close_at']}",
                            f"🔔 Clôture {tf} {asset} dans {ev['countdown']} — niveau {v}"))
            if _after(ev["closed_beyond_at"], added) and ev["status"] in (
                    "CLOSED_ABOVE", "CLOSED_BELOW", "CONFIRMED"):
                side = "au-dessus" if cond["operator"] == "ABOVE" else "en dessous"
                out.append(("CLOSED_BEYOND", f"closed:{asset}:{value}:{ev['closed_beyond_at']}",
                            f"🔔 {asset} clôture {side} de {v} ({tf})"))
            if _after(ev["confirmed_at"], added) and lv["kind"] in BREAKOUTS:
                out.append(("CONFIRMED", f"confirmed:{asset}:{value}",
                            f"🔔 Confirmation {asset} {v} validée"))
            if ev["status"] == "FAILED" and _after(ev["failed_at"], added):
                out.append(("CONFIRMATION_MISSING", f"failed:{asset}:{value}:{ev['failed_at']}",
                            f"🔔 Confirmation toujours manquante : {asset} n'a pas clôturé "
                            f"au-delà de {v} ({tf})"))
    return out


def _fired_within(s, key: str, minutes: int, now: datetime) -> bool:
    row = s.execute(select(LexaNotificationRow.created_at).where(
        LexaNotificationRow.dedup_key == key).order_by(
        LexaNotificationRow.created_at.desc())).first()
    if row is None:
        return False
    last = row[0] if row[0].tzinfo else row[0].replace(tzinfo=UTC)
    return now - last < timedelta(minutes=minutes)


def _source_snapshot(plan: dict[str, Any], kind: str, key: str,
                     now: datetime) -> dict[str, Any]:
    """Capture only the market facts that were available for this trigger."""

    price = plan.get("price") or {}
    snapshot: dict[str, Any] = {
        "trigger_id": key,
        "kind": kind,
        "asset_id": plan["asset"],
        "analysis_id": plan.get("analysis_id"),
        "evaluated_at": now.isoformat(),
        "current_price": price.get("value"),
        "price_source": price.get("source"),
    }
    parts = key.split(":")
    level = next(
        (lv for lv in plan.get("levels", []) if f"{lv.get('value'):g}" in parts),
        None,
    )
    if level is None and kind == "INVALIDATED":
        level = next(
            (lv for lv in plan.get("levels", []) if lv.get("kind") == "INVALIDATION"),
            None,
        )
    if level is None:
        return snapshot

    snapshot.update({
        "level_id": level.get("id"),
        "level_kind": level.get("kind"),
        "level_label": level.get("label"),
        "level_value": level.get("value"),
        "level_high": level.get("value_high"),
        "level_unit": level.get("unit"),
        "distance_pct": level.get("distance_pct"),
        "first_touched_at": level.get("first_touched_at"),
        "reached_now": level.get("reached_now"),
    })
    event_field = {
        "CLOSE_SOON": "next_close_at",
        "CLOSED_BEYOND": "closed_beyond_at",
        "CONFIRMED": "confirmed_at",
        "CONFIRMATION_MISSING": "failed_at",
    }.get(kind)
    for condition in level.get("conditions") or []:
        evaluation = condition.get("evaluation") or {}
        if event_field is not None and not evaluation.get(event_field):
            continue
        snapshot["condition"] = {
            "type": condition.get("type"),
            "timeframe": condition.get("timeframe"),
            "operator": condition.get("operator"),
            "required_closes": condition.get("required_closes"),
            "evaluation_status": evaluation.get("status"),
            "event_at": evaluation.get(event_field) if event_field else None,
            "next_close_at": evaluation.get("next_close_at"),
        }
        break
    return snapshot


def dispatch(plan: dict[str, Any], now: datetime) -> list[str]:
    """Send what is new for one plan. Returns the messages sent."""

    sent: list[str] = []
    todo = sorted(candidates(plan, now), key=lambda c: PRIORITY.index(c[0]))
    for kind, key, message in todo:
        delivered = False
        snapshot = _source_snapshot(plan, kind, key, now)
        for sink in SINKS:
            delivered = sink.send(
                plan["asset"], kind, message, key, plan["analysis_id"],
                now=now, source_snapshot=snapshot,
            ) or delivered
        if delivered:
            sent.append(message)
    return sent


def evaluate_all(market: MarketData | None = None) -> list[str]:
    """The periodic job: every followed plan, once."""

    from .service import current_ids, plan_for

    market = market or default_market()
    now = market.now()
    sent: list[str] = []
    for analysis_id in current_ids().values():
        plan = plan_for(analysis_id, market, with_chart=False)
        if plan is not None:
            sent += dispatch(plan, now)
    return sent


def listing(limit: int = 100) -> list[dict[str, Any]]:
    with lexa_session() as s:
        rows = s.execute(select(LexaNotificationRow).order_by(
            LexaNotificationRow.created_at.desc()).limit(limit)).scalars().all()
        return [{
            "id": r.id,
            "notification_id": r.id,
            "trigger_id": r.dedup_key,
            "asset": r.asset,
            "asset_id": r.asset,
            "kind": r.kind,
            "message": r.message,
            "analysis_id": r.analysis_id,
            "created_at": (
                r.created_at if r.created_at.tzinfo else r.created_at.replace(tzinfo=UTC)
            ).isoformat(),
            "delivered_at": (
                (r.delivered_at if r.delivered_at.tzinfo else r.delivered_at.replace(tzinfo=UTC))
                .isoformat()
                if r.delivered_at is not None
                else None
            ),
            "delivery_status": r.delivery_status or "UNKNOWN",
            "reason": r.reason or "",
            "source_snapshot": r.source_snapshot or {},
            "read": r.read_at is not None,
        } for r in rows]


def unread_count() -> int:
    with lexa_session() as s:
        return s.execute(select(func.count()).select_from(LexaNotificationRow).where(
            LexaNotificationRow.read_at.is_(None))).scalar_one()


def mark_read() -> None:
    with lexa_session() as s:
        s.execute(update(LexaNotificationRow).where(LexaNotificationRow.read_at.is_(None))
                  .values(read_at=datetime.now(UTC)))

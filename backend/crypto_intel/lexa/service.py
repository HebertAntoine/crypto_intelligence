"""The Lexa tab: current plan per crypto, the « à suivre » list, the calendar,
the history of versions, and the revision between two videos.

Any number of cryptos: nothing here is limited to BTC / ETH / SOL. Our own
engine is consulted only for the assets it covers, and only to be shown beside
Lexa - it never reads Lexa, and Lexa never feeds it (its output is exported
publicly; Lexa content must stay on this machine).
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from ..logging_setup import get_logger
from . import plans
from .market import PARIS, MarketData, default_market
from .repository import get_capital
from .store import LexaAnalysisRow, LexaLevelRow, LexaPlanEventRow, lexa_session

log = get_logger(__name__)
OUR_ASSETS = {"BTC", "ETH", "SOL"}
_OURS_CACHE: dict[str, tuple[float, dict[str, Any] | None]] = {}
_MACRO_CACHE: dict[str, tuple[float, list[dict[str, Any]]]] = {}

BUCKETS = [("TODAY", "AUJOURD'HUI"), ("TOMORROW", "DEMAIN"), ("THIS_WEEK", "CETTE SEMAINE"),
           ("LATER", "PLUS TARD"), ("PAST", "PASSÉ")]


def our_reading(asset: str) -> dict[str, Any] | None:
    """Our engine's 7-day reading, for the assets it covers. Cached 5 minutes."""

    if asset not in OUR_ASSETS:
        return None
    hit = _OURS_CACHE.get(asset)
    if hit and time.time() - hit[0] < 300:
        return hit[1]
    value = None
    try:
        from ..api.routes_future import future_decision

        decision = future_decision(asset, "7d")
        summary = (decision.get("analysis") or {}).get("summary") or {}
        etf = None
        for factor in ((decision.get("families") or {}).get("factors") or []):
            if factor.get("name") == "Flux ETF":
                emoji = {"POSITIVE": "🟢", "NEGATIVE": "🔴", "NEUTRAL": "🟠"}.get(
                    factor.get("direction"), "⚪")
                stale = factor.get("availability") in ("STALE", "UNAVAILABLE")
                etf = {"emoji": emoji, "status": "Flux ETF" + (" (données anciennes)" if stale else ""),
                       "key_info": (factor.get("causal_chain") or [""])[0]}
        value = {"action": decision.get("decision"), "sentence": summary.get("sentence"),
                 "home_families": summary.get("home_families") or [], "etf": etf}
    except Exception as exc:  # our engine unavailable: say so, never guess
        log.warning("lexa_ours_unavailable", asset=asset, error=str(exc))
    _OURS_CACHE[asset] = (time.time(), value)
    return value


def macro_events(days: int = 14) -> list[dict[str, Any]]:
    """Market-wide dated events from the app's own calendar (« À surveiller »)."""

    hit = _MACRO_CACHE.get("m")
    if hit and time.time() - hit[0] < 600:
        return hit[1]
    events: list[dict[str, Any]] = []
    try:
        from ..api.routes_future import future_timeline

        for e in future_timeline("BTC", days=days)["events"]:
            if e.get("scheduled_at") and e.get("importance") in ("CRITICAL", "HIGH"):
                events.append({"title": e["title"], "scheduled_at": e["scheduled_at"],
                               "importance": e["importance"], "event_type": e["event_type"]})
    except Exception as exc:
        log.warning("lexa_macro_unavailable", error=str(exc))
    _MACRO_CACHE["m"] = (time.time(), events)
    return events


def _analyses() -> list[LexaAnalysisRow]:
    with lexa_session() as s:
        return list(s.execute(select(LexaAnalysisRow).order_by(
            LexaAnalysisRow.published_at, LexaAnalysisRow.id)).scalars())


def current_ids() -> dict[str, int]:
    """The latest analysis of each crypto: the one the tab follows."""

    out: dict[str, int] = {}
    for a in _analyses():
        out[a.asset] = a.id
    return out


def plan_for(analysis_id: int, market: MarketData | None = None, *,
             with_ours: bool = True) -> dict[str, Any] | None:
    market = market or default_market()
    bundle = plans.load(analysis_id)
    if bundle is None:
        return None
    asset = bundle.analysis.asset
    plan = plans.compute(bundle, market, budget_eur=get_capital(asset),
                         ours=our_reading(asset) if with_ours else None,
                         macro=macro_events())
    plans.finish_concordance(plan)
    plan["revision"] = revision(bundle)
    return plan


def revision(bundle: plans.Bundle) -> dict[str, Any] | None:
    """What changed from the previous version of this crypto's plan."""

    ids = [v.id for v in bundle.versions]
    index = ids.index(bundle.analysis.id)
    if index == 0:
        return None
    previous = bundle.versions[index - 1]
    with lexa_session() as s:
        old_levels = list(s.execute(select(LexaLevelRow).where(
            LexaLevelRow.analysis_id == previous.id)).scalars())
    diff = plans.compare_versions(previous, old_levels, bundle.analysis, bundle.levels)
    return {**diff, "label": plans.RELATION_FR[diff["relation"]],
            "previous_analysis_id": previous.id, "previous_version": index,
            "previous_published_at": plans.utc(previous.published_at).isoformat()}


def _bucket(moment: datetime, now: datetime) -> str:
    day, today = moment.astimezone(PARIS).date(), now.astimezone(PARIS).date()
    if day < today:
        return "PAST"
    if day == today:
        return "TODAY"
    if day == today + timedelta(days=1):
        return "TOMORROW"
    if day <= today + timedelta(days=7):
        return "THIS_WEEK"
    return "LATER"


def _follow_row(plan: dict[str, Any], now: datetime) -> dict[str, Any]:
    """One line of « À suivre »: date, status, crypto, the level that matters."""

    status = plan["now"]["status"]
    close = next((c for c in plan["calendar"] if c["kind"] == "CLOSE_DUE"), None)
    moment = (datetime.fromisoformat(close["at"]) if close and status == "WAIT_CLOSE" else now)
    key_level = None
    if plan["next_actions"]:
        # A close to wait for is about the level above; otherwise the nearest action.
        ups = [a for a in plan["next_actions"] if a["direction"] == "↑"]
        n = ups[0] if ups and status in ("WAIT_CLOSE", "CONFIRMATION_MISSING") else plan["next_actions"][0]
        key_level = f"{'Niveau surveillé' if n['direction'] == '↑' else 'Zone'} : {plans.fr_price(n['value'])}"
    entries = [lv for lv in plan["levels"] if lv["kind"] in plans.ENTRY]
    if status in ("BUY_PLANNED", "BETWEEN_LEVELS") and entries:
        key_level = "Achat : " + " / ".join(plans.fr_price(e["value"]) for e in entries)
    category = ("CLOSE" if status in ("WAIT_CLOSE", "CONFIRMATION_MISSING") else
                "BUY" if status in ("BUY_PLANNED", "BUY_ZONE_REACHED", "BULLISH_CONFIRMATION") else
                "TARGET" if status == "TAKE_PROFIT" else
                "SELL" if status in ("SELL_PLANNED",) else "INFO")
    return {"asset": plan["asset"], "analysis_id": plan["analysis_id"], "at": moment.isoformat(),
            "bucket": _bucket(moment, now), "emoji": plan["now"]["emoji"],
            "status": status, "label": plan["now"]["label"], "verdict": plan["now"]["verdict"],
            "headline": plan["now"]["reason"], "key_level": key_level,
            "countdown": (close or {}).get("detail") if status == "WAIT_CLOSE" else None,
            "category": category, "lifecycle": plan["lifecycle"]}


def _card(plan: dict[str, Any]) -> dict[str, Any]:
    by_kind = lambda kinds: [lv["value"] for lv in plan["levels"] if lv["kind"] in kinds]  # noqa: E731
    pending_close = next((lv for lv in plan["levels"]
                          for c in lv["conditions"]
                          if c.get("evaluation") and c["evaluation"]["status"] in
                          ("TOUCHED_NOT_CLOSED", "CLOSED_ABOVE", "CLOSED_BELOW")), None)
    close_rule = next((c["rule"] for lv in plan["levels"] if lv["kind"] in plans.BREAKOUTS
                       for c in lv["conditions"] if c["evaluable"]), None)
    return {
        "asset": plan["asset"], "analysis_id": plan["analysis_id"], "version": plan["version"],
        "now": plan["now"], "price": plan["price"]["value"],
        "buy": by_kind(plans.ENTRY), "confirmation": by_kind(plans.BREAKOUTS),
        "targets": by_kind(plans.TARGETS)[:1] and sorted(by_kind(plans.TARGETS))[:1],
        "invalidation": by_kind(("INVALIDATION",)),
        "waiting_close": (close_rule if pending_close else None),
        "updated_at": plan["lexa"]["analysis_added_at"], "lifecycle": plan["lifecycle"],
        "lifecycle_fr": plan["lifecycle_fr"], "revision": (plan["revision"] or {}).get("label"),
        "concordance": {k: plan["validation"].get(k) for k in ("emoji", "label", "level")},
    }


def overview(market: MarketData | None = None) -> dict[str, Any]:
    market = market or default_market()
    now = market.now()
    follow, cards = [], []
    for _asset, analysis_id in sorted(current_ids().items()):
        plan = plan_for(analysis_id, market)
        if plan is None:
            continue
        cards.append(_card(plan))
        if plan["lifecycle"] not in ("EXPIRED", "SUPERSEDED"):
            follow.append(_follow_row(plan, now))
    follow.sort(key=lambda r: (r["at"], r["asset"]))
    from .notifier import unread_count

    return {"follow": follow, "plans": cards, "assets": sorted(current_ids()),
            "buckets": [{"key": k, "label": v} for k, v in BUCKETS],
            "unread_notifications": unread_count(), "as_of": now.isoformat(),
            "rule": "Lexa est une source externe : ces plans ne modifient jamais "
                    "ACHETER / ATTENDRE / VENDRE du moteur principal."}


def calendar(market: MarketData | None = None) -> dict[str, Any]:
    market = market or default_market()
    now = market.now()
    items: list[dict[str, Any]] = []
    for asset, analysis_id in sorted(current_ids().items()):
        plan = plan_for(analysis_id, market)
        if plan is None:
            continue
        for item in plan["calendar"]:
            items.append({**item, "asset": asset, "analysis_id": analysis_id})
    for e in macro_events():
        items.append({"at": e["scheduled_at"], "kind": "MARKET_EVENT", "emoji": "📅",
                      "title": e["title"], "asset": "MARCHÉ", "category": "INFO",
                      "detail": "Événement de marché (calendrier de l'application)"})
    seen, out = set(), []
    for item in sorted(items, key=lambda i: i["at"]):
        key = (item["asset"], item["kind"], item.get("level"), item["at"][:16])
        if key in seen:
            continue
        seen.add(key)
        item["bucket"] = _bucket(datetime.fromisoformat(item["at"]), now)
        out.append(item)
    return {"items": out, "buckets": [{"key": k, "label": v} for k, v in BUCKETS],
            "timezone": "Europe/Paris", "as_of": now.isoformat()}


def history(asset: str | None = None, market: MarketData | None = None) -> dict[str, Any]:
    market = market or default_market()
    rows = [a for a in _analyses() if asset is None or a.asset == asset.upper()]
    out = []
    for a in reversed(rows):
        plan = plan_for(a.id, market, with_ours=False)
        if plan is None:
            continue
        out.append({"analysis_id": a.id, "asset": a.asset, "version": plan["version"],
                    "published_at": plan["dates"]["published_at"],
                    "video_title": plan["lexa"]["video"]["title"],
                    "lifecycle": plan["lifecycle"], "lifecycle_fr": plan["lifecycle_fr"],
                    "lifecycle_reason": plan["lifecycle_reason"], "now": plan["now"],
                    "revision": plan["revision"]})
    return {"analyses": out}


def record_supersession(new_ids: list[int]) -> None:
    """When a new video lands, the previous plan of the same crypto is marked."""

    with lexa_session() as s:
        for new_id in new_ids:
            new = s.get(LexaAnalysisRow, new_id)
            older = s.execute(select(LexaAnalysisRow).where(
                LexaAnalysisRow.asset == new.asset, LexaAnalysisRow.id != new.id).order_by(
                LexaAnalysisRow.published_at.desc())).scalars().first()
            if older is None or plans.utc(older.published_at) > plans.utc(new.published_at):
                continue
            key = f"superseded:{older.id}:{new.id}"
            if s.execute(select(LexaPlanEventRow).where(LexaPlanEventRow.dedup_key == key)).first():
                continue
            s.add(LexaPlanEventRow(
                analysis_id=older.id, asset=new.asset, event_type="SUPERSEDED",
                triggered_at=datetime.now(UTC), status="TRIGGERED", dedup_key=key,
                description=f"Remplacée par une nouvelle analyse Lexa ({plans.fr_day(plans.utc(new.published_at))})"))

"""Lexa plans: statuses, closes, versions, budget, notifications, calendar.

The levels are FICTIONAL (the shape of a real plan, not its values): no
Lexa content is committed to this public repository. The market is
scripted hour by hour so every close is known exactly.

The ten mandatory cases of the brief are marked [1] … [10].
"""

from datetime import UTC, datetime, timedelta

import pytest

from crypto_intel.lexa import notifier, plans, service
from crypto_intel.lexa.closes import CloseCondition, evaluate
from crypto_intel.lexa.market import Bar, bar_start, next_close, paris
from crypto_intel.lexa.repository import (
    AssetInput,
    ConditionInput,
    LevelInput,
    add_fill,
    create_video,
    set_user_plan,
)

PUBLISHED = datetime(2026, 9, 18, 8, tzinfo=UTC)


class FakeMarket:
    """Hourly path -> 1h / 4h / 1d / 1w Binance-aligned candles, up to `now`."""

    def __init__(self, path, now, start=PUBLISHED - timedelta(hours=8), eurusd=1.87):
        self.path, self._now, self.start, self._eurusd = path, now, start, eurusd
        self.price_value = path[-1][2] if path else None

    def now(self):
        return self._now

    def eurusd(self):
        return self._eurusd

    def price(self, asset):
        return self.price_value

    def _hourly(self):
        out = []
        for i, (high, low, close) in enumerate(self.path):
            opened = self.start + timedelta(hours=i)
            if opened > self._now:
                break
            out.append(Bar(opened, opened + timedelta(hours=1), close, high, low, close,
                           closed=opened + timedelta(hours=1) <= self._now))
        return out

    def bars(self, asset, timeframe, since):
        hourly = self._hourly()
        if timeframe == "1H":
            return hourly
        size = {"4H": timedelta(hours=4), "1D": timedelta(days=1), "1W": timedelta(weeks=1)}[timeframe]
        groups = {}
        for bar in hourly:
            groups.setdefault(bar_start(bar.open_time, timeframe), []).append(bar)
        return [Bar(k, k + size, g[0].open, max(b.high for b in g), min(b.low for b in g),
                    g[-1].close, closed=k + size <= self._now) for k, g in sorted(groups.items())]


def flat(price, hours):
    return [(price * 1.001, price * 0.999, price)] * hours


@pytest.fixture(autouse=True)
def lexa_db(tmp_path, monkeypatch):
    monkeypatch.setenv("LEXA_DATABASE_PATH", str(tmp_path / "lexa" / "lexa.db"))
    from crypto_intel.lexa import store

    store.reset_engine()
    monkeypatch.setattr(service, "our_reading", lambda asset: None)
    monkeypatch.setattr(service, "macro_events", lambda days=14: [])
    yield
    store.reset_engine()


def xrp_levels(buy=2.15696, stance="WAIT", required=1, window=None, confirm_tf="1D"):
    close = [ConditionInput("CLOSE", confirm_tf, "ABOVE", required, window,
                            "Attendre une clôture journalière au-dessus")]
    return AssetInput(asset="XRP", price_at_video=2.346, stance=stance, levels=[
        LevelInput("BUY_ZONE", buy, timestamp="18:42", source_text="si XRP revient vers 2,15696"),
        LevelInput("REINFORCEMENT", 2.06397, timestamp="19:17"),
        LevelInput("CONFIRMATION", 2.444175, conditions=close),
        LevelInput("TARGET", 2.60763, allocation_pct=25),
        LevelInput("TARGET", 2.72748, allocation_pct=25),
        LevelInput("TARGET", 2.89272, allocation_pct=25),
        LevelInput("TARGET", 3.00084, allocation_pct=25),
    ])


def add(asset_input, when=PUBLISHED, title="Analyse XRP"):
    create_video(title=title, published_at=when, assets=[asset_input])
    return service.current_ids()[asset_input.asset]


def plan(analysis_id, market):
    return service.plan_for(analysis_id, market)


# --- closes: TOUCH ≠ CLOSE ≠ CONFIRMATION -------------------------------------------------


def test_1_touch_without_close_is_wait_close_never_confirmed():
    aid = add(xrp_levels())
    now = datetime(2026, 9, 20, 15, tzinfo=UTC)
    hours = int((now - (PUBLISHED - timedelta(hours=8))).total_seconds() // 3600)
    path = flat(2.346, hours - 3) + [(2.4514, 2.431, 2.4514)] * 3  # above since 12:00, day not closed
    p = plan(aid, FakeMarket(path, now))
    conf = next(lv for lv in p["levels"] if lv["kind"] == "CONFIRMATION")
    ev = conf["conditions"][0]["evaluation"]
    assert ev["status"] == "TOUCHED_NOT_CLOSED"
    assert "pas une confirmation" in ev["message"]
    assert p["now"]["status"] == "WAIT_CLOSE" and p["now"]["verdict"] == "ATTENDRE"
    assert ev["countdown"] == "9 h 00"
    assert ev["next_close_paris"] == "21 septembre — 02:00 heure de Paris"
    assert "CONFIRMED" not in str(p["now"])


def test_2_close_above_triggers_the_condition():
    aid = add(xrp_levels())
    now = datetime(2026, 9, 21, 3, tzinfo=UTC)
    hours = int((now - (PUBLISHED - timedelta(hours=8))).total_seconds() // 3600)
    path = flat(2.346, hours - 15) + [(2.465, 2.448, 2.4565)] * 15  # the 20 Sept daily closes above
    p = plan(aid, FakeMarket(path, now))
    ev = next(lv for lv in p["levels"] if lv["kind"] == "CONFIRMATION")["conditions"][0]["evaluation"]
    assert ev["status"] == "CONFIRMED"
    assert p["now"]["status"] == "BULLISH_CONFIRMATION"


def test_two_closes_required_means_one_is_not_enough():
    aid = add(xrp_levels(required=2))
    now = datetime(2026, 9, 21, 3, tzinfo=UTC)
    hours = int((now - (PUBLISHED - timedelta(hours=8))).total_seconds() // 3600)
    path = flat(2.346, hours - 15) + [(2.465, 2.448, 2.4565)] * 15
    p = plan(aid, FakeMarket(path, now))
    ev = next(lv for lv in p["levels"] if lv["kind"] == "CONFIRMATION")["conditions"][0]["evaluation"]
    assert ev["status"] == "CLOSED_ABOVE" and "1 clôture(s)" in ev["message"]
    assert p["now"]["status"] == "WAIT_CLOSE"


def test_touched_then_closed_back_below_is_a_missing_confirmation():
    aid = add(xrp_levels())
    now = datetime(2026, 9, 21, 3, tzinfo=UTC)
    hours = int((now - (PUBLISHED - timedelta(hours=8))).total_seconds() // 3600)
    path = flat(2.346, hours - 20) + [(2.448, 2.38, 2.414)] * 3 + flat(2.363, 17)
    p = plan(aid, FakeMarket(path, now))
    ev = next(lv for lv in p["levels"] if lv["kind"] == "CONFIRMATION")["conditions"][0]["evaluation"]
    assert ev["status"] == "FAILED"
    assert p["now"]["status"] == "CONFIRMATION_MISSING"
    assert any("Clôture non confirmée" in c["title"] for c in p["calendar"])
    assert any(t["emoji"] == "❌" for t in p["timeline"])


def test_breakout_lost_inside_the_confirmation_window_fails():
    cond = CloseCondition(level=100, operator="ABOVE", timeframe="1D", required_closes=1,
                          confirmation_window=2)
    day = lambda d, c: Bar(datetime(2026, 9, d, tzinfo=UTC), datetime(2026, 9, d + 1, tzinfo=UTC),  # noqa: E731
                           c, max(c, 101), min(c, 99), c, True)
    ev = evaluate(cond, [day(1, 101), day(2, 102), day(3, 98)],
                  since=datetime(2026, 8, 31, tzinfo=UTC), now=datetime(2026, 9, 4, 5, tzinfo=UTC),
                  price=98)
    assert ev.status == "FAILED"
    ev = evaluate(cond, [day(1, 101), day(2, 102), day(3, 103)],
                  since=datetime(2026, 8, 31, tzinfo=UTC), now=datetime(2026, 9, 4, 5, tzinfo=UTC),
                  price=103)
    assert ev.status == "CONFIRMED"


def test_close_times_are_binance_s_in_paris_time():
    summer = datetime(2026, 9, 21, 20, 30, tzinfo=UTC)
    assert next_close(summer, "1D") == datetime(2026, 9, 22, tzinfo=UTC)
    assert paris(next_close(summer, "1D")) == "22 septembre — 02:00 heure de Paris"
    winter = datetime(2026, 12, 3, 20, 30, tzinfo=UTC)
    assert paris(next_close(winter, "1D")) == "4 décembre — 01:00 heure de Paris"
    assert next_close(summer, "4H") == datetime(2026, 9, 22, 0, tzinfo=UTC)
    assert next_close(datetime(2026, 9, 23, 9, tzinfo=UTC), "1W") == datetime(2026, 9, 28, tzinfo=UTC)


def test_a_confirmation_without_stated_condition_is_only_touched():
    aid = add(AssetInput(asset="XRP", levels=[LevelInput("CONFIRMATION", 2.444175),
                                               LevelInput("BUY_ZONE", 2.15696)]))
    now = datetime(2026, 9, 21, 3, tzinfo=UTC)
    hours = int((now - (PUBLISHED - timedelta(hours=8))).total_seconds() // 3600)
    p = plan(aid, FakeMarket(flat(2.346, hours - 20) + flat(2.482, 20), now))
    conf = next(lv for lv in p["levels"] if lv["kind"] == "CONFIRMATION")
    assert conf["state"]["code"] == "TOUCHED"
    assert "ne précise pas" in conf["state"]["label"]
    assert p["now"]["status"] != "BULLISH_CONFIRMATION"


# --- the example: XRP between its zones ----------------------------------------------


def test_xrp_between_zones_waits_and_says_why():
    aid = add(xrp_levels())
    now = datetime(2026, 9, 20, 10, tzinfo=UTC)
    hours = int((now - (PUBLISHED - timedelta(hours=8))).total_seconds() // 3600)
    p = plan(aid, FakeMarket(flat(2.346, hours), now))
    assert p["now"]["status"] == "BETWEEN_LEVELS" and p["now"]["verdict"] == "ATTENDRE"
    assert "2,15696 $" in p["now"]["reason"] and "2,444175 $" in p["now"]["reason"]
    down, up = p["next_actions"]
    assert (down["direction"], down["value"]) == ("↓", 2.15696)
    assert up["direction"] == "↑" and "2,444175 $" in up["label"] and "journalière" in up["label"]
    buy = next(lv for lv in p["levels"] if lv["kind"] == "BUY_ZONE")
    assert buy["distance_fr"] == "↓ 8,1 % avant la zone d'achat"
    assert [r["state"] for r in p["rules"]][:1] == ["⏳ Pas encore"]
    assert p["timeline"][-1]["text"] == "Maintenant — ENTRE DEUX NIVEAUX"
    assert "aucun ordre" in p["no_order"]
    assert {i["emoji"] for i in p["why"]} >= {"🧱", "🕯️", "💰", "🎯"}


def test_reaching_a_buy_zone_says_buy_but_waits_if_something_is_missing(monkeypatch):
    aid = add(xrp_levels())
    now = datetime(2026, 9, 20, 10, tzinfo=UTC)
    hours = int((now - (PUBLISHED - timedelta(hours=8))).total_seconds() // 3600)
    market = FakeMarket(flat(2.346, hours - 2) + flat(2.1505, 2), now)
    p = plan(aid, market)
    assert (p["now"]["status"], p["now"]["verdict"]) == ("BUY_ZONE_REACHED", "ACHETER")
    monkeypatch.setattr(service, "macro_events", lambda days=14: [{
        "title": "FOMC", "scheduled_at": (now + timedelta(hours=5)).isoformat(),
        "importance": "CRITICAL", "event_type": "FOMC"}])
    p = plan(aid, market)
    assert p["now"]["status"] == "BUY_ZONE_REACHED" and p["now"]["verdict"] == "ATTENDRE"
    assert p["now"]["action_pending"] and "FOMC" in p["now"]["reason"]


# --- [3] versions ---------------------------------------------------------------------


def test_3_a_new_analysis_supersedes_the_old_one_and_says_what_changed():
    first = add(xrp_levels())
    second = add(xrp_levels(buy=2.227), when=PUBLISHED + timedelta(days=6), title="Analyse du 24")
    now = datetime(2026, 9, 25, 10, tzinfo=UTC)
    hours = int((now - (PUBLISHED - timedelta(hours=8))).total_seconds() // 3600)
    market = FakeMarket(flat(2.346, hours), now)
    old, new = plan(first, market), plan(second, market)
    assert old["lifecycle"] == "SUPERSEDED" and old["now"]["verdict"] == "PLAN REMPLACÉ"
    assert new["revision"]["relation"] == "UPDATES"
    change = next(c for c in new["revision"]["changes"] if c["what"] == "Zone d'achat")
    assert "2,15696 $" in change["old"] and "2,227 $" in change["new"]
    assert new["version"] == 2 and [v["version"] for v in new["versions"]] == [1, 2]


# --- [4] expiry ---------------------------------------------------------------------------


def test_4_a_level_reached_after_expiry_raises_no_alert():
    aid = add(xrp_levels())
    now = PUBLISHED + timedelta(days=30)
    hours = int((now - (PUBLISHED - timedelta(hours=8))).total_seconds() // 3600)
    market = FakeMarket(flat(2.346, hours - 3) + flat(2.142, 3), now)
    p = plan(aid, market)
    assert p["lifecycle"] == "EXPIRED" and p["now"]["verdict"] == "PLAN EXPIRÉ"
    assert notifier.candidates(p, now) == []
    assert notifier.evaluate_all(market) == []


# --- [5] duplicates -----------------------------------------------------------------------


def test_5_two_videos_on_the_same_level_notify_once():
    first = add(xrp_levels())
    now = PUBLISHED + timedelta(days=2)
    hours = int((now - (PUBLISHED - timedelta(hours=8))).total_seconds() // 3600)
    market = FakeMarket(flat(2.346, hours - 3) + flat(2.1845, 3), now)  # 1.3 % above 2.15696
    sent_first = notifier.dispatch(plan(first, market), now)
    assert any("approche de 2,15696 $" in m for m in sent_first)
    second = add(xrp_levels(), when=PUBLISHED + timedelta(days=1), title="Même niveau")
    sent_second = notifier.dispatch(plan(second, market), now)
    assert not any("approche de 2,15696 $" in m for m in sent_second)
    assert notifier.dispatch(plan(second, market), now) == []  # nothing new, nothing sent


# --- [6] Lexa vs our engine ---------------------------------------------------------------


def test_6_lexa_buy_while_our_engine_waits_is_a_visible_divergence(monkeypatch):
    monkeypatch.setattr(service, "our_reading", lambda asset: {
        "action": "WAIT", "sentence": "Levier élevé.", "etf": None,
        "home_families": [{"family": "technical", "tone": "ORANGE", "status": "Étirée"},
                          {"family": "derivatives", "tone": "RED", "status": "Longs encombrés"}]})
    aid = add(AssetInput(asset="BTC", levels=[LevelInput("BUY_ZONE", 60000)]))
    now = PUBLISHED + timedelta(days=2)
    hours = int((now - (PUBLISHED - timedelta(hours=8))).total_seconds() // 3600)
    p = plan(aid, FakeMarket(flat(64000, hours - 2) + flat(59900, 2), now))
    assert p["now"]["verdict"] == "ACHETER"
    v = p["validation"]
    assert v["divergence"] is True and v["level"] == "PARTIAL"
    assert "ATTENDRE" in v["explanation"]
    names = [f["name"] for f in v["families"]]
    assert names == ["Technique", "Flux spot", "Dérivés", "ETF", "Macro", "Cycle"]
    assert next(f for f in v["families"] if f["name"] == "ETF")["status"] == "Données insuffisantes"


def test_our_engine_selling_holds_the_lexa_buy_back(monkeypatch):
    monkeypatch.setattr(service, "our_reading", lambda asset: {
        "action": "SELL", "sentence": "", "etf": None, "home_families": []})
    aid = add(AssetInput(asset="ETH", levels=[LevelInput("BUY_ZONE", 2000)]))
    now = PUBLISHED + timedelta(days=2)
    hours = int((now - (PUBLISHED - timedelta(hours=8))).total_seconds() // 3600)
    p = plan(aid, FakeMarket(flat(2100, hours - 2) + flat(1995, 2), now))
    assert p["now"]["status"] == "BUY_ZONE_REACHED" and p["now"]["verdict"] == "ATTENDRE"
    assert "nos données contredisent" in p["now"]["reason"]
    assert p["validation"]["level"] == "WEAK"


def test_an_asset_we_do_not_cover_has_insufficient_data_not_a_guess():
    aid = add(xrp_levels())
    now = PUBLISHED + timedelta(days=1)
    hours = int((now - (PUBLISHED - timedelta(hours=8))).total_seconds() // 3600)
    p = plan(aid, FakeMarket(flat(2.346, hours), now))
    assert p["validation"]["label"] == "Données insuffisantes"


# --- [7] [8] whose money, whose levels ---------------------------------------------------


def test_7_the_member_s_amounts_are_never_lexa_s():
    aid = add(xrp_levels())
    now = PUBLISHED + timedelta(days=1)
    hours = int((now - (PUBLISHED - timedelta(hours=8))).total_seconds() // 3600)
    market = FakeMarket(flat(2.346, hours), now)
    budget = plan(aid, market)["budget"]
    assert {e["origin"] for e in budget["entries"]} == {"APP_EQUAL_SPLIT"}
    assert "Lexa ne donne pas de montant" in budget["entries"][0]["note"]
    levels = {lv["kind"]: lv for lv in plan(aid, market)["levels"]}
    set_user_plan(aid, [{"level_id": levels["BUY_ZONE"]["id"], "amount_type": "EURO", "amount": 60},
                        {"level_id": levels["REINFORCEMENT"]["id"], "amount_type": "EURO", "amount": 40}])
    p = plan(aid, market)
    entries = {e["value"]: e for e in p["budget"]["entries"]}
    assert entries[2.15696]["amount_eur"] == 60 and entries[2.15696]["origin"] == "USER_PLAN"
    assert entries[2.15696]["note"] == "Montant décidé par toi"
    buy = next(lv for lv in p["levels"] if lv["kind"] == "BUY_ZONE")
    assert buy["lexa_allocation_pct"] is None  # Lexa said no share: none is shown as hers
    add_fill(aid, side="BUY", price_usd=2.15696, amount_eur=60, eurusd=1.87,
             level_id=levels["BUY_ZONE"]["id"])
    b = plan(aid, market)["budget"]
    assert (b["budget_eur"], b["deployed_eur"], b["available_eur"], b["planned_eur"]) == (100, 60, 40, 100)
    tp1 = b["exits"][0]
    assert tp1["pct"] == 25 and tp1["origin"] == "LEXA"
    assert tp1["quantity"] == pytest.approx(60 * 1.87 / 2.15696 * 0.25)


def test_8_levels_come_from_the_analysis_only():
    aid = add(xrp_levels())
    now = PUBLISHED + timedelta(days=1)
    hours = int((now - (PUBLISHED - timedelta(hours=8))).total_seconds() // 3600)
    p = plan(aid, FakeMarket(flat(2.346, hours), now))
    stored = {2.15696, 2.06397, 2.444175, 2.60763, 2.72748, 2.89272, 3.00084}
    assert {lv["value"] for lv in p["levels"]} == stored
    assert all(lv["basis_fr"] == "🎬 Dit par Lexa" for lv in p["levels"])
    assert "levels" not in p["validation"]


# --- [9] no data, no invention -------------------------------------------------------------


def test_9_no_price_means_nothing_is_deduced():
    aid = add(AssetInput(asset="ZEC", levels=[LevelInput("BUY_ZONE", 30.0)]))
    market = FakeMarket([], PUBLISHED + timedelta(days=1))
    market.bars = lambda *a: None
    p = plan(aid, market)
    assert p["now"]["status"] == "NO_PRICE"
    assert p["levels"][0]["state"]["code"] == "NOT_WATCHED"
    assert p["next_actions"] == []


def test_9_an_unreadable_video_imports_nothing(tmp_path):
    from crypto_intel.lexa import test_run

    with pytest.raises(ValueError):
        test_run.start("aucune transcription", title="x", published_at=None, source="x",
                       background=False)
    assert service.current_ids() == {}


# --- [10] history ---------------------------------------------------------------------------


def test_10_old_analyses_stay_in_the_history():
    add(xrp_levels())
    add(xrp_levels(buy=2.227), when=PUBLISHED + timedelta(days=6))
    now = PUBLISHED + timedelta(days=7)
    hours = int((now - (PUBLISHED - timedelta(hours=8))).total_seconds() // 3600)
    h = service.history("XRP", FakeMarket(flat(2.346, hours), now))["analyses"]
    assert [(a["version"], a["lifecycle"]) for a in h] == [(2, "ACTIVE"), (1, "SUPERSEDED")]
    assert h[0]["revision"]["relation"] == "UPDATES"


# --- overview and calendar -------------------------------------------------------------------


def test_overview_lists_any_crypto_and_the_calendar_buckets_by_paris_day():
    add(xrp_levels())
    add(AssetInput(asset="HYPE", stance="WAIT", levels=[LevelInput("SUPPORT", 40.0)]))
    now = datetime(2026, 9, 20, 15, tzinfo=UTC)
    hours = int((now - (PUBLISHED - timedelta(hours=8))).total_seconds() // 3600)
    market = FakeMarket(flat(2.346, hours - 3) + [(2.4514, 2.431, 2.4514)] * 3, now)
    o = service.overview(market)
    assert o["assets"] == ["HYPE", "XRP"]
    xrp = next(r for r in o["follow"] if r["asset"] == "XRP")
    assert xrp["status"] == "WAIT_CLOSE" and xrp["bucket"] == "TOMORROW"  # 02:00 Paris on the 21st
    assert xrp["key_level"] == "Niveau surveillé : 2,444175 $"
    card = next(c for c in o["plans"] if c["asset"] == "XRP")
    assert card["buy"] == [2.15696, 2.06397] and card["targets"] == [2.60763]
    cal = service.calendar(market)["items"]
    assert {i["bucket"] for i in cal} >= {"PAST", "TOMORROW"}
    assert any(i["kind"] == "CLOSE_DUE" and i["asset"] == "XRP" for i in cal)


# --- routes and import -------------------------------------------------------------------


def test_plan_routes_are_local_only():
    from fastapi.testclient import TestClient

    from crypto_intel.main import app

    remote = TestClient(app, client=("203.0.113.9", 5000))
    for path in ("/api/lexa/overview", "/api/lexa/calendar", "/api/lexa/plans/XRP",
                 "/api/lexa/notifications", "/api/lexa/plans-history"):
        assert remote.get(path).status_code == 403
    local = TestClient(app, client=("127.0.0.1", 5000))
    assert local.get("/api/lexa/plans/NOPE").status_code == 404


def test_a_checked_test_run_imports_only_verified_values(tmp_path):
    import json

    from crypto_intel.lexa import test_run

    run = test_run.runs_dir() / "20260921T100000Z"
    run.mkdir()
    level = lambda v, kind, ok, **kw: {"value": v, "kind": kind, "basis": "INFERRED",  # noqa: E731
                                       "evidence": {"verified": ok, "timestamp_s": 182,
                                                    "quote": "si ADA revient vers 0,4870"}, **kw}
    (run / "status.json").write_text(json.dumps({
        "run_id": run.name, "state": "DONE", "title": "Vidéo test",
        "published_at": "2026-09-18T08:00:00Z"}))
    (run / "extraction.json").write_text(json.dumps({"assets": [{
        "symbol": "ADA", "stance": "WAIT", "stance_basis": "EXPLICIT", "price_at_video": 0.512,
        "situation": [], "levels": [
            level(0.487, "BUY_ZONE", True, allocation_pct=40, allocation_basis="EXPLICIT"),
            level(0.539, "CONFIRMATION", True,
                  condition={"kind": "CLOSE_ABOVE", "timeframe": "4H", "text": "clôture 4h"}),
            level(0.7777, "TARGET", False)]}]}))
    video_id = test_run.import_run(run.name)
    assert video_id
    aid = service.current_ids()["ADA"]
    bundle = plans.load(aid)
    assert sorted(plans.value_of(lv) for lv in bundle.levels) == [0.487, 0.539]
    buy = next(lv for lv in bundle.levels if lv.kind == "BUY_ZONE")
    assert (buy.basis, buy.allocation_pct, buy.timestamp_s) == ("INFERRED", 40, 182)
    conf = next(lv for lv in bundle.levels if lv.kind == "CONFIRMATION")
    cond = bundle.conditions[conf.id][0]
    assert (cond.condition_type, cond.timeframe, cond.operator) == ("CLOSE", "4H", "ABOVE")
    assert bundle.analysis.source_type == "TRANSCRIPT_TEST"
    with pytest.raises(ValueError):
        test_run.import_run(run.name)  # never twice

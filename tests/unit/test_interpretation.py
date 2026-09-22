"""The reading layer: what an intermediate investor sees in ten seconds.

Pinned here, from the brief:
  - ATTENDRE always says what is awaited
  - a level, a date, a percentile is shown only when an engine produced it
  - an event is followed by « la réaction du marché », never read as a direction
  - data quality and market clarity are two readings
  - contradictions between families are stated
  - at most three cards per family, three reasons, three things awaited
  - no probability anywhere
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace as Ns

from crypto_intel.engines.decision_presentation import _NOTABLE
from crypto_intel.engines.interpretation import build_reading, when_fr

NOW = datetime(2026, 9, 21, 16, tzinfo=UTC)


def fam(extra=None, metrics=(), components=(), usable=True, freshness="LIVE"):
    return Ns(extra=extra or {}, metrics=list(metrics), components=list(components),
              usable=usable, freshness=freshness)


def metric(key, value, display, label="", delta=None, delta_label="", when=NOW, source="Test"):
    return Ns(key=key, value=value, display_value=display, label=label, delta=delta,
              delta_label=delta_label, timestamp=when, available_at=when, usable=True,
              period_label="", source=source, status="AVAILABLE")


def decision(families, *, action="WAIT", gates=(), to_buy=(), to_worsen=()):
    return Ns(families=families, action=Ns(value=action), gates=list(gates), to_buy=list(to_buy),
              to_worsen=list(to_worsen), horizon="7d", data_quality=95)


def tech(resistance=None, support=None, rsi=60.0, structure="TREND_UP"):
    return fam({"price": 72000.0, "resistance": resistance, "support": support, "rsi": rsi,
                "structure": structure, "levels_timeframe": "1d", "changes": {"7": 6.0},
                "resistance_detail": {"explanation": "Sommet du 12/09, testé 3 fois."}
                if resistance else None})


def views(trend="UP", stretched=False, crowded=False, share=None, near=False):
    return {
        "technical": {"trend": {"key": trend, "emoji": "📈"}, "timing": {"stretched": stretched},
                      "near_resistance": near},
        "derivatives": {"crowded": crowded},
        "flows": {"pressure": {"share": share} if share is not None else {}},
    }


NO_EDGE = Ns(name="UNCERTAINTY", detail="Aucun avantage mesurable sur l'historique.")


def reading(families, v, **kw):
    event = kw.pop("event", None)
    return build_reading(decision(families, **kw), v, top_event=event, as_of=NOW, asset="BTC")


def test_wait_always_says_what_is_awaited_even_with_nothing_measured():
    r = reading({"technical": tech()}, views())
    assert r["verdict"]["label"] == "ATTENDRE"
    assert r["waiting_for"], "ATTENDRE sans condition"
    assert all(w["text"] and w["why"] for w in r["waiting_for"])


def test_no_level_is_invented_when_the_engine_has_none():
    r = reading({"technical": tech()}, views())
    texts = [w["text"] for w in r["waiting_for"]] + r["change_mind"]["bullish"] + r["change_mind"]["bearish"]
    assert not any("$" in t for t in texts)
    assert r["invalidation"] is None
    assert any(c["title"] == "Pas de niveau fiable" for c in r["families"]["technical"])


def test_a_real_resistance_becomes_the_close_we_wait_for():
    r = reading({"technical": tech(resistance=74800.0, support=69500.0)}, views(near=True))
    assert r["waiting_for"][0]["text"] == "Clôture journalière de BTC au-dessus de 74 800 $"
    assert r["change_mind"]["bullish"][0] == "BTC clôture (journalière) au-dessus de 74 800 $"
    assert r["change_mind"]["bearish"][0] == "BTC clôture (journalière) sous 69 500 $"
    assert "69 500 $" in r["invalidation"]
    assert "bute sous la résistance" in r["headline"]


def test_an_event_is_dated_and_followed_by_the_market_s_reaction():
    event = Ns(title="🏛️ Décision de la Fed", at=NOW + timedelta(days=1, hours=2), hours=26,
               score=0.6, delay="dans 26 h")
    fams = {"technical": tech(), "macro": fam({"central_banks": []})}
    r = reading(fams, views(), event=event)
    item = next(w for w in r["waiting_for"] if w["kind"] == "EVENT")
    assert item["emoji"] == "🏛️" and item["text"] == "Décision de la Fed — demain 20:00"
    assert "réaction du marché" in item["why"]
    macro = r["families"]["macro"][0]
    assert "attentes" in macro["so_what"] and "réaction" in macro["watch"]


def test_a_central_bank_is_never_read_as_a_direction():
    bank = {"available": True, "name": "Fed", "rate_label": "3,75 – 4,00 %",
            "next_meeting": (NOW + timedelta(days=2)).isoformat(), "days_to_next": 2,
            "expectation_label": "Anticipation de marché indisponible",
            "last_decision": {"label": "Hausse de 25 pb"}}
    r = reading({"technical": tech(), "macro": fam({"central_banks": [bank]})}, views())
    fed = r["families"]["macro"][0]
    assert "pas le sens de la décision" in fed["so_what"]
    assert "Anticipation de marché indisponible" in fed["what"]  # never a made-up consensus


def test_crowded_leverage_is_translated_and_awaited():
    deriv = fam({"crowding": "CROWDED_LONGS", "funding_percentile": 92.0})
    r = reading({"technical": tech(), "derivatives": deriv}, views(crowded=True))
    card = r["families"]["derivatives"][0]
    assert card["title"] == "Beaucoup de levier à la hausse"
    assert "92e rang sur 100" in card["what"] and "liquidations" in card["so_what"]
    assert any(w["kind"] == "LEVERAGE" for w in r["waiting_for"])


def test_data_quality_and_market_clarity_are_separate_and_contradictions_stay():
    deriv = fam({"crowding": "NEW_LONGS", "funding_percentile": 40.0})
    r = reading({"technical": tech(rsi=85.0), "derivatives": deriv},
                views(stretched=True))
    assert r["data"]["emoji"] == "🟢"
    assert r["market"]["label"] == "Marché incertain"
    assert r["contradictions"]["sentence"] == "Les signaux restent partagés."
    assert r["contradictions"]["positives"] and r["contradictions"]["cautions"]


def test_old_data_is_flagged_and_missing_data_is_said():
    r = reading({"technical": tech(), "flows": fam(usable=False),
                 "macro": fam({"central_banks": []}, freshness="STALE")}, views())
    assert r["data"]["label"] == "Données incomplètes" and "flux" in r["data"]["detail"]


def test_a_stale_etf_session_says_so():
    etf = metric("etf.net_flow", 433e6, "+433 M$", when=NOW - timedelta(days=5))
    r = reading({"technical": tech(), "flows": fam(metrics=[etf])}, views())
    card = next(c for c in r["families"]["flows"] if c["emoji"] == "💰")
    assert "Donnée ancienne" in card["what"] and "16 sept." in card["what"]


def test_no_edge_is_a_separate_line_and_awaited_never_a_reason():
    r = reading({"technical": tech()}, views(), gates=[NO_EDGE])
    assert "avantage statistique" in r["validation_note"]
    assert not any("avantage" in w["title"] for w in r["why"])
    assert any(w["kind"] == "EDGE" for w in r["waiting_for"])


def test_limits_and_no_probability():
    deriv = fam({"crowding": "CROWDED_LONGS", "funding_percentile": 92.0, "dvol_percentile": 90.0,
                 "liquidations": {"24h": {"covered_hours": 24, "long_usd": 300e6}, "dominance": "LONGS"}})
    r = reading({"technical": tech(74800.0, 69500.0, rsi=85.0), "derivatives": deriv},
                views(stretched=True, crowded=True, share=0.4), gates=[NO_EDGE],
                to_buy=["Un recul durable de l'offre de stablecoins."],
                to_worsen=["Des ventes agressives qui repassent majoritaires."])
    assert len(r["why"]) <= 3 and len(r["waiting_for"]) <= 3
    assert all(len(cards) <= 3 for cards in r["families"].values())
    assert len(r["change_mind"]["bullish"]) <= 2 and len(r["change_mind"]["bearish"]) <= 2
    assert "probabilit" not in str(r).lower()


def test_names_follow_the_asset():
    etf = metric("etf.net_flow", 144e6, "+144 M$")
    r = build_reading(decision({"technical": tech(rsi=85.0), "flows": fam(metrics=[etf])}),
                      views(stretched=True), as_of=NOW, asset="ETH")
    assert any("Ether a enchaîné" in c["what"] for c in r["families"]["technical"])
    assert any(c["title"] == "Les ETF Ether achètent" for c in r["families"]["flows"])


def test_paris_time():
    assert when_fr(datetime(2026, 9, 23, 18, tzinfo=UTC), NOW) == "mercredi 23 sept. 20:00"


def test_nasdaq_texts_follow_the_move():
    """Regression: a Nasdaq rise was shown as « Nasdaq en forte baisse »."""
    _, up_text, down_text = _NOTABLE["risk_appetite"]
    assert up_text.startswith("📈 Nasdaq en forte hausse")
    assert down_text.startswith("📉 Nasdaq en forte baisse")


def test_a_level_on_the_wrong_side_of_the_price_is_not_shown():
    r = reading({"technical": tech(resistance=70000.0, support=75000.0)}, views())  # price 72 000
    texts = str(r["waiting_for"]) + str(r["change_mind"]) + str(r["families"]["technical"])
    assert "70\u202f000" not in texts and "75\u202f000" not in texts
    assert r["invalidation"] is None


def test_decision_streak_is_built_from_records_only(monkeypatch):
    from crypto_intel.core.enums import Asset
    from crypto_intel.history import decisions

    def row(hours_ago, action, reason):
        return {"captured_at": NOW - timedelta(hours=hours_ago),
                "payload": {"future": {"7d": {"action": action, "reason": reason}}}}

    rows = [row(1, "WAIT", "Résistance non franchie"), row(20, "WAIT", "Résistance non franchie"),
            row(50, "WAIT", "Fed proche"), row(80, "BUY", "Cassure confirmée")]
    monkeypatch.setattr(decisions, "load_snapshots", lambda *a, **k: rows)
    streak = decisions.decision_streak(Asset("BTC"), "7d", now=NOW)
    assert streak["label"] == "Attendre depuis 2 jours"
    assert [s["reason"] for s in streak["steps"]] == ["Fed proche", "Résistance non franchie"]
    monkeypatch.setattr(decisions, "load_snapshots", lambda *a, **k: rows[:3])
    assert decisions.decision_streak(Asset("BTC"), "7d", now=NOW)["label"] == \
        "Attendre depuis au moins 2 jours"  # no older record: we do not claim more


def test_levels_are_judged_against_the_price_now_not_the_last_daily_close():
    family = tech(resistance=74800.0, support=69500.0)
    family.extra["current_price"] = 76000.0  # the daily close was 72 000, the price has moved on
    r = reading({"technical": family}, views())
    assert "74\u202f800" not in str(r["waiting_for"]) + str(r["change_mind"])


def test_moving_average_jargon_is_translated():
    from crypto_intel.engines.interpretation import plain

    assert plain("Une clôture sous la MM50 (73\u202f238).") == \
        "Une clôture sous la moyenne des 50 dernières bougies (73\u202f238 $)."
    assert plain("Une clôture sous la EMA20 (80 781).") == \
        "Une clôture sous la moyenne des 20 dernières bougies (80 781 $)."


def test_why_wait_lists_what_holds_the_entry_supports_go_to_the_split():
    deriv = fam({"crowding": "NEW_LONGS", "funding_percentile": 40.0})
    r = reading({"technical": tech(rsi=85.0), "derivatives": deriv}, views(stretched=True))
    assert all(w["tone"] in {"RED", "ORANGE"} for w in r["why"])
    assert "Levier en hausse, sans excès" in r["contradictions"]["positives"]

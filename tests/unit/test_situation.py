"""« 🧭 Résumé de la situation » : raconter sans inventer de cause.

Pinned here:
  - the summary names what the price did, what the move coincides with, what
    amplified it, what holds it back, and why the decision follows
  - « coïncide avec » for a correlation; « mécaniquement amplifié » only for
    forced liquidations, and only on the side that matches the move
  - no aligned driver -> « aucune cause dominante ne ressort des données »
  - a trigger is never an amplifier
  - six sentences at most, and never the word « parce que »
"""

from datetime import UTC, datetime
from types import SimpleNamespace as Ns

from crypto_intel.engines.situation import build, direction_of

NOW = datetime(2026, 9, 22, 18, tzinfo=UTC)


def component(key, signal, weight=1.0, active=True):
    return Ns(key=key, signal=signal, weight=weight, active=active)


def metric(key, value, display):
    return Ns(key=key, value=value, display_value=display, usable=True)


def fam(extra=None, metrics=(), components=()):
    return Ns(extra=extra or {}, metrics=list(metrics), components=list(components),
              usable=True, freshness="LIVE")


def technical(change_1d=6.0, change_7d=10.0, structure="BREAKOUT_CONFIRMED",
              resistance=None, support=81951.0):
    return fam({"price": 87000.0, "changes": {"1": change_1d, "7": change_7d},
                "structure": structure, "resistance": resistance, "support": support})


def decision(families):
    return Ns(families=families, action=Ns(value="WAIT"), gates=[], to_buy=[], to_worsen=[],
              horizon="7d", data_quality=95)


READING = {"verdict": {"label": "ATTENDRE"}, "horizon": "7 jours",
           "waiting_for": [{"text": "Un repli vers 81 951 $ qui tienne", "kind": "LEVEL"}]}


def views(stretched=False, crowded=False, near=False):
    return {"technical": {"timing": {"stretched": stretched}, "near_resistance": near},
            "derivatives": {"crowded": crowded}}


def summary(families, view=None, event=None, reading=None):
    return build(decision(families), view or views(), reading or READING,
                 asset="BTC", now=NOW, top_event=event)


def test_the_summary_tells_the_move_its_coincidences_and_the_decision():
    macro = fam(components=[component("oil_shock", 0.8), component("real_yield", 0.6)])
    flows = fam({"spot": {"share": 0.55}},
                metrics=[metric("etf.net_flow", 845e6, "+845 M$"),
                         metric("etf.streak", None, "3 séances d'entrées")])
    derivatives = fam({"liquidations": {"24h": {"covered_hours": 24, "short_usd": 61e6},
                                        "dominance": "SHORTS"}})
    s = summary({"technical": technical(), "macro": macro, "flows": flows,
                 "derivatives": derivatives})

    assert s["move"] == "UP" and s["dominant_cause"] is True
    text = s["text"]
    assert text.startswith("Bitcoin progresse (+6,0 % sur 24 h et +10,0 % sur 7 jours)")
    assert "coïncide avec la détente du pétrole" in text
    assert "pression inflationniste" in text          # the mechanism, in general terms
    assert "signe d'une demande institutionnelle qui revient" in text
    assert "mécaniquement amplifié la hausse" in text
    assert text.rstrip().endswith("nous attendons un repli vers 81 951 $ qui tienne.")
    assert len(s["sentences"]) <= 6
    assert "parce que" not in text.lower()


def test_each_factor_keeps_its_role():
    macro = fam(components=[component("oil_shock", 0.8)])
    derivatives = fam({"liquidations": {"24h": {"covered_hours": 24, "short_usd": 61e6},
                                        "dominance": "SHORTS"}})
    s = summary({"technical": technical(), "macro": macro, "derivatives": derivatives},
                views(stretched=True))
    roles = s["roles"]
    assert any("pétrole" in item["text"] for item in roles["triggers"])
    assert any("Liquidations" in item["text"] for item in roles["amplifiers"])
    assert not any("Liquidations" in item["text"] for item in roles["triggers"])
    assert any("étiré" in item["text"] for item in roles["brakes"])


def test_liquidations_on_the_other_side_are_not_an_amplifier():
    # Shorts liquidated while the price falls: nothing to amplify a fall.
    derivatives = fam({"liquidations": {"24h": {"covered_hours": 24, "short_usd": 61e6},
                                        "dominance": "SHORTS"}})
    s = summary({"technical": technical(change_1d=-4.0, change_7d=-7.0,
                                        structure="BREAKDOWN_CONFIRMED"),
                 "derivatives": derivatives})
    assert s["move"] == "DOWN"
    assert "amplifié" not in s["text"]
    assert s["roles"]["amplifiers"] == []


def test_without_an_aligned_driver_no_cause_is_claimed():
    s = summary({"technical": technical()})
    assert s["dominant_cause"] is False
    assert "Aucune cause dominante ne ressort des données" in s["text"]
    assert "coïncide avec" not in s["text"]


def test_a_single_etf_session_is_not_a_trend():
    flows = fam(metrics=[metric("etf.net_flow", 120e6, "+120 M$"),
                         metric("etf.streak", None, "1 séance d'entrées")])
    s = summary({"technical": technical(), "flows": flows})
    assert "une séance isolée qui ne fait pas encore une tendance" in s["text"]


def test_brakes_and_context_are_named():
    macro = fam(components=[component("dollar", -0.7)])
    s = summary({"technical": technical(resistance=92000.0)}, views(near=True, crowded=True),
                event=Ns(title="🏛️ Décision de la Fed", delay="dans 26 h", at=NOW))
    assert "une résistance à 92\u202f000 $ toujours pas franchie en clôture" in s["text"]
    assert "un levier tendu" in s["text"]
    assert any("Fed" in item["text"] for item in s["roles"]["context"])
    macro_summary = summary({"technical": technical(), "macro": macro})
    assert "la hausse du dollar" in macro_summary["text"]


def test_an_event_we_wait_for_is_followed_by_the_reaction():
    reading = {**READING, "waiting_for": [
        {"text": "Décision de la Fed — demain 20:00", "kind": "EVENT"}]}
    s = summary({"technical": technical()}, reading=reading)
    assert s["text"].rstrip().endswith(
        "nous attendons Décision de la Fed — demain 20:00, puis la réaction du marché.")


def test_direction_needs_a_real_move():
    assert direction_of(0.4, 1.2) == "FLAT"
    assert direction_of(0.4, 3.0) == "UP"
    assert direction_of(-2.0, 1.0) == "DOWN"


# --- the home summary: four lines, and the roles kept apart ---------------------------------


def test_the_home_summary_is_four_lines_at_most():
    """The home has ten seconds. The narrative stays behind « Comprendre le
    mouvement », and the brief never grows into it."""

    macro = fam(components=[component("oil_shock", 0.8), component("real_yield", 0.6)])
    flows = fam({"spot": {"share": 0.55}},
                metrics=[metric("etf.net_flow", 845e6, "+845 M$"),
                         metric("etf.streak", None, "3 séances d'entrées")])
    derivatives = fam({"liquidations": {"24h": {"covered_hours": 24, "short_usd": 61e6},
                                        "dominance": "SHORTS"}})
    s = summary({"technical": technical(), "macro": macro, "flows": flows,
                 "derivatives": derivatives})

    brief = s["brief"]
    assert len(brief.split()) <= 80
    assert brief.count(".") <= 4
    assert len(brief) < len(s["text"])
    assert brief.startswith("Bitcoin progresse")
    assert "accompagnent le mouvement" in brief
    assert brief.rstrip().endswith("Nous attendons un repli vers 81 951 $ qui tienne.")
    # The brief states a coincidence, never a cause.
    assert "parce que" not in brief.lower() and "grâce" not in brief.lower()


def test_real_money_is_a_support_not_a_trigger():
    """ETF inflows go the same way as the move; that does not make them its
    cause. They are listed as a support, and the macro driver stays the
    possible trigger."""

    macro = fam(components=[component("oil_shock", 0.8)])
    flows = fam(metrics=[metric("etf.net_flow", 845e6, "+845 M$"),
                         metric("etf.streak", None, "3 séances d'entrées")])
    s = summary({"technical": technical(), "macro": macro, "flows": flows})
    roles = s["roles"]
    assert any("Flux ETF" in item["text"] for item in roles["supports"])
    assert not any("Flux ETF" in item["text"] for item in roles["triggers"])
    assert any("pétrole" in item["text"] for item in roles["triggers"])
    assert s["labels"]["supports"] == "Soutiens"


def test_the_brief_says_plainly_when_no_cause_stands_out():
    s = summary({"technical": technical()})
    assert "Aucune cause dominante ne ressort des données." in s["brief"]
    assert len(s["brief"].split()) <= 80


def test_the_brief_does_not_name_the_level_the_condition_already_carries():
    """« la résistance de 87 396 $ tient » under a condition that reads
    « clôture au-dessus de 87 396 $ » is the same level twice on one screen."""

    reading = {**READING, "waiting_for": [
        {"text": "Clôture 4 h de BTC au-dessus de 87 396 $", "kind": "LEVEL"}]}
    s = summary({"technical": technical(resistance=87396.0)},
                views(near=True, stretched=True), reading=reading)
    assert s["brief"].count("87 396") == 1
    assert "étiré à court terme" in s["brief"]          # the other brake stays
    assert "Résistance 87 396 $" in [i["text"] for i in s["roles"]["brakes"]]


def test_a_short_level_is_deduplicated_like_a_long_one():
    """Solana's levels have three digits; Bitcoin's have five. The rule is the
    same: the summary does not repeat the level the condition carries."""

    reading = {**READING, "waiting_for": [
        {"text": "Clôture 4 h de SOL au-dessus de 120 $", "kind": "LEVEL"}]}
    s = build(decision({"technical": technical(resistance=120.0)}), views(near=True),
              reading, asset="SOL", now=NOW)
    assert s["brief"].count("120 $") == 1

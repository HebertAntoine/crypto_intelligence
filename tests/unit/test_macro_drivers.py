"""Le radar macro : quinze moteurs surveillés, cinq affichés.

Pinned here, from the brief:
  - importance and direction are two scales: CRITICAL + UNKNOWN is valid
  - no macro shortcut: an easing cycle inside credit stress is not « positive »
  - a driver with no source is declared, never shown as neutral
  - a monthly value keeps its publication date; the next one is named
  - the five on the home are the five highest, recomputed, never hard-coded
  - what changed since the previous cycle comes from a recorded snapshot
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace as Ns

from crypto_intel.engines.macro_drivers import (
    BY_KEY,
    CYCLE_HOURS,
    DRIVERS,
    TOP,
    Context,
    attention_of,
    build,
    next_cycle,
    read_fed,
    read_inflation,
    read_oil,
    title_fr,
)
from crypto_intel.engines.market_radar import AttentionLevel, EventDirection

NOW = datetime(2026, 10, 7, 17, 30, tzinfo=UTC)


def point(stamp, value):
    return Ns(timestamp=stamp, value=value, available_at=stamp, source="test", meta={})


def series(metric_values, *, days=400, move_days=25):
    """A metric -> daily points: flat history, then the move inside the window.

    A linear ramp over a year has no thirty-day change at all, which is
    precisely what the readers measure.
    """

    out = {}
    for metric, (start, end) in metric_values.items():
        points = []
        for i in range(days):
            age = days - 1 - i
            if age > move_days:
                value = start
            else:
                share = (move_days - age) / move_days
                value = start + (end - start) * share
            points.append(point(NOW - timedelta(days=age), value))
        out[metric] = points
    return out


class View:
    """Only what Context asks for: the points of a metric, or nothing."""

    def __init__(self, data):
        self.data = data

    def points(self, metric, asset=None):
        return self.data.get(metric, [])


def ctx(data, *, events=()):
    return Context(view=View(data), now=NOW, events=list(events))


def event(title, when, category="MACRO"):
    return Ns(title=title, scheduled_at=when, category=category, detected_at=when, source="test")


# --- the two scales stay apart -----------------------------------------------------------------


def test_a_decision_due_tomorrow_is_critical_and_unknown():
    """Attention says « look at this ». Direction says « it points there ».
    Before the result exists, the second has no honest answer."""

    data = series({"macro.fed_funds_rate": (3.5, 3.5), "cb.fed.target_upper": (3.75, 3.75),
                   "cb.fed.target_lower": (3.5, 3.5)})
    fomc = event("FOMC monetary policy decision (October 2026)", NOW + timedelta(hours=20))
    reading = read_fed(ctx(data, events=[fomc]), BY_KEY["fed"])

    assert reading.direction is EventDirection.UNKNOWN
    assert "inconnue" in reading.summary
    # And the attention it deserves is high precisely because it is unknown.
    radar = build(View(data), now=NOW, events=[fomc])
    fed = next(d for d in radar["drivers"] if d["key"] == "fed")
    assert fed["attention"] in {AttentionLevel.HIGH.value, AttentionLevel.CRITICAL.value}
    assert fed["direction"] == "UNKNOWN"


def test_importance_is_explained_line_by_line():
    data = series({"macro.real10y": (2.0, 2.9)})
    radar = build(View(data), now=NOW)
    yields = next(d for d in radar["drivers"] if d["key"] == "yields")
    assert yields["importance"] > 0
    assert yields["importance_reasons"], "un score sans explication n'est pas vérifiable"
    assert any("famille" in reason for reason in yields["importance_reasons"])


def test_attention_follows_the_score_and_nothing_else():
    assert attention_of(90) is AttentionLevel.CRITICAL
    assert attention_of(70) is AttentionLevel.HIGH
    assert attention_of(10) is AttentionLevel.NONE


# --- no macro shortcut -------------------------------------------------------------------------


def test_an_easing_fed_inside_credit_stress_is_not_read_as_positive():
    """« baisse des taux = crypto monte » est interdit : une baisse provoquée
    par une dégradation économique n'a pas la même portée qu'une baisse
    préventive. Le crédit est consulté avant toute direction."""

    calm = series({"macro.fed_funds_rate": (4.5, 3.5), "macro.hy_spread": (3.0, 3.0)})
    assert read_fed(ctx(calm), BY_KEY["fed"]).direction is EventDirection.FAVORABLE

    stressed = series({"macro.fed_funds_rate": (4.5, 3.5), "macro.hy_spread": (3.0, 6.5)})
    reading = read_fed(ctx(stressed), BY_KEY["fed"])
    assert reading.direction is EventDirection.MIXED
    assert "dégradation économique" in reading.summary


def test_oil_only_counts_when_the_move_is_large_enough_to_be_macro():
    small = series({"macro.oil_wti": (80.0, 83.0)})
    assert read_oil(ctx(small), BY_KEY["oil"]).direction is EventDirection.NEUTRAL

    shock = series({"macro.oil_wti": (80.0, 95.0)})
    reading = read_oil(ctx(shock), BY_KEY["oil"])
    assert reading.direction is EventDirection.UNFAVORABLE
    # Through inflation expectations, never as a direct crypto signal.
    assert "inflationniste" in reading.summary


# --- missing data is declared ------------------------------------------------------------------


def test_a_driver_without_a_source_is_declared_never_neutral():
    radar = build(View({}), now=NOW)
    for driver in radar["drivers"]:
        if not driver["available"]:
            assert driver["direction"] == "UNKNOWN"
            assert driver["state"] == "Source non branchée"
            assert driver["importance"] == 0
    # Et la page sait lesquels manquent, plutôt que de les cacher.
    assert set(radar["unavailable"]) <= {d.key for d in DRIVERS}
    assert radar["watched"] == len(DRIVERS) == 15


def test_an_unavailable_driver_never_reaches_the_top():
    radar = build(View({"macro.real10y": [point(NOW, 2.5)]}), now=NOW)
    assert all(d["available"] for d in radar["top"])


# --- a value is published, not refreshed --------------------------------------------------------


def test_a_monthly_figure_keeps_its_date_and_names_the_next_one():
    """Le cycle de 3 h recalcule l'importance, pas la donnée. Un CPI d'août
    n'est pas republié à 18:00 parce que le radar tourne."""

    # Two years of monthly prints, the last one published six weeks ago.
    last = NOW.replace(day=1, hour=0, minute=0) - timedelta(days=40)
    months = [point(last - timedelta(days=30 * (23 - i)), 100 + i * 0.2) for i in range(24)]
    data = {"macro.core_cpi": months}
    pce = event("Personal Income and Outlays, September 2026", NOW + timedelta(days=22))
    reading = read_inflation(ctx(data, events=[pce]), BY_KEY["inflation"])

    assert reading.last_release == months[-1].timestamp
    assert reading.last_release < NOW - timedelta(days=30)
    assert reading.next_release == pce.scheduled_at
    # And it says plainly that the surprise cannot be computed without a consensus.
    assert "consensus" in reading.summary


def test_official_english_titles_are_shown_in_french():
    assert title_fr("FOMC monetary policy decision (October 2026)") == \
        "Décision de la Fed sur les taux"
    assert title_fr("Personal Income and Outlays, September 2026") == \
        "Revenus et dépenses des ménages (PCE)"
    assert title_fr("Un titre déjà en français") == "Un titre déjà en français"


# --- the top five is a ranking, not a list --------------------------------------------------------


def test_the_top_five_is_recomputed_and_never_hard_coded():
    """Autour d'une échéance japonaise majeure, la BoJ peut passer devant la Fed."""

    data = series({"macro.real10y": (2.5, 2.5), "cb.boj.call_rate": (0.5, 1.0),
                   "cb.fed.target_upper": (4.0, 4.0), "cb.fed.target_lower": (3.75, 3.75),
                   "macro.fed_funds_rate": (3.9, 3.9)})
    boj = event("Décision de politique monétaire de la BoJ", NOW + timedelta(hours=4))
    radar = build(View(data), now=NOW, events=[boj])

    assert len(radar["top"]) <= TOP
    keys = [d["key"] for d in radar["top"]]
    assert keys[0] == "boj", f"la BoJ devrait mener à quatre heures de sa décision : {keys}"
    boj_reading = next(d for d in radar["drivers"] if d["key"] == "boj")
    assert boj_reading["direction"] == "UNKNOWN"  # imminent, donc sens inconnu


def test_the_cycle_runs_on_the_clock():
    assert CYCLE_HOURS == (0, 3, 6, 9, 12, 15, 18, 21)
    assert next_cycle(datetime(2026, 10, 7, 17, 30, tzinfo=UTC)) == \
        datetime(2026, 10, 7, 18, 0, tzinfo=UTC)
    # Le dernier cycle d'une journée renvoie au premier de la suivante.
    assert next_cycle(datetime(2026, 10, 7, 22, 0, tzinfo=UTC)) == \
        datetime(2026, 10, 8, 0, 0, tzinfo=UTC)


# --- what changed since the previous cycle ---------------------------------------------------------


def test_a_change_is_read_from_the_recorded_cycle_not_re_derived():
    data = series({"macro.dxy": (99.0, 103.0)})
    previous = {"as_of": (NOW - timedelta(hours=3)).isoformat(),
                "drivers": [{"key": "dollar", "direction": "NEUTRAL", "state": "Dollar stable"}]}
    radar = build(View(data), now=NOW, previous=previous)

    change = next(c for c in radar["changes"] if c["key"] == "dollar")
    assert change["from"] == "NEUTRAL" and change["to"] == "UNFAVORABLE"
    assert change["from_state"] == "Dollar stable"
    # Sans instantané enregistré, aucun changement n'est inventé.
    assert build(View(data), now=NOW, previous=None)["changes"] == []


def test_the_summary_never_claims_a_direction_the_drivers_do_not_have():
    data = series({"macro.real10y": (2.5, 2.5)})
    radar = build(View(data), now=NOW)
    summary = radar["summary"]
    assert "%" not in summary and "probab" not in summary.lower()

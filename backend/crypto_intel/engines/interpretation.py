"""From engine outputs to what an intermediate investor reads in ten seconds.

    engines (scores, gates, levels, events)  ->  interpretation (here)  ->  UI

Nothing here changes a score, a gate or a verdict. It reads them and answers,
for the page and for each of the five families:

    what is happening        « Le levier reste élevé »
    what it means            « Beaucoup de positions utilisent l'effet de levier. »
    so what                  « → Une baisse rapide pourrait déclencher des liquidations. »
    what we watch            « À surveiller : funding revenu sous le 85e rang de l'année. »

Rules held everywhere:

  * a figure is shown only when an engine produced it (a level from the
    structure engine, a date from the event calendar, a percentile from the
    derivatives history). Missing -> said missing, never filled in;
  * ATTENDRE always says what is awaited (at least one concrete condition);
  * no probability is produced; scenarios are conditional, not weighted;
  * the quality of the data and the clarity of the market are two separate
    readings, never one score;
  * contradictions between families are stated, not averaged away;
  * a rate cut is not « bullish » by itself: for an event we watch the
    outcome against expectations, then the market's reaction.

Deterministic: no language model writes a verdict, a level or a condition.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from .decision_config import CYCLE, DERIVATIVES, FLOWS, MACRO, TECHNICAL
from .factor_semantics import fr_number

PARIS = ZoneInfo("Europe/Paris")
GREEN, ORANGE, RED, YELLOW, WHITE = "GREEN", "ORANGE", "RED", "YELLOW", "WHITE"
TONE_EMOJI = {GREEN: "🟢", ORANGE: "🟠", RED: "🔴", YELLOW: "🟡", WHITE: "⚪"}
#: « Important maintenant » / « À surveiller » / « Secondaire actuellement ».
NOW, WATCH, SECONDARY = "NOW", "WATCH", "SECONDARY"
IMPORTANCE_FR = {NOW: "Important maintenant", WATCH: "À surveiller",
                 SECONDARY: "Secondaire actuellement"}
VERDICT_FR = {"BUY": ("🟢", "ACHETER"), "WAIT": ("🟠", "ATTENDRE"), "SELL": ("🔴", "VENDRE"),
              "INSUFFICIENT_DATA": ("⚪", "DONNÉES INSUFFISANTES")}
HORIZON_FR = {"24h": "24 heures", "7d": "7 jours", "30d": "30 jours"}
FUNDING_HIGH_PCT = 85  # the same line the derivatives view uses
MONTHS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.",
          "nov.", "déc."]
NAMES = {"BTC": "Bitcoin", "ETH": "Ether", "SOL": "Solana"}
DAYS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


# --- small helpers ------------------------------------------------------------------------


def usd(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{fr_number(value, 0 if abs(value) >= 100 else 2)} $"


def when_fr(moment: datetime | None, now: datetime | None = None) -> str:
    """« demain 20:00 », « mercredi 24 sept. 14:30 » - Paris time."""

    if moment is None:
        return ""
    local = moment.astimezone(PARIS)
    if now is not None:
        today = now.astimezone(PARIS).date()
        if local.date() == today:
            return f"aujourd'hui {local:%H:%M}"
        if local.date() == today + timedelta(days=1):
            return f"demain {local:%H:%M}"
    return f"{DAYS[local.weekday()]} {local.day} {MONTHS[local.month - 1]} {local:%H:%M}"


def day_fr(moment: datetime | None) -> str:
    if moment is None:
        return "date inconnue"
    local = moment.astimezone(PARIS)
    return f"{local.day} {MONTHS[local.month - 1]}"


def card(emoji: str, title: str, what: str, so_what: str = "", watch: str = "", *,
         tone: str = WHITE, importance: str = WATCH, family: str = "",
         value: str = "", clause: str = "") -> dict[str, Any]:
    """`clause` is the same fact as a phrase that fits after « mais » in a sentence."""

    return {"emoji": emoji, "title": title, "what": what, "so_what": so_what, "watch": watch,
            "clause": clause or (title[:1].lower() + title[1:]),
            "tone": tone, "tone_emoji": TONE_EMOJI.get(tone, "⚪"), "importance": importance,
            "importance_label": IMPORTANCE_FR[importance], "family": family, "value": value}


def _metric(family: Any, key: str) -> Any:
    if family is None:
        return None
    return next((m for m in family.metrics if m.key == key), None)


def levels(extra: dict[str, Any]) -> tuple[float | None, float | None]:
    """Resistance above the price, support below it - anything else is not shown.

    A « resistance » under the current price (or a support above it) would make
    the page say « le prix bute sous » a level it already cleared.
    """

    price = extra.get("current_price") or extra.get("price")
    resistance, support = extra.get("resistance"), extra.get("support")
    if price:
        resistance = resistance if resistance and resistance > price else None
        support = support if support and support < price else None
    return resistance, support


def _tf_fr(tf: str | None) -> str:
    return {"1h": "1 h", "4h": "4 h", "1d": "journalière", "1w": "hebdomadaire"}.get(
        str(tf or "").lower(), str(tf or ""))


# --- 📊 Technique ---------------------------------------------------------------------------


TREND_WORDS = {
    "TREND_UP": "Le prix fait des sommets et des creux de plus en plus hauts.",
    "TREND_DOWN": "Le prix fait des sommets et des creux de plus en plus bas.",
    "RANGE": "Le prix oscille entre un support et une résistance, sans direction.",
    "BREAKOUT_PENDING": "Le prix teste une résistance : la cassure n'est pas encore faite.",
    "BREAKOUT_CONFIRMED": "Le prix a franchi une résistance et s'est maintenu au-dessus.",
    "BREAKDOWN_PENDING": "Le prix teste un support : la cassure n'est pas encore faite.",
    "BREAKDOWN_CONFIRMED": "Le prix est passé sous un support et y reste.",
    "UNCLEAR": "La structure des sommets et des creux ne donne pas de direction claire.",
}


def technical_cards(family: Any, view: dict[str, Any], asset: str = "BTC") -> list[dict[str, Any]]:
    if family is None or not family.usable:
        return []
    extra = family.extra
    price = extra.get("current_price") or extra.get("price")
    tf = _tf_fr(extra.get("levels_timeframe") or extra.get("timeframe"))
    trend = view.get("trend") or {}
    structure = str(extra.get("structure") or "UNCLEAR")
    cards: list[dict[str, Any]] = []
    key = trend.get("key", "FLAT")
    title = {"UP": "Tendance haussière", "DOWN": "Tendance baissière"}.get(key, "Pas de tendance nette")
    tone = {"UP": GREEN, "DOWN": RED}.get(key, YELLOW)
    so_what = {"UP": "La structure reste globalement positive.",
               "DOWN": "Les rebonds restent fragiles tant que la structure ne se retourne pas.",
               }.get(key, "Ni les acheteurs ni les vendeurs ne contrôlent le marché.")
    cards.append(card(trend.get("emoji", "➡️"), title, TREND_WORDS.get(structure, ""), so_what,
                      tone=tone, importance=WATCH, family=TECHNICAL))

    resistance, support = levels(extra)
    near = bool(view.get("near_resistance"))
    if resistance:
        detail = (extra.get("resistance_detail") or {}).get("explanation", "")
        distance = (resistance / price - 1) * 100 if price else None
        cards.append(card(
            "🧱", f"Résistance importante — {usd(resistance)}",
            (detail + " " if detail else "") + (
                f"Elle se trouve à {fr_number(distance, 1)} % au-dessus du prix." if distance is not None else ""),
            "Tant qu'elle n'est pas franchie, la hausse n'est pas confirmée.",
            f"une clôture {tf} au-dessus de {usd(resistance)}.",
            tone=ORANGE, importance=NOW if near else WATCH, family=TECHNICAL, value=usd(resistance),
            clause=f"le prix bute sous la résistance de {usd(resistance)}"))
    if support:
        detail = (extra.get("support_detail") or {}).get("explanation", "")
        distance = (price / support - 1) * 100 if price else None
        close = distance is not None and distance <= 2.0
        cards.append(card(
            "🛡️", f"Support important — {usd(support)}",
            (detail + " " if detail else "") + (
                f"Le prix est {fr_number(distance, 1)} % au-dessus." if distance is not None else ""),
            "Une cassure nette sous ce niveau affaiblirait la structure actuelle.",
            f"une clôture {tf} sous {usd(support)} serait un signal de faiblesse.",
            tone=GREEN if not close else ORANGE, importance=NOW if close else WATCH,
            family=TECHNICAL, value=usd(support)))
    if not resistance and not support:
        cards.append(card("🧱", "Pas de niveau fiable",
                          "Le moteur de structure ne trouve pas de support ou de résistance assez "
                          "testés pour être utilisés.", "Aucun niveau n'est inventé pour combler ce vide.",
                          tone=WHITE, importance=SECONDARY, family=TECHNICAL))

    rsi = extra.get("rsi")
    changes = extra.get("changes") or {}
    change7 = changes.get("7", changes.get(7))
    if (view.get("timing") or {}).get("stretched") and rsi is not None:
        move = f"+{fr_number(change7, 1)} % sur 7 jours" if change7 and change7 > 0 else "une forte hausse récente"
        cards.append(card(
            "🔥", "Prix déjà très haut à court terme",
            f"{NAMES.get(asset, asset)} a enchaîné {move} sans vraie respiration (RSI {fr_number(rsi, 0)} : "
            "au-dessus de 70, le mouvement est considéré comme étiré).",
            "Acheter maintenant laisse moins de marge si le marché corrige.",
            f"un repli vers le support {usd(support)} ou une nouvelle cassure confirmée." if support
            else "un repli ou une cassure confirmée.",
            tone=ORANGE, importance=NOW, family=TECHNICAL, value=f"RSI {fr_number(rsi, 0)}",
            clause="le prix a déjà beaucoup monté"))
    return _rank(cards)


# --- 📈 Dérivés -----------------------------------------------------------------------------


LEVERAGE = {
    "CROWDED_LONGS": ("🔥", "Beaucoup de levier à la hausse", RED,
                      "Beaucoup de traders achètent avec de l'argent emprunté, et cela leur coûte cher.",
                      "Une baisse rapide pourrait forcer ces positions à fermer en chaîne (liquidations)."),
    "CROWDED_SHORTS": ("🔥", "Beaucoup de paris à la baisse", ORANGE,
                       "Beaucoup de traders parient sur la baisse avec effet de levier.",
                       "Une hausse rapide pourrait les forcer à racheter, ce qui accélère la hausse."),
    "NEW_LONGS": ("🟢", "Levier en hausse, sans excès", GREEN,
                  "De nouvelles positions à la hausse accompagnent le mouvement, à un coût normal.",
                  "Pas de signe de surchauffe venant des dérivés pour l'instant."),
    "NEW_SHORTS": ("📉", "Nouveaux paris à la baisse", RED,
                   "De nouvelles positions vendeuses accompagnent la baisse.",
                   "La pression vendeuse vient aussi des dérivés : la baisse a du carburant."),
    "SHORT_COVERING": ("🔄", "Rachats de positions vendeuses", YELLOW,
                       "Des vendeurs à découvert ferment leurs positions, ce qui fait monter le prix.",
                       "Une hausse portée par ces rachats dure souvent moins qu'une hausse d'acheteurs."),
    "DELEVERAGING": ("🧹", "Le levier se purge", YELLOW,
                     "Positions et prix reculent ensemble : le marché se désendette.",
                     "Souvent douloureux à court terme, mais cela assainit le marché ensuite."),
    "QUIET": ("🟢", "Levier calme", GREEN,
              "Ni le prix ni les positions à effet de levier ne bougent nettement.",
              "Les dérivés n'ajoutent pas de risque particulier aujourd'hui."),
}


def derivatives_cards(family: Any, view: dict[str, Any]) -> list[dict[str, Any]]:
    if family is None or not family.usable:
        return []
    extra = family.extra
    crowding = str(extra.get("crowding") or "UNKNOWN")
    funding = extra.get("funding_percentile")
    cards: list[dict[str, Any]] = []
    if crowding in LEVERAGE:
        emoji, title, tone, what, so_what = LEVERAGE[crowding]
        rank = (f" Le coût du levier (funding) est au {fr_number(funding, 0)}e rang sur 100 de "
                "l'année." if funding is not None else "")
        watch = ""
        if crowding == "CROWDED_LONGS":
            watch = f"un retour du funding sous le {FUNDING_HIGH_PCT}e rang sans chute du prix."
        elif funding is not None and funding >= 70:
            watch = f"le funding : au-delà du {FUNDING_HIGH_PCT}e rang, le levier deviendrait excessif."
        crowded = crowding in {"CROWDED_LONGS", "CROWDED_SHORTS"}
        clause = {"CROWDED_LONGS": "le levier à la hausse est élevé",
                  "CROWDED_SHORTS": "les paris à la baisse sont nombreux",
                  "NEW_SHORTS": "de nouveaux paris à la baisse apparaissent"}.get(crowding, "")
        cards.append(card(emoji, title, what + rank, so_what, watch, tone=tone,
                          importance=NOW if crowded else WATCH, family=DERIVATIVES, clause=clause))
    liquidations = extra.get("liquidations") or {}
    day = liquidations.get("24h") or {}
    dominance = liquidations.get("dominance")
    if day.get("covered_hours") and dominance in {"LONGS", "SHORTS"}:
        amount = day.get("long_usd" if dominance == "LONGS" else "short_usd") or 0
        big = amount >= 100e6
        who = "acheteurs (longs)" if dominance == "LONGS" else "vendeurs (shorts)"
        cards.append(card(
            "💥", f"Liquidations surtout côté {who.split(' ')[0]}",
            f"Sur 24 h, {fr_number(amount / 1e6, 0)} M$ de positions {who} ont été fermées de force.",
            "Des positions perdantes ont été purgées : le mouvement a été amplifié par le levier."
            if big else "Volume modéré : pas de purge majeure.",
            tone=ORANGE if big else WHITE, importance=NOW if big else SECONDARY, family=DERIVATIVES,
            value=f"{fr_number(amount / 1e6, 0)} M$"))
    dvol = extra.get("dvol_percentile")
    if dvol is not None and (dvol >= 80 or dvol <= 20):
        high = dvol >= 80
        cards.append(card(
            "🌊", "Volatilité attendue élevée" if high else "Volatilité attendue basse",
            ("Les options montrent que le marché s'attend à de forts mouvements dans les prochains jours."
             if high else "Les options montrent que le marché s'attend à peu de mouvement."),
            ("Éviter d'interpréter trop vite un mouvement isolé." if high else
             "Un calme prolongé précède souvent un mouvement plus ample, dans un sens ou dans l'autre."),
            tone=ORANGE if high else WHITE, importance=WATCH if high else SECONDARY,
            family=DERIVATIVES))
    return _rank(cards)


# --- 🪙 Flux spot ---------------------------------------------------------------------------


def flows_cards(family: Any, view: dict[str, Any], now: datetime | None,
                asset: str = "BTC") -> list[dict[str, Any]]:
    if family is None or not family.usable:
        return []
    cards: list[dict[str, Any]] = []
    spot = family.extra.get("spot") or {}
    share = spot.get("share")
    if share is not None:
        buyers = share >= 0.51
        sellers = share <= 0.49
        delta = spot.get("delta_usd")
        window = spot.get("window", "7 j")
        title = ("Les acheteurs prennent la main" if buyers else
                 "Les vendeurs prennent la main" if sellers else "Acheteurs et vendeurs s'équilibrent")
        what = (f"Sur {window}, {fr_number(share * 100, 0)} % des volumes au comptant sont des achats "
                "passés au prix du marché (les plus pressés)")
        if delta is not None:
            what += f", soit {'+' if delta > 0 else ''}{fr_number(delta / 1e6, 0)} M$ d'écart."
        else:
            what += "."
        cards.append(card(
            "🪙", title, what,
            f"De l'argent réel achète {NAMES.get(asset, asset)} : la hausse a du soutien." if buyers else
            "La demande au comptant manque : une hausse aurait moins de soutien." if sellers else
            "Le comptant ne donne pas de direction.",
            "des ventes agressives qui repasseraient majoritaires." if buyers else
            "un retour des achats au-dessus de 50 %.",
            tone=GREEN if buyers else RED if sellers else YELLOW,
            importance=NOW if sellers else WATCH, family=FLOWS,
            clause="les vendeurs dominent au comptant" if sellers else "",
            value=f"{fr_number(share * 100, 0)} % acheteurs"))
    etf = _metric(family, "etf.net_flow")
    if etf is not None and etf.usable and etf.value is not None:
        streak = _metric(family, "etf.streak")
        inflow = etf.value > 0
        big = abs(etf.value) >= 200e6
        dated = day_fr(etf.timestamp or etf.available_at)
        stale = bool(now and (etf.timestamp or etf.available_at) and
                     now - (etf.timestamp or etf.available_at) > timedelta(days=4))
        what = (f"{etf.display_value} lors de la séance du {dated}"
                + (f" ({streak.display_value})" if streak is not None and streak.usable else "") + ".")
        cards.append(card(
            "💰", f"Les ETF {NAMES.get(asset, asset)} achètent" if inflow
            else f"Les ETF {NAMES.get(asset, asset)} vendent",
            what + (" Donnée ancienne : les ETF ne publient qu'après chaque séance." if stale else ""),
            ("La demande institutionnelle soutient le marché." if inflow and big else
             "Entrées modestes : un soutien, pas un moteur." if inflow else
             "Des institutionnels réduisent leur exposition : pression vendeuse."),
            "plusieurs séances de suite dans un sens ou dans l'autre.",
            tone=GREEN if inflow else RED, importance=NOW if big else WATCH, family=FLOWS,
            value=etf.display_value))
    return _rank(cards)


# --- 🏛️ Macro -------------------------------------------------------------------------------


MACRO_MOVES = {
    # key: (metric, (emoji, title, so_what) if the metric rose, same if it fell, watch)
    "dollar": ("macro.dxy",
               ("💵", "Le dollar se renforce", "Un dollar fort pèse souvent sur les actifs risqués comme Bitcoin."),
               ("💵", "Le dollar recule", "Un dollar plus faible aide souvent les actifs risqués."),
               "un retournement du dollar."),
    "real_yield": ("macro.real10y",
                   ("🏛️", "Les taux réels américains montent",
                    "Détenir un actif sans rendement comme Bitcoin devient moins attractif."),
                   ("🏛️", "Les taux réels américains baissent",
                    "Le coût de détenir Bitcoin plutôt qu'une obligation diminue."),
                   "la direction des taux réels 10 ans."),
    "policy_expectations": ("macro.us2y",
                            ("🇺🇸", "Le marché anticipe une Fed plus stricte",
                             "Des taux plus hauts plus longtemps pèsent sur les actifs risqués."),
                            ("🇺🇸", "Le marché anticipe une Fed plus souple",
                             "Des baisses de taux attendues soutiennent les actifs risqués."),
                            "le taux 2 ans, le plus sensible aux attentes sur la Fed."),
    "risk_appetite": ("macro.nasdaq",
                      ("📈", "Les actions tech montent", "Un environnement qui favorise en général les actifs risqués."),
                      ("📉", "Les actions tech reculent", "Bitcoin peut suivre si l'aversion au risque augmente."),
                      "la stabilisation ou non du Nasdaq."),
    "equity_fear": ("macro.vix",
                    ("😨", "La nervosité monte sur les actions", "Les investisseurs réduisent le risque, crypto comprise."),
                    ("😌", "Les marchés actions se calment", "Un contexte plus favorable à la prise de risque."),
                    "l'indice de volatilité des actions (VIX)."),
    "oil_shock": ("macro.oil_wti",
                  ("🛢️", "Forte hausse du pétrole", "Risque de regain d'inflation, donc de taux plus hauts."),
                  ("🛢️", "Forte baisse du pétrole", "Moins de pression inflationniste."),
                  "le prix du pétrole."),
}
ABNORMAL = 0.6


def macro_cards(family: Any, view: dict[str, Any], now: datetime | None,
                event: Any = None) -> list[dict[str, Any]]:
    if family is None:
        return []
    cards: list[dict[str, Any]] = []
    banks = [b for b in family.extra.get("central_banks") or [] if b.get("available")]
    upcoming = sorted((b for b in banks if b.get("next_meeting")), key=lambda b: b["next_meeting"])
    for bank in upcoming[:1]:
        meeting = datetime.fromisoformat(bank["next_meeting"])
        days = bank.get("days_to_next")
        soon = days is not None and days <= 3
        expectation = bank.get("expectation_label") or "Attente du marché indisponible"
        last = bank.get("last_decision") or {}
        what = (f"Taux actuel : {bank['rate_label']}"
                + (f" (dernière décision : {last['label'].lower()})" if last.get("label") else "")
                + f". Prochaine décision : {when_fr(meeting, now)}. {expectation}.")
        cards.append(card(
            "🏛️", f"{bank['name']} — {'décision imminente' if soon else 'prochaine décision'}",
            what,
            "C'est l'écart entre la décision et ce qui était attendu qui fait bouger le marché, "
            "pas le sens de la décision.",
            "la décision, puis la réaction des taux, du dollar, du Nasdaq et de Bitcoin dans les heures suivantes."
            if soon else "",
            tone=ORANGE if soon else WHITE, importance=NOW if soon else SECONDARY, family=MACRO))
    moves = []
    for component in family.components:
        spec = MACRO_MOVES.get(component.key)
        if spec is None or not component.active or abs(component.signal or 0) < ABNORMAL:
            continue
        reading = _metric(family, spec[0])
        if reading is None or reading.delta is None:
            continue
        emoji, title, so_what = spec[1] if reading.delta > 0 else spec[2]
        tone = GREEN if (component.signal or 0) > 0 else RED
        move = reading.delta_label or ""
        moves.append((abs(component.signal) * component.weight, card(
            emoji, title, f"{reading.label} : {reading.display_value}" + (f" ({move})" if move else "") + ".",
            so_what, spec[3], tone=tone, importance=WATCH, family=MACRO)))
    moves.sort(key=lambda m: m[0], reverse=True)
    if moves:
        moves[0][1]["importance"] = NOW
        moves[0][1]["importance_label"] = IMPORTANCE_FR[NOW]
    cards += [c for _, c in moves[:2]]
    if event is not None and getattr(event, "at", None) is not None and event.hours <= 72:
        cards.append(card(
            event.title.split(" ", 1)[0] if event.title else "📅",
            f"{event.title.split(' ', 1)[-1]} — {when_fr(event.at, now)}",
            "Publication programmée qui peut faire bouger les taux et les actifs risqués.",
            "Le chiffre compte moins que son écart avec les attentes.",
            "le résultat, puis la réaction du marché : c'est elle qui confirme ou non une direction.",
            tone=ORANGE if event.score >= 0.3 else WHITE,
            importance=NOW if event.score >= 0.3 else WATCH, family=MACRO))
    return _rank(cards)


# --- 🔄 Cycle -------------------------------------------------------------------------------


def cycle_cards(family: Any, view: dict[str, Any], asset: str) -> list[dict[str, Any]]:
    if family is None or not family.usable:
        return []
    cycle = family.extra.get("cycle") or {}
    dims = cycle.get("dimensions") or {}
    if not cycle.get("phase_label"):
        return []
    evidence = cycle.get("evidence") or []
    facts = []
    if dims.get("days_since_halving") is not None:
        facts.append(f"{fr_number(dims['days_since_halving'], 0)} jours depuis le dernier halving")
    if dims.get("drawdown_pct") is not None:
        facts.append(f"{fr_number(abs(dims['drawdown_pct']), 0)} % sous le record")
    phase = cycle["phase_label"]
    return [card(
        "🔄", f"Phase : {phase.lower()}"
        + (f" ({cycle.get('direction_label', '').lower()})" if cycle.get("direction_label") else ""),
        (" · ".join(facts) + ". " if facts else "") + (evidence[0] if evidence else ""),
        "Contexte de long terme : les cycles passés ne permettent pas de dater un sommet ou un creux.",
        tone=WHITE, importance=NOW if cycle.get("elevated_structural_risk") else SECONDARY,
        family=CYCLE)]


def _rank(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    order = {NOW: 0, WATCH: 1, SECONDARY: 2}
    return sorted(cards, key=lambda c: order[c["importance"]])[:3]


# --- the page: verdict, why, what we wait for, what would change it -------------------------


_TO_BUY_WORDS = [
    (re.compile(r"Un signal dont l'avantage se confirme sur l'historique\.?", re.I),
     "Un signal dont l'avantage est démontré sur l'historique (aucun ne l'est aujourd'hui)."),
    (re.compile(r"Un repli du taux réel 10 ans sous ([\d ,.]+ ?%)\.?", re.I),
     r"Une baisse des taux réels américains à 10 ans sous \1."),
    (re.compile(r"Un recul durable de l'offre de stablecoins\.?", re.I),
     "Un recul durable des stablecoins en circulation (moins de liquidités prêtes à acheter)."),
    (re.compile(r"Une hausse durable de l'offre de stablecoins\.?", re.I),
     "Une hausse durable des stablecoins en circulation (plus de liquidités prêtes à acheter)."),
    (re.compile(r"Une clôture sous la (?:EMA|MM|SMA) ?(\d+) \(([\d \u00a0\u202f]+)\)\.?", re.I),
     r"Une clôture sous la moyenne des \1 dernières bougies (\2 $)."),
    (re.compile(r"Des ventes agressives qui repassent majoritaires\.?", re.I),
     "Des ventes au comptant qui repasseraient majoritaires."),
]


def plain(text: str) -> str:
    for pattern, repl in _TO_BUY_WORDS:
        if pattern.fullmatch(text.strip()):
            return pattern.sub(repl, text.strip())
    return text.strip()


def _gate_detail(decision: Any, name: str) -> str:
    return next((g.detail for g in decision.gates if g.name == name), "")


def build_reading(decision: Any, views: dict[str, dict[str, Any]], *, top_event: Any = None,
                  as_of: datetime | None = None, asset: str = "BTC") -> dict[str, Any]:
    fams = decision.families
    now = as_of
    action = decision.action.value
    emoji, label = VERDICT_FR.get(action, ("⚪", action))
    tech = fams.get(TECHNICAL)
    tech_view = views.get(TECHNICAL, {})
    extra = tech.extra if tech is not None else {}
    resistance, support = levels(extra)
    tf = _tf_fr(extra.get("levels_timeframe") or extra.get("timeframe"))

    per_family = {
        TECHNICAL: technical_cards(tech, tech_view, asset),
        DERIVATIVES: derivatives_cards(fams.get(DERIVATIVES), views.get(DERIVATIVES, {})),
        FLOWS: flows_cards(fams.get(FLOWS), views.get(FLOWS, {}), now, asset),
        MACRO: macro_cards(fams.get(MACRO), views.get(MACRO, {}), now, top_event),
        CYCLE: cycle_cards(fams.get(CYCLE), views.get(CYCLE, {}), asset),
    }

    # 1. Why - the cards that weigh now, across families (at most three).
    candidates: list[tuple[int, dict[str, Any]]] = []
    no_edge = "avantage mesurable" in _gate_detail(decision, "UNCERTAINTY")
    # The statistical validation is its own line, never one of the reasons:
    # it says how far the reasons can be trusted, not what the market does.
    validation_note = (
        "📊 Aucun signal n'a démontré d'avantage statistique sur l'historique (tests corrigés) : "
        "le moteur reste en attente plutôt que de parier." if no_edge else None)
    for fam_key in (TECHNICAL, DERIVATIVES, FLOWS, MACRO, CYCLE):
        for c in per_family[fam_key]:
            rank = {NOW: 1, WATCH: 2, SECONDARY: 4}[c["importance"]]
            # « Pourquoi attendre ? » lists what holds the entry before what supports it.
            if action == "WAIT" and c["tone"] in {GREEN, WHITE, YELLOW}:
                rank += 2
            candidates.append((rank, c))
    candidates.sort(key=lambda item: item[0])
    # « Pourquoi attendre ? » names what holds the entry. The supports are not
    # hidden: they appear in « les signaux restent partagés » below.
    if action == "WAIT" and any(c["tone"] in {RED, ORANGE} for _, c in candidates):
        candidates = [(r, c) for r, c in candidates if c["tone"] in {RED, ORANGE}]
    why: list[dict[str, Any]] = []
    for _, c in candidates:
        if c["title"] not in {w["title"] for w in why}:
            why.append(c)
        if len(why) == 3:
            break

    # 2. What we wait for - concrete, from engine values only.
    waiting: list[dict[str, Any]] = []

    def wait(emoji_: str, text: str, why_: str, kind: str) -> None:
        if len(waiting) < 3 and text not in {w["text"] for w in waiting}:
            waiting.append({"emoji": emoji_, "text": text, "why": why_, "kind": kind})

    trend_key = (tech_view.get("trend") or {}).get("key")
    if action in {"WAIT", "SELL"}:
        if resistance and trend_key != "DOWN":
            wait("🧱", f"Clôture {tf} de {asset} au-dessus de {usd(resistance)}",
                 "Elle montrerait que les acheteurs reprennent réellement le contrôle.", "LEVEL")
        elif (tech_view.get("timing") or {}).get("stretched") and support:
            wait("🛡️", f"Un repli vers {usd(support)} qui tienne",
                 "Il offrirait une entrée moins tardive, sur un support testé.", "LEVEL")
        if top_event is not None and getattr(top_event, "at", None) and top_event.score >= 0.2:
            ev_emoji, _, ev_name = top_event.title.partition(" ")
            if not ev_name:
                ev_emoji, ev_name = "📅", top_event.title
            wait(ev_emoji, f"{ev_name} — {when_fr(top_event.at, now)}",
                 "Puis la réaction du marché : l'événement seul n'est pas une confirmation.", "EVENT")
        if views.get(DERIVATIVES, {}).get("crowded"):
            wait("🔥", f"Un funding revenu sous le {FUNDING_HIGH_PCT}e rang de l'année",
                 "Moins de levier = moins de risque de liquidations en chaîne.", "LEVERAGE")
        pressure = (views.get(FLOWS, {}).get("pressure") or {}).get("share")
        if pressure is not None and pressure <= 0.49:
            wait("🪙", "Un retour des achats au comptant au-dessus de 50 %",
                 "Une hausse sans acheteurs au comptant tient rarement.", "FLOW")
        if no_edge:
            wait("📊", "Un signal dont l'avantage est démontré sur l'historique",
                 "C'est la condition que le moteur exige avant de proposer une position.", "EDGE")
        for item in decision.to_buy[:3]:
            if len(waiting) >= 3:
                break
            text = plain(item)
            if "avantage" not in text:
                wait("🔎", text.rstrip("."), "Condition relevée par le moteur de décision.", "ENGINE")
    if action == "WAIT" and not waiting:
        # Never « ATTENDRE » alone: say it plainly when nothing concrete is pending.
        wait("🔎", "Qu'au moins deux familles confirment la même direction",
             "Aujourd'hui, aucune configuration ne réunit structure, flux et levier.", "ENGINE")

    # 3. What would change the reading.
    bullish: list[str] = []
    bearish: list[str] = []
    if resistance:
        bullish.append(f"{asset} clôture ({tf}) au-dessus de {usd(resistance)}")
    for item in decision.to_buy:
        text = plain(item).rstrip(".")
        if "avantage" not in text and len(bullish) < 2:
            bullish.append(text)
    if support:
        bearish.append(f"{asset} clôture ({tf}) sous {usd(support)}")
    for item in decision.to_worsen:
        text = plain(item).rstrip(".")
        if len(bearish) < 2 and text not in bearish:
            bearish.append(text)
    invalidation = None
    if support and trend_key == "UP":
        invalidation = (f"Cette lecture haussière ne serait plus valable après une clôture {tf} "
                        f"sous {usd(support)} (support).")
    elif resistance and trend_key == "DOWN":
        invalidation = (f"Cette lecture baissière ne serait plus valable après une clôture {tf} "
                        f"au-dessus de {usd(resistance)} (résistance).")

    # 4. Contradictions, stated.
    positives, cautions = [], []
    for cards_ in per_family.values():
        lead = cards_[0] if cards_ else None
        if lead is None:
            continue
        if lead["tone"] == GREEN:
            positives.append(lead["title"])
        elif lead["tone"] in {RED, ORANGE}:
            cautions.append(lead["title"])
    contradictions = None
    if positives and cautions:
        contradictions = {"sentence": "Les signaux restent partagés.",
                          "positives": positives[:3], "cautions": cautions[:3]}

    # 5. Headline: what the market does, then what holds the decision.
    trend_text = {"UP": "La tendance reste haussière", "DOWN": "La tendance reste baissière"}.get(
        trend_key, "Le marché n'a pas de direction nette")
    if action == "BUY":
        headline = f"{trend_text} et plusieurs familles confirment : configuration favorable."
    elif action == "SELL":
        headline = f"{trend_text} et le risque domine : les conditions d'un maintien ne sont plus réunies."
    elif action == "INSUFFICIENT_DATA":
        headline = "Trop de données manquent ou sont anciennes pour conclure honnêtement."
    else:
        caution = next((w for w in why if w["family"] and w["tone"] in {RED, ORANGE}), None)
        if caution is not None:
            headline = f"{trend_text}, mais {caution['clause']} : entrée pas encore confirmée."
        elif no_edge:
            headline = (f"{trend_text}, mais aucun signal n'a prouvé son avantage : "
                        "le moteur préfère attendre.")
        else:
            headline = f"{trend_text}, sans confirmation suffisante pour agir."

    return {
        "verdict": {"action": action, "emoji": emoji, "label": label},
        "horizon": HORIZON_FR.get(decision.horizon, decision.horizon),
        "headline": headline,
        "why": why,
        "waiting_for": waiting,
        "change_mind": {"bullish": bullish[:2], "bearish": bearish[:2]},
        "invalidation": invalidation,
        "validation_note": validation_note,
        "contradictions": contradictions,
        "families": per_family,
        "data": data_quality(decision, now),
        "market": market_clarity(decision, trend_key, contradictions),
        "as_of": now.isoformat() if now else None,
    }


# --- two readings that are never merged -----------------------------------------------------


FAMILY_FR = {TECHNICAL: "technique", DERIVATIVES: "dérivés", FLOWS: "flux", MACRO: "macro",
             CYCLE: "cycle"}


def data_quality(decision: Any, now: datetime | None) -> dict[str, Any]:
    """How much we can trust the inputs - not whether the market is clear."""

    old = [FAMILY_FR[k] for k, f in decision.families.items()
           if k in FAMILY_FR and f.usable and f.freshness in {"STALE", "OLD"}]
    missing = [FAMILY_FR[k] for k, f in decision.families.items() if k in FAMILY_FR and not f.usable]
    if missing:
        return {"emoji": "🔴" if len(missing) > 1 else "🟠", "label": "Données incomplètes",
                "detail": "Indisponible : " + ", ".join(missing) + "."}
    if old:
        return {"emoji": "🟠", "label": "Certaines données anciennes",
                "detail": "Anciennes : " + ", ".join(old) + " (signalées comme telles)."}
    return {"emoji": "🟢", "label": "Données fraîches",
            "detail": f"Qualité des données {decision.data_quality} %."}


def market_clarity(decision: Any, trend_key: str | None,
                   contradictions: dict[str, Any] | None) -> dict[str, Any]:
    """Whether the market gives a clear reading - independent from data quality."""

    action = decision.action.value
    if action in {"BUY", "SELL"}:
        return {"emoji": "🟢", "label": "Direction nette", "detail": "Plusieurs familles concordent."}
    if contradictions:
        return {"emoji": "🟠", "label": "Marché incertain", "detail": "Les familles se contredisent."}
    if trend_key in {None, "FLAT"}:
        return {"emoji": "⚪", "label": "Sans direction", "detail": "Aucune tendance nette."}
    return {"emoji": "🟠", "label": "Direction non confirmée",
            "detail": "La tendance existe, la confirmation manque."}

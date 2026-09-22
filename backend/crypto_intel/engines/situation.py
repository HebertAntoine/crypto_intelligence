"""« 🧭 Résumé de la situation » : ce que fait le prix, avec quoi cela coïncide,
ce qui l'amplifie, ce qui le freine, et pourquoi la décision est ce qu'elle est.

Five roles, never confused (§20 of the brief):

    déclencheur   a driver that moved in the same direction, before or with
                  the move - stated as a coincidence, never as a proven cause
    soutien       real money going the same way (ETF flows, spot buying): it
                  accompanies the move, it does not prove it caused it
    amplificateur a mechanical effect that extends a move already under way
                  (forced liquidations), which is a cause of amplitude only
    contexte      what surrounds the move: an upcoming event, the cycle
    frein         what holds the confirmation back

Two texts come out of the same material: `brief`, four lines at most for the
home, and `sentences`, the full narrative behind « Comprendre le mouvement ».

Two rules hold the text honest:

  * a sentence exists only if the data behind it exists. No driver aligned
    with the move -> « aucune cause dominante ne ressort des données » (§21);
  * « coïncide avec », « s'accompagne de », « peut contribuer à » for a
    correlation; « a mécaniquement amplifié » only for forced liquidations,
    where the mechanism is the trade itself, not an interpretation.

Deterministic: assembled from the family readings, never written by a model.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from .decision_config import CYCLE, DERIVATIVES, FLOWS, MACRO, TECHNICAL
from .factor_semantics import fr_number

UP, DOWN, FLAT = "UP", "DOWN", "FLAT"
#: A driver is « aligned » from this component signal: below, the move is noise.
ALIGNED = 0.3
#: Liquidations worth naming as an amplifier, in dollars over 24 h.
LIQUIDATION_FLOOR = 20e6
#: The home summary is read in about ten seconds: four sentences, this many words.
BRIEF_WORDS = 80

#: Mechanisms stated in general terms - what the driver does to risk assets,
#: never « it caused today's move ».
MECHANISM = {
    "oil_shock": ("la détente du pétrole", "la hausse du pétrole",
                  "ce qui réduit la pression inflationniste attendue",
                  "ce qui ravive la pression inflationniste"),
    "real_yield": ("la baisse des taux réels américains", "la hausse des taux réels américains",
                   "ce qui réduit le coût d'opportunité de détenir un actif sans rendement",
                   "ce qui renchérit le coût d'opportunité de détenir un actif sans rendement"),
    "nominal_yield": ("la détente des rendements obligataires", "la tension des rendements obligataires",
                      "ce qui assouplit les conditions financières",
                      "ce qui durcit les conditions financières"),
    "policy_expectations": ("des anticipations de Fed plus souples",
                            "des anticipations de Fed plus strictes",
                            "ce qui soutient les actifs risqués",
                            "ce qui pèse sur les actifs risqués"),
    "dollar": ("le repli du dollar", "la hausse du dollar",
               "ce qui aide en général les actifs risqués",
               "ce qui pèse en général sur les actifs risqués"),
    "risk_appetite": ("la hausse des actions technologiques", "le repli des actions technologiques",
                      "signe d'un appétit pour le risque plus marqué",
                      "signe d'une aversion au risque plus marquée"),
    "equity_fear": ("le calme retrouvé sur les actions", "la nervosité des marchés actions",
                    "ce qui favorise la prise de risque", "ce qui réduit la prise de risque"),
}
NAMES = {"BTC": "Bitcoin", "ETH": "Ether", "SOL": "Solana"}


def _pct(value: float | None, digits: int = 1) -> str:
    return "—" if value is None else fr_number(value, digits, signed=True) + " %"


def _join(parts: list[str]) -> str:
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:-1]) + " et " + parts[-1]


def _levels(text: str) -> set[str]:
    """The price levels a sentence names, thin spaces removed: {« 87396 », « 120 »}."""

    flat = text.replace(" ", "").replace(" ", "").replace(" ", "")
    return set(re.findall(r"(\d+)\s*\$", flat))


def direction_of(change_24h: float | None, change_7d: float | None) -> str:
    """The move the summary describes: the day, or the week when the day is flat."""

    for change, floor in ((change_24h, 1.0), (change_7d, 2.0)):
        if change is None:
            continue
        if change >= floor:
            return UP
        if change <= -floor:
            return DOWN
    return FLAT


def build(decision: Any, views: dict[str, dict[str, Any]], reading: dict[str, Any], *,
          asset: str, now: datetime | None = None, top_event: Any = None) -> dict[str, Any]:
    families = decision.families
    technical = families.get(TECHNICAL)
    extra = technical.extra if technical is not None else {}
    changes = extra.get("changes") or {}
    change_24h = changes.get("1", changes.get(1))
    change_7d = changes.get("7", changes.get(7))
    move = direction_of(change_24h, change_7d)
    name = NAMES.get(asset, asset)
    roles: dict[str, list[dict[str, str]]] = {
        "triggers": [], "supports": [], "amplifiers": [], "context": [], "brakes": []}
    sentences: list[str] = []
    # Short forms, for the four-line summary the home shows.
    support_words: list[str] = []
    brake_words: list[str] = []

    # 1. What the price just did, with the structure when the engine names one.
    parts = []
    if change_24h is not None:
        parts.append(f"{_pct(change_24h)} sur 24 h")
    if change_7d is not None:
        parts.append(f"{_pct(change_7d)} sur 7 jours")
    verb = {UP: "progresse", DOWN: "recule", FLAT: "évolue sans direction nette"}[move]
    first = f"{name} {verb}" + (f" ({_join(parts)})" if parts else "") + "."
    structure = str(extra.get("structure") or "")
    resistance, support = extra.get("resistance"), extra.get("support")
    if structure == "BREAKOUT_CONFIRMED":
        first = first[:-1] + " et s'est maintenu au-dessus d'une résistance qu'il avait échoué à franchir."
    elif structure == "BREAKOUT_PENDING" and resistance:
        first = first[:-1] + f" et vient tester la résistance de {fr_number(resistance, 0)} $."
    elif structure == "BREAKDOWN_CONFIRMED":
        first = first[:-1] + " après avoir cassé un support important."
    elif structure == "RANGE" and support and resistance:
        first = first[:-1] + (f", toujours entre {fr_number(support, 0)} $ et "
                              f"{fr_number(resistance, 0)} $.")
    sentences.append(first)

    # 2. Drivers that moved with it - coincidence, with the general mechanism.
    macro = families.get(MACRO)
    aligned: list[tuple[float, str, str]] = []
    against: list[tuple[float, str]] = []
    for component in (macro.components if macro is not None else []):
        words = MECHANISM.get(component.key)
        signal = component.signal or 0.0
        if words is None or not component.active or abs(signal) < ALIGNED:
            continue
        favourable = signal > 0
        label = words[0] if favourable else words[1]
        mechanism = words[2] if favourable else words[3]
        helps_move = (favourable and move == UP) or (not favourable and move == DOWN)
        if helps_move:
            aligned.append((abs(signal) * component.weight, label, mechanism))
        elif move != FLAT:
            against.append((abs(signal) * component.weight, label))
    aligned.sort(reverse=True)
    against.sort(reverse=True)
    for _, label, mechanism in aligned[:2]:
        roles["triggers"].append({"emoji": "🏛️", "text": f"{label[0].upper()}{label[1:]} — {mechanism}"})
        support_words.append(label)
    if aligned:
        lead = aligned[0]
        others = [label for _, label, _ in aligned[1:2]]
        subject = _join([lead[1], *others])
        sentences.append(
            f"Ce mouvement coïncide avec {subject}, {lead[2]}.")

    # 3. Flows: real money, stated as demand, never as a cause of the move.
    flows = families.get(FLOWS)
    etf = next((m for m in (flows.metrics if flows is not None else []) if m.key == "etf.net_flow"), None)
    streak = next((m for m in (flows.metrics if flows is not None else []) if m.key == "etf.streak"), None)
    if etf is not None and etf.usable and etf.value is not None:
        repeated = streak is not None and streak.usable and "séance" in (streak.display_value or "") \
            and not streak.display_value.startswith("1 ")
        side = "des entrées" if etf.value > 0 else "des sorties"
        if repeated:
            sentences.append(
                f"Les ETF au comptant enregistrent {side} ({etf.display_value}, {streak.display_value}), "
                "signe d'une demande institutionnelle qui " +
                ("revient." if etf.value > 0 else "se retire."))
        else:
            sentences.append(
                f"Les ETF au comptant affichent {etf.display_value} sur la dernière séance publiée, "
                "une séance isolée qui ne fait pas encore une tendance.")
        # Real money that goes the same way is a support, not a trigger: it
        # accompanies the move without proving it started it.
        with_move = (etf.value > 0) == (move == UP) and move != FLAT
        roles["supports" if with_move else "brakes"].append(
            {"emoji": "💰", "text": f"Flux ETF {etf.display_value}"})
        if with_move:
            support_words.insert(0, "les flux ETF")
        else:
            brake_words.append("des ETF qui vont en sens inverse")

    spot = (flows.extra.get("spot") if flows is not None else None) or {}
    share = spot.get("share")
    if share is not None and (share >= 0.52 or share <= 0.48):
        buyers = share >= 0.52
        with_move = buyers == (move == UP) and move != FLAT
        roles["supports" if with_move else "brakes"].append(
            {"emoji": "🪙", "text": f"{fr_number(share * 100, 0)} % d'achats agressifs au comptant"})

    # 4. Amplifier: forced liquidations are mechanical, not an interpretation.
    derivatives = families.get(DERIVATIVES)
    liquidations = (derivatives.extra.get("liquidations") if derivatives is not None else None) or {}
    day = liquidations.get("24h") or {}
    dominance = liquidations.get("dominance")
    amount = day.get("short_usd" if dominance == "SHORTS" else "long_usd") or 0
    if day.get("covered_hours") and dominance in {"SHORTS", "LONGS"} and amount >= LIQUIDATION_FLOOR \
            and ((dominance == "SHORTS" and move == UP) or (dominance == "LONGS" and move == DOWN)):
        who = "vendeuses" if dominance == "SHORTS" else "acheteuses"
        sentences.append(
            f"La fermeture forcée de positions {who} ({fr_number(amount / 1e6, 0)} M$ sur 24 h) a "
            f"mécaniquement amplifié {'la hausse' if move == UP else 'la baisse'} : ces positions "
            "se rachètent au prix du marché.")
        roles["amplifiers"].append(
            {"emoji": "⚡", "text": f"Liquidations {who} : {fr_number(amount / 1e6, 0)} M$ sur 24 h"})

    # 5. Context and brakes.
    if top_event is not None and getattr(top_event, "at", None) is not None:
        roles["context"].append({"emoji": "📅", "text": f"{top_event.title} {top_event.delay}"})
    cycle = (families.get(CYCLE).extra.get("cycle") if families.get(CYCLE) is not None else None) or {}
    if cycle.get("phase_label"):
        roles["context"].append({"emoji": "🔄", "text": f"Cycle : {cycle['phase_label'].lower()}"})
    brakes: list[str] = []
    if (views.get(TECHNICAL, {}).get("timing") or {}).get("stretched"):
        brakes.append("un mouvement déjà étiré à court terme")
        brake_words.append("un mouvement déjà étiré à court terme")
        roles["brakes"].append({"emoji": "🔥", "text": "Mouvement étiré à court terme"})
    if views.get(TECHNICAL, {}).get("near_resistance") and resistance:
        brakes.append(f"une résistance à {fr_number(resistance, 0)} $ toujours pas franchie en clôture")
        brake_words.append(f"une résistance à {fr_number(resistance, 0)} $ qui tient")
        roles["brakes"].append({"emoji": "🧱", "text": f"Résistance {fr_number(resistance, 0)} $"})
    if views.get(DERIVATIVES, {}).get("crowded"):
        brakes.append("un levier tendu")
        brake_words.append("un levier tendu")
        roles["brakes"].append({"emoji": "🔥", "text": "Levier tendu"})
    for _, label in against[:1]:
        brakes.append(label)
        brake_words.append(label)
        roles["brakes"].append({"emoji": "🏛️", "text": f"{label[0].upper()}{label[1:]}"})
    if brakes:
        sentences.append(f"En face, {_join(brakes[:3])} : le mouvement n'est pas encore confirmé.")

    # 6. No dominant cause - said plainly rather than filled in.
    dominant = bool(aligned) or bool(roles["amplifiers"]) or (etf is not None and etf.usable)
    if not dominant:
        sentences.insert(1, "Aucune cause dominante ne ressort des données : plusieurs facteurs "
                            "coïncident avec le mouvement sans qu'une explication unique puisse "
                            "être établie.")

    # 7. Why the decision follows.
    verdict = reading["verdict"]["label"]
    waiting = reading.get("waiting_for") or []
    first_wait = waiting[0] if waiting else None
    tail = ""
    if first_wait is not None:
        if first_wait["kind"] == "EVENT":  # a title keeps its capital letter
            tail = f" : nous attendons {first_wait['text']}, puis la réaction du marché"
        else:
            text = f"{first_wait['text'][0].lower()}{first_wait['text'][1:]}"
            tail = f" : nous attendons {text}"
    sentences.append(
        f"C'est pourquoi la décision reste {verdict} à {reading['horizon']}{tail}.")

    brief = _brief(name, verb, parts, support_words, brake_words, bool(roles["amplifiers"]),
                   dominant, verdict, reading, first_wait)

    return {
        "brief": brief,
        "text": " ".join(sentences[:6]),
        "sentences": sentences[:6],
        "move": move,
        "dominant_cause": dominant,
        "roles": roles,
        "labels": {"triggers": "Déclencheurs possibles", "supports": "Soutiens",
                   "amplifiers": "Amplificateur", "context": "Contexte",
                   "brakes": "Ce qui freine"},
    }


def _brief(name: str, verb: str, parts: list[str], supports: list[str], brakes: list[str],
           amplified: bool, dominant: bool, verdict: str, reading: dict[str, Any],
           first_wait: dict[str, Any] | None) -> str:
    """The home summary: what moved, what goes with it, what holds it back, what we wait for.

    Four sentences at most and about eighty words: the reader has ten seconds.
    The full narrative, with every role, stays one tap away.
    """

    # A brake that names the level we are waiting for says it twice: the
    # condition below the summary already carries it.
    if first_wait is not None:
        awaited = _levels(first_wait["text"])
        if awaited:
            brakes = [text for text in brakes if not (awaited & _levels(text))]

    def assemble(support_count: int, brake_count: int, with_amplifier: bool) -> str:
        lines = [f"{name} {verb}" + (f" ({_join(parts)})" if parts else "") + "."]
        chosen = supports[:support_count]
        if chosen:
            subject = _join(chosen)
            verb_fr = "accompagnent" if len(chosen) > 1 else "accompagne"
            lines.append(f"{subject[0].upper()}{subject[1:]} {verb_fr} le mouvement"
                         + (", que des liquidations forcées ont amplifié." if with_amplifier
                            else "."))
        elif with_amplifier:
            lines.append("Des liquidations forcées ont amplifié le mouvement.")
        elif not dominant:
            lines.append("Aucune cause dominante ne ressort des données.")
        if brakes[:brake_count]:
            # Noun phrases throughout, so the list never breaks the sentence.
            # « En revanche » only answers something: without a named support
            # there is nothing to contrast with.
            opening = "En revanche" if (chosen or with_amplifier) else "Ce qui freine"
            lines.append(f"{opening} : {_join(brakes[:brake_count])}.")
        if first_wait is not None:
            text = first_wait["text"] if first_wait["kind"] == "EVENT" else \
                f"{first_wait['text'][0].lower()}{first_wait['text'][1:]}"
            lines.append(f"Nous attendons {text}.")
        else:
            lines.append(f"La décision est {verdict} à {reading['horizon']}.")
        return " ".join(lines)

    # Drop the least essential material first: a second support, then a second
    # brake, then the amplifier clause. What we wait for is never dropped.
    for supports_kept, brakes_kept, keep_amplifier in ((2, 2, True), (1, 2, True), (1, 1, True),
                                                       (1, 1, False), (0, 1, False)):
        text = assemble(supports_kept, brakes_kept, amplified and keep_amplifier)
        if len(text.split()) <= BRIEF_WORDS:
            return text
    return text

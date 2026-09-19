"""Turn the scored families into what a reader can take in at a glance.

Nothing here changes a score or a decision. It reads them and answers three
questions that used to be blurred on screen:

    TREND          where the market is going        📈 ➡️ 📉
    ENTRY QUALITY  whether now is a good moment      🟢 🟠 🔴
    RISK           how badly it could go wrong       🟢 🟠 🔴

An RSI of 77 in an uptrend is the canonical case: the trend is up, the entry is
stretched. Showing it as simply "favourable" mixed the two.

Each family also gets a layout: grouped sections instead of one large card per
value, a two-to-three point reading, two to four precise triggers, and a home
line with one key figure. Priority (1 now, 2 confirmation, 3 detail) is
recomputed every time, so a fresh surprise climbs and a stale print sinks.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from .decision_config import (
    DERIVATIVES,
    FAMILY_EMOJI,
    FAMILY_LABEL,
    FLOWS,
    LIQUIDITY,
    MACRO,
    ONCHAIN,
    TECHNICAL,
)
from .decision_families import DataStatus, FamilyScore, FamilyState, MetricReading
from .factor_semantics import fr_number

GREEN, ORANGE, RED, YELLOW, WHITE = "GREEN", "ORANGE", "RED", "YELLOW", "WHITE"
#: Measures no connected source provides; stated once, never a warning.
STRUCTURAL_GAPS = frozenset({"liquidations"})
_TONE_EMOJI = {GREEN: "🟢", ORANGE: "🟠", RED: "🔴", YELLOW: "🟡", WHITE: "⚪"}


def _usd(value: float | None, quote: str = "USDT") -> str:
    if value is None:
        return "—"
    return f"{fr_number(value, 0 if abs(value) >= 100 else 2)} $"


def _metric(family: FamilyScore, key: str) -> MetricReading | None:
    return next((m for m in family.metrics if m.key == key), None)


def _component(family: FamilyScore, key: str):
    return next((c for c in family.components if c.key == key and c.active), None)


def _row(label: str, value: str, tone: str = WHITE, metric: str | None = None,
         detail: str = "") -> dict[str, Any]:
    return {"label": label, "value": value, "tone": tone, "metric": metric, "detail": detail}


def _metric_row(reading: MetricReading | None, label: str | None = None) -> dict[str, Any] | None:
    if reading is None:
        return None
    if reading.status is DataStatus.NOT_APPLICABLE:
        return _row(label or reading.label, "Non applicable", WHITE, reading.key)
    if not reading.usable:
        text = "Périmée" if reading.status is DataStatus.STALE else "Source indisponible"
        return _row(label or reading.label, f"⚪ {text}", WHITE, reading.key)
    # The value stays short; its change goes on a second, smaller line.
    value = reading.display_value
    tone = {
        "FAVORABLE": GREEN, "UNFAVORABLE": RED, "CAUTION": ORANGE,
        "NEUTRAL": YELLOW, "CONTEXT": WHITE,
    }.get(reading.state, WHITE)
    return _row(label or reading.label, value, tone, reading.key, reading.delta_label)


def _section(emoji: str, title: str, rows: list[dict[str, Any] | None], *,
             verdict: str = "", tone: str = WHITE, sentence: str = "", why: str = "",
             secondary: bool = False) -> dict[str, Any]:
    return {
        "emoji": emoji,
        "title": title,
        "verdict": verdict,
        "tone": tone,
        "sentence": sentence,
        "why": why,
        "rows": [r for r in rows if r is not None],
        "secondary": secondary,
    }


# ---------------------------------------------------------------------------
# Technical & structure
# ---------------------------------------------------------------------------


def _trend(family: FamilyScore) -> tuple[str, str, str]:
    """(emoji, label, key) from the moving averages and the confirmed structure."""

    signal = float(family.extra.get("trend_signal") or 0.0)
    structure = str(family.extra.get("structure") or "UNCLEAR")
    up = signal >= 0.25 or structure in {"TREND_UP", "BREAKOUT_CONFIRMED"}
    down = signal <= -0.25 or structure in {"TREND_DOWN", "BREAKDOWN_CONFIRMED"}
    if up and not down:
        return "📈", "Haussière", "UP"
    if down and not up:
        return "📉", "Baissière", "DOWN"
    return "➡️", "Neutre", "FLAT"


def _momentum(rsi: float | None, trend_key: str) -> tuple[str, str, str]:
    """(label, tone, metric state). Stretched is caution, not a verdict on the trend."""

    if rsi is None:
        return "Momentum indisponible", WHITE, "UNKNOWN"
    if rsi >= 70:
        return "Momentum étiré", ORANGE, "CAUTION"
    if rsi <= 30:
        return "Survente", ORANGE, "CAUTION"
    if trend_key == "UP" and rsi >= 55:
        return "Momentum sain", GREEN, "FAVORABLE"
    if trend_key == "DOWN" and rsi <= 45:
        return "Momentum baissier", RED, "UNFAVORABLE"
    return "Momentum neutre", YELLOW, "NEUTRAL"


def present_technical(family: FamilyScore) -> dict[str, Any]:
    extra = family.extra
    if not family.usable and not extra:
        return _unavailable_view(family)
    trend_emoji, trend_label, trend_key = _trend(family)
    rsi = extra.get("rsi")
    momentum, momentum_tone, momentum_state = _momentum(rsi, trend_key)
    price = extra.get("price")
    support, resistance = extra.get("support"), extra.get("resistance")
    kind, fast, slow = extra.get("ma_kind", "EMA"), extra.get("fast", 20), extra.get("slow", 50)
    near_resistance = bool(price and resistance and 0 <= (resistance - price) / price <= 0.02)
    above_resistance = bool(price and resistance and price > resistance)

    rsi_metric = _metric(family, "technical.rsi")
    if rsi_metric is not None and rsi_metric.usable:
        rsi_metric.state = momentum_state
        rsi_metric.priority = 1 if momentum_state == "CAUTION" else 2

    # Bollinger: say what is measured. Expanded bands are not "tight".
    bw_pct = extra.get("bollinger_percentile")
    bollinger = _metric(family, "technical.bollinger_bandwidth")
    if bw_pct is None:
        vol_label, vol_tone, vol_sentence = "Volatilité indisponible", WHITE, ""
    elif bw_pct >= 85:
        vol_label, vol_tone = "Volatilité élevée", ORANGE
        vol_sentence = (
            f"Bandes de Bollinger en expansion ({fr_number(bw_pct, 0)}e centile) : "
            "le marché est déjà en mouvement ample."
        )
    elif bw_pct <= 15:
        vol_label, vol_tone = "Volatilité comprimée", YELLOW
        vol_sentence = (
            f"Bandes de Bollinger resserrées ({fr_number(bw_pct, 0)}e centile) : un "
            "mouvement ample peut se préparer, sans en dire le sens."
        )
    else:
        vol_label, vol_tone = "Volatilité normale", GREEN
        vol_sentence = f"Bandes de Bollinger au {fr_number(bw_pct, 0)}e centile."
    if bollinger is not None:
        bollinger.why = vol_sentence or bollinger.why
        bollinger.state = "CAUTION" if vol_tone == ORANGE else "CONTEXT"

    changes = extra.get("changes") or {}
    perf = " · ".join(
        f"{label} {fr_number(changes[d], 1, signed=True)} %"
        for d, label in ((1, "24 h"), (7, "7 j"), (30, "30 j"))
        if changes.get(d) is not None
    )

    structure_label = extra.get("structure_label", "—")
    sections = [
        _section(
            "📈", "Tendance & structure",
            [
                _row("Prix (BTC/USDT)" if family.extra.get("quote") else "Prix", _usd(price)),
                _row(f"{kind}{fast}", _usd(extra.get("fast_ma"))),
                _row(f"{kind}{slow}", _usd(extra.get("slow_ma"))),
                _row("🧱 Structure", structure_label,
                     GREEN if trend_key == "UP" else RED if trend_key == "DOWN" else YELLOW),
                _row("🟢 Support", _usd(support), GREEN) if support else None,
                (_row("🧱 Ancienne résistance (franchie)", _usd(resistance), GREEN)
                 if above_resistance else _row("🔴 Résistance", _usd(resistance), RED))
                if resistance else None,
            ],
            verdict=f"{trend_emoji} Tendance {trend_label.lower()}",
            tone=GREEN if trend_key == "UP" else RED if trend_key == "DOWN" else YELLOW,
            why="Les niveaux sont calculés sur la paire en dollars (USDT), pas sur le prix en euros.",
        ),
        _section(
            "🔥", "Momentum",
            [_metric_row(rsi_metric, "RSI 14")],
            verdict=momentum, tone=momentum_tone,
            sentence=(
                "La tendance reste forte, mais le mouvement est déjà avancé."
                if momentum_state == "CAUTION" and trend_key == "UP" and (rsi or 0) >= 70
                else "Le marché est survendu : un rebond technique est possible."
                if momentum_state == "CAUTION"
                else ""
            ),
            why="Au-dessus de 70, le mouvement est étiré : le suivre maintenant, c'est acheter tard.",
        ),
        _section(
            "🌪️", "Volatilité",
            [
                _metric_row(_metric(family, "technical.atr_pct"), "ATR"),
                _metric_row(_metric(family, "technical.realized_vol"), "Volatilité réalisée"),
                _metric_row(bollinger, "Largeur de Bollinger"),
            ],
            verdict=vol_label, tone=vol_tone, sentence=vol_sentence, secondary=True,
        ),
        _section("📅", "Performance", [_row("Variation", perf or "—")], secondary=True),
    ]
    dominance = _metric(family, "market.dominance")
    if dominance is not None:
        sections.append(_section("👑", "Dominance BTC", [_metric_row(dominance)], secondary=True))

    lecture = [f"{trend_emoji} Structure {'toujours ' if trend_key != 'FLAT' else ''}{trend_label.lower()}."]
    if momentum_state == "CAUTION":
        lecture.append(f"🔥 {momentum} (RSI {fr_number(rsi or 0, 0)}).")
    if resistance and not above_resistance:
        lecture.append(f"🧱 La résistance à {_usd(resistance)} reste la zone clé.")
    elif support:
        lecture.append(f"🧱 Le support à {_usd(support)} reste la zone clé.")

    triggers = []
    if extra.get("fast_ma"):
        triggers.append(
            f"📉 Clôture sous l'{kind}{fast} ({_usd(extra['fast_ma'])})."
            if trend_key != "DOWN"
            else f"📈 Clôture au-dessus de l'{kind}{fast} ({_usd(extra['fast_ma'])})."
        )
    if support and trend_key != "DOWN":
        triggers.append(f"🧱 Cassure du support {_usd(support)}.")
    if resistance and trend_key == "DOWN":
        triggers.append(f"🧱 Reprise de la résistance {_usd(resistance)}.")
    if momentum_state == "CAUTION" and (rsi or 0) >= 70:
        triggers.append("🔥 Un repli du RSI sous 70 sans casser la structure assainirait l'entrée.")

    stretched = momentum_state == "CAUTION" and (rsi or 0) >= 70
    status = f"{trend_label}{' mais étirée' if stretched and trend_key == 'UP' else ''}"
    key_info = f"RSI {fr_number(rsi, 0)}" if rsi is not None else ""
    if near_resistance:
        key_info += " · résistance proche"
    return {
        "sections": sections,
        "lecture": lecture[:3],
        "changes": triggers[:4],
        "home": {
            "status": status,
            "tone": ORANGE if stretched else GREEN if trend_key == "UP" else RED if trend_key == "DOWN" else YELLOW,
            "key_info": key_info,
            "status_emoji": trend_emoji,
        },
        "trend": {"emoji": trend_emoji, "label": trend_label, "key": trend_key},
        "momentum": {"label": momentum, "tone": momentum_tone, "stretched": stretched},
        "near_resistance": near_resistance,
    }


# ---------------------------------------------------------------------------
# Derivatives
# ---------------------------------------------------------------------------

_CROWDING_TONE = {
    "CROWDED_LONGS": RED, "CROWDED_SHORTS": ORANGE, "NEW_SHORTS": RED,
    "NEW_LONGS": GREEN, "SHORT_COVERING": YELLOW, "DELEVERAGING": YELLOW,
    "QUIET": GREEN, "UNKNOWN": WHITE,
}
_CROWDING_SHORT = {
    "CROWDED_LONGS": "De nouveaux longs utilisent beaucoup de levier : la hausse devient plus fragile.",
    "NEW_LONGS": "De nouvelles positions acheteuses accompagnent la hausse sans excès.",
    "SHORT_COVERING": "Des vendeurs se couvrent : une hausse qui dure souvent moins.",
    "NEW_SHORTS": "De nouveaux shorts accompagnent la baisse : pression directionnelle.",
    "CROWDED_SHORTS": "Les shorts paient cher : un rachat forcé peut provoquer un rebond brutal.",
    "DELEVERAGING": "Le levier se purge : prix et positions baissent ensemble.",
    "QUIET": "Ni le prix ni le levier ne bougent nettement.",
    "UNKNOWN": "Données de levier insuffisantes pour conclure.",
}


def present_derivatives(family: FamilyScore) -> dict[str, Any]:
    extra = family.extra
    crowding = str(extra.get("crowding") or "UNKNOWN")
    funding_pct = extra.get("funding_percentile")
    oi_pct = extra.get("oi_percentile")
    oi = next((m for m in family.metrics if m.key.startswith("oi.")), None)
    funding = _metric(family, "funding.rate")
    crowded = crowding in {"CROWDED_LONGS", "CROWDED_SHORTS"}
    # Open interest alone is context. It only takes a colour from the
    # combination with price and funding.
    if oi is not None and oi.usable:
        oi.state = oi.state if crowded or crowding in {"NEW_SHORTS", "NEW_LONGS"} else "CONTEXT"
        oi.priority = 1 if crowded else 2
    if funding is not None and funding.usable:
        funding.priority = 1 if funding_pct is not None and funding_pct >= 85 else 2
        if funding_pct is not None and funding_pct < 85 and funding_pct > 15:
            funding.state = "CONTEXT"
    for key in ("derivatives.basis_pct", "dvol.index"):
        reading = _metric(family, key)
        if reading is not None and reading.usable:
            reading.state = "CONTEXT"
            reading.priority = 3

    crowding_label = str(extra.get("crowding_label") or "Indéterminé")
    positioning = _section(
        "📈", "Positionnement & levier",
        [
            _metric_row(oi, "Open interest"),
            _row("Rang historique de l'OI", f"{fr_number(oi_pct, 0)}e") if oi_pct is not None else None,
            _metric_row(funding, "Funding (8 h)"),
            _row("Rang du funding (1 an)", f"{fr_number(funding_pct, 0)}e",
                 RED if funding_pct is not None and funding_pct >= 85 else WHITE)
            if funding_pct is not None else None,
            _row("Relation prix / OI", crowding_label, _CROWDING_TONE.get(crowding, WHITE)),
        ],
        verdict="🔴 Levier encombré" if crowded else "",
        tone=_CROWDING_TONE.get(crowding, WHITE),
        why="Le signal vient de la combinaison prix + open interest + funding, jamais d'une seule mesure.",
    )
    secondary = _section(
        "📐", "Base & volatilité implicite",
        [_metric_row(_metric(family, "derivatives.basis_pct"), "📐 Base"),
         _metric_row(_metric(family, "dvol.index"), "🌪️ DVOL")],
        secondary=True,
    )
    liquidations = _section(
        "💥", "Liquidations",
        [_row("Liquidations", "⚪ Source indisponible")], secondary=True,
    )

    lecture = [f"📈 {_CROWDING_SHORT.get(crowding, '')}"]
    if funding_pct is not None and funding_pct >= 85:
        lecture.append(f"💰 Funding au {fr_number(funding_pct, 0)}e centile : les longs paient plus que d'habitude.")
    elif oi_pct is not None:
        lecture.append(f"📊 Open interest au {fr_number(oi_pct, 0)}e centile historique : contexte, pas un signal seul.")
    triggers = []
    if crowding == "CROWDED_LONGS":
        triggers.append("📈 Normalisation du funding et de l'OI sans baisse du prix.")
        triggers.append("💥 Une baisse rapide avec des longs encombrés pourrait forcer des liquidations.")
    elif crowding == "NEW_SHORTS":
        triggers.append("📉 Une hausse de l'OI qui accompagne encore la baisse confirmerait la pression.")
    elif funding_pct is not None and funding_pct >= 85:
        triggers.append("💰 Un funding qui revient vers sa normale.")
    elif crowding in {"NEW_LONGS", "QUIET", "SHORT_COVERING"}:
        if funding_pct is not None:
            triggers.append(
                f"💰 Un funding au-delà du 85e centile (aujourd'hui {fr_number(funding_pct, 0)}e) "
                "signalerait un levier excessif."
            )
        triggers.append("📉 Une hausse de l'open interest pendant une baisse du prix : nouveaux shorts.")

    if crowded:
        status, tone = "Risque élevé", RED
    elif not family.usable:
        status, tone = "Données insuffisantes", WHITE
    else:
        status, tone = crowding_label, _CROWDING_TONE.get(crowding, WHITE)
    parts = []
    if funding_pct is not None:
        parts.append(f"Funding au {fr_number(funding_pct, 0)}e centile")
    if oi is not None and oi.usable and oi.delta_label:
        parts.append(f"OI {oi.delta_label}")
    key_info = " · ".join(parts)
    return {
        "sections": [positioning, secondary, liquidations],
        "lecture": [line for line in lecture if line.strip("📈 ")][:3],
        "changes": triggers[:4],
        "home": {"status": status, "tone": tone, "key_info": key_info,
                 "status_emoji": _TONE_EMOJI.get(tone, "")},
        "crowded": crowded,
    }


# ---------------------------------------------------------------------------
# ETF & spot
# ---------------------------------------------------------------------------


def present_flows(family: FamilyScore) -> dict[str, Any]:
    etf_c, spot_c = _component(family, "etf"), _component(family, "spot")
    etf_metric = _metric(family, "etf.net_flow")

    def lean(component, pos: str, neg: str, flat: str) -> tuple[str, int]:
        if component is None:
            return "indisponible", 0
        signal = component.signal or 0
        if signal >= 0.2:
            return pos, 1
        if signal <= -0.2:
            return neg, -1
        return flat, 0

    etf_word, etf_dir = lean(etf_c, "positifs", "négatifs", "irréguliers")
    if etf_metric is not None and etf_metric.status is DataStatus.NOT_APPLICABLE:
        etf_word = "non applicable"
    spot_word, spot_dir = lean(spot_c, "acheteur", "vendeur", "neutre")

    if etf_c is None and spot_c is not None and spot_dir == 0:
        verdict, tone, sentence = "🟡 Flux global neutre", YELLOW, "Pression spot équilibrée."
    elif etf_dir == spot_dir == 1 or (etf_c is None and spot_dir == 1):
        verdict, tone = "🟢 Flux global positif", GREEN
        sentence = "Demande nette confirmée." if etf_c else "Demande spot positive (pas d'ETF pour cet actif)."
    elif etf_dir == spot_dir == -1 or (etf_c is None and spot_dir == -1):
        verdict, tone = "🔴 Flux global négatif", RED
        sentence = "Offre nette : les capitaux sortent."
    elif etf_c is None and spot_c is None:
        verdict, tone, sentence = "⚪ Données insuffisantes", WHITE, ""
    else:
        verdict, tone = "🟠 Flux global mitigé", ORANGE
        sentence = (
            f"Demande spot {'positive' if spot_dir > 0 else 'négative' if spot_dir < 0 else 'neutre'}, "
            f"mais flux ETF {etf_word}."
        )
    # The family headline must not say "capital is flowing in" when the two
    # sources disagree.
    family.headline = sentence or family.headline

    streak = _metric(family, "etf.streak")
    sections = [
        _section(
            "💸", "Flux ETF & pression spot",
            [
                _metric_row(etf_metric, "💸 Flux ETF cumulés"),
                _metric_row(_metric(family, "spot.taker_buy_ratio"), "🪙 Achats agressifs au comptant"),
            ],
            verdict=verdict, tone=tone, sentence=sentence,
            why="Les ETF et le spot disent la même chose quand la demande est réelle ; sinon, prudence.",
        ),
    ]
    if streak is not None and streak.usable:
        sections.append(_section("🔁", "Série en cours", [_row("Séances", streak.display_value)], secondary=True))
    triggers = [c.turn_condition for c in (etf_c, spot_c) if c is not None and c.turn_condition]
    return {
        "sections": sections,
        "lecture": [f"💸 ETF : {etf_word}.", f"🪙 Spot : {spot_word}.", f"{verdict}."][:3],
        "changes": triggers[:4],
        "home": {
            "status": verdict.split(" ", 1)[1].replace("Flux global ", "").capitalize(),
            "tone": tone,
            "key_info": (
                f"Spot {spot_word}" if etf_c is None else f"Spot {spot_word}, ETF {etf_word}"
            ),
            "status_emoji": verdict.split(" ", 1)[0],
        },
    }


# ---------------------------------------------------------------------------
# Macro - priorities that follow the news
# ---------------------------------------------------------------------------

_MACRO_PRIORITY = {
    "macro.real10y": 1, "macro.dxy": 1, "macro.us2y": 1,
    "macro.vix": 2, "macro.nasdaq": 2, "macro.us10y": 2,
    "macro.sp500": 3, "macro.oil_wti": 3, "macro.yield_curve_10y2y": 3,
    "macro.fed_funds_rate": 3, "macro.cpi": 3, "macro.core_cpi": 3,
    "macro.unemployment": 3,
}
_MACRO_SHORT = {
    "real_yield": "Taux réels", "dollar": "dollar", "policy_expectations": "taux 2 ans",
    "nominal_yield": "taux 10 ans", "equity_fear": "VIX", "risk_appetite": "Nasdaq",
    "oil_shock": "pétrole", "core_inflation": "inflation",
}


def present_macro(family: FamilyScore, as_of) -> dict[str, Any]:
    for reading in family.metrics:
        reading.priority = _MACRO_PRIORITY.get(reading.key, 3)
        # A release inside its impact window climbs to the top, whatever it is.
        if (
            reading.usable
            and as_of is not None
            and reading.available_at is not None
            and reading.publication_estimated
            and as_of - reading.available_at <= timedelta(days=5)
        ):
            reading.priority = 1
            reading.note = (reading.note + " " if reading.note else "") + "Publication récente."
    oil = _component(family, "oil_shock")
    if oil is not None:
        metric = _metric(family, "macro.oil_wti")
        if metric is not None:
            metric.priority = 1 if abs(oil.signal or 0) >= 0.5 else 2

    by_priority = {1: [], 2: [], 3: []}
    for reading in family.metrics:
        by_priority[reading.priority].append(_metric_row(reading))
    sections = [
        _section("🎯", "Priorité 1 — Important maintenant", by_priority[1]),
        _section("🔎", "Priorité 2 — Confirmation", by_priority[2], secondary=True),
        _section("🗂️", "Contexte", by_priority[3], secondary=True),
    ]

    active = sorted(
        (c for c in family.components if c.active),
        key=lambda c: abs((c.signal or 0) * c.weight), reverse=True,
    )
    top = [c for c in active if abs(c.signal or 0) >= 0.2][:2]

    def arrow(component) -> str:
        metric = next((m for m in family.metrics if m.key in component.metrics), None)
        if metric is None or metric.delta is None:
            return ""
        return "↑" if metric.delta > 0 else "↓"

    names = [(_MACRO_SHORT.get(c.key, c.label), arrow(c)) for c in top]
    if len(names) == 2 and names[0][1] and names[0][1] == names[1][1]:
        key_info = f"{names[0][0]} + {names[1][0]} {names[0][1]}"
    else:
        key_info = " · ".join(f"{n} {a}".strip() for n, a in names)
    negative = family.state in {FamilyState.NEGATIVE, FamilyState.VERY_NEGATIVE, FamilyState.SLIGHTLY_NEGATIVE}
    positive = family.state in {FamilyState.POSITIVE, FamilyState.VERY_POSITIVE, FamilyState.SLIGHTLY_POSITIVE}
    return {
        "sections": [s for s in sections if s["rows"]],
        "lecture": [c.sentence for c in active[:3]],
        "changes": [c.turn_condition for c in active if c.turn_condition][:4],
        "home": {
            "status": "Défavorable" if negative else "Favorable" if positive else "Neutre",
            "tone": RED if family.state in {FamilyState.NEGATIVE, FamilyState.VERY_NEGATIVE}
            else ORANGE if negative else GREEN if positive else YELLOW,
            "key_info": key_info,
            "status_emoji": "",
        },
        "key_names": names,
    }


def present_liquidity(family: FamilyScore) -> dict[str, Any]:
    regime = family.extra.get("regime_label", "Incertaine")
    rows = [_metric_row(m) for m in family.metrics]
    active = sorted((c for c in family.components if c.active),
                    key=lambda c: abs((c.signal or 0) * c.weight), reverse=True)
    negative = (family.score or 0) < -10
    positive = (family.score or 0) > 10
    return {
        "sections": [_section("💵", "Composantes de la liquidité", rows,
                              verdict=f"Régime : {regime}",
                              tone=RED if negative else GREEN if positive else YELLOW,
                              why=str(family.extra.get("regime_rule", "")))],
        "lecture": [c.sentence for c in active[:3]],
        "changes": [c.turn_condition for c in active if c.turn_condition][:4],
        "home": {"status": regime, "tone": RED if negative else GREEN if positive else YELLOW,
                 "key_info": active[0].label if active else "", "status_emoji": ""},
    }


def _unavailable_view(family: FamilyScore) -> dict[str, Any]:
    return {
        "sections": [_section(FAMILY_EMOJI[family.family], FAMILY_LABEL[family.family],
                              [_row(m.label, "⚪ Source indisponible") for m in family.metrics]
                              or [_row("Données", "⚪ Source indisponible")],
                              verdict="⚪ Données insuffisantes", sentence=family.unavailable_reason)],
        "lecture": [],
        "changes": [],
        "home": {"status": "Données insuffisantes", "tone": WHITE, "key_info": "", "status_emoji": "⚪"},
    }


def present_family(family: FamilyScore, as_of) -> dict[str, Any]:
    if family.family == ONCHAIN or (not family.usable and family.family != TECHNICAL):
        view = _unavailable_view(family)
    elif family.family == TECHNICAL:
        view = present_technical(family) if family.extra else _unavailable_view(family)
    elif family.family == DERIVATIVES:
        view = present_derivatives(family)
    elif family.family == FLOWS:
        view = present_flows(family)
    elif family.family == MACRO:
        view = present_macro(family, as_of)
    else:
        view = present_liquidity(family)
    confidence_label = (
        "Confiance élevée" if family.confidence >= 75
        else "Confiance moyenne" if family.confidence >= 55
        else "Confiance faible"
    )
    issues = []
    # A measure that no source provides (liquidations) has its own line on the
    # page; flagging it on every reading would make the warning meaningless.
    expected = [
        m for m in family.metrics
        if m.status is not DataStatus.NOT_APPLICABLE and m.key not in STRUCTURAL_GAPS
    ]
    if any(m.status is DataStatus.STALE for m in expected):
        issues.append("🕒 Données anciennes")
    missing = [m for m in expected if m.status is DataStatus.UNAVAILABLE]
    if missing and len(missing) < len(expected):
        issues.append("⚠️ Données partielles")
    elif missing:
        issues.append("⚪ Source indisponible")
    home = view.get("home", {})
    if home and not home.get("status_emoji"):
        home["status_emoji"] = _TONE_EMOJI.get(home.get("tone", WHITE), "")
    view["confidence_label"] = confidence_label
    view["data_issues"] = issues
    family.extra["view"] = view
    return view


# ---------------------------------------------------------------------------
# The decision summary
# ---------------------------------------------------------------------------

HOME_FAMILIES = (TECHNICAL, DERIVATIVES, MACRO, FLOWS, ONCHAIN)


def _reason(family: FamilyScore, view: dict[str, Any]) -> dict[str, Any] | None:
    """One home reason: emoji, short title, one line."""

    key = family.family
    home = view.get("home", {})
    if key == MACRO:
        names = view.get("key_names") or []
        if not names:
            return None
        negative = home.get("tone") in {RED, ORANGE}
        words = " et ".join(n for n, _ in names)
        direction = names[0][1] if names else ""
        return {
            "emoji": "🏛️",
            "title": "Conditions financières restrictives" if negative else "Conditions financières plus souples",
            "detail": f"{words[0].upper()}{words[1:]} en {'hausse' if direction == '↑' else 'baisse'}.",
            "tone": home.get("tone", WHITE),
        }
    if key == DERIVATIVES:
        crowding = str(family.extra.get("crowding") or "UNKNOWN")
        titles = {
            "CROWDED_LONGS": ("Levier trop chargé", "Funding élevé + open interest en hausse."),
            "CROWDED_SHORTS": ("Shorts encombrés", "Risque de rachat forcé brutal."),
            "NEW_SHORTS": ("Pression vendeuse à levier", "Nouveaux shorts avec la baisse."),
            "NEW_LONGS": ("Levier sain", "Nouveaux longs sans excès de coût."),
            "SHORT_COVERING": ("Rachat de shorts", "Une hausse portée par des vendeurs qui se couvrent."),
            "DELEVERAGING": ("Levier en purge", "Prix et positions reculent ensemble."),
        }
        funding_pct = family.extra.get("funding_percentile")
        if crowding not in titles and funding_pct is not None and funding_pct >= 85:
            title, detail = "Funding élevé", f"Au {fr_number(funding_pct, 0)}e centile sur un an."
        else:
            title, detail = titles.get(crowding, ("Levier sans excès", home.get("key_info", "")))
        return {"emoji": "📈", "title": title, "detail": detail, "tone": home.get("tone", WHITE)}
    if key == TECHNICAL:
        momentum = view.get("momentum", {})
        trend = view.get("trend", {})
        if momentum.get("stretched"):
            detail = f"Tendance {trend.get('label', '').lower()} mais {home.get('key_info', '')}."
            return {"emoji": "🟠", "title": "Momentum étiré", "detail": detail, "tone": ORANGE}
        return {
            "emoji": trend.get("emoji", "📊"),
            "title": f"Tendance {trend.get('label', '').lower()}",
            "detail": family.headline,
            "tone": home.get("tone", WHITE),
        }
    if key == FLOWS:
        return {"emoji": "💸", "title": f"Flux {home.get('status', '').lower()}",
                "detail": family.headline, "tone": home.get("tone", WHITE)}
    if key == LIQUIDITY:
        return {"emoji": "💵", "title": f"Liquidité {home.get('status', '').lower()}",
                "detail": (view.get("lecture") or [""])[0].split(" : ")[0].lstrip("🏦💧 ") + ".",
                "tone": home.get("tone", WHITE)}
    return None


def summarize(decision: Any, *, as_of: Any = None, top_event: Any = None) -> dict[str, Any]:
    """Trend, entry quality, risk, three reasons, validation, data issues."""

    families: dict[str, FamilyScore] = decision.families
    views = {k: present_family(f, as_of) for k, f in families.items()}
    technical = views.get(TECHNICAL, {})
    trend = technical.get("trend") or {"emoji": "➡️", "label": "Neutre", "key": "FLAT"}
    stretched = bool((technical.get("momentum") or {}).get("stretched"))
    crowded = bool(views.get(DERIVATIVES, {}).get("crowded"))
    dvol_pct = families[DERIVATIVES].extra.get("dvol_percentile") if DERIVATIVES in families else None
    event_score = getattr(top_event, "score", 0.0) if top_event is not None else 0.0
    gate = decision.blocking_gate
    action = decision.action.value

    # Risk: how badly it could go wrong, whatever the direction.
    if crowded or (dvol_pct or 0) >= 85 or event_score >= 0.6 or (
        families.get(MACRO) and families[MACRO].state is FamilyState.VERY_NEGATIVE
    ):
        risk = ("🔴", "Élevé", RED)
    elif event_score >= 0.3 or gate == "CONTRADICTION" or stretched:
        risk = ("🟠", "Modéré", ORANGE)
    else:
        risk = ("🟢", "Faible", GREEN)

    # Entry quality: whether now is a good moment, distinct from the trend.
    if action == "BUY":
        entry = ("🟢", "Favorable", GREEN)
    elif crowded or gate == "EVENT_RISK" or (decision.score or 0) <= -30:
        entry = ("🔴", "Défavorable", RED)
    elif (
        stretched
        or gate in {"CONTRADICTION", "CROWDING", "DATA_QUALITY", "FRESHNESS"}
        or (decision.score or 0) < 15
        or event_score >= 0.3
    ):
        # The missing statistical edge is shown on its own line; it does not
        # make an otherwise clean setup a poor entry.
        entry = ("🟠", "Mitigé", ORANGE)
    else:
        entry = ("🟢", "Favorable", GREEN)

    if action == "INSUFFICIENT_DATA" or gate == "EVENT_RISK":
        sentence = decision.headline
    elif action == "BUY":
        sentence = "Les familles indépendantes confirment une configuration favorable."
    elif action == "SELL":
        sentence = "Le risque s'est nettement dégradé et plusieurs familles le confirment."
    elif trend["key"] == "UP":
        sentence = (
            "La hausse reste présente, mais le point d'entrée est fragile."
            if entry[2] != GREEN
            else "La hausse est saine, mais son avantage n'est pas prouvé statistiquement."
            if action == "WAIT"
            else "La hausse reste présente et le point d'entrée est correct."
        )
    elif trend["key"] == "DOWN":
        sentence = "La tendance reste baissière : pas de point d'entrée à l'achat."
    else:
        sentence = "Pas de direction nette : le marché cherche encore son sens."

    # Three reasons, chosen by weight in the decision - never the validation.
    ranked = sorted(
        (k for k in families if families[k].usable),
        key=lambda k: abs(decision.weights.get(k, 0) * (families[k].score or 0))
        + (0.25 if k == DERIVATIVES and crowded else 0)
        + (0.1 if k == TECHNICAL and stretched else 0),
        reverse=True,
    )
    reasons = [r for r in (_reason(families[k], views[k]) for k in ranked) if r][:3]

    no_edge = any(
        "avantage mesurable" in g.detail for g in decision.gates if g.name == "UNCERTAINTY"
    )
    validation = {
        "status": "NO_EDGE" if no_edge else "OK",
        "message": (
            "Aucun avantage statistique robuste détecté : prudence renforcée."
            if no_edge else "Pas d'alerte de validation."
        ),
    }

    home_families = []
    for key in HOME_FAMILIES:
        if key not in families:
            continue
        home = views[key].get("home", {})
        home_families.append({
            "family": key,
            "emoji": FAMILY_EMOJI[key],
            "name": {TECHNICAL: "Technique", DERIVATIVES: "Dérivés", MACRO: "Macro",
                     FLOWS: "ETF & spot", ONCHAIN: "Baleines & on-chain"}[key],
            "status": home.get("status", ""),
            "status_emoji": home.get("status_emoji", ""),
            "tone": home.get("tone", WHITE),
            "key_info": home.get("key_info", ""),
        })

    issues = []
    for key, view in views.items():
        for issue in view.get("data_issues", []):
            if key == ONCHAIN:
                continue
            issues.append(f"{issue} — {FAMILY_LABEL[key]}")
    confidence = decision.confidence
    return {
        "sentence": sentence,
        "trend": {"emoji": trend["emoji"], "label": trend["label"]},
        "entry_quality": {"emoji": entry[0], "label": entry[1], "tone": entry[2]},
        "risk": {"emoji": risk[0], "label": risk[1], "tone": risk[2]},
        "reasons": reasons,
        "home_families": home_families,
        "validation": validation,
        "confidence_label": (
            "Confiance élevée" if confidence >= 75
            else "Confiance moyenne" if confidence >= 55
            else "Confiance faible"
        ),
        "data_issues": issues[:3],
    }

"""Turn the scored families into what a reader can take in within seconds.

Nothing here changes a score or a decision. It reads them and answers, in order:

    What is the market doing?           trend            📈 ➡️ 📉
    Is now a good moment?               entry quality    🟢 🟠 🔴
    How badly could it go wrong?        risk             🟢 🟠 🔴
    Where are support and resistance?   key levels, in $ (the USDT pair)
    Who takes the initiative on spot?   aggressive buyers vs sellers
    Is leverage dangerous?              positioning, liquidations
    What are central banks doing?       rate, last decision, next meeting
    Where is Bitcoin in its cycle?      a described phase, never a forecast

Six families are shown: Technique, Dérivés, ETF & flux au comptant, Macro & banques
centrales, Cycle, Baleines. Liquidity stays in the engine and in Macro's
advanced data. Each family shows one state, one or two values, one sentence;
everything else sits in "Données avancées", still one tap away.

Importance is dynamic (CRITICAL / HIGH / MEDIUM / LOW / HIDDEN): a release two
days old climbs, the same release a month later sinks; a secondary indicator
is only brought forward when its move is abnormal.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from .decision_config import (
    CYCLE,
    DERIVATIVES,
    FAMILY_EMOJI,
    FAMILY_LABEL,
    FLOWS,
    LIQUIDITY,
    MACRO,
    ONCHAIN,
    TECHNICAL,
    THRESHOLDS,
)
from .decision_families import DataStatus, FamilyScore, FamilyState, MetricReading
from .factor_semantics import fr_number

GREEN, ORANGE, RED, YELLOW, WHITE = "GREEN", "ORANGE", "RED", "YELLOW", "WHITE"
_TONE_EMOJI = {GREEN: "🟢", ORANGE: "🟠", RED: "🔴", YELLOW: "🟡", WHITE: "⚪"}
CRITICAL, HIGH, MEDIUM, LOW, HIDDEN = "CRITICAL", "HIGH", "MEDIUM", "LOW", "HIDDEN"

#: Measures no connected source provides in full; stated once, never a warning.
STRUCTURAL_GAPS = frozenset({"liquidations"})

#: Shown only in advanced data unless something makes them explanatory.
HIDDEN_BY_DEFAULT = frozenset({
    "macro.real10y", "macro.us10y", "macro.us2y", "macro.yield_curve_10y2y",
    "macro.fed_funds_rate", "technical.atr_pct", "technical.bollinger_bandwidth",
    "technical.realized_vol", "derivatives.basis_pct", "oi.value_history",
    "oi.contracts_bybit", "macro.cpi", "macro.core_cpi", "technical.moving_averages",
})

#: Families on the home and the full page, in reading order.
DISPLAY_FAMILIES = (TECHNICAL, DERIVATIVES, FLOWS, MACRO, CYCLE, ONCHAIN)
DISPLAY_NAME = {
    TECHNICAL: "Technique",
    DERIVATIVES: "Dérivés",
    # Named after what it measures: US spot ETF flows and spot market buying.
    FLOWS: "ETF & flux au comptant",
    MACRO: "Macro & banques centrales",
    CYCLE: "Cycle Bitcoin",
    ONCHAIN: "Baleines & on-chain",
}


def _usd(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{fr_number(value, 0 if abs(value) >= 100 else 2)} $"


def _usd_compact(value: float) -> str:
    sign = "+" if value > 0 else "-" if value < 0 else ""
    value = abs(value)
    if value >= 1e9:
        return f"{sign}{fr_number(value / 1e9, 2)} Md$"
    if value >= 1e6:
        return f"{sign}{fr_number(value / 1e6, 0)} M$"
    return f"{sign}{fr_number(value / 1e3, 0)} k$"


def _unsigned(value: float) -> str:
    return _usd_compact(value).lstrip("+")


def _metric(family: FamilyScore | None, key: str) -> MetricReading | None:
    if family is None:
        return None
    return next((m for m in family.metrics if m.key == key), None)


def _component(family: FamilyScore | None, key: str):
    if family is None:
        return None
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
        text = "Périmée" if reading.status is DataStatus.STALE else "Indisponible"
        return _row(label or reading.label, f"⚪ {text}", WHITE, reading.key, reading.note)
    tone = {
        "FAVORABLE": GREEN, "UNFAVORABLE": RED, "CAUTION": ORANGE,
        "NEUTRAL": YELLOW, "CONTEXT": WHITE,
    }.get(reading.state, WHITE)
    return _row(label or reading.label, reading.display_value, tone, reading.key, reading.delta_label)


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


def _details(rows: list[dict[str, Any] | None]) -> dict[str, Any]:
    return _section("🗂️", "Données avancées", rows, secondary=True)


def _set_importance(family: FamilyScore) -> None:
    """Default importance from the priority; hidden series stay hidden unless
    something promoted them (priority 1)."""

    for reading in family.metrics:
        if reading.importance in {CRITICAL, HIGH} and reading.priority == 1:
            continue
        if reading.key in HIDDEN_BY_DEFAULT and reading.priority > 1:
            reading.importance = HIDDEN
        else:
            reading.importance = {1: HIGH, 2: MEDIUM}.get(reading.priority, LOW)


# ---------------------------------------------------------------------------
# 📊 Technique - trend, structure, support, next resistance, timing
# ---------------------------------------------------------------------------

STRUCTURE_PLAIN = {
    "TREND_UP": "Sommets et creux ascendants",
    "TREND_DOWN": "Sommets et creux descendants",
    "RANGE": "Range entre support et résistance",
    "BREAKOUT_PENDING": "Cassure haussière en approche",
    "BREAKOUT_CONFIRMED": "Cassure haussière confirmée",
    "BREAKDOWN_PENDING": "Cassure baissière en approche",
    "BREAKDOWN_CONFIRMED": "Cassure baissière confirmée",
    "UNCLEAR": "Structure indécise",
}


def _trend(family: FamilyScore) -> tuple[str, str, str]:
    signal = float(family.extra.get("trend_signal") or 0.0)
    structure = str(family.extra.get("structure") or "UNCLEAR")
    up = signal >= 0.25 or structure in {"TREND_UP", "BREAKOUT_CONFIRMED"}
    down = signal <= -0.25 or structure in {"TREND_DOWN", "BREAKDOWN_CONFIRMED"}
    if up and not down:
        return "📈", "Haussière", "UP"
    if down and not up:
        return "📉", "Baissière", "DOWN"
    return "➡️", "Neutre", "FLAT"


def _timing(rsi: float | None, trend_key: str, near_resistance: bool) -> tuple[str, str, str]:
    """(label, tone, metric state) - the quality of the entry, never the trend."""

    if rsi is not None and rsi >= THRESHOLDS.stretched_rsi:
        return "Marché étiré", ORANGE, "CAUTION"
    if near_resistance and trend_key != "DOWN":
        return "Sous résistance", ORANGE, "CAUTION"
    if rsi is not None and rsi <= 30:
        return "Survendu", ORANGE, "CAUTION"
    if trend_key == "DOWN":
        return "Défavorable", RED, "UNFAVORABLE"
    if rsi is None:
        return "Indéterminé", WHITE, "UNKNOWN"
    return "Correct", GREEN, "NEUTRAL"


def present_technical(family: FamilyScore, horizon: str = "7d") -> dict[str, Any]:
    extra = family.extra
    if not extra:
        return _unavailable_view(family)
    trend_emoji, trend_label, trend_key = _trend(family)
    rsi = extra.get("rsi")
    price = extra.get("price")
    support, resistance = extra.get("support"), extra.get("resistance")
    support_detail = extra.get("support_detail") or {}
    resistance_detail = extra.get("resistance_detail") or {}
    margin = THRESHOLDS.resistance_margin_pct.get(horizon, 1.5)
    distance = (resistance - price) / price * 100 if price and resistance else None
    near_resistance = distance is not None and 0 <= distance <= margin
    timing, timing_tone, _state = _timing(rsi, trend_key, near_resistance)
    stretched = rsi is not None and rsi >= THRESHOLDS.stretched_rsi

    rsi_metric = _metric(family, "technical.rsi")
    if rsi_metric is not None and rsi_metric.usable:
        # Never "RSI 77 -> favourable": a high RSI is a timing caution.
        rsi_metric.state = "CAUTION" if stretched or (rsi or 50) <= 30 else "CONTEXT"
        rsi_metric.priority = 1 if stretched else 2
    for key in ("technical.support", "technical.resistance"):
        reading = _metric(family, key)
        if reading is not None:
            reading.priority = 1
            reading.state = "CONTEXT"
    resistance_reading = _metric(family, "technical.resistance")
    if resistance_reading is not None and near_resistance:
        resistance_reading.state = "CAUTION"

    # Bollinger: the interpretation follows the measured state.
    bw_pct = extra.get("bollinger_percentile")
    bollinger = _metric(family, "technical.bollinger_bandwidth")
    if bw_pct is not None and bollinger is not None:
        if bw_pct >= 85:
            bollinger.why = (
                f"Bandes de Bollinger en expansion ({fr_number(bw_pct, 0)}e centile) : le "
                "marché est déjà en mouvement ample."
            )
            bollinger.state = "CAUTION"
        elif bw_pct <= 15:
            bollinger.why = (
                f"Bandes de Bollinger resserrées ({fr_number(bw_pct, 0)}e centile) : un "
                "mouvement ample peut se préparer, sans en dire le sens."
            )
            bollinger.state = "CONTEXT"
        else:
            bollinger.why = f"Bandes de Bollinger au {fr_number(bw_pct, 0)}e centile : amplitude normale."
            bollinger.state = "CONTEXT"

    structure = str(extra.get("structure") or "UNCLEAR")
    changes = extra.get("changes") or {}
    perf = " · ".join(
        f"{label} {fr_number(changes[d], 1, signed=True)} %"
        for d, label in ((1, "24 h"), (7, "7 j"), (30, "30 j"))
        if changes.get(d) is not None
    )
    kind, fast, slow = extra.get("ma_kind", "EMA"), extra.get("fast", 20), extra.get("slow", 50)
    trend_tone = GREEN if trend_key == "UP" else RED if trend_key == "DOWN" else YELLOW
    main = _section(
        "📊", "L'essentiel",
        [
            _row("📈 Tendance", trend_label, trend_tone),
            _row("🧱 Structure", STRUCTURE_PLAIN.get(structure, structure), trend_tone),
            _row("🟢 Support clé", _usd(support), GREEN, "technical.support",
                 support_detail.get("explanation", "")) if support else
            _row("🟢 Support clé", "Aucun support testé sous le prix"),
            _row("🔴 Prochaine résistance", _usd(resistance),
                 ORANGE if near_resistance else RED, "technical.resistance",
                 resistance_detail.get("explanation", "")) if resistance else
            _row("🔴 Prochaine résistance", "Aucune résistance testée au-dessus", GREEN),
            _row("🔥 Timing", timing, timing_tone, "technical.rsi" if rsi_metric else None,
                 f"RSI {fr_number(rsi, 0)}" if rsi is not None else ""),
        ],
        why="Niveaux calculés sur la paire en dollars (USDT), à partir des sommets et creux confirmés.",
    )
    details = _details([
        _row("Prix (paire USDT)", _usd(price)),
        _row(f"{kind}{fast}", _usd(extra.get("fast_ma"))),
        _row(f"{kind}{slow}", _usd(extra.get("slow_ma"))),
        _metric_row(rsi_metric, "RSI 14"),
        _metric_row(_metric(family, "technical.atr_pct"), "ATR"),
        _metric_row(_metric(family, "technical.realized_vol"), "Volatilité réalisée"),
        _metric_row(bollinger, "Largeur de Bollinger"),
        _row("Performance", perf) if perf else None,
        _metric_row(_metric(family, "market.dominance"), "Dominance BTC"),
    ])

    lecture = [f"{trend_emoji} Tendance {trend_label.lower()} : {STRUCTURE_PLAIN.get(structure, '').lower()}."]
    if stretched:
        lecture.append(f"🔥 Marché étiré (RSI {fr_number(rsi, 0)}) : la tendance tient, l'entrée est tardive.")
    if resistance:
        lecture.append(
            f"🧱 Prochaine résistance à {_usd(resistance)}"
            + (f", à {fr_number(distance, 1)} % du prix." if distance is not None else ".")
        )
    triggers = []
    if resistance and trend_key != "DOWN":
        triggers.append(f"📈 Une clôture au-dessus de {_usd(resistance)} ouvrirait la voie.")
    if support and trend_key != "DOWN":
        triggers.append(f"📉 Une clôture sous le support {_usd(support)} casserait la structure.")
    if resistance and trend_key == "DOWN":
        triggers.append(f"📈 La reprise de {_usd(resistance)} invaliderait la baisse.")
    if stretched:
        triggers.append("🔥 Un repli du RSI sous 70 sans casser le support assainirait l'entrée.")

    status = f"{trend_label}{' mais étirée' if stretched and trend_key == 'UP' else ''}"
    key_info = " · ".join(filter(None, [
        f"RSI {fr_number(rsi, 0)}" if rsi is not None else "",
        "résistance proche" if near_resistance else "",
    ]))
    return {
        "sections": [main, details],
        "lecture": lecture[:3],
        "changes": triggers[:4],
        "home": {
            "status": status,
            "tone": ORANGE if stretched or near_resistance else trend_tone,
            "key_info": key_info,
            "status_emoji": trend_emoji,
        },
        "trend": {"emoji": trend_emoji, "label": trend_label, "key": trend_key},
        "timing": {"label": timing, "tone": timing_tone, "stretched": stretched},
        "near_resistance": near_resistance,
        "resistance": resistance,
    }


# ---------------------------------------------------------------------------
# 📈 Dérivés - positioning & leverage first, then liquidations, then volatility
# ---------------------------------------------------------------------------

_CROWDING_TONE = {
    "CROWDED_LONGS": RED, "CROWDED_SHORTS": ORANGE, "NEW_SHORTS": RED,
    "NEW_LONGS": GREEN, "SHORT_COVERING": YELLOW, "DELEVERAGING": YELLOW,
    "QUIET": GREEN, "UNKNOWN": WHITE,
}
_CROWDING_VERDICT = {
    "CROWDED_LONGS": "Longs encombrés",
    "CROWDED_SHORTS": "Shorts encombrés",
    "NEW_SHORTS": "Nouveaux shorts",
    "NEW_LONGS": "Levier sain",
    "SHORT_COVERING": "Rachat de shorts",
    "DELEVERAGING": "Levier en purge",
    "QUIET": "Levier calme",
    "UNKNOWN": "Indéterminé",
}
_CROWDING_SHORT = {
    "CROWDED_LONGS": "De nouveaux longs utilisent beaucoup de levier, ce qui augmente le risque de purge.",
    "NEW_LONGS": "De nouvelles positions acheteuses accompagnent la hausse sans excès de coût.",
    "SHORT_COVERING": "Des vendeurs à découvert se couvrent : une hausse qui dure souvent moins.",
    "NEW_SHORTS": "De nouveaux shorts accompagnent la baisse.",
    "CROWDED_SHORTS": "Les shorts paient cher : un rachat forcé peut provoquer un rebond brutal.",
    "DELEVERAGING": "Le levier se purge : prix et positions reculent ensemble.",
    "QUIET": "Ni le prix ni le levier ne bougent nettement.",
    "UNKNOWN": "Données de levier insuffisantes pour conclure.",
}


def _dvol_level(pct: float | None) -> tuple[str, str]:
    if pct is None:
        return "Indisponible", WHITE
    if pct >= 80:
        return "Élevée", ORANGE
    if pct <= 20:
        return "Basse", GREEN
    return "Normale", YELLOW


def present_derivatives(family: FamilyScore) -> dict[str, Any]:
    extra = family.extra
    crowding = str(extra.get("crowding") or "UNKNOWN")
    funding_pct = extra.get("funding_percentile")
    oi_pct = extra.get("oi_percentile")
    dvol_pct = extra.get("dvol_percentile")
    oi = next((m for m in family.metrics if m.key.startswith("oi.")), None)
    funding = _metric(family, "funding.rate")
    basis = _metric(family, "derivatives.basis_pct")
    dvol = _metric(family, "dvol.index")
    liq_metric = _metric(family, "liquidations")
    liquidations = extra.get("liquidations") or {}
    crowded = crowding in {"CROWDED_LONGS", "CROWDED_SHORTS"}
    directional = crowded or crowding in {"NEW_SHORTS", "NEW_LONGS"}

    # Open interest alone is context: it only takes a colour from the
    # combination with price and funding.
    if oi is not None and oi.usable:
        oi.state = oi.state if directional else "CONTEXT"
        oi.priority = 1 if crowded else 2
    if funding is not None and funding.usable:
        funding.priority = 1 if funding_pct is not None and funding_pct >= 85 else 2
        if funding_pct is not None and 15 < funding_pct < 85:
            funding.state = "CONTEXT"
    for reading in (basis, dvol):
        if reading is not None and reading.usable:
            reading.state = "CONTEXT"
            reading.priority = 3

    verdict = _CROWDING_VERDICT.get(crowding, "Indéterminé")
    tone = _CROWDING_TONE.get(crowding, WHITE)
    price_change = extra.get("price_change_pct")
    oi_move = oi.delta_pct if oi is not None and oi.usable else None
    positioning = _section(
        "📈", "Positionnement & levier",
        [
            _row("Prix / open interest",
                 " · ".join(filter(None, [
                     f"prix {fr_number(price_change, 1, signed=True)} %" if price_change is not None else "",
                     f"OI {fr_number(oi_move, 1, signed=True)} %" if oi_move is not None else "",
                 ])) or "—", tone),
            _row("Funding", (
                "extrême" if funding_pct is not None and funding_pct >= 95
                else "élevé" if funding_pct is not None and funding_pct >= 85
                else "bas" if funding_pct is not None and funding_pct <= 15
                else "normal" if funding_pct is not None else "—"
            ), RED if funding_pct is not None and funding_pct >= 85 else WHITE, "funding.rate",
                 f"{fr_number(funding_pct, 0)}e centile sur un an" if funding_pct is not None else ""),
        ],
        verdict=f"{_TONE_EMOJI.get(tone, '')} {verdict}".strip(), tone=tone,
        sentence=_CROWDING_SHORT.get(crowding, ""),
        why="Le signal vient de la combinaison prix + open interest + funding, jamais d'une seule mesure.",
    )

    day = liquidations.get("24h") or {}
    dominance = liquidations.get("dominance", "UNKNOWN")
    if liq_metric is not None and liq_metric.usable:
        dom_text, dom_tone = {
            "LONGS": ("🔴 Longs liquidés", RED),
            "SHORTS": ("🟢 Shorts liquidés", GREEN),
            "BALANCED": ("🟡 Équilibre", YELLOW),
        }.get(dominance, ("—", WHITE))
        liq_section = _section(
            "💥", "Liquidations 24 h",
            [
                _row("Longs", _unsigned(day.get("long_usd", 0.0)), RED, "liquidations"),
                _row("Shorts", _unsigned(day.get("short_usd", 0.0)), GREEN, "liquidations"),
                _row("Dominance", dom_text, dom_tone),
            ],
            why="Des positions à levier fermées de force : elles disent la violence du mouvement, pas sa suite.",
        )
    else:
        covered = day.get("covered_hours", 0)
        started = liquidations.get("stream_started")
        liq_section = _section(
            "💥", "Liquidations 24 h",
            [_row("Liquidations",
                  "⚪ Collecte en cours" if started else "⚪ Source indisponible",
                  WHITE, "liquidations",
                  f"Flux en direct couvert {covered} h sur 24 : total publié à partir de 20 h"
                  if started else "")],
        )

    dvol_level, dvol_tone = _dvol_level(dvol_pct)
    if dvol is not None and dvol.status is DataStatus.NOT_APPLICABLE:
        vol_rows = [_row("Volatilité anticipée", "Non publiée pour cet actif")]
    else:
        vol_rows = [_row("Volatilité anticipée", dvol_level, dvol_tone, "dvol.index",
                         f"{fr_number(dvol_pct, 0)}e centile sur deux ans" if dvol_pct is not None else "")]
    vol_section = _section(
        "🌪️", "Volatilité anticipée", vol_rows,
        why="Elle indique l'ampleur du mouvement attendu par le marché des options, jamais sa direction.",
    )
    for_liq = [
        _row(f"Liquidations {label}",
             f"longs {_unsigned(liquidations[label]['long_usd'])} · shorts {_unsigned(liquidations[label]['short_usd'])}",
             detail=f"couverture {liquidations[label]['covered_hours']} h / {liquidations[label]['hours']} h")
        for label in ("1h", "4h") if liquidations.get(label)
    ]
    details = _details([
        _metric_row(oi, "Open interest"),
        _row("Rang historique de l'OI", f"{fr_number(oi_pct, 0)}e centile") if oi_pct is not None else None,
        _metric_row(funding, "Funding (8 h)"),
        _metric_row(basis, "Prime des futures"),
        _metric_row(dvol, "DVOL"),
        *for_liq,
    ])

    # A synthesis, not the card's own sentence again.
    lecture = [
        f"📈 Levier : {verdict.lower()}"
        + (f", funding au {fr_number(funding_pct, 0)}e centile de l'année" if funding_pct is not None else "")
        + "."
    ]
    if dvol_pct is not None and dvol_pct >= 80:
        lecture.append("🌪️ Volatilité anticipée élevée : un mouvement ample est attendu, dans un sens ou dans l'autre.")
    if liq_metric is not None and liq_metric.usable and dominance in {"LONGS", "SHORTS"}:
        lecture.append(
            f"💥 {'Longs' if dominance == 'LONGS' else 'Shorts'} majoritairement liquidés sur 24 h "
            f"({liq_metric.display_value})."
        )
    triggers = []
    if crowding == "CROWDED_LONGS":
        triggers.append("📈 Un funding et un OI qui se normalisent sans baisse du prix.")
        triggers.append("💥 Une baisse rapide pourrait forcer la liquidation des longs encombrés.")
    elif crowding == "NEW_SHORTS":
        triggers.append("📉 Un OI qui monte encore pendant la baisse confirmerait la pression vendeuse.")
    elif funding_pct is not None:
        triggers.append(
            f"💰 Un funding au-delà du 85e centile (aujourd'hui {fr_number(funding_pct, 0)}e) "
            "signalerait un levier excessif."
        )
        triggers.append("📉 Un OI en hausse pendant une baisse du prix : nouveaux shorts.")

    if crowded:
        status, home_tone = verdict, RED
    elif not family.usable:
        status, home_tone = "Données insuffisantes", WHITE
    else:
        status, home_tone = verdict, tone
    key_info = " · ".join(filter(None, [
        f"Funding {('élevé' if funding_pct >= 85 else 'normal')}" if funding_pct is not None else "",
        f"OI {fr_number(oi_move, 1, signed=True)} %" if oi_move is not None else "",
    ]))
    return {
        "sections": [positioning, liq_section, vol_section, details],
        "lecture": [line for line in lecture if line.strip("📈 ")][:3],
        "changes": triggers[:4],
        "home": {"status": status, "tone": home_tone, "key_info": key_info,
                 "status_emoji": _TONE_EMOJI.get(home_tone, "")},
        "crowded": crowded,
        "dvol_level": dvol_level,
        "liquidations_dominance": dominance,
    }


# ---------------------------------------------------------------------------
# 🪙 Flux spot - who takes the initiative
# ---------------------------------------------------------------------------


def _pressure_words(share: float) -> tuple[str, str, str]:
    """(verdict, tone, home status) from the aggressive-buy share."""

    lean = (share - 0.5) * 100
    if abs(lean) < 1:
        return "Pression équilibrée", YELLOW, "Équilibre acheteurs / vendeurs"
    side = "acheteuse" if lean > 0 else "vendeuse"
    actors = "Acheteurs" if lean > 0 else "Vendeurs"
    tone = GREEN if lean > 0 else RED
    if abs(lean) < 3:
        return f"Pression {side} légère", tone, f"{actors} légèrement dominants"
    if abs(lean) < 6:
        return f"Pression {side} modérée", tone, f"{actors} dominants"
    return f"Pression {side} forte", tone, f"{actors} nettement dominants"


def present_flows(family: FamilyScore) -> dict[str, Any]:
    spot = family.extra.get("spot") or {}
    share = spot.get("share")
    pressure = _metric(family, "spot.pressure")
    etf_metric = _metric(family, "etf.net_flow")
    etf_c = _component(family, "etf")
    if share is None or pressure is None or not pressure.usable:
        view = _unavailable_view(family)
        view["sections"][0]["title"] = "Pression acheteurs / vendeurs"
        return view
    window = spot.get("window", "")
    verdict, tone, status = _pressure_words(share)
    trend = spot.get("trend")
    trend_line = {
        "UP": "📈 Pression acheteuse en progression",
        "DOWN": "📉 Pression vendeuse en progression",
        "FLAT": "➡️ Pression stable",
    }.get(trend or "", "")
    count = len(spot.get("exchanges", []))
    exchanges = f"{count} plateforme{'s' if count > 1 else ''} majeure{'s' if count > 1 else ''}"
    if spot.get("source") == "hourly":
        rows = [
            _row("Achats agressifs", f"{fr_number(share * 100, 0)} %", GREEN if share >= 0.5 else WHITE,
                 "spot.pressure", _unsigned(spot["buy_usd"])),
            _row("Ventes agressives", f"{fr_number((1 - share) * 100, 0)} %", RED if share < 0.5 else WHITE,
                 "spot.pressure", _unsigned(spot["sell_usd"])),
            _row("Delta", _usd_compact(spot["delta_usd"]), GREEN if spot["delta_usd"] > 0 else RED),
        ]
    else:
        rows = [_row("Achats agressifs", f"{fr_number(share * 100, 0)} %", tone, "spot.pressure",
                     "historique quotidien")]
    main = _section(
        "🪙", f"Flux spot — {window}", rows,
        verdict=f"{_TONE_EMOJI[tone]} {verdict}", tone=tone,
        sentence=(
            "Les acheteurs prennent plus souvent l'initiative." if share >= 0.51
            else "Les vendeurs prennent plus souvent l'initiative." if share <= 0.49
            else "Acheteurs et vendeurs prennent l'initiative à parts égales."
        ),
        why="Chaque transaction a un acheteur et un vendeur : on mesure qui accepte de payer l'écart pour agir tout de suite.",
    )
    coverage = spot.get("coverage") or {}
    missing = [e for e, c in coverage.items() if c < 0.9]
    details = _details([
        _row("Plateformes agrégées", exchanges if count else "—",
             detail=(f"{len(missing)} plateforme{'s' if len(missing) > 1 else ''} écartée"
                     f"{'s' if len(missing) > 1 else ''} (couverture insuffisante)") if missing else ""),
        _row("Tendance de la pression", trend_line.split(" ", 1)[1] if trend_line else "—"),
        _metric_row(etf_metric, "Flux ETF (contexte)") if etf_metric is not None else None,
    ])
    # The family headline says what is measured - never "capital is flowing in".
    family.headline = main["sentence"]
    triggers = [c.turn_condition for c in family.components if c.active and c.turn_condition][:2]
    lecture = [f"{_TONE_EMOJI[tone]} {verdict} sur {window}."]
    if trend_line:
        lecture.append(f"{trend_line} par rapport à la période précédente.")
    if etf_c is not None and etf_metric is not None and etf_metric.usable:
        lecture.append(f"💸 ETF (contexte) : {etf_metric.display_value}.")
    return {
        "sections": [main, details],
        "lecture": lecture[:3],
        "changes": triggers,
        "home": {
            "status": status,
            "tone": tone,
            "key_info": f"Achats agressifs {fr_number(share * 100, 0)} %"
            + (f" · delta {_usd_compact(spot['delta_usd'])}" if spot.get("delta_usd") is not None else ""),
            "status_emoji": _TONE_EMOJI[tone],
        },
        "pressure": {"share": share, "tone": tone, "verdict": verdict, "trend": trend},
    }


# ---------------------------------------------------------------------------
# 🏛️ Macro & banques centrales
# ---------------------------------------------------------------------------

#: Engine inputs shown only when their move is abnormal, with the sentence.
_NOTABLE = {
    "dollar": ("macro.dxy", "💵 Dollar fortement en hausse → pression possible sur les actifs risqués.",
               "💵 Dollar en net repli → soutien possible pour les actifs risqués."),
    "real_yield": ("macro.real10y", "🏛️ Taux réels en forte hausse → détenir des cryptos coûte plus cher.",
                   "🏛️ Taux réels en net repli → le coût d'opportunité baisse."),
    "policy_expectations": ("macro.us2y", "🇺🇸 Taux 2 ans en forte hausse → le marché anticipe une Fed plus restrictive.",
                            "🇺🇸 Taux 2 ans en net repli → le marché anticipe une Fed plus souple."),
    "oil_shock": ("macro.oil_wti", "🛢️ Choc pétrolier → risque inflationniste.",
                  "🛢️ Pétrole en forte baisse → pression inflationniste en recul."),
    "equity_fear": ("macro.vix", "😨 Volatilité actions en forte hausse → aversion au risque.",
                    "😌 Volatilité actions en net repli → appétit pour le risque."),
    "risk_appetite": ("macro.nasdaq", "📈 Nasdaq en forte hausse → appétit pour le risque.",
                      "📉 Nasdaq en forte baisse → aversion au risque."),
    "nominal_yield": ("macro.us10y", "🏛️ Taux 10 ans en forte hausse.", "🏛️ Taux 10 ans en net repli."),
}
#: A component signal (tanh of the move over one normal move) at or beyond
#: this is an abnormal move worth bringing forward.
ABNORMAL_SIGNAL = 0.6


def _days_label(days: float) -> str:
    if days < 1:
        hours = max(1, round(days * 24))
        return f"dans {hours} h"
    return f"dans {round(days)} j"


def present_macro(family: FamilyScore, as_of: datetime | None,
                  liquidity: FamilyScore | None = None) -> dict[str, Any]:
    banks = family.extra.get("central_banks") or []
    for reading in family.metrics:
        reading.priority = 3
    # Central banks first.
    bank_rows = []
    bank_importance = []
    for bank in banks:
        if not bank.get("available"):
            bank_rows.append(_row(f"{bank['flag']} {bank['name']}", "⚪ Taux indisponible"))
            continue
        parts = []
        last = bank.get("last_decision")
        if last:
            parts.append(f"Dernière : {last['label'].lower()} ({datetime.fromisoformat(last['date']):%d/%m})")
        if bank.get("next_meeting"):
            parts.append(f"Prochaine : {datetime.fromisoformat(bank['next_meeting']):%d/%m}"
                         + (f" ({_days_label(bank['days_to_next'])})" if bank.get("days_to_next") is not None else ""))
        parts.append(bank.get("expectation_label") or "Anticipation de marché indisponible")
        importance = bank.get("importance", LOW)
        bank_importance.append((importance, bank))
        reading = _metric(family, f"cb.{bank['key']}.rate")
        if reading is not None:
            reading.importance = importance
            reading.priority = 1 if importance in {CRITICAL, HIGH} else 2
        bank_rows.append(_row(
            f"{bank['flag']} {bank['name']}", bank["rate_label"],
            ORANGE if importance == CRITICAL else WHITE, f"cb.{bank['key']}.rate", " · ".join(parts),
        ))
    critical = [b for i, b in bank_importance if i == CRITICAL]
    upcoming = sorted(
        (b for _, b in bank_importance if b.get("days_to_next") is not None),
        key=lambda b: b["days_to_next"],
    )
    banks_section = _section(
        "🏛️", "Banques centrales", bank_rows,
        verdict=(f"⚠️ {critical[0]['name']} : décision imminente ou toute récente" if critical else ""),
        tone=ORANGE if critical else WHITE,
        why="La Fed pèse le plus ; la BCE et la BoJ deviennent critiques à l'approche d'une décision.",
    )

    sections = [banks_section]
    # Inflation / employment: only when a release is recent.
    recent = []
    for key in ("macro.core_cpi", "macro.cpi", "macro.unemployment", "macro.nonfarm_payrolls"):
        reading = _metric(family, key)
        if reading is None or not reading.usable or reading.available_at is None or as_of is None:
            continue
        age = as_of - reading.available_at
        if age <= timedelta(days=2):
            reading.importance, reading.priority = CRITICAL, 1
        elif age <= timedelta(days=7):
            reading.importance, reading.priority = HIGH, 1
        elif age <= timedelta(days=21):
            reading.importance, reading.priority = MEDIUM, 2
        else:
            reading.importance, reading.priority = LOW, 3
            continue
        recent.append(reading)
    if recent:
        rows = []
        for reading in recent:
            detail = " · ".join(filter(None, [
                reading.delta_label if "sur 7 j" not in reading.delta_label else "",
                "Consensus indisponible",
                f"Données : {reading.period_label}" if reading.period_label else "",
            ]))
            rows.append(_row(f"🇺🇸 {reading.label}", reading.display_value, WHITE, reading.key, detail))
        sections.append(_section(
            "🧾", "Publication récente", rows,
            why="Ces chiffres comptent surtout autour de leur publication et quand ils surprennent.",
        ))

    # Secondary engine inputs: only abnormal moves are brought forward.
    notable = []
    for component in family.components:
        if not component.active or component.key not in _NOTABLE:
            continue
        metric_key, up_text, down_text = _NOTABLE[component.key]
        reading = _metric(family, metric_key)
        if reading is None or reading.delta is None or abs(component.signal or 0) < ABNORMAL_SIGNAL:
            continue
        reading.importance, reading.priority = HIGH, 1
        notable.append((abs(component.signal or 0) * component.weight,
                        up_text if reading.delta > 0 else down_text, reading))
    notable.sort(key=lambda item: item[0], reverse=True)
    if notable:
        sections.append(_section(
            "⚡", "Mouvements notables",
            [_row(text.split(" → ")[0], _signed_move(reading), WHITE, reading.key,
                  text.split(" → ")[1] if " → " in text else "")
             for _, text, reading in notable[:3]],
        ))

    detail_rows: list[dict[str, Any] | None] = [
        _metric_row(m) for m in family.metrics
        if not m.key.startswith("cb.") and m not in [r for _, _, r in notable] and m not in recent
    ]
    if liquidity is not None:
        regime = liquidity.extra.get("regime_label")
        if regime:
            detail_rows.append(_row("💵 Liquidité", regime))
        detail_rows.extend(_metric_row(m) for m in liquidity.metrics)
    sections.append(_details(detail_rows))

    active = sorted((c for c in family.components if c.active),
                    key=lambda c: abs((c.signal or 0) * c.weight), reverse=True)
    negative = family.state in {FamilyState.NEGATIVE, FamilyState.VERY_NEGATIVE, FamilyState.SLIGHTLY_NEGATIVE}
    positive = family.state in {FamilyState.POSITIVE, FamilyState.VERY_POSITIVE, FamilyState.SLIGHTLY_POSITIVE}
    tone = (RED if family.state in {FamilyState.NEGATIVE, FamilyState.VERY_NEGATIVE}
            else ORANGE if negative else GREEN if positive else YELLOW)
    next_bank = upcoming[0] if upcoming else None
    key_info = (
        f"{next_bank['name']} {_days_label(next_bank['days_to_next'])}" if next_bank else ""
    )
    if notable:
        key_info = notable[0][1].split(" → ")[0].split(" ", 1)[1] + (f" · {key_info}" if key_info else "")
    lecture = [text for _, text, _ in notable[:2]] or [c.sentence for c in active[:2]]
    if next_bank:
        lecture.append(
            f"{next_bank['flag']} Prochaine décision {next_bank['name']} "
            f"{_days_label(next_bank['days_to_next'])} ({next_bank.get('expectation_label', '').lower()})."
        )
    return {
        "sections": [s for s in sections if s["rows"]],
        "lecture": lecture[:3],
        "changes": [c.turn_condition for c in active if c.turn_condition][:3],
        "home": {
            "status": "Défavorable" if negative else "Favorable" if positive else "Neutre",
            "tone": tone,
            "key_info": key_info,
            "status_emoji": "",
        },
        "notable": [text for _, text, _ in notable],
        "next_bank": next_bank,
        "critical_bank": critical[0] if critical else None,
    }


def _signed_move(reading: MetricReading) -> str:
    return reading.delta_label or reading.display_value


# ---------------------------------------------------------------------------
# 🔄 Cycle Bitcoin / régime crypto
# ---------------------------------------------------------------------------


def present_cycle(family: FamilyScore, asset: str) -> dict[str, Any]:
    cycle = family.extra.get("cycle") or {}
    if not cycle:
        return _unavailable_view(family)
    dims = cycle.get("dimensions") or {}
    relative = family.extra.get("relative") or {}
    phase = cycle.get("phase_label", "Indéterminé")
    phase_emoji = cycle.get("phase_emoji", "🔄")
    direction = cycle.get("direction_label", "Stable")
    direction_emoji = cycle.get("direction_emoji", "➡️")
    drawdown = dims.get("drawdown_pct")
    days_halving = dims.get("days_since_halving")
    days_in_phase = cycle.get("days_in_phase")
    elevated = bool(cycle.get("elevated_structural_risk"))
    tone = {
        "GREEN": GREEN, "BLUE": "BLUE", "FIRE": "FIRE", "ORANGE": ORANGE,
        "RED": RED, "WHITE": WHITE,
    }.get(cycle.get("tone", "WHITE"), WHITE)

    # Three figures on the main card, never more.
    rows = []
    if asset == "BTC" and days_halving is not None:
        rows.append(_row("⚡ Depuis le halving", f"{days_halving} jours", WHITE,
                         "cycle.days_since_halving"))
    if drawdown is not None:
        label = "🏆 Distance de l'ATH" if asset == "BTC" else "🏆 BTC sous son record"
        rows.append(_row(label, f"{fr_number(drawdown, 0, signed=True)} %", WHITE, "cycle.drawdown"))
    if days_in_phase is not None:
        rows.append(_row("📅 Phase actuelle depuis", f"{days_in_phase} jours", WHITE,
                         "cycle.days_in_phase"))
    change = relative.get("change_pct")
    notable_relative = change is not None and abs(change) >= 2.0
    if notable_relative:
        rows.append(_row(
            f"📊 {asset} face à BTC", relative.get("label", ""),
            GREEN if change > 0 else RED, f"cycle.relative_{asset.lower()}_btc",
            f"{fr_number(change, 1, signed=True)} % sur {relative.get('window', '')}",
        ))
    main = _section(
        "🔄", "Cycle Bitcoin" if asset == "BTC" else "Régime crypto", rows,
        verdict=f"{phase_emoji} {phase} {direction_emoji} {direction}", tone=tone,
        sentence=(family.headline or ""),
        why="Le cycle est du contexte : il ne déclenche jamais seul un achat ou une vente.",
    )
    candidate = cycle.get("candidate_label")
    details_rows = [
        _row("Record (ATH)", _usd(dims.get("ath")),
             detail=(f"le {datetime.fromisoformat(dims['ath_date']):%d/%m/%Y}"
                     if dims.get("ath_date") else "")),
        _row("Moyenne 200 jours", _usd(dims.get("sma200")),
             detail=(f"pente 30 j {fr_number(dims['sma200_slope_pct'], 1, signed=True)} %"
                     if dims.get("sma200_slope_pct") is not None else "")),
        _row("Structure long terme", {
            "HIGHER": "Sommets et creux ascendants", "LOWER": "Sommets et creux descendants",
            "MIXED": "Mixte", "UNCLEAR": "Indéterminée",
        }.get(dims.get("structure", ""), "—")),
        _row("Momentum long terme", {
            "ACCELERATING": "Accélère", "SLOWING": "Ralentit",
            "REVERSING": "Se retourne", "STEADY": "Stable",
        }.get(dims.get("momentum", ""), "—")),
        _row("Rebond depuis le plus bas",
             f"{fr_number(dims['rebound_from_low_pct'], 0, signed=True)} %")
        if dims.get("rebound_from_low_pct") is not None else None,
    ]
    if candidate:
        details_rows.append(_row(
            "Phase candidate", candidate,
            detail=f"confirmée à {cycle.get('candidate_days', 0)}/{cycle.get('confirmation_days', 15)}",
        ))
    lecture = list(cycle.get("evidence") or [])[:3]
    if elevated:
        lecture.append("⚠️ Risque structurel supérieur, sans signal de calendrier.")
    key_parts = []
    if asset == "BTC" and days_halving is not None:
        key_parts.append(f"{days_halving} j depuis le halving")
    if drawdown is not None:
        key_parts.append(f"{fr_number(drawdown, 0, signed=True)} % sous l'ATH")
    if asset != "BTC" and notable_relative:
        key_parts.append(relative.get("label", ""))
    return {
        "sections": [main, _details(details_rows)],
        "lecture": lecture[:3],
        "changes": [],
        "home": {
            "status": f"{phase} {direction_emoji}",
            "tone": tone if tone in {GREEN, ORANGE, RED, YELLOW, WHITE} else WHITE,
            "key_info": " · ".join(key_parts),
            "status_emoji": phase_emoji,
        },
        "elevated": elevated,
        "phase_label": phase,
        "direction": cycle.get("direction", "STABLE"),
    }


# ---------------------------------------------------------------------------
# 🐋 Baleines & on-chain - small, and silent without direction
# ---------------------------------------------------------------------------


def present_onchain(family: FamilyScore) -> dict[str, Any]:
    whales = family.extra.get("whales") or {}
    deposits = whales.get("exchange_deposits_usd")
    withdrawals = whales.get("exchange_withdrawals_usd")
    directional = family.usable and (deposits or withdrawals)
    if not directional:
        return {
            "sections": [_section(
                "🐋", "Flux baleines",
                [_row("Direction", "⚪ Données directionnelles insuffisantes")],
                sentence=(
                    "Un gros transfert n'est pas une vente : sans étiquettes fiables des "
                    "adresses d'exchanges, aucune direction n'est déduite."
                ),
            )],
            "lecture": [],
            "changes": [],
            "home": {"status": "Données directionnelles insuffisantes", "tone": WHITE,
                     "key_info": "", "status_emoji": "⚪"},
            "hide_on_home": True,
        }
    tone = RED if (deposits or 0) > (withdrawals or 0) else GREEN
    return {
        "sections": [_section(
            "🐋", "Flux baleines",
            [_row("Entrées sur les exchanges", _unsigned(deposits or 0.0), RED),
             _row("Sorties des exchanges", _unsigned(withdrawals or 0.0), GREEN)],
            verdict=f"{_TONE_EMOJI[tone]} "
            + ("Gros transferts vers les exchanges" if tone == RED else "Sorties d'exchanges importantes"),
            tone=tone,
            sentence="Une pression potentielle, jamais la preuve d'une vente ou d'un achat.",
        )],
        "lecture": [],
        "changes": [],
        "home": {"status": "Entrées sur exchanges" if tone == RED else "Sorties d'exchanges",
                 "tone": tone, "key_info": "", "status_emoji": _TONE_EMOJI[tone]},
        "hide_on_home": False,
    }


def present_liquidity(family: FamilyScore) -> dict[str, Any]:
    regime = family.extra.get("regime_label", "Incertaine")
    return {
        "sections": [_details([_metric_row(m) for m in family.metrics])],
        "lecture": [],
        "changes": [],
        "home": {"status": regime, "tone": WHITE, "key_info": "", "status_emoji": "💵"},
    }


def _unavailable_view(family: FamilyScore) -> dict[str, Any]:
    return {
        "sections": [_section(
            FAMILY_EMOJI.get(family.family, "⚪"), FAMILY_LABEL.get(family.family, family.family),
            [_row("Données", "⚪ Source indisponible")],
            verdict="⚪ Données insuffisantes", sentence=family.unavailable_reason,
        )],
        "lecture": [],
        "changes": [],
        "home": {"status": "Données insuffisantes", "tone": WHITE, "key_info": "", "status_emoji": "⚪"},
    }


def present_family(family: FamilyScore, as_of: datetime | None,
                   families: dict[str, FamilyScore] | None = None,
                   asset: str = "BTC") -> dict[str, Any]:
    families = families or {}
    horizon = family.horizon
    if family.family == ONCHAIN:
        view = present_onchain(family)
    elif family.family == TECHNICAL:
        view = present_technical(family, horizon)
    elif not family.usable and family.family not in {MACRO, CYCLE}:
        view = _unavailable_view(family)
    elif family.family == DERIVATIVES:
        view = present_derivatives(family)
    elif family.family == FLOWS:
        view = present_flows(family)
    elif family.family == MACRO:
        view = present_macro(family, as_of, families.get(LIQUIDITY))
    elif family.family == CYCLE:
        view = present_cycle(family, asset)
    else:
        view = present_liquidity(family)
    _set_importance(family)
    confidence_label = (
        "Confiance élevée" if family.confidence >= 75
        else "Confiance moyenne" if family.confidence >= 55
        else "Confiance faible"
    )
    issues = []
    expected = [
        m for m in family.metrics
        if m.status is not DataStatus.NOT_APPLICABLE and m.key not in STRUCTURAL_GAPS
    ]
    if family.family != ONCHAIN:
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
    view["display_name"] = DISPLAY_NAME.get(family.family, FAMILY_LABEL.get(family.family, ""))
    family.extra["view"] = view
    return view


# ---------------------------------------------------------------------------
# The decision summary
# ---------------------------------------------------------------------------

HOME_FAMILIES = DISPLAY_FAMILIES


def _reasons(decision: Any, views: dict[str, dict[str, Any]], top_event: Any) -> list[dict[str, Any]]:
    """At most three, chosen by what actually weighs on the decision now.

    What holds the entry comes first (leverage, a close resistance, a
    stretched market, a close event, sellers on spot); then the families that
    weigh most. The statistical validation is never one of them.
    """

    families: dict[str, FamilyScore] = decision.families
    candidates: list[tuple[float, dict[str, Any]]] = []
    technical = views.get(TECHNICAL, {})
    derivatives = views.get(DERIVATIVES, {})
    flows = views.get(FLOWS, {})
    macro = views.get(MACRO, {})
    cycle = views.get(CYCLE, {})

    if top_event is not None and getattr(top_event, "score", 0) >= 0.3:
        candidates.append((6 + top_event.score, {
            "emoji": "⚠️", "title": "Événement majeur proche",
            "detail": f"{top_event.title} {top_event.delay}.", "tone": ORANGE,
        }))
    if derivatives.get("crowded"):
        candidates.append((5, {
            "emoji": "📈", "title": "Levier élevé",
            "detail": "Funding + open interest montrent un marché chargé.", "tone": RED,
        }))
    if technical.get("near_resistance") and technical.get("resistance"):
        candidates.append((4.5, {
            "emoji": "🧱", "title": "Résistance proche",
            "detail": f"Le prochain seuil important se situe à {_usd(technical['resistance'])}.",
            "tone": ORANGE,
        }))
    if (technical.get("timing") or {}).get("stretched"):
        rsi = families[TECHNICAL].extra.get("rsi") if TECHNICAL in families else None
        candidates.append((4, {
            "emoji": "🔥", "title": "Marché étiré",
            "detail": f"RSI {fr_number(rsi, 0)} : la tendance tient, l'entrée est tardive." if rsi else
            "La tendance tient, l'entrée est tardive.", "tone": ORANGE,
        }))
    pressure = flows.get("pressure") or {}
    if pressure:
        share = pressure["share"]
        weight = decision.weights.get(FLOWS, 0)
        if share <= 0.49:
            candidates.append((3.5, {
                "emoji": "🪙", "title": "Vendeurs à l'initiative",
                "detail": f"{fr_number((1 - share) * 100, 0)} % des volumes au comptant sont des ventes agressives.",
                "tone": RED,
            }))
        elif share >= 0.51:
            candidates.append((1 + weight * 5, {
                "emoji": "🪙", "title": "Acheteurs à l'initiative",
                "detail": f"{fr_number(share * 100, 0)} % des volumes au comptant sont des achats agressifs.",
                "tone": GREEN,
            }))
    critical_bank = macro.get("critical_bank")
    notable = macro.get("notable") or []
    next_bank = macro.get("next_bank")
    macro_family = families.get(MACRO)
    macro_weight = decision.weights.get(MACRO, 0) * abs((macro_family.score or 0) if macro_family else 0) / 100
    if critical_bank:
        candidates.append((5.5, {
            "emoji": "🏛️", "title": f"{critical_bank['name']} : décision imminente ou récente",
            "detail": critical_bank.get("expectation_label", ""), "tone": ORANGE,
        }))
    elif notable:
        emoji, rest = notable[0].split(" ", 1)
        title, _, detail = rest.partition(" → ")
        candidates.append((2 + macro_weight * 10, {
            "emoji": emoji, "title": title,
            "detail": (detail[:1].upper() + detail[1:]) if detail else "",
            "tone": views.get(MACRO, {}).get("home", {}).get("tone", WHITE),
        }))
    elif next_bank and macro_family is not None and macro_family.usable:
        candidates.append((1 + macro_weight * 10, {
            "emoji": "🏛️", "title": "Macro",
            "detail": f"Prochaine décision {next_bank['name']} {_days_label(next_bank['days_to_next'])}.",
            "tone": views.get(MACRO, {}).get("home", {}).get("tone", WHITE),
        }))
    if cycle.get("elevated"):
        candidates.append((1.5, {
            "emoji": "🔄", "title": f"Cycle : {cycle.get('phase_label', '').lower()}",
            "detail": "Risque structurel supérieur, sans signal de timing.", "tone": ORANGE,
        }))
    if not derivatives.get("crowded") and DERIVATIVES in families and families[DERIVATIVES].usable:
        verdict = (derivatives.get("home") or {}).get("status", "")
        candidates.append((0.5 + decision.weights.get(DERIVATIVES, 0) * 3, {
            "emoji": "📈", "title": verdict or "Levier",
            "detail": (derivatives.get("sections") or [{}])[0].get("sentence", ""),
            "tone": (derivatives.get("home") or {}).get("tone", WHITE),
        }))
    trend = technical.get("trend") or {}
    if trend and not technical.get("near_resistance") and not (technical.get("timing") or {}).get("stretched"):
        structure = families[TECHNICAL].extra.get("structure") if TECHNICAL in families else None
        candidates.append((0.8 + decision.weights.get(TECHNICAL, 0) * 3, {
            "emoji": trend.get("emoji", "📊"), "title": f"Tendance {trend.get('label', '').lower()}",
            "detail": STRUCTURE_PLAIN.get(str(structure), "") + ".",
            "tone": (technical.get("home") or {}).get("tone", WHITE),
        }))
    candidates.sort(key=lambda item: item[0], reverse=True)
    out: list[dict[str, Any]] = []
    for _, reason in candidates:
        if reason["title"] and all(r["title"] != reason["title"] for r in out):
            out.append(reason)
        if len(out) == 3:
            break
    return out


def summarize(decision: Any, *, as_of: Any = None, top_event: Any = None,
              asset: str = "") -> dict[str, Any]:
    """Trend, entry quality, risk, three reasons, validation, data issues."""

    families: dict[str, FamilyScore] = decision.families
    cycle_family = families.get(CYCLE)
    asset = asset or (cycle_family.extra.get("asset", "BTC") if cycle_family is not None else "BTC")
    views = {k: present_family(f, as_of, families, asset) for k, f in families.items()}
    technical = views.get(TECHNICAL, {})
    trend = technical.get("trend") or {"emoji": "➡️", "label": "Neutre", "key": "FLAT"}
    stretched = bool((technical.get("timing") or {}).get("stretched"))
    near_resistance = bool(technical.get("near_resistance"))
    crowded = bool(views.get(DERIVATIVES, {}).get("crowded"))
    dvol_pct = families[DERIVATIVES].extra.get("dvol_percentile") if DERIVATIVES in families else None
    liq_dominance = views.get(DERIVATIVES, {}).get("liquidations_dominance")
    cycle_elevated = bool(views.get(CYCLE, {}).get("elevated"))
    event_score = getattr(top_event, "score", 0.0) if top_event is not None else 0.0
    gate = decision.blocking_gate
    action = decision.action.value
    pressure = (views.get(FLOWS, {}).get("pressure") or {})
    spot_sellers = pressure.get("share") is not None and pressure["share"] <= 0.49

    # Risk: how badly it could go wrong, whatever the direction.
    if crowded or (dvol_pct or 0) >= 85 or event_score >= 0.6 or (
        families.get(MACRO) and families[MACRO].state is FamilyState.VERY_NEGATIVE
    ):
        risk = ("🔴", "Élevé", RED)
    elif (event_score >= 0.3 or gate == "CONTRADICTION" or stretched or cycle_elevated
          or liq_dominance == "LONGS" or (dvol_pct or 0) >= 70):
        risk = ("🟠", "Modéré", ORANGE)
    else:
        risk = ("🟢", "Faible", GREEN)

    # Entry quality: whether now is a good moment, distinct from the trend.
    if action == "BUY":
        entry = ("🟢", "Favorable", GREEN)
    elif crowded or gate == "EVENT_RISK" or trend["key"] == "DOWN" or (decision.score or 0) <= -30:
        entry = ("🔴", "Défavorable", RED)
    elif (stretched or near_resistance or spot_sellers
          or gate in {"CONTRADICTION", "CROWDING", "DATA_QUALITY", "FRESHNESS", "TECHNICAL_SETUP",
                      "SPOT_CONFIRMATION", "MARKET_REGIME"}
          or (decision.score or 0) < 15 or event_score >= 0.3):
        entry = ("🟠", "Mitigé", ORANGE)
    else:
        entry = ("🟢", "Favorable", GREEN)

    # One market sentence: what the market does, then what holds the entry.
    obstacles: list[tuple[str, bool]] = []  # (words, plural)
    if crowded:
        obstacles.append(("le levier", False))
    if near_resistance:
        obstacles.append(("la résistance proche", False))
    if stretched:
        obstacles.append(("un marché étiré", False))
    if spot_sellers:
        obstacles.append(("des vendeurs à l'initiative", True))
    if event_score >= 0.3 and top_event is not None:
        obstacles.append((f"l'échéance {top_event.title}", False))
    base = {
        "UP": "La hausse reste présente",
        "DOWN": "La baisse domine",
        "FLAT": "Le marché n'a pas de direction nette",
    }[trend["key"]]
    if action == "INSUFFICIENT_DATA":
        sentence = decision.headline
    elif action == "BUY":
        sentence = "Structure, comptant et levier confirment ensemble une configuration favorable."
    elif action == "SELL":
        sentence = "Cassure de structure, vendeurs à l'initiative et contexte dégradé : le risque domine."
    elif obstacles:
        words = [w for w, _ in obstacles]
        joined = words[0] if len(words) == 1 else ", ".join(words[:-1]) + " et " + words[-1]
        verb = "rendent" if len(words) > 1 or obstacles[0][1] else "rend"
        sentence = f"{base}, mais {joined} {verb} l'entrée moins attractive."
    elif trend["key"] == "UP" and entry[2] == GREEN:
        sentence = f"{base}, mais son avantage n'est pas prouvé statistiquement."
    elif trend["key"] == "DOWN":
        sentence = f"{base} : pas de point d'entrée à l'achat."
    else:
        sentence = f"{base} : le ratio risque / opportunité n'est pas assez clair."

    reasons = _reasons(decision, views, top_event)

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
        view = views[key]
        if view.get("hide_on_home"):
            continue
        home = view.get("home", {})
        name = DISPLAY_NAME[key]
        if key == CYCLE and asset != "BTC":
            name = "Régime Bitcoin"
        if key == MACRO:
            name = "Macro"
        home_families.append({
            "family": key,
            "emoji": FAMILY_EMOJI[key],
            "name": name,
            "status": home.get("status", ""),
            "status_emoji": home.get("status_emoji", ""),
            "tone": home.get("tone", WHITE),
            "key_info": home.get("key_info", ""),
        })

    # A family with no connected source is still listed: hiding it would let
    # the reader believe whales were measured and found quiet.
    if ONCHAIN in families and not families[ONCHAIN].usable and \
            not any(f["family"] == ONCHAIN for f in home_families):
        home_families.append({
            "family": ONCHAIN, "emoji": FAMILY_EMOJI[ONCHAIN],
            "name": DISPLAY_NAME[ONCHAIN], "status": "Source non branchée",
            "status_emoji": "⚪", "tone": WHITE,
            "key_info": "Rien n'est déduit de l'activité des grandes adresses.",
        })

    issues = []
    for key, view in views.items():
        if key in {ONCHAIN, LIQUIDITY}:
            continue
        for issue in view.get("data_issues", []):
            issues.append(f"{issue} — {DISPLAY_NAME.get(key, FAMILY_LABEL[key])}")
    confidence = decision.confidence
    from .interpretation import build_reading

    reading = build_reading(decision, views, top_event=top_event,
                            as_of=as_of if isinstance(as_of, datetime) else None, asset=asset)
    return {
        "reading": reading,
        "sentence": sentence,
        "trend": {"emoji": trend["emoji"], "label": trend["label"]},
        "entry_quality": {"emoji": entry[0], "label": entry[1], "tone": entry[2]},
        "risk": {"emoji": risk[0], "label": risk[1], "tone": risk[2]},
        "reasons": reasons,
        "home_families": home_families,
        "display_families": [k for k in DISPLAY_FAMILIES if k in families],
        "validation": validation,
        "confidence_label": (
            "Confiance élevée" if confidence >= 75
            else "Confiance moyenne" if confidence >= 55
            else "Confiance faible"
        ),
        "data_issues": issues[:3],
    }

"""The plan table, the human report and the validation report of a test run.

Two kinds of figures, never mixed:

  LEXA       values and allocations found in the transcript, with their passage
  CALCUL APP what the application computes (equal split when Lexa gives no
             allocation, average price, simulated value) - always labelled so
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .levels import STATE_FR, track
from .schema import BASIS_FR, AssetAnalysis, ExtractionResult, Level
from .simulation import SimLevel, simulate
from .transcript import format_ts

KIND_FR = {
    "SUPPORT": ("🧱", "Support"),
    "RESISTANCE": ("🧱", "Résistance"),
    "BUY_ZONE": ("🟢", "Zone d'achat"),
    "REINFORCEMENT": ("🟢", "Renforcement"),
    "CONFIRMATION": ("🚀", "Confirmation"),
    "INVALIDATION": ("⚠️", "Invalidation"),
    "TARGET": ("🔴", "Objectif"),
    "TAKE_PROFIT": ("🔴", "Prise de bénéfices"),
    "OTHER": ("📝", "Autre niveau"),
}
STANCE_FR = {"WAIT": "🟠 Attendre", "BUY": "🟢 Acheter", "SELL": "🔴 Vendre",
             "NEUTRAL": "⚪ Neutre", "UNSPECIFIED": "⚪ Non précisé"}
CONDITION_FR = {
    "BREAKOUT": "cassure", "CLOSE_ABOVE": "clôture au-dessus", "CLOSE_BELOW": "clôture en dessous",
    "RETEST": "retest", "VOLUME": "volume", "HOLD_ABOVE": "maintien au-dessus",
    "HOLD_BELOW": "maintien en dessous", "OTHER": "autre condition", "UNKNOWN": "non précisée",
}
TIMEFRAME_FR = {"15M": "15 min", "1H": "1 h", "4H": "4 h", "1D": "journalier",
                "1W": "hebdomadaire", "LONG_TERM": "long terme"}
ORDER = ["BUY_ZONE", "REINFORCEMENT", "CONFIRMATION", "INVALIDATION", "SUPPORT", "RESISTANCE",
         "TARGET", "TAKE_PROFIT", "OTHER"]
ENTRY = ("BUY_ZONE", "REINFORCEMENT")
EXITS = ("TARGET", "TAKE_PROFIT")
# Only these conditions can be checked on candles.
TRACKABLE = {("CLOSE_ABOVE", "1H"): "CLOSE_1H_ABOVE", ("CLOSE_ABOVE", "4H"): "CLOSE_4H_ABOVE",
             ("CLOSE_ABOVE", "1D"): "CLOSE_1D_ABOVE", ("CLOSE_BELOW", "1H"): "CLOSE_1H_BELOW",
             ("CLOSE_BELOW", "4H"): "CLOSE_4H_BELOW", ("CLOSE_BELOW", "1D"): "CLOSE_1D_BELOW"}


def price(value: float | None) -> str:
    if value is None:
        return "—"
    # Every decimal that was said, none added: 2,444175 stays 2,444175.
    text = f"{value:,.8f}".rstrip("0").rstrip(".")
    text = text.replace(",", "\u202f").replace(".", ",")
    return f"{text} $"


def computed_price(value: float | None) -> str:
    """A price the application computed: rounded, never mistaken for one Lexa said."""

    if value is None:
        return "—"
    return price(round(value, 2 if value >= 1000 else (4 if value >= 1 else 6)))


def eur(value: float | None) -> str:
    return "—" if value is None else f"{value:.2f} €".replace(".", ",")


def _ordered(levels: list[Level]) -> list[Level]:
    return sorted(levels, key=lambda lv: (ORDER.index(lv.kind), lv.value))


def _labels(asset: AssetAnalysis) -> dict[int, str]:
    """TP1, TP2 ... in price order; the entries as main / reinforcement."""

    labels: dict[int, str] = {}
    exits = sorted((lv for lv in asset.levels if lv.kind in EXITS), key=lambda lv: lv.value)
    for n, lv in enumerate(exits, 1):
        labels[id(lv)] = f"TP{n}" + (" (dernier objectif)" if n == len(exits) and n > 1 else "")
    for lv in asset.levels:
        if lv.kind == "BUY_ZONE":
            labels[id(lv)] = "Achat principal"
        elif lv.kind == "REINFORCEMENT":
            labels[id(lv)] = "Achat renforcé"
    return labels


def app_allocation(asset: AssetAnalysis, capital: float) -> tuple[dict[int, float], str]:
    """Euros per entry. Lexa's percentages when she gives them, else CALCUL APP."""

    entries = [lv for lv in asset.levels if lv.kind in ENTRY]
    if not entries:
        return {}, ""
    stated = [lv for lv in entries if lv.allocation_pct is not None]
    if len(stated) == len(entries):
        return {id(lv): capital * lv.allocation_pct / 100 for lv in entries}, "LEXA"
    share = capital / len(entries)
    return {id(lv): share for lv in entries}, "CALCUL APP"


def _situation(lv: Level, frame, published_at: datetime | None) -> str:
    if frame is None or published_at is None:
        return "Non suivi (pas de prix ou pas de date)"
    # Only a confirmation or an invalidation is confirmed by a close; a support
    # or a resistance is reached or not.
    condition = "UNKNOWN"
    if lv.kind in ("CONFIRMATION", "INVALIDATION"):
        condition = TRACKABLE.get((lv.condition.kind, lv.condition.timeframe or ""), "UNKNOWN")
    kind = "TARGET" if lv.kind in EXITS else lv.kind
    state = track(kind, lv.value, condition, frame, published_at)
    if lv.kind == "INVALIDATION" and state.state == "TOUCHED":
        return "⚠️ Niveau atteint (condition non vérifiable automatiquement)"
    if lv.kind in ("SUPPORT", "RESISTANCE") and state.state == "TOUCHED":
        return "🟢 Atteint"
    emoji, label = STATE_FR[state.state]
    return f"{emoji} {label}"


def plan(asset: AssetAnalysis, *, capital: float = 100.0, frame=None,
         published_at: datetime | None = None) -> dict[str, Any]:
    labels = _labels(asset)
    euros, allocation_source = app_allocation(asset, capital)
    rows: list[dict[str, Any]] = []
    if asset.price_at_video is not None:
        rows.append({
            "level": f"≈ {price(asset.price_at_video)}",
            "interpretation": STANCE_FR[asset.stance],
            "allocation": "0 €",
            "situation": "Prix cité dans la vidéo",
            "timestamp": format_ts(asset.price_at_video_evidence.timestamp_s),
            "basis": BASIS_FR[asset.stance_basis],
        })
    for lv in _ordered(asset.levels):
        emoji, kind_fr = KIND_FR[lv.kind]
        if lv.kind in ENTRY:
            lexa_pct = f"{lv.allocation_pct:g} % (Lexa)" if lv.allocation_pct is not None else "Non précisée par Lexa"
            allocation = f"{lexa_pct} · {eur(euros.get(id(lv)))} ({allocation_source})"
        elif lv.kind in EXITS:
            allocation = f"{lv.allocation_pct:g} % (Lexa)" if lv.allocation_pct is not None else "Non précisé par Lexa"
        else:
            allocation = "—"
        extra = []
        if lv.kind in ("CONFIRMATION", "INVALIDATION"):
            extra.append(f"condition : {CONDITION_FR[lv.condition.kind]}")
        if lv.timeframe:
            extra.append(TIMEFRAME_FR[lv.timeframe])
        rows.append({
            "level": price(lv.value),
            "interpretation": f"{emoji} {labels.get(id(lv), kind_fr)}"
                              + (f" ({', '.join(extra)})" if extra else ""),
            "allocation": allocation,
            "situation": _situation(lv, frame, published_at),
            "timestamp": format_ts(lv.evidence.timestamp_s),
            "basis": BASIS_FR[lv.basis],
        })

    simulation = None
    entries = [lv for lv in asset.levels if lv.kind in ENTRY]
    if entries and frame is not None and published_at is not None:
        sim_levels = [SimLevel(id=n, kind=lv.kind, value=lv.value,
                               allocation_pct=euros[id(lv)] / capital * 100)
                      for n, lv in enumerate(entries)]
        exits = sorted((lv for lv in asset.levels if lv.kind in EXITS), key=lambda lv: lv.value)
        sim_levels += [SimLevel(id=100 + n, kind=lv.kind, value=lv.value,
                                allocation_pct=lv.allocation_pct) for n, lv in enumerate(exits)]
        invalidation = next((lv.value for lv in asset.levels if lv.kind == "INVALIDATION"), None)
        simulation = simulate(sim_levels, frame, capital_eur=capital, published_at=published_at,
                              invalidation=invalidation).to_dict()
    return {"rows": rows, "allocation_source": allocation_source,
            "capital_eur": capital, "simulation": simulation}


# --- human report ------------------------------------------------------------------


def _quote(text: str) -> str:
    return f"« {text[:280]}{'…' if len(text) > 280 else ''} »"


def asset_report(asset: AssetAnalysis, table: dict[str, Any]) -> str:
    out = [f"## {asset.symbol}", ""]
    out += ["### 🧭 Situation", ""]
    if asset.price_at_video is not None:
        out.append(f"- Prix pendant la vidéo : **{price(asset.price_at_video)}** "
                   f"(🎬 {format_ts(asset.price_at_video_evidence.timestamp_s)})")
    else:
        out.append("- Prix pendant la vidéo : ⚪ Non précisé")
    out.append(f"- Position : {STANCE_FR[asset.stance]} — {BASIS_FR[asset.stance_basis]}")
    for claim in asset.situation:
        out.append(f"- {claim.text} — {BASIS_FR[claim.basis]} "
                   f"(🎬 {format_ts(claim.evidence.timestamp_s)})")
    out.append("")

    def block(title: str, kinds: tuple[str, ...]) -> None:
        levels = [lv for lv in _ordered(asset.levels) if lv.kind in kinds]
        out.extend([f"### {title}", ""])
        if not levels:
            out.extend(["⚪ Non précisé dans la vidéo.", ""])
            return
        for lv in levels:
            emoji, kind_fr = KIND_FR[lv.kind]
            out.append(f"**{price(lv.value)}** — {emoji} {kind_fr} · {BASIS_FR[lv.basis]}")
            if lv.kind in ("CONFIRMATION", "INVALIDATION"):
                tf = f", {TIMEFRAME_FR[lv.timeframe]}" if lv.timeframe else ""
                out.append(f"Condition : {CONDITION_FR[lv.condition.kind]}{tf}"
                           + (f" — {lv.condition.text}" if lv.condition.text else ""))
            if lv.allocation_pct is not None:
                ts = lv.allocation_evidence.timestamp_s if lv.allocation_evidence else None
                out.append(f"Allocation dite par Lexa : {lv.allocation_pct:g} % (🎬 {format_ts(ts)})")
            if lv.reasoning:
                out.append(f"Pourquoi (lecture du modèle) : {lv.reasoning}")
            out.append(f"🎬 {format_ts(lv.evidence.timestamp_s)} — {_quote(lv.evidence.quote)}")
            if lv.evidence.verification_note:
                out.append(f"ℹ️ {lv.evidence.verification_note}")
            out.append("")

    block("🟢 Zones surveillées", ENTRY)
    block("🧱 Supports et résistances", ("SUPPORT", "RESISTANCE"))
    block("🚀 Confirmation", ("CONFIRMATION",))
    block("🔴 Objectifs", EXITS)
    block("⚠️ Invalidation", ("INVALIDATION",))

    if asset.scenarios:
        out += ["### 🔀 Scénarios (conditionnels, non fusionnés)", ""]
        for sc in asset.scenarios:
            values = ", ".join(price(v) for v in sc.level_values) or "—"
            targets = ", ".join(price(v) for v in sc.targets) or "—"
            out.append(f"**Scénario {sc.scenario_id}** — si {sc.condition}")
            out.append(f"Niveaux : {values} · Objectifs : {targets} · "
                       f"Invalidation : {price(sc.invalidation)}")
            out.append(f"🎬 {format_ts(sc.evidence.timestamp_s)} — {_quote(sc.evidence.quote)}")
            out.append("")

    if asset.arguments:
        out += ["### 📊 Arguments utilisés", ""]
        for arg in asset.arguments:
            direction = {"BULLISH": "haussier", "BEARISH": "baissier", "NEUTRAL": "neutre"}.get(
                arg.direction or "", "direction non précisée")
            out.append(f"- **{arg.indicator}** : {arg.argument} ({direction}) — "
                       f"🎬 {format_ts(arg.evidence.timestamp_s)}")
        out.append("")
    if asset.events:
        out += ["### 📅 Événements cités", ""]
        for ev in asset.events:
            out.append(f"- **{ev.event}** — {ev.date or 'date non précisée'} — {ev.comment} "
                       f"(🎬 {format_ts(ev.evidence.timestamp_s)})")
        out.append("")
    if asset.reasoning:
        out += ["### 🧠 Raisonnement de Lexa (résumé du modèle)", ""]
        out += [f"- {r}" for r in asset.reasoning] + [""]

    out += [f"### 💶 Tableau sur {eur(table['capital_eur'])}", "",
            "| Niveau | Interprétation | Allocation | Situation | 🎬 | Source |",
            "|---|---|---|---|---|---|"]
    for row in table["rows"]:
        out.append(f"| {row['level']} | {row['interpretation']} | {row['allocation']} | "
                   f"{row['situation']} | {row['timestamp']} | {row['basis']} |")
    out.append("")
    if table["allocation_source"] == "CALCUL APP":
        out.append("> **SIMULATION APP** : Lexa ne donne pas de répartition. Le capital est "
                   "réparti à parts égales entre les entrées. Ce n'est pas une recommandation de Lexa.")
    sim = table.get("simulation")
    if sim:
        out.append(f"> **CALCUL APP** : investi {eur(sim['executed_eur'])}, "
                   f"en attente {eur(sim['remaining_eur'])}, prix moyen {computed_price(sim['average_price'])}, "
                   f"valeur actuelle {eur(sim['current_value_eur'])}.")
    out.append("")
    return "\n".join(out)


def human_report(result: ExtractionResult, tables: dict[str, dict[str, Any]]) -> str:
    head = [f"# 🎬 {result.video.title}", "",
            f"Publiée : {result.video.published_at or 'non précisé'} · "
            f"Source de la transcription : {result.transcript.source} · Modèle : {result.model}", "",
            "Tout ce qui suit est **ce que dit Lexa**, relu depuis la transcription. "
            "Rien ici ne modifie les décisions de l'application.", ""]
    body = [asset_report(a, tables[a.symbol]) for a in result.assets]
    if not result.assets:
        body = ["Aucune crypto n'a pu être rattachée à des niveaux vérifiés.", ""]
    return "\n".join(head + body)


# --- validation report ------------------------------------------------------------


def validation_report(result: ExtractionResult) -> str:
    t = result.transcript
    levels = sum(len(a.levels) for a in result.assets)
    rejected = [(a.symbol, r) for a in result.assets for r in a.rejected]
    ambiguous = [(a.symbol, x) for a in result.assets for x in a.ambiguous]
    inferred = [(a.symbol, lv) for a in result.assets for lv in a.levels if lv.basis != "EXPLICIT"]
    out = ["# Rapport de validation — premier test", "",
           "## TRANSCRIPTION", "",
           f"Durée analysée : {format_ts(t.duration_s)} ({t.segments} passages, {t.characters} caractères)",
           f"Qualité : {t.quality}",
           f"Passages incertains : {len(t.uncertain_passages)}"]
    out += [f"- 🎬 {format_ts(p.timestamp_s)} {_quote(p.quote)}" for p in t.uncertain_passages[:20]]
    out += ["", "## CRYPTOS DÉTECTÉES", ""]
    out += [f"- {s} : citée {n} fois" + (" → fiche" if s in {a.symbol for a in result.assets}
                                        else " → pas de fiche (non analysée ou rien de vérifié)")
            for s, n in result.assets_mentioned.items()] or ["- Aucune"]
    out += ["", "## INFORMATIONS EXTRAITES", ""]
    for a in result.assets:
        out.append(f"- {a.symbol} : {len(a.levels)} niveaux, {len(a.scenarios)} scénarios, "
                   f"{len(a.arguments)} arguments, {len(a.events)} événements")
    out += ["", "## INFORMATIONS AMBIGUËS", ""]
    lines = [f"- {s} : {x}" for s, x in ambiguous]
    lines += [f"- {s} : {price(lv.value)} classé {KIND_FR[lv.kind][1].lower()} par déduction "
              f"du contexte (🎬 {format_ts(lv.evidence.timestamp_s)})" for s, lv in inferred]
    out += lines or ["- Aucune signalée"]
    out += ["", "## INFORMATIONS NON TROUVÉES", ""]
    for a in result.assets:
        missing = [label for kinds, label in ((ENTRY, "zone d'achat"), (("CONFIRMATION",), "confirmation"),
                                              (("INVALIDATION",), "invalidation"), (EXITS, "objectifs"))
                   if not any(lv.kind in kinds for lv in a.levels)]
        if a.price_at_video is None:
            missing.insert(0, "prix pendant la vidéo")
        if not any(lv.allocation_pct is not None for lv in a.levels):
            missing.append("allocation (non dite : aucune n'est attribuée à Lexa)")
        out.append(f"- {a.symbol} : {', '.join(missing) if missing else 'rien de manquant'}")
    out += ["", "## ERREURS POSSIBLES", ""]
    out += [f"- {s} : {r.what} {price(r.value)} rejeté — {r.reason}" for s, r in rejected]
    out += [f"- {e}" for e in result.errors]
    if not rejected and not result.errors:
        out.append("- Aucune valeur rejetée par le vérificateur.")
    out += ["", "## COMPARAISON MANUELLE (à remplir par toi)", "",
            "✅ correct · 🟡 détecté mais mal interprété · 🔴 incorrect · ⚪ manquant", "",
            "| Crypto | Valeur | Lecture automatique | 🎬 | Ta lecture | Verdict |",
            "|---|---|---|---|---|---|"]
    for a in result.assets:
        for lv in _ordered(a.levels):
            out.append(f"| {a.symbol} | {price(lv.value)} | {KIND_FR[lv.kind][1]} | "
                       f"{format_ts(lv.evidence.timestamp_s)} |  |  |")
    out += ["| … | (niveaux que tu as entendus et qui manquent) | | | | ⚪ |", "",
            "## CONCLUSION TECHNIQUE", ""]
    total = levels + len(rejected)
    share = len(rejected) / total if total else 0
    if not result.assets:
        verdict = "🔴 Rien de vérifiable n'a été extrait : pas d'automatisation."
    elif result.errors:
        verdict = ("🔴 Le modèle local a échoué sur une partie de la vidéo (voir ERREURS "
                   "POSSIBLES) : le test est incomplet, pas d'automatisation.")
    elif share > 0.2:
        verdict = (f"🔴 {len(rejected)} valeurs sur {total} proposées par le modèle ne figurent pas "
                   "dans la transcription : pas assez fiable pour automatiser.")
    else:
        verdict = (f"🟡 {levels} niveaux vérifiés dans la transcription, {len(rejected)} rejetés. "
                   "La fiabilité des *valeurs* est contrôlée ; celle des *interprétations* ne peut "
                   "être jugée que par ta comparaison manuelle ci-dessus. Pas d'automatisation "
                   "avant ta validation.")
    out += [verdict, ""]
    return "\n".join(out)

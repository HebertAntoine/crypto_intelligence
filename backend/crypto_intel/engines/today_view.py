"""The cockpit projection: one analysis, arranged so it reads in ten seconds.

This module computes nothing. It is a pure function of an
`AnalysisContextSnapshot`, and every block it returns carries that snapshot's
`analysis_id`. Two consequences matter:

  * the screen never combines readings from two moments, because there is only
    one moment in here;
  * no decision is taken in Flutter. The page receives sentences and numbers
    that were already decided, and arranges them.

The order of the blocks is the order of the questions someone actually asks:
where is the market going, where is the price, is now interesting, why, what
would change it, what is coming, and how much of this rests on real data.

Three of those are kept apart on purpose and never merged into one score:

  DIRECTION   where the market has been going
  TIMING      whether this moment is a good place to act
  EDGE        whether any of it has been shown to predict returns

"Strongly bullish + wait + no measurable edge" is a coherent reading, and the
most common one this system produces.
"""

from __future__ import annotations

from typing import Any

from ..core import labels_fr
from ..core.enums import Asset

# One vocabulary, one table, in `core/labels_fr.py`. Re-exported here because
# this module is where the page's wording is assembled and read.
DIRECTION_FR = labels_fr.DIRECTION_FR
TIMING_FR = labels_fr.TIMING_FR
EDGE_FR = labels_fr.EDGE_FR
LOCATION_FR = labels_fr.LOCATION_TITLE_FR
STRUCTURE_FR = labels_fr.STRUCTURE_FR
VOLATILITY_FR = labels_fr.VOLATILITY_FR
PRICING_FR = labels_fr.PRICING_FR
CROWDING_FR = labels_fr.CROWDING_FR
FUNDING_BAND_FR = labels_fr.FUNDING_BAND_FR
LEVERAGE_STATE_FR = labels_fr.LEVERAGE_STATE_FR
TIMEFRAME_FR = labels_fr.TIMEFRAME_FR
EVENT_KIND_FR = labels_fr.EVENT_KIND_FR

MACRO_ALERT_HOURS = 24.0


def edge_label(state: str, tested: int) -> str:
    """Never having tested is not the same answer as having found nothing."""
    if state == "INSUFFICIENT_DATA" and tested:
        return "PREUVE INSUFFISANTE"
    return EDGE_FR.get(state, "NON TESTÉ")


def _label(table: dict[str, str], value: Any, default: str = "Indisponible") -> str:
    key = str(getattr(value, "value", value) or "").upper()
    return table.get(key, default)


def _enum(value: Any, default: str = "") -> str:
    return str(getattr(value, "value", value) or default)


# --- direction / timing / edge --------------------------------------------

def direction_timing_edge(snapshot: Any) -> dict[str, Any]:
    """Three independent readings, stated as three, never as one score."""
    regime_label = _enum(getattr(snapshot.regime, "regime", None), "UNDETERMINED")
    edge_state = _enum(getattr(snapshot.edge, "state", None), "NO_MEASURABLE_EDGE")
    decision_state = _enum(getattr(snapshot.opportunity, "state", None), "INSUFFICIENT_DATA")
    confidence = float(getattr(snapshot.regime, "confidence", 0) or 0)
    tested = int(getattr(snapshot.edge, "admitted_count", 0) or 0) + int(
        getattr(snapshot.edge, "rejected_count", 0) or 0
    )
    return {
        "direction": {
            "value": DIRECTION_FR.get(regime_label, "INDÉTERMINÉE"),
            "state": regime_label,
            "detail": (
                f"Tendance, structure et momentum concordent à {confidence:.0f} %."
                if confidence else "Historique insuffisant pour reconstruire un régime."
            ),
            "question": "Où va le marché ?",
        },
        "timing": {
            "value": TIMING_FR.get(decision_state, "INDÉTERMINÉ"),
            "state": decision_state,
            "detail": getattr(snapshot.opportunity, "summary", ""),
            "question": "Est-ce intéressant maintenant ?",
        },
        "edge": {
            "value": edge_label(edge_state, tested),
            "state": edge_state,
            "detail": (
                "Au moins une relation a franchi les baselines et les contrôles."
                if edge_state == "POSITIVE_EDGE"
                else f"{tested} relation(s) testée(s); aucune n'a survécu aux "
                     "contrôles statistiques."
                if tested
                else "Aucune étude n'a encore été menée pour cet actif. Ce n'est "
                     "pas la même chose que ne rien avoir trouvé."
            ),
            "question": "Est-ce historiquement démontré ?",
        },
        "note": (
            "Ces trois lectures sont indépendantes. Une direction haussière, un "
            "timing « attendre » et aucun avantage démontré est une combinaison "
            "cohérente, pas une contradiction."
        ),
    }


# --- where the price sits -------------------------------------------------

def structural_position(snapshot: Any) -> dict[str, Any]:
    """The position bar, or an honest replacement when there is no range.

    A bar with invented endpoints would be worse than no bar. When the range
    engine reports nothing validated, the block says which structure was found
    instead and the bar is simply absent.
    """
    location = snapshot.location
    state = _enum(getattr(location, "state", None), "NO_VALID_RANGE")
    detected = getattr(location, "detected_range", None)
    position = getattr(location, "relative_position", None)
    top = getattr(getattr(detected, "top_zone", None), "midpoint", None)
    bottom = getattr(getattr(detected, "bottom_zone", None), "midpoint", None)
    valid = bool(
        getattr(detected, "valid", False)
        and top is not None and bottom is not None and position is not None
    )
    structure_state = _enum(
        (snapshot.structure.get("timeframes", {}).get("4h", {}) or {}).get("state"),
        "UNCLEAR",
    )
    if not valid:
        return {
            "has_range": False,
            "timeframe": "4H",
            "headline": _label(STRUCTURE_FR, structure_state, "Structure indéterminée"),
            "detail": (
                getattr(location, "range_summary", "")
                or "Aucun range validé n'a été détecté sur cette unité de temps."
            ),
            "reason": "; ".join(getattr(location, "explanation", [])[:2]),
            "note": (
                "Aucune barre de position n'est affichée : fabriquer des bornes "
                "de range pour la remplir donnerait une fausse précision."
            ),
        }
    percent = round(max(0.0, min(1.0, float(position))) * 100)
    return {
        "has_range": True,
        "timeframe": "4H",
        "headline": LOCATION_FR.get(state, "Position dans le range"),
        "state": state,
        "range_bottom": bottom,
        "range_midpoint": getattr(detected, "midpoint", None),
        "range_top": top,
        "price": getattr(location, "price", None),
        "relative_position": round(float(position), 4),
        "percent": percent,
        "bottom_label": "Bas du range",
        "top_label": "Haut du range",
        "detail": f"{percent} % de la hauteur du range 4H",
        "invalidation": getattr(location, "invalidation", ""),
        "note": (
            "La position est descriptive. Être proche d'un bord ne prédit rien "
            "par soi-même."
        ),
    }


def nearest_levels(snapshot: Any, price: float | None = None) -> dict[str, Any]:
    """The closest support below and resistance above, with real distances.

    Levels come from the swing-cluster engine. Nothing is placed by hand, and
    when the clustering finds none the block says so rather than falling back
    to a round number.
    """
    reference = price if price is not None else snapshot.price_at_analysis

    def nearest(levels: list[Any], below: bool) -> dict[str, Any] | None:
        if reference is None:
            return None
        candidates = [
            level for level in levels
            if getattr(level, "price", None) is not None
            and (level.price < reference if below else level.price > reference)
        ]
        if not candidates:
            return None
        best = min(candidates, key=lambda level: abs(level.price - reference))
        return {
            "price": round(float(best.price), 2),
            "distance_pct": round((best.price - reference) / reference * 100, 2),
            "touches": getattr(best, "touches", None),
            "strength": getattr(best, "strength", None),
            "last_touch": (
                best.last_touch.isoformat() if getattr(best, "last_touch", None) else None
            ),
        }

    support = nearest(snapshot.supports, below=True)
    resistance = nearest(snapshot.resistances, below=False)
    return {
        "reference_price": reference,
        "support": support,
        "resistance": resistance,
        "available": bool(support or resistance),
        "source": "clusters de swings 4H (TechnicalAnalysisEngine)",
        "reason": (
            "" if support or resistance
            else "aucun niveau n'a été touché assez souvent pour être retenu"
        ),
    }


# --- immediate context ----------------------------------------------------

def immediate_context(snapshot: Any) -> list[dict[str, Any]]:
    """Four readings at most: position, volatility, crowding, next event."""
    out: list[dict[str, Any]] = []
    position = structural_position(snapshot)
    out.append({
        "label": "Position",
        "value": position["headline"],
        "detail": position.get("detail", ""),
    })
    out.append({
        "label": "Volatilité",
        "value": _label(VOLATILITY_FR, getattr(snapshot.volatility, "regime", None), "Inconnue"),
        "detail": "Volatilité réalisée sur 30 jours, mesure d'amplitude et non de sens.",
    })
    crowding_level = _enum(getattr(snapshot.crowding, "level", None), "UNKNOWN")
    out.append({
        "label": "Encombrement",
        "value": CROWDING_FR.get(crowding_level, "Inconnu"),
        "detail": "Positionnement dérivé agrégé; il ne donne pas de direction.",
    })
    if snapshot.macro_events:
        event = snapshot.macro_events[0]
        out.append({
            "label": "Prochain événement",
            "value": f"{_event_name(event)} · {_countdown(event)}",
            "detail": "Date programmée et publiée à l'avance.",
        })
    return out[:4]


# --- catalysts ------------------------------------------------------------

def _event_name(event: dict[str, Any]) -> str:
    kind = str(event.get("kind") or "").upper()
    return EVENT_KIND_FR.get(kind, str(event.get("name") or kind or "Événement"))


def _countdown(event: dict[str, Any]) -> str:
    hours = float(event.get("hours_until") or 0)
    if hours < 1:
        return "dans moins d'une heure"
    if hours < 24:
        return f"dans {hours:.0f} h"
    days = hours / 24
    if days < 2:
        return "demain"
    return f"dans {days:.0f} jours"


def catalysts(snapshot: Any, limit: int = 3) -> dict[str, Any]:
    """The few scheduled events worth knowing about, ranked, never a news feed.

    Relevance is stated, not scored opaquely: it is the event's published
    importance and how soon it lands. Nothing here claims to know what the
    event will do to the price.
    """
    importance_rank = {"CRITICAL": 3, "HIGH": 2, "MEDIUM": 1, "LOW": 0}
    items: list[dict[str, Any]] = []
    for event in snapshot.macro_events:
        hours = float(event.get("hours_until") or 0)
        if hours <= 0 or hours > 24 * 7:
            continue
        importance = str(event.get("importance") or "MEDIUM").upper()
        # Sooner and more important ranks higher; both halves are visible.
        horizon_score = 3 if hours <= 24 else 2 if hours <= 72 else 1
        items.append({
            "type": "MACRO",
            "kind": event.get("kind"),
            "name": _event_name(event),
            "when": _countdown(event),
            "scheduled_at": event.get("scheduled_at"),
            "hours_until": hours,
            "importance": importance,
            "importance_label": {
                "CRITICAL": "Majeur", "HIGH": "Important",
                "MEDIUM": "Modéré", "LOW": "Mineur",
            }.get(importance, "Modéré"),
            "asset_scope": event.get("assets") or ["BTC", "ETH", "SOL"],
            "relevance": importance_rank.get(importance, 1) * 10 + horizon_score,
            "source": event.get("source"),
        })
    items.sort(key=lambda item: (-item["relevance"], item["hours_until"]))
    imminent = [
        item for item in items
        if item["importance"] == "CRITICAL" and item["hours_until"] <= MACRO_ALERT_HOURS
    ]
    alert = None
    if imminent:
        hours = imminent[0]["hours_until"]
        alert = {
            "label": f"ÉVÉNEMENT IMPORTANT DANS {hours:.0f} H",
            "name": imminent[0]["name"],
            "hours_until": hours,
            "note": (
                "Le sens n'est pas prédit. Le moteur de décision applique déjà "
                "son garde-fou; rien n'est décidé à l'écran."
            ),
        }
    return {
        "items": items[:limit],
        "alert": alert,
        "horizon_note": "Événements programmés des 7 prochains jours, 24-72 h en priorité.",
        "not_news": (
            "Cette liste ne contient que des échéances programmées et sourcées, "
            "pas un flux d'actualité."
        ),
    }


# --- what would change the reading ----------------------------------------

def change_conditions(snapshot: Any, limit: int = 2) -> dict[str, Any]:
    """Conditions, phrased as conditions, in three separate categories."""
    opportunity = snapshot.opportunity

    def sentences(items: list[str], prefix: str) -> list[dict[str, str]]:
        return [{"text": f"{prefix} {item}"} for item in items[:limit]]

    return {
        "improve": sentences(
            opportunity.improvement_conditions, "Le timing deviendrait plus favorable avec"
        ),
        "degrade": sentences(
            opportunity.deterioration_conditions, "La lecture serait dégradée par"
        ),
        # Third category, and not a sign: a range break invalidates the range
        # without making the market worse. Filing it under "would degrade" is
        # what made a bullish break read as a deterioration.
        "structure_change": sentences(
            opportunity.structure_change_conditions, "La structure changerait avec"
        ),
        "improve_title": "POUR DEVENIR PLUS FAVORABLE",
        "degrade_title": "POUR DEVENIR MOINS FAVORABLE",
        "structure_change_title": "CHANGEMENT À SURVEILLER",
        "note": (
            "Ce sont des conditions, pas des prévisions. Aucune de ces phrases "
            "n'annonce ce que le prix va faire."
        ),
    }


# --- timeframes -----------------------------------------------------------

def timeframe_summary(snapshot: Any) -> dict[str, Any]:
    """1W / 1D / 4H / 1H, each named in words as well as drawn.

    An arrow alone is not readable by everyone and not readable at all by a
    screen reader, so every row carries its label.
    """
    readings = snapshot.structure.get("timeframes", {}) or {}
    rows: list[dict[str, Any]] = []
    for timeframe in ("1w", "1d", "4h", "1h"):
        reading = readings.get(timeframe) or {}
        state = str(reading.get("state") or "UNCLEAR")
        rows.append({
            "timeframe": TIMEFRAME_FR.get(timeframe, timeframe.upper()),
            "key": timeframe,
            "state": state,
            "label": STRUCTURE_FR.get(state, "Indéterminée"),
            "arrow": {"BULLISH_STRUCTURE": "↑", "BEARISH_STRUCTURE": "↓"}.get(state, "↔"),
            "swings_used": reading.get("swings_used"),
        })
    bullish = [row for row in rows if row["state"] == "BULLISH_STRUCTURE"]
    bearish = [row for row in rows if row["state"] == "BEARISH_STRUCTURE"]
    named = [row for row in rows if row["state"] in
             ("BULLISH_STRUCTURE", "BEARISH_STRUCTURE", "RANGE_STRUCTURE")]
    directional = bullish + bearish
    if len(named) <= 1:
        alignment, label = "UNDETERMINED", "Indéterminé"
    elif bullish and bearish:
        alignment, label = "DIVERGENT", "Divergent"
    elif not directional:
        # Every readable timeframe is in a range. That is agreement, not a
        # partial one: they all say the same thing.
        alignment, label = "ALIGNED", "Aligné (toutes en range)"
    elif len(directional) == len(named):
        alignment, label = "ALIGNED", "Aligné"
    else:
        alignment, label = "PARTIAL", "Partiellement aligné"
    return {
        "rows": rows,
        "alignment": alignment,
        "alignment_label": label,
        "note": (
            "L'alignement est descriptif. Des unités de temps qui concordent ne "
            "constituent pas un avantage démontré."
        ),
    }


def contradictions(snapshot: Any) -> dict[str, Any]:
    """Named disagreements between readings that are each individually true."""
    found: list[dict[str, str]] = []
    regime = _enum(getattr(snapshot.regime, "regime", None), "UNDETERMINED")
    weekly = str(
        (snapshot.structure.get("timeframes", {}).get("1w", {}) or {}).get("state") or ""
    )
    if "BULL" in regime and weekly == "BEARISH_STRUCTURE":
        found.append({
            "title": "Régime haussier, structure hebdomadaire baissière",
            "text": (
                "La tendance récente est positive, mais la structure de plus long "
                "terme n'est pas encore totalement alignée."
            ),
        })
    if "BEAR" in regime and weekly == "BULLISH_STRUCTURE":
        found.append({
            "title": "Régime baissier, structure hebdomadaire haussière",
            "text": (
                "Le mouvement récent est négatif alors que la structure de fond "
                "reste haussière. Les deux lectures sont exactes."
            ),
        })
    if snapshot.structure.get("conflict"):
        found.append({
            "title": "Unités de temps en désaccord",
            "text": (
                "Les unités de temps ne décrivent pas la même chose : les plus "
                "hautes donnent le contexte, les plus basses la jambe en cours."
            ),
        })
    for text in getattr(snapshot.pressure, "contradictions", []) or []:
        found.append({"title": "Sources de pression opposées", "text": str(text)})
    return {
        "items": found[:3],
        "has_contradiction": bool(found),
        "badge": "LECTURE MIXTE" if found else "",
    }


# --- volatility, edge, pressure, positioning ------------------------------

def volatility_block(snapshot: Any) -> dict[str, Any]:
    """Realised and implied kept apart: they answer different questions."""
    realised_state = _enum(getattr(snapshot.volatility, "regime", None), "UNKNOWN")
    implied = snapshot.implied_volatility
    available = bool(getattr(implied, "available", False))
    return {
        "headline": VOLATILITY_FR.get(realised_state, "Inconnue"),
        "realised": {
            "state": realised_state,
            "label": VOLATILITY_FR.get(realised_state, "Inconnue"),
            "direction": _enum(getattr(snapshot.volatility, "direction", None), "STABLE"),
            "percentile": getattr(snapshot.volatility, "atr_percentile", None),
        },
        "implied": {
            "available": available,
            "label": (
                PRICING_FR.get(_enum(getattr(implied, "pricing", None), "UNKNOWN"), "non évaluée")
                if available else "Indisponible"
            ),
            "dvol": getattr(implied, "dvol", None),
            "percentile": getattr(implied, "dvol_percentile", None),
            "reason": "" if available else str(getattr(implied, "unavailable_reason", "")),
        },
        "note": (
            "Réalisée = ce qui s'est produit. Implicite = ce que les options "
            "font payer. Les deux ne sont jamais additionnées."
        ),
    }


def edge_block(snapshot: Any) -> dict[str, Any]:
    """The measured edge, small on the page and complete underneath."""
    edge = snapshot.edge
    state = _enum(getattr(edge, "state", None), "NO_MEASURABLE_EDGE")
    analogs = snapshot.analogs or {}
    effective = analogs.get("effective_n")
    tested = int(getattr(edge, "admitted_count", 0) or 0) + int(
        getattr(edge, "rejected_count", 0) or 0
    )
    return {
        "state": state,
        "label": edge_label(state, tested),
        "tested_relations": tested,
        "tooltip": (
            "Les configurations historiques comparables n’ont pas démontré de "
            "surperformance robuste après les contrôles statistiques."
        ),
        "evidence_label": (
            "Preuve limitée" if state != "POSITIVE_EDGE" and (effective or 0) < 20 else ""
        ),
        "admitted": getattr(edge, "admitted_count", None),
        "rejected": getattr(edge, "rejected_count", None),
        # The sample figures belong in the detail sheet, not on the card.
        "detail": {
            "raw_n": analogs.get("raw_n"),
            "effective_n": effective,
            "median_return_7d": analogs.get("median_return"),
            "hit_rate_7d": analogs.get("hit_rate"),
            "mfe_7d": analogs.get("mfe"),
            "mae_7d": analogs.get("mae"),
        },
        "not_a_bearish_signal": (
            "L'absence d'avantage démontré ne dit pas que le prix va baisser. "
            "Elle dit que rien n'a été démontré."
        ),
    }


def pressure_block(snapshot: Any) -> dict[str, Any]:
    """Who is buying, who is selling - headline on the page, detail on tap."""
    return pressure_breakdown(snapshot)


def positioning_block(snapshot: Any) -> dict[str, Any]:
    """Positioning, funding and crowding in words; the raw numbers live in evidence."""
    return {
        "positioning": {
            "label": "Positionnement",
            "value": LEVERAGE_STATE_FR.get(
                _enum(getattr(snapshot.leverage_state, "state", None), "UNKNOWN"), "Indisponible"
            ),
        },
        "funding": {
            "label": "Funding",
            "value": FUNDING_BAND_FR.get(
                _enum(getattr(snapshot.funding, "band", None), "UNKNOWN"), "Indisponible"
            ),
        },
        "crowding": {
            "label": "Encombrement",
            "value": CROWDING_FR.get(
                _enum(getattr(snapshot.crowding, "level", None), "UNKNOWN"), "Inconnu"
            ),
        },
        "note": "Les valeurs brutes sont dans l'écran Preuves.",
    }


# --- who buys, who sells --------------------------------------------------

def pressure_breakdown(snapshot: Any) -> dict[str, Any]:
    """Every family's contribution, with the arithmetic left visible.

    The total is a weighted average of the families that actually reported, so
    an absent source is removed from the denominator. It is never folded in as
    a zero: "no data" and "no pressure" are different statements, and treating
    the first as the second quietly pulls every score towards neutral.
    """
    pressure = snapshot.pressure
    components = list(getattr(pressure, "components", []) or [])
    score = getattr(pressure, "pressure_score", None)

    usable = [
        component for component in components
        if getattr(component, "available", False)
        and getattr(component, "normalized_pressure", None) is not None
    ]
    denominator = sum(
        float(component.weight) * float(component.confidence) for component in usable
    )

    def described(component: Any) -> dict[str, Any]:
        available = bool(getattr(component, "available", False))
        normalized = getattr(component, "normalized_pressure", None)
        weight = float(getattr(component, "weight", 0) or 0)
        confidence = float(getattr(component, "confidence", 0) or 0)
        contribution = (
            round(float(normalized) * weight * confidence / denominator, 2)
            if available and normalized is not None and denominator else None
        )
        return {
            "family": getattr(component, "name", ""),
            "label": getattr(component, "label", ""),
            "availability": "AVAILABLE" if available else "UNAVAILABLE",
            "available": available,
            "raw_input": getattr(component, "raw_value", None),
            "normalized_score": (
                round(float(normalized), 1) if normalized is not None else None
            ),
            # Classified by sign, not by a magnitude threshold: a small
            # selling contribution is still a selling contribution, and its
            # size is printed next to it.
            "direction": (
                "UNKNOWN" if not available or normalized is None else
                "BUYING" if float(normalized) > 0 else
                "SELLING" if float(normalized) < 0 else "NEUTRAL"
            ),
            "weight_if_any": weight,
            "confidence": confidence,
            "contribution_points": contribution,
            "source": getattr(component, "source", ""),
            "timestamp": getattr(component, "as_of", None),
            "freshness": getattr(component, "freshness", "UNAVAILABLE"),
            "explanation": (
                getattr(component, "detail", "") if available
                else getattr(component, "reason", "")
            ),
        }

    described_all = [described(component) for component in components]
    buyers = sorted(
        [item for item in described_all if item["direction"] == "BUYING"],
        key=lambda item: -(item["normalized_score"] or 0),
    )
    sellers = sorted(
        [item for item in described_all if item["direction"] == "SELLING"],
        key=lambda item: item["normalized_score"] or 0,
    )
    neutral = [item for item in described_all if item["direction"] == "NEUTRAL"]
    unavailable = [item for item in described_all if not item["available"]]
    reconstructed = (
        round(sum(item["contribution_points"] or 0 for item in described_all), 1)
        if denominator else None
    )
    state = _enum(getattr(pressure, "state", None), "INSUFFICIENT_DATA")
    return {
        "state": state,
        "label": getattr(pressure, "label", ""),
        "score": score,
        "headline": (
            f"{getattr(pressure, 'label', '')} {score:+.0f}/100"
            if score is not None else "Pression indéterminée"
        ),
        "families_active": len(usable),
        "families_total": len(components),
        "families_line": f"{len(usable)}/{len(components)} familles disponibles",
        "buyers": buyers,
        "sellers": sellers,
        "neutral": neutral,
        "unavailable": unavailable,
        "buyers_title": "FACTEURS ACHETEURS",
        "sellers_title": "FACTEURS VENDEURS",
        "unavailable_title": "INDISPONIBLE",
        "contradictions": list(getattr(pressure, "contradictions", []) or []),
        "reconstruction": {
            "method": "moyenne pondérée des familles disponibles",
            "formula": "score = Σ(score_normalisé × poids × confiance) / Σ(poids × confiance)",
            "denominator": round(denominator, 4) if denominator else 0.0,
            "sum_of_contributions": reconstructed,
            "matches_score": (
                None if score is None or reconstructed is None
                else abs(reconstructed - float(score)) <= 0.5
            ),
        },
        "tooltip": (
            "Ce score mesure la pression relative des facteurs disponibles. Il "
            "ne représente ni une probabilité de hausse ni une edge statistique."
        ),
        "missing_note": (
            "Une source absente n'est ni neutre ni zéro : elle est retirée du "
            "calcul et listée ici."
        ),
    }


# --- data coverage --------------------------------------------------------

def coverage_block(snapshot: Any) -> dict[str, Any]:
    """What we could actually look at, kept distinct from how sure we are.

    Uncertainty and coverage answer different questions and are shown as two
    numbers on purpose. "Incertitude 60/100 élevée" alongside "couverture 85 %
    bonne" is a perfectly coherent pair: we saw most of the evidence, and the
    evidence does not agree.
    """
    coverage = snapshot.coverage
    if coverage is None:
        return {"available": False}
    payload = coverage.to_dict()
    families = payload["families"]
    payload.update({
        "available_families": [
            item for item in families if item["coverage"] == "EXPECTED_AND_AVAILABLE"
        ],
        "missing_families": [
            item for item in families if item["coverage"] == "EXPECTED_BUT_MISSING"
        ],
        "not_applicable_families": [
            item for item in families if item["coverage"] == "NOT_APPLICABLE"
        ],
        "by_design_families": [
            item for item in families if item["coverage"] == "UNAVAILABLE_BY_DESIGN"
        ],
        "stale_families": [item for item in families if item["stale"]],
        "titles": {
            "available": "DONNÉES DISPONIBLES",
            "missing": "DONNÉES MANQUANTES",
            "not_applicable": "NON APPLICABLE",
            "by_design": "NON COLLECTÉ PAR CONCEPTION",
            "stale": "PRÉSENTES MAIS PÉRIMÉES",
        },
        "uncertainty_score": getattr(snapshot.uncertainty, "score", None),
        "uncertainty_note": (
            "L'incertitude décrit la solidité de la conclusion. La couverture "
            "décrit ce que nous avons pu observer. Les deux sont distinctes."
        ),
    })
    return payload


# --- the decision itself --------------------------------------------------

def decision_sentence(snapshot: Any) -> str:
    """A short, deterministic sentence built from the dominant readings.

    No model writes this. It is assembled from the regime, the structural
    position and the guard rail that actually capped the state, so it can only
    say things the snapshot already contains.
    """
    asset = snapshot.asset
    opportunity = snapshot.opportunity
    state = _enum(getattr(opportunity, "state", None), "INSUFFICIENT_DATA")
    if state == "INSUFFICIENT_DATA":
        return (
            "Les données majeures ne permettent pas d'évaluer la situation "
            "actuellement. Aucune lecture n'est proposée."
        )

    regime = _enum(getattr(snapshot.regime, "regime", None), "UNDETERMINED")
    clauses: list[str] = []
    if "STRONGLY_BULL" in regime:
        clauses.append("La tendance de fond est nettement positive")
    elif "BULL" in regime:
        clauses.append("La tendance de fond reste positive")
    elif "STRONGLY_BEAR" in regime:
        clauses.append("La tendance de fond est nettement négative")
    elif "BEAR" in regime:
        clauses.append("La tendance de fond reste négative")
    elif regime == "NEUTRAL":
        clauses.append("La tendance de fond est sans direction nette")

    location_state = _enum(getattr(snapshot.location, "state", None), "NO_VALID_RANGE")
    location_clause = {
        "AT_RANGE_TOP": f"{asset} est sur le haut de son range 4H",
        "NEAR_RANGE_TOP": f"{asset} évolue proche du haut de son range 4H",
        "UPPER_THIRD": f"{asset} se situe dans le tiers haut de son range 4H",
        "MID_RANGE": "le prix se situe au milieu de son range 4H",
        "LOWER_THIRD": f"{asset} se situe dans le tiers bas de son range 4H",
        "NEAR_RANGE_BOTTOM": f"{asset} évolue proche du bas de son range 4H",
        "AT_RANGE_BOTTOM": f"{asset} est sur le bas de son range 4H",
        "ABOVE_RANGE": f"{asset} est sorti par le haut de son range 4H",
        "BELOW_RANGE": f"{asset} est sorti par le bas de son range 4H",
    }.get(location_state, "")
    unfavourable_location = location_state in (
        "AT_RANGE_TOP", "NEAR_RANGE_TOP", "UPPER_THIRD"
    )
    if location_clause:
        joiner = (
            "mais" if clauses and unfavourable_location and state in ("WAIT", "WATCH", "UNFAVORABLE")
            else "et"
        )
        clauses.append(f"{joiner} {location_clause}" if clauses else location_clause)

    conclusion = {
        "STRONG_OPPORTUNITY": "Les facteurs majeurs concordent et l'emplacement n'est pas défavorable.",
        "OPPORTUNITY": "Aucun facteur majeur ne justifie actuellement d'attendre.",
        "WATCH": "La configuration mérite d'être suivie, sans justifier d'agir maintenant.",
        "WAIT": "Le timing actuel n'est pas suffisamment favorable.",
        "UNFAVORABLE": "La configuration est moins favorable que la normale.",
    }.get(state, "")

    guard = (getattr(opportunity, "guard_rails_applied", []) or [])[:1]
    first = ", ".join(clauses) if clauses else ""
    sentence = (first + ". " if first else "") + conclusion
    if guard and state in ("WAIT", "WATCH", "UNFAVORABLE"):
        sentence += f" Raison retenue : {guard[0].rstrip('.')}."
    return sentence.strip()


def decision_block(snapshot: Any) -> dict[str, Any]:
    """The headline verdict, its sentence, and the evidence ranked beneath it."""
    opportunity = snapshot.opportunity
    state = _enum(getattr(opportunity, "state", None), "INSUFFICIENT_DATA")
    return {
        "state": state,
        "headline": opportunity.headline,
        "label": TIMING_FR.get(state, "INDÉTERMINÉ"),
        "sentence": decision_sentence(snapshot),
        "summary": opportunity.summary,
        "score": opportunity.score,
        "guard_rails": list(opportunity.guard_rails_applied),
        "positives": [factor.to_dict() for factor in opportunity.positives],
        "waits": [factor.to_dict() for factor in opportunity.waits],
        "negatives": [factor.to_dict() for factor in opportunity.negatives],
        "missing": [factor.to_dict() for factor in opportunity.missing],
        "disclaimer": (
            "Évaluation déterministe du contexte, pas une garantie de performance "
            "ni un conseil. L’application ne passe aucun ordre."
        ),
    }


def last_change_block(asset: Asset, now: Any = None) -> dict[str, Any]:
    """When the verdict last moved, from recorded readings or not at all."""
    from ..history.decisions import last_decision_change

    change = last_decision_change(asset, now=now)
    if change is None:
        return {
            "available": False,
            "reason": (
                "Pas encore assez de lectures enregistrées pour dater un "
                "changement. Rien n'est reconstruit après coup."
            ),
        }
    return {
        "available": True,
        "title": "DERNIER CHANGEMENT DE LECTURE",
        "changed_at": change["changed_at"],
        "from_label": TIMING_FR.get(change["from_state"], change["from_state"]),
        "to_label": TIMING_FR.get(change["to_state"], change["to_state"]),
        "text": (
            f"Timing passé de {TIMING_FR.get(change['from_state'], change['from_state'])} "
            f"à {TIMING_FR.get(change['to_state'], change['to_state'])}"
        ),
        "reason": change["reason"],
        "reason_title": change["reason_title"],
    }


# --- the whole page -------------------------------------------------------

def render(snapshot: Any, live_price: float | None = None) -> dict[str, Any]:
    """The compact page, in the order the questions are asked.

    Every block carries the snapshot's `analysis_id`, so a client can refuse to
    combine two of them rather than silently showing a mixture.
    """
    asset = Asset(snapshot.asset)
    return {
        "analysis_id": snapshot.analysis_id,
        "asset": snapshot.asset,
        "analysis_time": snapshot.analysis_time.isoformat(),
        "price_at_analysis": snapshot.price_at_analysis,
        "direction_timing_edge": direction_timing_edge(snapshot),
        "decision": decision_block(snapshot),
        "structural_position": structural_position(snapshot),
        "levels": nearest_levels(snapshot, live_price),
        "immediate_context": immediate_context(snapshot),
        "pressure": pressure_breakdown(snapshot),
        "catalysts": catalysts(snapshot),
        "change_conditions": change_conditions(snapshot),
        "timeframes": timeframe_summary(snapshot),
        "contradictions": contradictions(snapshot),
        "volatility": volatility_block(snapshot),
        "edge": edge_block(snapshot),
        "positioning": positioning_block(snapshot),
        "etf": snapshot.etf,
        "coverage": coverage_block(snapshot),
        "last_change": last_change_block(asset, snapshot.analysis_time),
        "reading_order": [
            "direction_timing_edge", "decision", "structural_position",
            "immediate_context", "pressure", "catalysts", "change_conditions",
            "coverage",
        ],
    }

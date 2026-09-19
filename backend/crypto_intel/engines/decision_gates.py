"""From six family scores to BUY / WAIT / SELL, through gates first.

The order is fixed and every gate is evaluated, so the reader always sees why:

    1. DATA QUALITY     critical families missing        -> INSUFFICIENT_DATA
    2. FRESHNESS        critical data stale               -> WAIT
    3. EVENT RISK       major event inside the horizon    -> WAIT
    4. UNCERTAINTY      confidence too low, no proven edge -> WAIT
    5. CONTRADICTION    strong families pulling apart     -> WAIT
    6. CROWDING/EXTREME leverage against the move, panic  -> WAIT
    7. FINAL            score, confidence, confirmations -> BUY / SELL / WAIT

The first gate that blocks decides. A score slightly above zero is never enough:
BUY and SELL need a clear score, a high confidence and several independent
families agreeing.

``confidence`` is confidence in the data and in its coherence. It is not, and
is never shown as, a probability that the price goes up.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from ..future_events.models import DecisionHorizon
from .decision_config import (
    CRITICAL_FAMILIES,
    DERIVATIVES,
    FAMILIES,
    FAMILY_EMOJI,
    FAMILY_LABEL,
    HORIZON_WEIGHTS,
    LIQUIDITY,
    ONCHAIN,
    TECHNICAL,
    THRESHOLDS,
    DecisionThresholds,
)
from .decision_families import STATE_LABEL_FR, DataStatus, FamilyScore, FamilyState
from .factor_semantics import fr_number


class GateStatus(StrEnum):
    PASS = "PASS"
    BLOCK = "BLOCK"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class FinalAction(StrEnum):
    BUY = "BUY"
    WAIT = "WAIT"
    SELL = "SELL"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


@dataclass(slots=True)
class GateResult:
    name: str
    label: str
    status: GateStatus
    action_if_blocked: FinalAction
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "status": self.status.value,
            "action_if_blocked": self.action_if_blocked.value,
            "detail": self.detail,
        }


@dataclass(slots=True)
class EventCandidate:
    """One upcoming event and how much it can overturn a call made now."""

    title: str
    delay: str
    hours: float
    score: float
    reasons: str


def event_candidates(
    events: list[Any], asset: Any, horizon: DecisionHorizon, now: datetime
) -> list[EventCandidate]:
    """Grade each scheduled event instead of blocking on its mere presence.

    importance x proximity x magnitude x uncertainty x exposure of the asset.
    A Fed meeting in 36 hours scores near the top; the same meeting three weeks
    out barely registers - it still sits in a 30-day window, but a decision
    taken today will have other readings to lean on before it lands.
    """

    from datetime import timedelta as _td

    from .event_relevance import AssetImpact, asset_impact

    span = {DecisionHorizon.H24: _td(days=1), DecisionHorizon.D7: _td(days=7),
            DecisionHorizon.D30: _td(days=30)}[horizon]
    importance = {"CRITICAL": 1.0, "HIGH": 0.7, "MEDIUM": 0.35, "LOW": 0.1}
    magnitude = {"EXTREME": 1.0, "HIGH": 0.85, "NORMAL": 0.6, "LOW": 0.4}
    exposure = {AssetImpact.NONE: 0.0, AssetImpact.LOW: 0.4, AssetImpact.MEDIUM: 0.7,
                AssetImpact.HIGH: 0.9, AssetImpact.VERY_HIGH: 1.0}
    out: list[EventCandidate] = []
    for event in events:
        when = getattr(event, "scheduled_at", None)
        if when is None:
            continue
        hours = (when - now).total_seconds() / 3600
        if hours < 0 or hours > span.total_seconds() / 3600:
            continue
        proximity = 1.0 if hours <= 48 else 0.6 if hours <= 24 * 7 else 0.35 if hours <= 24 * 14 else 0.15
        probabilities = getattr(event, "market_probabilities", None) or []
        top = max((p.probability for p in probabilities), default=None)
        uncertainty = 1.0 if top is None else 1.0 - 0.6 * top
        imp = importance.get(str(getattr(getattr(event, "importance", ""), "value", "")), 0.35)
        mag = magnitude.get(str(getattr(getattr(event, "magnitude_effect", ""), "value", "")), 0.6)
        exp_ = exposure.get(asset_impact(event, asset), 0.7)
        score = imp * proximity * mag * uncertainty * exp_
        delay = f"dans {hours:.0f} h" if hours < 48 else f"dans {hours / 24:.0f} j"
        from .decision_hierarchy import _event_profile

        try:
            profile = _event_profile(event)
            title = f"{profile.emoji} {profile.name}"
        except Exception:  # an unusual event still gets graded, under its own title
            title = str(getattr(event, "title", ""))
        out.append(EventCandidate(
            title=title,
            delay=delay,
            hours=hours,
            score=score,
            reasons=(
                f"importance {imp:.2f} × proximité {proximity:.2f} × amplitude {mag:.2f} × "
                f"incertitude {uncertainty:.2f} × exposition {exp_:.2f}"
            ),
        ))
    return sorted(out, key=lambda c: c.score, reverse=True)


@dataclass(slots=True)
class ExternalChecks:
    """What the existing engine already knows, fed into the gates unchanged."""

    #: Graded upcoming events; when given, they decide the event gate.
    event_candidates: list[EventCandidate] | None = None
    event_gate_active: bool = False
    event_title: str = ""
    event_delay: str = ""
    data_quality_blocks: bool = False
    missing_critical_inputs: list[str] = field(default_factory=list)
    #: The consistency validator's findings (NO_MEASURABLE_EDGE, ...).
    consistency_codes: list[str] = field(default_factory=list)
    #: The moment of the reading, for recency-based display priorities.
    as_of: datetime | None = None


@dataclass(slots=True)
class HomeFactor:
    family: str
    emoji: str
    label: str
    status: str
    tone: str  # GREEN | ORANGE | RED | YELLOW | WHITE
    value: str = ""
    contribution: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "emoji": self.emoji,
            "label": self.label,
            "status": self.status,
            "tone": self.tone,
            "value": self.value,
            "contribution": round(self.contribution, 2),
        }


@dataclass(slots=True)
class HorizonDecision:
    horizon: str
    action: FinalAction
    score: float | None
    confidence: int
    data_quality: int
    newest_data: datetime | None
    oldest_critical_data: datetime | None
    weights: dict[str, float]
    families: dict[str, FamilyScore]
    gates: list[GateResult]
    blocking_gate: str | None
    confirming_families: list[str]
    headline: str
    subtitle: str
    reasons: list[str]
    to_buy: list[str]
    to_worsen: list[str]
    home_factors: list[HomeFactor]
    thresholds: dict[str, Any]
    #: Trend / entry quality / risk, three reasons, per-family home lines.
    summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "horizon": self.horizon,
            "action": self.action.value,
            "score": None if self.score is None else round(self.score, 1),
            "confidence": self.confidence,
            "confidence_meaning": (
                "Confiance dans les données et leur cohérence - ce n'est pas une "
                "probabilité de hausse ou de baisse."
            ),
            "data_quality": self.data_quality,
            "newest_data": self.newest_data.isoformat() if self.newest_data else None,
            "oldest_critical_data": (
                self.oldest_critical_data.isoformat() if self.oldest_critical_data else None
            ),
            "weights": {k: round(v, 3) for k, v in self.weights.items()},
            "families": {k: v.to_dict() for k, v in self.families.items()},
            "gates": [g.to_dict() for g in self.gates],
            "blocking_gate": self.blocking_gate,
            "confirming_families": self.confirming_families,
            "headline": self.headline,
            "subtitle": self.subtitle,
            "reasons": self.reasons,
            "to_buy": self.to_buy,
            "to_worsen": self.to_worsen,
            "home_factors": [f.to_dict() for f in self.home_factors],
            "thresholds": self.thresholds,
            "summary": self.summary,
            "disclaimer": (
                "Signal analytique interne à l'application, jamais un ordre "
                "d'exécution."
            ),
        }


def _sign(value: float | None) -> int:
    if value is None:
        return 0
    return 1 if value > 0 else -1 if value < 0 else 0


def aggregate(
    families: dict[str, FamilyScore], horizon: DecisionHorizon
) -> tuple[float | None, int, int, dict[str, float]]:
    """Score, confidence and data quality, weights renormalised on what exists."""

    base = HORIZON_WEIGHTS[horizon]
    usable = {k: f for k, f in families.items() if f.usable}
    total_all = sum(base[k] for k in FAMILIES)
    total_usable = sum(base[k] for k in usable)
    if not usable or total_usable == 0:
        quality = round(sum(base[k] * families[k].data_quality for k in FAMILIES) / total_all)
        return None, 0, quality, {}
    weights = {k: base[k] / total_usable for k in usable}
    score = sum(weights[k] * (usable[k].score or 0) for k in usable)
    mean_conf = sum(weights[k] * usable[k].confidence for k in usable)
    coverage = total_usable / total_all
    # Families scattered across the scale lower confidence in the reading.
    variance = sum(weights[k] * ((usable[k].score or 0) - score) ** 2 for k in usable)
    disagreement = min(1.0, (variance ** 0.5) / 100)
    confidence = round(mean_conf * (0.6 + 0.4 * coverage) * (1 - 0.5 * disagreement))
    quality = round(
        sum(base[k] * (families[k].data_quality if k in families else 0) for k in FAMILIES)
        / total_all
    )
    return score, max(0, min(100, confidence)), quality, weights


def decide(
    families: dict[str, FamilyScore],
    horizon: DecisionHorizon,
    external: ExternalChecks | None = None,
    thresholds: DecisionThresholds = THRESHOLDS,
) -> HorizonDecision:
    external = external or ExternalChecks()
    score, confidence, quality, weights = aggregate(families, horizon)
    critical = CRITICAL_FAMILIES[horizon]
    usable = [k for k, f in families.items() if f.usable]
    gates: list[GateResult] = []

    # 1. Data quality
    missing_critical = [
        k for k in critical
        if families[k].status in {DataStatus.UNAVAILABLE, DataStatus.INSUFFICIENT_DATA}
    ]
    if external.data_quality_blocks or missing_critical or len(usable) < thresholds.min_available_families:
        what = [FAMILY_LABEL[k] for k in missing_critical] or external.missing_critical_inputs
        detail = (
            f"Famille{'s' if len(what) > 1 else ''} critique{'s' if len(what) > 1 else ''} "
            f"indisponible{'s' if len(what) > 1 else ''} : {', '.join(what)}."
            if what
            else f"Seulement {len(usable)} famille(s) exploitable(s) sur {len(FAMILIES)}."
        )
        gates.append(GateResult("DATA_QUALITY", "Qualité des données", GateStatus.BLOCK,
                                FinalAction.INSUFFICIENT_DATA, detail))
    else:
        gates.append(GateResult("DATA_QUALITY", "Qualité des données", GateStatus.PASS,
                                FinalAction.INSUFFICIENT_DATA,
                                f"{len(usable)} familles exploitables, familles critiques présentes."))

    # 2. Freshness
    stale_critical = [k for k in critical if families[k].status is DataStatus.STALE]
    if stale_critical:
        gates.append(GateResult(
            "FRESHNESS", "Fraîcheur", GateStatus.BLOCK, FinalAction.WAIT,
            "Données critiques périmées : " + ", ".join(FAMILY_LABEL[k] for k in stale_critical) + ".",
        ))
    else:
        gates.append(GateResult("FRESHNESS", "Fraîcheur", GateStatus.PASS, FinalAction.WAIT,
                                "Les familles critiques sont à jour."))

    # 3. Event risk - graded, never "an event in the window = WAIT" blindly
    top_event = (external.event_candidates or [None])[0] if external.event_candidates else None
    if external.event_candidates is not None:
        blocked = top_event is not None and (
            top_event.score >= thresholds.event_block_score
            or (
                top_event.score >= thresholds.event_caution_score
                and confidence < thresholds.event_caution_confidence
            )
        )
        if blocked and top_event is not None:
            external.event_title = top_event.title
            external.event_delay = top_event.delay
            why = (
                "trop proche et trop incertain pour s'engager"
                if top_event.score >= thresholds.event_block_score
                else f"les autres signaux (confiance {confidence} %) ne suffisent pas à le traverser"
            )
            gates.append(GateResult(
                "EVENT_RISK", "Risque événementiel", GateStatus.BLOCK, FinalAction.WAIT,
                f"{top_event.title} {top_event.delay} : {why}.",
            ))
        else:
            gates.append(GateResult(
                "EVENT_RISK", "Risque événementiel", GateStatus.PASS, FinalAction.WAIT,
                f"À surveiller : {top_event.title} {top_event.delay} (risque "
                f"{fr_number(top_event.score, 2)}, sous le seuil de blocage)."
                if top_event is not None else "Aucun événement majeur dans l'horizon.",
            ))
    elif external.event_gate_active:
        gates.append(GateResult(
            "EVENT_RISK", "Risque événementiel", GateStatus.BLOCK, FinalAction.WAIT,
            f"{external.event_title or 'Événement majeur'} {external.event_delay} : issue "
            "inconnue et non valorisée, trop proche pour s'engager.".strip(),
        ))
    else:
        gates.append(GateResult("EVENT_RISK", "Risque événementiel", GateStatus.PASS,
                                FinalAction.WAIT, "Aucun événement majeur non résolu dans l'horizon."))

    # 4. Uncertainty - including the existing no-measurable-edge finding
    no_edge = "NO_MEASURABLE_EDGE" in external.consistency_codes
    if score is not None and confidence < thresholds.uncertainty_confidence:
        gates.append(GateResult(
            "UNCERTAINTY", "Incertitude", GateStatus.BLOCK, FinalAction.WAIT,
            f"Confiance {confidence} % : sous le minimum de "
            f"{fr_number(thresholds.uncertainty_confidence, 0)} %.",
        ))
    elif no_edge:
        gates.append(GateResult(
            "UNCERTAINTY", "Incertitude", GateStatus.BLOCK, FinalAction.WAIT,
            "Aucun des signaux testés n'a montré d'avantage mesurable sur l'historique "
            "(tests statistiques corrigés) : la lecture n'est pas encore exploitable.",
        ))
    else:
        gates.append(GateResult("UNCERTAINTY", "Incertitude", GateStatus.PASS, FinalAction.WAIT,
                                f"Confiance {confidence} %."))

    # 5. Contradiction
    strong_pos = [k for k in usable if (families[k].score or 0) >= thresholds.contradiction_family_score]
    strong_neg = [k for k in usable if (families[k].score or 0) <= -thresholds.contradiction_family_score]
    share_pos = sum(weights.get(k, 0) for k in strong_pos)
    share_neg = sum(weights.get(k, 0) for k in strong_neg)
    if share_pos >= thresholds.contradiction_weight_share and share_neg >= thresholds.contradiction_weight_share:
        gates.append(GateResult(
            "CONTRADICTION", "Contradictions", GateStatus.BLOCK, FinalAction.WAIT,
            f"{', '.join(FAMILY_LABEL[k] for k in strong_pos)} favorable"
            f"{'s' if len(strong_pos) > 1 else ''} contre "
            f"{', '.join(FAMILY_LABEL[k] for k in strong_neg)} défavorable"
            f"{'s' if len(strong_neg) > 1 else ''}.",
        ))
    else:
        gates.append(GateResult("CONTRADICTION", "Contradictions", GateStatus.PASS,
                                FinalAction.WAIT, "Pas d'opposition forte entre familles."))

    # 6. Crowding / extreme risk
    derivatives = families.get(DERIVATIVES)
    crowding = (derivatives.extra.get("crowding") if derivatives else None) or "UNKNOWN"
    dvol_pct = derivatives.extra.get("dvol_percentile") if derivatives else None
    direction = _sign(score)
    crowding_block = None
    if direction > 0 and crowding == "CROWDED_LONGS":
        crowding_block = (
            "Les longs sont encombrés : entrer à l'achat maintenant, c'est rejoindre "
            "une foule qui paie cher son levier."
        )
    elif direction < 0 and crowding == "CROWDED_SHORTS":
        crowding_block = (
            "Les shorts sont encombrés : vendre maintenant expose à un rachat forcé brutal."
        )
    elif dvol_pct is not None and dvol_pct >= thresholds.extreme_dvol_percentile:
        crowding_block = (
            f"Volatilité implicite au {fr_number(dvol_pct, 0)}e percentile : régime de "
            "risque extrême."
        )
    gates.append(GateResult(
        "CROWDING", "Levier & risque extrême",
        GateStatus.BLOCK if crowding_block else GateStatus.PASS, FinalAction.WAIT,
        crowding_block or "Pas d'excès de levier contre le mouvement.",
    ))

    # 7. Final decision
    confirming = [
        k for k in usable
        if direction != 0
        and _sign(families[k].score) == direction
        and abs(families[k].score or 0) >= thresholds.confirming_family_score
    ]
    final = FinalAction.WAIT
    final_detail = ""
    if score is not None:
        meets = confidence >= thresholds.min_confidence and len(confirming) >= thresholds.min_confirming_families
        if score >= thresholds.buy_score and meets:
            final = FinalAction.BUY
        elif score <= thresholds.sell_score and meets:
            final = FinalAction.SELL
        else:
            missing = []
            if abs(score) < thresholds.buy_score:
                missing.append(f"score {fr_number(score, 0, signed=True)} (seuil ±{fr_number(thresholds.buy_score, 0)})")
            if confidence < thresholds.min_confidence:
                missing.append(f"confiance {confidence} % (minimum {fr_number(thresholds.min_confidence, 0)} %)")
            if len(confirming) < thresholds.min_confirming_families:
                missing.append(
                    f"{len(confirming)} famille{'s' if len(confirming) > 1 else ''} concordante"
                    f"{'s' if len(confirming) > 1 else ''} sur {thresholds.min_confirming_families} requises"
                )
            final_detail = "Conditions non réunies : " + ", ".join(missing) + "."
    gates.append(GateResult(
        "FINAL", "Décision", GateStatus.PASS if final is not FinalAction.WAIT else GateStatus.BLOCK,
        final, final_detail or f"{len(confirming)} familles indépendantes concordantes.",
    ))

    blocking = next((g for g in gates[:-1] if g.status is GateStatus.BLOCK), None)
    action = blocking.action_if_blocked if blocking else final

    decision = HorizonDecision(
        horizon=horizon.value,
        action=action,
        score=score,
        confidence=confidence,
        data_quality=quality,
        newest_data=max((f.newest for f in families.values() if f.newest), default=None),
        oldest_critical_data=min(
            (families[k].oldest for k in critical if families[k].oldest), default=None
        ),
        weights=weights,
        families=families,
        gates=gates,
        blocking_gate=blocking.name if blocking else (None if action is not FinalAction.WAIT else "FINAL"),
        confirming_families=confirming,
        headline="",
        subtitle="",
        reasons=[],
        to_buy=[],
        to_worsen=[],
        home_factors=[],
        thresholds={
            "buy_score": thresholds.buy_score,
            "sell_score": thresholds.sell_score,
            "min_confidence": thresholds.min_confidence,
            "min_confirming_families": thresholds.min_confirming_families,
            "status": "Valeurs initiales configurables, à valider par backtest.",
        },
    )
    _explain(decision, external, blocking)
    from .decision_presentation import summarize

    top_event = (external.event_candidates or [None])[0]
    decision.summary = summarize(
        decision, as_of=external.as_of or decision.newest_data, top_event=top_event
    )
    return decision


# ---------------------------------------------------------------------------
# Explanation
# ---------------------------------------------------------------------------

_SUBTITLE = {
    "DATA_QUALITY": "Données insuffisantes",
    "FRESHNESS": "Données critiques périmées",
    "EVENT_RISK": "Événement majeur imminent",
    "UNCERTAINTY": "Lecture encore incertaine",
    "CONTRADICTION": "Signaux contradictoires",
    "CROWDING": "Risque de levier élevé",
    "FINAL": "Pas de configuration claire",
}


def _contribution(decision: HorizonDecision, family: str) -> float:
    f = decision.families[family]
    return decision.weights.get(family, 0.0) * (f.score or 0.0)


def _tone(family: FamilyScore) -> str:
    if not family.usable:
        return "WHITE"
    return {
        FamilyState.VERY_POSITIVE: "GREEN",
        FamilyState.POSITIVE: "GREEN",
        FamilyState.SLIGHTLY_POSITIVE: "GREEN",
        FamilyState.NEUTRAL: "YELLOW",
        FamilyState.MIXED: "YELLOW",
        FamilyState.SLIGHTLY_NEGATIVE: "ORANGE",
        FamilyState.NEGATIVE: "RED",
        FamilyState.VERY_NEGATIVE: "RED",
    }.get(family.state, "WHITE")


def _home_label(family: FamilyScore) -> tuple[str, str, str]:
    """(label, status word, value) for one family on the home."""

    active = [c for c in family.components if c.active]
    lead = max(active, key=lambda c: abs((c.signal or 0) * c.weight), default=None)
    label = lead.label if lead else FAMILY_LABEL[family.family]
    status = STATE_LABEL_FR[family.state]
    if family.family == LIQUIDITY and family.extra.get("regime_label"):
        label = "Liquidité"
        status = family.extra["regime_label"]
    if family.family == TECHNICAL:
        label = "Structure de prix"
    if family.family == DERIVATIVES:
        label = "Dérivés"
        if family.state in {FamilyState.NEGATIVE, FamilyState.VERY_NEGATIVE}:
            status = "Risque élevé"
    value = ""
    if lead and family.family != LIQUIDITY:
        # Liquidity is shown by its regime: one component's figure (the TGA
        # balance, say) would read as the level of liquidity itself.
        metric = next((m for m in family.metrics if m.key in lead.metrics and m.usable), None)
        if metric:
            short = {
                "oi.value_history": "OI",
                "oi.contracts_bybit": "OI",
                "funding.rate": "Funding",
            }.get(metric.key)
            value = f"{short} {metric.display_value}" if short else metric.display_value
    return label, status, value


def _explain(decision: HorizonDecision, external: ExternalChecks, blocking: GateResult | None) -> None:
    families = decision.families
    usable = [k for k, f in families.items() if f.usable]
    ranked = sorted(usable, key=lambda k: abs(_contribution(decision, k)), reverse=True)

    if decision.action is FinalAction.BUY:
        decision.headline = "Plusieurs familles indépendantes confirment une configuration favorable."
        decision.subtitle = "Configuration favorable confirmée"
    elif decision.action is FinalAction.SELL:
        decision.headline = "Plusieurs familles indépendantes confirment une dégradation nette."
        decision.subtitle = "Risque nettement dégradé"
    elif decision.action is FinalAction.INSUFFICIENT_DATA:
        decision.headline = blocking.detail if blocking else "Données insuffisantes pour conclure."
        decision.subtitle = "Données insuffisantes"
    else:
        gate = blocking or next(g for g in decision.gates if g.name == "FINAL")
        decision.subtitle = _SUBTITLE.get(gate.name, "Pas de configuration claire")
        decision.headline = gate.detail

    # Why: one line per family, strongest contribution first, each with a figure.
    reasons: list[str] = []
    for key in ranked:
        family = families[key]
        line = next((c.sentence for c in sorted(
            (c for c in family.components if c.active),
            key=lambda c: abs((c.signal or 0) * c.weight), reverse=True,
        )), "")
        if line:
            reasons.append(line)
    if families.get(ONCHAIN) and not families[ONCHAIN].usable:
        reasons.append("🐋 On-chain : aucune source robuste branchée, famille exclue du calcul.")
    decision.reasons = reasons[:6]

    # What would move it to BUY: the blocking gate first, then the weakest links.
    to_buy: list[str] = []
    if decision.action is not FinalAction.BUY:
        if blocking is not None and blocking.name == "EVENT_RISK":
            to_buy.append(
                f"Le passage de {external.event_title or 'l’événement'} sans surprise défavorable."
            )
        if blocking is not None and blocking.name == "UNCERTAINTY" and "NO_MEASURABLE_EDGE" in external.consistency_codes:
            to_buy.append("Un signal dont l'avantage se confirme sur l'historique.")
        if blocking is not None and blocking.name == "CROWDING":
            to_buy.append("Un open interest qui se normalise sans cassure du prix.")
        negatives = sorted(
            (k for k in usable if (families[k].score or 0) < 15),
            key=lambda k: _contribution(decision, k),
        )
        for key in negatives:
            for component in sorted(
                (c for c in families[key].components if c.active and (c.signal or 0) < 0),
                key=lambda c: (c.signal or 0) * c.weight,
            ):
                if component.turn_condition and component.turn_condition not in to_buy:
                    to_buy.append(component.turn_condition)
                    break
    decision.to_buy = to_buy[:3]

    # What would degrade it further: invalidations of what currently helps.
    to_worsen: list[str] = []
    derivatives = families.get(DERIVATIVES)
    if derivatives and derivatives.extra.get("crowding") == "CROWDED_LONGS":
        to_worsen.append("Une cascade de liquidations si le prix casse avec des longs encombrés.")
    positives = sorted(
        (k for k in usable if (families[k].score or 0) > 0),
        key=lambda k: -_contribution(decision, k),
    )
    for key in positives:
        for condition in families[key].invalidation_conditions:
            if condition and condition not in to_worsen:
                to_worsen.append(condition)
                break
    decision.to_worsen = to_worsen[:3]

    # Home: the families that actually move the decision, not always the same.
    factors: list[HomeFactor] = []
    for key in ranked[:4]:
        family = families[key]
        label, status, value = _home_label(family)
        factors.append(HomeFactor(
            family=key, emoji=FAMILY_EMOJI[key], label=label, status=status,
            tone=_tone(family), value=value, contribution=_contribution(decision, key),
        ))
    decision.home_factors = factors

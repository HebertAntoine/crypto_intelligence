"""Six families of evidence, each scored from several measures, never from one.

Every family reads the market through a ``PointInTimeView`` - so the live call
and the backtest run exactly this code - and returns:

* a score from -100 to +100, built from components that each contribute a
  signal in [-1, 1] and a weight;
* a state, a confidence and a data-quality figure;
* the metrics behind it, each with its value, change, date, source and
  freshness - and an explanation of why it matters.

What is absent stays absent. A component with no usable data contributes no
signal and no weight: it lowers the family's coverage, which lowers its
confidence. A family with too little coverage says INSUFFICIENT_DATA rather
than lending the decision a neutral stance it has not measured.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from itertools import pairwise
from typing import Any

import pandas as pd

from ..core.enums import Asset, Timeframe
from ..future_events.models import DecisionHorizon
from .decision_config import (
    CYCLE,
    DERIVATIVES,
    FAMILY_EMOJI,
    FAMILY_LABEL,
    FLOWS,
    HORIZON_WINDOW,
    LIQUIDITY,
    MACRO,
    METRICS,
    ONCHAIN,
    PROVENANCE,
    SCALES,
    TECHNICAL,
    MetricSpec,
)
from .factor_semantics import fr_number
from .pit_view import Point, PointInTimeView


class DataStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class FamilyState(StrEnum):
    VERY_NEGATIVE = "VERY_NEGATIVE"
    NEGATIVE = "NEGATIVE"
    SLIGHTLY_NEGATIVE = "SLIGHTLY_NEGATIVE"
    NEUTRAL = "NEUTRAL"
    SLIGHTLY_POSITIVE = "SLIGHTLY_POSITIVE"
    POSITIVE = "POSITIVE"
    VERY_POSITIVE = "VERY_POSITIVE"
    MIXED = "MIXED"
    UNKNOWN = "UNKNOWN"


STATE_LABEL_FR = {
    FamilyState.VERY_NEGATIVE: "Très défavorable",
    FamilyState.NEGATIVE: "Défavorable",
    FamilyState.SLIGHTLY_NEGATIVE: "Plutôt défavorable",
    FamilyState.NEUTRAL: "Neutre",
    FamilyState.SLIGHTLY_POSITIVE: "Plutôt favorable",
    FamilyState.POSITIVE: "Favorable",
    FamilyState.VERY_POSITIVE: "Très favorable",
    FamilyState.MIXED: "Mitigé",
    FamilyState.UNKNOWN: "Indéterminé",
}


def _squash(value: float, scale: float) -> float:
    """Signal in [-1, 1]: one ``scale`` of move gives ~0.76, large moves saturate."""

    if scale <= 0:
        return 0.0
    return math.tanh(value / scale)


# ---------------------------------------------------------------------------
# Metric readings
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class MetricReading:
    key: str
    label: str
    emoji: str
    status: DataStatus
    unit: str = ""
    value: float | None = None
    display_value: str = "—"
    timestamp: datetime | None = None
    available_at: datetime | None = None
    source: str = ""
    source_tier: str = ""
    quality: int = 0
    confidence: int = 0
    previous_value: float | None = None
    delta: float | None = None
    delta_pct: float | None = None
    delta_label: str = ""
    #: FAVORABLE | UNFAVORABLE | NEUTRAL | CAUTION | CONTEXT | UNKNOWN.
    #: CAUTION is not "unfavourable": an overbought RSI inside an uptrend says
    #: the move is stretched, not that the trend is wrong.
    state: str = "UNKNOWN"
    why: str = ""
    note: str = ""
    #: 1 = can change the decision now, 2 = confirmation / context,
    #: 3 = technical detail. Recomputed each time: a fresh surprise climbs.
    priority: int = 2
    #: CRITICAL | HIGH | MEDIUM | LOW | HIDDEN - set by the presentation from
    #: what is happening now (a fresh surprise, a meeting in 48 h), not fixed.
    importance: str = "MEDIUM"
    #: The exact endpoint behind ``source``, when the collector recorded it.
    endpoint: str = ""
    #: What the value describes ("août 2026", "18/09") - never shown as the
    #: date it was updated.
    period_label: str = ""
    fetched_at: datetime | None = None
    #: The release time is an estimate (publication lag), not the calendar.
    publication_estimated: bool = False
    raw_value: str = ""

    @property
    def usable(self) -> bool:
        return self.status is DataStatus.AVAILABLE and self.value is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "emoji": self.emoji,
            "status": self.status.value,
            "unit": self.unit,
            "value": self.value,
            "display_value": self.display_value,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "available_at": self.available_at.isoformat() if self.available_at else None,
            "source": self.source,
            "source_tier": self.source_tier,
            "quality": self.quality,
            "confidence": self.confidence,
            "previous_value": self.previous_value,
            "delta": self.delta,
            "delta_pct": self.delta_pct,
            "delta_label": self.delta_label,
            "state": self.state,
            "why": self.why,
            "why_short": _first_sentence(self.why),
            "note": self.note,
            "priority": self.priority,
            "importance": self.importance,
            "endpoint": self.endpoint,
            # The currency a figure is in, so no screen can mix $ and €.
            "currency": "USD" if self.unit in {"$", "M$", "Md$"} else None,
            "freshness": self.status.value,
            "period_label": self.period_label,
            "published_at": self.available_at.isoformat() if self.available_at else None,
            "publication_estimated": self.publication_estimated,
            "fetched_at": self.fetched_at.isoformat() if self.fetched_at else None,
            "raw_value": self.raw_value,
        }


def _first_sentence(text: str) -> str:
    """The one line a card shows; the full explanation stays one tap away."""

    if not text:
        return ""
    cut = text.find(". ")
    return text if cut < 0 else text[: cut + 1]


_MONTHS_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
              "août", "septembre", "octobre", "novembre", "décembre"]


def unavailable(key: str, label: str, emoji: str, reason: str, why: str = "") -> MetricReading:
    return MetricReading(
        key=key, label=label, emoji=emoji, status=DataStatus.UNAVAILABLE,
        note=reason, why=why,
    )


def read_metric(
    view: PointInTimeView,
    metric: str,
    *,
    window: timedelta,
    asset: str | None = None,
    spec: MetricSpec | None = None,
    label: str | None = None,
    emoji: str | None = None,
    unit: str | None = None,
    max_age: timedelta | None = None,
    why: str | None = None,
    source_tier: str | None = None,
    transform=None,
    decimals: int = 2,
    delta_kind: str = "pct",
) -> MetricReading:
    """Latest known value, its change over ``window``, and whether it is current."""

    spec = spec or METRICS.get(metric)
    label = label or (spec.label if spec else metric)
    emoji = emoji or (spec.emoji if spec else "📊")
    unit = unit if unit is not None else (spec.unit if spec else "")
    max_age = max_age or (spec.max_age if spec else timedelta(days=2))
    why = why if why is not None else (spec.why if spec else "")
    tier = source_tier or (spec.source_tier if spec else "MARKET_DATA")
    transform = transform or (lambda v: v)

    latest = view.latest(metric, asset)
    if latest is None:
        return unavailable(metric, label, emoji, "Aucune donnée publiée pour cette mesure.", why)

    value = transform(latest.value)
    age = view.as_of - latest.available_at
    status = DataStatus.STALE if age > max_age else DataStatus.AVAILABLE
    previous: Point | None = view.value_before(metric, latest.timestamp - window, asset)
    reading = MetricReading(
        key=metric,
        label=label,
        emoji=emoji,
        status=status,
        unit=unit,
        value=value,
        display_value=_display(value, unit, decimals),
        timestamp=latest.timestamp,
        available_at=latest.available_at,
        source=latest.source,
        source_tier=tier,
        quality=100 if status is DataStatus.AVAILABLE else 40,
        confidence=90 if tier == "OFFICIAL" else 80,
        why=why,
    )
    fetched = (latest.meta or {}).get("fetched_at")
    if fetched:
        reading.fetched_at = datetime.fromisoformat(fetched)
    monthly = max_age >= timedelta(days=30)
    reading.period_label = (
        f"{_MONTHS_FR[latest.timestamp.month - 1]} {latest.timestamp.year}"
        if monthly else f"{latest.timestamp:%d/%m}"
    )
    # Official monthly releases carry a lag-based publication time.
    reading.publication_estimated = monthly and tier == "OFFICIAL"
    if status is DataStatus.STALE:
        reading.note = (
            f"Dernière valeur ({reading.period_label}) : trop ancienne pour être "
            "utilisée comme valeur actuelle."
        )
    if tier not in PROVENANCE.may_drive:
        # A social source can flag something to check; it never drives a score.
        reading.status = DataStatus.UNAVAILABLE
        reading.note = "Source sociale : signalée, jamais utilisée comme signal."
        return reading
    if previous is not None:
        prev_value = transform(previous.value)
        reading.previous_value = prev_value
        reading.delta = value - prev_value
        if prev_value not in (0, None):
            reading.delta_pct = (value - prev_value) / abs(prev_value) * 100
        reading.delta_label = _delta_label(reading, delta_kind, window)
    return reading


def _display(value: float, unit: str, decimals: int) -> str:
    if unit == "%":
        return f"{fr_number(value, decimals)} %"
    if unit == "pt":
        return f"{fr_number(value, decimals, signed=True)} pt"
    if unit == "Md$":
        return f"{fr_number(value, 0)} Md$"
    if unit == "$":
        return f"{fr_number(value, decimals)} $"
    if unit == "M$":
        return f"{fr_number(value, 0, signed=True)} M$"
    return fr_number(value, decimals)


def _window_label(window: timedelta) -> str:
    days = window.days
    return "24 h" if days <= 1 else f"{days} j"


def _delta_label(reading: MetricReading, kind: str, window: timedelta) -> str:
    span = _window_label(window)
    if reading.delta is None:
        return ""
    if kind == "bp":
        return f"{fr_number(reading.delta * 100, 0, signed=True)} pb sur {span}"
    if kind == "abs":
        return f"{fr_number(reading.delta, 1, signed=True)} sur {span}"
    if kind == "bn":
        return f"{fr_number(reading.delta, 0, signed=True)} Md$ sur {span}"
    if reading.delta_pct is None:
        return ""
    return f"{fr_number(reading.delta_pct, 1, signed=True)} % sur {span}"


# ---------------------------------------------------------------------------
# Components and families
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class Component:
    """One reasoned contribution: a signal in [-1, 1], weighted."""

    key: str
    label: str
    weight: float
    signal: float | None
    sentence: str
    #: What would reverse this component, stated with its current figure.
    turn_condition: str = ""
    metrics: list[str] = field(default_factory=list)

    @property
    def active(self) -> bool:
        return self.signal is not None and self.weight > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "weight": self.weight,
            "signal": None if self.signal is None else round(self.signal, 3),
            "sentence": self.sentence,
            "turn_condition": self.turn_condition,
            "metrics": self.metrics,
        }


@dataclass(slots=True)
class FamilyScore:
    family: str
    horizon: str
    status: DataStatus
    score: float | None = None
    state: FamilyState = FamilyState.UNKNOWN
    confidence: int = 0
    data_quality: int = 0
    freshness: str = "UNAVAILABLE"
    newest: datetime | None = None
    oldest: datetime | None = None
    components: list[Component] = field(default_factory=list)
    metrics: list[MetricReading] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    contradictions: list[str] = field(default_factory=list)
    invalidation_conditions: list[str] = field(default_factory=list)
    important_values: list[str] = field(default_factory=list)
    headline: str = ""
    extra: dict[str, Any] = field(default_factory=dict)
    unavailable_reason: str = ""

    @property
    def usable(self) -> bool:
        return self.status in {DataStatus.AVAILABLE, DataStatus.PARTIAL} and self.score is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "label": FAMILY_LABEL[self.family],
            "emoji": FAMILY_EMOJI[self.family],
            "horizon": self.horizon,
            "status": self.status.value,
            "score": None if self.score is None else round(self.score, 1),
            "state": self.state.value,
            "state_label": STATE_LABEL_FR[self.state],
            "confidence": self.confidence,
            "data_quality": self.data_quality,
            "freshness": self.freshness,
            "newest": self.newest.isoformat() if self.newest else None,
            "oldest": self.oldest.isoformat() if self.oldest else None,
            "components": [c.to_dict() for c in self.components],
            "metrics": [m.to_dict() for m in self.metrics],
            "reasons": self.reasons,
            "contradictions": self.contradictions,
            "invalidation_conditions": self.invalidation_conditions,
            "important_values": self.important_values,
            "headline": self.headline,
            "extra": self.extra,
            "unavailable_reason": self.unavailable_reason,
        }


def _state(score: float, components: list[Component]) -> FamilyState:
    active = [c for c in components if c.active]
    total = sum(c.weight for c in active) or 1.0
    pro = sum(c.weight for c in active if (c.signal or 0) >= 0.35) / total
    con = sum(c.weight for c in active if (c.signal or 0) <= -0.35) / total
    # Strong components pulling apart are a finding, not an average.
    if pro >= 0.3 and con >= 0.3:
        return FamilyState.MIXED
    if score >= 60:
        return FamilyState.VERY_POSITIVE
    if score >= 30:
        return FamilyState.POSITIVE
    if score >= 10:
        return FamilyState.SLIGHTLY_POSITIVE
    if score > -10:
        return FamilyState.NEUTRAL
    if score > -30:
        return FamilyState.SLIGHTLY_NEGATIVE
    if score > -60:
        return FamilyState.NEGATIVE
    return FamilyState.VERY_NEGATIVE


def finish_family(
    family: str,
    horizon: DecisionHorizon,
    components: list[Component],
    metrics: list[MetricReading],
    *,
    min_coverage: float = 0.4,
    headline_positive: str = "",
    headline_negative: str = "",
    headline_neutral: str = "",
) -> FamilyScore:
    """Turn components into a family score, honestly about what is missing."""

    defined = sum(c.weight for c in components) or 1.0
    active = [c for c in components if c.active]
    coverage = sum(c.weight for c in active) / defined
    # A measure that does not exist for this asset is not missing data.
    metrics_expected = [m for m in metrics if m.status is not DataStatus.NOT_APPLICABLE]
    usable_metrics = [m for m in metrics_expected if m.usable]
    stale = [m for m in metrics_expected if m.status is DataStatus.STALE]
    stamps = [m.timestamp for m in metrics if m.timestamp and m.usable]

    result = FamilyScore(
        family=family,
        horizon=horizon.value,
        status=DataStatus.AVAILABLE,
        components=components,
        metrics=metrics,
        newest=max(stamps) if stamps else None,
        oldest=min(stamps) if stamps else None,
    )
    result.data_quality = (
        round(100 * len(usable_metrics) / len(metrics_expected)) if metrics_expected else 0
    )
    result.freshness = (
        "UNAVAILABLE" if not usable_metrics else "STALE" if stale and not active else "FRESH"
    )

    if not active or coverage < min_coverage:
        result.status = DataStatus.STALE if stale and not usable_metrics else DataStatus.INSUFFICIENT_DATA
        result.state = FamilyState.UNKNOWN
        missing = [m.label for m in metrics if not m.usable]
        result.unavailable_reason = (
            "Mesures insuffisantes : " + ", ".join(missing[:4])
            if missing
            else "Aucune composante mesurable sur cet horizon."
        )
        result.headline = "Données insuffisantes pour conclure."
        return result

    if coverage < 0.999:
        result.status = DataStatus.PARTIAL
    score = 100 * sum(c.weight * (c.signal or 0) for c in active) / sum(c.weight for c in active)
    result.score = max(-100.0, min(100.0, score))
    result.state = _state(result.score, active)

    # Confidence in the data and its coherence - never a probability.
    signals = [c.signal or 0 for c in active]
    mean = sum(signals) / len(signals)
    dispersion = (
        math.sqrt(sum((s - mean) ** 2 for s in signals) / len(signals)) if len(signals) > 1 else 0.0
    )
    agreement = max(0.0, 1.0 - dispersion)
    quality = result.data_quality / 100
    result.confidence = round(100 * coverage * (0.5 + 0.5 * quality) * (0.6 + 0.4 * agreement))

    ranked = sorted(active, key=lambda c: abs((c.signal or 0) * c.weight), reverse=True)
    result.reasons = [c.sentence for c in ranked if c.sentence][:3]
    positive = [c for c in active if (c.signal or 0) >= 0.35]
    negative = [c for c in active if (c.signal or 0) <= -0.35]
    if positive and negative:
        result.contradictions = [
            f"{positive[0].label} va dans un sens, {negative[0].label} dans l'autre."
        ]
    result.invalidation_conditions = [c.turn_condition for c in ranked if c.turn_condition][:3]
    important = [m for m in metrics if m.usable]
    lead = {k for c in ranked[:3] for k in c.metrics}
    important.sort(key=lambda m: (m.key not in lead,))
    result.important_values = [m.key for m in important[:3]]
    if result.state in {FamilyState.POSITIVE, FamilyState.VERY_POSITIVE, FamilyState.SLIGHTLY_POSITIVE}:
        result.headline = headline_positive or (ranked[0].sentence if ranked else "")
    elif result.state in {FamilyState.NEGATIVE, FamilyState.VERY_NEGATIVE, FamilyState.SLIGHTLY_NEGATIVE}:
        result.headline = headline_negative or (ranked[0].sentence if ranked else "")
    elif result.state is FamilyState.MIXED:
        result.headline = "Des mesures fortes tirent dans des sens opposés."
    else:
        result.headline = headline_neutral or "Pas d'effet net sur cet horizon."
    return result


def _mark(reading: MetricReading, signal: float | None) -> None:
    if signal is None or not reading.usable:
        return
    reading.state = (
        "FAVORABLE" if signal >= 0.2 else "UNFAVORABLE" if signal <= -0.2 else "NEUTRAL"
    )


def _inflation_display(view: PointInTimeView, reading: MetricReading) -> None:
    """An index level (337,77) means nothing to a reader; its changes do.

    Shows the monthly and yearly changes; the raw index stays in the details.
    No consensus is shown: no source for it is connected, and none is invented.
    """

    if not reading.usable or reading.value is None or reading.timestamp is None:
        return
    previous = view.value_before(reading.key, reading.timestamp - timedelta(days=20))
    monthly = (
        (reading.value / previous.value - 1) * 100 if previous and previous.value else None
    )
    yearly = reading.delta_pct
    parts = []
    if monthly is not None:
        parts.append(f"{fr_number(monthly, 1, signed=True)} % m/m")
    if yearly is not None:
        parts.append(f"{fr_number(yearly, 1, signed=True)} % sur un an")
    if parts:
        reading.raw_value = f"indice {fr_number(reading.value, 2)}"
        reading.display_value = " · ".join(parts)
        reading.delta_label = ""
        reading.unit = "%"


# ---------------------------------------------------------------------------
# A. Macro & central banks
# ---------------------------------------------------------------------------


#: (key, flag, name, rate metric, decision metric, calendar source)
_CENTRAL_BANKS = (
    ("fed", "🇺🇸", "Fed", "cb.fed.target_upper", "cb.fed.target_upper", "Federal Reserve"),
    ("ecb", "🇪🇺", "BCE", "cb.ecb.deposit_rate", "cb.ecb.deposit_rate", "European Central Bank"),
    ("boj", "🇯🇵", "BoJ", "cb.boj.call_rate", "cb.boj.basic_loan_rate", "Bank of Japan"),
)


def central_banks(view: PointInTimeView) -> list[dict[str, Any]]:
    """Rate in force, last decision, next meeting - from each bank's own data.

    The rate the market expects at the next meeting needs a pricing source
    (fed funds futures, OIS). None is connected: the field says so and is
    never filled with a value the engine finds plausible.
    """

    out: list[dict[str, Any]] = []
    meetings = view.cache.meetings()
    for key, flag, name, rate_metric, decision_metric, calendar in _CENTRAL_BANKS:
        rate_points = view.points(rate_metric)
        if not rate_points:
            out.append({"key": key, "flag": flag, "name": name, "available": False})
            continue
        current = rate_points[-1]
        lower = view.latest("cb.fed.target_lower") if key == "fed" else None
        if key == "fed" and lower is not None:
            rate_text = f"{fr_number(lower.value, 2)} – {fr_number(current.value, 2)} %"
        elif key == "boj":
            rate_text = f"{fr_number(current.value, 2)} % (taux au jour le jour)"
        else:
            rate_text = f"{fr_number(current.value, 2)} %"

        decision_points = view.points(decision_metric)
        change = None
        for before, after in pairwise(decision_points):
            if abs(after.value - before.value) > 1e-9:
                change = (after.timestamp, (after.value - before.value) * 100)
        bank_meetings = [m for m in meetings if m[0] == calendar]
        past = [m for m in bank_meetings if m[1] <= view.as_of]
        upcoming = [m for m in bank_meetings if m[1] > view.as_of]
        last_meeting = past[-1][1] if past else None
        if change and (last_meeting is None or change[0] >= last_meeting - timedelta(days=1)):
            move = change[1]
            verb = "Hausse" if move > 0 else "Baisse"
            # The new rate applies from the day after the announcement: the
            # decision is dated to its meeting when one precedes the change.
            decided = (
                last_meeting
                if last_meeting is not None and timedelta(0) <= change[0] - last_meeting <= timedelta(days=7)
                else change[0]
            )
            last = {
                "date": decided.isoformat(),
                "label": f"{verb} de {fr_number(abs(move), 0)} pb",
                "change_bp": round(move),
            }
        elif last_meeting is not None:
            last = {"date": last_meeting.isoformat(), "label": "Maintien", "change_bp": 0}
        else:
            last = None
        next_meeting = upcoming[0][1] if upcoming else None
        days_to_next = (next_meeting - view.as_of).total_seconds() / 86400 if next_meeting else None
        days_since_last = (
            (view.as_of - datetime.fromisoformat(last["date"])).total_seconds() / 86400
            if last else None
        )
        # Importance follows the calendar: a meeting within 48 h or a decision
        # within 48 h is critical; the Fed weighs most the rest of the time.
        if (days_to_next is not None and days_to_next <= 2) or (
            days_since_last is not None and days_since_last <= 2 and last and last["change_bp"]
        ):
            importance = "CRITICAL"
        elif (days_to_next is not None and days_to_next <= 7) or (
            days_since_last is not None and days_since_last <= 7
        ):
            importance = "HIGH"
        else:
            importance = "MEDIUM" if key == "fed" else "LOW"
        out.append({
            "key": key, "flag": flag, "name": name, "available": True,
            "rate": current.value, "rate_label": rate_text,
            "rate_date": current.timestamp.isoformat(),
            "source": {"fed": "Réserve fédérale de New York", "ecb": "Banque centrale européenne",
                       "boj": "Banque du Japon"}[key],
            "last_decision": last,
            "next_meeting": next_meeting.isoformat() if next_meeting else None,
            "days_to_next": days_to_next,
            "expectation": None,
            "expectation_label": "Anticipation de marché indisponible",
            "importance": importance,
        })
    return out


def macro_family(view: PointInTimeView, asset: Asset, horizon: DecisionHorizon) -> FamilyScore:
    window = HORIZON_WINDOW[horizon]
    scale = SCALES[horizon]
    metrics: list[MetricReading] = []
    components: list[Component] = []

    def read(metric: str, **kwargs: Any) -> MetricReading:
        reading = read_metric(view, metric, window=window, **kwargs)
        metrics.append(reading)
        return reading

    real = read("macro.real10y", delta_kind="bp")
    us10 = read("macro.us10y", delta_kind="bp")
    us2 = read("macro.us2y", delta_kind="bp")
    read("macro.yield_curve_10y2y", delta_kind="bp")
    read("macro.fed_funds_rate", delta_kind="bp")
    dollar = read("macro.dxy")
    vix = read("macro.vix", delta_kind="abs")
    nasdaq = read("macro.nasdaq", decimals=0)
    read("macro.sp500", decimals=0)
    oil = read("macro.oil_wti", decimals=1)
    cpi = read_metric(view, "macro.core_cpi", window=timedelta(days=365))
    metrics.append(cpi)
    headline_cpi = read_metric(view, "macro.cpi", window=timedelta(days=365))
    metrics.append(headline_cpi)
    for reading in (cpi, headline_cpi):
        _inflation_display(view, reading)
    unemployment = read("macro.unemployment", delta_kind="abs")

    # Real yields: the cost of holding a non-yielding asset.
    if real.usable and real.delta is not None:
        signal = -_squash(real.delta * 100, scale.yield_bp)
        _mark(real, signal)
        rising = real.delta > 0
        components.append(Component(
            "real_yield", "Taux réels US", 1.0, signal,
            f"🏛️ Taux réel 10 ans à {real.display_value} ({real.delta_label}) : "
            + ("le coût d'opportunité de détenir une crypto augmente."
               if rising else "le coût d'opportunité de détenir une crypto recule."),
            turn_condition=(
                f"Un repli du taux réel 10 ans sous {real.display_value}."
                if rising else f"Une remontée du taux réel 10 ans au-dessus de {real.display_value}."
            ),
            metrics=[real.key],
        ))
    # Nominal 10 y: partly the same information as real yields, so it weighs less.
    if us10.usable and us10.delta is not None:
        signal = -_squash(us10.delta * 100, scale.yield_bp)
        _mark(us10, signal)
        components.append(Component(
            "nominal_yield", "Taux US 10 ans", 0.5, signal,
            f"🏛️ 10 ans à {us10.display_value} ({us10.delta_label}).",
            metrics=[us10.key],
        ))
    # 2 y: what the market expects the Fed to do next.
    if us2.usable and us2.delta is not None:
        signal = -_squash(us2.delta * 100, scale.yield_bp)
        _mark(us2, signal)
        components.append(Component(
            "policy_expectations", "Anticipations Fed (2 ans)", 0.5, signal,
            f"🇺🇸 2 ans à {us2.display_value} ({us2.delta_label}) : le marché "
            + ("anticipe une Fed plus restrictive." if us2.delta > 0 else "anticipe une Fed plus accommodante."),
            metrics=[us2.key],
        ))
    if dollar.usable and dollar.delta_pct is not None:
        signal = -_squash(dollar.delta_pct, scale.dollar_pct)
        _mark(dollar, signal)
        components.append(Component(
            "dollar", "Dollar", 0.8, signal,
            f"💵 Dollar {dollar.delta_label} : "
            + ("il resserre les conditions financières mondiales."
               if dollar.delta_pct > 0 else "il desserre les conditions financières mondiales."),
            turn_condition="Un retournement du dollar.",
            metrics=[dollar.key],
        ))
    if vix.usable and vix.delta is not None:
        signal = -_squash(vix.delta, scale.vix_points)
        _mark(vix, signal)
        components.append(Component(
            "equity_fear", "Peur sur les actions (VIX)", 0.6, signal,
            f"📉 VIX à {vix.display_value} ({vix.delta_label}) : "
            + ("la nervosité monte sur les marchés." if vix.delta > 0 else "la nervosité reflue."),
            metrics=[vix.key],
        ))
    if nasdaq.usable and nasdaq.delta_pct is not None:
        signal = _squash(nasdaq.delta_pct, scale.equity_pct)
        _mark(nasdaq, signal)
        components.append(Component(
            "risk_appetite", "Appétit pour le risque (Nasdaq)", 0.7, signal,
            f"📈 Nasdaq {nasdaq.delta_label} : l'appétit pour les actifs de croissance "
            + ("se renforce." if nasdaq.delta_pct > 0 else "s'affaiblit."),
            metrics=[nasdaq.key],
        ))
    # Oil only matters when the move is large enough to reach inflation and rates.
    if oil.usable and oil.delta_pct is not None:
        if abs(oil.delta_pct) >= scale.oil_shock_pct:
            signal = -_squash(oil.delta_pct, scale.oil_shock_pct * 1.5)
            _mark(oil, signal)
            up = oil.delta_pct > 0
            components.append(Component(
                "oil_shock", "Choc pétrolier", 0.5, signal,
                f"🛢️ Pétrole {oil.delta_label} : "
                + ("pression inflationniste possible, qui peut éloigner des baisses de taux et faire remonter les rendements."
                   if up else "la pression inflationniste s'allège, ce qui peut faciliter une détente des taux."),
                metrics=[oil.key],
            ))
        else:
            oil.state = "NEUTRAL"
            oil.note = "Mouvement trop faible pour modifier le scénario inflation / taux."
    # Core inflation trend - only on horizons where it can move a decision.
    if horizon is not DecisionHorizon.H24 and cpi.usable and cpi.delta_pct is not None:
        three = view.value_before("macro.core_cpi", cpi.timestamp - timedelta(days=89))
        if three is not None and three.value:
            annualised = ((cpi.value / three.value) ** 4 - 1) * 100
            yearly = cpi.delta_pct
            acceleration = annualised - yearly
            signal = -_squash(acceleration, 1.0)
            _mark(cpi, signal)
            cpi.delta_label = f"{fr_number(annualised, 1)} % annualisé sur 3 mois"
            components.append(Component(
                "core_inflation", "Inflation sous-jacente", 0.6 if horizon is DecisionHorizon.D30 else 0.3,
                signal,
                f"📈 Inflation sous-jacente {fr_number(yearly, 1)} % sur un an, "
                f"{fr_number(annualised, 1)} % annualisé sur 3 mois : "
                + ("elle réaccélère, ce qui retarde une détente monétaire."
                   if acceleration > 0 else "elle ralentit, ce qui laisse de la place à une détente monétaire."),
                metrics=[cpi.key],
            ))
    if unemployment.usable:
        unemployment.state = "NEUTRAL"
        unemployment.note = (
            "Effet ambigu : un chômage en hausse ralentit l'économie mais peut "
            "rapprocher des baisses de taux. Affiché, non noté."
        )

    # Central banks: rate in force, last decision, next meeting. Context and
    # event risk only - a hike or a cut is never mapped to a direction here.
    banks = central_banks(view)
    for bank in banks:
        if not bank.get("available"):
            continue
        reading = MetricReading(
            key=f"cb.{bank['key']}.rate", label=f"{bank['flag']} {bank['name']}", emoji=bank["flag"],
            status=DataStatus.AVAILABLE, unit="%", value=bank["rate"],
            display_value=bank["rate_label"],
            timestamp=datetime.fromisoformat(bank["rate_date"]), source=bank["source"],
            source_tier="OFFICIAL", quality=100, confidence=95, state="CONTEXT",
            why="Le taux directeur fixe le coût de l'argent ; ses décisions et leurs "
                "surprises déplacent tous les actifs risqués.",
        )
        if bank.get("last_decision"):
            decided = datetime.fromisoformat(bank["last_decision"]["date"])
            reading.delta_label = f"{bank['last_decision']['label']} le {decided:%d/%m}"
        metrics.append(reading)

    result = finish_family(
        MACRO, horizon, components, metrics,
        headline_positive="Conditions macro plutôt porteuses pour les actifs risqués.",
        headline_negative="Les conditions macro pèsent sur les actifs risqués.",
    )
    result.extra["central_banks"] = banks
    return result


# ---------------------------------------------------------------------------
# B. Liquidity
# ---------------------------------------------------------------------------


class LiquidityRegime(StrEnum):
    EXPANDING = "EXPANDING"
    MILDLY_EXPANDING = "MILDLY_EXPANDING"
    NEUTRAL = "NEUTRAL"
    MILDLY_CONTRACTING = "MILDLY_CONTRACTING"
    CONTRACTING = "CONTRACTING"
    UNCERTAIN = "UNCERTAIN"


LIQUIDITY_REGIME_FR = {
    LiquidityRegime.EXPANDING: "En expansion",
    LiquidityRegime.MILDLY_EXPANDING: "En légère expansion",
    LiquidityRegime.NEUTRAL: "Stable",
    LiquidityRegime.MILDLY_CONTRACTING: "En légère contraction",
    LiquidityRegime.CONTRACTING: "En contraction",
    LiquidityRegime.UNCERTAIN: "Incertaine",
}


def liquidity_family(view: PointInTimeView, asset: Asset, horizon: DecisionHorizon) -> FamilyScore:
    # Balance-sheet data is weekly and slow: below a week the change is noise.
    window = max(HORIZON_WINDOW[horizon], timedelta(days=7))
    scale = SCALES[horizon]
    metrics: list[MetricReading] = []
    components: list[Component] = []
    bn = lambda v: v / 1000  # noqa: E731 - millions -> billions

    fed = read_metric(view, "liquidity.fed_total_assets", window=window, transform=bn, delta_kind="bn")
    tga = read_metric(view, "liquidity.tga", window=window, transform=bn, delta_kind="bn")
    rrp = read_metric(view, "liquidity.rrp", window=window, transform=bn, delta_kind="bn")
    stable_window = timedelta(days=30) if horizon is DecisionHorizon.D30 else timedelta(days=7)
    stables = read_metric(
        view, "stablecoin.supply.total", window=stable_window, transform=lambda v: v / 1e9,
        unit="Md$",
    )
    metrics.extend([fed, tga, rrp, stables])

    fed_change = fed.delta
    if fed.usable and fed_change is None:
        # H.4.1 states its own week-on-week change: use it rather than nothing.
        latest = view.latest("liquidity.fed_total_assets")
        weekly = (latest.meta or {}).get("change_week_musd") if latest else None
        if weekly is not None:
            fed_change = float(weekly) / 1000
            fed.delta = fed_change
            fed.delta_label = f"{fr_number(fed_change, 0, signed=True)} Md$ sur la semaine"
    if fed.usable and fed_change is not None:
        signal = _squash(fed_change, scale.fed_assets_bn)
        _mark(fed, signal)
        components.append(Component(
            "fed_balance_sheet", "Bilan de la Fed", 1.0, signal,
            f"🏦 Bilan de la Fed {fed.delta_label} : "
            + ("il injecte des liquidités." if fed_change > 0 else "il en retire."),
            metrics=[fed.key],
        ))
    if tga.usable and tga.delta is not None:
        signal = -_squash(tga.delta, scale.tga_bn)
        _mark(tga, signal)
        components.append(Component(
            "treasury_account", "Compte du Trésor (TGA)", 0.8, signal,
            f"🏦 Compte du Trésor {tga.delta_label} : "
            + ("il retire des liquidités au système." if tga.delta > 0 else "il rend des liquidités au système."),
            metrics=[tga.key],
        ))
    if rrp.usable and rrp.delta is not None:
        signal = -_squash(rrp.delta, scale.rrp_bn)
        # Near zero the stock has nothing left to release.
        if rrp.value is not None and rrp.value < 50:
            signal *= 0.3
            rrp.note = "Stock déjà proche de zéro : ses variations comptent peu."
        _mark(rrp, signal)
        components.append(Component(
            "reverse_repo", "Reverse repo (RRP)", 0.5, signal,
            f"🏦 RRP à {rrp.display_value} ({rrp.delta_label}).",
            metrics=[rrp.key],
        ))
    if stables.usable and stables.delta_pct is not None:
        signal = _squash(stables.delta_pct, scale.stablecoin_pct)
        _mark(stables, signal)
        components.append(Component(
            "stablecoins", "Offre de stablecoins", 1.0, signal,
            f"💧 Stablecoins {stables.delta_label} : "
            + ("offre quasi stable." if abs(signal) < 0.15
               else "du cash crypto supplémentaire arrive sur les plateformes."
               if stables.delta_pct > 0 else "du cash crypto quitte les plateformes."),
            # What would turn this reading: a supply that grows would turn a
            # falling reading, and the reverse - never a fixed sentence.
            turn_condition=("Un recul durable de l'offre de stablecoins." if stables.delta_pct > 0
                            else "Une hausse durable de l'offre de stablecoins."),
            metrics=[stables.key],
        ))

    result = finish_family(
        LIQUIDITY, horizon, components, metrics,
        headline_positive="La liquidité disponible progresse.",
        headline_negative="La liquidité disponible se contracte.",
        headline_neutral="Liquidité globale stable.",
    )
    # The regime is read from how many components agree, never from one total
    # presented as a truth.
    active = [c for c in components if c.active]
    ups = sum(1 for c in active if (c.signal or 0) >= 0.3)
    downs = sum(1 for c in active if (c.signal or 0) <= -0.3)
    if not active or (ups and downs):
        regime = LiquidityRegime.UNCERTAIN
    elif ups >= 2:
        regime = LiquidityRegime.EXPANDING
    elif ups == 1:
        regime = LiquidityRegime.MILDLY_EXPANDING
    elif downs >= 2:
        regime = LiquidityRegime.CONTRACTING
    elif downs == 1:
        regime = LiquidityRegime.MILDLY_CONTRACTING
    else:
        regime = LiquidityRegime.NEUTRAL
    result.extra["regime"] = regime.value
    result.extra["regime_label"] = LIQUIDITY_REGIME_FR[regime]
    result.extra["regime_rule"] = (
        "Régime lu par l'accord des composantes (bilan Fed, TGA, RRP, stablecoins), "
        "affichées séparément ; aucune formule unique n'est présentée comme une vérité."
    )
    if fed.usable and tga.usable and rrp.usable:
        net = (fed.value or 0) - (tga.value or 0) - (rrp.value or 0)
        result.extra["net_liquidity_bn"] = round(net, 0)
        result.extra["net_liquidity_note"] = (
            "Indicateur interne (bilan Fed − TGA − RRP), usage descriptif uniquement."
        )
    return result


# ---------------------------------------------------------------------------
# C. ETF & spot flows
# ---------------------------------------------------------------------------


def _zscore(value: float, history: list[float]) -> float | None:
    if len(history) < 20:
        return None
    mean = sum(history) / len(history)
    variance = sum((h - mean) ** 2 for h in history) / (len(history) - 1)
    std = math.sqrt(variance)
    return None if std == 0 else (value - mean) / std


#: Window of aggressive-flow sums per horizon, and the step between the past
#: windows it is compared with.
_SPOT_WINDOW = {
    DecisionHorizon.H24: (timedelta(hours=24), timedelta(hours=6)),
    DecisionHorizon.D7: (timedelta(days=7), timedelta(days=1)),
    DecisionHorizon.D30: (timedelta(days=30), timedelta(days=2)),
}
SPOT_EXCHANGES = ("binance", "okx", "bybit")
_EXCHANGE_FR = {"binance": "Binance", "okx": "OKX", "bybit": "Bybit"}


def _hour_map(points: list[Point]) -> dict[datetime, float]:
    return {p.timestamp: p.value for p in points}


def spot_pressure(view: PointInTimeView, asset: Asset, horizon: DecisionHorizon) -> dict[str, Any] | None:
    """Aggressive buy / sell notional over the horizon, from hourly exchange data.

    An exchange counts only if it covers at least 90 % of the window's hours;
    Bybit's live stream counts an hour only when it was connected for 55
    minutes of it. Returns None when no exchange covers the window - the
    caller then falls back to the long daily history.
    """

    span, step = _SPOT_WINDOW[horizon]
    end = view.as_of.replace(minute=0, second=0, microsecond=0)
    hours = int(span.total_seconds() // 3600)
    wanted = [end - timedelta(hours=h + 1) for h in range(hours)]
    exchanges: dict[str, tuple[dict[datetime, float], dict[datetime, float]]] = {}
    coverage: dict[str, float] = {}
    for exchange in SPOT_EXCHANGES:
        buys = _hour_map(view.points(f"spot.flow.buy_usd.{exchange}", asset.value))
        sells = _hour_map(view.points(f"spot.flow.sell_usd.{exchange}", asset.value))
        if exchange == "bybit":
            minutes = _hour_map(view.points("stream.bybit_spot.minutes", asset.value))
            complete = {h for h, m in minutes.items() if m >= 55}
            buys = {h: v for h, v in buys.items() if h in complete}
            sells = {h: v for h, v in sells.items() if h in complete}
        covered = sum(1 for h in wanted if h in buys and h in sells)
        coverage[exchange] = covered / hours if hours else 0.0
        if coverage[exchange] >= 0.9:
            exchanges[exchange] = (buys, sells)
    if not exchanges:
        return {"coverage": coverage, "usable": False}

    def window(stop: datetime) -> tuple[float, float] | None:
        buy = sell = 0.0
        slots = [stop - timedelta(hours=h + 1) for h in range(hours)]
        for buys, sells in exchanges.values():
            present = [h for h in slots if h in buys and h in sells]
            if len(present) < 0.9 * hours:
                return None
            buy += sum(buys[h] for h in present)
            sell += sum(sells[h] for h in present)
        return (buy, sell) if buy + sell > 0 else None

    current = window(end)
    if current is None:
        return {"coverage": coverage, "usable": False}
    buy, sell = current
    share = buy / (buy + sell)
    previous = window(end - span)
    prev_share = previous[0] / sum(previous) if previous else None
    history: list[float] = []
    stop = end - step
    while len(history) < 200:
        past = window(stop)
        if past is None:
            break
        history.append(past[0] / sum(past))
        stop -= step
    return {
        "usable": True,
        "buy_usd": buy,
        "sell_usd": sell,
        "delta_usd": buy - sell,
        "share": share,
        "previous_share": prev_share,
        "history": history,
        "exchanges": sorted(exchanges),
        "coverage": coverage,
        "hours": hours,
    }


def _usd_compact(value: float) -> str:
    sign = "-" if value < 0 else ""
    value = abs(value)
    if value >= 1e9:
        return f"{sign}{fr_number(value / 1e9, 2)} Md$"
    if value >= 1e6:
        return f"{sign}{fr_number(value / 1e6, 0)} M$"
    return f"{sign}{fr_number(value / 1e3, 0)} k$"


def flows_family(view: PointInTimeView, asset: Asset, horizon: DecisionHorizon) -> FamilyScore:
    metrics: list[MetricReading] = []
    components: list[Component] = []
    sessions_for = {DecisionHorizon.H24: 1, DecisionHorizon.D7: 5, DecisionHorizon.D30: 20}
    n = sessions_for[horizon]

    flows = view.points("etf.net_flow", asset.value)
    etf_applicable = bool(flows) or asset in {Asset.BTC, Asset.ETH}
    if not flows:
        missing = unavailable(
            "etf.net_flow", "Flux ETF", "💸",
            "Aucun ETF au comptant vérifié pour cet actif : pas de score ETF, "
            "les autres composantes sont repondérées."
            if asset is Asset.SOL else "Aucune série de flux ETF disponible.",
        )
        if asset is Asset.SOL:
            missing.status = DataStatus.NOT_APPLICABLE
        metrics.append(missing)
    else:
        last = flows[-1]
        age = view.as_of - last.available_at
        stale = age > timedelta(days=4)  # weekends and holidays included
        values = [p.value for p in flows]
        window_sum = sum(values[-n:])
        # Each past window of the same length, for a scale that is the asset's own.
        history = [sum(values[i - n:i]) for i in range(n, len(values) - n + 1, max(1, n // 2))][-120:]
        z = _zscore(window_sum, history)
        streak = 0
        for value in reversed(values):
            if value == 0 or (streak and (value > 0) != (streak > 0)):
                break
            streak += 1 if value > 0 else -1
        five = sum(values[-5:])
        twenty = sum(values[-20:])
        acceleration = (five / 5) - (twenty / 20) if len(values) >= 20 else None
        label = f"Flux ETF {asset.value} ({n} séance{'s' if n > 1 else ''})"
        reading = MetricReading(
            key="etf.net_flow", label=label, emoji="💸",
            status=DataStatus.STALE if stale else DataStatus.AVAILABLE,
            unit="M$", value=window_sum,
            display_value=f"{fr_number(window_sum, 0, signed=True)} M$",
            timestamp=last.timestamp, available_at=last.available_at,
            source=last.source, source_tier="AGGREGATOR", quality=100 if not stale else 40,
            confidence=80,
            delta=acceleration, delta_label=(
                f"moyenne 5 séances {fr_number(five / 5, 0, signed=True)} M$ vs 20 séances "
                f"{fr_number(twenty / 20, 0, signed=True)} M$" if acceleration is not None else ""
            ),
            why=(
                "Les ETF au comptant achètent ou vendent réellement l'actif pour leurs "
                "clients : des entrées persistantes sont une demande nette, des sorties "
                "une offre nette."
            ),
        )
        metrics.append(reading)
        metrics.append(MetricReading(
            key="etf.streak", label="Série en cours", emoji="🔁", status=reading.status,
            value=float(streak), unit="",
            display_value=(
                f"{abs(streak)} séance{'s' if abs(streak) > 1 else ''} "
                + ("d'entrées" if streak > 0 else "de sorties" if streak < 0 else "")
            ).strip(),
            timestamp=last.timestamp, source=last.source, source_tier="AGGREGATOR",
            quality=reading.quality, confidence=80,
            why="Plusieurs séances dans le même sens pèsent plus qu'une séance isolée.",
        ))
        if not stale and z is not None:
            signal = _squash(z, 1.5)
            _mark(reading, signal)
            direction = (
                "quasi équilibré" if abs(signal) < 0.2
                else "entrées" if window_sum > 0 else "sorties"
            )
            components.append(Component(
                "etf", "Flux ETF", 1.0, signal,
                f"💸 ETF {asset.value} : {fr_number(window_sum, 0, signed=True)} M$ sur "
                f"{n} séance{'s' if n > 1 else ''} ({direction}"
                + (f", {abs(streak)} séances d'affilée" if abs(streak) >= 3 else "")
                + ").",
                turn_condition=(
                    "Plusieurs séances consécutives de sorties nettes des ETF."
                    if window_sum > 0 else "Un retour durable des entrées nettes dans les ETF."
                ),
                metrics=["etf.net_flow"],
            ))
        elif stale:
            reading.note = f"Dernière séance publiée le {last.timestamp:%d/%m} : trop ancienne."

    # Spot pressure: who takes the initiative - aggressive buyers or sellers.
    # Every trade has a buyer and a seller; the taker side is what is measured.
    pressure = spot_pressure(view, asset, horizon)
    window_fr = {DecisionHorizon.H24: "24 h", DecisionHorizon.D7: "7 j", DecisionHorizon.D30: "30 j"}[horizon]
    spot_extra: dict[str, Any] = {"coverage": (pressure or {}).get("coverage", {})}
    if pressure and pressure.get("usable"):
        share = pressure["share"]
        history = pressure["history"]
        z = _zscore(share, history) if len(history) >= 15 else None
        # Too little history for a z-score: distance from balance, where two
        # percentage points is a clear lean.
        signal = _squash(z, 1.5) if z is not None else _squash((share - 0.5) * 100, 2.0)
        names = ", ".join(_EXCHANGE_FR[e] for e in pressure["exchanges"])
        newest = max(
            (p.timestamp for e in pressure["exchanges"]
             for p in view.points(f"spot.flow.buy_usd.{e}", asset.value)[-1:]),
            default=None,
        )
        reading = MetricReading(
            key="spot.pressure", label=f"Pression acheteurs / vendeurs ({window_fr})", emoji="🪙",
            status=DataStatus.AVAILABLE, unit="%", value=share * 100,
            display_value=f"{fr_number(share * 100, 0)} % acheteurs",
            timestamp=newest, available_at=(newest + timedelta(hours=1)) if newest else None,
            source=names, source_tier="EXCHANGE", quality=100, confidence=85,
            endpoint="klines 1 h / taker-volume 1 h / publicTrade",
            delta_label=f"delta {_usd_compact(pressure['delta_usd'])}",
            why=(
                "Chaque transaction a un acheteur et un vendeur. On mesure qui prend "
                "l'initiative : l'acheteur qui accepte le prix demandé ou le vendeur "
                "qui accepte le prix offert."
            ),
        )
        reading.raw_value = (
            f"achats agressifs {_usd_compact(pressure['buy_usd'])} · ventes agressives "
            f"{_usd_compact(pressure['sell_usd'])}"
        )
        metrics.append(reading)
        _mark(reading, signal)
        trend = None
        if pressure["previous_share"] is not None:
            move = (share - pressure["previous_share"]) * 100
            trend = "UP" if move >= 1 else "DOWN" if move <= -1 else "FLAT"
        spot_extra.update({
            "source": "hourly",
            "buy_usd": pressure["buy_usd"],
            "sell_usd": pressure["sell_usd"],
            "delta_usd": pressure["delta_usd"],
            "share": share,
            "previous_share": pressure["previous_share"],
            "trend": trend,
            "exchanges": pressure["exchanges"],
            "window": window_fr,
        })
        components.append(Component(
            "spot", "Pression spot", 1.0, signal,
            f"🪙 Achats agressifs {fr_number(share * 100, 0)} % sur {window_fr} "
            f"({len(pressure['exchanges'])} plateforme{'s' if len(pressure['exchanges']) > 1 else ''}) : "
            f"{'les acheteurs' if share >= 0.5 else 'les vendeurs'} prennent "
            "plus souvent l'initiative.",
            turn_condition=(
                "Des ventes agressives qui repassent majoritaires."
                if share >= 0.5 else "Des achats agressifs qui redeviennent majoritaires."
            ),
            metrics=["spot.pressure"],
        ))
    else:
        # The long daily history (Binance, since 2017): the same question on a
        # coarser clock - and the only one a backtest can replay.
        ratio_points = view.points("spot.taker_buy_ratio", asset.value)
        days = {DecisionHorizon.H24: 1, DecisionHorizon.D7: 7, DecisionHorizon.D30: 30}[horizon]
        if len(ratio_points) >= days + 60:
            last = ratio_points[-1]
            stale = view.as_of - last.available_at > timedelta(days=2)
            recent = [p.value for p in ratio_points[-days:]]
            base = [p.value for p in ratio_points[-(days + 180):-days]]
            mean_recent = sum(recent) / len(recent)
            z = _zscore(mean_recent, base)
            reading = MetricReading(
                key="spot.pressure", label=f"Pression acheteurs / vendeurs ({window_fr})", emoji="🪙",
                status=DataStatus.STALE if stale else DataStatus.AVAILABLE, unit="%",
                value=mean_recent * 100, display_value=f"{fr_number(mean_recent * 100, 0)} % acheteurs",
                timestamp=last.timestamp, available_at=last.available_at, source=last.source,
                source_tier="EXCHANGE", quality=100 if not stale else 40, confidence=75,
                why=(
                    "Chaque transaction a un acheteur et un vendeur. On mesure qui prend "
                    "l'initiative, d'après l'historique quotidien d'une plateforme majeure."
                ),
            )
            metrics.append(reading)
            spot_extra.update({"source": "daily", "share": mean_recent, "window": window_fr,
                               "exchanges": ["binance"]})
            if not stale and z is not None:
                signal = _squash(z, 1.5)
                _mark(reading, signal)
                components.append(Component(
                    "spot", "Pression spot", 1.0, signal,
                    f"🪙 Achats agressifs à {reading.display_value} sur {window_fr} : "
                    + ("au-dessus" if signal > 0 else "en dessous") + " de leur normale.",
                    metrics=["spot.pressure"],
                ))
        else:
            metrics.append(unavailable(
                "spot.pressure", "Pression acheteurs / vendeurs", "🪙",
                "Aucune plateforme ne couvre la période et l'historique est insuffisant.",
            ))

    # ETF flows stay an internal sub-signal: real demand, but a daily file
    # published the next morning. They weigh less than the live spot tape.
    for component in components:
        if component.key == "etf":
            component.weight = 0.35

    result = finish_family(
        FLOWS, horizon, components, metrics,
        headline_positive="Les acheteurs prennent plus souvent l'initiative.",
        headline_negative="Les vendeurs prennent plus souvent l'initiative.",
        headline_neutral="Acheteurs et vendeurs s'équilibrent.",
    )
    result.extra["etf_applicable"] = etf_applicable and bool(flows)
    result.extra["spot"] = spot_extra
    return result


# ---------------------------------------------------------------------------
# D. Derivatives - crowding, never open interest alone
# ---------------------------------------------------------------------------


class CrowdingRegime(StrEnum):
    CROWDED_LONGS = "CROWDED_LONGS"
    NEW_LONGS = "NEW_LONGS"
    SHORT_COVERING = "SHORT_COVERING"
    NEW_SHORTS = "NEW_SHORTS"
    CROWDED_SHORTS = "CROWDED_SHORTS"
    DELEVERAGING = "DELEVERAGING"
    QUIET = "QUIET"
    UNKNOWN = "UNKNOWN"


CROWDING_FR = {
    CrowdingRegime.CROWDED_LONGS: ("Longs encombrés", "La hausse s'appuie sur de nouveaux longs qui paient leur levier plus que d'habitude : elle est plus fragile."),
    CrowdingRegime.NEW_LONGS: ("Nouveaux longs", "De nouvelles positions acheteuses accompagnent la hausse sans excès de coût."),
    CrowdingRegime.SHORT_COVERING: ("Rachat de shorts", "Le prix monte pendant que des positions se ferment : des vendeurs se couvrent, ce qui dure moins qu'une vraie demande."),
    CrowdingRegime.NEW_SHORTS: ("Nouveaux shorts", "De nouvelles positions vendeuses accompagnent la baisse : pression directionnelle."),
    CrowdingRegime.CROWDED_SHORTS: ("Shorts encombrés", "Les vendeurs paient pour rester à découvert : un rachat forcé peut provoquer un rebond brutal."),
    CrowdingRegime.DELEVERAGING: ("Désendettement", "Prix et positions baissent ensemble : le levier se purge."),
    CrowdingRegime.QUIET: ("Calme", "Ni le prix ni le levier ne bougent nettement."),
    CrowdingRegime.UNKNOWN: ("Indéterminé", "Données de levier insuffisantes."),
}


def _percentile(value: float, history: list[float]) -> float | None:
    """Mid-rank percentile: ties count half.

    Binance funding sits at its 0.01 % baseline much of the time. Counting
    every tie as "below" put that ordinary baseline at the 100th percentile and
    read it as longs paying dearly.
    """

    if len(history) < 60:
        return None
    below = sum(1 for h in history if h < value)
    equal = sum(1 for h in history if h == value)
    return 100 * (below + 0.5 * equal) / len(history)


def liquidation_totals(view: PointInTimeView, asset: Asset) -> dict[str, Any]:
    """Forced liquidations over 1 h, 4 h and 24 h, from the Bybit live feed.

    Only hours the stream covered for 55 minutes or more are summed, and the
    covered share is stated: a quiet feed and a disconnected one must never
    read the same. Liquidations measure the violence of a move, not its
    direction - they feed the risk reading, not the score.
    """

    a = asset.value
    longs = _hour_map(view.points("liq.long_usd.bybit", a))
    shorts = _hour_map(view.points("liq.short_usd.bybit", a))
    minutes = _hour_map(view.points("stream.bybit_liq.minutes", a))
    end = view.as_of.replace(minute=0, second=0, microsecond=0)
    out: dict[str, Any] = {}
    for label, hours in (("1h", 1), ("4h", 4), ("24h", 24)):
        slots = [end - timedelta(hours=h + 1) for h in range(hours)]
        complete = [h for h in slots if minutes.get(h, 0) >= 55]
        out[label] = {
            "long_usd": sum(longs.get(h, 0.0) for h in complete),
            "short_usd": sum(shorts.get(h, 0.0) for h in complete),
            "covered_hours": len(complete),
            "hours": hours,
        }
    day = out["24h"]
    total = day["long_usd"] + day["short_usd"]
    why = (
        "Des positions à levier fermées de force : elles amplifient le mouvement "
        "en cours. Elles disent sa violence, jamais sa direction à venir."
    )
    if day["covered_hours"] < 20:
        reading = MetricReading(
            key="liquidations", label="Liquidations 24 h", emoji="💥",
            status=DataStatus.INSUFFICIENT_DATA if day["covered_hours"] else DataStatus.UNAVAILABLE,
            why=why, source="Bybit (flux public en direct)", source_tier="EXCHANGE",
            display_value="—",
            note=(
                f"Flux en direct couvert sur {day['covered_hours']} h des dernières 24 h : "
                "total non publié tant que la couverture est incomplète."
            ),
        )
        dominance = "UNKNOWN"
    else:
        dominance = (
            "LONGS" if day["long_usd"] >= 1.5 * max(day["short_usd"], 1)
            else "SHORTS" if day["short_usd"] >= 1.5 * max(day["long_usd"], 1)
            else "BALANCED"
        )
        newest = max((h for h in longs if minutes.get(h, 0) >= 55), default=None)
        reading = MetricReading(
            key="liquidations", label="Liquidations 24 h", emoji="💥",
            status=DataStatus.AVAILABLE, unit="$", value=total,
            display_value=_usd_compact(total),
            delta_label=(
                f"longs {_usd_compact(day['long_usd'])} · shorts {_usd_compact(day['short_usd'])}"
            ),
            timestamp=newest, available_at=(newest + timedelta(hours=1)) if newest else None,
            source="Bybit (flux public en direct)", source_tier="EXCHANGE",
            quality=round(100 * day["covered_hours"] / 24), confidence=80, state="CONTEXT",
            why=why,
        )
        if day["covered_hours"] < 24:
            reading.note = f"Couverture : {day['covered_hours']} h sur 24."
    out["dominance"] = dominance
    # Buckets exist from the moment the stream runs, even before a first hour
    # has closed: "being collected" and "no source" are different states.
    out["stream_started"] = len(view.cache.series("stream.bybit_liq.minutes", a).values) > 0
    out["reading"] = reading
    return out


def derivatives_family(view: PointInTimeView, asset: Asset, horizon: DecisionHorizon) -> FamilyScore:
    window = HORIZON_WINDOW[horizon]
    scale = SCALES[horizon]
    metrics: list[MetricReading] = []
    components: list[Component] = []
    a = asset.value

    # Price change over the window, from closed candles.
    candles = view.candles(a, Timeframe.H1)
    price_change = None
    if len(candles) > window.days * 24 + 1:
        closes = candles["close"]
        price_change = (closes.iloc[-1] / closes.iloc[-(window.days * 24 + 1)] - 1) * 100

    # Open interest: hourly Binance for 24 h / 7 d, daily Bybit history for 30 d
    # and for the percentile. One venue per computation, named.
    oi_metric = "oi.value_history" if horizon is not DecisionHorizon.D30 else "oi.contracts_bybit"
    oi = read_metric(
        view, oi_metric, asset=a, window=window, label="Open interest",
        emoji="📊", unit="Md$" if oi_metric == "oi.value_history" else "",
        max_age=timedelta(hours=6) if oi_metric == "oi.value_history" else timedelta(days=3),
        transform=(lambda v: v / 1e9) if oi_metric == "oi.value_history" else None,
        why=(
            "Le montant total des positions à levier ouvertes. Il ne dit rien seul : "
            "c'est son évolution face au prix qui révèle qui entre et qui sort."
        ),
        source_tier="EXCHANGE", decimals=1,
    )
    if oi_metric == "oi.value_history" and oi.value is not None:
        oi.display_value = f"{fr_number(oi.value, 1)} Md$"
    if not oi.usable or oi.delta_pct is None:
        # Binance's hourly history only reaches back a few weeks. The daily
        # Bybit series covers years: same question, one named venue.
        fallback = read_metric(
            view, "oi.contracts_bybit", asset=a, window=max(window, timedelta(days=1)),
            label="Open interest (historique)", emoji="📊", unit="", max_age=timedelta(days=3),
            why=oi.why, source_tier="EXCHANGE", decimals=0,
        )
        if fallback.usable and fallback.delta_pct is not None:
            oi = fallback
    metrics.append(oi)
    bybit = [p.value for p in view.points("oi.contracts_bybit", a)]
    oi_pct = _percentile(bybit[-1], bybit[-730:]) if bybit else None
    if oi_pct is not None:
        oi.note = f"Niveau historique (2 ans) : {fr_number(oi_pct, 0)}e centile."

    funding = read_metric(
        view, "funding.rate", asset=a, window=window, label="Funding (8 h)", emoji="💰",
        unit="%", max_age=timedelta(hours=12), transform=lambda v: v * 100,
        why=(
            "Ce que les acheteurs à levier paient aux vendeurs pour garder leur "
            "position. Très positif : beaucoup de longs, souvent trop."
        ),
        source_tier="EXCHANGE", decimals=4,
    )
    metrics.append(funding)
    everything = view.points("funding.rate", a)
    # Settlements only (every 8 h). Live snapshots every few minutes would
    # crowd the recent end of the history and bias the percentile.
    history = [p for p in everything if "historique" in p.source] or everything
    recent_24h = [p.value * 100 for p in history if p.timestamp >= view.as_of - timedelta(days=1)]
    recent_7d = [p.value * 100 for p in history if p.timestamp >= view.as_of - timedelta(days=7)]
    current_funding = everything[-1].value if everything else None
    funding_pct = (
        _percentile(current_funding, [p.value for p in history[-1095:]])
        if current_funding is not None and history else None
    )
    if recent_24h and recent_7d:
        funding.delta_label = (
            f"moyenne 24 h {fr_number(sum(recent_24h) / len(recent_24h), 4)} % · "
            f"7 j {fr_number(sum(recent_7d) / len(recent_7d), 4)} %"
        )
    if funding_pct is not None:
        funding.note = f"{fr_number(funding_pct, 0)}e percentile sur un an."

    basis = read_metric(
        view, "derivatives.basis_pct", asset=a, window=window, label="Base (prime du perpétuel)",
        emoji="📐", unit="%", max_age=timedelta(hours=12), source_tier="EXCHANGE", decimals=3,
        # A percentage change of a spread near zero means nothing (-0.024 to
        # -0.034 read "+39 %"); the move is stated in basis points.
        delta_kind="bp",
        why="L'écart entre le prix du contrat perpétuel et le prix au comptant.",
    )
    metrics.append(basis)
    dvol = read_metric(
        view, "dvol.index", asset=a, window=window, label="Volatilité implicite (DVOL)",
        emoji="🌪️", unit="", max_age=timedelta(days=3), source_tier="EXCHANGE", decimals=1,
        why=(
            "La volatilité attendue par le marché des options sur 30 jours. Élevée, "
            "elle signale un risque de mouvement brutal dans un sens ou dans l'autre."
        ),
    )
    if dvol.status is DataStatus.UNAVAILABLE and asset is Asset.SOL:
        dvol.status = DataStatus.NOT_APPLICABLE
        dvol.note = "Deribit ne publie pas de DVOL pour SOL."
    metrics.append(dvol)
    dvol_points = [p.value for p in view.points("dvol.index", a)]
    dvol_pct = _percentile(dvol_points[-1], dvol_points[-730:]) if dvol_points else None
    if dvol_pct is not None:
        dvol.note = f"{fr_number(dvol_pct, 0)}e percentile sur deux ans."
    liquidations = liquidation_totals(view, asset)
    metrics.append(liquidations.pop("reading"))

    regime = CrowdingRegime.UNKNOWN
    if oi.usable and oi.delta_pct is not None and price_change is not None:
        up = price_change >= scale.price_move_pct * 0.5
        down = price_change <= -scale.price_move_pct * 0.5
        oi_up = oi.delta_pct >= scale.oi_move_pct * 0.5
        oi_down = oi.delta_pct <= -scale.oi_move_pct * 0.5
        hot = funding_pct is not None and funding_pct >= 85
        cold = funding_pct is not None and funding_pct <= 15
        if up and oi_up:
            regime = CrowdingRegime.CROWDED_LONGS if hot else CrowdingRegime.NEW_LONGS
        elif up and oi_down:
            regime = CrowdingRegime.SHORT_COVERING
        elif down and oi_up:
            regime = CrowdingRegime.CROWDED_SHORTS if cold else CrowdingRegime.NEW_SHORTS
        elif down and oi_down:
            regime = CrowdingRegime.DELEVERAGING
        else:
            regime = CrowdingRegime.QUIET
        signal = {
            CrowdingRegime.CROWDED_LONGS: -0.6,
            CrowdingRegime.NEW_LONGS: 0.45,
            CrowdingRegime.SHORT_COVERING: 0.1,
            CrowdingRegime.NEW_SHORTS: -0.45,
            CrowdingRegime.CROWDED_SHORTS: 0.3,
            CrowdingRegime.DELEVERAGING: 0.0,
            CrowdingRegime.QUIET: 0.0,
        }[regime]
        _mark(oi, signal)
        name, meaning = CROWDING_FR[regime]
        components.append(Component(
            "crowding", "Levier face au prix", 1.0, signal,
            f"📈 {name} : prix {fr_number(price_change, 1, signed=True)} %, open interest "
            f"{fr_number(oi.delta_pct, 1, signed=True)} % sur {_window_label(window)}. {meaning}",
            turn_condition=(
                "Un open interest qui se normalise sans cassure du prix."
                if regime is CrowdingRegime.CROWDED_LONGS else ""
            ),
            metrics=[oi.key, "funding.rate"],
        ))
    # Funding only speaks at its extremes - and never alone.
    if funding.usable and funding_pct is not None and (funding_pct >= 85 or funding_pct <= 15):
        signal = -0.5 if funding_pct >= 85 else 0.3
        _mark(funding, signal)
        components.append(Component(
            "funding_extreme", "Funding extrême", 0.5, signal,
            f"💰 Funding au {fr_number(funding_pct, 0)}e percentile de l'année : "
            + ("les acheteurs à levier paient plus que d'habitude, le marché penche d'un côté."
               if funding_pct >= 85 else "les vendeurs à découvert paient pour rester, un rachat forcé est possible."),
            metrics=["funding.rate"],
        ))
    elif funding.usable:
        funding.state = "NEUTRAL"

    result = finish_family(
        DERIVATIVES, horizon, components, metrics, min_coverage=0.5,
        headline_positive="Le levier accompagne sainement le mouvement.",
        headline_negative="L'effet de levier fragilise le marché.",
        headline_neutral="Levier sans excès.",
    )
    result.extra.update({
        "crowding": regime.value,
        "crowding_label": CROWDING_FR[regime][0],
        "funding_percentile": funding_pct,
        "oi_percentile": oi_pct,
        "dvol_percentile": dvol_pct,
        "price_change_pct": price_change,
        "liquidations": liquidations,
    })
    return result


# ---------------------------------------------------------------------------
# E. On-chain & whales
# ---------------------------------------------------------------------------


def onchain_family(view: PointInTimeView, asset: Asset, horizon: DecisionHorizon) -> FamilyScore:
    """No robust public source is connected: say so, score nothing."""

    reason = (
        "Aucune source on-chain robuste n'est branchée (flux et réserves des "
        "plateformes, grosses transactions attribuées) : Glassnode, CryptoQuant et "
        "Whale Alert exigent une clé payante. Rien n'est estimé à la place."
    )
    metrics = [
        unavailable("exchange.inflows", "Entrées sur les plateformes", "📥", reason),
        unavailable("exchange.outflows", "Sorties des plateformes", "📤", reason),
        unavailable("exchange.netflow", "Flux net des plateformes", "🔁", reason),
        unavailable("exchange.reserves", "Réserves des plateformes", "🏦", reason),
        unavailable(
            "whales.transfers", "Grosses transactions", "🐋", reason,
            why=(
                "Une grosse transaction vers une plateforme rend une vente possible, "
                "pas certaine ; vers un stockage à froid, elle réduit l'offre liquide."
            ),
        ),
    ]
    return FamilyScore(
        family=ONCHAIN, horizon=horizon.value, status=DataStatus.UNAVAILABLE,
        metrics=metrics, unavailable_reason=reason,
        headline="Données on-chain non disponibles.",
    )


# ---------------------------------------------------------------------------
# F. Technical & structure
# ---------------------------------------------------------------------------


_TECH_FRAME = {
    DecisionHorizon.H24: (Timeframe.H1, 24, 20, 50),
    DecisionHorizon.D7: (Timeframe.H4, 42, 20, 50),
    DecisionHorizon.D30: (Timeframe.D1, 30, 50, 200),
}


def _structure(asset: Asset, timeframe: Timeframe, frame: pd.DataFrame) -> tuple[str, dict[str, Any]]:
    """Confirmed swing structure, from the existing causal engine."""

    from ..structure.market_structure import MarketStructureEngine, MarketStructureReading
    from ..structure.swings import find_causal_swings
    from .technical import indicators as ind

    if len(frame) < 60:
        return "UNCLEAR", {}
    window = frame.iloc[-400:]
    atr = ind.atr(window["high"], window["low"], window["close"], 14)
    swings = find_causal_swings(window["high"], window["low"], window["close"], atr, lookback=5)
    swings = swings.as_of(window.index[-1])
    out = MarketStructureReading(asset=asset.value, timeframe=timeframe.value)
    reading = MarketStructureEngine().assess_from_swings(swings, out, window)
    last = float(window["close"].iloc[-1])
    levels = {
        "support": reading.last_confirmed_hl or reading.last_confirmed_ll,
        "resistance": reading.last_confirmed_lh or reading.last_confirmed_hh,
    }
    state = str(getattr(reading.state, "value", reading.state))
    mapped = {
        "BULLISH_STRUCTURE": "TREND_UP",
        "BEARISH_STRUCTURE": "TREND_DOWN",
        "RANGE_STRUCTURE": "RANGE",
    }.get(state, "UNCLEAR")
    # A close beyond the last confirmed swing is a break; near it, pending.
    resistance, support = levels["resistance"], levels["support"]
    if mapped == "RANGE" and resistance and last > resistance:
        mapped = "BREAKOUT_CONFIRMED"
    elif mapped == "RANGE" and support and last < support:
        mapped = "BREAKDOWN_CONFIRMED"
    elif mapped == "RANGE" and resistance and last >= resistance * 0.99:
        mapped = "BREAKOUT_PENDING"
    elif mapped == "RANGE" and support and last <= support * 1.01:
        mapped = "BREAKDOWN_PENDING"
    return mapped, {"support": support, "resistance": resistance, "raw_state": state}


STRUCTURE_FR = {
    "TREND_UP": "Tendance haussière",
    "TREND_DOWN": "Tendance baissière",
    "RANGE": "Range",
    "BREAKOUT_PENDING": "Cassure haussière en approche",
    "BREAKOUT_CONFIRMED": "Cassure haussière confirmée",
    "BREAKDOWN_PENDING": "Cassure baissière en approche",
    "BREAKDOWN_CONFIRMED": "Cassure baissière confirmée",
    "UNCLEAR": "Structure indécise",
}
_STRUCTURE_SIGNAL = {
    "TREND_UP": 0.6, "TREND_DOWN": -0.6, "RANGE": 0.0,
    "BREAKOUT_PENDING": 0.2, "BREAKOUT_CONFIRMED": 0.8,
    "BREAKDOWN_PENDING": -0.2, "BREAKDOWN_CONFIRMED": -0.8, "UNCLEAR": 0.0,
}


def technical_family(view: PointInTimeView, asset: Asset, horizon: DecisionHorizon) -> FamilyScore:
    from .technical import indicators as ind

    timeframe, _bars_in_window, fast, slow = _TECH_FRAME[horizon]
    frame = view.candles(asset.value, timeframe)
    metrics: list[MetricReading] = []
    components: list[Component] = []
    if len(frame) < slow + 20:
        return FamilyScore(
            family=TECHNICAL, horizon=horizon.value, status=DataStatus.INSUFFICIENT_DATA,
            unavailable_reason="Historique de prix insuffisant.",
            headline="Données insuffisantes pour conclure.",
        )
    frame = frame.iloc[-(slow + 400):]
    close = frame["close"]
    last_time = frame.index[-1].to_pydatetime()
    if last_time.tzinfo is None:
        last_time = last_time.replace(tzinfo=view.as_of.tzinfo)
    from .pit_view import TIMEFRAME_SPAN

    # A bar is known once closed; allow a little collection lag on top.
    allowed_lag = {Timeframe.H1: timedelta(hours=3), Timeframe.H4: timedelta(hours=6),
                   Timeframe.D1: timedelta(hours=30)}[timeframe]
    stale = view.as_of - (last_time + TIMEFRAME_SPAN[timeframe]) > allowed_lag
    status = DataStatus.STALE if stale else DataStatus.AVAILABLE
    source = "Binance (bougies)"
    last = float(close.iloc[-1])

    def add(key: str, label: str, emoji: str, value: float | None, display: str, why: str,
            delta_label: str = "") -> MetricReading:
        reading = MetricReading(
            key=key, label=label, emoji=emoji,
            status=status if value is not None else DataStatus.UNAVAILABLE,
            value=value, display_value=display if value is not None else "—",
            timestamp=last_time, available_at=last_time, source=source,
            source_tier="EXCHANGE", quality=100 if not stale else 40, confidence=85,
            delta_label=delta_label, why=why,
        )
        metrics.append(reading)
        return reading

    # Price changes on the three spans, whatever the horizon: context.
    daily = view.candles(asset.value, Timeframe.D1)
    for days, label in ((1, "24 h"), (7, "7 j"), (30, "30 j")):
        change = None
        if len(daily) > days:
            change = (last / float(daily["close"].iloc[-days - 1]) - 1) * 100
        add(f"price.change_{days}d", f"Variation {label}", "📈", change,
            f"{fr_number(change, 1, signed=True)} %" if change is not None else "—",
            "La variation du prix sur la période.")

    fast_ma = ind.ema(close, fast) if timeframe is not Timeframe.D1 else ind.sma(close, fast)
    slow_ma = ind.ema(close, slow) if timeframe is not Timeframe.D1 else ind.sma(close, slow)
    f_last, s_last = float(fast_ma.iloc[-1]), float(slow_ma.iloc[-1])
    trend_signal = 0.0
    if last > f_last > s_last:
        trend_signal = 0.7
    elif last < f_last < s_last:
        trend_signal = -0.7
    elif f_last > s_last:
        trend_signal = 0.25
    elif f_last < s_last:
        trend_signal = -0.25
    ma_kind = "EMA" if timeframe is not Timeframe.D1 else "MM"
    ma = add("technical.moving_averages", f"{ma_kind} {fast} / {slow}", "〽️", f_last - s_last,
             f"{ma_kind}{fast} {fr_number(f_last, 0)}",
             "L'alignement du prix et des moyennes mobiles résume la tendance de fond.",
             delta_label=f"{ma_kind}{fast} {fr_number(f_last, 0)} · {ma_kind}{slow} {fr_number(s_last, 0)}")
    _mark(ma, trend_signal)
    components.append(Component(
        "trend", "Tendance", 1.0, trend_signal,
        f"〽️ Prix {'au-dessus' if last > f_last else 'en dessous'} de sa {ma_kind}{fast} "
        f"({fr_number(f_last, 0)}), {ma_kind}{fast} {'au-dessus' if f_last > s_last else 'en dessous'} "
        f"de la {ma_kind}{slow}.",
        turn_condition=f"Une clôture sous la {ma_kind}{fast} ({fr_number(f_last, 0)})."
        if trend_signal > 0 else f"Une clôture au-dessus de la {ma_kind}{fast} ({fr_number(f_last, 0)}).",
        metrics=[ma.key],
    ))

    rsi = float(ind.rsi(close, 14).iloc[-1])
    rsi_reading = add("technical.rsi", "RSI 14", "📏", rsi, fr_number(rsi, 0),
                      "Au-dessus de 70 le mouvement est étiré, sous 30 il est survendu ; "
                      "en tendance, un RSI élevé est aussi un signe de force.")
    rsi_signal = math.tanh((rsi - 50) / 20) * 0.7
    if rsi >= 75:
        rsi_signal = min(rsi_signal, 0.2)  # stretched: strength, but late
    _mark(rsi_reading, rsi_signal)
    components.append(Component(
        "momentum", "Momentum (RSI)", 0.5, rsi_signal,
        f"📏 RSI {fr_number(rsi, 0)}"
        + (" : mouvement étiré." if rsi >= 70 else " : survente." if rsi <= 30 else "."),
        metrics=[rsi_reading.key],
    ))

    atr_pct = float(ind.atr_percent(frame["high"], frame["low"], close, 14).iloc[-1])
    add("technical.atr_pct", "ATR (amplitude moyenne)", "📐", atr_pct, f"{fr_number(atr_pct, 2)} %",
        "L'amplitude moyenne d'une bougie : elle dimensionne les stops et les objectifs.")
    periods = {Timeframe.H1: 24 * 365, Timeframe.H4: 6 * 365, Timeframe.D1: 365}[timeframe]
    realized = float(ind.realized_volatility(close, 20, periods).iloc[-1])
    realized_pct = realized  # already annualised percent
    add("technical.realized_vol", "Volatilité réalisée", "🌪️", realized_pct,
        f"{fr_number(realized_pct, 0)} % annualisée", "L'agitation effective du prix récemment.")
    bandwidth = ind.bollinger_bandwidth(close, 20, 2.0)
    bw = float(bandwidth.iloc[-1])
    bw_hist = bandwidth.dropna().iloc[-250:]
    bw_pct = float((bw_hist <= bw).mean() * 100) if len(bw_hist) >= 50 else None
    squeeze = "compression" if bw_pct is not None and bw_pct <= 15 else (
        "expansion" if bw_pct is not None and bw_pct >= 85 else "normale")
    add("technical.bollinger_bandwidth", "Largeur de Bollinger", "📊", bw,
        f"{squeeze}" + (f" ({fr_number(bw_pct, 0)}e centile)" if bw_pct is not None else ""),
        "Des bandes resserrées annoncent souvent un mouvement ample à venir, sans en dire le sens.")

    structure, _swing_levels = _structure(asset, timeframe, frame)
    # Support and resistance come from clusters of confirmed pivots on a frame
    # where a pivot means something (4 h, or daily for the 30 d call), not
    # from the last swing - which could sit below the price and still be
    # called "resistance".
    from .key_levels import find_key_levels

    level_tf = Timeframe.D1 if horizon is DecisionHorizon.D30 else Timeframe.H4
    level_frame = frame if level_tf is timeframe else view.candles(asset.value, level_tf)
    key_support, key_resistance, _all_levels = find_key_levels(level_frame, level_tf.value)
    levels = {
        "support": key_support.price if key_support else None,
        "resistance": key_resistance.price if key_resistance else None,
    }
    structure_reading = add(
        "technical.structure", "Structure de marché", "🧱", _STRUCTURE_SIGNAL[structure],
        STRUCTURE_FR[structure],
        "La suite des sommets et des creux confirmés : elle dit si la tendance tient.",
    )
    _mark(structure_reading, _STRUCTURE_SIGNAL[structure])
    if key_support is not None:
        reading = add("technical.support", "Support clé", "🟢", key_support.price,
                      f"{fr_number(key_support.price, 0)} $",
                      "Le niveau le plus proche sous le prix où le marché a déjà rebondi.")
        reading.note = key_support.explanation
        reading.unit = "$"
    if key_resistance is not None:
        reading = add("technical.resistance", "Prochaine résistance", "🔴", key_resistance.price,
                      f"{fr_number(key_resistance.price, 0)} $",
                      "Le prochain niveau au-dessus du prix où le marché a déjà reculé.")
        reading.note = key_resistance.explanation
        reading.unit = "$"
    components.append(Component(
        "structure", "Structure", 0.8, _STRUCTURE_SIGNAL[structure],
        f"🧱 {STRUCTURE_FR[structure]}"
        + (f" ; support {fr_number(float(levels['support']), 0)} $" if levels.get("support") else "")
        + (f", résistance {fr_number(float(levels['resistance']), 0)} $" if levels.get("resistance") else "")
        + ".",
        turn_condition=(
            f"Une clôture sous le support ({fr_number(float(levels['support']), 0)} $)."
            if levels.get("support") and _STRUCTURE_SIGNAL[structure] > 0
            else f"Une clôture au-dessus de la résistance ({fr_number(float(levels['resistance']), 0)} $)."
            if levels.get("resistance") and _STRUCTURE_SIGNAL[structure] < 0 else ""
        ),
        metrics=[structure_reading.key],
    ))

    # BTC dominance, as context for ETH and SOL.
    if asset is not Asset.BTC:
        dominance = read_metric(
            view, "market.dominance", asset="BTC", window=HORIZON_WINDOW[horizon],
            label="Dominance BTC", emoji="👑", unit="%", max_age=timedelta(hours=12),
            source_tier="AGGREGATOR", delta_kind="abs",
            why="Quand la part du bitcoin monte, les capitaux délaissent les autres cryptos.",
        )
        metrics.append(dominance)
        if dominance.usable and dominance.delta is not None:
            signal = -_squash(dominance.delta, 1.0)
            _mark(dominance, signal)
            components.append(Component(
                "btc_dominance", "Dominance BTC", 0.3, signal,
                f"👑 Dominance BTC {dominance.display_value} ({dominance.delta_label}).",
                metrics=[dominance.key],
            ))

    result = finish_family(
        TECHNICAL, horizon, components, metrics,
        headline_positive="La structure de prix soutient la hausse.",
        headline_negative="La structure de prix reste fragile.",
        headline_neutral="Structure sans direction nette.",
    )
    result.extra.update({
        # Levels come from the exchange's USDT pair, not from the EUR price in
        # the header: they are labelled in dollars, never shown as euros.
        "quote": "USDT",
        "price": last,
        "fast_ma": f_last,
        "slow_ma": s_last,
        "ma_kind": ma_kind,
        "fast": fast,
        "slow": slow,
        "trend_signal": trend_signal,
        "changes": {
            days: next((m.value for m in metrics if m.key == f"price.change_{days}d"), None)
            for days in (1, 7, 30)
        },
        "structure": structure,
        "structure_label": STRUCTURE_FR[structure],
        "support": levels.get("support"),
        "resistance": levels.get("resistance"),
        "support_detail": key_support.to_dict() if key_support else None,
        "resistance_detail": key_resistance.to_dict() if key_resistance else None,
        "levels_timeframe": level_tf.value,
        "timeframe": timeframe.value,
        "rsi": rsi,
        "bollinger_percentile": bw_pct,
    })
    return result



# ---------------------------------------------------------------------------
# G. Bitcoin cycle / crypto regime - context, never a trigger
# ---------------------------------------------------------------------------

#: Relative move against BTC that counts as a clear out- or under-performance.
_RELATIVE_SCALE = {DecisionHorizon.H24: 2.0, DecisionHorizon.D7: 5.0, DecisionHorizon.D30: 10.0}
#: The cycle family can never lean harder than this, whatever it reads.
CYCLE_SIGNAL_CAP = 0.4


def _btc_cycle(view: PointInTimeView):
    """The cycle regime, computed once per data cache and reused."""

    from .cycle_regime import BitcoinCycleRegimeEngine

    cached = getattr(view.cache, "_cycle_regime", None)
    if cached is not None:
        return cached
    halvings = [
        datetime.fromtimestamp(p.value, tz=view.as_of.tzinfo)
        for p in view.points("btc.halving.block_epoch")
    ]
    regime = BitcoinCycleRegimeEngine().read(
        view.candles("BTC", Timeframe.D1), halvings, as_of=view.as_of
    )
    view.cache._cycle_regime = regime
    return regime


def cycle_family(view: PointInTimeView, asset: Asset, horizon: DecisionHorizon) -> FamilyScore:
    from .cycle_regime import CYCLE_SIGNAL_CAP, PHASE_LEAN

    regime = _btc_cycle(view)
    metrics: list[MetricReading] = []
    components: list[Component] = []
    if regime is None:
        return FamilyScore(
            family=CYCLE, horizon=horizon.value, status=DataStatus.INSUFFICIENT_DATA,
            unavailable_reason="Historique journalier de BTC insuffisant pour situer le cycle.",
            headline="Cycle indéterminé.",
        )
    dims = regime.dimensions
    payload = regime.to_dict()
    stamp = regime.data_cutoff

    def add(key: str, label: str, emoji: str, value: float | None, display: str, why: str,
            source: str = "Bougies journalières", tier: str = "EXCHANGE") -> MetricReading:
        reading = MetricReading(
            key=key, label=label, emoji=emoji,
            status=DataStatus.AVAILABLE if value is not None else DataStatus.UNAVAILABLE,
            value=value, display_value=display if value is not None else "—",
            timestamp=stamp, available_at=stamp, source=source, source_tier=tier,
            quality=100, confidence=regime.confidence, state="CONTEXT", why=why,
        )
        metrics.append(reading)
        return reading

    name = "Cycle Bitcoin" if asset is Asset.BTC else "Régime Bitcoin"
    add("cycle.phase", name, "🔄", float(regime.confidence), f"{regime.emoji} {regime.label}",
        "La phase vient de plusieurs mesures du marché - écart au record, structure long "
        "terme, momentum, volatilité. Jamais du seul nombre de jours depuis le halving.")
    add("cycle.direction", "Direction du régime", payload["direction_emoji"],
        regime.health_change, payload["direction_label"],
        "L'évolution de la santé du régime sur un mois : la phase peut tenir alors que "
        "la situation s'améliore ou se dégrade.")
    add("cycle.days_in_phase", "Phase actuelle depuis", "📅", float(regime.days_in_phase),
        f"{regime.days_in_phase} jours",
        "Une phase ne change qu'une fois confirmée sur plusieurs clôtures.")
    add("cycle.drawdown", "Distance de l'ATH", "🏆", dims.drawdown_pct,
        f"{fr_number(dims.drawdown_pct, 0, signed=True)} %",
        f"Record de {fr_number(dims.ath, 0)} $ le {dims.ath_date:%d/%m/%Y}.")
    if dims.days_since_halving is not None:
        add("cycle.days_since_halving", "Depuis le halving", "⚡", float(dims.days_since_halving),
            f"{dims.days_since_halving} jours",
            "Le halving est un repère historique, pas une règle prédictive.",
            source="Horodatage du bloc", tier="OFFICIAL")

    lean = max(-CYCLE_SIGNAL_CAP, min(CYCLE_SIGNAL_CAP, PHASE_LEAN[regime.phase]))
    components.append(Component(
        "btc_cycle", name, 1.0 if asset is Asset.BTC else 0.6, lean,
        f"🔄 {name} : {regime.label.lower()} ({payload['direction_label'].lower()}). "
        + (regime.evidence[0] if regime.evidence else ""),
        metrics=["cycle.phase"],
    ))

    relative: dict[str, Any] | None = None
    if asset is not Asset.BTC:
        window = HORIZON_WINDOW[horizon]
        own = view.candles(asset.value, Timeframe.H1)
        btc = view.candles("BTC", Timeframe.H1)
        hours = int(window.total_seconds() // 3600)
        if len(own) > hours + 1 and len(btc) > hours + 1:
            ratio_now = float(own["close"].iloc[-1]) / float(btc["close"].iloc[-1])
            ratio_then = float(own["close"].iloc[-hours - 1]) / float(btc["close"].iloc[-hours - 1])
            change = (ratio_now / ratio_then - 1) * 100
            signal = _squash(change, _RELATIVE_SCALE[horizon]) * 0.5
            reading = add(f"cycle.relative_{asset.value.lower()}_btc", f"{asset.value}/BTC",
                          "⚖️", change, f"{fr_number(change, 1, signed=True)} %",
                          f"{asset.value} n'a pas de halving : seuls le régime de BTC et la "
                          "force relative donnent du contexte.")
            reading.state = (
                "FAVORABLE" if signal > 0.15 else "UNFAVORABLE" if signal < -0.15 else "NEUTRAL"
            )
            relative = {
                "change_pct": change, "window": _window_label(window),
                "label": (f"{asset.value} surperforme BTC" if change > 0
                          else f"{asset.value} sous-performe BTC"),
            }
            components.append(Component(
                "relative_strength", f"{asset.value} face à BTC", 0.4, signal,
                f"⚖️ {relative['label']} ({fr_number(change, 1, signed=True)} % sur "
                f"{_window_label(window)}).",
                metrics=[reading.key],
            ))

    headline = regime.evidence[0] if regime.evidence else regime.label
    result = finish_family(
        CYCLE, horizon, components, metrics,
        headline_positive=headline, headline_negative=headline, headline_neutral=headline,
    )
    result.extra.update({
        "cycle": payload, "relative": relative, "is_context": True, "asset": asset.value,
    })
    return result


FAMILY_BUILDERS = {
    MACRO: macro_family,
    LIQUIDITY: liquidity_family,
    FLOWS: flows_family,
    DERIVATIVES: derivatives_family,
    ONCHAIN: onchain_family,
    TECHNICAL: technical_family,
    CYCLE: cycle_family,
}


def build_families(
    view: PointInTimeView, asset: Asset, horizon: DecisionHorizon
) -> dict[str, FamilyScore]:
    out: dict[str, FamilyScore] = {}
    for name, builder in FAMILY_BUILDERS.items():
        try:
            out[name] = builder(view, asset, horizon)
        except Exception as exc:  # a broken family is reported, never fatal
            out[name] = FamilyScore(
                family=name, horizon=horizon.value, status=DataStatus.UNAVAILABLE,
                unavailable_reason=f"Calcul impossible : {type(exc).__name__}.",
                headline="Données indisponibles.",
            )
    return out

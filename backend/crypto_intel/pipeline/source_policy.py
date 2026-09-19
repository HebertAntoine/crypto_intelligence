"""How often each source is worth asking, and when its answer stops counting.

Two numbers, deliberately separate. ``refresh_interval`` is how often we try;
``max_age`` is when the answer stops being usable. They are not the same thing:
funding can be polled every fifteen minutes and still be perfectly good at
forty, while an ETF file republished once a day is worthless the moment it is
two days old regardless of how often we checked.

The intervals are not invented here. The project already scheduled market data
every five minutes, derivatives hourly, ETF every four hours and the event
calendars every six, and those choices are carried over. What is added is the
second number, the criticality, and a single place to read them from.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any


class Criticality(StrEnum):
    """What the pipeline owes a source when it fails."""

    CRITICAL = "CRITICAL"      # a verdict without it is not defensible
    IMPORTANT = "IMPORTANT"    # the family degrades, the pipeline continues
    OPTIONAL = "OPTIONAL"      # absence is noted and nothing else changes


class SourceHealth(StrEnum):
    """The state of the *source*, which is not the state of its data."""

    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    DOWN = "DOWN"
    AUTH_ERROR = "AUTH_ERROR"
    RATE_LIMITED = "RATE_LIMITED"
    DATA_STUCK = "DATA_STUCK"
    NOT_CONFIGURED = "NOT_CONFIGURED"


class RunType(StrEnum):
    FULL = "FULL"
    LIGHT = "LIGHT"
    EVENT = "EVENT"
    MANUAL = "MANUAL"


@dataclass(slots=True, frozen=True)
class RetryPolicy:
    """Bounded, and different per failure kind.

    An expired credential does not become valid by being asked again, so auth
    failures are not retried at all. A rate limit is the source telling us the
    cadence is wrong; it is respected rather than worked around.
    """

    attempts: int = 3
    base_delay_s: float = 1.0
    max_delay_s: float = 30.0
    #: Jitter spreads simultaneous retries so a recovering source is not hit by
    #: every client at the same instant.
    jitter_ratio: float = 0.25

    def delay_for(self, attempt: int, *, rng: Any = None) -> float:
        raw = min(self.base_delay_s * (2 ** max(0, attempt - 1)), self.max_delay_s)
        if not self.jitter_ratio:
            return raw
        spread = raw * self.jitter_ratio
        offset = (rng.uniform(-spread, spread) if rng is not None else 0.0)
        return max(0.0, raw + offset)


#: Errors that a second attempt cannot fix.
NON_RETRYABLE = {"AUTH", "HTTP_4XX", "BLOCKED_BY_SOURCE", "NOT_CONFIGURED"}


def is_retryable(error_kind: str) -> bool:
    return error_kind.upper() not in NON_RETRYABLE


@dataclass(slots=True, frozen=True)
class SourceRefreshPolicy:
    source_id: str
    family: str
    refresh_interval: timedelta
    max_age: timedelta
    criticality: Criticality
    #: True when the source is worth polling between full cycles.
    fast: bool = False
    timeout_s: float = 20.0
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    fallback_sources: tuple[str, ...] = ()
    event_driven: bool = False
    enabled: bool = True
    #: Metric prefix to read freshness from when the source is collected by the
    #: full pass rather than the light one. Measuring the stored observation is
    #: honest where attributing a bulk collect to one source would be a guess.
    metric_prefix: str = ""
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "family": self.family,
            "refresh_interval_min": self.refresh_interval.total_seconds() / 60,
            "max_age_min": self.max_age.total_seconds() / 60,
            "criticality": self.criticality.value,
            "fast": self.fast,
            "timeout_s": self.timeout_s,
            "fallback_sources": list(self.fallback_sources),
            "event_driven": self.event_driven,
            "enabled": self.enabled,
            "note": self.note,
        }


def _m(minutes: float) -> timedelta:
    return timedelta(minutes=minutes)


#: The catalogue. Intervals carry over the cadences the scheduler already used;
#: the maximum ages come from how often each source actually publishes.
POLICIES: dict[str, SourceRefreshPolicy] = {
    # -- fast: the market moves between full cycles ------------------------
    "market_price": SourceRefreshPolicy(
        source_id="market_price",
        family="technical",
        refresh_interval=_m(5),
        max_age=_m(30),
        criticality=Criticality.CRITICAL,
        fast=True,
        note="Cadence reprise du job 'market'. Un prix de plus de 30 min ne "
        "décrit plus la séance en cours.",
    ),
    "ohlcv": SourceRefreshPolicy(
        source_id="ohlcv",
        family="technical",
        refresh_interval=_m(15),
        max_age=_m(90),
        criticality=Criticality.CRITICAL,
        fast=True,
        note="La plus petite bougie suivie est de 15 min: interroger plus "
        "souvent ne produirait aucune barre nouvelle.",
    ),
    "derivatives_oi": SourceRefreshPolicy(
        source_id="derivatives_oi",
        family="derivatives",
        refresh_interval=_m(15),
        max_age=_m(60),
        criticality=Criticality.IMPORTANT,
        fast=True,
        fallback_sources=("bybit_oi",),
        note="L'intérêt ouvert bouge en continu; l'heure du job existant "
        "laissait une lecture vieillir sans raison.",
    ),
    "derivatives_funding": SourceRefreshPolicy(
        source_id="derivatives_funding",
        family="derivatives",
        refresh_interval=_m(15),
        max_age=_m(60),
        criticality=Criticality.IMPORTANT,
        fast=True,
        note="Le funding se règle toutes les 8 h mais s'anticipe en continu; "
        "60 min couvre un cycle manqué sans périmer une lecture utile.",
    ),
    "spot_pressure": SourceRefreshPolicy(
        source_id="spot_pressure",
        family="spot",
        refresh_interval=_m(5),
        max_age=_m(30),
        criticality=Criticality.IMPORTANT,
        fast=True,
        note="Mesure de flux au comptant: sa valeur est immédiate.",
    ),
    "implied_volatility": SourceRefreshPolicy(
        source_id="implied_volatility",
        family="derivatives",
        refresh_interval=_m(30),
        max_age=_m(180),
        criticality=Criticality.OPTIONAL,
        fast=True,
        note="DVOL est un indice de séance; il ne se recalcule pas en continu.",
    ),
    # -- slower: these publish on a schedule of their own ------------------
    "etf_flows": SourceRefreshPolicy(
        source_id="etf_flows",
        family="flows",
        refresh_interval=_m(120),
        max_age=_m(60 * 30),
        criticality=Criticality.IMPORTANT,
        metric_prefix="etf.",
        note="Farside publie une fois par séance, en soirée. Deux heures "
        "suffisent à l'attraper; au-delà de 30 h une séance a été manquée.",
    ),
    "stablecoins": SourceRefreshPolicy(
        source_id="stablecoins",
        family="flows",
        refresh_interval=_m(240),
        max_age=_m(60 * 24),
        criticality=Criticality.OPTIONAL,
        metric_prefix="stablecoin",
        note="Les encours bougent lentement et se lisent à l'échelle du jour.",
    ),
    "macro_series": SourceRefreshPolicy(
        source_id="macro_series",
        family="macro",
        refresh_interval=_m(120),
        max_age=_m(60 * 26),
        criticality=Criticality.IMPORTANT,
        metric_prefix="macro.",
        note="Séries quotidiennes (taux, pétrole). 26 h laissent passer un "
        "week-end sans déclarer périmé ce qui ne l'est pas.",
    ),
    "macro_credit": SourceRefreshPolicy(
        source_id="macro_credit",
        family="macro",
        refresh_interval=_m(240),
        max_age=_m(60 * 30),
        criticality=Criticality.IMPORTANT,
        enabled=False,
        metric_prefix="macro.hy_spread",
        note="ICE BofA via FRED: désactivée tant qu'aucune clé n'est "
        "configurée, plutôt que d'échouer deux fois par jour.",
    ),
    "liquidity_official": SourceRefreshPolicy(
        source_id="liquidity_official",
        family="liquidity",
        refresh_interval=_m(720),
        max_age=_m(60 * 24 * 5),
        criticality=Criticality.IMPORTANT,
        metric_prefix="liquidity.",
        note="Bilan de la Fed (hebdomadaire), TGA et RRP (quotidiens, jours "
        "ouvrés) : cinq jours couvrent un week-end prolongé et la publication "
        "hebdomadaire du H.4.1.",
    ),
    "event_calendars": SourceRefreshPolicy(
        source_id="event_calendars",
        family="events",
        refresh_interval=_m(360),
        max_age=_m(60 * 24),
        criticality=Criticality.IMPORTANT,
        event_driven=True,
        note="Les calendriers officiels changent rarement, mais la fenêtre "
        "autour d'un événement impose une vérification rapprochée.",
    ),
    "regulation": SourceRefreshPolicy(
        source_id="regulation",
        family="events",
        refresh_interval=_m(360),
        max_age=_m(60 * 48),
        criticality=Criticality.OPTIONAL,
        event_driven=True,
        note="Étapes législatives: lentes, sauf vote imminent.",
    ),
    "whales": SourceRefreshPolicy(
        source_id="whales",
        family="spot",
        refresh_interval=_m(60),
        max_age=_m(360),
        criticality=Criticality.OPTIONAL,
        metric_prefix="whale",
        note="Transferts attribués: utiles en tendance, pas à la minute.",
    ),
}


def fast_sources() -> list[SourceRefreshPolicy]:
    return [item for item in POLICIES.values() if item.enabled and item.fast]


def policy_for(source_id: str) -> SourceRefreshPolicy | None:
    return POLICIES.get(source_id)


# ---------------------------------------------------------------------------
# Runtime state
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class SourceState:
    """What happened last time, kept apart from what was asked for.

    ``last_attempt_at`` and ``last_success_at`` are separate on purpose: a
    source called five minutes ago that has been failing for three hours is not
    fresh, and judging due-ness on the attempt would hide exactly that.
    """

    source_id: str
    last_attempt_at: datetime | None = None
    last_success_at: datetime | None = None
    consecutive_failures: int = 0
    circuit: str = "CLOSED"
    opened_at: datetime | None = None
    last_error_kind: str = ""
    last_payload_fingerprint: str = ""
    unchanged_successes: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "last_attempt_at": self.last_attempt_at.isoformat() if self.last_attempt_at else None,
            "last_success_at": self.last_success_at.isoformat() if self.last_success_at else None,
            "consecutive_failures": self.consecutive_failures,
            "circuit": self.circuit,
            "opened_at": self.opened_at.isoformat() if self.opened_at else None,
            "last_error_kind": self.last_error_kind,
            "last_payload_fingerprint": self.last_payload_fingerprint,
            "unchanged_successes": self.unchanged_successes,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> SourceState:
        def when(key: str) -> datetime | None:
            value = payload.get(key)
            return datetime.fromisoformat(value) if value else None

        return cls(
            source_id=str(payload.get("source_id") or ""),
            last_attempt_at=when("last_attempt_at"),
            last_success_at=when("last_success_at"),
            consecutive_failures=int(payload.get("consecutive_failures") or 0),
            circuit=str(payload.get("circuit") or "CLOSED"),
            opened_at=when("opened_at"),
            last_error_kind=str(payload.get("last_error_kind") or ""),
            last_payload_fingerprint=str(payload.get("last_payload_fingerprint") or ""),
            unchanged_successes=int(payload.get("unchanged_successes") or 0),
        )


#: Failures before a source is left alone, and how long it is left alone.
CIRCUIT_FAILURE_THRESHOLD = 3
CIRCUIT_COOLDOWN = timedelta(minutes=30)

#: Identical payloads in a row before the source is called stuck. Three is the
#: smallest count that cannot be a coincidence of two equal readings.
STUCK_THRESHOLD = 3


def circuit_allows(state: SourceState, now: datetime) -> bool:
    """Whether the source may be called at all right now."""

    if state.circuit == "CLOSED":
        return True
    if state.circuit == "OPEN":
        if state.opened_at and now - state.opened_at >= CIRCUIT_COOLDOWN:
            # The cooldown has passed: one probe is allowed through.
            state.circuit = "HALF_OPEN"
            return True
        return False
    return True  # HALF_OPEN lets a single probe through


def is_due(
    policy: SourceRefreshPolicy, state: SourceState | None, now: datetime
) -> bool:
    """Due-ness is measured from the last *success*, never the last attempt."""

    if not policy.enabled:
        return False
    if state is None:
        return True
    # The breaker is checked first. Ordering it after the "never succeeded"
    # case let a source that has only ever failed be hammered on every pass,
    # which is the exact situation the breaker exists to stop.
    if not circuit_allows(state, now):
        return False
    if state.last_success_at is None:
        return True
    return now - state.last_success_at >= policy.refresh_interval


def which_sources_are_due(
    states: dict[str, SourceState], now: datetime, *, fast_only: bool = False
) -> list[SourceRefreshPolicy]:
    """Ask the policies, so adding a source never means editing the runner."""

    candidates = fast_sources() if fast_only else [
        item for item in POLICIES.values() if item.enabled
    ]
    return [item for item in candidates if is_due(item, states.get(item.source_id), now)]


def record_attempt(state: SourceState, now: datetime) -> None:
    state.last_attempt_at = now


def record_success(
    state: SourceState, now: datetime, *, fingerprint: str = ""
) -> None:
    state.last_success_at = now
    state.consecutive_failures = 0
    state.last_error_kind = ""
    if state.circuit in {"OPEN", "HALF_OPEN"}:
        state.circuit = "CLOSED"
        state.opened_at = None
    if fingerprint:
        if fingerprint == state.last_payload_fingerprint:
            state.unchanged_successes += 1
        else:
            state.unchanged_successes = 0
        state.last_payload_fingerprint = fingerprint


def record_failure(state: SourceState, now: datetime, *, error_kind: str) -> None:
    state.consecutive_failures += 1
    state.last_error_kind = error_kind
    # An auth failure is not a flaky network: one is enough to stop asking.
    threshold = 1 if error_kind.upper() == "AUTH" else CIRCUIT_FAILURE_THRESHOLD
    if state.circuit == "HALF_OPEN" or state.consecutive_failures >= threshold:
        state.circuit = "OPEN"
        state.opened_at = now


def health_of(
    policy: SourceRefreshPolicy, state: SourceState | None, now: datetime
) -> SourceHealth:
    """The source's own condition, separate from the age of its data."""

    if not policy.enabled:
        return SourceHealth.NOT_CONFIGURED
    if state is None:
        return SourceHealth.HEALTHY
    if state.last_error_kind.upper() == "AUTH":
        return SourceHealth.AUTH_ERROR
    if state.last_error_kind.upper() in {"HTTP_429", "RATE_LIMITED"}:
        return SourceHealth.RATE_LIMITED
    if state.unchanged_successes >= STUCK_THRESHOLD:
        return SourceHealth.DATA_STUCK
    if state.circuit == "OPEN":
        return SourceHealth.DOWN
    if state.consecutive_failures:
        return SourceHealth.DEGRADED
    return SourceHealth.HEALTHY


def data_freshness(
    policy: SourceRefreshPolicy, state: SourceState | None, now: datetime
) -> str:
    """The age of the answer, whatever the source is doing now."""

    if state is None or state.last_success_at is None:
        return "UNAVAILABLE"
    age = now - state.last_success_at
    if age >= policy.max_age:
        return "STALE"
    if age >= policy.max_age / 2:
        return "AGING"
    return "FRESH"

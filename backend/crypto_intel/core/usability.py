"""Present, valid, fresh, usable - four questions, not one.

The page used to answer a single question per family: is the data there. That
collapsed four different things into one word, and the collapse showed on
screen: an embedded snapshot nearly an hour old reported every family as "OK"
while the page header correctly said the data were stale. Both statements came
from the same payload, and only one of them was true.

So each family now answers four questions separately:

  available   the data exists at all
  valid       it parses, and its numbers are in range
  fresh       it is recent enough for the role it plays here
  usable      it may feed the verdict being shown right now

The fourth is the one the UI needs and the only one that gates an action. A
funding series can be present, valid, and two days old: available, valid, not
fresh, not usable. Calling that "OK" is what produced a confident reading on
top of stale numbers.

Freshness thresholds are per family because the sources do not share a cadence.
A six-minute-old spot price is old; a six-hour-old ETF flow is normal, because
it is published once a session. The thresholds live in `core/freshness.py` and
are read from there rather than restated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class Freshness(StrEnum):
    """How recent, judged against the family's own normal cadence."""

    LIVE = "LIVE"
    RECENT = "RECENT"
    DELAYED = "DELAYED"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"

    @property
    def is_fresh(self) -> bool:
        return self in (Freshness.LIVE, Freshness.RECENT)


class PageStatus(StrEnum):
    """What the page as a whole may claim."""

    LIVE = "LIVE"
    RECENT = "RECENT"
    DEGRADED = "DEGRADED"
    STALE = "STALE"
    SUSPENDED = "SUSPENDED"
    UNAVAILABLE = "UNAVAILABLE"

    @property
    def allows_action(self) -> bool:
        return self in (PageStatus.LIVE, PageStatus.RECENT, PageStatus.DEGRADED)


# Seconds before a family stops being live / recent / delayed. Chosen from how
# often each source actually publishes, not from a single global TTL.
CADENCE: dict[str, dict[str, int]] = {
    # Spot price moves continuously; a minute old is already not "now".
    "price": {"live": 120, "recent": 900, "delayed": 3600},
    # Daily candles close once a day, so the useful question is whether the
    # last close is yesterday's or older. One day plus a margin for ingestion.
    "ohlcv_daily": {"live": 93600, "recent": 172800, "delayed": 345600},
    # Funding settles every eight hours on most venues.
    "funding": {"live": 3600, "recent": 32400, "delayed": 86400},
    # Open interest is polled in minutes but backfilled daily.
    "open_interest": {"live": 3600, "recent": 93600, "delayed": 259200},
    # Implied volatility index, published continuously but consumed daily.
    "dvol": {"live": 3600, "recent": 93600, "delayed": 259200},
    "default": {"live": 300, "recent": 3600, "delayed": 86400},
}


def freshness_for(family: str, observed_at: datetime | None, now: datetime | None = None) -> Freshness:
    """Classify an observation against its family's cadence."""
    if observed_at is None:
        return Freshness.UNAVAILABLE
    reference = now or datetime.now(UTC)
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=UTC)
    age = (reference - observed_at).total_seconds()
    # A timestamp well into the future means a broken clock somewhere. Do not
    # reward it with the freshest possible verdict.
    if age < -300:
        return Freshness.UNAVAILABLE
    thresholds = CADENCE.get(family, CADENCE["default"])
    if age <= thresholds["live"]:
        return Freshness.LIVE
    if age <= thresholds["recent"]:
        return Freshness.RECENT
    if age <= thresholds["delayed"]:
        return Freshness.DELAYED
    return Freshness.STALE


@dataclass(slots=True)
class FamilyState:
    """One input family, answered four ways."""

    family: str
    available: bool = False
    valid: bool = False
    freshness: Freshness = Freshness.UNAVAILABLE
    observed_at: datetime | None = None
    source: str = ""
    reason: str = ""
    points: int | None = None

    @property
    def usable(self) -> bool:
        return self.available and self.valid and self.freshness.is_fresh

    def to_dict(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "available": self.available,
            "valid": self.valid,
            "freshness": self.freshness.value,
            "usable": self.usable,
            "observed_at": self.observed_at.isoformat() if self.observed_at else None,
            "age_seconds": (
                round((datetime.now(UTC) - self.observed_at).total_seconds(), 1)
                if self.observed_at else None
            ),
            "source": self.source,
            "points": self.points,
            "reason": self.reason or self._default_reason(),
        }

    def _default_reason(self) -> str:
        if not self.available:
            return "aucune observation disponible"
        if not self.valid:
            return "les valeurs reçues ne sont pas exploitables"
        if self.freshness is Freshness.DELAYED:
            return "au-delà de la cadence normale de cette source"
        if self.freshness is Freshness.STALE:
            return "trop ancienne pour décrire l'état actuel"
        if self.freshness is Freshness.UNAVAILABLE:
            return "âge inconnu, donc traitée comme périmée"
        return "présente, valide et dans sa cadence"


@dataclass(slots=True)
class EngineDependencies:
    """What an engine must have, and what merely improves it."""

    engine: str
    required: list[str] = field(default_factory=list)
    optional: list[str] = field(default_factory=list)


# Read from the engines themselves rather than assumed. `required` means the
# engine cannot produce a current answer without it; `optional` means its
# absence widens the uncertainty but does not invalidate the result.
DEPENDENCIES: dict[str, EngineDependencies] = {
    "price": EngineDependencies("price", required=["price"]),
    "direction": EngineDependencies("direction", required=["ohlcv_daily"]),
    "persistence": EngineDependencies("persistence", required=["ohlcv_daily"]),
    "volatility": EngineDependencies(
        "volatility", required=["ohlcv_daily"], optional=["dvol"]
    ),
    "funding": EngineDependencies("funding", required=["funding"]),
    "positioning": EngineDependencies(
        "positioning", required=["ohlcv_daily", "open_interest"], optional=["funding"]
    ),
    "crowding": EngineDependencies(
        "crowding", required=["funding", "open_interest"]
    ),
    "edge": EngineDependencies("edge", required=["ohlcv_daily"]),
    "uncertainty": EngineDependencies("uncertainty", required=[]),
    "action": EngineDependencies(
        "action", required=["price", "ohlcv_daily"], optional=["funding"]
    ),
}


@dataclass(slots=True)
class EngineState:
    engine: str
    usable: bool
    blocking: list[str] = field(default_factory=list)
    degraded_by: list[str] = field(default_factory=list)
    mode: str = "full"
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "engine": self.engine,
            "usable": self.usable,
            "mode": self.mode,
            "blocking_inputs": self.blocking,
            "degraded_by": self.degraded_by,
            "reason": self.reason,
        }


def assess_engine(
    engine: str, families: dict[str, FamilyState], mode: str = "full"
) -> EngineState:
    """An engine is usable only if every required input is."""
    spec = DEPENDENCIES.get(engine)
    if spec is None:
        return EngineState(engine=engine, usable=False, reason="moteur non déclaré")

    blocking = [
        name for name in spec.required
        if name not in families or not families[name].usable
    ]
    degraded = [
        name for name in spec.optional
        if name not in families or not families[name].usable
    ]

    if blocking:
        detail = ", ".join(blocking)
        return EngineState(
            engine=engine, usable=False, blocking=blocking, degraded_by=degraded,
            mode=mode,
            reason=(
                f"entrée obligatoire non utilisable: {detail}. Le résultat a pu "
                "être calculé, mais il ne décrit plus l'état actuel."
            ),
        )

    return EngineState(
        engine=engine, usable=True, degraded_by=degraded, mode=mode,
        reason=(
            "toutes les entrées obligatoires sont utilisables"
            + (f"; {', '.join(degraded)} manquante(s) ou périmée(s), ce qui "
               "élargit l'incertitude sans invalider le résultat"
               if degraded else "")
        ),
    )


def page_status(
    families: dict[str, FamilyState],
    engines: dict[str, EngineState],
    critical: tuple[str, ...] = ("price", "ohlcv_daily"),
) -> tuple[PageStatus, str]:
    """What the page as a whole may claim, and why."""
    if not families:
        return PageStatus.UNAVAILABLE, "aucune famille d'entrée n'a été évaluée"

    missing_critical = [
        name for name in critical
        if name not in families or not families[name].available
    ]
    if missing_critical:
        return (
            PageStatus.UNAVAILABLE,
            f"donnée critique absente: {', '.join(missing_critical)}",
        )

    stale_critical = [
        name for name in critical if not families[name].usable
    ]
    if stale_critical:
        # Critical inputs exist but are too old: the analysis is not merely
        # uncertain, it is about a moment that has passed.
        return (
            PageStatus.SUSPENDED,
            f"entrée critique périmée: {', '.join(stale_critical)}. Aucune "
            "analyse actuelle ne peut en être tirée.",
        )

    unusable_engines = [name for name, state in engines.items() if not state.usable]
    if unusable_engines:
        return (
            PageStatus.STALE,
            f"{len(unusable_engines)} moteur(s) sans entrée utilisable: "
            f"{', '.join(sorted(unusable_engines))}",
        )

    degraded = [name for name, state in engines.items() if state.degraded_by]
    if degraded:
        return (
            PageStatus.DEGRADED,
            f"entrées optionnelles manquantes sur: {', '.join(sorted(degraded))}",
        )

    worst = min(
        (families[name].freshness for name in critical),
        key=lambda f: ["LIVE", "RECENT", "DELAYED", "STALE", "UNAVAILABLE"].index(f.value),
        default=Freshness.UNAVAILABLE,
    )
    if worst is Freshness.LIVE:
        return PageStatus.LIVE, "toutes les entrées critiques sont dans leur cadence"
    return PageStatus.RECENT, "entrées critiques récentes mais pas instantanées"

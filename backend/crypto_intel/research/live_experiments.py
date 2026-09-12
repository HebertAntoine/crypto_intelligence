"""Claims registered for prospective test, and how long until they can answer.

Everything else in this project is retrospective. A hypothesis is formed after
seeing the data it is tested on, and no amount of purging, embargoing or
cross-validation fully removes that. The only test without that problem is one
declared before the data exists.

So a claim can be registered here with its rule, its horizon and the number of
independent observations it needs. From that moment it accumulates evidence it
cannot influence. The registry reports what has accrued and, more usefully,
what has not: a claim needing 60 independent 30-day observations at ten per
year will not be answerable for six years, and saying so now is more honest
than checking it hopefully every month.

Nothing here places or suggests an order. An experiment records what a rule
would have said and what happened next.
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import numpy as np

from ..logging_setup import get_logger

log = get_logger("research.live")

REGISTRY_PATH = pathlib.Path("data/research/live_experiments.json")


class MaturityState(StrEnum):
    JUST_REGISTERED = "JUST_REGISTERED"
    ACCUMULATING = "ACCUMULATING"
    NEARLY_MATURE = "NEARLY_MATURE"
    MATURE = "MATURE"
    ABANDONED = "ABANDONED"


@dataclass(slots=True)
class LiveExperiment:
    id: str
    claim: str
    hypothesis_key: str = ""
    horizon_days: int = 30
    expected_effect_pct: float = 0.0
    expected_sign: int = 0
    required_observations: int = 0
    expected_events_per_year: float = 0.0
    registered_at: str = ""
    observations: list[dict[str, Any]] = field(default_factory=list)
    state: str = MaturityState.JUST_REGISTERED
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "claim": self.claim,
            "hypothesis_key": self.hypothesis_key,
            "horizon_days": self.horizon_days,
            "expected_effect_pct": self.expected_effect_pct,
            "expected_sign": self.expected_sign,
            "required_observations": self.required_observations,
            "expected_events_per_year": self.expected_events_per_year,
            "registered_at": self.registered_at,
            "observations": self.observations,
            "state": self.state, "note": self.note,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LiveExperiment:
        return cls(**{k: v for k, v in data.items() if k in set(cls.__slots__)})


def assess_maturity(experiment: LiveExperiment) -> dict[str, Any]:
    """What this experiment can and cannot yet say."""
    settled = [o for o in experiment.observations if o.get("outcome_pct") is not None]
    n = len(settled)
    required = max(experiment.required_observations, 1)
    progress = n / required

    registered = experiment.registered_at
    days_live = 0.0
    if registered:
        try:
            start = datetime.fromisoformat(registered)
            days_live = (datetime.now(UTC) - start).total_seconds() / 86400
        except ValueError:
            days_live = 0.0

    rate = experiment.expected_events_per_year
    remaining_years = (
        (required - n) / rate if rate > 0 and n < required else 0.0
    )

    if n == 0:
        state = MaturityState.JUST_REGISTERED
    elif progress >= 1.0:
        state = MaturityState.MATURE
    elif progress >= 0.75:
        state = MaturityState.NEARLY_MATURE
    else:
        state = MaturityState.ACCUMULATING

    payload: dict[str, Any] = {
        "id": experiment.id,
        "state": state.value,
        "observations_settled": n,
        "observations_required": required,
        "progress_pct": round(progress * 100, 1),
        "days_live": round(days_live, 1),
        "estimated_years_remaining": round(remaining_years, 1),
        "can_conclude": state is MaturityState.MATURE,
    }

    if n >= 5:
        outcomes = [float(o["outcome_pct"]) for o in settled]
        observed = float(np.mean(outcomes))
        payload["observed_mean_pct"] = round(observed, 4)
        payload["observed_sd_pct"] = round(float(np.std(outcomes, ddof=1)), 4)
        if experiment.expected_sign:
            payload["sign_matches_claim"] = bool(
                np.sign(observed) == experiment.expected_sign
            )
        payload["interim_note"] = (
            f"{n} settled observations show a mean of {observed:+.2f}%. This is "
            "an interim reading, not a conclusion: stopping to look at an "
            "experiment before it matures is how prospective tests are turned "
            "back into retrospective ones."
        )

    payload["note"] = (
        f"{n} of {required} observations. "
        + (
            "Mature: the experiment can be concluded."
            if payload["can_conclude"] else
            f"About {remaining_years:.1f} more years at the expected rate of "
            f"{rate:.1f} events per year."
            if rate > 0 else
            "No event rate was estimated, so no completion date can be given."
        )
    )
    return payload


class LiveExperimentRegistry:
    def __init__(self, path: pathlib.Path | None = None) -> None:
        self.path = path or REGISTRY_PATH
        self._experiments: dict[str, LiveExperiment] = {}
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("live_registry_unreadable", error=str(exc))
            return
        for item in raw.get("experiments", []):
            experiment = LiveExperiment.from_dict(item)
            self._experiments[experiment.id] = experiment

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({
            "saved_at": datetime.now(UTC).isoformat(),
            "count": len(self._experiments),
            "experiments": [e.to_dict() for e in self._experiments.values()],
        }, indent=2, default=str))

    def register(self, experiment: LiveExperiment) -> LiveExperiment:
        """Register once. Re-registering never resets the clock or the data."""
        existing = self._experiments.get(experiment.id)
        if existing is not None:
            return existing
        experiment.registered_at = (
            experiment.registered_at or datetime.now(UTC).isoformat()
        )
        self._experiments[experiment.id] = experiment
        return experiment

    def record_observation(
        self,
        experiment_id: str,
        occurred_at: str,
        signal_value: float | None = None,
        outcome_pct: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        experiment = self._experiments.get(experiment_id)
        if experiment is None:
            raise KeyError(f"{experiment_id} is not registered")
        for observation in experiment.observations:
            same_time = observation.get("occurred_at") == occurred_at
            same_identity = (
                metadata is None or observation.get("metadata") == metadata
            )
            if same_time and same_identity:
                if outcome_pct is not None:
                    observation["outcome_pct"] = outcome_pct
                    observation["settled_at"] = datetime.now(UTC).isoformat()
                return
        experiment.observations.append({
            "occurred_at": occurred_at,
            "signal_value": signal_value,
            "outcome_pct": outcome_pct,
            "metadata": metadata or {},
            "recorded_at": datetime.now(UTC).isoformat(),
            "settled_at": (
                datetime.now(UTC).isoformat() if outcome_pct is not None else None
            ),
        })

    def all(self) -> list[LiveExperiment]:
        return sorted(self._experiments.values(), key=lambda e: e.id)

    def report(self) -> dict[str, Any]:
        assessments = [assess_maturity(e) for e in self.all()]
        states: dict[str, int] = {}
        for assessment in assessments:
            states[assessment["state"]] = states.get(assessment["state"], 0) + 1
        mature = [a for a in assessments if a["can_conclude"]]
        soonest = min(
            (a["estimated_years_remaining"] for a in assessments
             if not a["can_conclude"] and a["estimated_years_remaining"] > 0),
            default=None,
        )
        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "n_experiments": len(assessments),
            "by_state": states,
            "n_mature": len(mature),
            "soonest_conclusion_years": soonest,
            "experiments": assessments,
            "note": (
                "No experiment here places an order or produces a recommendation. "
                "Each records what a pre-declared rule would have said and what "
                "followed. "
                + (
                    f"None is mature; the earliest could conclude in about "
                    f"{soonest:.1f} years."
                    if not mature and soonest is not None else
                    f"{len(mature)} of {len(assessments)} can be concluded."
                    if mature else
                    "None is mature and no completion date can be estimated."
                )
            ),
        }


_LIVE: LiveExperimentRegistry | None = None


def get_live_registry(path: pathlib.Path | None = None) -> LiveExperimentRegistry:
    global _LIVE
    if _LIVE is None or path is not None:
        _LIVE = LiveExperimentRegistry(path)
    return _LIVE

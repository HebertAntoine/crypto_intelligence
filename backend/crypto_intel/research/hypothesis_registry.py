"""A hypothesis, once tested, is frozen.

The failure this prevents is the most human one in research: a hypothesis is
declared, tested, comes back at p = 0.07, and the threshold quietly moves from
85 to 80 until it comes back at p = 0.04. Nothing is falsified, no rule is
broken, and the result is worthless.

So a declaration is hashed the moment it is written down. Once it carries a
result, any change to that hash is refused. The variant is not a correction of
the old hypothesis - it is a new hypothesis, with its own identity, its own
pre-registration date, and its own place in the multiple-testing count. That
last part is the point: the cost of trying a second threshold is that both
thresholds are counted.

The registry is stored as JSON so it survives restarts and lands in git, where
the history of what was declared when is visible to anyone who looks.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from ..logging_setup import get_logger

log = get_logger("research.hypotheses")

REGISTRY_PATH = pathlib.Path("data/research/hypothesis_registry.json")
REGISTRY_VERSION = "lot6b.1"

# Fields that define what is being claimed. Changing any of them changes the
# hypothesis. Everything else - prose, notes, tags - can be edited freely.
FROZEN_FIELDS = (
    "statement", "family", "asset", "feature", "rule",
    "threshold", "horizon_days", "target", "expected_sign",
)


class HypothesisStatus(StrEnum):
    PREREGISTERED = "PREREGISTERED"
    TESTED = "TESTED"
    SUPPORTED = "SUPPORTED"
    INCONCLUSIVE = "INCONCLUSIVE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    REJECTED = "REJECTED"
    UNSTABLE = "UNSTABLE"


TERMINAL_STATUSES = frozenset({
    HypothesisStatus.SUPPORTED, HypothesisStatus.INCONCLUSIVE,
    HypothesisStatus.INSUFFICIENT_DATA, HypothesisStatus.REJECTED,
    HypothesisStatus.UNSTABLE,
})


class FrozenHypothesisError(ValueError):
    """Raised when a tested hypothesis is edited instead of superseded."""


@dataclass(slots=True)
class Hypothesis:
    id: str
    statement: str
    family: str
    expected_sign: int
    asset: str | None = None
    feature: str | None = None
    rule: str | None = None
    threshold: float | None = None
    horizon_days: int | None = None
    target: str = "forward_return_pct"
    version: int = 1
    status: str = HypothesisStatus.PREREGISTERED
    preregistered_at: str = ""
    tested_at: str | None = None
    supersedes: str | None = None
    superseded_by: str | None = None
    definition_hash: str = ""
    result: dict[str, Any] | None = None
    notes: str = ""
    tags: list[str] = field(default_factory=list)

    def frozen_definition(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in FROZEN_FIELDS}

    def compute_hash(self) -> str:
        payload = json.dumps(self.frozen_definition(), sort_keys=True, default=str)
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    @property
    def key(self) -> str:
        """Identity including version: what the multiple-testing count sees."""
        return f"{self.id}@v{self.version}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "key": self.key, "statement": self.statement,
            "family": self.family, "asset": self.asset, "feature": self.feature,
            "rule": self.rule, "threshold": self.threshold,
            "horizon_days": self.horizon_days, "target": self.target,
            "expected_sign": self.expected_sign, "version": self.version,
            "status": self.status, "preregistered_at": self.preregistered_at,
            "tested_at": self.tested_at, "supersedes": self.supersedes,
            "superseded_by": self.superseded_by,
            "definition_hash": self.definition_hash, "result": self.result,
            "notes": self.notes, "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Hypothesis:
        known = set(cls.__slots__)
        return cls(**{k: v for k, v in data.items() if k in known})


class HypothesisRegistry:
    """Append-mostly store: declarations are added, results are attached."""

    def __init__(self, path: pathlib.Path | None = None) -> None:
        self.path = path or REGISTRY_PATH
        self._entries: dict[str, Hypothesis] = {}
        self.load()

    # --- persistence ------------------------------------------------------

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("hypothesis_registry_unreadable", error=str(exc))
            return
        for item in raw.get("hypotheses", []):
            entry = Hypothesis.from_dict(item)
            self._entries[entry.key] = entry

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "registry_version": REGISTRY_VERSION,
            "saved_at": datetime.now(UTC).isoformat(),
            "count": len(self._entries),
            "hypotheses": [e.to_dict() for e in self.sorted_entries()],
        }
        self.path.write_text(json.dumps(payload, indent=2, default=str))

    # --- declaration ------------------------------------------------------

    def preregister(self, hypothesis: Hypothesis) -> Hypothesis:
        """Declare a hypothesis, or return the identical existing one.

        Re-declaring the same definition is a no-op, so a study module can call
        this on every run. Re-declaring a *different* definition under an id
        that already carries a result is refused.
        """
        hypothesis.definition_hash = hypothesis.compute_hash()
        existing = self.latest(hypothesis.id)

        if existing is None:
            hypothesis.version = 1
            hypothesis.preregistered_at = (
                hypothesis.preregistered_at or datetime.now(UTC).isoformat()
            )
            self._entries[hypothesis.key] = hypothesis
            return hypothesis

        if existing.definition_hash == hypothesis.definition_hash:
            return existing

        if existing.status != HypothesisStatus.PREREGISTERED:
            raise FrozenHypothesisError(
                f"{existing.key} has status {existing.status} and cannot be "
                f"redefined. Its frozen definition hash is "
                f"{existing.definition_hash}, the new one is "
                f"{hypothesis.definition_hash}. Register the variant with "
                f"supersede() so both versions are counted."
            )

        # Never tested: an untested declaration may still be corrected.
        hypothesis.version = existing.version
        hypothesis.preregistered_at = datetime.now(UTC).isoformat()
        self._entries[hypothesis.key] = hypothesis
        return hypothesis

    def supersede(self, hypothesis: Hypothesis) -> Hypothesis:
        """Register a variant of a tested hypothesis as a new version.

        Both versions stay in the registry and both are counted as tests. That
        is the price of the second look, and it is paid explicitly.
        """
        previous = self.latest(hypothesis.id)
        if previous is None:
            return self.preregister(hypothesis)

        hypothesis.version = previous.version + 1
        hypothesis.supersedes = previous.key
        hypothesis.status = HypothesisStatus.PREREGISTERED
        hypothesis.result = None
        hypothesis.tested_at = None
        hypothesis.preregistered_at = datetime.now(UTC).isoformat()
        hypothesis.definition_hash = hypothesis.compute_hash()
        previous.superseded_by = hypothesis.key
        self._entries[hypothesis.key] = hypothesis
        return hypothesis

    # --- results ----------------------------------------------------------

    def record_result(
        self, key: str, status: str, result: dict[str, Any]
    ) -> Hypothesis:
        entry = self._entries.get(key) or self.latest(key)
        if entry is None:
            raise KeyError(f"{key} was never pre-registered; refusing to record")
        if entry.definition_hash != entry.compute_hash():
            raise FrozenHypothesisError(
                f"{entry.key} was edited after registration "
                f"({entry.definition_hash} -> {entry.compute_hash()})"
            )
        entry.status = status
        entry.result = result
        entry.tested_at = datetime.now(UTC).isoformat()
        return entry

    # --- queries ----------------------------------------------------------

    def latest(self, hypothesis_id: str) -> Hypothesis | None:
        if "@v" in hypothesis_id:
            return self._entries.get(hypothesis_id)
        versions = [e for e in self._entries.values() if e.id == hypothesis_id]
        return max(versions, key=lambda e: e.version) if versions else None

    def get(self, key: str) -> Hypothesis | None:
        return self._entries.get(key)

    def sorted_entries(self) -> list[Hypothesis]:
        return sorted(self._entries.values(), key=lambda e: (e.id, e.version))

    def all(self) -> list[Hypothesis]:
        return self.sorted_entries()

    def by_status(self, status: str) -> list[Hypothesis]:
        return [e for e in self.sorted_entries() if e.status == status]

    def by_family(self, family: str) -> list[Hypothesis]:
        return [e for e in self.sorted_entries() if e.family == family]

    def active(self) -> list[Hypothesis]:
        """Current versions only: superseded declarations are excluded."""
        return [e for e in self.sorted_entries() if e.superseded_by is None]

    def tested_count(self) -> int:
        """Every version ever tested. This is the multiple-testing denominator."""
        return sum(1 for e in self._entries.values() if e.tested_at is not None)

    def summary(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for entry in self._entries.values():
            counts[entry.status] = counts.get(entry.status, 0) + 1
        families: dict[str, int] = {}
        for entry in self._entries.values():
            families[entry.family] = families.get(entry.family, 0) + 1
        superseded = [
            {"from": e.supersedes, "to": e.key}
            for e in self._entries.values() if e.supersedes
        ]
        return {
            "registry_version": REGISTRY_VERSION,
            "total_declarations": len(self._entries),
            "active_hypotheses": len(self.active()),
            "tested_ever": self.tested_count(),
            "by_status": counts,
            "by_family": families,
            "superseded_chains": superseded,
            "note": (
                "tested_ever counts every version that was run, including "
                "superseded ones. It is the correct denominator for multiple "
                "testing: trying a second threshold costs a second test."
            ),
        }


_REGISTRY: HypothesisRegistry | None = None


def get_registry(path: pathlib.Path | None = None) -> HypothesisRegistry:
    global _REGISTRY
    if _REGISTRY is None or path is not None:
        _REGISTRY = HypothesisRegistry(path)
    return _REGISTRY


def reset_registry() -> None:
    """Test hook: drop the process-wide instance."""
    global _REGISTRY
    _REGISTRY = None

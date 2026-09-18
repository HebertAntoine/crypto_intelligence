"""The pass that keeps the market alive between the two full cycles.

A full refresh at 07:00 and 19:00 leaves a price, an open-interest reading or a
funding rate able to sit for almost twelve hours while still being the newest
thing the app has. This pass asks only the sources whose own policy says they
are due, recomputes the families they touch, and republishes through the same
atomic export the full cycle uses.

It deliberately does not call the economic calendars, the legislative feeds or
the ETF file: those publish on their own schedule and asking them every quarter
of an hour would spend rate limit for nothing.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .source_policy import (
    RunType,
    SourceRefreshPolicy,
    SourceState,
    record_attempt,
    record_failure,
    record_success,
    which_sources_are_due,
)
from .source_state_store import load, save

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def fingerprint(payload: Any) -> str:
    """A short digest used only to notice that nothing changed."""

    try:
        text = json.dumps(payload, sort_keys=True, default=str)
    except (TypeError, ValueError):
        text = repr(payload)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


@dataclass(slots=True)
class RefreshOutcome:
    run_id: str
    run_type: str
    trigger: str
    due: list[str] = field(default_factory=list)
    succeeded: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    skipped_open_circuit: list[str] = field(default_factory=list)
    dirty_families: set[str] = field(default_factory=set)
    exported: bool = False
    started_at: str = ""
    completed_at: str = ""

    @property
    def status(self) -> str:
        if not self.exported and self.dirty_families:
            return "FAILED"
        if self.failed:
            return "DEGRADED_SUCCESS"
        return "SUCCESS"

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "run_type": self.run_type,
            "trigger": self.trigger,
            "status": self.status,
            "due": self.due,
            "succeeded": self.succeeded,
            "failed": self.failed,
            "skipped_open_circuit": self.skipped_open_circuit,
            "dirty_families": sorted(self.dirty_families),
            "exported": self.exported,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


def new_run_id(now: datetime, run_type: RunType) -> str:
    return f"run_{now.strftime('%Y%m%dT%H%M%SZ')}_{run_type.value.lower()}"


def run_light_refresh(
    *,
    now: datetime | None = None,
    collector=None,
    exporter=None,
    state_path: Path | None = None,
    trigger: str = "SYSTEMD_LIGHT",
) -> RefreshOutcome:
    """Collect what is due, recompute what that touched, republish.

    ``collector`` and ``exporter`` are injected so the behaviour can be driven
    through failures in tests without reaching a network or a filesystem.
    """

    reference = now or datetime.now(UTC)
    states = load(state_path)
    outcome = RefreshOutcome(
        run_id=new_run_id(reference, RunType.LIGHT),
        run_type=RunType.LIGHT.value,
        trigger=trigger,
        started_at=reference.isoformat(),
    )

    due = which_sources_are_due(states, reference, fast_only=True)
    outcome.due = [item.source_id for item in due]

    for policy in due:
        state = states.setdefault(
            policy.source_id, SourceState(source_id=policy.source_id)
        )
        record_attempt(state, reference)
        try:
            payload = (collector or _collect)(policy)
        except Exception as error:
            record_failure(state, reference, error_kind=_classify(error))
            outcome.failed.append(policy.source_id)
            continue
        record_success(state, reference, fingerprint=fingerprint(payload))
        outcome.succeeded.append(policy.source_id)
        outcome.dirty_families.add(policy.family)

    # Sources whose breaker is open were never in `due`; naming them keeps the
    # log honest about why they were not tried.
    for source_id, state in states.items():
        if state.circuit == "OPEN" and source_id not in outcome.due:
            outcome.skipped_open_circuit.append(source_id)

    if outcome.dirty_families:
        # Nothing changed means nothing to republish: an export with identical
        # content would still rewrite every file and move the run_id forward.
        outcome.exported = (exporter or _export)(outcome.run_id)

    save(states, state_path)
    outcome.completed_at = datetime.now(UTC).isoformat()
    return outcome


def _classify(error: Exception) -> str:
    """Map an exception onto the kinds the retry policy understands."""

    name = type(error).__name__.lower()
    text = str(error).lower()
    if "timeout" in name or "timeout" in text:
        return "TIMEOUT"
    if "auth" in text or "401" in text or "403" in text:
        return "AUTH"
    if "429" in text or "rate limit" in text:
        return "HTTP_429"
    if "connect" in name or "connection" in text or "dns" in text:
        return "CONNECTION"
    if "json" in name or "decode" in name:
        return "INVALID_PAYLOAD"
    return "HTTP_5XX"


def _collect(policy: SourceRefreshPolicy) -> Any:
    """Real collection, through the CLI the full pass already uses."""

    result = subprocess.run(
        [
            str(PROJECT_ROOT / ".venv" / "bin" / "python"),
            "-m",
            "crypto_intel.cli",
            "collect",
        ],
        cwd=PROJECT_ROOT,
        env={"PYTHONPATH": str(PROJECT_ROOT / "backend")},
        capture_output=True,
        text=True,
        timeout=policy.timeout_s * 30,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"collect failed: {result.stderr[-200:]}")
    return result.stdout


def _export(run_id: str) -> bool:
    result = subprocess.run(
        [
            str(PROJECT_ROOT / ".venv" / "bin" / "python"),
            str(PROJECT_ROOT / "scripts" / "export_flutter_static_api.py"),
            "--in-process",
            "--run-id",
            run_id,
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0

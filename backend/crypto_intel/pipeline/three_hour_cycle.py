"""Durable execution contract for the three-hour server cycle.

The scheduler owns *when* a cycle starts and the domain jobs own *how* data is
collected or analysed.  This module only owns the durable workflow contract:

* one execution at a time in this process and on this host;
* one report per three-hour UTC bucket;
* a persisted status before and after every step;
* restart from the first unfinished/failed step;
* no successful report when a step failed or degraded.

The report is stored in the existing snapshot table.  That gives the workflow
crash-safe, idempotent persistence without adding a second job database or a
schema migration just for orchestration state.
"""

from __future__ import annotations

import asyncio
import errno
import fcntl
import os
from collections.abc import Awaitable, Callable, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from ..history import snapshots
from ..logging_setup import get_logger

log = get_logger("pipeline.three_hour_cycle")

CYCLE_REPORT_KIND = "server_cycle_3h"
CYCLE_MINUTES = 180
snapshots.CADENCES.setdefault(CYCLE_REPORT_KIND, CYCLE_MINUTES)

# ``APScheduler(max_instances=1)`` protects one scheduler and the asyncio lock
# below protects every runner instance in one process.  Production can still
# have several API workers, however, so a non-blocking host lock closes the
# remaining same-host race without holding a database transaction open during
# network calls.  Deployments on several hosts must provide their own shared
# scheduler/leader election; the status payload reports the scope honestly.
_PROCESS_LOCK = asyncio.Lock()
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_HOST_LOCK_PATH = _PROJECT_ROOT / "data" / ".three_hour_cycle.lock"


class StepStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"


@dataclass(slots=True)
class StepResult:
    """Truthful result returned by one workflow step."""

    status: StepStatus = StepStatus.SUCCESS
    detail: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    @classmethod
    def success(cls, detail: str = "", **data: Any) -> StepResult:
        return cls(status=StepStatus.SUCCESS, detail=detail, data=data)

    @classmethod
    def degraded(
        cls, detail: str, *, errors: Sequence[str] = (), **data: Any
    ) -> StepResult:
        return cls(
            status=StepStatus.DEGRADED,
            detail=detail,
            data=data,
            errors=[str(item) for item in errors],
        )


@dataclass(slots=True)
class CycleContext:
    """Ephemeral values shared by the steps of one process execution."""

    now: datetime
    trigger: str
    cycle_id: str
    shared: dict[str, Any] = field(default_factory=dict)


StepHandler = Callable[[CycleContext], Awaitable[StepResult | dict[str, Any] | None]]


@dataclass(slots=True, frozen=True)
class CycleStep:
    number: int
    key: str
    label: str
    handler: StepHandler


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def cycle_id_for(when: datetime) -> str:
    """Stable identity of a UTC three-hour bucket."""

    reference = _utc(when)
    hour = reference.hour - reference.hour % 3
    return reference.replace(hour=hour, minute=0, second=0, microsecond=0).strftime(
        "%Y%m%dT%H%MZ"
    )


def _step_payload(step: CycleStep) -> dict[str, Any]:
    return {
        "number": step.number,
        "key": step.key,
        "label": step.label,
        "status": StepStatus.PENDING.value,
        "attempts": 0,
        "started_at": None,
        "finished_at": None,
        "detail": "",
        "data": {},
        "errors": [],
    }


def _new_report(
    steps: Sequence[CycleStep], *, when: datetime, trigger: str
) -> dict[str, Any]:
    stamp = _utc(when).isoformat()
    return {
        "schema_version": 2,
        "cycle_id": cycle_id_for(when),
        "bucket": snapshots.bucket_for(CYCLE_REPORT_KIND, when),
        "trigger": trigger,
        "status": StepStatus.RUNNING.value,
        "attempts": 0,
        "started_at": stamp,
        "last_started_at": stamp,
        "updated_at": stamp,
        "completed_at": None,
        "last_successful_at": None,
        "steps": [_step_payload(step) for step in steps],
        "errors": [],
        "failure_history": [],
        "lock_scope": "PROCESS_AND_HOST",
    }


def load_cycle_report(when: datetime | None = None) -> dict[str, Any] | None:
    """Load the report for exactly this bucket, never a neighbouring cycle."""

    reference = _utc(when or datetime.now(UTC))
    expected = cycle_id_for(reference)
    for row in snapshots.load_snapshots(CYCLE_REPORT_KIND, limit=4):
        payload = row.get("payload") or {}
        if payload.get("cycle_id") == expected:
            return payload
    return None


def latest_cycle_report() -> dict[str, Any] | None:
    rows = snapshots.load_snapshots(CYCLE_REPORT_KIND, limit=1)
    return (rows[0].get("payload") or None) if rows else None


def _persist(report: dict[str, Any], when: datetime) -> None:
    report["updated_at"] = datetime.now(UTC).isoformat()
    snapshots.save_snapshot(CYCLE_REPORT_KIND, None, report, when=when)


@contextmanager
def _host_lock(path: Path = _HOST_LOCK_PATH) -> Any:
    """Acquire the same-host process lock without blocking the event loop.

    ``flock`` is released by the kernel when a worker dies, which is exactly
    the crash behaviour a durable scheduler needs.  The yielded boolean keeps
    lock contention distinct from an I/O/configuration error: contention is a
    normal skipped run, whereas inability to create the lock fails closed.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    acquired = False
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except OSError as exc:
            if exc.errno not in {errno.EACCES, errno.EAGAIN}:
                raise
        yield acquired
    finally:
        if acquired:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _validate_steps(steps: Sequence[CycleStep]) -> None:
    numbers = [step.number for step in steps]
    if numbers != list(range(1, 14)):
        raise ValueError("the three-hour workflow requires exactly steps 1 through 13")
    keys = [step.key for step in steps]
    if len(keys) != len(set(keys)):
        raise ValueError("cycle step keys must be unique")


def _normalise_result(value: StepResult | dict[str, Any] | None) -> StepResult:
    if value is None:
        return StepResult.success()
    if isinstance(value, StepResult):
        return value
    return StepResult(status=StepStatus.SUCCESS, data=value)


def _resume_index(report: dict[str, Any]) -> int | None:
    """Return first step that must be replayed; completed suffix is invalidated.

    A later step may have succeeded with stale inputs after an earlier degraded
    pass.  On retry, replaying the suffix is the only safe interpretation of
    "resume": prior successful prerequisites remain durable, dependent output
    is recomputed.
    """

    for index, step in enumerate(report.get("steps") or []):
        if step.get("status") != StepStatus.SUCCESS.value:
            return index
    return None


def _report_matches_steps(
    report: dict[str, Any], definitions: Sequence[CycleStep]
) -> bool:
    persisted = report.get("steps") or []
    return len(persisted) == len(definitions) and all(
        item.get("number") == definition.number
        and item.get("key") == definition.key
        for item, definition in zip(persisted, definitions, strict=True)
    )


class DurableCycleRunner:
    """Execute a 13-step workflow with bucket idempotence and restart safety."""

    def __init__(self, *, host_lock_path: Path | None = None) -> None:
        # Shared by all instances, not only by the scheduler singleton.  This
        # matters in tests, manual invocations and application code that builds
        # a second runner accidentally.
        self._lock = _PROCESS_LOCK
        self._host_lock_path = host_lock_path or _HOST_LOCK_PATH

    @property
    def locked(self) -> bool:
        return self._lock.locked()

    async def run(
        self,
        steps: Sequence[CycleStep],
        *,
        when: datetime | None = None,
        trigger: str = "CRON_3H",
    ) -> dict[str, Any]:
        _validate_steps(steps)
        reference = _utc(when or datetime.now(UTC))
        cycle_id = cycle_id_for(reference)

        if self._lock.locked():
            log.warning("three_hour_cycle_skipped", cycle_id=cycle_id, reason="locked")
            return {
                "cycle_id": cycle_id,
                "trigger": trigger,
                "status": "SKIPPED_LOCKED",
                "detail": "another three-hour cycle is still running",
                "lock_scope": "PROCESS",
            }

        async with self._lock:
            with _host_lock(self._host_lock_path) as host_lock_acquired:
                if not host_lock_acquired:
                    log.warning(
                        "three_hour_cycle_skipped",
                        cycle_id=cycle_id,
                        reason="host_locked",
                    )
                    return {
                        "cycle_id": cycle_id,
                        "trigger": trigger,
                        "status": "SKIPPED_LOCKED",
                        "detail": "another host process is running this cycle",
                        "lock_scope": "HOST",
                    }
                return await self._run_locked(
                    steps, reference=reference, trigger=trigger, cycle_id=cycle_id
                )

    async def _run_locked(
        self,
        steps: Sequence[CycleStep],
        *,
        reference: datetime,
        trigger: str,
        cycle_id: str,
    ) -> dict[str, Any]:
        report = load_cycle_report(reference)
        if report is not None and not _report_matches_steps(report, steps):
            # A deployment may change the workflow while the current bucket is
            # unfinished.  Treating an empty/short report as completed would
            # be a false success; restarting all idempotent steps is safer.
            previous_status = str(report.get("status") or "UNKNOWN")
            report = _new_report(steps, when=reference, trigger=trigger)
            report["failure_history"].append(
                {
                    "at": datetime.now(UTC).isoformat(),
                    "cycle_attempt": 0,
                    "step": "workflow_contract",
                    "step_attempt": 0,
                    "status": StepStatus.FAILED.value,
                    "detail": "persisted step contract did not match the deployed workflow",
                    "errors": [f"previous_status={previous_status}"],
                }
            )
        if report is None:
            report = _new_report(steps, when=reference, trigger=trigger)
        elif report.get("status") == StepStatus.SUCCESS.value:
            # A restart or duplicate scheduler fire inside the same bucket
            # returns the durable result and performs no external call.
            return {**report, "idempotent_replay": True}
        else:
            report["trigger"] = trigger

        # Additive compatibility for an unfinished schema-v1 report that a
        # newly deployed worker may have to resume in the same UTC bucket.
        report["schema_version"] = 2
        report.setdefault("failure_history", [])
        report.setdefault("last_successful_at", None)
        report.setdefault("lock_scope", "PROCESS_AND_HOST")
        report["attempts"] = int(report.get("attempts") or 0) + 1
        report["status"] = StepStatus.RUNNING.value
        report["last_started_at"] = datetime.now(UTC).isoformat()
        report["completed_at"] = None
        report["errors"] = []

        start = _resume_index(report)
        if start is None:
            # A previous process may have completed every step but died
            # before writing the aggregate status.
            completed = datetime.now(UTC).isoformat()
            report["status"] = StepStatus.SUCCESS.value
            report["completed_at"] = completed
            report["last_successful_at"] = completed
            _persist(report, reference)
            return report

        for stale in report["steps"][start:]:
            stale.update(
                status=StepStatus.PENDING.value,
                started_at=None,
                finished_at=None,
                detail="",
                data={},
                errors=[],
            )

        _persist(report, reference)
        context = CycleContext(now=reference, trigger=trigger, cycle_id=cycle_id)
        # Successful prerequisite outputs are small JSON values on purpose.
        # Hydrating them here lets a restarted process continue at step N
        # without rerunning external calls from steps 1..N-1.
        for completed_step in report["steps"][:start]:
            data = completed_step.get("data") or {}
            if isinstance(data, dict):
                context.shared.update(data)
        hard_failure = False

        for index in range(start, len(steps)):
            definition = steps[index]
            state = report["steps"][index]
            state["status"] = StepStatus.RUNNING.value
            state["attempts"] = int(state.get("attempts") or 0) + 1
            state["started_at"] = datetime.now(UTC).isoformat()
            _persist(report, reference)
            log.info(
                "three_hour_cycle_step_started",
                cycle_id=cycle_id,
                step=definition.key,
                number=definition.number,
                attempt=state["attempts"],
            )

            try:
                result = _normalise_result(await definition.handler(context))
            except Exception as exc:
                result = StepResult(
                    status=StepStatus.FAILED,
                    detail=str(exc)[:500],
                    errors=[f"{type(exc).__name__}: {exc}"[:1000]],
                )
                log.exception(
                    "three_hour_cycle_step_failed",
                    cycle_id=cycle_id,
                    step=definition.key,
                )

            state["status"] = result.status.value
            state["detail"] = result.detail[:1000]
            state["data"] = result.data
            state["errors"] = result.errors
            state["finished_at"] = datetime.now(UTC).isoformat()
            report["errors"].extend(
                f"{definition.key}: {error}" for error in result.errors
            )
            if result.status in {StepStatus.DEGRADED, StepStatus.FAILED}:
                report["failure_history"].append(
                    {
                        "at": state["finished_at"],
                        "cycle_attempt": report["attempts"],
                        "step": definition.key,
                        "step_attempt": state["attempts"],
                        "status": result.status.value,
                        "detail": result.detail[:1000],
                        "errors": result.errors,
                    }
                )
                # Bound the row while retaining enough history to diagnose
                # repeated failures across many retries in one bucket.
                report["failure_history"] = report["failure_history"][-100:]
            _persist(report, reference)
            context.shared.update(result.data)
            log.info(
                "three_hour_cycle_step_finished",
                cycle_id=cycle_id,
                step=definition.key,
                number=definition.number,
                status=result.status.value,
                attempt=state["attempts"],
            )

            if result.status is StepStatus.FAILED:
                hard_failure = True
                # Dependent steps remain visibly PENDING.  A later retry in
                # the same bucket starts here and then recomputes the suffix.
                break

        statuses = [item["status"] for item in report["steps"]]
        if hard_failure or StepStatus.FAILED.value in statuses:
            report["status"] = StepStatus.FAILED.value
        elif StepStatus.DEGRADED.value in statuses:
            report["status"] = StepStatus.DEGRADED.value
        elif all(status == StepStatus.SUCCESS.value for status in statuses):
            report["status"] = StepStatus.SUCCESS.value
        else:
            report["status"] = StepStatus.RUNNING.value

        if report["status"] in {
            StepStatus.SUCCESS.value,
            StepStatus.DEGRADED.value,
            StepStatus.FAILED.value,
        }:
            report["completed_at"] = datetime.now(UTC).isoformat()
        if report["status"] == StepStatus.SUCCESS.value:
            report["last_successful_at"] = report["completed_at"]
        _persist(report, reference)
        log.info(
            "three_hour_cycle_finished",
            cycle_id=cycle_id,
            status=report["status"],
            attempts=report["attempts"],
        )
        return report

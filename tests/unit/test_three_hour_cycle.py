"""Durability contract of the UTC three-hour, thirteen-step workflow."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import delete

from crypto_intel.core.enums import Asset
from crypto_intel.db.base import MarketSnapshotRow
from crypto_intel.db.session import session_scope
from crypto_intel.pipeline.three_hour_cycle import (
    CYCLE_REPORT_KIND,
    CycleContext,
    CycleStep,
    DurableCycleRunner,
    StepResult,
    StepStatus,
    _host_lock,
    cycle_id_for,
    latest_cycle_report,
    load_cycle_report,
)

NOW = datetime(2026, 10, 30, 12, 17, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _clear_cycle_reports() -> Any:
    with session_scope() as session:
        session.execute(
            delete(MarketSnapshotRow).where(MarketSnapshotRow.kind == CYCLE_REPORT_KIND)
        )
    yield
    with session_scope() as session:
        session.execute(
            delete(MarketSnapshotRow).where(MarketSnapshotRow.kind == CYCLE_REPORT_KIND)
        )


def _steps(handler: Any) -> tuple[CycleStep, ...]:
    return tuple(
        CycleStep(number, f"step_{number}", f"Step {number}", handler(number))
        for number in range(1, 14)
    )


def _runner(tmp_path: Path) -> DurableCycleRunner:
    return DurableCycleRunner(host_lock_path=tmp_path / "cycle.lock")


@pytest.mark.asyncio
async def test_success_is_persisted_per_step_and_same_bucket_is_idempotent(
    tmp_path: Path,
) -> None:
    calls: list[int] = []

    def handler(number: int) -> Any:
        async def run(context: CycleContext) -> StepResult:
            calls.append(number)
            if number == 1:
                persisted = load_cycle_report(context.now)
                assert persisted is not None
                assert persisted["steps"][0]["status"] == StepStatus.RUNNING.value
                assert persisted["steps"][1]["status"] == StepStatus.PENDING.value
            return StepResult.success(f"step {number}", **{f"value_{number}": number})

        return run

    runner = _runner(tmp_path)
    first = await runner.run(_steps(handler), when=NOW)

    assert first["status"] == StepStatus.SUCCESS.value
    assert first["cycle_id"] == cycle_id_for(NOW)
    assert first["schema_version"] == 2
    assert first["last_successful_at"] == first["completed_at"]
    assert [item["status"] for item in first["steps"]] == [
        StepStatus.SUCCESS.value
    ] * 13
    assert calls == list(range(1, 14))

    second = await runner.run(_steps(handler), when=NOW, trigger="DUPLICATE")

    assert second["idempotent_replay"] is True
    assert calls == list(range(1, 14))
    assert latest_cycle_report()["cycle_id"] == cycle_id_for(NOW)


@pytest.mark.asyncio
async def test_failed_step_resumes_from_first_unfinished_and_keeps_history(
    tmp_path: Path,
) -> None:
    calls: list[int] = []
    fourth_attempts = 0

    def handler(number: int) -> Any:
        async def run(_context: CycleContext) -> StepResult:
            nonlocal fourth_attempts
            calls.append(number)
            if number == 4:
                fourth_attempts += 1
                if fourth_attempts == 1:
                    raise TimeoutError("provider timeout")
            return StepResult.success(f"step {number}", shared_value=number)

        return run

    runner = _runner(tmp_path)
    failed = await runner.run(_steps(handler), when=NOW)

    assert failed["status"] == StepStatus.FAILED.value
    assert calls == [1, 2, 3, 4]
    assert [item["status"] for item in failed["steps"][:5]] == [
        StepStatus.SUCCESS.value,
        StepStatus.SUCCESS.value,
        StepStatus.SUCCESS.value,
        StepStatus.FAILED.value,
        StepStatus.PENDING.value,
    ]
    assert failed["failure_history"][0]["step"] == "step_4"
    assert failed["failure_history"][0]["status"] == StepStatus.FAILED.value

    resumed = await runner.run(_steps(handler), when=NOW, trigger="RESTART")

    assert resumed["status"] == StepStatus.SUCCESS.value
    assert calls == [1, 2, 3, 4, *range(4, 14)]
    assert [item["attempts"] for item in resumed["steps"][:5]] == [1, 1, 1, 2, 1]
    assert resumed["failure_history"][0]["step"] == "step_4"
    assert resumed["errors"] == []


@pytest.mark.asyncio
async def test_degraded_step_cannot_produce_a_successful_cycle(tmp_path: Path) -> None:
    def handler(number: int) -> Any:
        async def run(_context: CycleContext) -> StepResult:
            if number == 7:
                return StepResult.degraded(
                    "partial data", errors=["one source unavailable"]
                )
            return StepResult.success()

        return run

    report = await _runner(tmp_path).run(_steps(handler), when=NOW)

    assert report["status"] == StepStatus.DEGRADED.value
    assert report["steps"][6]["status"] == StepStatus.DEGRADED.value
    assert report["steps"][12]["status"] == StepStatus.SUCCESS.value
    assert report["failure_history"][0]["step"] == "step_7"


@pytest.mark.asyncio
async def test_concurrent_runner_instance_is_skipped(tmp_path: Path) -> None:
    entered = asyncio.Event()
    release = asyncio.Event()

    def handler(number: int) -> Any:
        async def run(_context: CycleContext) -> StepResult:
            if number == 1:
                entered.set()
                await release.wait()
            return StepResult.success()

        return run

    steps = _steps(handler)
    first_task = asyncio.create_task(_runner(tmp_path).run(steps, when=NOW))
    await entered.wait()

    skipped = await _runner(tmp_path).run(steps, when=NOW)
    assert skipped["status"] == "SKIPPED_LOCKED"
    assert skipped["lock_scope"] == "PROCESS"

    release.set()
    assert (await first_task)["status"] == StepStatus.SUCCESS.value


def test_host_lock_is_non_blocking_and_released(tmp_path: Path) -> None:
    path = tmp_path / "cycle.lock"
    with _host_lock(path) as first:
        assert first is True
        with _host_lock(path) as second:
            assert second is False
    with _host_lock(path) as after_release:
        assert after_release is True


@pytest.mark.asyncio
async def test_malformed_persisted_contract_restarts_instead_of_false_success(
    tmp_path: Path,
) -> None:
    from crypto_intel.history import snapshots

    snapshots.save_snapshot(
        CYCLE_REPORT_KIND,
        None,
        {
            "cycle_id": cycle_id_for(NOW),
            "status": StepStatus.RUNNING.value,
            "steps": [],
        },
        when=NOW,
    )
    calls: list[int] = []

    def handler(number: int) -> Any:
        async def run(_context: CycleContext) -> StepResult:
            calls.append(number)
            return StepResult.success()

        return run

    report = await _runner(tmp_path).run(_steps(handler), when=NOW)

    assert report["status"] == StepStatus.SUCCESS.value
    assert calls == list(range(1, 14))
    assert report["failure_history"][0]["step"] == "workflow_contract"


def test_scheduler_declares_the_exact_thirteen_required_steps() -> None:
    from crypto_intel.scheduler import three_hour_cycle_steps

    steps = three_hour_cycle_steps()
    assert [(step.number, step.key) for step in steps] == [
        (1, "read_latest"),
        (2, "provider_limits"),
        (3, "new_publications"),
        (4, "revisions"),
        (5, "indicators"),
        (6, "active_events"),
        (7, "compare"),
        (8, "signals"),
        (9, "scenarios"),
        (10, "asset_states"),
        (11, "analysis"),
        (12, "cycle_report"),
        (13, "notifications"),
    ]


@pytest.mark.asyncio
async def test_resume_rehydrates_non_json_asset_snapshots(monkeypatch: Any) -> None:
    from crypto_intel import scheduler
    from crypto_intel.engines import analysis_context

    calls: list[Asset] = []

    def context_for(asset: Asset, _now: datetime, *, refresh: bool) -> Any:
        assert refresh is True
        calls.append(asset)
        return SimpleNamespace(asset=asset.value)

    async def inline(function: Any, *args: Any, **kwargs: Any) -> Any:
        return function(*args, **kwargs)

    monkeypatch.setattr(analysis_context, "context_for", context_for)
    monkeypatch.setattr(scheduler.asyncio, "to_thread", inline)
    context = CycleContext(now=NOW, trigger="RESTART", cycle_id=cycle_id_for(NOW))

    restored, errors = await scheduler._cycle_asset_snapshots(context)
    restored_again, errors_again = await scheduler._cycle_asset_snapshots(context)

    assert errors == errors_again == []
    assert set(restored) == {"BTC", "ETH", "SOL"}
    assert restored_again is restored
    assert calls == list(Asset.tradables())


@pytest.mark.asyncio
async def test_cycle_analysis_targets_only_changed_assets(monkeypatch: Any) -> None:
    from crypto_intel import scheduler

    captured: dict[str, Any] = {}

    async def job_analysis(global_data: dict[str, Any], assets: list[Asset]) -> None:
        captured["global_data"] = global_data
        captured["assets"] = assets

    monkeypatch.setattr(scheduler, "job_analysis", job_analysis)
    monkeypatch.setattr(scheduler, "_job_result", lambda _name: (True, "ok"))
    context = CycleContext(
        now=NOW,
        trigger="RESTART",
        cycle_id=cycle_id_for(NOW),
        shared={
            "input_before": {"BTC": {"v": 1}, "ETH": {"v": 1}, "SOL": {"v": 1}},
            "input_after": {"BTC": {"v": 1}, "ETH": {"v": 2}, "SOL": {"v": 1}},
            "reports_before": {
                asset: {"created_at": NOW.isoformat()}
                for asset in ("BTC", "ETH", "SOL")
            },
        },
    )

    result = await scheduler._cycle_generate_if_needed(context)

    assert result.status is StepStatus.SUCCESS
    assert result.data["changed_assets"] == ["ETH"]
    assert captured == {"global_data": {}, "assets": [Asset.ETH]}


@pytest.mark.asyncio
async def test_scheduler_status_exposes_the_durable_step_report(tmp_path: Path) -> None:
    from crypto_intel.api.routes_lot2 import scheduler_status

    def handler(_number: int) -> Any:
        async def run(_context: CycleContext) -> StepResult:
            return StepResult.success()

        return run

    await _runner(tmp_path).run(_steps(handler), when=NOW)

    payload = await scheduler_status()

    assert payload["three_hour_cycle"]["cycle_id"] == cycle_id_for(NOW)
    assert len(payload["three_hour_cycle"]["steps"]) == 13
    assert payload["three_hour_cycle"]["status"] == StepStatus.SUCCESS.value


@pytest.mark.asyncio
async def test_derivative_refresh_honours_the_selected_source_family(
    monkeypatch: Any,
) -> None:
    from crypto_intel import scheduler
    from crypto_intel.history import backfill
    from crypto_intel.providers.derivatives import multi_exchange
    from crypto_intel.providers.volatility import deribit

    calls: list[tuple[str, str]] = []

    def recorder(name: str) -> Any:
        async def run(asset: Asset, **_kwargs: Any) -> None:
            calls.append((name, asset.value))

        return run

    monkeypatch.setattr(backfill, "backfill_funding", recorder("funding"))
    monkeypatch.setattr(backfill, "backfill_long_short_accounts", recorder("ratio"))
    monkeypatch.setattr(backfill, "backfill_open_interest", recorder("oi_binance"))
    monkeypatch.setattr(backfill, "backfill_spot_taker_flow", recorder("spot"))
    monkeypatch.setattr(
        multi_exchange, "backfill_bybit_open_interest", recorder("oi_bybit")
    )
    monkeypatch.setattr(deribit, "backfill_dvol", recorder("dvol"))

    await scheduler.job_derivatives_sync({"implied_volatility"})

    assert calls == [("dvol", "BTC"), ("dvol", "ETH")]


@pytest.mark.asyncio
async def test_retry_does_not_recollect_a_source_that_already_succeeded(
    monkeypatch: Any,
) -> None:
    from crypto_intel import scheduler
    from crypto_intel.db import repo
    from crypto_intel.pipeline import orchestrator, source_state_store
    from crypto_intel.pipeline.source_policy import SourceState
    from crypto_intel.providers import registry

    states = {"market_price": SourceState("market_price", last_success_at=NOW)}
    saved: list[dict[str, SourceState]] = []

    async def inline(function: Any, *args: Any, **kwargs: Any) -> Any:
        return function(*args, **kwargs)

    async def forbidden_market_call() -> None:
        raise AssertionError("a successful source must not be recollected on retry")

    monkeypatch.setattr(scheduler.asyncio, "to_thread", inline)
    monkeypatch.setattr(source_state_store, "load", lambda: states)
    monkeypatch.setattr(source_state_store, "save", lambda value: saved.append(value))
    monkeypatch.setattr(scheduler, "job_market_only", forbidden_market_call)
    monkeypatch.setattr(repo, "future_event_fingerprint", lambda: {"digest": "same"})
    monkeypatch.setattr(orchestrator, "get_pipeline", lambda: SimpleNamespace())
    monkeypatch.setattr(registry, "get_registry", lambda: SimpleNamespace())
    context = CycleContext(
        # A process restart a few minutes later stays in the same UTC bucket;
        # the source must still be recognised as already completed.
        now=NOW.replace(minute=27),
        trigger="RESTART",
        cycle_id=cycle_id_for(NOW),
        shared={"due_sources": ["market_price"]},
    )

    result = await scheduler._cycle_collect_publications(context)

    assert result.status is StepStatus.SUCCESS
    assert result.data["collected_sources"] == []
    assert result.data["already_succeeded"] == ["market_price"]
    assert result.data["blocked_sources"] == []
    assert saved


@pytest.mark.asyncio
async def test_event_collection_calls_only_the_due_capability_group(
    monkeypatch: Any,
) -> None:
    from crypto_intel import scheduler
    from crypto_intel.db import repo
    from crypto_intel.future_events import collector
    from crypto_intel.pipeline import orchestrator, source_state_store
    from crypto_intel.providers import registry

    collected: list[tuple[str, ...]] = []

    class FakeCollector:
        async def collect(self, capabilities: tuple[str, ...]) -> Any:
            collected.append(capabilities)
            return SimpleNamespace(saved=1, failures={})

    class FakePipeline:
        def persist(self, _results: dict[str, Any]) -> int:
            return 0

    async def inline(function: Any, *args: Any, **kwargs: Any) -> Any:
        return function(*args, **kwargs)

    monkeypatch.setattr(scheduler.asyncio, "to_thread", inline)
    monkeypatch.setattr(source_state_store, "load", lambda: {})
    monkeypatch.setattr(source_state_store, "save", lambda _states: None)
    monkeypatch.setattr(collector, "FutureEventCollector", FakeCollector)
    monkeypatch.setattr(repo, "future_event_fingerprint", lambda: {})
    monkeypatch.setattr(orchestrator, "get_pipeline", lambda: FakePipeline())
    monkeypatch.setattr(registry, "get_registry", lambda: SimpleNamespace())
    context = CycleContext(
        now=NOW,
        trigger="CRON_3H",
        cycle_id=cycle_id_for(NOW),
        shared={"due_sources": ["sec_filings"]},
    )

    result = await scheduler._cycle_collect_publications(context)

    assert result.status is StepStatus.SUCCESS
    assert collected == [("events.regulation.sec_filings",)]
    assert result.data["collected_sources"] == ["sec_filings"]


@pytest.mark.asyncio
async def test_failed_source_under_backoff_keeps_collection_degraded(
    monkeypatch: Any,
) -> None:
    from crypto_intel import scheduler
    from crypto_intel.db import repo
    from crypto_intel.pipeline import orchestrator, source_state_store
    from crypto_intel.pipeline.source_policy import SourceState
    from crypto_intel.providers import registry

    failed = SourceState(
        "market_price",
        last_success_at=None,
        consecutive_failures=3,
        circuit="OPEN",
        opened_at=NOW,
        last_error_kind="HTTP_429",
    )

    async def inline(function: Any, *args: Any, **kwargs: Any) -> Any:
        return function(*args, **kwargs)

    monkeypatch.setattr(scheduler.asyncio, "to_thread", inline)
    monkeypatch.setattr(source_state_store, "load", lambda: {"market_price": failed})
    monkeypatch.setattr(source_state_store, "save", lambda _states: None)
    monkeypatch.setattr(repo, "future_event_fingerprint", lambda: {})
    monkeypatch.setattr(orchestrator, "get_pipeline", lambda: SimpleNamespace())
    monkeypatch.setattr(registry, "get_registry", lambda: SimpleNamespace())
    context = CycleContext(
        now=NOW,
        trigger="RESTART",
        cycle_id=cycle_id_for(NOW),
        shared={"due_sources": ["market_price"]},
    )

    result = await scheduler._cycle_collect_publications(context)

    assert result.status is StepStatus.DEGRADED
    assert result.data["already_succeeded"] == []
    assert result.data["blocked_sources"] == ["market_price"]
    assert result.data["collected_sources"] == []
    assert result.data["source_results"]["market_price"]["ok"] is False
    assert "HTTP_429" in result.data["source_results"]["market_price"]["errors"][0]


@pytest.mark.asyncio
async def test_planning_reports_an_open_source_circuit_as_degraded(
    monkeypatch: Any,
) -> None:
    from crypto_intel import scheduler
    from crypto_intel.pipeline import source_state_store
    from crypto_intel.pipeline.source_policy import SourceState

    failed = SourceState(
        "market_price",
        consecutive_failures=3,
        circuit="OPEN",
        opened_at=NOW,
        last_error_kind="TIMEOUT",
    )

    async def inline(function: Any, *args: Any, **kwargs: Any) -> Any:
        return function(*args, **kwargs)

    monkeypatch.setattr(scheduler.asyncio, "to_thread", inline)
    monkeypatch.setattr(source_state_store, "load", lambda: {"market_price": failed})
    monkeypatch.setattr(source_state_store, "save", lambda _states: None)
    context = CycleContext(now=NOW, trigger="CRON_3H", cycle_id=cycle_id_for(NOW))

    result = await scheduler._cycle_plan_due_sources(context)

    assert result.status is StepStatus.DEGRADED
    assert result.data["blocked_sources"] == ["market_price"]
    assert "market_price" not in result.data["due_sources"]


@pytest.mark.asyncio
async def test_due_whale_source_is_collected_and_persisted_per_asset(
    monkeypatch: Any,
) -> None:
    from crypto_intel import scheduler
    from crypto_intel.db import repo
    from crypto_intel.pipeline import orchestrator, source_state_store
    from crypto_intel.providers import registry

    requests: list[tuple[str, str | None]] = []
    persisted: list[set[str]] = []

    class FakeRegistry:
        async def fetch(self, request: Any) -> Any:
            requests.append(
                (
                    request.capability,
                    request.asset.value if request.asset is not None else None,
                )
            )
            return SimpleNamespace(
                ok=True,
                observations=[],
                status=SimpleNamespace(value="OK"),
            )

    class FakePipeline:
        def persist(self, results: dict[str, Any]) -> int:
            persisted.append(set(results))
            return 0

    async def inline(function: Any, *args: Any, **kwargs: Any) -> Any:
        return function(*args, **kwargs)

    monkeypatch.setattr(scheduler.asyncio, "to_thread", inline)
    monkeypatch.setattr(source_state_store, "load", lambda: {})
    monkeypatch.setattr(source_state_store, "save", lambda _states: None)
    monkeypatch.setattr(repo, "future_event_fingerprint", lambda: {})
    monkeypatch.setattr(orchestrator, "get_pipeline", lambda: FakePipeline())
    monkeypatch.setattr(registry, "get_registry", lambda: FakeRegistry())
    context = CycleContext(
        now=NOW,
        trigger="CRON_3H",
        cycle_id=cycle_id_for(NOW),
        shared={"due_sources": ["whales"]},
    )

    result = await scheduler._cycle_collect_publications(context)

    assert result.status is StepStatus.SUCCESS
    assert requests == [
        ("whales.flows", "BTC"),
        ("whales.flows", "ETH"),
        ("whales.flows", "SOL"),
    ]
    assert persisted == [{"whales_BTC", "whales_ETH", "whales_SOL"}]
    assert result.data["source_results"]["whales"]["ok"] is True

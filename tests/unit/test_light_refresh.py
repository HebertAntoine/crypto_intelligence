"""Sections 5-10, 26-29, 33, 39, 42: the pass that runs between full cycles.

The failure this whole pass exists to prevent is the twelve-hour one: a price or
an open-interest reading sitting almost half a day old while still being the
newest thing the app has, purely because the next full cycle had not come round.
"""

from datetime import UTC, datetime, timedelta

import pytest

from crypto_intel.pipeline.light_refresh import (
    RefreshOutcome,
    _classify,
    fingerprint,
    run_light_refresh,
)
from crypto_intel.pipeline.source_policy import (
    CIRCUIT_COOLDOWN,
    SourceHealth,
    SourceState,
    fast_sources,
    health_of,
    policy_for,
)
from crypto_intel.pipeline.source_state_store import load, save

NOW = datetime(2026, 9, 18, 12, tzinfo=UTC)


@pytest.fixture
def state_file(tmp_path):
    return tmp_path / "source_state.json"


def collector_ok(payload="data"):
    calls: list[str] = []

    def collect(policy):
        calls.append(policy.source_id)
        return f"{payload}-{policy.source_id}"

    collect.calls = calls
    return collect


def exporter_ok():
    runs: list[str] = []

    def export(run_id):
        runs.append(run_id)
        return True

    export.runs = runs
    return export


def run(*, now=NOW, collector=None, exporter=None, state_path=None, trigger="SYSTEMD_LIGHT"):
    return run_light_refresh(
        now=now,
        collector=collector or collector_ok(),
        exporter=exporter or exporter_ok(),
        state_path=state_path,
        trigger=trigger,
    )


# --- section 42: the twelve-hour failure ------------------------------------


def test_fast_data_is_refreshed_without_waiting_for_the_full_cycle(
    state_file,
) -> None:
    """The criterion the whole phase is measured against."""

    collect = collector_ok()
    outcome = run(collector=collect, state_path=state_file)

    fast_ids = {item.source_id for item in fast_sources()}
    assert set(collect.calls) == fast_ids
    assert outcome.status == "SUCCESS"


def test_a_source_refreshed_minutes_ago_is_left_alone(state_file) -> None:
    run(state_path=state_file)
    collect = collector_ok()
    second = run(
        now=NOW + timedelta(minutes=2), collector=collect, state_path=state_file
    )
    assert collect.calls == []
    assert second.due == []


def test_each_source_comes_due_on_its_own_cadence(state_file) -> None:
    run(state_path=state_file)
    collect = collector_ok()
    # Seven minutes: past the five-minute sources, short of the fifteen-minute
    # ones. A single cadence for everything would refresh all or none.
    run(now=NOW + timedelta(minutes=7), collector=collect, state_path=state_file)
    assert set(collect.calls) == {"market_price", "spot_pressure"}


def test_the_slow_sources_are_never_polled_by_the_light_pass(state_file) -> None:
    collect = collector_ok()
    run(collector=collect, state_path=state_file)
    for slow in ("event_calendars", "regulation", "etf_flows", "stablecoins"):
        assert slow not in collect.calls


# --- dirty propagation and export -------------------------------------------


def test_only_the_families_actually_touched_are_marked_dirty(state_file) -> None:
    outcome = run(state_path=state_file)
    assert outcome.dirty_families == {"technical", "derivatives", "spot"}
    assert "macro" not in outcome.dirty_families
    assert "events" not in outcome.dirty_families


def test_nothing_collected_means_nothing_republished(state_file) -> None:
    run(state_path=state_file)
    export = exporter_ok()
    second = run(
        now=NOW + timedelta(minutes=1), exporter=export, state_path=state_file
    )
    assert export.runs == []
    assert second.exported is False


def test_the_run_is_stamped_with_its_type_and_trigger(state_file) -> None:
    outcome = run(state_path=state_file, trigger="MANUAL")
    assert outcome.run_type == "LIGHT"
    assert outcome.trigger == "MANUAL"
    assert outcome.run_id.endswith("_light")


def test_every_export_of_one_pass_uses_a_single_run_id(state_file) -> None:
    export = exporter_ok()
    outcome = run(exporter=export, state_path=state_file)
    assert export.runs == [outcome.run_id]


# --- section 39: chaos ------------------------------------------------------


def test_one_failing_source_does_not_stop_the_others(state_file) -> None:
    def collect(policy):
        if policy.source_id == "derivatives_oi":
            raise TimeoutError("bybit timeout")
        return "data"

    outcome = run(collector=collect, state_path=state_file)
    assert outcome.failed == ["derivatives_oi"]
    assert "market_price" in outcome.succeeded
    assert outcome.status == "DEGRADED_SUCCESS"
    assert outcome.exported is True


def test_repeated_failures_open_the_breaker_and_stop_the_calls(state_file) -> None:
    def always_fails(policy):
        raise TimeoutError("down")

    moment = NOW
    for _ in range(3):
        run(now=moment, collector=always_fails, state_path=state_file)
        moment += timedelta(minutes=20)

    states = load(state_file)
    assert states["market_price"].circuit == "OPEN"

    collect = collector_ok()
    run(now=moment, collector=collect, state_path=state_file)
    assert "market_price" not in collect.calls


def test_a_source_recovers_on_its_own_after_the_cooldown(state_file) -> None:
    """Section 33: no human step between down and healthy again."""

    def always_fails(policy):
        raise TimeoutError("down")

    moment = NOW
    for _ in range(3):
        run(now=moment, collector=always_fails, state_path=state_file)
        moment += timedelta(minutes=20)
    assert load(state_file)["market_price"].circuit == "OPEN"

    collect = collector_ok()
    run(
        now=moment + CIRCUIT_COOLDOWN + timedelta(minutes=1),
        collector=collect,
        state_path=state_file,
    )
    assert "market_price" in collect.calls
    assert load(state_file)["market_price"].circuit == "CLOSED"


def test_an_auth_failure_stops_after_one_attempt(state_file) -> None:
    def unauthorised(policy):
        raise RuntimeError("HTTP 401 auth failed")

    run(collector=unauthorised, state_path=state_file)
    states = load(state_file)
    assert states["market_price"].circuit == "OPEN"
    assert states["market_price"].last_error_kind == "AUTH"


def test_a_refused_export_marks_the_pass_failed(state_file) -> None:
    def refuse(run_id):
        return False

    outcome = run(exporter=refuse, state_path=state_file)
    assert outcome.exported is False
    assert outcome.status == "FAILED"


def test_a_source_stuck_on_one_value_is_detected(state_file) -> None:
    """Section 18: HTTP 200 forever is not the same as data that moves."""

    constant = collector_ok(payload="frozen")
    moment = NOW
    for _ in range(4):
        run(now=moment, collector=constant, state_path=state_file)
        moment += timedelta(minutes=20)

    states = load(state_file)
    assert health_of(policy_for("market_price"), states["market_price"], moment) is (
        SourceHealth.DATA_STUCK
    )


def test_a_corrupt_state_file_costs_one_collection_not_a_cycle(
    state_file,
) -> None:
    state_file.write_text("{ not json", encoding="utf-8")
    outcome = run(state_path=state_file)
    assert outcome.status == "SUCCESS"
    assert outcome.succeeded


def test_state_is_written_atomically_and_survives_the_process(state_file) -> None:
    run(state_path=state_file)
    reloaded = load(state_file)
    assert reloaded["market_price"].last_success_at == NOW
    assert reloaded["market_price"].last_attempt_at == NOW


# --- error classification ---------------------------------------------------


def test_errors_are_classified_into_the_kinds_the_policy_understands() -> None:
    assert _classify(TimeoutError("read timeout")) == "TIMEOUT"
    assert _classify(RuntimeError("HTTP 401 unauthorised")) == "AUTH"
    assert _classify(RuntimeError("HTTP 429 slow down")) == "HTTP_429"
    assert _classify(ConnectionError("dns failure")) == "CONNECTION"
    assert _classify(ValueError("invalid json")) == "HTTP_5XX"


def test_a_fingerprint_changes_with_the_payload() -> None:
    assert fingerprint({"a": 1}) == fingerprint({"a": 1})
    assert fingerprint({"a": 1}) != fingerprint({"a": 2})


def test_the_outcome_reports_sources_left_alone_by_an_open_breaker(
    state_file,
) -> None:
    save(
        {
            "derivatives_oi": SourceState(
                source_id="derivatives_oi", circuit="OPEN", opened_at=NOW,
                consecutive_failures=3,
            )
        },
        state_file,
    )
    outcome = run(now=NOW + timedelta(minutes=1), state_path=state_file)
    assert "derivatives_oi" in outcome.skipped_open_circuit
    assert "derivatives_oi" not in outcome.due


def test_an_outcome_serialises_for_the_log_and_the_health_report() -> None:
    payload = RefreshOutcome(
        run_id="run_X", run_type="LIGHT", trigger="SYSTEMD_LIGHT"
    ).to_dict()
    assert payload["status"] == "SUCCESS"
    assert payload["run_type"] == "LIGHT"

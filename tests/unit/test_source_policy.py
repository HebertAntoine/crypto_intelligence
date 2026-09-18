"""Sections 3, 7, 8, 11-14, 18: cadence, due-ness, retry and circuit breaking.

The distinction these tests defend: how often we *ask* a source is not how long
its answer *counts*, and a source being down is not the same as its data being
old. Collapsing either pair is how a pipeline ends up confidently serving
something it should have discarded.
"""

import random
from datetime import UTC, datetime, timedelta

from crypto_intel.pipeline.source_policy import (
    CIRCUIT_COOLDOWN,
    CIRCUIT_FAILURE_THRESHOLD,
    POLICIES,
    STUCK_THRESHOLD,
    Criticality,
    RetryPolicy,
    SourceHealth,
    SourceState,
    circuit_allows,
    data_freshness,
    fast_sources,
    health_of,
    is_due,
    is_retryable,
    policy_for,
    record_attempt,
    record_failure,
    record_success,
    which_sources_are_due,
)

NOW = datetime(2026, 9, 18, 12, tzinfo=UTC)


def state(source_id="market_price", **kwargs) -> SourceState:
    return SourceState(source_id=source_id, **kwargs)


# --- section 3: the two numbers are not the same ----------------------------


def test_every_policy_tolerates_at_least_one_missed_cycle() -> None:
    """max_age below refresh_interval would mark data stale before the retry."""

    for policy in POLICIES.values():
        assert policy.max_age > policy.refresh_interval, policy.source_id


def test_refresh_interval_and_max_age_are_genuinely_distinct() -> None:
    funding = policy_for("derivatives_funding")
    assert funding.refresh_interval == timedelta(minutes=15)
    assert funding.max_age == timedelta(minutes=60)


def test_every_policy_documents_why_it_was_chosen() -> None:
    for policy in POLICIES.values():
        assert policy.note.strip(), policy.source_id


def test_fast_sources_are_the_ones_that_move_between_full_cycles() -> None:
    ids = {item.source_id for item in fast_sources()}
    assert {"market_price", "ohlcv", "derivatives_oi", "spot_pressure"} <= ids
    # A monthly release has no business being polled between cycles.
    assert "event_calendars" not in ids
    assert "stablecoins" not in ids


# --- sections 7 and 8: due-ness is measured from success ---------------------


def test_a_source_never_collected_is_due() -> None:
    assert is_due(policy_for("ohlcv"), None, NOW) is True


def test_a_failing_source_called_recently_is_still_due() -> None:
    """The regression this prevents: judging freshness on the attempt."""

    stale = state(
        last_attempt_at=NOW - timedelta(minutes=2),
        last_success_at=NOW - timedelta(hours=3),
    )
    assert is_due(policy_for("ohlcv"), stale, NOW) is True


def test_a_recently_successful_source_is_not_due() -> None:
    fresh = state(last_success_at=NOW - timedelta(minutes=2))
    assert is_due(policy_for("ohlcv"), fresh, NOW) is False


def test_a_disabled_source_is_never_due() -> None:
    credit = policy_for("macro_credit")
    assert credit.enabled is False
    assert is_due(credit, None, NOW) is False


def test_the_runner_asks_the_policies_rather_than_a_hardcoded_list() -> None:
    due = which_sources_are_due({}, NOW, fast_only=True)
    assert {item.source_id for item in due} == {
        item.source_id for item in fast_sources()
    }
    slow = {item.source_id for item in which_sources_are_due({}, NOW)}
    assert "etf_flows" in slow


# --- sections 11 and 12: retry ----------------------------------------------


def test_backoff_grows_and_is_capped() -> None:
    retry = RetryPolicy(base_delay_s=1.0, max_delay_s=8.0, jitter_ratio=0.0)
    assert [retry.delay_for(n) for n in (1, 2, 3, 4, 9)] == [1.0, 2.0, 4.0, 8.0, 8.0]


def test_jitter_spreads_simultaneous_retries() -> None:
    retry = RetryPolicy(base_delay_s=4.0, jitter_ratio=0.5)
    rng = random.Random(0)
    delays = {round(retry.delay_for(2, rng=rng), 4) for _ in range(20)}
    assert len(delays) > 1
    assert all(0 <= value <= 12 for value in delays)


def test_an_expired_credential_is_not_retried() -> None:
    """Asking again does not make a key valid."""

    assert is_retryable("AUTH") is False
    assert is_retryable("HTTP_4XX") is False
    assert is_retryable("BLOCKED_BY_SOURCE") is False


def test_transient_failures_are_retried() -> None:
    for kind in ("TIMEOUT", "CONNECTION", "HTTP_5XX", "HTTP_429"):
        assert is_retryable(kind) is True, kind


# --- section 13: circuit breaker --------------------------------------------


def test_repeated_failures_open_the_circuit() -> None:
    item = state()
    for _ in range(CIRCUIT_FAILURE_THRESHOLD):
        record_attempt(item, NOW)
        record_failure(item, NOW, error_kind="TIMEOUT")
    assert item.circuit == "OPEN"


def test_an_open_circuit_stops_the_hammering() -> None:
    item = state(circuit="OPEN", opened_at=NOW)
    assert circuit_allows(item, NOW + timedelta(minutes=5)) is False
    assert is_due(policy_for("ohlcv"), item, NOW + timedelta(minutes=5)) is False


def test_the_cooldown_lets_exactly_one_probe_through() -> None:
    item = state(circuit="OPEN", opened_at=NOW)
    later = NOW + CIRCUIT_COOLDOWN + timedelta(seconds=1)
    assert circuit_allows(item, later) is True
    assert item.circuit == "HALF_OPEN"


def test_a_successful_probe_closes_the_circuit() -> None:
    item = state(circuit="HALF_OPEN")
    record_success(item, NOW)
    assert item.circuit == "CLOSED"
    assert item.opened_at is None


def test_a_failed_probe_reopens_it_immediately() -> None:
    item = state(circuit="HALF_OPEN", consecutive_failures=0)
    record_failure(item, NOW, error_kind="TIMEOUT")
    assert item.circuit == "OPEN"


def test_an_auth_failure_opens_the_circuit_at_once() -> None:
    item = state()
    record_failure(item, NOW, error_kind="AUTH")
    assert item.circuit == "OPEN"
    assert health_of(policy_for("ohlcv"), item, NOW) is SourceHealth.AUTH_ERROR


# --- section 14: source health is not data freshness ------------------------


def test_a_down_source_can_still_have_fresh_data() -> None:
    """A source that just broke has not made its last answer old."""

    item = state(last_success_at=NOW - timedelta(minutes=2), circuit="OPEN",
                 opened_at=NOW, consecutive_failures=3)
    policy = policy_for("ohlcv")
    assert health_of(policy, item, NOW) is SourceHealth.DOWN
    assert data_freshness(policy, item, NOW) == "FRESH"


def test_a_healthy_source_can_still_have_stale_data() -> None:
    item = state(last_success_at=NOW - timedelta(hours=4))
    policy = policy_for("ohlcv")
    assert health_of(policy, item, NOW) is SourceHealth.HEALTHY
    assert data_freshness(policy, item, NOW) == "STALE"


def test_freshness_passes_through_aging_before_stale() -> None:
    policy = policy_for("ohlcv")  # max_age 90 min
    assert data_freshness(policy, state(last_success_at=NOW - timedelta(minutes=10)), NOW) == "FRESH"
    assert data_freshness(policy, state(last_success_at=NOW - timedelta(minutes=60)), NOW) == "AGING"
    assert data_freshness(policy, state(last_success_at=NOW - timedelta(minutes=120)), NOW) == "STALE"


def test_a_never_collected_source_is_unavailable_not_stale() -> None:
    assert data_freshness(policy_for("ohlcv"), None, NOW) == "UNAVAILABLE"


# --- section 18: data stuck -------------------------------------------------


def test_identical_payloads_in_a_row_are_reported_as_stuck() -> None:
    """HTTP 200 forever is not the same as data that moves."""

    item = state()
    for _ in range(STUCK_THRESHOLD + 1):
        record_success(item, NOW, fingerprint="same-bytes")
    assert health_of(policy_for("ohlcv"), item, NOW) is SourceHealth.DATA_STUCK


def test_a_changing_payload_clears_the_stuck_counter() -> None:
    item = state()
    for _ in range(STUCK_THRESHOLD + 1):
        record_success(item, NOW, fingerprint="same-bytes")
    record_success(item, NOW, fingerprint="different-bytes")
    assert item.unchanged_successes == 0
    assert health_of(policy_for("ohlcv"), item, NOW) is SourceHealth.HEALTHY


# --- criticality ------------------------------------------------------------


def test_the_credit_source_is_declared_rather_than_silently_failing() -> None:
    credit = policy_for("macro_credit")
    assert credit.enabled is False
    assert "clé" in credit.note
    assert health_of(credit, None, NOW) is SourceHealth.NOT_CONFIGURED


def test_criticality_is_set_on_every_source() -> None:
    for policy in POLICIES.values():
        assert isinstance(policy.criticality, Criticality)


def test_state_survives_a_round_trip_through_storage() -> None:
    """Light and full refresh are separate processes; the state must persist."""

    item = state(last_success_at=NOW, consecutive_failures=2, circuit="OPEN",
                 opened_at=NOW, last_error_kind="TIMEOUT")
    restored = SourceState.from_dict(item.to_dict())
    assert restored == item


def test_a_source_that_has_only_ever_failed_is_not_hammered() -> None:
    """Never-succeeded must not outrank an open breaker."""

    never = state(last_success_at=None, circuit="OPEN", opened_at=NOW,
                  consecutive_failures=5)
    assert is_due(policy_for("ohlcv"), never, NOW + timedelta(minutes=5)) is False
    # Once the cooldown has passed, one probe is allowed.
    assert is_due(
        policy_for("ohlcv"), never, NOW + CIRCUIT_COOLDOWN + timedelta(minutes=1)
    ) is True

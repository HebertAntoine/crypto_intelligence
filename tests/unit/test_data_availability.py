"""The availability layer must never let a short series pass as history.

These tests pin the distinction the whole page depends on: usable_for_live and
usable_for_backtest answer different questions, and a series can pass one while
failing the other. Getting this wrong is how a base rate gets computed from
eleven observations, so the rules are asserted rather than assumed.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from crypto_intel.core.availability import (
    AvailabilityReason,
    DataAvailability,
    assess,
    summarise,
)

NOW = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)


def _series(days: float, points: int, *, age_hours: float = 1.0, **kwargs):
    last = NOW - timedelta(hours=age_hours)
    return assess(
        source="test",
        first=last - timedelta(days=days),
        last=last,
        points=points,
        now=NOW,
        **kwargs,
    )


def test_empty_series_is_no_data_not_stale():
    """Having nothing and having something old are different failures."""
    record = assess(source="test", metric="price.close", points=0, now=NOW)

    assert record.reason is AvailabilityReason.NO_DATA
    assert not record.usable_for_live
    assert not record.usable_for_backtest
    assert record.coverage_days == 0.0


def test_deep_fresh_series_is_usable_for_both():
    record = _series(1200, 1200, metric="ohlcv.1d", symbol="BTC")

    assert record.usable_for_live
    assert record.usable_for_backtest
    assert record.reason is AvailabilityReason.OK


def test_short_but_current_series_is_live_only():
    """The open-interest case: perfectly current, far too short to study."""
    record = _series(30, 31, metric="oi.value", symbol="BTC")

    assert record.usable_for_live
    assert not record.usable_for_backtest
    assert record.reason is AvailabilityReason.INSUFFICIENT_HISTORY


def test_source_limited_series_says_so():
    """A ceiling from the source must not read as a backfill we forgot to run."""
    record = _series(
        30, 31, metric="oi.value", symbol="BTC",
        source_limited=True, source_note="Binance publishes only ~30 days",
    )

    assert record.reason is AvailabilityReason.SOURCE_LIMIT
    assert "Binance" in record.detail
    assert record.source_limited


def test_deep_but_stale_series_keeps_backtest_and_loses_live():
    """Old data still supports a study; it just cannot describe the present."""
    record = _series(1200, 1200, age_hours=72, metric="ohlcv.1d", symbol="BTC")

    assert not record.usable_for_live
    assert record.usable_for_backtest
    assert record.reason is AvailabilityReason.STALE


def test_long_window_with_few_points_is_rejected_as_sparse():
    """Two points a decade apart span ten years and are not ten years of data."""
    record = _series(3650, 4, metric="ohlcv.1d", symbol="BTC")

    assert not record.usable_for_backtest
    assert record.reason is AvailabilityReason.INSUFFICIENT_POINTS


def test_depth_requirement_follows_metric_class():
    """Macro needs more depth than a price series - the class decides, not the caller."""
    # 500 days sits above the price floor (365) and below the macro one (730).
    price = _series(500, 500, metric="price.close", symbol="BTC")
    macro = _series(500, 500, metric="macro.dxy")

    assert price.usable_for_backtest
    assert not macro.usable_for_backtest
    assert macro.required_days > price.required_days


def test_explicit_depth_override_wins():
    """A daily pattern study asks for more than the class default."""
    record = _series(800, 800, metric="ohlcv.1d", symbol="BTC", min_backtest_days=1095)

    assert not record.usable_for_backtest
    assert record.required_days == 1095


def test_reason_reports_the_binding_constraint_first():
    """Short AND stale reads as short: waiting fixes one, nothing fixes the other."""
    record = _series(30, 31, age_hours=500, metric="ohlcv.1d", symbol="BTC")

    assert record.reason is AvailabilityReason.INSUFFICIENT_HISTORY
    assert not record.usable_for_live
    assert not record.usable_for_backtest


def test_serialisation_carries_every_decision_field():
    payload = _series(1200, 1200, metric="ohlcv.1d", symbol="BTC").to_dict()

    for key in (
        "source", "symbol", "metric", "first_timestamp", "last_timestamp",
        "number_of_points", "coverage_days", "usable_for_live",
        "usable_for_backtest", "reason", "detail", "required_days",
    ):
        assert key in payload, f"{key} missing from the API payload"
    assert isinstance(payload["first_timestamp"], str)


def test_summary_counts_do_not_double_count():
    records = [
        _series(1200, 1200, metric="ohlcv.1d", symbol="BTC"),
        _series(30, 31, metric="oi.value", symbol="BTC"),
        DataAvailability(source="test", metric="dvol.btc"),
    ]

    summary = summarise(records)

    assert summary["series"] == 3
    assert summary["usable_for_backtest"] == 1
    assert summary["usable_for_live"] == 2
    assert summary["by_reason"][AvailabilityReason.NO_DATA.value] == 1


def test_unavailable_series_never_reads_as_a_bad_one():
    """A missing series must be excluded, not scored zero. §9 depends on it."""
    record = DataAvailability(source="test", metric="dvol.btc")

    assert record.reason is AvailabilityReason.NO_DATA
    assert not record.usable_for_live
    assert record.age_hours is None

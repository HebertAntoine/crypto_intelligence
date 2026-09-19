"""The backtest runs the live code and never sees the future."""

from datetime import UTC, datetime, timedelta

from tests.unit.test_decision_engine_v2 import FakeCache

from crypto_intel.backtest.decision_backtest import Call, HorizonReport, _forward, run
from crypto_intel.core.enums import Asset, Timeframe
from crypto_intel.future_events.models import DecisionHorizon

NOW = datetime(2026, 9, 19, 12, tzinfo=UTC)


def test_forward_return_starts_at_the_last_known_close():
    cache = FakeCache()
    cache.trend("BTC", Timeframe.H1, 24 * 60, slope=0.001)
    frame = cache.candles("BTC", Timeframe.H1)
    at = frame.index[-24 * 10].to_pydatetime()

    ret, adverse = _forward(frame, at, timedelta(days=1), 1)
    assert ret is not None and ret > 0
    assert adverse is not None


def test_a_horizon_without_complete_future_is_not_scored():
    cache = FakeCache()
    cache.trend("BTC", Timeframe.H1, 24 * 20)
    frame = cache.candles("BTC", Timeframe.H1)
    at = frame.index[-5].to_pydatetime()
    assert _forward(frame, at, timedelta(days=7), 1) == (None, None)


def test_the_replay_only_sees_what_was_published():
    cache = FakeCache()
    cache.trend("BTC", Timeframe.H1, 24 * 90)
    cache.trend("BTC", Timeframe.H4, 6 * 90)
    cache.trend("BTC", Timeframe.D1, 400)
    # A value published at NOW must not be visible to a decision a week before.
    cache.add("macro.real10y", [2.0, 9.9], step=timedelta(days=30), end=NOW - timedelta(days=1),
              delay=timedelta(days=1))
    reports = run(Asset.BTC, NOW - timedelta(days=8), NOW - timedelta(days=7),
                  horizons=(DecisionHorizon.D7,), cache=cache, events=[])
    assert reports["7d"].calls
    from crypto_intel.engines.pit_view import PointInTimeView

    seen = PointInTimeView(cache, NOW - timedelta(days=7)).latest("macro.real10y")
    assert seen is not None and seen.value == 2.0


def test_summary_reports_counts_rates_stability_and_calibration():
    report = HorizonReport("7d", calls=[
        Call(NOW, "BUY", 40, 75, None, 3.0, -1.0),
        Call(NOW, "BUY", 35, 72, None, -2.0, -4.0),
        Call(NOW, "WAIT", 5, 55, "FINAL", 1.0, None),
        Call(NOW, "SELL", -40, 80, None, -5.0, -2.0),
    ])
    summary = report.summary()

    assert summary["counts"] == {"BUY": 2, "WAIT": 1, "SELL": 1}
    assert summary["buy"]["hit_rate_pct"] == 50.0
    assert summary["buy"]["false_positive_rate_pct"] == 50.0
    assert summary["sell"]["hit_rate_pct"] == 100.0
    assert summary["buy"]["worst_adverse_move_pct"] == -4.0
    assert summary["decision_changes"] == 2
    assert summary["confidence_calibration"]

"""Section 21: the rules of the six-family decision, each pinned by a test.

A controlled data cache stands in for the database so every rule is checked in
isolation: stale data, missing data, horizons, leverage, ETF scope, gates.
"""

from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from crypto_intel.core.enums import Asset, Timeframe
from crypto_intel.engines.decision_config import (
    CYCLE,
    DERIVATIVES,
    FLOWS,
    HORIZON_WEIGHTS,
    LIQUIDITY,
    MACRO,
    ONCHAIN,
    TECHNICAL,
)
from crypto_intel.engines.decision_families import (
    Component,
    DataStatus,
    FamilyScore,
    FamilyState,
    build_families,
    derivatives_family,
    finish_family,
    flows_family,
    macro_family,
    onchain_family,
    read_metric,
)
from crypto_intel.engines.decision_gates import (
    ExternalChecks,
    FinalAction,
    GateStatus,
    aggregate,
    decide,
)
from crypto_intel.engines.pit_view import DataCache, Point, PointInTimeView, _Series
from crypto_intel.future_events.models import DecisionHorizon

NOW = datetime(2026, 9, 19, 12, tzinfo=UTC)


class FakeCache(DataCache):
    """Series and candles supplied by the test, never read from disk."""

    def __init__(self) -> None:
        super().__init__(database="/nonexistent.db")
        self.points: dict[tuple[str, str | None], list[Point]] = {}
        self.frames: dict[tuple[str, str], pd.DataFrame] = {}

    def add(self, metric, values, *, asset=None, step=timedelta(days=1), end=NOW,
            delay=timedelta(0), source="Source officielle"):
        start = end - step * (len(values) - 1)
        self.points[(metric, asset)] = [
            Point(start + step * i, start + step * i + delay, float(v), source)
            for i, v in enumerate(values)
        ]

    def series(self, metric, asset=None):
        return _Series.build(self.points.get((metric, asset), []))

    def candles(self, asset, timeframe):
        return self.frames.get((asset, timeframe.value), pd.DataFrame())

    def trend(self, asset, timeframe, n, *, start=100.0, slope=0.002):
        span = {Timeframe.H1: timedelta(hours=1), Timeframe.H4: timedelta(hours=4),
                Timeframe.D1: timedelta(days=1)}[timeframe]
        index = pd.date_range(end=NOW - span, periods=n, freq=span, tz="UTC")
        close = start * np.cumprod(np.full(n, 1 + slope))
        wiggle = np.sin(np.arange(n) / 3) * close * 0.004
        close = close + wiggle
        self.frames[(asset, timeframe.value)] = pd.DataFrame(
            {"open": close, "high": close * 1.003, "low": close * 0.997, "close": close,
             "volume": np.full(n, 10.0)},
            index=index,
        )


def view(cache):
    return PointInTimeView(cache, NOW)


def family(name, score, *, status=DataStatus.AVAILABLE, confidence=80, quality=100,
           horizon=DecisionHorizon.D7, extra=None):
    signal = None if score is None else score / 100
    # The gates read the spot component and the technical structure by name:
    # a synthetic family carries the same shape as a real one.
    key = "spot" if name == FLOWS else name
    components = [] if score is None else [Component(key, name, 1.0, signal, f"{name} {score}")]
    if name == TECHNICAL and extra is None and score is not None:
        extra = {
            "structure": "TREND_UP" if score > 0 else "TREND_DOWN" if score < 0 else "RANGE",
            "rsi": 55.0, "price": 100.0, "resistance": 110.0, "support": 90.0,
            "trend_signal": 0.5 if score > 0 else -0.5 if score < 0 else 0.0,
        }
    return FamilyScore(
        family=name, horizon=horizon.value, status=status, score=score,
        state=FamilyState.UNKNOWN if score is None else (
            FamilyState.POSITIVE if score >= 30 else FamilyState.NEGATIVE if score <= -30
            else FamilyState.NEUTRAL),
        confidence=confidence, data_quality=quality, components=components,
        extra=extra or {},
    )


def all_families(scores, *, horizon=DecisionHorizon.D7, confidence=85, extra=None):
    out = {}
    for name in (MACRO, LIQUIDITY, FLOWS, DERIVATIVES, ONCHAIN, TECHNICAL):
        score = scores.get(name)
        status = DataStatus.UNAVAILABLE if score is None else DataStatus.AVAILABLE
        out[name] = family(name, score, status=status, confidence=confidence,
                           horizon=horizon, extra=(extra or {}).get(name))
    return out


# --- stale and missing data ---------------------------------------------------


def test_stale_data_is_shown_but_never_used_as_current():
    cache = FakeCache()
    cache.add("macro.real10y", [2.0 + i * 0.01 for i in range(30)], end=NOW - timedelta(days=10))
    reading = read_metric(view(cache), "macro.real10y", window=timedelta(days=7))

    assert reading.status is DataStatus.STALE
    assert reading.value is not None  # shown, dated
    assert reading.usable is False  # never used as the current value
    assert "trop ancienne" in reading.note


def test_missing_data_is_never_turned_into_neutral():
    empty = FakeCache()
    result = macro_family(view(empty), Asset.BTC, DecisionHorizon.D7)

    assert result.score is None
    assert result.state is FamilyState.UNKNOWN
    assert result.status in {DataStatus.INSUFFICIENT_DATA, DataStatus.UNAVAILABLE}
    assert all(m.value is None for m in result.metrics)


def test_a_value_is_invisible_before_it_was_published():
    cache = FakeCache()
    # August CPI describes 1 August but is published mid-September.
    cache.add("macro.cpi", [300.0, 301.0], step=timedelta(days=31),
              end=datetime(2026, 8, 1, tzinfo=UTC), delay=timedelta(days=45))
    before = PointInTimeView(cache, datetime(2026, 9, 10, tzinfo=UTC)).latest("macro.cpi")
    after = PointInTimeView(cache, datetime(2026, 9, 20, tzinfo=UTC)).latest("macro.cpi")

    assert before is not None and before.timestamp.month == 7
    assert after is not None and after.timestamp.month == 8


# --- events -------------------------------------------------------------------


def test_a_close_critical_event_blocks_through_the_event_gate():
    families = all_families({MACRO: 60, LIQUIDITY: 50, FLOWS: 60, DERIVATIVES: 40, TECHNICAL: 60})
    decision = decide(
        families, DecisionHorizon.D7,
        ExternalChecks(event_gate_active=True, event_title="Décision de la Fed",
                       event_delay="dans 8 h"),
    )

    assert decision.action is FinalAction.WAIT
    assert decision.blocking_gate == "EVENT_RISK"
    assert "Décision de la Fed dans 8 h" in decision.headline
    assert any("Décision de la Fed" in c for c in decision.to_buy)


def test_a_future_fed_meeting_has_no_direction():
    from crypto_intel.engines.decision_hierarchy import DriverDirection, driver_from_event
    from crypto_intel.future_events.models import (
        EventImportance,
        EventScheduleType,
        ExpectedMovement,
        FutureEvent,
        FutureEventCategory,
        FutureEventSourceTier,
    )

    fomc = FutureEvent(
        event_type="FOMC_DECISION", category=FutureEventCategory.MONETARY_POLICY,
        schedule_type=EventScheduleType.SCHEDULED, title="FOMC", source="Federal Reserve",
        source_tier=FutureEventSourceTier.A, source_url="https://www.federalreserve.gov/",
        importance=EventImportance.CRITICAL, magnitude_effect=ExpectedMovement.HIGH,
        scheduled_at=NOW + timedelta(hours=8), detected_at=NOW, last_updated=NOW,
    )
    driver = driver_from_event(fomc, asset=Asset.BTC, horizon=DecisionHorizon.D7, now=NOW)
    assert driver.direction is DriverDirection.UNKNOWN


# --- horizons -----------------------------------------------------------------


def test_the_24h_reading_is_not_a_copy_of_the_30d_one():
    cache = FakeCache()
    # Yields: a sharp move this week after a quiet month - the horizons must
    # read it differently.
    cache.add("macro.real10y", [2.0] * 50 + [2.0 + 0.02 * i for i in range(10)])
    cache.add("macro.dxy", [100.0 + 0.1 * i for i in range(60)])
    short = macro_family(view(cache), Asset.BTC, DecisionHorizon.H24)
    month = macro_family(view(cache), Asset.BTC, DecisionHorizon.D30)

    assert short.score != month.score
    assert HORIZON_WEIGHTS[DecisionHorizon.H24] != HORIZON_WEIGHTS[DecisionHorizon.D30]
    short_real = next(m for m in short.metrics if m.key == "macro.real10y")
    month_real = next(m for m in month.metrics if m.key == "macro.real10y")
    assert short_real.delta_label.endswith("24 h")
    assert month_real.delta_label.endswith("30 j")


# --- derivatives --------------------------------------------------------------


def test_open_interest_alone_never_produces_a_sell():
    cache = FakeCache()
    cache.add("oi.value_history", [8e9 * (1 + 0.01 * i) for i in range(200)],
              asset="BTC", step=timedelta(hours=1), source="Binance Futures")
    # No candles: no price change, so OI cannot be interpreted at all.
    result = derivatives_family(view(cache), Asset.BTC, DecisionHorizon.D7)

    assert all(c.key != "crowding" for c in result.components)
    assert result.extra["crowding"] == "UNKNOWN"
    decision = decide(
        {**all_families({MACRO: 0, LIQUIDITY: 0, FLOWS: 0, TECHNICAL: 0}), DERIVATIVES: result},
        DecisionHorizon.D7,
    )
    assert decision.action is not FinalAction.SELL


def test_rising_price_and_leverage_with_hot_funding_reads_crowded_longs():
    cache = FakeCache()
    cache.trend("BTC", Timeframe.H1, 24 * 40, slope=0.0004)
    cache.add("oi.value_history", [8e9 * (1 + 0.002 * i) for i in range(24 * 40)],
              asset="BTC", step=timedelta(hours=1), source="Binance Futures")
    cache.add("funding.rate", [0.00002] * 900 + [0.0003] * 3, asset="BTC",
              step=timedelta(hours=8), source="Binance Futures (historique)")
    result = derivatives_family(view(cache), Asset.BTC, DecisionHorizon.D7)

    assert result.extra["crowding"] == "CROWDED_LONGS"
    assert result.score < 0


def test_crowded_longs_block_a_buy():
    families = all_families(
        {MACRO: 60, LIQUIDITY: 50, FLOWS: 60, DERIVATIVES: 20, TECHNICAL: 70},
        extra={DERIVATIVES: {"crowding": "CROWDED_LONGS"}},
    )
    decision = decide(families, DecisionHorizon.D7)
    assert decision.action is FinalAction.WAIT
    assert decision.blocking_gate == "CROWDING"


# --- scope of each source -----------------------------------------------------


def test_btc_etf_flows_never_reach_eth_or_sol():
    cache = FakeCache()
    cache.add("etf.net_flow", [500.0] * 120, asset="BTC", delay=timedelta(days=1),
              source="Farside Investors")
    for asset in (Asset.ETH, Asset.SOL):
        result = flows_family(view(cache), asset, DecisionHorizon.D7)
        assert all(c.key != "etf" for c in result.components), asset
    sol = flows_family(view(cache), Asset.SOL, DecisionHorizon.D7)
    etf = next(m for m in sol.metrics if m.key == "etf.net_flow")
    assert etf.status is DataStatus.NOT_APPLICABLE


def test_on_chain_without_a_source_contributes_nothing():
    result = onchain_family(view(FakeCache()), Asset.BTC, DecisionHorizon.D7)
    assert result.status is DataStatus.UNAVAILABLE
    assert result.score is None
    assert all(m.status is DataStatus.UNAVAILABLE for m in result.metrics)


def test_a_social_source_never_drives_a_family():
    cache = FakeCache()
    cache.add("macro.real10y", [2.0 + 0.02 * i for i in range(30)], source="Twitter")
    reading = read_metric(view(cache), "macro.real10y", window=timedelta(days=7),
                          source_tier="SOCIAL")
    assert reading.usable is False
    assert "sociale" in reading.note


# --- aggregation and gates ----------------------------------------------------


def test_missing_family_weights_are_renormalised():
    families = all_families({MACRO: 10, LIQUIDITY: 10, FLOWS: 10, DERIVATIVES: 10, TECHNICAL: 10})
    _, _, _, weights = aggregate(families, DecisionHorizon.D7)
    base = HORIZON_WEIGHTS[DecisionHorizon.D7]
    remaining = sum(base[k] for k in weights)

    assert ONCHAIN not in weights
    assert sum(weights.values()) == pytest.approx(1.0)
    assert weights[MACRO] == pytest.approx(base[MACRO] / remaining)


def test_strong_contradictions_hold_the_decision():
    families = all_families({MACRO: -70, LIQUIDITY: -60, FLOWS: 70, DERIVATIVES: -60, TECHNICAL: 70})
    decision = decide(families, DecisionHorizon.D7)
    assert decision.action is FinalAction.WAIT
    assert decision.blocking_gate == "CONTRADICTION"


def test_missing_critical_data_says_insufficient_data():
    families = all_families({FLOWS: 60, DERIVATIVES: 40, TECHNICAL: 60})  # no macro on 7 d
    decision = decide(families, DecisionHorizon.D7)
    assert decision.action is FinalAction.INSUFFICIENT_DATA
    assert decision.blocking_gate == "DATA_QUALITY"


def test_stale_critical_family_means_wait():
    families = all_families({MACRO: 60, LIQUIDITY: 50, FLOWS: 60, DERIVATIVES: 40, TECHNICAL: 60})
    families[TECHNICAL].status = DataStatus.STALE
    decision = decide(families, DecisionHorizon.D7)
    assert decision.action is FinalAction.WAIT
    assert decision.blocking_gate == "FRESHNESS"


def test_a_score_just_above_zero_is_never_a_buy():
    families = all_families({MACRO: 8, LIQUIDITY: 5, FLOWS: 9, DERIVATIVES: 6, TECHNICAL: 7})
    decision = decide(families, DecisionHorizon.D7)
    assert decision.action is FinalAction.WAIT


def test_a_buy_needs_three_independent_confirming_families():
    two = all_families({MACRO: 0, LIQUIDITY: 0, FLOWS: 90, DERIVATIVES: 0, TECHNICAL: 90})
    assert decide(two, DecisionHorizon.D7).action is FinalAction.WAIT

    three = all_families({MACRO: 50, LIQUIDITY: 40, FLOWS: 60, DERIVATIVES: 20, TECHNICAL: 60})
    decision = decide(three, DecisionHorizon.D7)
    assert decision.action is FinalAction.BUY
    assert len(decision.confirming_families) >= 3


def test_a_sell_mirrors_the_buy_rule():
    families = all_families({MACRO: -50, LIQUIDITY: -40, FLOWS: -60, DERIVATIVES: -20, TECHNICAL: -60})
    assert decide(families, DecisionHorizon.D7).action is FinalAction.SELL


def test_no_measurable_edge_holds_even_a_clean_setup():
    families = all_families({MACRO: 50, LIQUIDITY: 40, FLOWS: 60, DERIVATIVES: 20, TECHNICAL: 60})
    decision = decide(families, DecisionHorizon.D7,
                      ExternalChecks(consistency_codes=["NO_MEASURABLE_EDGE"]))
    assert decision.action is FinalAction.WAIT
    assert decision.blocking_gate == "UNCERTAINTY"


def test_every_gate_is_reported_in_order():
    decision = decide(all_families({MACRO: 10, FLOWS: 10, TECHNICAL: 10}), DecisionHorizon.D7)
    assert [g.name for g in decision.gates] == [
        "DATA_QUALITY", "FRESHNESS", "EVENT_RISK", "MARKET_REGIME", "UNCERTAINTY",
        "TECHNICAL_SETUP", "CONTRADICTION", "CROWDING", "SPOT_CONFIRMATION", "FINAL",
    ]
    assert all(g.status in set(GateStatus) for g in decision.gates)


def test_confidence_is_never_presented_as_a_probability():
    families = all_families({MACRO: 50, LIQUIDITY: 40, FLOWS: 60, DERIVATIVES: 20, TECHNICAL: 60})
    payload = decide(families, DecisionHorizon.D7).to_dict()

    assert "pas une probabilité" in payload["confidence_meaning"]
    assert not any("probab" in key for key in payload)
    text = " ".join([payload["headline"], *payload["reasons"]])
    assert "chance" not in text and "probabilit" not in text


def test_explanations_are_bounded():
    families = all_families({MACRO: -40, LIQUIDITY: -30, FLOWS: 20, DERIVATIVES: -50, TECHNICAL: 30})
    decision = decide(families, DecisionHorizon.D7)
    assert len(decision.to_buy) <= 3
    assert len(decision.to_worsen) <= 3
    assert len(decision.home_factors) <= 4
    assert len(decision.reasons) <= 6


def test_the_live_builder_never_crashes_on_an_empty_store():
    families = build_families(view(FakeCache()), Asset.BTC, DecisionHorizon.H24)
    assert set(families) == {MACRO, LIQUIDITY, FLOWS, DERIVATIVES, ONCHAIN, TECHNICAL, CYCLE}
    decision = decide(families, DecisionHorizon.H24)
    assert decision.action is FinalAction.INSUFFICIENT_DATA


def test_finish_family_with_opposed_strong_components_is_mixed():
    result = finish_family(
        MACRO, DecisionHorizon.D7,
        [Component("a", "A", 1.0, 0.8, "a"), Component("b", "B", 1.0, -0.8, "b")], [],
    )
    assert result.state is FamilyState.MIXED


# --- section 5: the event gate weighs, it does not merely detect --------------


def _fomc(hours):
    from crypto_intel.future_events.models import (
        EventImportance,
        EventScheduleType,
        ExpectedMovement,
        FutureEvent,
        FutureEventCategory,
        FutureEventSourceTier,
    )

    return FutureEvent(
        event_type="FOMC_DECISION", category=FutureEventCategory.MONETARY_POLICY,
        schedule_type=EventScheduleType.SCHEDULED, title="Décision de la Fed",
        source="Federal Reserve", source_tier=FutureEventSourceTier.A,
        source_url="https://www.federalreserve.gov/", importance=EventImportance.CRITICAL,
        magnitude_effect=ExpectedMovement.HIGH, scheduled_at=NOW + timedelta(hours=hours),
        detected_at=NOW, last_updated=NOW,
    )


def _graded(hours, horizon, confidence):
    from crypto_intel.engines.decision_gates import event_candidates

    families = all_families(
        {MACRO: 50, LIQUIDITY: 40, FLOWS: 60, DERIVATIVES: 20, TECHNICAL: 60},
        horizon=horizon, confidence=confidence,
    )
    return decide(families, horizon, ExternalChecks(
        event_candidates=event_candidates([_fomc(hours)], Asset.BTC, horizon, NOW)
    ))


def test_a_fed_decision_in_36_hours_holds_the_entry():
    decision = _graded(36, DecisionHorizon.D7, confidence=95)
    assert decision.blocking_gate == "EVENT_RISK"
    assert "dans 36 h" in decision.headline


def test_a_fed_decision_three_weeks_out_does_not_blindly_hold_a_30d_call():
    decision = _graded(24 * 20, DecisionHorizon.D30, confidence=95)
    gate = next(g for g in decision.gates if g.name == "EVENT_RISK")
    assert gate.status is GateStatus.PASS
    assert "À surveiller" in gate.detail


def test_a_nearby_event_holds_a_weakly_supported_call_only():
    weak = _graded(24 * 5, DecisionHorizon.D7, confidence=55)
    strong = _graded(24 * 5, DecisionHorizon.D7, confidence=95)

    assert weak.blocking_gate == "EVENT_RISK"
    assert next(g for g in strong.gates if g.name == "EVENT_RISK").status is GateStatus.PASS


def test_an_event_beyond_the_horizon_is_ignored():
    from crypto_intel.engines.decision_gates import event_candidates

    assert event_candidates([_fomc(24 * 3)], Asset.BTC, DecisionHorizon.H24, NOW) == []


def test_the_missing_edge_veto_holds_even_when_an_older_gate_said_wait_first():
    """Regression: the finding was only raised on a directional provisional
    action, so a 30 d call held by the old event gate never carried it - and
    the graded gate could have let a BUY through."""

    from tests.unit.test_decision_consistency import five

    from crypto_intel.engines.future_decision import DecisionAction, FutureDecisionEngine

    strong = all_families({MACRO: 50, LIQUIDITY: 40, FLOWS: 60, DERIVATIVES: 20, TECHNICAL: 60},
                          horizon=DecisionHorizon.D30, confidence=95)
    decision = FutureDecisionEngine().decide(
        Asset.BTC, [_fomc(24 * 20)], five(), horizon=DecisionHorizon.D30, as_of=NOW,
        analysis_uncertainty=0.8, edge_state="NO_MEASURABLE_EDGE", decision_families=strong,
    )
    assert decision.decision is DecisionAction.WAIT
    assert decision.analysis.blocking_gate == "UNCERTAINTY"

    with_edge = FutureDecisionEngine().decide(
        Asset.BTC, [_fomc(24 * 20)], five(), horizon=DecisionHorizon.D30, as_of=NOW,
        analysis_uncertainty=0.8, edge_state="POSITIVE_EDGE", decision_families=strong,
    )
    assert with_edge.decision is DecisionAction.BUY

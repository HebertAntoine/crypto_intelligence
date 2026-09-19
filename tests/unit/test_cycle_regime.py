"""The cycle reading, and the mistakes it must never make.

Section 26 of the mission lists them, each pinned here: days since the halving
never make a bull on their own, a halving is not a BUY, a high RSI is not the
end of a bull, a passing drawdown is not a bear, a new high is not a SELL, a
resemblance with a past cycle is not a forecast, ETH and SOL get no invented
halving cycle, and later data never rewrites an archived snapshot.
"""

from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import pytest
from tests.unit.test_decision_engine_v2 import NOW, all_families, family

from crypto_intel.core.enums import Asset
from crypto_intel.engines.cycle_history import cycle_stats, normalised_cycles
from crypto_intel.engines.cycle_regime import (
    CONFIRMATION_DAYS,
    CYCLE_SIGNAL_CAP,
    PHASE_LEAN,
    BitcoinCycleRegimeEngine,
    Dimensions,
    Phase,
    classify,
    dimension_frame,
    next_step,
)
from crypto_intel.engines.cycle_snapshots import (
    changes_since,
    list_snapshots,
    write_snapshot,
)
from crypto_intel.engines.decision_config import CYCLE, MACRO, TECHNICAL
from crypto_intel.engines.decision_gates import FinalAction, decide
from crypto_intel.future_events.models import DecisionHorizon

HALVING = datetime(2024, 4, 20, tzinfo=UTC)


def dims(**overrides) -> Dimensions:
    base = {
        "price": 80_000.0,
        "ath": 126_000.0,
        "ath_date": NOW - timedelta(days=350),
        "drawdown_pct": -36.0,
        "days_since_ath": 350,
        "new_high": False,
        "structure": "MIXED",
        "sma200": 70_000.0,
        "sma200_slope_pct": 2.0,
        "above_sma200": True,
        "momentum": "STEADY",
        "volatility": "NORMAL",
        "rebound_from_low_pct": 40.0,
        "days_since_halving": 880,
    }
    base.update(overrides)
    return Dimensions(**base)


def _frame(prices: list[float], *, start: datetime = datetime(2020, 1, 1, tzinfo=UTC)) -> pd.DataFrame:
    index = pd.date_range(start=start, periods=len(prices), freq="D", tz="UTC")
    series = pd.Series(prices, index=index, dtype=float)
    return pd.DataFrame(
        {"open": series, "high": series * 1.01, "low": series * 0.99,
         "close": series, "volume": 1.0},
        index=index,
    )


# --- 26.1  Days after a halving never make a bull ---------------------------


@pytest.mark.parametrize("days", [120, 400, 550, 900])
def test_the_halving_clock_alone_never_produces_a_bullish_phase(days):
    bearish = dims(
        days_since_halving=days, drawdown_pct=-62.0, structure="LOWER",
        above_sma200=False, sma200_slope_pct=-3.0, momentum="REVERSING",
        rebound_from_low_pct=3.0, days_since_ath=300,
    )
    assert classify(bearish).phase in {Phase.BEAR_MARKET, Phase.DEEP_DRAWDOWN}


def test_the_same_day_count_gives_different_phases_on_different_markets():
    common = {"days_since_halving": 500}
    expansion = classify(dims(
        drawdown_pct=-8.0, structure="HIGHER", above_sma200=True,
        sma200_slope_pct=6.0, momentum="ACCELERATING", **common)).phase
    bear = classify(dims(
        drawdown_pct=-55.0, structure="LOWER", above_sma200=False,
        sma200_slope_pct=-4.0, momentum="REVERSING", rebound_from_low_pct=2.0,
        days_since_ath=200, **common)).phase
    assert expansion is Phase.EXPANSION
    assert bear is Phase.BEAR_MARKET


# --- 26.2  A halving is not a BUY ------------------------------------------


def test_a_fresh_halving_never_buys_by_itself():
    families = all_families({MACRO: 0, TECHNICAL: 0}, horizon=DecisionHorizon.D30)
    families[CYCLE] = family(CYCLE, 100, horizon=DecisionHorizon.D30,
                             extra={"cycle": {"phase": "EXPANSION", "dimensions": {"days_since_halving": 3}}})
    decision = decide(families, DecisionHorizon.D30)
    assert decision.action is not FinalAction.BUY


def test_the_cycle_signal_is_capped_whatever_the_phase():
    assert max(abs(lean) for lean in PHASE_LEAN.values()) <= CYCLE_SIGNAL_CAP


# --- 26.3  A high RSI is not the end of a bull ------------------------------


def test_the_cycle_ignores_short_term_overbought_readings():
    # RSI is not a cycle dimension at all: the phase cannot move with it.
    bullish = dims(drawdown_pct=-2.0, new_high=True, structure="HIGHER",
                   momentum="ACCELERATING", sma200_slope_pct=8.0)
    assert classify(bullish).phase is Phase.PRICE_DISCOVERY
    assert "rsi" not in set(Dimensions.__slots__)


# --- 26.4  A passing drawdown is not a bear --------------------------------


def test_a_short_drawdown_inside_an_uptrend_is_not_a_bear():
    dip = dims(drawdown_pct=-18.0, days_since_ath=20, structure="HIGHER",
               above_sma200=True, sma200_slope_pct=5.0, momentum="SLOWING",
               rebound_from_low_pct=4.0)
    assert classify(dip).phase is not Phase.BEAR_MARKET


def test_a_phase_needs_confirmation_before_it_changes():
    # An uptrend, then a two-day scare, then the uptrend again.
    prices = [100 * 1.004 ** i for i in range(700)]
    prices[-3] *= 0.95
    prices[-2] *= 0.93
    frame = _frame(prices)
    engine = BitcoinCycleRegimeEngine()
    regime = engine.read(frame, [HALVING])
    assert regime is not None
    # The scare lasted two closes: far short of the confirmation window.
    assert regime.days_in_phase > CONFIRMATION_DAYS


def test_a_sustained_change_does_move_the_phase():
    rising = [100 * 1.004 ** i for i in range(600)]
    falling = [rising[-1] * 0.985 ** i for i in range(200)]
    regime = BitcoinCycleRegimeEngine().read(_frame(rising + falling), [HALVING])
    assert regime is not None
    assert regime.phase in {Phase.BEAR_MARKET, Phase.DEEP_DRAWDOWN, Phase.TRANSITION}
    assert len(regime.runs) >= 2


# --- 26.5  A new record is not a SELL ---------------------------------------


def test_a_new_all_time_high_never_sells():
    families = all_families({MACRO: 0, TECHNICAL: 10}, horizon=DecisionHorizon.D30)
    families[CYCLE] = family(CYCLE, 20, horizon=DecisionHorizon.D30,
                             extra={"cycle": {"phase": "PRICE_DISCOVERY"}})
    assert decide(families, DecisionHorizon.D30).action is not FinalAction.SELL


# --- 26.6  A resemblance is never a forecast --------------------------------


def test_the_cycle_page_carries_no_forecast():
    from crypto_intel.api.routes_cycle import DISCLAIMER

    assert "non prédictive" in DISCLAIMER
    step = next_step(
        BitcoinCycleRegimeEngine().read(
            _frame([100 * 1.003 ** i for i in range(700)]), [HALVING]
        )
    )
    text = " ".join([*step["conditions"], step["invalidation"]]).lower()
    for forbidden in ("prévu", "prévision", "dans 54 jours", "sommet estimé"):
        assert forbidden not in text


def test_past_cycles_are_measured_not_extrapolated():
    prices = [100 * 1.01 ** i for i in range(400)] + [100 * 1.01 ** 400 * 0.99 ** i for i in range(400)]
    frame = _frame(prices, start=datetime(2016, 1, 1, tzinfo=UTC))
    halvings = [datetime(2016, 7, 9, tzinfo=UTC)]
    stats = cycle_stats(frame, halvings, as_of=frame.index[-1].to_pydatetime())
    assert stats and stats[0].days_to_ath is not None
    assert stats[0].drawdown_after_ath_pct < 0
    # Nothing about the next cycle is produced.
    assert all(not key.startswith("next") for key in stats[0].to_dict())


def test_the_current_cycle_bottom_is_never_declared_in_real_time():
    prices = [100 * 1.01 ** i for i in range(300)] + [100 * 1.01 ** 300 * 0.99 ** i for i in range(200)]
    frame = _frame(prices, start=datetime(2024, 1, 1, tzinfo=UTC))
    stats = cycle_stats(frame, [datetime(2024, 4, 20, tzinfo=UTC)],
                        as_of=frame.index[-1].to_pydatetime())
    assert stats[-1].ongoing
    assert stats[-1].to_dict()["bottom_confirmed"] is False


# --- 26.7  ETH and SOL get no invented halving cycle ------------------------


def test_eth_and_sol_read_the_bitcoin_regime_not_their_own_halving():
    from tests.unit.test_decision_engine_v2 import FakeCache

    from crypto_intel.api.routes_cycle import _relative_strength
    from crypto_intel.engines.pit_view import PointInTimeView

    cache = FakeCache()
    from crypto_intel.core.enums import Timeframe

    cache.trend("BTC", Timeframe.D1, 120, slope=0.001)
    cache.trend("ETH", Timeframe.D1, 120, slope=0.004)
    view = PointInTimeView(cache, NOW)
    relative = _relative_strength(view, Asset.ETH)
    assert relative is not None
    assert relative["state"] == "OUTPERFORM"
    assert "n'a pas de halving" in relative["note"]
    assert _relative_strength(view, Asset.BTC) is None


def test_the_cycle_family_labels_eth_as_a_regime_not_a_cycle():
    from tests.unit.test_decision_engine_v2 import FakeCache

    from crypto_intel.core.enums import Timeframe
    from crypto_intel.engines.decision_families import cycle_family
    from crypto_intel.engines.pit_view import PointInTimeView

    cache = FakeCache()
    cache.trend("BTC", Timeframe.D1, 400, slope=0.002)
    cache.trend("ETH", Timeframe.D1, 400, slope=0.002)
    cache.trend("ETH", Timeframe.H1, 400, slope=0.002)
    cache.trend("BTC", Timeframe.H1, 400, slope=0.002)
    view = PointInTimeView(cache, NOW)
    result = cycle_family(view, Asset.ETH, DecisionHorizon.D30)
    labels = {m.label for m in result.metrics}
    assert "Régime Bitcoin" in labels
    assert "Cycle Bitcoin" not in labels


# --- 26.8  Later data never rewrites an archived snapshot -------------------


def test_an_archived_snapshot_is_never_rewritten_with_later_data():
    frame = _frame([100 * 1.004 ** i for i in range(700)])
    engine = BitcoinCycleRegimeEngine()
    first = engine.read(frame, [HALVING])
    month = datetime(2026, 3, 15, tzinfo=UTC)
    stored = write_snapshot(first, asset="TEST", now=month)
    assert stored is not None

    # The market crashes afterwards. A phase change may add a row, but the
    # row already written for March must be exactly what it was.
    crashed = _frame([*[100 * 1.004 ** i for i in range(700)],
                      *[100 * 1.004 ** 700 * 0.97 ** i for i in range(120)]])
    later = engine.read(crashed, [HALVING])
    extra = write_snapshot(later, asset="TEST", now=month)
    assert extra is None or extra["month"] != "2026-03"
    rows = [s for s in list_snapshots("TEST", limit=5) if s["month"] == "2026-03"]
    assert len(rows) == 1
    assert rows[0]["phase"] == stored["phase"]
    assert rows[0]["btc_price"] == pytest.approx(stored["btc_price"])
    assert rows[0]["drawdown_from_ath"] == pytest.approx(stored["drawdown_from_ath"])


def test_a_phase_change_adds_a_row_instead_of_editing_the_month():
    frame = _frame([100 * 1.004 ** i for i in range(700)])
    engine = BitcoinCycleRegimeEngine()
    month = datetime(2026, 5, 10, tzinfo=UTC)
    first = engine.read(frame, [HALVING])
    assert write_snapshot(first, asset="TEST2", now=month) is not None

    crashed = _frame([*[100 * 1.004 ** i for i in range(700)],
                      *[100 * 1.004 ** 700 * 0.97 ** i for i in range(200)]])
    later = engine.read(crashed, [HALVING])
    if later.phase != first.phase:
        extra = write_snapshot(later, asset="TEST2", now=month)
        assert extra is not None
        assert extra["month"].endswith("changement-de-phase")
    assert len(list_snapshots("TEST2", limit=5)) >= 1


def test_the_monthly_note_states_what_moved():
    frame = _frame([100 * 1.004 ** i for i in range(700)])
    regime = BitcoinCycleRegimeEngine().read(frame, [HALVING])
    assert changes_since(None, regime) == ["🆕 Première lecture archivée du cycle."]


# --- The timeline is causal -------------------------------------------------


def test_the_timeline_of_a_past_day_does_not_change_when_later_bars_arrive():
    prices = [100 * 1.004 ** i for i in range(700)]
    engine = BitcoinCycleRegimeEngine()
    early = engine.timeline(_frame(prices), [HALVING])
    late = engine.timeline(_frame([*prices, *[prices[-1] * 0.95 ** i for i in range(60)]]), [HALVING])
    assert [c.phase for _, c, _ in early] == [c.phase for _, c, _ in late[: len(early)]]


def test_the_vectorised_dimensions_match_the_day_by_day_reading():
    from crypto_intel.engines.cycle_regime import read_dimensions

    frame = _frame([100 + 30 * np.sin(i / 40) + i * 0.1 for i in range(600)])
    table = dimension_frame(frame, [HALVING])
    for position in (300, 450, 599):
        window = frame.iloc[: position + 1]
        day = window.index[-1].to_pydatetime()
        expected = read_dimensions(window, day, [HALVING])
        row = table.iloc[position]
        assert expected is not None
        assert row.structure == expected.structure
        assert row.momentum == expected.momentum
        assert float(row.drawdown_pct) == pytest.approx(expected.drawdown_pct, abs=1e-6)
        assert float(row.rebound_from_low_pct) == pytest.approx(
            expected.rebound_from_low_pct, abs=1e-6
        )


def test_normalised_cycles_start_at_one_hundred():
    frame = _frame([100 * 1.002 ** i for i in range(900)], start=datetime(2016, 1, 1, tzinfo=UTC))
    cycles = normalised_cycles(frame, [datetime(2016, 7, 9, tzinfo=UTC)],
                               as_of=frame.index[-1].to_pydatetime())
    assert cycles and cycles[0]["points"][0]["index"] == pytest.approx(100.0)
    assert cycles[0]["ongoing"] is True

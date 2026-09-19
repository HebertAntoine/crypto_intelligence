"""What the reader sees, and the regressions it must never show again.

Section 29 of the refactor lists them; each has a test here:
    RSI 77 read as "favourable" on its own; expanded Bollinger bands called
    tight; a raw whale transfer read as a sale; open interest alone read as
    unfavourable; implied volatility read as a direction; an advanced cycle
    turned into a SELL; a Fed rate invented without a source; a USD level
    shown without its unit next to a EUR price; stale data used as a live
    signal; a 30-day value reused blindly for the 24-hour call.
"""

from datetime import UTC, datetime, timedelta

import pandas as pd
from tests.unit.test_decision_engine_v2 import NOW, FakeCache, all_families, family, view

from crypto_intel.core.enums import Asset, Timeframe
from crypto_intel.engines.decision_config import (
    CYCLE,
    DERIVATIVES,
    FLOWS,
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
    MetricReading,
    central_banks,
    derivatives_family,
    flows_family,
    liquidation_totals,
    read_metric,
    spot_pressure,
)
from crypto_intel.engines.decision_gates import ExternalChecks, FinalAction, decide
from crypto_intel.engines.decision_presentation import (
    present_derivatives,
    present_flows,
    present_macro,
    present_onchain,
    present_technical,
)
from crypto_intel.engines.key_levels import find_key_levels
from crypto_intel.engines.whales import (
    WhaleEntityType,
    WhaleIntelligenceEngine,
    WhaleObservation,
    WhaleState,
)
from crypto_intel.future_events.models import DecisionHorizon
from crypto_intel.providers.macro.central_bank_rates import (
    parse_boj_series,
    parse_ecb_series,
    parse_nyfed_targets,
    rate_changes,
)


def _reading(key, value, *, label=None, available_at=NOW, estimated=False, state="NEUTRAL"):
    return MetricReading(
        key=key, label=label or key, emoji="", status=DataStatus.AVAILABLE, value=value,
        display_value=str(value), available_at=available_at, state=state,
        publication_estimated=estimated,
    )


def _technical(rsi=77.0, bw_pct=92.0, price=81_600.0, resistance=84_000.0, support=75_065.0):
    fam = family(TECHNICAL, 40, extra={
        "quote": "USDT", "price": price, "fast_ma": 79_000.0, "slow_ma": 78_000.0,
        "ma_kind": "EMA", "fast": 20, "slow": 50, "trend_signal": 0.8,
        "changes": {1: 6.4, 7: 5.3, 30: 17.3}, "structure": "TREND_UP",
        "structure_label": "Tendance haussière", "support": support,
        "resistance": resistance, "rsi": rsi, "bollinger_percentile": bw_pct,
        "support_detail": {"explanation": "Support issu du creux du 02/09/2026, testé 2 fois."},
        "resistance_detail": {"explanation": "Résistance issue du sommet du 28/08/2026, testée 3 fois."},
    })
    fam.metrics = [
        _reading("technical.rsi", rsi, label="RSI 14"),
        _reading("technical.bollinger_bandwidth", 0.1),
    ]
    return fam


def _rows(view_: dict) -> dict[str, dict]:
    return {r["label"]: r for s in view_["sections"] for r in s["rows"]}


def _texts(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [t for v in value.values() for t in _texts(v)]
    if isinstance(value, list):
        return [t for v in value for t in _texts(v)]
    return []


# --- 29.1  RSI 77 is never "favourable" on its own --------------------------


def test_an_overbought_uptrend_is_up_but_its_timing_is_stretched():
    fam = _technical(rsi=77)
    view_ = present_technical(fam)

    assert view_["trend"]["label"] == "Haussière"
    assert _rows(view_)["🔥 Timing"]["value"] == "Marché étiré"
    assert next(m for m in fam.metrics if m.key == "technical.rsi").state == "CAUTION"
    assert "Favorable" not in _texts(view_)

    families = all_families({MACRO: 10, LIQUIDITY: 5, FLOWS: 20, DERIVATIVES: 10})
    families[TECHNICAL] = _technical(rsi=77)
    summary = decide(families, DecisionHorizon.D7).summary
    assert summary["trend"]["label"] == "Haussière"
    assert summary["entry_quality"]["label"] != "Favorable"


def test_a_stretched_market_holds_a_buy_at_the_technical_setup():
    families = all_families({MACRO: 60, LIQUIDITY: 50, FLOWS: 60, DERIVATIVES: 40})
    families[TECHNICAL] = _technical(rsi=78)
    families[TECHNICAL].score = 70
    decision = decide(families, DecisionHorizon.D7)
    assert decision.action is FinalAction.WAIT
    assert decision.blocking_gate == "TECHNICAL_SETUP"


# --- 29.2  Expanded bands are never "tight" ---------------------------------


def test_expanded_bollinger_bands_are_never_called_tight():
    fam = _technical(bw_pct=92)
    present_technical(fam)
    bollinger = next(m for m in fam.metrics if m.key == "technical.bollinger_bandwidth")
    assert "expansion" in bollinger.why
    assert "resserr" not in bollinger.why

    tight = _technical(bw_pct=8)
    present_technical(tight)
    assert "resserr" in next(m for m in tight.metrics if m.key == "technical.bollinger_bandwidth").why


# --- 29.3  A raw whale transfer is never a sale -----------------------------


def _whale(from_type, to_type, amount=50e6):
    return WhaleObservation(
        id=f"tx-{from_type}-{to_type}-{amount}", asset=Asset.BTC, observed_at=NOW,
        amount_usd=amount, from_type=from_type, to_type=to_type, provider="test", confidence=0.8,
    )


def test_a_raw_whale_transfer_is_never_read_as_a_sale():
    engine = WhaleIntelligenceEngine()
    unknown = engine.analyze(Asset.BTC, [_whale(WhaleEntityType.UNKNOWN, WhaleEntityType.UNKNOWN)])
    assert unknown.potential_sell_pressure is None
    assert unknown.state is WhaleState.NEUTRAL

    deposit = engine.analyze(Asset.BTC, [_whale(WhaleEntityType.WALLET, WhaleEntityType.EXCHANGE)])
    assert any("sans preuve de vente" in f for f in deposit.factors)
    assert not deposit.is_certainty

    onchain = FamilyScore(family=ONCHAIN, horizon="7d", status=DataStatus.UNAVAILABLE)
    view_ = present_onchain(onchain)
    texts = " ".join(_texts(view_)).lower()
    assert "vente baleine" not in texts
    assert "données directionnelles insuffisantes" in texts
    assert view_["hide_on_home"] is True
    assert len(view_["sections"]) == 1 and len(view_["sections"][0]["rows"]) == 1


# --- 29.4  Open interest alone is context -----------------------------------


def test_open_interest_alone_is_context_never_unfavourable():
    fam = family(DERIVATIVES, 10, extra={"crowding": "QUIET", "crowding_label": "Calme",
                                         "funding_percentile": 50.0, "oi_percentile": 90.0})
    fam.metrics = [_reading("oi.value_history", 8.8, state="UNFAVORABLE")]
    present_derivatives(fam)
    assert fam.metrics[0].state == "CONTEXT"


# --- 29.5  Implied volatility never predicts a direction --------------------


def test_implied_volatility_has_no_direction():
    cache = FakeCache()
    cache.add("dvol.index", [40.0] * 700 + [95.0], asset="BTC", source="Deribit (historique)")
    result = derivatives_family(view(cache), Asset.BTC, DecisionHorizon.D7)
    assert all("dvol" not in c.key for c in result.components)

    fam = family(DERIVATIVES, 0, extra={"crowding": "QUIET", "dvol_percentile": 97.0})
    view_ = present_derivatives(fam)
    vol = next(s for s in view_["sections"] if s["title"] == "Volatilité anticipée")
    assert vol["rows"][0]["value"] == "Élevée"
    assert "jamais sa direction" in vol["why"]


# --- 29.6  An advanced cycle never triggers a SELL --------------------------


def test_an_advanced_cycle_alone_never_sells():
    families = all_families({MACRO: 0, LIQUIDITY: 0, FLOWS: 0, DERIVATIVES: 0, TECHNICAL: 0},
                            horizon=DecisionHorizon.D30)
    cycle = family(CYCLE, -100, horizon=DecisionHorizon.D30,
                   extra={"cycle": {"phase": "POST_ATH_DRAWDOWN", "phase_label": "Repli après le sommet"}})
    families[CYCLE] = cycle
    decision = decide(families, DecisionHorizon.D30)
    assert decision.action is not FinalAction.SELL
    assert CYCLE not in decision.confirming_families


def test_the_cycle_never_counts_as_a_confirming_family():
    families = all_families({MACRO: 50, LIQUIDITY: 40, FLOWS: 60, DERIVATIVES: 20, TECHNICAL: 60})
    families[CYCLE] = family(CYCLE, 40, extra={"cycle": {"phase": "EXPANSION"}})
    decision = decide(families, DecisionHorizon.D7)
    assert CYCLE not in decision.confirming_families


# The phase rules and their regressions live with the cycle engine, in
# tests/unit/test_cycle_regime.py.


# --- 29.7  No expected Fed rate without a pricing source --------------------


def test_the_next_fed_rate_is_never_invented():
    cache = FakeCache()
    cache.add("cb.fed.target_upper", [4.0] * 30 + [4.25] * 5)
    cache.add("cb.fed.target_lower", [3.75] * 30 + [4.0] * 5)
    banks = central_banks(view(cache))
    fed = next(b for b in banks if b["key"] == "fed")
    assert fed["expectation"] is None
    assert fed["expectation_label"] == "Anticipation de marché indisponible"
    assert fed["last_decision"]["label"] == "Hausse de 25 pb"
    assert fed["rate_label"] == "4,00 – 4,25 %"


def test_a_meeting_within_48_hours_makes_the_bank_critical():
    cache = FakeCache()
    cache.add("cb.fed.target_upper", [4.0] * 30)
    cache._meetings = [("Federal Reserve", NOW + timedelta(hours=30), "FOMC")]
    fed = next(b for b in central_banks(view(cache)) if b["key"] == "fed")
    assert fed["importance"] == "CRITICAL"

    far = FakeCache()
    far.add("cb.fed.target_upper", [4.0] * 30)
    far._meetings = [("Federal Reserve", NOW + timedelta(days=30), "FOMC")]
    assert next(b for b in central_banks(view(far)) if b["key"] == "fed")["importance"] == "MEDIUM"


def test_central_bank_parsers_read_the_official_payloads():
    fed = parse_nyfed_targets({"refRates": [
        {"effectiveDate": "2026-09-17", "targetRateFrom": 3.75, "targetRateTo": 4.0},
    ]})
    assert fed[0][1:] == (3.75, 4.0)
    ecb = parse_ecb_series({
        "dataSets": [{"series": {"0": {"observations": {"0": [2.25], "1": [2.5]}}}}],
        "structure": {"dimensions": {"observation": [{"values": [{"id": "2026-09-15"}, {"id": "2026-09-16"}]}]}},
    })
    assert [v for _, v in ecb] == [2.25, 2.5]
    assert rate_changes(ecb)[0][1:] == (2.25, 2.5)
    boj = parse_boj_series({"RESULTSET": [{"VALUES": {"SURVEY_DATES": [20260916, 20260917],
                                                      "VALUES": [0.977, ""]}}]})
    assert boj == [(datetime(2026, 9, 16, tzinfo=UTC), 0.977)]


# --- 29.8  A USD level is never shown without its unit ----------------------


def test_every_technical_level_carries_its_dollar_unit():
    rows = _rows(present_technical(_technical()))
    for label in ("🟢 Support clé", "🔴 Prochaine résistance"):
        assert rows[label]["value"].endswith("$"), label
    assert "testée 3 fois" in rows["🔴 Prochaine résistance"]["detail"]


def test_key_levels_come_from_tested_pivots():
    index = pd.date_range(end=NOW, periods=300, freq="4h", tz="UTC")
    wave = [100 + 10 * ((i // 20) % 2) for i in range(300)]  # tops at 110, bottoms at 100
    frame = pd.DataFrame({"open": wave, "high": [w + 1 for w in wave], "low": [w - 1 for w in wave],
                          "close": wave, "volume": 1.0}, index=index)
    frame.iloc[-1, frame.columns.get_loc("close")] = 105.0
    support, resistance, _ = find_key_levels(frame, "4h", lookback=3)
    assert resistance is not None and resistance.price > 105
    assert support is not None and support.price < 105
    assert resistance.touches >= 2
    assert resistance.to_dict()["label"].endswith("$")


# --- 29.9  Stale data is never an active signal -----------------------------


def test_stale_spot_flow_hours_never_drive_the_spot_reading():
    cache = FakeCache()
    old_end = NOW - timedelta(days=5)
    cache.add("spot.flow.buy_usd.binance", [60.0] * 48, asset="BTC", step=timedelta(hours=1), end=old_end)
    cache.add("spot.flow.sell_usd.binance", [40.0] * 48, asset="BTC", step=timedelta(hours=1), end=old_end)
    pressure = spot_pressure(view(cache), Asset.BTC, DecisionHorizon.H24)
    assert pressure is not None and pressure["usable"] is False
    result = flows_family(view(cache), Asset.BTC, DecisionHorizon.H24)
    assert all(c.key != "spot" for c in result.components)


def test_stale_macro_series_is_shown_but_not_used():
    cache = FakeCache()
    cache.add("macro.dxy", [100 + i * 0.1 for i in range(60)], end=NOW - timedelta(days=30))
    reading = read_metric(view(cache), "macro.dxy", window=timedelta(days=7))
    assert reading.status is DataStatus.STALE
    assert not reading.usable


# --- 29.10  Each horizon reads its own window -------------------------------


def _hourly_flows(cache: FakeCache, buys: list[float], sells: list[float], exchange="binance"):
    end = NOW.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
    cache.add(f"spot.flow.buy_usd.{exchange}", buys, asset="BTC", step=timedelta(hours=1), end=end)
    cache.add(f"spot.flow.sell_usd.{exchange}", sells, asset="BTC", step=timedelta(hours=1), end=end)


def test_the_24h_spot_reading_is_not_the_30d_one():
    cache = FakeCache()
    hours = 24 * 40
    # Sellers for weeks, buyers in the last day.
    buys = [40.0] * (hours - 24) + [70.0] * 24
    sells = [60.0] * (hours - 24) + [30.0] * 24
    _hourly_flows(cache, buys, sells)
    day = spot_pressure(view(cache), Asset.BTC, DecisionHorizon.H24)
    month = spot_pressure(view(cache), Asset.BTC, DecisionHorizon.D30)
    assert day["usable"] and month["usable"]
    assert day["share"] > 0.6
    assert month["share"] < 0.5


def test_an_exchange_with_gaps_is_left_out_not_averaged_in():
    cache = FakeCache()
    _hourly_flows(cache, [50.0] * 48, [50.0] * 48, "binance")
    _hourly_flows(cache, [90.0] * 48, [10.0] * 48, "bybit")  # no coverage minutes stored
    pressure = spot_pressure(view(cache), Asset.BTC, DecisionHorizon.H24)
    assert pressure["exchanges"] == ["binance"]
    assert abs(pressure["share"] - 0.5) < 1e-9


def test_liquidations_are_not_totalled_on_a_partial_stream():
    cache = FakeCache()
    end = NOW.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
    cache.add("liq.long_usd.bybit", [1e6] * 5, asset="BTC", step=timedelta(hours=1), end=end)
    cache.add("stream.bybit_liq.minutes", [60.0] * 5, asset="BTC", step=timedelta(hours=1), end=end)
    totals = liquidation_totals(view(cache), Asset.BTC)
    assert totals["reading"].status is not DataStatus.AVAILABLE
    assert totals["stream_started"] is True

    full = FakeCache()
    full.add("liq.long_usd.bybit", [3e6] * 24, asset="BTC", step=timedelta(hours=1), end=end)
    full.add("liq.short_usd.bybit", [1e6] * 24, asset="BTC", step=timedelta(hours=1), end=end)
    full.add("stream.bybit_liq.minutes", [60.0] * 24, asset="BTC", step=timedelta(hours=1), end=end)
    totals = liquidation_totals(view(full), Asset.BTC)
    assert totals["reading"].usable
    assert totals["dominance"] == "LONGS"
    assert totals["24h"]["long_usd"] == 72e6


# --- Spot, macro and summary layout -----------------------------------------


def test_spot_pressure_says_who_takes_the_initiative_never_money_in():
    fam = family(FLOWS, 20)
    fam.metrics = [_reading("spot.pressure", 54.0)]
    fam.extra = {"spot": {"source": "hourly", "share": 0.54, "buy_usd": 412e6, "sell_usd": 351e6,
                          "delta_usd": 61e6, "trend": "UP", "exchanges": ["binance", "okx"],
                          "window": "24 h", "coverage": {"binance": 1.0, "okx": 1.0, "bybit": 0.2}}}
    view_ = present_flows(fam)
    rows = _rows(view_)
    assert rows["Achats agressifs"]["value"] == "54 %"
    assert rows["Achats agressifs"]["detail"] == "412 M$"
    assert rows["Delta"]["value"] == "+61 M$"
    assert view_["sections"][0]["verdict"] == "🟢 Pression acheteuse modérée"
    text = " ".join(_texts(view_)).lower()
    assert "ont été achetés" not in text and "capitaux entrent" not in text


def test_secondary_macro_inputs_only_surface_on_abnormal_moves():
    fam = family(MACRO, -30)
    fam.components = [Component("dollar", "Dollar", 1.0, -0.8, ""), Component("oil_shock", "Pétrole", 0.5, -0.1, "")]
    dxy = _reading("macro.dxy", 101.0)
    dxy.delta = 1.4
    dxy.delta_label = "+1,4 % sur 7 j"
    oil = _reading("macro.oil_wti", 80.0)
    oil.delta = 0.3
    fam.metrics = [dxy, oil]
    fam.extra = {"central_banks": []}
    view_ = present_macro(fam, NOW)
    notable = next(s for s in view_["sections"] if s["title"] == "Mouvements notables")
    assert [r["label"] for r in notable["rows"]] == ["💵 Dollar fortement en hausse"]
    assert oil.importance != "HIGH"


def test_a_monthly_release_names_its_period_not_a_fake_update_date():
    cache = FakeCache()
    cache.add("macro.core_cpi", [300 + i for i in range(14)], step=timedelta(days=30),
              end=NOW - timedelta(days=35), delay=timedelta(days=15))
    reading = read_metric(view(cache), "macro.core_cpi", window=timedelta(days=365))
    assert reading.period_label and not reading.period_label[0].isdigit()


def test_validation_is_separate_and_never_a_reason():
    families = all_families({MACRO: 50, LIQUIDITY: 40, FLOWS: 60, DERIVATIVES: 20, TECHNICAL: 60})
    decision = decide(families, DecisionHorizon.D7,
                      ExternalChecks(consistency_codes=["NO_MEASURABLE_EDGE"]))
    summary = decision.summary

    assert summary["validation"]["status"] == "NO_EDGE"
    assert "prudence renforcée" in summary["validation"]["message"]
    assert len(summary["reasons"]) <= 3
    assert all("avantage" not in (r["title"] + r["detail"]) for r in summary["reasons"])
    assert summary["confidence_label"].startswith("Confiance ")
    assert "%" not in summary["confidence_label"]


def test_the_home_lists_six_families_and_hides_silent_whales():
    families = all_families({MACRO: 10, LIQUIDITY: 5, FLOWS: 20, DERIVATIVES: 10, TECHNICAL: 20})
    families[CYCLE] = family(CYCLE, 10, extra={"cycle": {
        "phase": "RECOVERY", "phase_label": "Récupération", "phase_emoji": "🔵",
        "tone": "BLUE", "direction_label": "Amélioration", "direction_emoji": "↗️",
        "days_in_phase": 29,
        "dimensions": {"drawdown_pct": -35.0, "days_since_halving": 882},
    }})
    summary = decide(families, DecisionHorizon.D7, ExternalChecks(asset="BTC")).summary
    names = [f["family"] for f in summary["home_families"]]
    assert names == [TECHNICAL, DERIVATIVES, FLOWS, MACRO, CYCLE]
    cycle_line = summary["home_families"][-1]
    assert cycle_line["key_info"] == "882 j depuis le halving · -35 % sous l'ATH"
    assert cycle_line["status"].startswith("Récupération")


def test_a_sell_needs_a_structural_break():
    families = all_families({MACRO: -50, LIQUIDITY: -40, FLOWS: -60, DERIVATIVES: -20, TECHNICAL: -60})
    families[TECHNICAL].extra["structure"] = "RANGE"
    decision = decide(families, DecisionHorizon.D7)
    assert decision.action is FinalAction.WAIT
    assert decision.blocking_gate == "TECHNICAL_SETUP"


def test_a_buy_waits_when_sellers_lead_on_spot():
    families = all_families({MACRO: 60, LIQUIDITY: 50, FLOWS: -40, DERIVATIVES: 60, TECHNICAL: 70})
    decision = decide(families, DecisionHorizon.D7)
    assert decision.action is FinalAction.WAIT
    assert decision.blocking_gate in {"SPOT_CONFIRMATION", "CONTRADICTION"}


def test_trend_entry_and_risk_are_three_fields():
    families = all_families({MACRO: 10, LIQUIDITY: 5, FLOWS: 20, DERIVATIVES: 10, TECHNICAL: 20})
    summary = decide(families, DecisionHorizon.D7).summary
    assert {"trend", "entry_quality", "risk"} <= set(summary)
    assert summary["trend"]["label"] in {"Haussière", "Neutre", "Baissière"}
    assert summary["entry_quality"]["label"] in {"Favorable", "Mitigé", "Défavorable"}
    assert summary["risk"]["label"] in {"Faible", "Modéré", "Élevé"}


def test_family_state_enum_is_untouched():
    # The presentation reads states; it never adds one.
    assert {s.value for s in FamilyState} >= {"POSITIVE", "NEGATIVE", "NEUTRAL"}


def test_a_hourly_candle_frame_is_known_only_once_closed():
    cache = FakeCache()
    cache.trend("BTC", Timeframe.H1, 50)
    frame = view(cache).candles("BTC", Timeframe.H1)
    assert frame.index[-1] <= pd.Timestamp(NOW) - pd.Timedelta(hours=1)

"""What the reader sees: trend, entry quality and risk kept apart, few reasons.

The scores are not under test here - only how they are turned into sections,
home lines and triggers.
"""

from datetime import timedelta

from tests.unit.test_decision_engine_v2 import NOW, FakeCache, all_families, family, view

from crypto_intel.engines.decision_config import (
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
    MetricReading,
    read_metric,
)
from crypto_intel.engines.decision_gates import ExternalChecks, decide
from crypto_intel.engines.decision_presentation import (
    present_derivatives,
    present_flows,
    present_macro,
    present_technical,
)
from crypto_intel.future_events.models import DecisionHorizon


def _reading(key, value, *, label=None, available_at=NOW, estimated=False, state="NEUTRAL"):
    return MetricReading(
        key=key, label=label or key, emoji="", status=DataStatus.AVAILABLE, value=value,
        display_value=str(value), available_at=available_at, state=state,
        publication_estimated=estimated,
    )


def _technical(rsi=77.0, bw_pct=92.0, price=81_600.0, resistance=82_000.0):
    fam = family(TECHNICAL, 40, extra={
        "quote": "USDT", "price": price, "fast_ma": 79_000.0, "slow_ma": 78_000.0,
        "ma_kind": "EMA", "fast": 20, "slow": 50, "trend_signal": 0.8,
        "changes": {1: 6.4, 7: 5.3, 30: 17.3}, "structure": "TREND_UP",
        "structure_label": "Tendance haussière", "support": 75_065.0,
        "resistance": resistance, "rsi": rsi, "bollinger_percentile": bw_pct,
    })
    fam.metrics = [_reading("technical.rsi", rsi, label="RSI 14"),
                   _reading("technical.bollinger_bandwidth", 0.1)]
    return fam


def test_an_overbought_uptrend_is_up_but_stretched_never_favourable():
    view_ = present_technical(_technical(rsi=77))

    assert view_["trend"]["label"] == "Haussière"
    assert view_["momentum"]["stretched"]
    assert view_["home"]["status"] == "Haussière mais étirée"
    rsi = next(r for s in view_["sections"] for r in s["rows"] if r["metric"] == "technical.rsi")
    assert rsi["tone"] == "ORANGE"

    families = all_families({MACRO: 10, LIQUIDITY: 5, FLOWS: 20, DERIVATIVES: 10})
    families[TECHNICAL] = _technical(rsi=77)
    summary = decide(families, DecisionHorizon.D7).summary
    assert summary["trend"]["label"] == "Haussière"
    assert summary["entry_quality"]["label"] != "Favorable"


def test_expanded_bollinger_bands_are_never_called_tight():
    wide = present_technical(_technical(bw_pct=92))
    vol = next(s for s in wide["sections"] if s["title"] == "Volatilité")
    assert "expansion" in vol["sentence"]
    assert "resserr" not in vol["sentence"]

    tight = present_technical(_technical(bw_pct=8))
    assert "resserr" in next(s for s in tight["sections"] if s["title"] == "Volatilité")["sentence"]


def test_technical_levels_state_their_dollar_quote_and_performance_is_one_line():
    sections = present_technical(_technical())["sections"]
    rows = {r["label"]: r["value"] for s in sections for r in s["rows"]}
    assert rows["EMA20"].endswith("$")
    assert rows["🟢 Support"].endswith("$")
    performance = next(s for s in sections if s["title"] == "Performance")
    assert len(performance["rows"]) == 1
    assert "24 h +6,4 %" in performance["rows"][0]["value"]


def test_a_broken_resistance_is_not_shown_as_overhead():
    rows = {r["label"] for s in present_technical(_technical(price=81_600, resistance=79_600))["sections"]
            for r in s["rows"]}
    assert "🧱 Ancienne résistance (franchie)" in rows
    assert "🔴 Résistance" not in rows


def test_open_interest_alone_is_context_and_missing_liquidations_take_one_line():
    fam = family(DERIVATIVES, 10, extra={"crowding": "QUIET", "crowding_label": "Calme",
                                         "funding_percentile": 50.0, "oi_percentile": 60.0})
    fam.metrics = [_reading("oi.value_history", 8.8, state="FAVORABLE")]
    view_ = present_derivatives(fam)

    assert fam.metrics[0].state == "CONTEXT"
    liquidations = next(s for s in view_["sections"] if s["title"] == "Liquidations")
    assert len(liquidations["rows"]) == 1
    assert "indisponible" in liquidations["rows"][0]["value"]


def test_etf_and_spot_disagreeing_is_mixed_never_capital_flowing_in():
    fam = family(FLOWS, 20)
    fam.headline = "Les capitaux entrent."
    fam.components = [Component("etf", "ETF", 0.5, 0.05, ""), Component("spot", "Spot", 0.5, 0.6, "")]
    view_ = present_flows(fam)

    assert view_["sections"][0]["verdict"] == "🟠 Flux global mitigé"
    assert "capitaux entrent" not in fam.headline
    assert "Demande spot positive" in fam.headline


def test_macro_priorities_follow_recency():
    fam = family(MACRO, -30)
    fresh = NOW - timedelta(days=2)
    old = NOW - timedelta(days=40)
    fam.metrics = [
        _reading("macro.real10y", 2.7),
        _reading("macro.sp500", 7650),
        _reading("macro.cpi", 0.3, available_at=old, estimated=True),
        _reading("macro.core_cpi", 0.4, available_at=fresh, estimated=True),
    ]
    present_macro(fam, NOW)
    priority = {m.key: m.priority for m in fam.metrics}
    assert priority["macro.real10y"] == 1
    assert priority["macro.sp500"] == 3
    assert priority["macro.cpi"] == 3
    assert priority["macro.core_cpi"] == 1


def test_a_monthly_release_names_its_period_not_a_fake_update_date():
    cache = FakeCache()
    cache.add("macro.core_cpi", [300 + i for i in range(14)], step=timedelta(days=30),
              end=NOW - timedelta(days=35), delay=timedelta(days=15))
    reading = read_metric(view(cache), "macro.core_cpi", window=timedelta(days=365))
    assert reading.period_label and not reading.period_label[0].isdigit()
    assert reading.to_dict()["published_at"] != reading.to_dict().get("period_label")


def test_validation_is_separate_and_never_a_reason():
    families = all_families({MACRO: 50, LIQUIDITY: 40, FLOWS: 60, DERIVATIVES: 20, TECHNICAL: 60})
    decision = decide(families, DecisionHorizon.D7,
                      ExternalChecks(consistency_codes=["NO_MEASURABLE_EDGE"]))
    summary = decision.summary

    assert summary["validation"]["status"] == "NO_EDGE"
    assert "prudence renforcée" in summary["validation"]["message"]
    assert len(summary["reasons"]) <= 3
    assert all("avantage" not in (r["title"] + r["detail"]) for r in summary["reasons"])
    assert [f["family"] for f in summary["home_families"]] == [
        TECHNICAL, DERIVATIVES, MACRO, FLOWS, ONCHAIN,
    ]
    assert summary["confidence_label"].startswith("Confiance ")
    assert "%" not in summary["confidence_label"]

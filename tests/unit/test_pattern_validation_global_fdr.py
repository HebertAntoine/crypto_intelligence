"""The published pattern study gets one false-discovery budget, not one per asset."""

from __future__ import annotations

from crypto_intel.research.pattern_validation import _apply_global_multiple_testing


def _series(p_value: float) -> dict:
    return {
        "status": "OK",
        "multiple_testing": {"scope": "WITHIN_SERIES"},
        "patterns": {
            "double_top": {
                "raw_occurrences": 100,
                "horizons": {
                    "14d": {
                        "p_value": p_value,
                        "excess_vs_regime_baseline_pct": -3.0,
                        "effective_n": 30.0,
                        "stability": {"verdict": "STABLE"},
                    }
                },
            }
        },
    }


def test_fdr_is_applied_once_across_all_assets():
    results = {"BTC_1d": _series(0.01), "ETH_1d": _series(0.20)}

    _apply_global_multiple_testing(results)

    for result in results.values():
        testing = result["multiple_testing"]
        assert testing["scope"] == "GLOBAL_RUN"
        assert testing["hypotheses_tested"] == 2
        assert testing["survives_fdr"] == 1
        assert testing["survivors"] == ["BTC_1d|double_top|14d"]
        assert testing["within_series_diagnostic"] == {"scope": "WITHIN_SERIES"}
    assert results["BTC_1d"]["patterns"]["double_top"]["verdict"] == "MEASURABLE_EDGE"
    assert results["ETH_1d"]["patterns"]["double_top"]["verdict"] == "NO_MEASURABLE_EDGE"

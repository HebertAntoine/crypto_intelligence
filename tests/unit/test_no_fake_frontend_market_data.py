from __future__ import annotations

from pathlib import Path

APP_LIB = Path(__file__).resolve().parents[2] / "app" / "lib"


def _dart_sources() -> list[Path]:
    return sorted(APP_LIB.rglob("*.dart"))


def test_flutter_production_code_has_no_hardcoded_market_prices():
    forbidden = [
        "€52 840",
        "€2 210",
        "€128",
        "+2,4 %",
        "+1,8 %",
        "52840",
        "2210",
        "81634.80",
        "84200",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in _dart_sources())
    for token in forbidden:
        assert token not in combined


def test_flutter_chart_does_not_draw_synthetic_market_candles():
    chart_screen = APP_LIB / "screens" / "chart_screen.dart"
    text = chart_screen.read_text(encoding="utf-8")
    assert "_syntheticCandle" not in text
    assert "_chartValues" not in text
    assert "Bougies OHLCV indisponibles" in text

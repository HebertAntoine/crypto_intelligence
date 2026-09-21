"""Lexa: a separate, local, immutable record of what the videos said.

Pinned here:
  - allocations scale with the capital, levels never move (100 / 200 / 500 €)
  - a missing allocation is an announced assumption, never a silent one
  - the simulation follows the prices after the video, bar by bar
  - a touch is not a confirmation; a confirmation needs the stated condition
  - a correction keeps the original value
  - two videos on the same crypto are two scenarios, the first is untouched
  - the routes answer this machine only, and are never exported
"""

from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from crypto_intel.lexa.levels import track
from crypto_intel.lexa.simulation import SimLevel, allocate, simulate

T0 = datetime(2026, 9, 21, 8, tzinfo=UTC)


@pytest.fixture(autouse=True)
def lexa_db(tmp_path, monkeypatch):
    monkeypatch.setenv("LEXA_DATABASE_PATH", str(tmp_path / "lexa" / "lexa.db"))
    from crypto_intel.lexa import store

    store.reset_engine()
    yield
    store.reset_engine()


def _hourly(prices: list[float], start: datetime = T0) -> pd.DataFrame:
    index = pd.date_range(start=start, periods=len(prices), freq="h", tz="UTC")
    return pd.DataFrame({
        "open": prices, "high": [p * 1.001 for p in prices],
        "low": [p * 0.999 for p in prices], "close": prices,
    }, index=index)


XRP_LEVELS = [
    SimLevel(1, "BUY_ZONE", 2.15696, 60),
    SimLevel(2, "REINFORCEMENT", 2.06397, 40),
    SimLevel(3, "TARGET", 2.60763, 25),
    SimLevel(4, "TARGET", 2.72748, 25),
    SimLevel(5, "TARGET", 2.89272, 25),
    SimLevel(6, "TARGET", 3.00084, 25),
]


# --- capital and allocations ------------------------------------------------


@pytest.mark.parametrize(("capital", "first", "second"), [(100, 60, 40), (200, 120, 80), (500, 300, 200)])
def test_allocations_scale_with_the_capital(capital, first, second):
    allocations, notes = allocate(capital, XRP_LEVELS)
    assert allocations[1] == pytest.approx(first)
    assert allocations[2] == pytest.approx(second)
    assert notes == []


def test_a_missing_allocation_is_an_announced_assumption():
    allocations, notes = allocate(100, [SimLevel(1, "BUY_ZONE", 10.0, 60), SimLevel(2, "REINFORCEMENT", 9.0)])
    assert allocations[2] == pytest.approx(40)
    assert any("hypothèse" in note for note in notes)


# --- simulation -------------------------------------------------------------


def test_the_xrp_scenario_is_simulated_on_the_prices_after_the_video():
    # 1,38 -> down through both entries -> up through the first two targets.
    path = [2.346, 2.21, 2.142, 2.057, 2.125, 2.38, 2.635, 2.737, 2.686]
    result = simulate(XRP_LEVELS, _hourly(path), capital_eur=100, published_at=T0)
    assert result.executed_eur == pytest.approx(100)
    assert [f.level_id for f in result.fills] == [1, 2]
    assert result.targets_hit == [3, 4]
    assert result.average_price == pytest.approx(100 / (60 / 2.15696 + 40 / 2.06397))
    assert result.performance_pct is not None and result.performance_pct > 0
    assert "pas une recommandation" in result.to_dict()["disclaimer"]


def test_nothing_is_bought_before_the_video_or_above_the_zone():
    before = T0 - timedelta(hours=5)
    path = [2.04, 2.04, 2.04, 2.04, 2.04, 2.38, 2.414, 2.465]  # cheap only before the video
    result = simulate(XRP_LEVELS, _hourly(path, before), capital_eur=100, published_at=T0)
    assert result.fills == []
    assert result.remaining_eur == pytest.approx(100)


def test_an_invalidation_is_flagged_but_nothing_is_sold_without_a_rule():
    levels = [SimLevel(1, "BUY_ZONE", 100.0, 100)]
    result = simulate(levels, _hourly([105, 99, 90, 85]), capital_eur=100,
                      published_at=T0, invalidation=88.0)
    assert result.invalidation_reached is True
    assert result.quantity_held > 0
    assert any("ne vend pas" in note for note in result.assumptions)


# --- level states -----------------------------------------------------------


def test_a_touch_without_a_stated_condition_is_never_a_confirmation():
    state = track("CONFIRMATION", 2.444175, "UNKNOWN", _hourly([2.346, 2.448, 2.465, 2.482]), T0)
    assert state.state == "TOUCHED"
    assert "Aucune condition" in state.note


def test_a_confirmation_needs_the_stated_close():
    # Wick above 2.444175 on the hourly, but no 4-hour close above it.
    wick = _hourly([2.38, 2.38, 2.38, 2.38, 2.397, 2.414, 2.397, 2.38])
    wick.iloc[2, wick.columns.get_loc("high")] = 2.465
    assert track("CONFIRMATION", 2.444175, "CLOSE_4H_ABOVE", wick, T0).state != "CONFIRMED"

    held = _hourly([2.38, 2.448, 2.465, 2.482, 2.499, 2.499, 2.516, 2.516])
    state = track("CONFIRMATION", 2.444175, "CLOSE_4H_ABOVE", held, T0)
    assert state.state == "CONFIRMED"
    assert state.confirmed_at is not None


def test_a_confirmation_tested_then_lost_says_so():
    state = track("CONFIRMATION", 2.444175, "UNKNOWN", _hourly([2.346, 2.465, 2.38, 2.312]), T0)
    assert state.state == "TESTED_LOST"


def test_levels_without_prices_are_not_watched():
    assert track("BUY_ZONE", 2.15696, "UNKNOWN", None, T0).state == "NOT_WATCHED"


def test_first_and_last_touches_are_kept():
    state = track("BUY_ZONE", 100.0, "UNKNOWN", _hourly([105, 99, 104, 98, 103]), T0)
    assert state.first_touched_at < state.last_touched_at


# --- storage ----------------------------------------------------------------


def _video(title: str, when: datetime, buy: float) -> int:
    from crypto_intel.lexa.repository import AssetInput, LevelInput, create_video

    return create_video(title=title, published_at=when, assets=[AssetInput(
        asset="XRP", price_at_video=2.346, stance="WAIT",
        levels=[LevelInput(kind="BUY_ZONE", value=buy, allocation_pct=60, timestamp="18:42",
                           source_text="la zone d'achat se situe vers 1,26")],
    )])


def test_two_videos_are_two_scenarios_and_the_first_is_untouched(monkeypatch):
    from crypto_intel.lexa import repository

    monkeypatch.setattr(repository, "_price_frame", lambda *_: None)
    _video("Analyse du 18/09", T0 - timedelta(days=3), 2.125)
    _video("Analyse du 21/09", T0, 2.15696)
    history = repository.asset_history("XRP")
    assert [a["levels"][0]["value"] for a in history] == [2.15696, 2.125]
    assert history[0]["levels"][0]["timestamp"] == "18:42"
    assert history[0]["origin"] == "LEXA"


def test_a_correction_keeps_the_original_value(monkeypatch):
    from crypto_intel.lexa import repository

    monkeypatch.setattr(repository, "_price_frame", lambda *_: None)
    _video("Analyse", T0, 2.15696)
    analysis_id = repository.list_by_date()[0]["assets"][0]["analysis_id"]
    level_id = repository.asset_report(analysis_id)["levels"][0]["id"]
    repository.correct_level(level_id, 2.1556)
    level = repository.asset_report(analysis_id)["levels"][0]
    assert level["value"] == 2.1556
    assert level["original_value"] == 2.15696
    assert level["corrected_at"] is not None


def test_the_capital_setting_changes_allocations_not_levels(monkeypatch):
    from crypto_intel.lexa import repository

    monkeypatch.setattr(repository, "_price_frame", lambda *_: None)
    _video("Analyse", T0, 2.15696)
    analysis_id = repository.list_by_date()[0]["assets"][0]["analysis_id"]
    repository.set_capital(200)
    level = repository.asset_report(analysis_id)["levels"][0]
    assert level["allocation_eur"] == pytest.approx(120)
    assert level["value"] == 2.15696


def test_bad_inputs_are_refused_not_guessed():
    from crypto_intel.lexa.repository import AssetInput, LevelInput, LexaInputError, create_video

    with pytest.raises(LexaInputError):
        create_video(title="x", published_at=T0, assets=[AssetInput(
            asset="XRP", levels=[LevelInput(kind="BUY_ZONE", value=2.04, timestamp="18h42")])])
    with pytest.raises(LexaInputError):
        create_video(title="x", published_at=T0, assets=[AssetInput(
            asset="XRP", levels=[LevelInput(kind="BUY_ZONE", value=2.04, condition="SOON")])])


# --- privacy ----------------------------------------------------------------


def test_lexa_routes_answer_this_machine_only():
    from fastapi.testclient import TestClient

    from crypto_intel.main import app

    local = TestClient(app, client=("127.0.0.1", 5000))
    assert local.get("/api/lexa/videos").status_code == 200
    remote = TestClient(app, client=("203.0.113.9", 5000))
    assert remote.get("/api/lexa/videos").status_code == 403
    lan = TestClient(app, client=("192.168.1.20", 5000))
    assert lan.get("/api/lexa/videos").status_code == 403
    tailnet = TestClient(app, client=("100.119.156.72", 5000))  # own device via Tailscale
    assert tailnet.get("/api/lexa/videos").status_code == 200


def test_lexa_routes_are_never_exported():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "scripts" / "export_flutter_static_api.py"
    spec = importlib.util.spec_from_file_location("export_script", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert not any(p.startswith("/lexa") for p, _ in module._endpoints())
    with pytest.raises(RuntimeError):
        module.assert_exportable([("/lexa/videos", None)])


def test_lexa_data_is_ignored_by_git():
    from pathlib import Path

    gitignore = (Path(__file__).resolve().parents[2] / ".gitignore").read_text()
    assert "data/lexa/" in gitignore


def test_stored_videos_are_tracked_on_utc_candles(monkeypatch):
    # SQLite returns naive datetimes; the candles are tz-aware UTC.
    from crypto_intel.lexa import repository

    prices = [2.346, 2.21, 2.142, 2.057, 2.125, 2.38]
    monkeypatch.setattr(repository, "_price_frame", lambda *_: _hourly(prices))
    _video("Analyse", T0, 2.15696)
    analysis_id = repository.list_by_date()[0]["assets"][0]["analysis_id"]
    report = repository.asset_report(analysis_id)
    assert report["published_at"].endswith("+00:00")
    assert report["levels"][0]["state"]["state"] == "TOUCHED"
    assert report["simulation"]["fills"][0]["level_id"] == report["levels"][0]["id"]

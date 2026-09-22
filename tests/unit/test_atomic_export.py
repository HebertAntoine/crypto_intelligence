"""Sections 5, 6, 8 and 36: an incomplete cycle must never reach the app.

The app reads files, not the API. So a half-written set is indistinguishable
from a good one unless the export refuses to publish it: these tests drive the
export through failure cases and check that the previous set survives.
"""

import json
import os
import sys
import time
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import export_flutter_static_api as exporter  # noqa: E402


@pytest.fixture
def snapshot_dir(tmp_path, monkeypatch):
    out = tmp_path / "api_snapshots"
    out.mkdir()
    monkeypatch.setattr(exporter, "OUT_DIR", out)
    monkeypatch.setattr(exporter, "PROJECT_ROOT", tmp_path)
    return out


def payload(asset: str = "BTC", horizon: str = "7d", **overrides) -> dict:
    data = {
        "asset": asset,
        "horizon": horizon,
        "decision": "WAIT",
        "as_of": "2026-09-18T00:00:00+00:00",
        "families": {
            "items": {name: {"available": True} for name in
                      ("macro_liquidity", "catalysts_regulation", "flows_whales",
                       "positioning_derivatives", "technical_volatility")},
            "factors": [],
        },
        "synthesis": {"data_status": "AVAILABLE", "missing_families": [],
                      "upcoming_events": []},
    }
    data.update(overrides)
    return data


def endpoints(*specs):
    return [(f"/future/{asset}", {"horizon": horizon}) for asset, horizon in specs]


def fetcher(payloads):
    def fetch(_base, path, query):
        return payloads[(path.split("/")[-1], (query or {}).get("horizon"))]
    return fetch


# --- the happy path ---------------------------------------------------------


def test_a_complete_cycle_publishes_and_stamps_one_run_id(snapshot_dir) -> None:
    specs = [("BTC", "7d"), ("ETH", "7d"), ("SOL", "7d")]
    fetch = fetcher({(a, h): payload(a, h) for a, h in specs})

    written = exporter._export_atomically(fetch, "", endpoints(*specs), "run_X")

    assert len(written) == 3
    run_ids = {
        json.loads((snapshot_dir / Path(name).name).read_text())["run_id"]
        for name in written
    }
    assert run_ids == {"run_X"}


def test_the_manifest_reports_the_whole_set(snapshot_dir) -> None:
    specs = [("BTC", "7d"), ("ETH", "7d")]
    fetch = fetcher({(a, h): payload(a, h) for a, h in specs})
    exporter._export_atomically(fetch, "", endpoints(*specs), "run_Y")

    manifest = json.loads((snapshot_dir / "snapshot_manifest.json").read_text())
    assert manifest["run_id"] == "run_Y"
    assert manifest["status"] == "HEALTHY"
    assert set(manifest["assets"]) == {"BTC", "ETH"}
    assert manifest["assets"]["BTC"]["families_available"] == "5/5"


def test_a_partial_family_set_is_reported_as_degraded(snapshot_dir) -> None:
    fetch = fetcher({
        ("BTC", "7d"): payload(
            synthesis={"data_status": "PARTIAL_DATA",
                       "missing_families": ["Crédit"], "upcoming_events": []}
        )
    })
    exporter._export_atomically(fetch, "", endpoints(("BTC", "7d")), "run_Z")

    manifest = json.loads((snapshot_dir / "snapshot_manifest.json").read_text())
    assert manifest["status"] == "DEGRADED"
    assert manifest["degraded_assets"] == ["BTC"]


# --- refusals ---------------------------------------------------------------


def seed_previous_set(snapshot_dir) -> dict:
    """A known-good set already being served."""

    previous = payload()
    previous["run_id"] = "run_PREVIOUS"
    (snapshot_dir / "future__BTC__horizon-7d.json").write_text(
        json.dumps(previous), encoding="utf-8"
    )
    return previous


def test_a_snapshot_for_the_wrong_asset_blocks_publication(snapshot_dir) -> None:
    seed_previous_set(snapshot_dir)
    # The payload says ETH while the filename says BTC.
    fetch = fetcher({("BTC", "7d"): payload(asset="ETH")})

    with pytest.raises(SystemExit, match="export refusé"):
        exporter._export_atomically(fetch, "", endpoints(("BTC", "7d")), "run_BAD")

    kept = json.loads((snapshot_dir / "future__BTC__horizon-7d.json").read_text())
    assert kept["run_id"] == "run_PREVIOUS"


def test_a_missing_decision_blocks_publication(snapshot_dir) -> None:
    seed_previous_set(snapshot_dir)
    fetch = fetcher({("BTC", "7d"): payload(decision="")})

    with pytest.raises(SystemExit, match="décision absente"):
        exporter._export_atomically(fetch, "", endpoints(("BTC", "7d")), "run_BAD")

    kept = json.loads((snapshot_dir / "future__BTC__horizon-7d.json").read_text())
    assert kept["run_id"] == "run_PREVIOUS"


def test_a_stale_reading_claiming_high_confidence_blocks_publication(
    snapshot_dir,
) -> None:
    seed_previous_set(snapshot_dir)
    bad = payload()
    bad["families"]["factors"] = [
        {"key": "flows", "availability": "STALE", "confidence_band": "HIGH",
         "direction": "POSITIVE"}
    ]
    fetch = fetcher({("BTC", "7d"): bad})

    with pytest.raises(SystemExit, match="périmé avec confiance élevée"):
        exporter._export_atomically(fetch, "", endpoints(("BTC", "7d")), "run_BAD")


def test_an_unavailable_reading_with_a_direction_blocks_publication(
    snapshot_dir,
) -> None:
    seed_previous_set(snapshot_dir)
    bad = payload()
    bad["families"]["factors"] = [
        {"key": "credit", "availability": "UNAVAILABLE", "direction": "POSITIVE",
         "confidence_band": "LOW"}
    ]
    fetch = fetcher({("BTC", "7d"): bad})

    with pytest.raises(SystemExit, match="indisponible mais directionnel"):
        exporter._export_atomically(fetch, "", endpoints(("BTC", "7d")), "run_BAD")


def test_a_past_event_still_listed_as_upcoming_blocks_publication(
    snapshot_dir,
) -> None:
    seed_previous_set(snapshot_dir)
    bad = payload()
    bad["synthesis"]["upcoming_events"] = [
        {"title": "Décision de la Fed", "scheduled_at": "2020-01-01T00:00:00+00:00"}
    ]
    fetch = fetcher({("BTC", "7d"): bad})

    with pytest.raises(SystemExit, match="événement passé"):
        exporter._export_atomically(fetch, "", endpoints(("BTC", "7d")), "run_BAD")


def test_a_missing_family_slot_blocks_publication(snapshot_dir) -> None:
    seed_previous_set(snapshot_dir)
    bad = payload()
    bad["families"]["items"].pop("flows_whales")
    fetch = fetcher({("BTC", "7d"): bad})

    with pytest.raises(SystemExit, match="familles au lieu de 5"):
        exporter._export_atomically(fetch, "", endpoints(("BTC", "7d")), "run_BAD")


def test_one_bad_asset_prevents_the_whole_set_from_publishing(
    snapshot_dir,
) -> None:
    """Section 5: never BTC from this cycle beside ETH from the previous one."""

    seed_previous_set(snapshot_dir)
    specs = [("BTC", "7d"), ("ETH", "7d")]
    fetch = fetcher({
        ("BTC", "7d"): payload("BTC"),
        ("ETH", "7d"): payload("ETH", decision=""),
    })

    with pytest.raises(SystemExit):
        exporter._export_atomically(fetch, "", endpoints(*specs), "run_BAD")

    # The good BTC payload of the failed cycle must not have been published.
    kept = json.loads((snapshot_dir / "future__BTC__horizon-7d.json").read_text())
    assert kept["run_id"] == "run_PREVIOUS"
    assert not (snapshot_dir / "future__ETH__horizon-7d.json").exists()


# --- crash recovery ---------------------------------------------------------


def test_a_staging_directory_left_by_a_killed_run_is_never_promoted(
    snapshot_dir,
) -> None:
    orphan = snapshot_dir / ".staging" / "run_KILLED"
    orphan.mkdir(parents=True)
    (orphan / "future__BTC__horizon-7d.json").write_text('{"asset": "BTC"}')
    old = time.time() - 3 * 3600
    os.utime(orphan, (old, old))

    fetch = fetcher({("BTC", "7d"): payload()})
    exporter._export_atomically(fetch, "", endpoints(("BTC", "7d")), "run_NEW")

    assert not orphan.exists()
    published = json.loads(
        (snapshot_dir / "future__BTC__horizon-7d.json").read_text()
    )
    assert published["run_id"] == "run_NEW"


def test_a_run_still_writing_is_left_alone_and_never_promoted(snapshot_dir) -> None:
    """The light pass exports every 15 minutes. Deleting a fresh staging
    directory pulled the floor from under another run mid-write."""

    concurrent = snapshot_dir / ".staging" / "run_WRITING"
    concurrent.mkdir(parents=True)
    (concurrent / "future__ETH__horizon-7d.json").write_text('{"asset": "ETH"}')

    fetch = fetcher({("BTC", "7d"): payload()})
    exporter._export_atomically(fetch, "", endpoints(("BTC", "7d")), "run_NEW")

    assert concurrent.exists()
    assert not (snapshot_dir / "future__ETH__horizon-7d.json").exists()


def test_staging_is_cleaned_up_after_a_refused_export(snapshot_dir) -> None:
    fetch = fetcher({("BTC", "7d"): payload(decision="")})
    with pytest.raises(SystemExit):
        exporter._export_atomically(fetch, "", endpoints(("BTC", "7d")), "run_BAD")

    assert not (snapshot_dir / ".staging" / "run_BAD").exists()


def test_the_shipped_manifest_matches_the_shipped_snapshots() -> None:
    """The set actually in the repository must be internally consistent."""

    live = PROJECT_ROOT / "app" / "assets" / "api_snapshots"
    manifest_path = live / "snapshot_manifest.json"
    if not manifest_path.exists():
        pytest.skip("aucun manifeste exporté")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    for path in live.glob("future__*__horizon-*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data.get("run_id") == manifest["run_id"], path.name


def test_two_endpoints_sharing_a_snapshot_name_are_promoted_once(
    snapshot_dir,
) -> None:
    """Appending to a list made the second move fail on an already-moved file."""

    fetch = fetcher({("BTC", "7d"): payload()})
    duplicated = endpoints(("BTC", "7d")) * 2

    written = exporter._export_atomically(fetch, "", duplicated, "run_DUP")

    assert len(written) == 1
    assert (snapshot_dir / "future__BTC__horizon-7d.json").exists()


def test_a_cycle_chart_without_a_past_halving_blocks_publication() -> None:
    """A transient read failure once shipped a Bitcoin cycle page whose chart
    had lost every past halving. It still rendered, silently poorer."""

    from pathlib import Path

    degraded = {"run_id": "run_OK", "asset": "BTC",
                "chart": {"halvings": [{"date": "2028-03-28", "estimated": True}]}}
    problems = exporter._validate_snapshot(Path("cycle__BTC.json"), degraded, "run_OK")
    assert any("halving passé" in problem for problem in problems)

    whole = {"run_id": "run_OK", "asset": "BTC",
             "chart": {"halvings": [{"date": "2024-04-20", "estimated": False},
                                    {"date": "2028-03-28", "estimated": True}]}}
    assert exporter._validate_snapshot(Path("cycle__BTC.json"), whole, "run_OK") == []

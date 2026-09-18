"""Sections 28, 29 and 43: the system reports its own state.

A report that always says HEALTHY is worth nothing, so each test drives a real
failure mode through it and checks the verdict moves.
"""

import json
from datetime import UTC, datetime, timedelta

import pytest

from crypto_intel.pipeline import health as health_module


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    snapshots = tmp_path / "api_snapshots"
    logs = tmp_path / "refresh_logs"
    snapshots.mkdir()
    logs.mkdir()
    monkeypatch.setattr(health_module, "SNAPSHOT_DIR", snapshots)
    monkeypatch.setattr(health_module, "LOG_DIR", logs)
    # These tests are about the snapshot set. Source rows read the real state
    # file and database, which belong to their own tests below.
    monkeypatch.setattr(health_module, "_source_rows", lambda now: [])
    monkeypatch.setattr(health_module, "_next_runs", lambda now: {})
    return snapshots, logs


NOW = datetime(2026, 9, 18, 12, tzinfo=UTC)


def write_manifest(snapshots, *, generated_at, status="HEALTHY", degraded=()):
    (snapshots / "snapshot_manifest.json").write_text(
        json.dumps({
            "run_id": "run_A",
            "generated_at": generated_at.isoformat(),
            "status": status,
            "degraded_assets": list(degraded),
            "assets": {
                "BTC": {"verdict": "WAIT", "families_available": "5/5",
                        "data_status": "AVAILABLE", "missing_families": []},
            },
        }),
        encoding="utf-8",
    )


def write_snapshot(snapshots, asset="BTC", run_id="run_A"):
    (snapshots / f"future__{asset}__horizon-7d.json").write_text(
        json.dumps({"asset": asset, "run_id": run_id}), encoding="utf-8"
    )


def write_log(logs, verdict="refresh done: SUCCESS"):
    (logs / "refresh_20260918T070000Z.log").write_text(
        f"07:00:00 refresh start\n07:05:00 {verdict}\n", encoding="utf-8"
    )


def test_a_fresh_coherent_set_is_healthy(workspace) -> None:
    snapshots, logs = workspace
    write_manifest(snapshots, generated_at=NOW - timedelta(hours=2))
    write_snapshot(snapshots)
    write_log(logs)

    report = health_module.collect_health(now=NOW)
    assert report.status == "HEALTHY"
    assert report.alerts == []


def test_a_missing_manifest_is_invalid_not_merely_degraded(workspace) -> None:
    report = health_module.collect_health(now=NOW)
    assert report.status == "INVALID"
    assert any("SNAPSHOT_EXPORT_FAILED" in alert for alert in report.alerts)


def test_a_set_older_than_the_refresh_cadence_raises_an_alert(workspace) -> None:
    snapshots, logs = workspace
    write_manifest(snapshots, generated_at=NOW - timedelta(hours=30))
    write_snapshot(snapshots)
    write_log(logs)

    report = health_module.collect_health(now=NOW)
    assert report.status == "DEGRADED"
    assert any("SNAPSHOT_STALE" in alert for alert in report.alerts)


def test_mixed_run_ids_are_invalid(workspace) -> None:
    """Section 6: a set built from two cycles is worse than an old one."""

    snapshots, logs = workspace
    write_manifest(snapshots, generated_at=NOW - timedelta(hours=1))
    write_snapshot(snapshots, "BTC", run_id="run_A")
    write_snapshot(snapshots, "ETH", run_id="run_B")
    write_log(logs)

    report = health_module.collect_health(now=NOW)
    assert report.status == "INVALID"
    assert any("run_id mélangés" in alert for alert in report.alerts)


def test_a_failed_last_run_is_reported(workspace) -> None:
    snapshots, logs = workspace
    write_manifest(snapshots, generated_at=NOW - timedelta(hours=1))
    write_snapshot(snapshots)
    write_log(logs, verdict="refresh done: FAILED (export unusable)")

    report = health_module.collect_health(now=NOW)
    assert report.status == "DEGRADED"
    assert any("PIPELINE_FAILED" in alert for alert in report.alerts)


def test_no_log_at_all_means_nothing_has_run(workspace) -> None:
    snapshots, _ = workspace
    write_manifest(snapshots, generated_at=NOW - timedelta(hours=1))
    write_snapshot(snapshots)

    report = health_module.collect_health(now=NOW)
    assert any("NO_SUCCESSFUL_REFRESH" in alert for alert in report.alerts)


def test_a_degraded_manifest_names_the_missing_families(workspace) -> None:
    snapshots, logs = workspace
    (snapshots / "snapshot_manifest.json").write_text(
        json.dumps({
            "run_id": "run_A",
            "generated_at": (NOW - timedelta(hours=1)).isoformat(),
            "status": "DEGRADED",
            "degraded_assets": ["SOL"],
            "assets": {"SOL": {"verdict": "WAIT", "families_available": "4/5",
                               "data_status": "PARTIAL_DATA",
                               "missing_families": ["Crédit"]}},
        }),
        encoding="utf-8",
    )
    write_snapshot(snapshots, "SOL")
    write_log(logs)

    report = health_module.collect_health(now=NOW)
    assert report.status == "DEGRADED"
    assert any("Crédit" in note for note in report.notes)


def test_the_rendered_report_reads_as_a_verdict(workspace) -> None:
    snapshots, logs = workspace
    write_manifest(snapshots, generated_at=NOW - timedelta(hours=1))
    write_snapshot(snapshots)
    write_log(logs)

    text = health_module.render(health_module.collect_health(now=NOW))
    assert "ÉTAT DU SYSTÈME" in text
    assert "Pipeline" in text
    assert "BTC" in text


# --- section 30: the SLA of each source is visible ---------------------------


def test_each_source_row_carries_its_own_sla(monkeypatch) -> None:
    rows = health_module._source_rows(NOW)
    assert rows
    for row in rows:
        assert row["max_age_min"] > row["refresh_interval_min"], row["source_id"]
        assert row["criticality"] in {"CRITICAL", "IMPORTANT", "OPTIONAL"}
        assert row["freshness"] in {"FRESH", "AGING", "STALE", "UNAVAILABLE"}


def test_a_stale_critical_source_raises_an_alert(workspace, monkeypatch) -> None:
    snapshots, logs = workspace
    write_manifest(snapshots, generated_at=NOW - timedelta(hours=1))
    write_snapshot(snapshots)
    write_log(logs)
    monkeypatch.setattr(
        health_module,
        "_source_rows",
        lambda now: [{
            "source_id": "market_price", "family": "technical", "health": "HEALTHY",
            "freshness": "STALE", "age_min": 120.0, "max_age_min": 30.0,
            "refresh_interval_min": 5.0, "criticality": "CRITICAL",
            "enabled": True, "note": "",
        }],
    )

    report = health_module.collect_health(now=NOW)
    assert report.status == "DEGRADED"
    assert any("CRITICAL_SOURCE_STALE" in alert for alert in report.alerts)


def test_a_stale_optional_source_does_not_degrade_the_pipeline(
    workspace, monkeypatch
) -> None:
    """Section 31: an optional absence is noted, not treated as a failure."""

    snapshots, logs = workspace
    write_manifest(snapshots, generated_at=NOW - timedelta(hours=1))
    write_snapshot(snapshots)
    write_log(logs)
    monkeypatch.setattr(
        health_module,
        "_source_rows",
        lambda now: [{
            "source_id": "whales", "family": "spot", "health": "HEALTHY",
            "freshness": "STALE", "age_min": 900.0, "max_age_min": 360.0,
            "refresh_interval_min": 60.0, "criticality": "OPTIONAL",
            "enabled": True, "note": "",
        }],
    )

    report = health_module.collect_health(now=NOW)
    assert report.status == "HEALTHY"


def test_a_down_source_is_reported(workspace, monkeypatch) -> None:
    snapshots, logs = workspace
    write_manifest(snapshots, generated_at=NOW - timedelta(hours=1))
    write_snapshot(snapshots)
    write_log(logs)
    monkeypatch.setattr(
        health_module,
        "_source_rows",
        lambda now: [{
            "source_id": "derivatives_oi", "family": "derivatives", "health": "DOWN",
            "freshness": "FRESH", "age_min": 3.0, "max_age_min": 60.0,
            "refresh_interval_min": 15.0, "criticality": "IMPORTANT",
            "enabled": True, "note": "",
        }],
    )

    report = health_module.collect_health(now=NOW)
    assert any("SOURCE_DOWN" in alert for alert in report.alerts)


def test_next_runs_are_computed_rather_than_written(workspace) -> None:
    """Section 32: a fixed "07:00" reads as reassurance while being false."""

    from pathlib import Path

    # Read the module file: the fixture replaces the attribute, so inspecting
    # the live object would only show the stub.
    source = Path(health_module.__file__).read_text(encoding="utf-8")
    assert "list-timers" in source
    assert '"07:00"' not in source

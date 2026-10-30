"""General alerts have durable, auditable in-app delivery receipts."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text

from crypto_intel.core.enums import Asset
from crypto_intel.db import migrations, repo
from crypto_intel.db.base import AlertRow
from crypto_intel.db.session import session_scope


def _row(
    suffix: str,
    when: datetime,
    *,
    asset: str = "BTC",
    cooldown_minutes: int = 360,
) -> dict[str, Any]:
    return {
        "kind": f"RECEIPT_TEST_{suffix}",
        "importance": "WATCH",
        "asset": asset,
        "title": f"Receipt {suffix}",
        "detail": "Measured trigger",
        "triggered_at": when.isoformat(),
        "evidence_ids": [f"evidence-{suffix}"],
        "dedup_key": f"{asset}:receipt:{suffix}",
        "reason": "Measured condition changed.",
        "analysis_id": f"rpt_{suffix}",
        "cooldown_minutes": cooldown_minutes,
        "delivery_status": "SENT",  # caller input must never be trusted
        "source_snapshot": {"measured_value": 42.0},
    }


def test_legacy_alert_table_receives_additive_receipt_migration(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy-alerts.db'}")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE alerts ("
                "id INTEGER PRIMARY KEY, kind VARCHAR(48), importance VARCHAR(16), "
                "asset VARCHAR(16), title VARCHAR(256), detail TEXT, "
                "triggered_at DATETIME, evidence_ids JSON, acknowledged BOOLEAN)"
            )
        )

    monkeypatch.setattr(migrations, "get_engine", lambda: engine)
    applied = migrations.run_migrations()

    expected = {
        "notification_id",
        "trigger_id",
        "asset_id",
        "analysis_id",
        "created_at",
        "delivered_at",
        "delivery_status",
        "reason",
        "source_snapshot",
    }
    assert expected <= migrations.existing_columns("alerts")
    assert "ux_alert_notification_id" in migrations.existing_indexes("alerts")
    assert {f"alerts.{column}" for column in expected} <= set(applied)
    assert migrations.run_migrations() == []
    engine.dispose()


def test_receipt_is_persisted_only_as_stored_and_has_trace_coordinates():
    when = datetime(2031, 1, 2, 3, 4, 5, tzinfo=UTC)
    row = _row("persisted", when)

    assert repo.save_alerts([row]) == 1
    receipt = next(
        alert
        for alert in repo.recent_alerts(limit=200, asset=Asset.BTC)
        if alert["kind"] == row["kind"]
    )

    assert receipt["notification_id"].startswith("ntf_")
    assert receipt["trigger_id"] == row["dedup_key"]
    assert receipt["asset_id"] == "BTC"
    assert receipt["analysis_id"] == "rpt_persisted"
    assert receipt["created_at"] is not None
    assert receipt["delivered_at"] is not None
    assert receipt["delivery_status"] == "STORED"
    assert receipt["delivery_status"] != "SENT"
    assert receipt["reason"] == row["reason"]
    assert receipt["source_snapshot"]["measured_value"] == 42.0
    assert receipt["source_snapshot"]["notification_id"] == receipt["notification_id"]
    assert receipt["source_snapshot"]["trigger_id"] == receipt["trigger_id"]
    assert receipt["source_snapshot"]["evidence_ids"] == ["evidence-persisted"]


def test_receipt_save_is_atomic_on_a_bad_batch():
    when = datetime(2031, 2, 2, tzinfo=UTC)
    valid = _row("rolled-back", when)
    invalid = _row("invalid", when + timedelta(seconds=1))
    invalid.pop("importance")

    with pytest.raises(KeyError):
        repo.save_alerts([valid, invalid])

    with session_scope() as session:
        persisted = session.execute(
            select(AlertRow.id).where(AlertRow.kind == valid["kind"])
        ).first()
    assert persisted is None


def test_save_boundary_preserves_cooldown_and_exact_retry_deduplication():
    when = datetime(2031, 3, 2, tzinfo=UTC)
    first = _row("cooldown", when)
    same_event = dict(first)
    during_cooldown = _row("cooldown", when + timedelta(minutes=5))
    after_cooldown = _row("cooldown", when + timedelta(minutes=361))

    assert repo.save_alerts([first]) == 1
    assert repo.save_alerts([same_event]) == 0
    assert repo.save_alerts([during_cooldown]) == 0
    assert repo.save_alerts([after_cooldown]) == 1

    with session_scope() as session:
        rows = session.execute(
            select(AlertRow).where(AlertRow.dedup_key == first["dedup_key"])
        ).scalars().all()
    assert len(rows) == 2


def test_exact_retry_deduplication_is_atomic_across_writers():
    row = _row("concurrent", datetime(2031, 3, 3, tzinfo=UTC))

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(repo.save_alerts, ([row], [row])))

    assert sum(results) == 1
    with session_scope() as session:
        rows = session.execute(
            select(AlertRow).where(AlertRow.dedup_key == row["dedup_key"])
        ).scalars().all()
    assert len(rows) == 1


def test_alerts_api_exposes_complete_general_receipt_contract():
    when = datetime(2031, 4, 2, tzinfo=UTC)
    row = _row("api", when, asset="SOL", cooldown_minutes=0)
    assert repo.save_alerts([row]) == 1

    from crypto_intel.main import create_app

    with TestClient(create_app()) as client:
        response = client.get("/api/alerts?asset=SOL&limit=200")

    assert response.status_code == 200
    receipt = next(item for item in response.json() if item["kind"] == row["kind"])
    assert {
        "notification_id",
        "trigger_id",
        "asset_id",
        "analysis_id",
        "created_at",
        "delivered_at",
        "delivery_status",
        "reason",
        "source_snapshot",
    } <= receipt.keys()
    assert receipt["delivery_status"] == "STORED"
    assert receipt["analysis_id"] == "rpt_api"

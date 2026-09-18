"""One answer to "is the machine still doing its job?".

Everything here is read from artefacts the pipeline already produces: the
snapshot manifest, the snapshots themselves and the refresh logs. Nothing is
recomputed, so the report describes what the app is actually being served
rather than what a fresh analysis would say.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SNAPSHOT_DIR = PROJECT_ROOT / "app" / "assets" / "api_snapshots"
LOG_DIR = PROJECT_ROOT / "data" / "refresh_logs"

#: Twice-daily refresh, so a set older than this means a run was missed.
SNAPSHOT_MAX_AGE_HOURS = 14.0


@dataclass(slots=True)
class HealthReport:
    status: str = "HEALTHY"
    run_id: str | None = None
    generated_at: str | None = None
    snapshot_age_hours: float | None = None
    assets: dict[str, Any] = field(default_factory=dict)
    last_refresh: str | None = None
    last_refresh_status: str | None = None
    alerts: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "run_id": self.run_id,
            "generated_at": self.generated_at,
            "snapshot_age_hours": (
                round(self.snapshot_age_hours, 2)
                if self.snapshot_age_hours is not None
                else None
            ),
            "assets": self.assets,
            "last_refresh": self.last_refresh,
            "last_refresh_status": self.last_refresh_status,
            "alerts": self.alerts,
            "notes": self.notes,
            "checked_at": datetime.now(UTC).isoformat(),
        }


def _degrade(report: HealthReport, level: str) -> None:
    """Status only ever gets worse, never better, as checks accumulate."""

    order = {"HEALTHY": 0, "DEGRADED": 1, "INVALID": 2}
    if order[level] > order[report.status]:
        report.status = level


def collect_health(now: datetime | None = None) -> HealthReport:
    reference = now or datetime.now(UTC)
    report = HealthReport()

    manifest_path = SNAPSHOT_DIR / "snapshot_manifest.json"
    if not manifest_path.exists():
        report.status = "INVALID"
        report.alerts.append("SNAPSHOT_EXPORT_FAILED: aucun manifeste")
        return report

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    report.run_id = manifest.get("run_id")
    report.generated_at = manifest.get("generated_at")
    report.assets = manifest.get("assets") or {}

    if report.generated_at:
        age = (reference - datetime.fromisoformat(report.generated_at)).total_seconds()
        report.snapshot_age_hours = age / 3600
        if report.snapshot_age_hours > SNAPSHOT_MAX_AGE_HOURS:
            _degrade(report, "DEGRADED")
            report.alerts.append(
                f"SNAPSHOT_STALE: {report.snapshot_age_hours:.1f} h "
                f"(limite {SNAPSHOT_MAX_AGE_HOURS:.0f} h)"
            )

    # A set built from two cycles is worse than an old one: it is incoherent.
    mixed = {
        json.loads(path.read_text(encoding="utf-8")).get("run_id")
        for path in SNAPSHOT_DIR.glob("future__*__horizon-*.json")
    }
    if len(mixed) > 1:
        report.status = "INVALID"
        report.alerts.append(f"DATA_ANOMALY: run_id mélangés {sorted(mixed)}")

    if manifest.get("status") == "DEGRADED":
        _degrade(report, "DEGRADED")
        for asset in manifest.get("degraded_assets") or []:
            missing = report.assets.get(asset, {}).get("missing_families") or []
            report.notes.append(
                f"{asset}: familles indisponibles — {', '.join(missing) or 'non précisé'}"
            )

    logs = sorted(LOG_DIR.glob("refresh_*.log")) if LOG_DIR.exists() else []
    if not logs:
        _degrade(report, "DEGRADED")
        report.alerts.append("NO_SUCCESSFUL_REFRESH: aucun journal de passage")
    else:
        last = logs[-1]
        report.last_refresh = last.stem.removeprefix("refresh_")
        tail = last.read_text(encoding="utf-8", errors="replace").splitlines()[-40:]
        verdict = next(
            (line for line in reversed(tail) if "refresh done" in line), ""
        )
        report.last_refresh_status = verdict.split("refresh done:")[-1].strip() or None
        if "FAILED" in verdict:
            _degrade(report, "DEGRADED")
            report.alerts.append("PIPELINE_FAILED: dernier passage en échec")

    return report


def render(report: HealthReport) -> str:
    """The same information a person would want at a glance."""

    lines = [
        "ÉTAT DU SYSTÈME",
        "",
        f"  Pipeline           : {report.status}",
        f"  Cycle              : {report.run_id or '—'}",
        f"  Snapshots générés  : {str(report.generated_at)[:19] or '—'}"
        + (
            f"  (il y a {report.snapshot_age_hours:.1f} h)"
            if report.snapshot_age_hours is not None
            else ""
        ),
        f"  Dernier passage    : {report.last_refresh or '—'}"
        + (f"  [{report.last_refresh_status}]" if report.last_refresh_status else ""),
        "",
        "  Actifs :",
    ]
    for asset, item in sorted(report.assets.items()):
        lines.append(
            f"    {asset:<5} {item.get('verdict')!s:<8} "
            f"familles {item.get('families_available', '?')}  "
            f"{item.get('data_status', '')}"
        )
    if report.notes:
        lines += ["", "  Détail :"]
        lines += [f"    {note}" for note in report.notes]
    if report.alerts:
        lines += ["", "  Alertes :"]
        lines += [f"    ⚠️  {alert}" for alert in report.alerts]
    else:
        lines += ["", "  Aucune alerte."]
    return "\n".join(lines)


def write_health_json(report: HealthReport) -> Path:
    target = SNAPSHOT_DIR / "health.json"
    target.write_text(
        json.dumps(report.to_dict(), ensure_ascii=True, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    return target

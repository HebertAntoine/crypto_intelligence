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
    sources: list[dict[str, Any]] = field(default_factory=list)
    next_runs: dict[str, str | None] = field(default_factory=dict)
    news_radar: dict[str, Any] = field(default_factory=dict)
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
            "sources": self.sources,
            "next_runs": self.next_runs,
            "news_radar": self.news_radar,
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

    report.sources = _source_rows(reference)
    for row in report.sources:
        # A critical source whose data has aged out is the one case that turns
        # a degraded pipeline into an unusable one.
        if row["criticality"] == "CRITICAL" and row["freshness"] == "STALE":
            _degrade(report, "DEGRADED")
            report.alerts.append(f"CRITICAL_SOURCE_STALE: {row['source_id']}")
        if row["health"] == "DOWN":
            report.alerts.append(f"SOURCE_DOWN: {row['source_id']}")
            _degrade(report, "DEGRADED")
        if row["health"] == "DATA_STUCK":
            report.alerts.append(f"DATA_STUCK: {row['source_id']}")
            _degrade(report, "DEGRADED")
        if row["health"] == "AUTH_ERROR":
            report.alerts.append(f"AUTH_FAILURE: {row['source_id']}")
            _degrade(report, "DEGRADED")

    report.next_runs = _next_runs(reference)

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

    report.news_radar = _radar_summary(reference)
    if report.news_radar.get("awaiting_result"):
        # An event whose moment passed and whose outcome nobody read back is
        # the failure mode a freshness check never catches: the row is recent,
        # the information is missing.
        _degrade(report, "DEGRADED")
        report.alerts.append(
            "EVENT_RESULT_MISSING: "
            f"{report.news_radar['awaiting_result']} événement(s) passés sans résultat"
        )

    return report


def _radar_summary(now: datetime) -> dict[str, Any]:
    """Fold the stored catalysts through the radar, tolerating an empty store."""

    try:
        import sqlite3

        from ..engines.market_radar import RadarItem, radar_summary

        database = PROJECT_ROOT / "data" / "crypto_intel.db"
        if not database.exists():
            return {}
        con = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
        rows = con.execute(
            "SELECT canonical_event_id, title, category, source_tier, source, "
            "detected_at, scheduled_at, source_published_at, source_url "
            "FROM future_events"
        ).fetchall()
        con.close()
    except Exception:
        return {}

    from ..engines.market_radar import _CATEGORY_BRIDGE, _TIER_BRIDGE, RadarCategory, SourceTrust

    items: list[RadarItem] = []
    for row in rows:
        (event_id, title, category, tier, source, detected, scheduled, published, url) = row
        parsed = [_as_datetime(value) for value in (detected, scheduled, published)]
        items.append(
            RadarItem(
                event_id=str(event_id),
                title=str(title or ""),
                category=_CATEGORY_BRIDGE.get(str(category), RadarCategory.OTHER),
                trust=_TIER_BRIDGE.get(str(tier), SourceTrust.SECONDARY),
                source=str(source or "inconnue"),
                detected_at=parsed[0] or now,
                scheduled_at=parsed[1],
                published_at=parsed[2],
                source_url=url,
            )
        )
    return radar_summary(items, now=now)


def _as_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed


def _source_rows(now: datetime) -> list[dict[str, Any]]:
    """Each source with its own SLA beside its measured age."""

    from .source_policy import (
        POLICIES,
        SourceState,
        data_freshness,
        health_of,
    )
    from .source_state_store import load as load_states

    states = load_states()
    observed = _observed_freshness()
    rows: list[dict[str, Any]] = []
    for policy in POLICIES.values():
        state = states.get(policy.source_id)
        age_min = None
        if state is not None and state.last_success_at is not None:
            age_min = round(
                (now - state.last_success_at).total_seconds() / 60, 1
            )
        elif policy.metric_prefix:
            # Collected by the full pass, which does not attribute per source.
            # The stored observation is the measurement rather than a guess.
            seen = observed.get(policy.metric_prefix)
            if seen is not None:
                age_min = round((now - seen).total_seconds() / 60, 1)
                state = SourceState(
                    source_id=policy.source_id, last_success_at=seen
                )
        rows.append({
            "source_id": policy.source_id,
            "family": policy.family,
            "health": health_of(policy, state, now).value,
            "freshness": data_freshness(policy, state, now),
            "age_min": age_min,
            "max_age_min": policy.max_age.total_seconds() / 60,
            "refresh_interval_min": policy.refresh_interval.total_seconds() / 60,
            "criticality": policy.criticality.value,
            "enabled": policy.enabled,
            "note": policy.note,
        })
    return rows


def _observed_freshness() -> dict[str, datetime]:
    """Newest stored observation per metric prefix, read once."""

    try:
        import sqlite3

        database = PROJECT_ROOT / "data" / "crypto_intel.db"
        if not database.exists():
            return {}
        con = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
        rows = con.execute(
            "SELECT metric, MAX(timestamp) FROM observations GROUP BY metric"
        ).fetchall()
        con.close()
    except Exception:
        return {}

    newest: dict[str, datetime] = {}
    for metric, stamp in rows:
        if not stamp:
            continue
        try:
            when = datetime.fromisoformat(str(stamp))
        except ValueError:
            continue
        if when.tzinfo is None:
            when = when.replace(tzinfo=UTC)
        for prefix in {"etf.", "stablecoin", "macro.", "macro.hy_spread", "whale", "liquidity."}:
            if str(metric).startswith(prefix):
                current = newest.get(prefix)
                if current is None or when > current:
                    newest[prefix] = when
    return newest


def _next_runs(now: datetime) -> dict[str, str | None]:
    """Computed from the timers, never written as a fixed string.

    A report that says "next run 07:00" at nine in the morning is worse than
    saying nothing: it reads as reassurance while being false.
    """

    import subprocess

    result: dict[str, str | None] = {"full": None, "light": None}
    try:
        output = subprocess.run(
            ["systemctl", "--user", "list-timers", "crypto-intel-*",
             "--no-pager", "--output=json"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        if result and output.returncode == 0 and output.stdout.strip():
            for row in json.loads(output.stdout):
                unit = str(row.get("unit") or "")
                when = row.get("next") or row.get("NEXT")
                key = "light" if "light" in unit else "full"
                result[key] = str(when) if when else None
    except (OSError, ValueError, subprocess.SubprocessError):
        # Health must still report when systemd cannot be queried.
        pass
    return result


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
    if report.sources:
        lines += ["", "  Sources :"]
        for row in sorted(report.sources, key=lambda item: item["source_id"]):
            age = f"{row['age_min']:.0f} min" if row["age_min"] is not None else "—"
            lines.append(
                f"    {row['source_id']:<21} {row['health']:<15} "
                f"{row['freshness']:<12} âge {age:<9} "
                f"max {int(row['max_age_min'])} min  [{row['criticality']}]"
            )
    if report.news_radar:
        radar = report.news_radar
        lines += [
            "",
            "  Radar d'actualité :",
            f"    suivis {radar.get('tracked', 0)}"
            f"  affichés {radar.get('on_home', 0)}"
            f"  expirés {radar.get('expired', 0)}"
            f"  en attente de confirmation {radar.get('unconfirmed', 0)}",
        ]
        by_attention = radar.get("by_attention") or {}
        if by_attention:
            detail = "  ".join(
                f"{level} {count}" for level, count in by_attention.items() if count
            )
            lines.append(f"    attention : {detail or '—'}")
        if radar.get("awaiting_result"):
            # Published but never read back: the one state that silently rots.
            lines.append(
                f"    ⏳ {radar['awaiting_result']} événement(s) passés sans résultat lu"
            )
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

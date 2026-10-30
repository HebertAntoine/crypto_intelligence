"""Repository layer: the only place that translates domain models to rows.

Engines and analysts never touch SQLAlchemy directly.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select

from ..core.data_integrity import is_production_etf_source
from ..core.enums import Asset, DataQuality, Freshness, Timeframe
from ..core.models import Observation, Provenance
from .base import (
    AlertRow,
    ETFFlowRow,
    EventRow,
    FutureEventRow,
    ObservationRow,
    ReportOutcomeRow,
    ReportRow,
)
from .session import session_scope


def _as_utc(dt: datetime | None) -> datetime | None:
    """SQLite hands back naive datetimes even for timezone-aware columns."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _coerce_dt(value: Any) -> datetime | None:
    """Accept a datetime or an ISO string.

    Callers routinely hand us `model_dump(mode="json")` payloads, where
    datetimes have become strings. SQLAlchemy rejects those outright, and the
    resulting TypeError used to be swallowed upstream - which is how the alerts
    table stayed empty while alerts were being generated on every run.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return _as_utc(value)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return _as_utc(parsed)
    return None


def observation_to_row(obs: Observation) -> ObservationRow:
    num: float | None = None
    text: str | None = None
    js: dict[str, Any] | None = None
    if isinstance(obs.value, int | float) and not isinstance(obs.value, bool):
        num = float(obs.value)
    elif isinstance(obs.value, str):
        text = obs.value
    elif isinstance(obs.value, dict):
        js = obs.value
    elif isinstance(obs.value, list):
        js = {"items": obs.value}
    elif isinstance(obs.value, bool):
        num = float(obs.value)

    return ObservationRow(
        id=obs.id,
        asset=obs.asset.value if obs.asset else None,
        metric=obs.metric,
        value_num=num,
        value_text=text,
        value_json=js,
        unit=obs.unit,
        timeframe=obs.timeframe.value if obs.timeframe else None,
        timestamp=obs.timestamp,
        fetched_at=obs.provenance.fetched_at,
        source=obs.provenance.source,
        provider=obs.provenance.provider,
        source_url=obs.provenance.source_url,
        freshness=obs.freshness.value,
        confidence=obs.confidence,
        quality=obs.quality.value,
        meta=obs.meta or None,
    )


def row_to_observation(row: ObservationRow) -> Observation:
    value: Any
    if row.value_num is not None:
        value = row.value_num
    elif row.value_text is not None:
        value = row.value_text
    elif row.value_json is not None:
        value = row.value_json.get("items", row.value_json)
    else:
        value = None

    return Observation(
        id=row.id,
        asset=Asset(row.asset) if row.asset else None,
        metric=row.metric,
        value=value,
        unit=row.unit,
        timeframe=Timeframe(row.timeframe) if row.timeframe else None,
        timestamp=_as_utc(row.timestamp) or datetime.now(UTC),
        provenance=Provenance(
            source=row.source,
            provider=row.provider,
            source_url=row.source_url,
            fetched_at=_as_utc(row.fetched_at) or datetime.now(UTC),
        ),
        freshness=Freshness(row.freshness),
        confidence=row.confidence,
        quality=DataQuality(row.quality),
        meta=row.meta or {},
    )


def save_observations(observations: list[Observation]) -> int:
    """Upsert by deterministic id - re-collection is idempotent."""
    if not observations:
        return 0
    saved = 0
    with session_scope() as s:
        for obs in observations:
            existing = s.get(ObservationRow, obs.id)
            row = observation_to_row(obs)
            if existing is None:
                s.add(row)
            else:
                for field in (
                    "value_num",
                    "value_text",
                    "value_json",
                    "unit",
                    "freshness",
                    "confidence",
                    "quality",
                    "fetched_at",
                    "meta",
                    "source_url",
                ):
                    setattr(existing, field, getattr(row, field))
            saved += 1
    return saved


def latest_observation(
    asset: Asset | None,
    metric: str,
    *,
    as_of: datetime | None = None,
) -> Observation | None:
    with session_scope() as s:
        stmt = select(ObservationRow).where(ObservationRow.metric == metric)
        stmt = stmt.where(ObservationRow.asset == (asset.value if asset else None))
        if as_of is not None:
            stmt = stmt.where(ObservationRow.timestamp <= _coerce_dt(as_of))
        stmt = stmt.order_by(ObservationRow.timestamp.desc()).limit(1)
        row = s.execute(stmt).scalar_one_or_none()
        return row_to_observation(row) if row else None


def observations_since(
    asset: Asset | None, metric_prefix: str, since: datetime, limit: int = 5000
) -> list[Observation]:
    with session_scope() as s:
        stmt = select(ObservationRow).where(
            ObservationRow.metric.like(f"{metric_prefix}%"),
            ObservationRow.timestamp >= since,
        )
        if asset is not None:
            stmt = stmt.where(ObservationRow.asset == asset.value)
        stmt = stmt.order_by(ObservationRow.timestamp.asc()).limit(limit)
        return [row_to_observation(r) for r in s.execute(stmt).scalars().all()]


def observations_by_ids(ids: list[str]) -> list[Observation]:
    """Backing store for the WHY? panel."""
    if not ids:
        return []
    with session_scope() as s:
        rows = s.execute(select(ObservationRow).where(ObservationRow.id.in_(ids))).scalars().all()
        return [row_to_observation(r) for r in rows]


# --- ETF flows ------------------------------------------------------------


def save_etf_flows(rows: list[dict[str, Any]]) -> int:
    """Upsert daily ETF flows. Key is asset|ticker|date so re-importing the
    same CSV corrects rather than duplicates."""
    if not rows:
        return 0
    n = 0
    with session_scope() as s:
        for r in rows:
            if not is_production_etf_source(str(r.get("import_source") or "")):
                continue
            date = _coerce_dt(r["date"])
            if date is None:
                continue
            rid = f"{r['asset']}_{r['ticker']}_{date:%Y%m%d}"
            existing = s.get(ETFFlowRow, rid)
            if existing:
                existing.flow_musd = float(r["flow_musd"])
                existing.import_source = r.get("import_source", "csv")
                existing.source_url = r.get("source_url")
                existing.imported_at = datetime.now(UTC)
            else:
                s.add(
                    ETFFlowRow(
                        id=rid,
                        asset=r["asset"],
                        ticker=r["ticker"],
                        date=date,
                        flow_musd=float(r["flow_musd"]),
                        import_source=r.get("import_source", "csv"),
                        source_url=r.get("source_url"),
                    )
                )
            n += 1
    return n


def get_etf_flows(
    asset: Asset, days: int = 90, *, production_only: bool = True
) -> list[dict[str, Any]]:
    since = datetime.now(UTC) - timedelta(days=days)
    with session_scope() as s:
        stmt = (
            select(ETFFlowRow)
            .where(ETFFlowRow.asset == asset.value, ETFFlowRow.date >= since)
            .order_by(ETFFlowRow.date.asc())
        )
        rows = [
            {
                "id": r.id,
                "date": _as_utc(r.date),
                "ticker": r.ticker,
                "flow_musd": r.flow_musd,
                "import_source": r.import_source,
                "source_url": r.source_url,
            }
            for r in s.execute(stmt).scalars().all()
        ]
        return (
            [row for row in rows if is_production_etf_source(row["import_source"])]
            if production_only
            else rows
        )


def etf_flow_count(asset: Asset, *, production_only: bool = True) -> int:
    with session_scope() as s:
        rows = s.execute(
            select(ETFFlowRow.id, ETFFlowRow.import_source).where(
                ETFFlowRow.asset == asset.value
            )
        ).all()
        return sum(
            not production_only or is_production_etf_source(source)
            for _row_id, source in rows
        )


def purge_non_production_etf_flows() -> int:
    """Delete rows that a fixture/example/mock/sample/test import introduced.

    The source label is persisted with every ETF row, so this cleanup is
    deterministic and never guesses from a flow value.
    """
    with session_scope() as s:
        rows = s.execute(select(ETFFlowRow.id, ETFFlowRow.import_source)).all()
        rejected_ids = [
            row_id
            for row_id, source in rows
            if not is_production_etf_source(source)
        ]
        if rejected_ids:
            s.execute(delete(ETFFlowRow).where(ETFFlowRow.id.in_(rejected_ids)))
        return len(rejected_ids)


# --- reports --------------------------------------------------------------


def save_report(
    report_id: str,
    asset: Asset,
    payload: dict[str, Any],
    text_report: str,
    price: float | None,
    convictions: dict[str, float],
    scores: dict[str, Any],
    confidence: float,
    market_regime: str,
    llm_used: bool,
) -> str:
    with session_scope() as s:
        existing = s.get(ReportRow, report_id)
        if existing:
            s.delete(existing)
            s.flush()
        s.add(
            ReportRow(
                id=report_id,
                asset=asset.value,
                price_at_report=price,
                conviction_short=convictions.get("short"),
                conviction_medium=convictions.get("medium"),
                conviction_long=convictions.get("long"),
                confidence=confidence,
                market_regime=market_regime,
                scores=scores,
                payload=payload,
                text_report=text_report,
                llm_used=llm_used,
            )
        )
    return report_id


def get_report(report_id: str) -> dict[str, Any] | None:
    with session_scope() as s:
        r = s.get(ReportRow, report_id)
        if not r:
            return None
        return _report_dict(r)


def latest_report(asset: Asset) -> dict[str, Any] | None:
    with session_scope() as s:
        stmt = (
            select(ReportRow)
            .where(ReportRow.asset == asset.value)
            .order_by(ReportRow.created_at.desc())
            .limit(1)
        )
        r = s.execute(stmt).scalar_one_or_none()
        return _report_dict(r) if r else None


def list_reports(asset: Asset | None = None, limit: int = 50) -> list[dict[str, Any]]:
    with session_scope() as s:
        stmt = select(ReportRow).order_by(ReportRow.created_at.desc()).limit(limit)
        if asset:
            stmt = stmt.where(ReportRow.asset == asset.value)
        return [_report_dict(r) for r in s.execute(stmt).scalars().all()]


def reports_needing_evaluation(older_than_minutes: int = 60) -> list[dict[str, Any]]:
    cutoff = datetime.now(UTC) - timedelta(minutes=older_than_minutes)
    with session_scope() as s:
        stmt = select(ReportRow).where(ReportRow.created_at <= cutoff)
        return [_report_dict(r) for r in s.execute(stmt).scalars().all()]


def _report_dict(r: ReportRow) -> dict[str, Any]:
    return {
        "id": r.id,
        "asset": r.asset,
        "created_at": _as_utc(r.created_at),
        "price_at_report": r.price_at_report,
        "conviction_short": r.conviction_short,
        "conviction_medium": r.conviction_medium,
        "conviction_long": r.conviction_long,
        "confidence": r.confidence,
        "market_regime": r.market_regime,
        "scores": r.scores or {},
        "payload": r.payload or {},
        "text_report": r.text_report or "",
        "llm_used": r.llm_used,
    }


def save_outcome(
    report_id: str,
    asset: Asset,
    horizon: str,
    price_then: float,
    price_now: float,
    predicted_direction: str,
) -> None:
    ret = ((price_now - price_then) / price_then * 100.0) if price_then else 0.0
    actual = "BULLISH" if ret > 0.15 else ("BEARISH" if ret < -0.15 else "NEUTRAL")
    correct: bool | None = None
    if predicted_direction in ("BULLISH", "BEARISH") and actual != "NEUTRAL":
        correct = predicted_direction == actual

    with session_scope() as s:
        stmt = select(ReportOutcomeRow).where(
            ReportOutcomeRow.report_id == report_id, ReportOutcomeRow.horizon == horizon
        )
        existing = s.execute(stmt).scalar_one_or_none()
        if existing:
            existing.price_now = price_now
            existing.return_pct = ret
            existing.actual_direction = actual
            existing.correct = correct
            existing.evaluated_at = datetime.now(UTC)
        else:
            s.add(
                ReportOutcomeRow(
                    report_id=report_id,
                    asset=asset.value,
                    horizon=horizon,
                    price_then=price_then,
                    price_now=price_now,
                    return_pct=ret,
                    predicted_direction=predicted_direction,
                    actual_direction=actual,
                    correct=correct,
                )
            )


def get_outcomes(asset: Asset | None = None) -> list[dict[str, Any]]:
    with session_scope() as s:
        stmt = select(ReportOutcomeRow)
        if asset:
            stmt = stmt.where(ReportOutcomeRow.asset == asset.value)
        return [
            {
                "report_id": r.report_id,
                "asset": r.asset,
                "horizon": r.horizon,
                "return_pct": r.return_pct,
                "predicted_direction": r.predicted_direction,
                "actual_direction": r.actual_direction,
                "correct": r.correct,
                "evaluated_at": _as_utc(r.evaluated_at),
            }
            for r in s.execute(stmt).scalars().all()
        ]


def has_outcome(report_id: str, horizon: str) -> bool:
    with session_scope() as s:
        stmt = select(ReportOutcomeRow.id).where(
            ReportOutcomeRow.report_id == report_id, ReportOutcomeRow.horizon == horizon
        )
        return s.execute(stmt).first() is not None


# --- alerts ---------------------------------------------------------------


def _alert_text(value: Any) -> str | None:
    if value is None:
        return None
    enum_value = getattr(value, "value", value)
    text_value = str(enum_value).strip()
    return text_value or None


def _alert_receipt_identity(
    alert: dict[str, Any], triggered_at: datetime
) -> tuple[str, str]:
    """Return stable trigger and notification identifiers for one event.

    ``trigger_id`` identifies the condition (and therefore follows the legacy
    cooldown key). ``notification_id`` identifies this exact occurrence, so a
    retry of the same payload is idempotent while a later post-cooldown event
    receives a distinct receipt.
    """

    asset_id = _alert_text(alert.get("asset_id") or alert.get("asset")) or "GLOBAL"
    trigger_id = _alert_text(alert.get("trigger_id") or alert.get("dedup_key"))
    if trigger_id is None:
        trigger_seed = "|".join(
            (
                _alert_text(alert.get("kind")) or "ALERT",
                asset_id,
                _alert_text(alert.get("title")) or "",
                _alert_text(alert.get("reason")) or "",
            )
        )
        trigger_id = "trigger_" + hashlib.sha256(trigger_seed.encode()).hexdigest()[:24]

    event_time = triggered_at.astimezone(UTC).isoformat(timespec="microseconds")
    notification_seed = "|".join(
        (trigger_id, event_time, _alert_text(alert.get("kind")) or "ALERT", asset_id)
    )
    notification_id = "ntf_" + hashlib.sha256(notification_seed.encode()).hexdigest()[:32]
    return trigger_id, notification_id


def save_alerts(alerts: list[dict[str, Any]]) -> int:
    """Atomically persist in-app alerts and their delivery receipts.

    The cooldown is checked again under SQLite's immediate write transaction;
    the earlier engine-side check remains a cheap fast path. ``STORED`` is the
    only status written because database acceptance *is* delivery for the
    in-app inbox. The function returns only after commit and never reports an
    optimistic ``SENT`` state.
    """

    if not alerts:
        return 0
    stored = 0
    with session_scope(immediate=True) as s:
        for a in alerts:
            triggered_at = _coerce_dt(a.get("triggered_at")) or datetime.now(UTC)
            trigger_id, notification_id = _alert_receipt_identity(a, triggered_at)
            dedup_key = _alert_text(a.get("dedup_key")) or trigger_id
            cooldown_minutes = max(0, int(a.get("cooldown_minutes") or 0))

            # Exact retries are idempotent even when no cooldown was supplied.
            already_stored = s.execute(
                select(AlertRow.id).where(AlertRow.notification_id == notification_id)
            ).first()
            if already_stored is not None:
                continue

            if cooldown_minutes:
                last = s.execute(
                    select(AlertRow.triggered_at)
                    .where(AlertRow.dedup_key == dedup_key)
                    .order_by(AlertRow.triggered_at.desc())
                    .limit(1)
                ).scalar_one_or_none()
                last = _as_utc(last)
                if last is not None and triggered_at - last < timedelta(
                    minutes=cooldown_minutes
                ):
                    continue

            accepted_at = datetime.now(UTC)
            asset_id = _alert_text(a.get("asset_id") or a.get("asset"))
            analysis_id = _alert_text(a.get("analysis_id"))
            evidence_ids = list(a.get("evidence_ids") or [])
            reason = _alert_text(a.get("reason")) or ""
            supplied_snapshot = a.get("source_snapshot")
            source_snapshot = (
                dict(supplied_snapshot) if isinstance(supplied_snapshot, dict) else {}
            )
            # Canonical receipt coordinates cannot be spoofed by a caller's
            # optional snapshot fields.
            source_snapshot.update(
                {
                    "notification_id": notification_id,
                    "trigger_id": trigger_id,
                    "asset_id": asset_id,
                    "analysis_id": analysis_id,
                    "kind": a["kind"],
                    "triggered_at": triggered_at.isoformat(),
                    "evidence_ids": evidence_ids,
                    "reason": reason,
                }
            )
            s.add(
                AlertRow(
                    kind=a["kind"],
                    importance=a["importance"],
                    asset=asset_id,
                    title=a["title"],
                    detail=a.get("detail", ""),
                    triggered_at=triggered_at,
                    evidence_ids=evidence_ids or None,
                    dedup_key=dedup_key,
                    reason=reason,
                    notification_id=notification_id,
                    trigger_id=trigger_id,
                    asset_id=asset_id,
                    analysis_id=analysis_id,
                    created_at=accepted_at,
                    delivered_at=accepted_at,
                    delivery_status="STORED",
                    source_snapshot=source_snapshot,
                )
            )
            stored += 1
    return stored


def recent_alerts(limit: int = 50, asset: Asset | None = None) -> list[dict[str, Any]]:
    with session_scope() as s:
        stmt = select(AlertRow).order_by(AlertRow.triggered_at.desc()).limit(limit)
        if asset:
            stmt = stmt.where(AlertRow.asset == asset.value)
        return [
            {
                "id": r.id,
                "kind": r.kind,
                "importance": r.importance,
                "asset": r.asset,
                "title": r.title,
                "detail": r.detail,
                "triggered_at": _as_utc(r.triggered_at),
                "evidence_ids": r.evidence_ids or [],
                "acknowledged": r.acknowledged,
                # Legacy rows predate receipts. Their primary key remains a
                # stable notification coordinate, while nullable facts stay
                # explicitly unknown rather than being invented.
                "notification_id": r.notification_id or f"legacy-alert-{r.id}",
                "trigger_id": r.trigger_id or r.dedup_key,
                "asset_id": r.asset_id or r.asset,
                "analysis_id": r.analysis_id,
                "created_at": _as_utc(r.created_at) or _as_utc(r.triggered_at),
                "delivered_at": _as_utc(r.delivered_at),
                "delivery_status": r.delivery_status or "UNKNOWN",
                "reason": r.reason,
                "source_snapshot": r.source_snapshot or {},
            }
            for r in s.execute(stmt).scalars().all()
        ]


# --- events ---------------------------------------------------------------


def save_events(events: list[dict[str, Any]]) -> int:
    if not events:
        return 0
    with session_scope() as s:
        for e in events:
            existing = s.get(EventRow, e["id"])
            if existing:
                existing.name = e["name"]
                existing.summary = e.get("summary", "")
                existing.importance = e.get("importance", "INFO")
                existing.legal_status = e.get("legal_status")
                continue
            s.add(
                EventRow(
                    id=e["id"],
                    kind=e["kind"],
                    name=e["name"],
                    institution=e.get("institution"),
                    legal_status=e.get("legal_status"),
                    scheduled_at=_coerce_dt(e["scheduled_at"]) or datetime.now(UTC),
                    importance=e.get("importance", "INFO"),
                    summary=e.get("summary", ""),
                    source_url=e.get("source_url"),
                    source_name=e.get("source_name"),
                    assets=e.get("assets"),
                    meta=e.get("meta"),
                )
            )
    return len(events)


def upcoming_events(days: int = 30, limit: int = 40) -> list[dict[str, Any]]:
    now = datetime.now(UTC)
    until = now + timedelta(days=days)
    with session_scope() as s:
        stmt = (
            select(EventRow)
            .where(EventRow.scheduled_at >= now, EventRow.scheduled_at <= until)
            .order_by(EventRow.scheduled_at.asc())
            .limit(limit)
        )
        return [_event_dict(r, now) for r in s.execute(stmt).scalars().all()]


def recent_events(days: int = 14, kind: str | None = None, limit: int = 60) -> list[dict[str, Any]]:
    now = datetime.now(UTC)
    since = now - timedelta(days=days)
    with session_scope() as s:
        stmt = (
            select(EventRow)
            .where(EventRow.scheduled_at >= since, EventRow.scheduled_at <= now)
            .order_by(EventRow.scheduled_at.desc())
            .limit(limit)
        )
        if kind:
            stmt = stmt.where(EventRow.kind == kind)
        return [_event_dict(r, now) for r in s.execute(stmt).scalars().all()]


def _event_dict(r: EventRow, now: datetime) -> dict[str, Any]:
    sched = _as_utc(r.scheduled_at) or now
    return {
        "id": r.id,
        "kind": r.kind,
        "name": r.name,
        "institution": r.institution,
        "legal_status": r.legal_status,
        "scheduled_at": sched,
        "importance": r.importance,
        "summary": r.summary,
        "source_url": r.source_url,
        "source_name": r.source_name,
        "assets": r.assets or [],
        "hours_until": (sched - now).total_seconds() / 3600.0,
        "is_past": sched < now,
    }


# --- future events --------------------------------------------------------


def save_future_events(events: list[Any]) -> int:
    """Upsert canonical FutureEvent objects without persisting freshness."""
    if not events:
        return 0
    from ..future_events.models import FutureEvent

    saved = 0
    with session_scope() as s:
        for event in events:
            if not isinstance(event, FutureEvent):
                event = FutureEvent.model_validate(event)
            row = _future_event_to_row(event)
            existing = s.get(FutureEventRow, event.canonical_event_id)
            if existing is None:
                s.add(row)
            else:
                for column in FutureEventRow.__table__.columns:
                    if column.name == "id":
                        continue
                    attr = "metadata_json" if column.name == "metadata" else column.name
                    setattr(existing, attr, getattr(row, attr))
            saved += 1
    return saved


def _future_event_to_row(event: Any) -> FutureEventRow:
    return FutureEventRow(
        id=event.canonical_event_id,
        canonical_event_id=event.canonical_event_id,
        event_signature=event.event_signature,
        event_type=event.event_type,
        category=event.category.value,
        schedule_type=event.schedule_type.value,
        title=event.title,
        normalized_title=event.normalized_title,
        source=event.source,
        source_tier=event.source_tier.value,
        source_url=event.source_url,
        source_reference=event.source_reference,
        source_published_at=event.source_published_at,
        detected_at=event.detected_at,
        scheduled_at=event.scheduled_at,
        timezone=event.timezone,
        expected_end_at=event.expected_end_at,
        status=event.status.value,
        affected_assets=[asset.value for asset in event.affected_assets] or None,
        affected_markets=event.affected_markets or None,
        importance=event.importance.value,
        consensus=event.consensus,
        outcome_space=event.outcome_space or None,
        market_probabilities=[
            probability.model_dump(mode="json") for probability in event.market_probabilities
        ]
        or None,
        probability_timestamp=event.probability_timestamp,
        expected_value=event.expected_value,
        previous_value=event.previous_value,
        actual_value=event.actual_value,
        surprise=event.surprise,
        directional_effect=event.directional_effect.value,
        magnitude_effect=event.magnitude_effect.value,
        time_horizon=event.time_horizon.value,
        confidence=event.confidence,
        causal_chain=event.causal_chain or None,
        evidence_ids=event.evidence_ids or None,
        last_updated=event.last_updated,
        expires_at=event.expires_at,
        source_references=[
            reference.model_dump(mode="json") for reference in event.source_references
        ]
        or None,
        metadata_json=event.metadata or None,
    )


def _row_to_future_event(row: FutureEventRow) -> Any:
    from ..future_events.models import FutureEvent

    return FutureEvent.model_validate(
        {
            "id": row.id,
            "canonical_event_id": row.canonical_event_id,
            "event_signature": row.event_signature,
            "event_type": row.event_type,
            "category": row.category,
            "schedule_type": row.schedule_type,
            "title": row.title,
            "normalized_title": row.normalized_title,
            "source": row.source,
            "source_tier": row.source_tier,
            "source_url": row.source_url,
            "source_reference": row.source_reference,
            "source_published_at": _as_utc(row.source_published_at),
            "detected_at": _as_utc(row.detected_at),
            "scheduled_at": _as_utc(row.scheduled_at),
            "timezone": row.timezone,
            "expected_end_at": _as_utc(row.expected_end_at),
            "status": row.status,
            "affected_assets": row.affected_assets or [],
            "affected_markets": row.affected_markets or [],
            "importance": row.importance,
            "consensus": row.consensus,
            "outcome_space": row.outcome_space or [],
            "market_probabilities": row.market_probabilities or [],
            "probability_timestamp": _as_utc(row.probability_timestamp),
            "expected_value": row.expected_value,
            "previous_value": row.previous_value,
            "actual_value": row.actual_value,
            "surprise": row.surprise,
            "directional_effect": row.directional_effect,
            "magnitude_effect": row.magnitude_effect,
            "time_horizon": row.time_horizon,
            "confidence": row.confidence,
            "causal_chain": row.causal_chain or [],
            "evidence_ids": row.evidence_ids or [],
            "last_updated": _as_utc(row.last_updated),
            "expires_at": _as_utc(row.expires_at),
            "source_references": row.source_references or [],
            "metadata": row.metadata_json or {},
        }
    )


def future_event(event_id: str) -> Any | None:
    with session_scope() as s:
        row = s.get(FutureEventRow, event_id)
        return _row_to_future_event(row) if row else None


def list_future_events(
    *,
    asset: Asset | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    include_expired: bool = False,
    limit: int = 200,
) -> list[Any]:
    """Read rich events; asset filtering stays portable across JSON dialects."""
    from ..future_events.models import FutureEventStatus

    with session_scope() as s:
        stmt = select(FutureEventRow)
        if start is not None:
            stmt = stmt.where(
                (FutureEventRow.scheduled_at >= start)
                | ((FutureEventRow.scheduled_at.is_(None)) & (FutureEventRow.detected_at >= start))
            )
        if end is not None:
            stmt = stmt.where(
                (FutureEventRow.scheduled_at <= end)
                | ((FutureEventRow.scheduled_at.is_(None)) & (FutureEventRow.detected_at <= end))
            )
        rows = (
            s.execute(
                stmt.order_by(
                    FutureEventRow.scheduled_at.asc(), FutureEventRow.detected_at.desc()
                ).limit(limit * 3)
            )
            .scalars()
            .all()
        )

    events = [_row_to_future_event(row) for row in rows]
    if asset is not None:
        events = [
            event for event in events if not event.affected_assets or asset in event.affected_assets
        ]
    if not include_expired:
        now = datetime.now(UTC)
        events = [
            event for event in events if event.runtime_status(now) is not FutureEventStatus.EXPIRED
        ]
    return events[:limit]


def future_event_fingerprint() -> dict[str, Any]:
    """Return a compact content fingerprint for every persisted future event.

    Future events are market-wide inputs and can affect several assets.  A
    global digest is therefore intentional: changing a regulatory or macro
    event invalidates every cached asset analysis instead of risking a stale
    decision because JSON asset filtering behaved differently across database
    backends.
    """
    columns = (
        FutureEventRow.canonical_event_id,
        FutureEventRow.event_signature,
        FutureEventRow.status,
        FutureEventRow.scheduled_at,
        FutureEventRow.importance,
        FutureEventRow.directional_effect,
        FutureEventRow.magnitude_effect,
        FutureEventRow.confidence,
        FutureEventRow.consensus,
        FutureEventRow.expected_value,
        FutureEventRow.actual_value,
        FutureEventRow.surprise,
        FutureEventRow.market_probabilities,
        FutureEventRow.probability_timestamp,
        FutureEventRow.last_updated,
    )
    with session_scope() as s:
        rows = s.execute(select(*columns).order_by(FutureEventRow.canonical_event_id.asc())).all()
    payload = json.dumps(
        [list(row) for row in rows],
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return {
        "count": len(rows),
        "sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
    }


def purge_old_observations(days: int = 400) -> int:
    cutoff = datetime.now(UTC) - timedelta(days=days)
    with session_scope() as s:
        res = s.execute(delete(ObservationRow).where(ObservationRow.timestamp < cutoff))
        return res.rowcount or 0


def observation_fingerprint(
    asset: Asset,
    prefixes: tuple[str, ...] = (
        "price.",
        "onchain.",
        "stablecoin.",
        "macro.",
        "whale.",
    ),
) -> dict[str, list[Any]]:
    """Row count and last timestamp per observation family, plus ETF flows.

    Same purpose as `store.series_fingerprint`: name the inputs an analysis
    was built from, cheaply enough to check on every request.
    """
    from sqlalchemy import func, or_

    out: dict[str, list[Any]] = {}
    with session_scope() as s:
        for prefix in prefixes:
            # Asset-scoped families are stored against the asset; market-wide
            # ones (stablecoins, macro) carry no asset at all.
            rows, last = s.execute(
                select(func.count(ObservationRow.id), func.max(ObservationRow.timestamp)).where(
                    ObservationRow.metric.like(f"{prefix}%"),
                    or_(ObservationRow.asset == asset.value, ObservationRow.asset.is_(None)),
                )
            ).one()
            observed = _as_utc(last)
            out[f"observations:{prefix}"] = [
                int(rows or 0),
                observed.isoformat() if observed else None,
            ]
        etf_rows = s.execute(
            select(ETFFlowRow.date, ETFFlowRow.import_source).where(
                ETFFlowRow.asset == asset.value
            )
        ).all()
        production_dates = [
            date for date, source in etf_rows if is_production_etf_source(source)
        ]
        observed = _as_utc(max(production_dates, default=None))
        out["etf_flows"] = [
            len(production_dates), observed.isoformat() if observed else None
        ]
    return out

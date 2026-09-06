"""Immutable prediction snapshots and their later evaluation.

The evaluation layer only means something if what was recorded at time T is
never touched afterwards. Otherwise a revised macro figure, a corrected ETF
flow, or a code change quietly rewrites history and the accuracy statistics
become self-congratulation.

So a prediction snapshot is:
  * written once, with a content hash;
  * never updated - re-running at the same moment is a no-op, not an overwrite;
  * verified on read, so tampering is detectable rather than silent.

Outcomes are stored separately and reference the snapshot by id. Facts and
consequences never share a row.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from ..core.enums import Asset
from ..db.base import PredictionOutcomeRow, PredictionSnapshotRow
from ..db.session import session_scope
from ..logging_setup import get_logger

log = get_logger("history.immutable")

# Horizons the brief asks for.
HORIZONS: dict[str, timedelta] = {
    "1h": timedelta(hours=1),
    "4h": timedelta(hours=4),
    "1d": timedelta(days=1),
    "3d": timedelta(days=3),
    "7d": timedelta(days=7),
    "14d": timedelta(days=14),
    "30d": timedelta(days=30),
}


def content_hash(payload: dict[str, Any]) -> str:
    """Stable hash of the recorded prediction, used to detect any later edit."""
    canonical = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass(slots=True)
class SnapshotResult:
    snapshot_id: str
    created: bool
    reason: str = ""


def record_prediction(
    asset: Asset,
    price: float | None,
    regime: dict[str, Any],
    entry_timing: dict[str, Any],
    conviction: dict[str, Any],
    scores: dict[str, Any],
    scenarios: list[dict[str, Any]],
    data_quality: dict[str, Any],
    when: datetime | None = None,
) -> SnapshotResult:
    """Write an immutable prediction snapshot.

    Bucketed to the hour: two runs inside the same hour record one prediction
    rather than two near-identical ones. The existing row is NOT updated - the
    first observation of that hour is what stands.
    """
    when = when or datetime.now(UTC)
    bucket = when.strftime("%Y%m%d%H")
    snapshot_id = f"pred_{asset.value}_{bucket}"

    payload = {
        "asset": asset.value,
        "recorded_at": when.isoformat(),
        "price": price,
        "regime": {
            "regime": regime.get("regime"),
            "regime_score": regime.get("regime_score"),
            "confidence": regime.get("confidence"),
            "conditions": regime.get("conditions"),
        },
        "entry_timing": {
            "timing": entry_timing.get("timing"),
            "timing_score": entry_timing.get("timing_score"),
            "confidence": entry_timing.get("confidence"),
            "invalidation_level": entry_timing.get("invalidation_level"),
        },
        "conviction": {
            horizon: {
                "score": (conviction.get(horizon) or {}).get("score"),
                "label": (conviction.get(horizon) or {}).get("label"),
                "confidence": (conviction.get(horizon) or {}).get("confidence"),
                "direction": (conviction.get(horizon) or {}).get("direction"),
            }
            for horizon in ("short", "medium", "long")
        },
        "overall_confidence": conviction.get("overall_confidence"),
        "scores": {
            domain: {
                "score": card.get("score"),
                "confidence": card.get("confidence"),
                "available": card.get("available"),
                "freshness": card.get("freshness"),
            }
            for domain, card in (scores or {}).items()
        },
        "scenarios": [
            {"name": s.get("name"), "probability": s.get("probability")}
            for s in (scenarios or [])
        ],
        "data_quality": data_quality,
    }

    digest = content_hash(payload)

    with session_scope() as s:
        existing = s.get(PredictionSnapshotRow, snapshot_id)
        if existing is not None:
            # Immutability: the first record of this hour stands. A second run
            # is a no-op, not an update.
            return SnapshotResult(
                snapshot_id=snapshot_id, created=False,
                reason="A snapshot already exists for this hour and is never overwritten",
            )
        s.add(
            PredictionSnapshotRow(
                id=snapshot_id,
                asset=asset.value,
                recorded_at=when,
                bucket=bucket,
                price=price,
                regime=payload["regime"].get("regime"),
                entry_timing=payload["entry_timing"].get("timing"),
                conviction_medium=payload["conviction"]["medium"].get("score"),
                payload=payload,
                content_hash=digest,
            )
        )

    log.info("prediction_recorded", asset=asset.value, snapshot=snapshot_id)
    return SnapshotResult(snapshot_id=snapshot_id, created=True)


def verify_integrity(snapshot_id: str) -> dict[str, Any]:
    """Check a snapshot's payload still matches the hash written with it."""
    with session_scope() as s:
        row = s.get(PredictionSnapshotRow, snapshot_id)
        if row is None:
            return {"snapshot_id": snapshot_id, "found": False}
        recomputed = content_hash(row.payload or {})
        return {
            "snapshot_id": snapshot_id,
            "found": True,
            "intact": recomputed == row.content_hash,
            "stored_hash": row.content_hash,
            "recomputed_hash": recomputed,
        }


def verify_all() -> dict[str, Any]:
    with session_scope() as s:
        rows = s.execute(select(PredictionSnapshotRow)).scalars().all()
        checked = []
        for row in rows:
            recomputed = content_hash(row.payload or {})
            checked.append({
                "snapshot_id": row.id,
                "intact": recomputed == row.content_hash,
            })
    tampered = [c for c in checked if not c["intact"]]
    return {
        "total": len(checked),
        "intact": len(checked) - len(tampered),
        "tampered": tampered,
        "all_intact": not tampered,
    }


def pending_evaluations(now: datetime | None = None) -> list[dict[str, Any]]:
    """Snapshots whose horizons have elapsed but are not yet scored."""
    now = now or datetime.now(UTC)
    pending: list[dict[str, Any]] = []

    with session_scope() as s:
        snapshots = s.execute(select(PredictionSnapshotRow)).scalars().all()
        scored = {
            (row.snapshot_id, row.horizon)
            for row in s.execute(select(PredictionOutcomeRow)).scalars().all()
        }

        for snapshot in snapshots:
            recorded = (
                snapshot.recorded_at if snapshot.recorded_at.tzinfo
                else snapshot.recorded_at.replace(tzinfo=UTC)
            )
            for horizon, delta in HORIZONS.items():
                if (snapshot.id, horizon) in scored:
                    continue
                target = recorded + delta
                if target > now:
                    continue
                pending.append({
                    "snapshot_id": snapshot.id,
                    "asset": snapshot.asset,
                    "horizon": horizon,
                    "recorded_at": recorded,
                    "target_at": target,
                    "price_then": snapshot.price,
                    "regime": snapshot.regime,
                    "entry_timing": snapshot.entry_timing,
                    "conviction_medium": snapshot.conviction_medium,
                })
    return pending


def record_outcome(
    snapshot_id: str,
    asset: Asset,
    horizon: str,
    price_then: float,
    price_now: float,
    predicted_direction: str,
    regime: str | None,
    entry_timing: str | None,
) -> bool:
    """Store what actually happened. Written once per (snapshot, horizon)."""
    if not price_then:
        return False

    return_pct = (price_now - price_then) / price_then * 100.0
    # A flat move is neither a hit nor a miss; the dead band avoids scoring noise.
    actual = (
        "BULLISH" if return_pct > 0.15
        else "BEARISH" if return_pct < -0.15
        else "NEUTRAL"
    )
    correct: bool | None = None
    if predicted_direction in ("BULLISH", "BEARISH") and actual != "NEUTRAL":
        correct = predicted_direction == actual

    outcome_id = f"{snapshot_id}:{horizon}"
    with session_scope() as s:
        if s.get(PredictionOutcomeRow, outcome_id) is not None:
            return False
        s.add(
            PredictionOutcomeRow(
                id=outcome_id,
                snapshot_id=snapshot_id,
                asset=asset.value,
                horizon=horizon,
                price_then=price_then,
                price_now=price_now,
                return_pct=return_pct,
                predicted_direction=predicted_direction,
                actual_direction=actual,
                correct=correct,
                regime_at_prediction=regime,
                timing_at_prediction=entry_timing,
            )
        )
    return True


def evaluate_pending(price_lookup, now: datetime | None = None) -> dict[str, Any]:
    """Score every elapsed horizon. `price_lookup(asset, at) -> float | None`."""
    pending = pending_evaluations(now)
    written = 0
    skipped = 0

    for item in pending:
        asset = Asset(item["asset"])
        price_now = price_lookup(asset, item["target_at"])
        if price_now is None or not item["price_then"]:
            skipped += 1
            continue
        direction = (
            "BULLISH" if (item["conviction_medium"] or 0) > 8
            else "BEARISH" if (item["conviction_medium"] or 0) < -8
            else "NEUTRAL"
        )
        if record_outcome(
            item["snapshot_id"], asset, item["horizon"],
            item["price_then"], price_now, direction,
            item["regime"], item["entry_timing"],
        ):
            written += 1

    return {"pending": len(pending), "written": written, "skipped": skipped}


def live_performance(asset: Asset | None = None) -> dict[str, Any]:
    """Live accuracy, kept strictly separate from backtest results.

    Backtest numbers come from replaying today's logic over old candles. These
    come from predictions the system actually made, before the outcome existed.
    Conflating the two is how a backtest gets mistaken for a track record.
    """
    with session_scope() as s:
        stmt = select(PredictionOutcomeRow)
        if asset is not None:
            stmt = stmt.where(PredictionOutcomeRow.asset == asset.value)
        outcomes = s.execute(stmt).scalars().all()
        snapshot_count = len(
            s.execute(
                select(PredictionSnapshotRow.id).where(
                    PredictionSnapshotRow.asset == asset.value
                ) if asset else select(PredictionSnapshotRow.id)
            ).all()
        )

    if not outcomes:
        return {
            "available": False,
            "snapshots": snapshot_count,
            "outcomes": 0,
            "reason": (
                "No live outcome recorded yet. Live performance needs predictions old "
                "enough for their horizons to have elapsed - run the scheduler for a "
                "few days. Until then, only backtest figures exist, and they are not "
                "a track record."
            ),
        }

    by_horizon: dict[str, list[Any]] = {}
    for outcome in outcomes:
        by_horizon.setdefault(outcome.horizon, []).append(outcome)

    stats: dict[str, Any] = {}
    for horizon, rows in by_horizon.items():
        scored = [r for r in rows if r.correct is not None]
        returns = [r.return_pct for r in rows if r.return_pct is not None]
        stats[horizon] = {
            "n": len(rows),
            "n_directional": len(scored),
            "accuracy": (
                round(sum(1 for r in scored if r.correct) / len(scored) * 100.0, 1)
                if scored else None
            ),
            "mean_return": round(sum(returns) / len(returns), 3) if returns else None,
            "reliable": len(scored) >= 30,
        }

    return {
        "available": True,
        "source": "live",
        "snapshots": snapshot_count,
        "outcomes": len(outcomes),
        "by_horizon": stats,
        "note": (
            "These are predictions the system actually made, evaluated after the fact. "
            "They are NOT comparable to backtest figures, which replay current logic "
            "over historical data. Samples under 30 are marked unreliable."
        ),
    }

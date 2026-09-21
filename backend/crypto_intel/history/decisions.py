"""The reading's own history: when the verdict changed, and what changed with it.

"Timing passé de À SURVEILLER à ATTENDRE à 21:00" is only worth showing if it
is true, and it is only true if the earlier reading was written down when it
was current. So this reads recorded snapshots and nothing else. It never
reconstructs a past verdict from today's data: re-running an engine on today's
candles answers what we would say now, not what we said then.

When there is not enough recorded history to name a change, the answer is
nothing at all rather than a plausible sentence.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from ..core.enums import Asset
from ..logging_setup import get_logger
from .snapshots import load_snapshots, save_snapshot

log = get_logger("history.decisions")

KIND = "decision"


def record_decision(snapshot: Any, future: dict[str, Any] | None = None) -> bool:
    """Write what the system concluded, at the moment it concluded it.

    `future` holds, per horizon, the verdict shown on the page and the one
    line that explains it - so « ATTENDRE depuis 3 jours » is a record, not a
    reconstruction.
    """
    opportunity = snapshot.opportunity
    location_state = str(
        getattr(getattr(snapshot.location, "state", None), "value", "") or ""
    )
    dominant = (
        (opportunity.negatives or opportunity.waits or opportunity.positives or [])[:1]
    )
    payload = {
        "analysis_id": snapshot.analysis_id,
        "state": opportunity.state.value,
        "headline": opportunity.headline,
        "summary": opportunity.summary,
        "regime": str(getattr(getattr(snapshot.regime, "regime", None), "value", "")),
        "edge_state": opportunity.measured_edge_state,
        "location_state": location_state,
        "relative_position": getattr(snapshot.location, "relative_position", None),
        "pressure_state": getattr(snapshot.pressure, "state", None),
        "pressure_score": getattr(snapshot.pressure, "pressure_score", None),
        "dominant_factor": dominant[0].title if dominant else "",
        "dominant_factor_text": dominant[0].short_text if dominant else "",
        "guard_rails": list(opportunity.guard_rails_applied),
    }
    if future:
        payload["future"] = future
    return save_snapshot(
        KIND, Asset(snapshot.asset), payload,
        price=snapshot.price_at_analysis, when=snapshot.analysis_time,
    )


def last_decision_change(
    asset: Asset, lookback_days: int = 14, now: datetime | None = None
) -> dict[str, Any] | None:
    """The most recent recorded change of verdict, or nothing.

    Returns None when fewer than two readings were recorded, or when the
    verdict has not moved inside the window: an unchanged reading is not a
    change, and saying "no change since 14 days" would claim a history we may
    not have.
    """
    reference = now or datetime.now(UTC)
    rows = load_snapshots(
        KIND, asset, since=reference - timedelta(days=lookback_days), limit=800
    )
    if len(rows) < 2:
        return None

    current = str((rows[0].get("payload") or {}).get("state") or "")
    if not current:
        return None
    for index in range(1, len(rows)):
        payload = rows[index].get("payload") or {}
        previous = str(payload.get("state") or "")
        if not previous or previous == current:
            continue
        changed = rows[index - 1]
        newer = changed.get("payload") or {}
        return {
            "changed_at": changed["captured_at"].isoformat(),
            "from_state": previous,
            "to_state": current,
            # The reason is the factor the newer reading itself recorded as
            # dominant, not an explanation written afterwards.
            "reason": newer.get("dominant_factor_text") or newer.get("summary") or "",
            "reason_title": newer.get("dominant_factor") or "",
            "guard_rails": newer.get("guard_rails") or [],
            "readings_examined": len(rows),
            "window_days": lookback_days,
        }
    return None


def decision_history(
    asset: Asset, lookback_days: int = 14, now: datetime | None = None
) -> list[dict[str, Any]]:
    """Recorded readings, newest first, for the evidence screen."""
    reference = now or datetime.now(UTC)
    rows = load_snapshots(
        KIND, asset, since=reference - timedelta(days=lookback_days), limit=800
    )
    return [
        {"captured_at": row["captured_at"].isoformat(), "price": row.get("price"),
         **(row.get("payload") or {})}
        for row in rows
    ]


VERDICT_FR = {"BUY": "Acheter", "WAIT": "Attendre", "SELL": "Vendre",
              "INSUFFICIENT_DATA": "Données insuffisantes"}


def decision_streak(asset: Asset, horizon: str, lookback_days: int = 30,
                    now: datetime | None = None) -> dict[str, Any] | None:
    """How long the page's verdict has held, and why it did not change.

    Built only from recorded readings. When the streak reaches the oldest
    record, it says « depuis au moins »: we do not claim a history we lack.
    """

    reference = now or datetime.now(UTC)
    rows = [r for r in load_snapshots(KIND, asset, since=reference - timedelta(days=lookback_days),
                                      limit=3000)
            if ((r.get("payload") or {}).get("future") or {}).get(horizon)]
    if not rows:
        return None
    current = rows[0]["payload"]["future"][horizon]
    streak = [rows[0]]
    for row in rows[1:]:
        if row["payload"]["future"][horizon].get("action") != current.get("action"):
            break
        streak.append(row)
    complete = len(streak) < len(rows)
    since = streak[-1]["captured_at"]
    steps: list[dict[str, Any]] = []
    for row in reversed(streak):
        reading = row["payload"]["future"][horizon]
        reason = reading.get("reason") or ""
        if steps and steps[-1]["reason"] == reason:
            continue
        steps.append({"at": row["captured_at"].isoformat(),
                      "label": VERDICT_FR.get(reading.get("action"), reading.get("action")),
                      "reason": reason})
    days = (reference - since).total_seconds() / 86400
    span = (f"{int(days)} jour{'s' if int(days) > 1 else ''}" if days >= 1
            else f"{max(1, int(days * 24))} h")
    label = VERDICT_FR.get(current.get("action"), current.get("action"))
    return {
        "action": current.get("action"),
        "since": since.isoformat(),
        "complete": complete,
        "label": f"{label} depuis {'' if complete else 'au moins '}{span}",
        "steps": steps[-4:],
        "readings": len(streak),
    }

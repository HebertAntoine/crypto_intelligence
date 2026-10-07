"""One recorded snapshot per macro cycle, and what changed between two of them.

The point of recording is to be able to say « il y a 3 h, la Fed était NEUTRAL,
elle est maintenant NEGATIVE » and to say it truthfully. That is only possible
if the earlier reading was written down when it was current, with the factors
that explained it. Nothing here re-derives a past state from today's data: it
would answer what we would say now, not what we said then.

A snapshot is never rewritten. A cycle that runs twice inside the same
three-hour bucket refreshes that bucket's row, which is what makes the
scheduler safe to restart; two different cycles are two different rows.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from ..logging_setup import get_logger
from .snapshots import CADENCES, load_snapshots, save_snapshot

log = get_logger("history.macro_cycles")

KIND = "macro_cycle"

#: Three hours, the cycle the mission sets. Registered so `bucket_for` groups
#: a restart inside the same cycle instead of writing a second row.
CADENCES.setdefault(KIND, 180)


def record_cycle(radar: dict[str, Any], when: datetime | None = None) -> bool:
    """Write the cycle as it was read. Returns True when a new row was created."""

    when = when or datetime.now(UTC)
    payload = {
        "as_of": radar.get("as_of"),
        "summary": radar.get("summary", ""),
        "top": [d.get("key") for d in radar.get("top") or []],
        # Only what is needed to compare two cycles and to replay the page:
        # the whole reading would store the same long sentences every 3 h.
        "drivers": [
            {
                "key": d.get("key"),
                "name": d.get("name"),
                "emoji": d.get("emoji"),
                "direction": d.get("direction"),
                "attention": d.get("attention"),
                "importance": d.get("importance"),
                "state": d.get("state"),
                "available": d.get("available", True),
            }
            for d in radar.get("drivers") or []
        ],
    }
    created = save_snapshot(KIND, None, payload, when=when)
    log.info("macro_cycle_recorded", created=created, top=payload["top"])
    return created


def previous_cycle(now: datetime | None = None, *, within: timedelta | None = None,
                   ) -> dict[str, Any] | None:
    """The most recent recorded cycle strictly before the current bucket.

    `within` bounds how far back a comparison is allowed to reach: after a long
    pause, « il y a 3 h » would be false, so no comparison is offered at all.
    """

    now = now or datetime.now(UTC)
    within = within or timedelta(hours=9)
    rows = load_snapshots(KIND, since=now - within, limit=10)
    for row in rows:
        captured = row.get("captured_at")
        if captured is None:
            continue
        if (now - captured) >= timedelta(minutes=CADENCES[KIND] // 2):
            return row.get("payload") or None
    return None


def cycle_history(now: datetime | None = None, *, hours: int = 24) -> list[dict[str, Any]]:
    """The recorded cycles of the last `hours`, oldest first, for the timeline."""

    now = now or datetime.now(UTC)
    rows = load_snapshots(KIND, since=now - timedelta(hours=hours), limit=40)
    out: list[dict[str, Any]] = []
    for row in reversed(rows):
        payload = row.get("payload") or {}
        drivers = payload.get("drivers") or []
        out.append({
            "at": (row.get("captured_at").isoformat()
                   if row.get("captured_at") else payload.get("as_of")),
            "summary": payload.get("summary", ""),
            "top": payload.get("top") or [],
            # The factors that explained that state, kept with it.
            "directions": {d.get("key"): d.get("direction") for d in drivers},
        })
    return out

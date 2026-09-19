"""Replay the six-family decision through history, point-in-time.

The engine is run exactly as it runs live - same view, same families, same
gates - at each past date, seeing only what had been published by then. Each
decision is then compared with what the price did next.

What this measures, per horizon:

* how often the engine says BUY, WAIT, SELL, INSUFFICIENT_DATA;
* the forward return after each call, its hit rate and false-positive rate,
  against the unconditional baseline over the same dates;
* the worst adverse move inside the horizon after a call (drawdown);
* how often the call changes (stability);
* whether higher confidence goes with better hit rates (calibration).

It is not an optimiser. The weights and thresholds are not tuned to this
output: tuning them to maximise past returns is precisely the overfitting this
report exists to detect.

Two deliberate exclusions, stated in the report:

* the no-measurable-edge veto is left out - it is itself a historical test, and
  with it every call is WAIT, which would measure nothing;
* scheduled events use the stored official calendars (FOMC, ECB, BoJ, BEA...):
  their dates are published months ahead, so knowing them in the past is not
  look-ahead.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import pandas as pd

from ..core.enums import Asset, Timeframe
from ..engines.decision_families import build_families
from ..engines.decision_gates import ExternalChecks, FinalAction, decide
from ..engines.pit_view import DataCache, PointInTimeView
from ..future_events.models import DecisionHorizon

HORIZON_SPAN = {
    DecisionHorizon.H24: timedelta(days=1),
    DecisionHorizon.D7: timedelta(days=7),
    DecisionHorizon.D30: timedelta(days=30),
}


@dataclass(slots=True)
class Call:
    at: datetime
    action: str
    score: float | None
    confidence: int
    blocking_gate: str | None
    forward_return: float | None
    adverse_move: float | None


@dataclass(slots=True)
class HorizonReport:
    horizon: str
    calls: list[Call] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for call in self.calls:
            counts[call.action] = counts.get(call.action, 0) + 1
        scored = [c for c in self.calls if c.forward_return is not None]
        baseline = _stats([c.forward_return for c in scored], direction=1)

        def by_action(action: str, direction: int) -> dict[str, Any]:
            chosen = [c for c in scored if c.action == action]
            stats = _stats([c.forward_return for c in chosen], direction=direction)
            adverse = [c.adverse_move for c in chosen if c.adverse_move is not None]
            stats["mean_adverse_move_pct"] = _round(sum(adverse) / len(adverse)) if adverse else None
            stats["worst_adverse_move_pct"] = _round(min(adverse)) if adverse else None
            return stats

        changes = sum(
            1 for a, b in zip(self.calls, self.calls[1:], strict=False) if a.action != b.action
        )
        blocking: dict[str, int] = {}
        for call in self.calls:
            if call.blocking_gate:
                blocking[call.blocking_gate] = blocking.get(call.blocking_gate, 0) + 1

        # Calibration: does a more confident reading point the right way more
        # often? Uses the sign of every scored reading, whatever the action.
        buckets = [(0, 50), (50, 60), (60, 70), (70, 80), (80, 101)]
        calibration = []
        for low, high in buckets:
            chosen = [
                c for c in scored
                if c.score is not None and abs(c.score) >= 5 and low <= c.confidence < high
            ]
            if not chosen:
                continue
            hits = sum(
                1 for c in chosen if (c.forward_return or 0) * (1 if (c.score or 0) > 0 else -1) > 0
            )
            calibration.append({
                "confidence": f"{low}-{min(high, 100)}",
                "readings": len(chosen),
                "direction_hit_rate": _round(hits / len(chosen) * 100),
            })

        return {
            "horizon": self.horizon,
            "evaluations": len(self.calls),
            "counts": counts,
            "baseline_all_dates": baseline,
            "buy": by_action("BUY", 1),
            "sell": by_action("SELL", -1),
            "wait_forward_return": _stats(
                [c.forward_return for c in scored if c.action == "WAIT"], direction=1
            ),
            "decision_changes": changes,
            "change_rate_pct": _round(changes / max(1, len(self.calls) - 1) * 100),
            "blocking_gates": blocking,
            "confidence_calibration": calibration,
        }


def _round(value: float | None, digits: int = 2) -> float | None:
    return None if value is None or math.isnan(value) else round(value, digits)


def _stats(returns: list[float | None], *, direction: int) -> dict[str, Any]:
    values = [r for r in returns if r is not None]
    if not values:
        return {"n": 0}
    values_sorted = sorted(values)
    hits = sum(1 for r in values if r * direction > 0)
    return {
        "n": len(values),
        "mean_return_pct": _round(sum(values) / len(values)),
        "median_return_pct": _round(values_sorted[len(values) // 2]),
        "hit_rate_pct": _round(hits / len(values) * 100),
        "false_positive_rate_pct": _round((len(values) - hits) / len(values) * 100),
    }


def _forward(
    candles: pd.DataFrame, at: datetime, span: timedelta, direction: int
) -> tuple[float | None, float | None]:
    """Return over ``span`` from the last close known at ``at``, and the worst
    move against ``direction`` inside the span."""

    if candles.empty:
        return None, None
    index = candles.index
    stamp = pd.Timestamp(at)
    if index.tz is None:
        stamp = stamp.tz_localize(None)
    past = candles[index <= stamp - pd.Timedelta(hours=1)]
    future = candles[(index > stamp - pd.Timedelta(hours=1)) & (index <= stamp + pd.Timedelta(span))]
    if past.empty or future.empty or future.index[-1] < stamp + pd.Timedelta(span) - pd.Timedelta(hours=2):
        return None, None
    entry = float(past["close"].iloc[-1])
    exit_ = float(future["close"].iloc[-1])
    ret = (exit_ / entry - 1) * 100
    if direction >= 0:
        adverse = (float(future["low"].min()) / entry - 1) * 100
    else:
        adverse = -(float(future["high"].max()) / entry - 1) * 100
    return ret, adverse


def _event_checks(events: list[Any], asset: Asset, horizon: DecisionHorizon, at: datetime) -> ExternalChecks:
    """The same graded event gate the live decision uses."""

    from ..engines.decision_gates import event_candidates

    return ExternalChecks(event_candidates=event_candidates(events, asset, horizon, at))


def run(
    asset: Asset,
    start: datetime,
    end: datetime,
    *,
    step: timedelta = timedelta(days=1),
    horizons: tuple[DecisionHorizon, ...] = tuple(DecisionHorizon),
    cache: DataCache | None = None,
    events: list[Any] | None = None,
) -> dict[str, HorizonReport]:
    cache = cache or DataCache()
    reports = {h.value: HorizonReport(h.value) for h in horizons}
    hourly = cache.candles(asset.value, Timeframe.H1)
    if events is None:
        events = _load_events()
    moment = start
    while moment <= end:
        view = PointInTimeView(cache, moment)
        for horizon in horizons:
            families = build_families(view, asset, horizon)
            decision = decide(families, horizon, _event_checks(events, asset, horizon, moment))
            direction = -1 if decision.action is FinalAction.SELL else 1
            ret, adverse = _forward(hourly, moment, HORIZON_SPAN[horizon], direction)
            reports[horizon.value].calls.append(Call(
                at=moment,
                action=decision.action.value,
                score=decision.score,
                confidence=decision.confidence,
                blocking_gate=decision.blocking_gate,
                forward_return=ret,
                adverse_move=adverse if decision.action in {FinalAction.BUY, FinalAction.SELL} else None,
            ))
        moment += step
    return reports


def report(
    assets: tuple[Asset, ...] = (Asset.BTC, Asset.ETH, Asset.SOL),
    start: datetime | None = None,
    end: datetime | None = None,
    step: timedelta = timedelta(days=1),
) -> dict[str, Any]:
    end = end or datetime.now(UTC) - timedelta(days=31)
    start = start or datetime(2024, 3, 1, tzinfo=UTC)
    events = _load_events()
    out: dict[str, Any] = {
        "period": {"start": start.isoformat(), "end": end.isoformat(), "step_days": step.days},
        "method": {
            "point_in_time": "Chaque date ne voit que les données publiées avant elle (available_at).",
            "excluded": "Veto « aucun avantage mesurable » exclu : il fait l'objet du test.",
            "entry": "Dernière clôture horaire connue à la date de décision.",
        },
        "assets": {},
    }
    for asset in assets:
        cache = DataCache()
        reports = run(asset, start, end, step=step, cache=cache, events=events)
        out["assets"][asset.value] = {h: r.summary() for h, r in reports.items()}
    return out


def _load_events() -> list[Any]:
    """Stored scheduled events (official calendars), as FutureEvent objects.

    Only scheduled releases are kept: their dates are published well in advance,
    so a past date could legitimately know them. Unscheduled news is dropped -
    its detection time is when this system saw it, not when it became public.
    """

    from ..db import repo

    events = repo.list_future_events(
        start=datetime(2019, 1, 1, tzinfo=UTC), include_expired=True, limit=20000
    )
    return [e for e in events if e.scheduled_at is not None]

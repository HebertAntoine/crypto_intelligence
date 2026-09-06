"""Shadow model, expected-versus-live comparison, and drift detection.

A backtest tells you what today's logic would have done on old data. A track
record tells you what the system actually said before the outcome existed.
They are not the same thing and the gap between them is the most informative
number the system can produce about itself, so this module keeps them apart
and compares them explicitly.

The shadow model runs the current logic on every new bar and records its call
WITHOUT acting on it. Once enough horizons elapse, its live hit rate can be
set against the hit rate the backtest predicted. A large, sustained gap means
the backtest was optimistic - overfitting, leakage, or a regime the model has
not seen.

Nothing here promotes anything. Drift is reported, never acted upon.
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

import numpy as np
from scipy.stats import binomtest

from ..core.enums import Asset
from ..logging_setup import get_logger

log = get_logger("research.drift")

SHADOW_DIR = pathlib.Path("data/shadow")

# Below this many resolved predictions, a live hit rate is noise. Chosen so a
# binomial test can distinguish 50% from 70% at all.
MIN_LIVE_OBSERVATIONS = 30


class DriftState(StrEnum):
    NO_DRIFT = "NO_DRIFT"
    MILD_DRIFT = "MILD_DRIFT"
    SIGNIFICANT_DRIFT = "SIGNIFICANT_DRIFT"
    INSUFFICIENT_LIVE_DATA = "INSUFFICIENT_LIVE_DATA"
    NO_EXPECTATION = "NO_EXPECTATION"


@dataclass(slots=True)
class ShadowPrediction:
    """One recorded call, made before the outcome was knowable."""

    asset: str
    made_at: datetime
    horizon_days: int
    direction: str                 # UP / DOWN / NEUTRAL
    regime: str
    edge_state: str
    price_at_prediction: float
    expected_hit_rate: float | None = None
    resolved: bool = False
    realised_return_pct: float | None = None
    correct: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset": self.asset, "made_at": self.made_at.isoformat(),
            "horizon_days": self.horizon_days, "direction": self.direction,
            "regime": self.regime, "edge_state": self.edge_state,
            "price_at_prediction": self.price_at_prediction,
            "expected_hit_rate": self.expected_hit_rate, "resolved": self.resolved,
            "realised_return_pct": self.realised_return_pct, "correct": self.correct,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ShadowPrediction:
        return cls(
            asset=payload["asset"],
            made_at=datetime.fromisoformat(payload["made_at"]),
            horizon_days=payload["horizon_days"], direction=payload["direction"],
            regime=payload.get("regime", "UNKNOWN"),
            edge_state=payload.get("edge_state", "UNKNOWN"),
            price_at_prediction=payload["price_at_prediction"],
            expected_hit_rate=payload.get("expected_hit_rate"),
            resolved=payload.get("resolved", False),
            realised_return_pct=payload.get("realised_return_pct"),
            correct=payload.get("correct"),
        )


class ShadowModel:
    """Record predictions without acting on them, then resolve them honestly."""

    def __init__(self, directory: pathlib.Path | None = None) -> None:
        self.directory = directory or SHADOW_DIR
        self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, asset: Asset) -> pathlib.Path:
        return self.directory / f"{asset.value}_shadow.json"

    def load(self, asset: Asset) -> list[ShadowPrediction]:
        path = self._path(asset)
        if not path.exists():
            return []
        try:
            return [ShadowPrediction.from_dict(p) for p in json.loads(path.read_text())]
        except (json.JSONDecodeError, OSError, KeyError) as exc:
            log.warning("shadow_unreadable", asset=asset.value, error=str(exc))
            return []

    def save(self, asset: Asset, predictions: list[ShadowPrediction]) -> None:
        self._path(asset).write_text(
            json.dumps([p.to_dict() for p in predictions], indent=2)
        )

    def record(
        self, asset: Asset, direction: str, price: float, regime: str,
        edge_state: str, horizons: list[int] | None = None,
        expected_hit_rate: float | None = None, made_at: datetime | None = None,
    ) -> int:
        """Log a call for each horizon. Duplicates on the same day are ignored."""
        horizons = horizons or [1, 7, 30]
        made_at = made_at or datetime.now(UTC)
        existing = self.load(asset)
        already = {
            (p.made_at.date(), p.horizon_days) for p in existing
        }

        added = 0
        for horizon in horizons:
            if (made_at.date(), horizon) in already:
                continue
            existing.append(ShadowPrediction(
                asset=asset.value, made_at=made_at, horizon_days=horizon,
                direction=direction, regime=regime, edge_state=edge_state,
                price_at_prediction=price, expected_hit_rate=expected_hit_rate,
            ))
            added += 1

        if added:
            self.save(asset, existing)
            log.info("shadow_recorded", asset=asset.value, added=added, direction=direction)
        return added

    def resolve(self, asset: Asset, now: datetime | None = None) -> dict[str, Any]:
        """Score predictions whose horizon has elapsed, using stored prices."""
        from ..core.enums import Timeframe
        from ..history import store

        now = now or datetime.now(UTC)
        predictions = self.load(asset)
        if not predictions:
            return {"asset": asset.value, "resolved": 0, "pending": 0}

        closes = store.load_candles(asset, Timeframe.D1)
        if closes.empty:
            return {"asset": asset.value, "resolved": 0, "error": "no price history"}
        prices = closes["close"]

        resolved = 0
        for prediction in predictions:
            if prediction.resolved:
                continue
            target_time = prediction.made_at + timedelta(days=prediction.horizon_days)
            if target_time > now:
                continue
            available = prices[prices.index <= target_time]
            if available.empty:
                continue
            realised = float(
                (available.iloc[-1] - prediction.price_at_prediction)
                / prediction.price_at_prediction * 100
            )
            prediction.realised_return_pct = round(realised, 3)
            prediction.resolved = True
            # NEUTRAL calls are recorded but never scored as right or wrong -
            # counting them would inflate the hit rate with non-predictions.
            if prediction.direction == "UP":
                prediction.correct = realised > 0
            elif prediction.direction == "DOWN":
                prediction.correct = realised < 0
            else:
                prediction.correct = None
            resolved += 1

        if resolved:
            self.save(asset, predictions)
        pending = sum(1 for p in predictions if not p.resolved)
        return {
            "asset": asset.value, "resolved": resolved, "pending": pending,
            "total": len(predictions),
        }


class SignalDriftEngine:
    """Compare what the backtest expected against what actually happened."""

    def __init__(self, shadow: ShadowModel | None = None) -> None:
        self.shadow = shadow or ShadowModel()

    def assess(self, asset: Asset) -> dict[str, Any]:
        predictions = self.shadow.load(asset)
        scored = [p for p in predictions if p.resolved and p.correct is not None]

        out: dict[str, Any] = {
            "asset": asset.value,
            "predictions_total": len(predictions),
            "predictions_resolved": sum(1 for p in predictions if p.resolved),
            "predictions_scored": len(scored),
            "state": DriftState.INSUFFICIENT_LIVE_DATA.value,
        }

        if len(scored) < MIN_LIVE_OBSERVATIONS:
            out["note"] = (
                f"{len(scored)} scored live predictions, below the "
                f"{MIN_LIVE_OBSERVATIONS} needed to distinguish a real gap from noise. "
                "No drift claim is possible yet - this is not evidence the model is fine."
            )
            return out

        by_horizon: dict[str, Any] = {}
        drift_flags: list[str] = []

        for horizon in sorted({p.horizon_days for p in scored}):
            rows = [p for p in scored if p.horizon_days == horizon]
            if len(rows) < MIN_LIVE_OBSERVATIONS:
                by_horizon[f"{horizon}d"] = {
                    "state": DriftState.INSUFFICIENT_LIVE_DATA.value, "n": len(rows),
                }
                continue

            hits = sum(1 for p in rows if p.correct)
            live_rate = hits / len(rows)
            expectations = [
                p.expected_hit_rate for p in rows if p.expected_hit_rate is not None
            ]
            expected = float(np.mean(expectations)) if expectations else None

            entry: dict[str, Any] = {
                "n": len(rows),
                "live_hit_rate": round(live_rate * 100, 1),
                "expected_hit_rate": round(expected * 100, 1) if expected else None,
                "mean_return_pct": round(
                    float(np.mean([p.realised_return_pct for p in rows])), 3
                ),
            }

            if expected is None:
                entry["state"] = DriftState.NO_EXPECTATION.value
                entry["note"] = (
                    "no backtest expectation was recorded with these predictions, so "
                    "live performance cannot be compared to anything"
                )
            else:
                # Binomial test: is the live hit rate consistent with what the
                # backtest promised, or has the model degraded?
                test = binomtest(hits, len(rows), expected, alternative="two-sided")
                entry["p_value"] = float(test.pvalue)
                gap = live_rate - expected
                entry["gap_pp"] = round(gap * 100, 1)
                if test.pvalue < 0.05 and gap < 0:
                    entry["state"] = DriftState.SIGNIFICANT_DRIFT.value
                    drift_flags.append(f"{horizon}d")
                elif abs(gap) > 0.10:
                    entry["state"] = DriftState.MILD_DRIFT.value
                else:
                    entry["state"] = DriftState.NO_DRIFT.value
            by_horizon[f"{horizon}d"] = entry

        out["by_horizon"] = by_horizon
        out["state"] = (
            DriftState.SIGNIFICANT_DRIFT.value if drift_flags
            else DriftState.NO_DRIFT.value
        )
        out["note"] = (
            f"Live performance is significantly below backtest expectation at "
            f"{', '.join(drift_flags)}. The backtest was optimistic; treat its figures "
            "as an upper bound."
            if drift_flags else
            "Live performance is consistent with backtest expectation at every horizon "
            "with enough data."
        )
        return out


def run_all(assets: list[Asset] | None = None) -> dict[str, Any]:
    assets = assets or Asset.tradables()
    shadow = ShadowModel()
    engine = SignalDriftEngine(shadow)
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "assets": {
            a.value: {
                "resolution": shadow.resolve(a),
                "drift": engine.assess(a),
            }
            for a in assets
        },
        "note": (
            "Shadow predictions are recorded and scored but never acted upon. They "
            "exist to measure the gap between backtest and reality."
        ),
    }

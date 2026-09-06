"""Live shadow record for structural detections.

The LOT 4 shadow model records a directional call. This records the STRUCTURE
the system saw at a point in time - the range, the location, the pattern, the
recognition confidence, the entry opportunity - and resolves what followed.

Its purpose is the comparison the backtest cannot make. A backtest replays
today's detector over old bars; a live record captures what the detector
actually emitted before the outcome existed. When the two disagree, the
backtest is the one to distrust.

Nothing is ever reconstructed. A detection missing from the live record stays
missing; back-filling it from history would turn a track record into another
backtest wearing its name.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import numpy as np

from ..core.enums import Asset, Timeframe
from ..logging_setup import get_logger

log = get_logger("research.structural_shadow")

SHADOW_DIR = pathlib.Path("data/shadow/structural")
MIN_MATURED_FOR_VERDICT = 20


class LiveVerdict(StrEnum):
    TOO_EARLY = "TOO_EARLY"
    LIVE_CONFIRMS = "LIVE_CONFIRMS"
    LIVE_WEAKER = "LIVE_WEAKER"
    LIVE_CONTRADICTS = "LIVE_CONTRADICTS"
    NO_BACKTEST_EXPECTATION = "NO_BACKTEST_EXPECTATION"


@dataclass(slots=True)
class StructuralSnapshot:
    """One immutable record of what the system saw, before the outcome."""

    id: str
    recorded_at: datetime
    asset: str
    timeframe: str
    price: float
    location_state: str
    range_type: str | None = None
    range_top: float | None = None
    range_bottom: float | None = None
    range_confidence: float | None = None
    market_structure: str | None = None
    pattern_name: str | None = None
    pattern_state: str | None = None
    recognition_confidence: float | None = None
    pattern_edge_state: str | None = None
    entry_opportunity: str | None = None
    edge_state: str | None = None
    regime: str | None = None
    funding_percentile: float | None = None
    crowding_level: str | None = None
    volatility_regime: str | None = None
    uncertainty: float | None = None
    detector_version: str = ""
    # Outcome fields, filled only once the horizon has elapsed.
    resolved: bool = False
    returns: dict[str, float] = field(default_factory=dict)
    mfe_pct: float | None = None
    mae_pct: float | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {
            k: getattr(self, k) for k in self.__slots__ if k != "recorded_at"
        }
        payload["recorded_at"] = self.recorded_at.isoformat()
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> StructuralSnapshot:
        data = dict(payload)
        data["recorded_at"] = datetime.fromisoformat(data["recorded_at"])
        known = set(cls.__slots__)
        return cls(**{k: v for k, v in data.items() if k in known})


class StructuralShadowRecorder:
    """Append-only record of live structural detections."""

    def __init__(self, directory: pathlib.Path | None = None) -> None:
        self.directory = directory or SHADOW_DIR
        self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, asset: Asset) -> pathlib.Path:
        return self.directory / f"{asset.value}_structural_shadow.json"

    def load(self, asset: Asset) -> list[StructuralSnapshot]:
        path = self._path(asset)
        if not path.exists():
            return []
        try:
            return [StructuralSnapshot.from_dict(r) for r in json.loads(path.read_text())]
        except (json.JSONDecodeError, OSError, TypeError, KeyError) as exc:
            log.warning("structural_shadow_unreadable", error=str(exc))
            return []

    def save(self, asset: Asset, snapshots: list[StructuralSnapshot]) -> None:
        self._path(asset).write_text(
            json.dumps([s.to_dict() for s in snapshots], indent=2, default=str)
        )

    def record(
        self, asset: Asset, timeframe: Timeframe = Timeframe.H4,
        as_of: datetime | None = None,
    ) -> dict[str, Any]:
        """Capture the current structural reading. One record per bar."""
        from ..engines.edge import EdgeEngine
        from ..engines.entry_opportunity import EntryOpportunityEngine
        from ..engines.leverage import LeverageCrowdingEngine
        from ..engines.volatility import VolatilityRegimeEngine
        from ..history import store
        from ..structure.cache import DETECTOR_VERSION
        from ..structure.location import StructuralLocationEngine
        from ..structure.market_structure import MarketStructureEngine
        from ..structure.patterns import build_context, detect_all

        df = store.load_candles(asset, timeframe)
        if as_of is not None and not df.empty:
            df = df[df.index <= as_of]
        if df.empty:
            return {"status": "NO_DATA"}

        timestamp = df.index[-1]
        existing = self.load(asset)
        if any(
            s.recorded_at == timestamp.to_pydatetime() and s.timeframe == timeframe.value
            for s in existing
        ):
            return {"status": "ALREADY_RECORDED", "timestamp": str(timestamp)}

        location = StructuralLocationEngine().assess(asset, timeframe, as_of)
        structure = MarketStructureEngine().assess(asset, timeframe, as_of)
        opportunity = EntryOpportunityEngine().assess(asset, timeframe, as_of)
        leverage = LeverageCrowdingEngine()
        funding = leverage.funding_context(asset, as_of)
        crowding = leverage.crowding(asset, as_of)
        volatility = VolatilityRegimeEngine().assess(asset, as_of)
        edge = EdgeEngine().assess(asset)

        ctx = build_context(df, timeframe)
        patterns = detect_all(ctx) if ctx is not None else []
        best = patterns[0] if patterns else None
        detected = location.detected_range

        snapshot = StructuralSnapshot(
            id="ss_" + hashlib.sha1(
                f"{asset.value}|{timeframe.value}|{timestamp}".encode()
            ).hexdigest()[:14],
            recorded_at=timestamp.to_pydatetime(),
            asset=asset.value, timeframe=timeframe.value,
            price=float(df["close"].iloc[-1]),
            location_state=location.state.value,
            range_type=detected.range_type.value if detected else None,
            range_top=detected.top_zone.midpoint if detected and detected.top_zone else None,
            range_bottom=(
                detected.bottom_zone.midpoint if detected and detected.bottom_zone else None
            ),
            range_confidence=detected.confidence if detected else None,
            market_structure=structure.state.value,
            pattern_name=best.name if best else None,
            pattern_state=best.state.value if best else None,
            recognition_confidence=best.recognition_confidence if best else None,
            pattern_edge_state=best.edge_state.value if best else None,
            entry_opportunity=opportunity.state.value,
            edge_state=edge.state.value,
            funding_percentile=funding.percentile,
            crowding_level=crowding.level.value,
            volatility_regime=volatility.regime,
            detector_version=DETECTOR_VERSION,
        )
        existing.append(snapshot)
        self.save(asset, existing)
        log.info(
            "structural_snapshot_recorded", asset=asset.value,
            location=snapshot.location_state, pattern=snapshot.pattern_name,
        )
        return {"status": "RECORDED", "id": snapshot.id, "total": len(existing)}

    def resolve(self, asset: Asset, now: datetime | None = None) -> dict[str, Any]:
        """Fill in outcomes for snapshots whose horizons have elapsed."""
        from ..history import store

        now = now or datetime.now(UTC)
        snapshots = self.load(asset)
        if not snapshots:
            return {"asset": asset.value, "resolved": 0, "total": 0}

        resolved = 0
        for snapshot in snapshots:
            if snapshot.resolved:
                continue
            timeframe = Timeframe(snapshot.timeframe)
            df = store.load_candles(asset, timeframe)
            after = df[df.index > snapshot.recorded_at]
            if after.empty:
                continue

            minutes = timeframe.minutes
            horizons = {"1d": 1440, "3d": 4320, "7d": 10080, "14d": 20160, "30d": 43200}
            matured = False
            for label, horizon_minutes in horizons.items():
                bars = int(horizon_minutes / minutes)
                if bars < 1 or bars > len(after):
                    continue
                target = float(after["close"].iloc[bars - 1])
                snapshot.returns[label] = round(
                    (target - snapshot.price) / snapshot.price * 100, 3
                )
                matured = True

            if matured:
                window = after.iloc[: int(43200 / minutes)]
                if len(window):
                    snapshot.mfe_pct = round(
                        float((window["high"].max() - snapshot.price) / snapshot.price * 100), 3
                    )
                    snapshot.mae_pct = round(
                        float((window["low"].min() - snapshot.price) / snapshot.price * 100), 3
                    )
                # Only mark resolved once the longest horizon has elapsed, so a
                # partially matured record cannot be counted as complete.
                longest_bars = int(43200 / minutes)
                snapshot.resolved = len(after) >= longest_bars
                resolved += 1

        self.save(asset, snapshots)
        return {
            "asset": asset.value, "resolved": resolved,
            "total": len(snapshots),
            "fully_resolved": sum(1 for s in snapshots if s.resolved),
        }


def live_track_record(asset: Asset | None = None) -> dict[str, Any]:
    """Live outcomes per pattern and location, against backtest expectation."""
    recorder = StructuralShadowRecorder()
    assets = [asset] if asset else Asset.tradables()

    by_key: dict[str, list[StructuralSnapshot]] = {}
    total = 0
    for target in assets:
        for snapshot in recorder.load(target):
            total += 1
            if not snapshot.returns:
                continue
            for key in (
                f"location:{snapshot.location_state}",
                f"pattern:{snapshot.pattern_name}" if snapshot.pattern_name else None,
                f"opportunity:{snapshot.entry_opportunity}",
            ):
                if key:
                    by_key.setdefault(f"{snapshot.asset}|{key}", []).append(snapshot)

    if total == 0:
        return {
            "status": "NO_RECORDS",
            "note": (
                "No live structural snapshots yet. The recorder runs on each pipeline "
                "pass; a usable track record needs weeks of scheduler uptime. Backtest "
                "figures are NOT shown here in their place."
            ),
        }

    rows: list[dict[str, Any]] = []
    for key, snapshots in sorted(by_key.items()):
        matured = [s for s in snapshots if s.returns.get("7d") is not None]
        if not matured:
            continue
        returns = [s.returns["7d"] for s in matured]
        rows.append({
            "key": key,
            "matured_predictions": len(matured),
            "median_return_7d_pct": round(float(np.median(returns)), 3),
            "mean_return_7d_pct": round(float(np.mean(returns)), 3),
            "mfe_median_pct": round(
                float(np.median([s.mfe_pct for s in matured if s.mfe_pct is not None])), 3
            ) if any(s.mfe_pct is not None for s in matured) else None,
            "mae_median_pct": round(
                float(np.median([s.mae_pct for s in matured if s.mae_pct is not None])), 3
            ) if any(s.mae_pct is not None for s in matured) else None,
            "verdict": (
                LiveVerdict.TOO_EARLY.value if len(matured) < MIN_MATURED_FOR_VERDICT
                else LiveVerdict.NO_BACKTEST_EXPECTATION.value
            ),
            "note": (
                f"{len(matured)} matured records, below the {MIN_MATURED_FOR_VERDICT} "
                "needed for any verdict"
                if len(matured) < MIN_MATURED_FOR_VERDICT else
                "matured enough to compare, but no stored backtest expectation exists "
                "for this key yet"
            ),
        })

    return {
        "status": "OK",
        "total_snapshots": total,
        "keys_with_outcomes": len(rows),
        "rows": rows,
        "note": (
            "These are LIVE outcomes from detections recorded before the outcome "
            "existed. They are never mixed with backtest figures, and no snapshot is "
            "ever reconstructed from history."
        ),
    }


def record_all(timeframe: Timeframe = Timeframe.H4) -> dict[str, Any]:
    recorder = StructuralShadowRecorder()
    return {
        asset.value: {
            "record": recorder.record(asset, timeframe),
            "resolve": recorder.resolve(asset),
        }
        for asset in Asset.tradables()
    }

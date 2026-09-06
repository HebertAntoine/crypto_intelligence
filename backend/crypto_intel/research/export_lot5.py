"""Export research artefacts with the provenance needed to trust them.

Every exported row carries the version information that determines what it
means: the detector version, the feature version, the code revision and
whether the row is point-in-time safe. A CSV of pattern detections without
those fields is unusable six months later, because nobody can tell which
definition produced it.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
from datetime import UTC, datetime
from typing import Any

import pandas as pd

from ..core.enums import Asset, Timeframe
from ..history import store
from ..logging_setup import get_logger
from ..structure.cache import DETECTOR_VERSION
from ..structure.patterns import build_context, detect_all

log = get_logger("research.export_lot5")


def _code_version() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL, timeout=5,
        ).decode().strip()
    except Exception:
        return "unknown"


def _provenance() -> dict[str, Any]:
    from ..research.registry import FEATURE_VERSION

    return {
        "exported_at": datetime.now(UTC).isoformat(),
        "detector_version": DETECTOR_VERSION,
        "feature_version": FEATURE_VERSION,
        "code_version": _code_version(),
        "point_in_time_safe": True,
    }


def export_patterns(
    out_dir: pathlib.Path, fmt: str = "json",
    assets: list[Asset] | None = None, timeframe: Timeframe = Timeframe.D1,
) -> dict[str, Any]:
    """Every pattern detection across history, with its context."""
    assets = assets or Asset.tradables()
    rows: list[dict[str, Any]] = []

    for asset in assets:
        df = store.load_candles(asset, timeframe)
        if df.empty or len(df) < 200:
            continue
        # Sample rather than every bar: a full replay belongs in the research
        # command, and an export is meant to be readable.
        for i in range(150, len(df), 5):
            window = df.iloc[:i + 1]
            ctx = build_context(window, timeframe)
            if ctx is None:
                continue
            for pattern in detect_all(ctx):
                rows.append({
                    "timestamp": df.index[i].isoformat(),
                    "asset": asset.value, "timeframe": timeframe.value,
                    "pattern": pattern.name,
                    "pattern_class": pattern.pattern_class.value,
                    "state": pattern.state.value,
                    "recognition_confidence": pattern.recognition_confidence,
                    "direction_if_textbook": pattern.direction_if_textbook,
                    "edge_state": pattern.edge_state.value,
                    "invalidation_level": pattern.invalidation_level,
                    **_provenance(),
                })

    return _write(out_dir, "patterns", rows, fmt)


def export_ranges(
    out_dir: pathlib.Path, fmt: str = "json",
    assets: list[Asset] | None = None, timeframe: Timeframe = Timeframe.D1,
) -> dict[str, Any]:
    from ..structure.ranges import RangeIntelligenceEngine

    assets = assets or Asset.tradables()
    engine = RangeIntelligenceEngine()
    rows: list[dict[str, Any]] = []

    for asset in assets:
        df = store.load_candles(asset, timeframe)
        if df.empty or len(df) < 200:
            continue
        for i in range(150, len(df), 5):
            detected = engine.detect_from_frame(df.iloc[:i + 1])
            rows.append({
                "timestamp": df.index[i].isoformat(),
                "asset": asset.value, "timeframe": timeframe.value,
                "range_type": detected.range_type.value,
                "valid": detected.valid,
                "recognition_confidence": detected.confidence,
                "top": detected.top_zone.midpoint if detected.top_zone else None,
                "bottom": detected.bottom_zone.midpoint if detected.bottom_zone else None,
                "width_atr": detected.width_atr,
                "top_touches": detected.top_touches,
                "bottom_touches": detected.bottom_touches,
                "duration_bars": detected.duration_bars,
                **_provenance(),
            })
    return _write(out_dir, "ranges", rows, fmt)


def export_human_examples(out_dir: pathlib.Path, fmt: str = "json") -> dict[str, Any]:
    from ..trader_knowledge.dataset import load_examples

    rows = [
        {**e.model_dump(mode="json"), **_provenance()} for e in load_examples()
    ]
    return _write(out_dir, "human_examples", rows, fmt)


def export_educational_claims(out_dir: pathlib.Path, fmt: str = "json") -> dict[str, Any]:
    from ..trader_knowledge.educational import load_claims

    rows = [{**c, **_provenance()} for c in load_claims()]
    return _write(out_dir, "educational_claims", rows, fmt)


def export_research_results(out_dir: pathlib.Path, fmt: str = "json") -> dict[str, Any]:
    """Copy the stored study outputs with provenance attached."""
    source_dir = pathlib.Path("data/research")
    written: list[str] = []
    out_dir.mkdir(parents=True, exist_ok=True)

    for name in (
        "structural_research.json", "marginal_value.json",
        "replication.json", "claim_validation.json",
        "pattern_validation.json", "baselines.json",
    ):
        path = source_dir / name
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        target = out_dir / name
        target.write_text(
            json.dumps({**payload, "provenance": _provenance()}, indent=2, default=str)
        )
        written.append(str(target))

    return {"files": written, "count": len(written)}


def _write(
    out_dir: pathlib.Path, name: str, rows: list[dict[str, Any]], fmt: str
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    if not rows:
        return {"rows": 0, "note": f"no {name} to export"}

    if fmt == "json":
        path = out_dir / f"{name}.json"
        path.write_text(json.dumps(rows, indent=2, default=str))
        return {"rows": len(rows), "path": str(path)}

    frame = pd.DataFrame(rows)
    if fmt == "parquet":
        path = out_dir / f"{name}.parquet"
        try:
            frame.to_parquet(path)
            return {"rows": len(rows), "path": str(path)}
        except Exception as exc:
            log.info("parquet_unavailable", error=str(exc)[:100])
            fmt = "csv"

    path = out_dir / f"{name}.csv"
    frame.to_csv(path, index=False)
    return {"rows": len(rows), "path": str(path), "format": fmt}


def export_all(out_dir: str = "data/exports", fmt: str = "json") -> dict[str, Any]:
    directory = pathlib.Path(out_dir)
    return {
        "provenance": _provenance(),
        "exports": {
            "patterns": export_patterns(directory, fmt),
            "ranges": export_ranges(directory, fmt),
            "human_examples": export_human_examples(directory, fmt),
            "educational_claims": export_educational_claims(directory, fmt),
            "research_results": export_research_results(directory, fmt),
        },
    }

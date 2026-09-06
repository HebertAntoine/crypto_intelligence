"""Cached structural results with incremental update.

Replaying nine years of bars across five timeframes and every detector takes
minutes, which is fine for a research run and unusable for a dashboard. But
the results are deterministic and causal: the structure at bar i depends only
on bars up to i, so a result computed once is valid forever.

That is what makes caching safe here. Nothing is approximated - a cached row
is exactly what a fresh computation would produce. The cache is invalidated
only when something that changes the ANSWER changes: the detector version, the
feature version, or the configuration.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
from datetime import UTC, datetime
from typing import Any

import pandas as pd

from ..core.enums import Asset, Timeframe
from ..logging_setup import get_logger

log = get_logger("structure.cache")

CACHE_DIR = pathlib.Path("data/cache/structure")

# Bump when a detector's behaviour changes. Cached rows computed under a
# different version are discarded rather than mixed with new ones.
DETECTOR_VERSION = "lot5.1"


def _cache_path(asset: Asset, timeframe: Timeframe, kind: str) -> pathlib.Path:
    return CACHE_DIR / f"{asset.value}_{timeframe.value}_{kind}_{DETECTOR_VERSION}.parquet"


def _meta_path(asset: Asset, timeframe: Timeframe, kind: str) -> pathlib.Path:
    return CACHE_DIR / f"{asset.value}_{timeframe.value}_{kind}_{DETECTOR_VERSION}.meta.json"


def config_fingerprint(config: dict[str, Any] | None = None) -> str:
    payload = json.dumps(config or {}, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


def load_cached(
    asset: Asset, timeframe: Timeframe, kind: str, config: dict[str, Any] | None = None
) -> tuple[pd.DataFrame | None, dict[str, Any]]:
    """Return the cached frame when it is still valid, else None."""
    path = _cache_path(asset, timeframe, kind)
    meta_path = _meta_path(asset, timeframe, kind)
    if not meta_path.exists():
        return None, {"status": "MISS", "reason": "no cache metadata"}

    try:
        meta = json.loads(meta_path.read_text())
    except (json.JSONDecodeError, OSError):
        return None, {"status": "MISS", "reason": "unreadable metadata"}

    if meta.get("detector_version") != DETECTOR_VERSION:
        return None, {
            "status": "STALE", "reason": (
                f"cache built with detector {meta.get('detector_version')}, "
                f"current is {DETECTOR_VERSION}"
            ),
        }
    if meta.get("config_fingerprint") != config_fingerprint(config):
        return None, {"status": "STALE", "reason": "configuration changed"}

    fmt = meta.get("format", "parquet")
    if fmt == "pickle":
        path = path.with_suffix(".pkl")
    if not path.exists():
        return None, {"status": "MISS", "reason": "cache payload missing"}
    try:
        frame = pd.read_pickle(path) if fmt == "pickle" else pd.read_parquet(path)
    except Exception as exc:
        return None, {"status": "MISS", "reason": f"unreadable cache: {exc}"[:120]}

    return frame, {
        "status": "HIT", "rows": len(frame),
        "computed_at": meta.get("computed_at"),
        "last_bar": meta.get("last_bar"),
    }


def save_cache(
    asset: Asset, timeframe: Timeframe, kind: str, frame: pd.DataFrame,
    config: dict[str, Any] | None = None, last_bar: Any = None,
) -> dict[str, Any]:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _cache_path(asset, timeframe, kind)
    fmt = "parquet"
    try:
        frame.to_parquet(path)
    except Exception as exc:
        # Parquet needs pyarrow. Rather than losing the cache entirely when it
        # is missing, fall back to pickle and record which format was used.
        log.info("parquet_unavailable_using_pickle", error=str(exc)[:100])
        path = path.with_suffix(".pkl")
        try:
            frame.to_pickle(path)
            fmt = "pickle"
        except Exception as inner:
            log.warning("cache_write_failed", error=str(inner))
            return {"status": "FAILED", "reason": str(inner)[:120]}

    _meta_path(asset, timeframe, kind).write_text(json.dumps({
        "asset": asset.value, "timeframe": timeframe.value, "kind": kind,
        "detector_version": DETECTOR_VERSION,
        "config_fingerprint": config_fingerprint(config),
        "computed_at": datetime.now(UTC).isoformat(),
        "rows": len(frame),
        "format": fmt,
        "last_bar": str(last_bar) if last_bar is not None else None,
    }, indent=2))
    return {"status": "SAVED", "rows": len(frame), "path": str(path), "format": fmt}


def compute_incremental(
    asset: Asset,
    timeframe: Timeframe,
    kind: str,
    compute_row,
    df: pd.DataFrame,
    config: dict[str, Any] | None = None,
    warmup: int = 150,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Compute only the bars the cache does not already cover.

    `compute_row(window)` receives every bar up to and including the one being
    computed, so incremental results are identical to a full replay - the
    function cannot see anything a full run would not have shown it.
    """
    cached, info = load_cached(asset, timeframe, kind, config)
    rows: list[dict[str, Any]] = []
    start_index = warmup

    if cached is not None and len(cached):
        cached.index = pd.to_datetime(cached.index, utc=True)
        last_cached = cached.index.max()
        newer = df.index[df.index > last_cached]
        if len(newer) == 0:
            return cached, {**info, "computed": 0, "reused": len(cached)}
        start_index = int(df.index.get_indexer([newer[0]])[0])
        log.info(
            "incremental_update", asset=asset.value, tf=timeframe.value,
            cached=len(cached), new_bars=len(newer),
        )

    for i in range(start_index, len(df)):
        window = df.iloc[:i + 1]
        try:
            row = compute_row(window)
        except Exception:
            continue
        if row:
            rows.append({"timestamp": df.index[i], **row})

    fresh = pd.DataFrame(rows)
    if not fresh.empty:
        fresh = fresh.set_index("timestamp")

    if cached is not None and len(cached):
        combined = pd.concat([cached, fresh])
        combined = combined[~combined.index.duplicated(keep="last")].sort_index()
    else:
        combined = fresh

    save_cache(
        asset, timeframe, kind, combined, config,
        last_bar=df.index[-1] if len(df) else None,
    )
    return combined, {
        "status": info.get("status", "MISS"),
        "computed": len(fresh),
        "reused": len(cached) if cached is not None else 0,
        "total": len(combined),
    }


def invalidate(asset: Asset | None = None, timeframe: Timeframe | None = None) -> dict[str, Any]:
    """Delete cached results. Used when a detector definition changes."""
    if not CACHE_DIR.exists():
        return {"removed": 0}
    removed = 0
    for path in CACHE_DIR.iterdir():
        if asset and not path.name.startswith(f"{asset.value}_"):
            continue
        if timeframe and f"_{timeframe.value}_" not in path.name:
            continue
        if path.is_dir():
            continue
        try:
            path.unlink()
            removed += 1
        except OSError:
            continue
    log.info("cache_invalidated", removed=removed)
    return {"removed": removed}


def cache_status() -> dict[str, Any]:
    if not CACHE_DIR.exists():
        return {"entries": 0, "detector_version": DETECTOR_VERSION}
    entries = []
    for meta_file in sorted(CACHE_DIR.glob("*.meta.json")):
        try:
            entries.append(json.loads(meta_file.read_text()))
        except (json.JSONDecodeError, OSError):
            continue
    return {
        "entries": len(entries),
        "detector_version": DETECTOR_VERSION,
        "cached": entries,
        "note": (
            "Cached structural results are exact, not approximations: each row was "
            "computed from bars up to its own timestamp and cannot change."
        ),
    }

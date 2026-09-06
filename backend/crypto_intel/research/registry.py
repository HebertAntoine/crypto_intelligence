"""Feature registry and reproducibility.

Every feature the research layer can compute is declared here with its
point-in-time status, the lag before it is knowable, and the code that builds
it. Two things follow from that.

First, a dataset can be assembled with a guarantee that nothing inside it was
unknowable at its own timestamp - the registry refuses to emit a feature whose
availability says otherwise.

Second, a result can be reproduced. Each dataset carries a hash of the feature
definitions, the code version and the data coverage that produced it, so a
number in a report can be traced back to exactly what generated it.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd

from ..core.enums import Asset, Timeframe
from ..core.pointintime import Availability
from ..engines.technical import indicators as ind
from ..history import store
from ..logging_setup import get_logger

log = get_logger("research.registry")

FEATURE_VERSION = "lot5.1"


@dataclass(slots=True)
class FeatureSpec:
    """One feature, with everything needed to judge and rebuild it."""

    name: str
    description: str
    builder: Callable[[pd.DataFrame, Asset], pd.Series]
    availability: Availability = Availability.POINT_IN_TIME
    lag_bars: int = 0
    category: str = "technical"
    min_history: int = 200
    experimental: bool = False
    formula: str = ""
    source: str = "price"
    detector_version: str | None = None
    assets: tuple[str, ...] = ("BTC", "ETH", "SOL")
    timeframes: tuple[str, ...] = ("1d",)

    @property
    def usable_for_backtest(self) -> bool:
        return self.availability.usable_for_backtest

    def definition_hash(self) -> str:
        """Hash of the actual source of the builder, so edits are detectable."""
        try:
            source = inspect.getsource(self.builder)
        except (OSError, TypeError):
            source = self.name
        payload = f"{self.name}|{self.availability.value}|{self.lag_bars}|{source}"
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "description": self.description,
            "availability": self.availability.value,
            "usable_for_backtest": self.usable_for_backtest,
            "lag_bars": self.lag_bars, "category": self.category,
            "min_history": self.min_history, "experimental": self.experimental,
            "formula": self.formula, "source": self.source,
            "detector_version": self.detector_version,
            "assets": list(self.assets), "timeframes": list(self.timeframes),
            "definition_hash": self.definition_hash(),
        }


def _trailing_rank(series: pd.Series, min_history: int = 200) -> pd.Series:
    values = series.to_numpy(dtype=float)
    ranks = np.full(len(values), np.nan)
    for i in range(min_history, len(values)):
        window = values[:i]
        window = window[~np.isnan(window)]
        if len(window):
            ranks[i] = float((window < values[i]).mean() * 100)
    return pd.Series(ranks, index=series.index)


class FeatureRegistry:
    """The declared set of features, and the datasets built from them."""

    def __init__(self) -> None:
        self._features: dict[str, FeatureSpec] = {}
        self._register_defaults()

    # -- registration ----------------------------------------------------
    def register(self, spec: FeatureSpec) -> None:
        if spec.name in self._features:
            raise ValueError(f"feature '{spec.name}' is already registered")
        self._features[spec.name] = spec

    def get(self, name: str) -> FeatureSpec | None:
        return self._features.get(name)

    def names(self, *, backtest_safe_only: bool = False) -> list[str]:
        return sorted(
            name for name, spec in self._features.items()
            if not backtest_safe_only or spec.usable_for_backtest
        )

    def describe(self) -> list[dict[str, Any]]:
        return [self._features[n].to_dict() for n in sorted(self._features)]

    def _register_defaults(self) -> None:
        """Features built only from price, volume and stored derivatives."""

        def rsi14(df: pd.DataFrame, _: Asset) -> pd.Series:
            return ind.rsi(df["close"], 14)

        def atr_pct(df: pd.DataFrame, _: Asset) -> pd.Series:
            return ind.atr_percent(df["high"], df["low"], df["close"], 14)

        def adx14(df: pd.DataFrame, _: Asset) -> pd.Series:
            return ind.adx(df["high"], df["low"], df["close"], 14)

        def dist_ema200(df: pd.DataFrame, _: Asset) -> pd.Series:
            ema = df["close"].ewm(span=200, adjust=False).mean()
            return (df["close"] - ema) / df["close"] * 100

        def dist_ema50(df: pd.DataFrame, _: Asset) -> pd.Series:
            ema = df["close"].ewm(span=50, adjust=False).mean()
            return (df["close"] - ema) / df["close"] * 100

        def return_7d(df: pd.DataFrame, _: Asset) -> pd.Series:
            return df["close"].pct_change(7) * 100

        def return_30d(df: pd.DataFrame, _: Asset) -> pd.Series:
            return df["close"].pct_change(30) * 100

        def relative_volume(df: pd.DataFrame, _: Asset) -> pd.Series:
            return ind.relative_volume(df["volume"], 20)

        def volatility_rank(df: pd.DataFrame, _: Asset) -> pd.Series:
            return _trailing_rank(ind.atr_percent(df["high"], df["low"], df["close"], 14))

        def funding_percentile(df: pd.DataFrame, asset: Asset) -> pd.Series:
            funding = store.load_derivatives(asset, "funding.rate")
            if funding.empty:
                return pd.Series(np.nan, index=df.index)
            daily = funding.resample("1D").mean().dropna()
            ranks = _trailing_rank(daily, min_history=180)
            return ranks.reindex(df.index, method="ffill")

        def oi_change_7d(df: pd.DataFrame, asset: Asset) -> pd.Series:
            for metric in ("oi.contracts_bybit", "oi.value"):
                series = store.load_derivatives(asset, metric)
                if not series.empty:
                    daily = series.resample("1D").last().dropna()
                    change = daily.pct_change(7) * 100
                    return change.reindex(df.index, method="ffill")
            return pd.Series(np.nan, index=df.index)

        def oi_percentile(df: pd.DataFrame, asset: Asset) -> pd.Series:
            for metric in ("oi.contracts_bybit", "oi.value"):
                series = store.load_derivatives(asset, metric)
                if not series.empty:
                    daily = series.resample("1D").last().dropna()
                    return _trailing_rank(daily, min_history=180).reindex(
                        df.index, method="ffill"
                    )
            return pd.Series(np.nan, index=df.index)

        specs = [
            FeatureSpec("rsi_14", "Wilder RSI, 14 periods", rsi14, lag_bars=0),
            FeatureSpec("atr_percent", "ATR as a percentage of price", atr_pct),
            FeatureSpec("adx_14", "ADX trend strength", adx14),
            FeatureSpec("dist_ema200_pct", "Distance from the 200 EMA, percent", dist_ema200),
            FeatureSpec("dist_ema50_pct", "Distance from the 50 EMA, percent", dist_ema50),
            FeatureSpec("return_7d_pct", "Trailing 7-day return", return_7d, min_history=30),
            FeatureSpec("return_30d_pct", "Trailing 30-day return", return_30d, min_history=60),
            FeatureSpec("relative_volume_20", "Volume against its 20-bar mean", relative_volume),
            FeatureSpec(
                "volatility_rank", "Trailing percentile of ATR percent", volatility_rank,
                category="volatility",
            ),
            FeatureSpec(
                "funding_percentile", "Trailing percentile of funding", funding_percentile,
                category="derivatives", min_history=180,
            ),
            FeatureSpec(
                "oi_change_7d_pct", "7-day change in open interest", oi_change_7d,
                category="derivatives", min_history=30,
            ),
            FeatureSpec(
                "oi_percentile", "Trailing percentile of open interest", oi_percentile,
                category="derivatives", min_history=180,
            ),
        ]
        for spec in specs:
            self.register(spec)
        self._register_structural()

    def _register_structural(self) -> None:
        """LOT 5 structural features.

        Each is expensive - they replay range and pattern detection bar by bar -
        so they carry the detector version and are cached. They are still
        strictly point-in-time: every value uses only bars up to its own
        timestamp, which the mutation test asserts.
        """
        from ..structure.cache import DETECTOR_VERSION

        def _structural_frame(df: pd.DataFrame, asset: Asset, column: str) -> pd.Series:
            from ..core.enums import Timeframe
            from ..structure.cache import compute_incremental
            from ..structure.location import LocationState, StructuralLocationEngine
            from ..structure.ranges import RangeIntelligenceEngine

            engine = RangeIntelligenceEngine()
            location_engine = StructuralLocationEngine(engine)
            codes = {state.value: i for i, state in enumerate(LocationState)}

            def compute_row(window: pd.DataFrame) -> dict[str, Any]:
                detected = engine.detect_from_frame(window)
                if not detected.valid or not detected.top_zone or not detected.bottom_zone:
                    return {
                        "location_code": float(codes[LocationState.NO_VALID_RANGE.value]),
                        "range_position": float("nan"),
                        "range_width_atr": float("nan"),
                        "range_confidence": detected.confidence,
                    }
                price = float(window["close"].iloc[-1])
                state = location_engine._classify(
                    price, detected.top_zone, detected.bottom_zone,
                    detected.position(price),
                )
                return {
                    "location_code": float(codes.get(state.value, 0)),
                    "range_position": detected.position(price),
                    "range_width_atr": detected.width_atr,
                    "range_confidence": detected.confidence,
                }

            frame, _ = compute_incremental(
                asset, Timeframe.D1, "structural_features", compute_row, df
            )
            if frame.empty or column not in frame.columns:
                return pd.Series(np.nan, index=df.index)
            return frame[column].reindex(df.index)

        structural = [
            FeatureSpec(
                "range_location_code",
                "Structural location as an ordinal code, 0 = at range bottom",
                lambda df, a: _structural_frame(df, a, "location_code"),
                category="structure", min_history=150,
                formula="StructuralLocationEngine state, encoded ordinally",
                source="structure", detector_version=DETECTOR_VERSION,
            ),
            FeatureSpec(
                "range_position",
                "Position inside the validated range, 0 = bottom, 1 = top",
                lambda df, a: _structural_frame(df, a, "range_position"),
                category="structure", min_history=150,
                formula="(price - bottom_midpoint) / (top_midpoint - bottom_midpoint)",
                source="structure", detector_version=DETECTOR_VERSION,
            ),
            FeatureSpec(
                "range_width_atr",
                "Range width in ATR, so it is comparable across assets",
                lambda df, a: _structural_frame(df, a, "range_width_atr"),
                category="structure", min_history=150,
                formula="(top_midpoint - bottom_midpoint) / ATR14",
                source="structure", detector_version=DETECTOR_VERSION,
            ),
            FeatureSpec(
                "range_recognition_confidence",
                "How cleanly the range matches its definition - NOT a prediction",
                lambda df, a: _structural_frame(df, a, "range_confidence"),
                category="structure", min_history=150,
                formula="mean of touch, balance, duration, integrity and zone quality",
                source="structure", detector_version=DETECTOR_VERSION,
            ),
        ]
        for spec in structural:
            self.register(spec)

    # -- dataset ---------------------------------------------------------
    def build_dataset(
        self,
        asset: Asset,
        timeframe: Timeframe = Timeframe.D1,
        horizons: list[int] | None = None,
        *,
        backtest_safe_only: bool = True,
    ) -> tuple[pd.DataFrame, dict[str, Any]]:
        """Feature matrix plus forward returns, with a reproducibility manifest.

        Forward returns are placed in clearly named columns and are the only
        columns holding future information. Every feature column is built from
        the registry, which refuses non-point-in-time features when
        `backtest_safe_only` is set.
        """
        horizons = horizons or [1, 7, 30]
        df = store.load_candles(asset, timeframe)
        if df.empty:
            return pd.DataFrame(), {"status": "NO_DATA", "asset": asset.value}

        names = self.names(backtest_safe_only=backtest_safe_only)
        out = pd.DataFrame(index=df.index)
        built: list[str] = []
        skipped: list[dict[str, str]] = []

        for name in names:
            spec = self._features[name]
            try:
                series = spec.builder(df, asset)
            except Exception as exc:
                skipped.append({"feature": name, "reason": f"builder failed: {exc}"[:120]})
                continue
            if series is None or series.dropna().empty:
                skipped.append({"feature": name, "reason": "produced no values"})
                continue
            # A feature declaring a lag must be shifted, so the value at row t
            # is one that was actually knowable at t.
            out[name] = series.shift(spec.lag_bars) if spec.lag_bars else series
            built.append(name)

        # Forward returns, computed separately and never fed back into features.
        closes = df["close"]
        for horizon in horizons:
            out[f"target_fwd_{horizon}d_pct"] = (
                closes.shift(-horizon) - closes
            ) / closes * 100.0

        out["close"] = closes
        manifest = self._manifest(asset, timeframe, built, skipped, out, horizons)
        return out, manifest

    def _manifest(
        self, asset: Asset, timeframe: Timeframe, built: list[str],
        skipped: list[dict[str, str]], frame: pd.DataFrame, horizons: list[int],
    ) -> dict[str, Any]:
        definitions = {name: self._features[name].definition_hash() for name in built}
        definition_hash = hashlib.sha256(
            json.dumps(definitions, sort_keys=True).encode()
        ).hexdigest()[:16]

        coverage = {
            name: round(float(frame[name].notna().mean() * 100), 1) for name in built
        }
        return {
            "status": "OK",
            "asset": asset.value,
            "timeframe": timeframe.value,
            "feature_version": FEATURE_VERSION,
            "code_version": _git_revision(),
            "generated_at": datetime.now(UTC).isoformat(),
            "rows": len(frame),
            "period": {
                "start": str(frame.index.min())[:10], "end": str(frame.index.max())[:10],
            },
            "features_built": built,
            "features_skipped": skipped,
            "feature_coverage_pct": coverage,
            "target_columns": [f"target_fwd_{h}d_pct" for h in horizons],
            "definitions": definitions,
            "definition_hash": definition_hash,
            "point_in_time_safe": True,
            "note": (
                "Feature columns contain only information knowable at each row's "
                "timestamp. Columns prefixed 'target_' hold future returns and must "
                "never be used as inputs."
            ),
        }


def _git_revision() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL, timeout=5,
        ).decode().strip()
    except Exception:
        return "unknown"


_REGISTRY: FeatureRegistry | None = None


def get_registry() -> FeatureRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = FeatureRegistry()
    return _REGISTRY


def export_dataset(
    asset: Asset, out_dir: str = "data/datasets", timeframe: Timeframe = Timeframe.D1
) -> dict[str, Any]:
    """Write the dataset and its manifest side by side."""
    import pathlib

    frame, manifest = get_registry().build_dataset(asset, timeframe)
    if manifest.get("status") != "OK":
        return manifest

    directory = pathlib.Path(out_dir)
    directory.mkdir(parents=True, exist_ok=True)
    stem = f"{asset.value}_{timeframe.value}_{manifest['feature_version']}"

    csv_path = directory / f"{stem}.csv"
    frame.to_csv(csv_path)
    manifest["csv_path"] = str(csv_path)

    try:
        parquet_path = directory / f"{stem}.parquet"
        frame.to_parquet(parquet_path)
        manifest["parquet_path"] = str(parquet_path)
    except Exception as exc:
        manifest["parquet_note"] = f"parquet unavailable: {exc}"[:120]

    manifest_path = directory / f"{stem}_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, default=str))
    manifest["manifest_path"] = str(manifest_path)
    log.info("dataset_exported", asset=asset.value, rows=manifest["rows"], path=str(csv_path))
    return manifest

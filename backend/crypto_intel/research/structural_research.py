"""Do structural readings carry forward information?

This is the LOT 5 research core, and it applies every lesson LOT 4 paid for:

  * never test against zero - crypto rose, so everything "works" against zero;
  * compare against conditioned baselines, including same-regime;
  * report raw_n AND effective_n, because overlapping windows are not
    independent observations;
  * FDR across the whole hypothesis family, never per-test;
  * walk-forward with train / validation / out-of-sample;
  * a result that lives in one year is UNSTABLE regardless of its p-value.

The output is expected to be mostly NO_MEASURABLE_EDGE. That is a finding, not
a failure, and no threshold is tuned to avoid it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import ttest_ind

from ..core.enums import Asset, Timeframe
from ..engines.technical import indicators as ind
from ..history import store
from ..logging_setup import get_logger
from ..structure.location import StructuralLocationEngine
from ..structure.market_structure import MarketStructureEngine
from ..structure.patterns import (
    PATTERN_CLASSES,
    PatternEdgeState,
    build_context,
    detect_all,
)
from ..structure.ranges import RangeIntelligenceEngine
from .regime_conditioned import reconstruct_regime
from .stats import benjamini_hochberg

log = get_logger("research.structural")

HORIZONS_BY_TIMEFRAME: dict[str, list[int]] = {
    "1d": [1, 3, 7, 14, 30],
    "4h": [6, 12, 24, 42],       # bars: 1d, 2d, 4d, 7d
    "1h": [24, 48, 96, 168],
}

MIN_OCCURRENCES = 20
MIN_EFFECTIVE_N = 20
NEGLIGIBLE_EFFECT_PCT = 0.5
ROUND_TRIP_COST_PCT = 0.20
WINDOW = 150


@dataclass(slots=True)
class BaselineSet:
    """Every reference a result must beat, computed on the same bars."""

    unconditional: float | None = None
    same_regime: float | None = None
    same_regime_momentum: float | None = None
    momentum: float | None = None
    ema_trend: float | None = None
    random_draw: float | None = None
    always_long: float | None = None

    def best(self) -> tuple[str, float] | None:
        candidates = [
            (name, value) for name, value in {
                "unconditional": self.unconditional,
                "same_regime": self.same_regime,
                "same_regime_momentum": self.same_regime_momentum,
                "momentum": self.momentum,
                "ema_trend": self.ema_trend,
                "random": self.random_draw,
                "always_long": self.always_long,
            }.items() if value is not None
        ]
        return max(candidates, key=lambda kv: kv[1]) if candidates else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "unconditional": self.unconditional, "same_regime": self.same_regime,
            "same_regime_momentum": self.same_regime_momentum,
            "momentum": self.momentum, "ema_trend": self.ema_trend,
            "random": self.random_draw, "always_long": self.always_long,
        }


@dataclass(slots=True)
class StructuralEvent:
    """One occurrence of a structural condition, with its context at T."""

    timestamp: pd.Timestamp
    kind: str
    label: str
    regime: str
    momentum: str
    confidence: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)


def _momentum_bucket(close: pd.Series, window: int = 14) -> pd.Series:
    change = close.pct_change(window) * 100
    buckets = pd.Series(index=close.index, dtype=object)
    buckets[change <= -10] = "FALLING"
    buckets[(change > -10) & (change < 10)] = "FLAT"
    buckets[change >= 10] = "RISING"
    return buckets


def effective_sample(timestamps: pd.DatetimeIndex, horizon_bars: int, freq_days: float) -> dict[str, Any]:
    """Distinct episodes and independent windows.

    Two corrections matter. Occurrences on consecutive bars describe one
    episode, and forward windows that overlap share most of their return. The
    effective count is the smaller of the two corrections, because neither
    alone is sufficient.
    """
    if len(timestamps) == 0:
        return {"raw_n": 0, "episodes": 0, "effective_n": 0.0}

    ordered = pd.DatetimeIndex(sorted(timestamps))
    horizon_days = horizon_bars * freq_days
    gaps = ordered.to_series().diff().dt.total_seconds() / 86400.0
    episodes = int((gaps.fillna(1e9) > horizon_days).sum())
    overlap_adjusted = len(ordered) / max(horizon_bars, 1)

    return {
        "raw_n": len(ordered),
        "episodes": episodes,
        "effective_n": round(min(float(episodes), float(overlap_adjusted)), 1),
        "method": (
            "min(distinct episodes separated by the forward horizon, n / horizon). "
            "Both corrections are needed: clustering alone ignores window overlap, "
            "and overlap alone ignores repeated occurrences inside one episode."
        ),
    }


def _stratified_excess(
    forward: pd.Series, mask: pd.Series, regimes: pd.Series,
    min_events: int = 10, min_baseline: int = 20,
) -> dict[str, Any]:
    """Excess over a regime-MATCHED baseline, weighted by the event mix.

    Filtering to "regimes where the event occurs" is not conditioning when the
    event occurs everywhere. Comparing inside each regime and weighting by how
    often the event appears there is.
    """
    aligned = pd.concat(
        [forward.rename("fwd"), regimes.rename("regime"), mask.rename("event")], axis=1
    ).dropna(subset=["fwd", "regime"])
    if aligned.empty:
        return {"excess": None, "strata": []}

    strata: list[dict[str, Any]] = []
    weighted_event = weighted_baseline = 0.0
    total_weight = 0
    residual_events: list[float] = []
    residual_baseline: list[float] = []

    for regime_value, chunk in aligned.groupby("regime"):
        events = chunk.loc[chunk["event"], "fwd"]
        baseline = chunk.loc[~chunk["event"], "fwd"]
        if len(events) < min_events or len(baseline) < min_baseline:
            continue
        weight = len(events)
        event_mean = float(events.mean())
        baseline_mean = float(baseline.mean())
        strata.append({
            "regime": str(regime_value),
            "n_events": int(weight), "n_baseline": len(baseline),
            "event_mean_pct": round(event_mean, 3),
            "baseline_mean_pct": round(baseline_mean, 3),
            "excess_pct": round(event_mean - baseline_mean, 3),
        })
        weighted_event += event_mean * weight
        weighted_baseline += baseline_mean * weight
        total_weight += weight
        residual_events.extend((events - baseline_mean).tolist())
        residual_baseline.extend((baseline - baseline_mean).tolist())

    if not total_weight or len(residual_events) < 30 or len(residual_baseline) < 30:
        return {"excess": None, "strata": strata}

    t_stat, p_value = ttest_ind(residual_events, residual_baseline, equal_var=False)
    return {
        "excess": (weighted_event - weighted_baseline) / total_weight,
        "baseline": round(weighted_baseline / total_weight, 3),
        "p_value": float(p_value),
        "t_stat": round(float(t_stat), 3),
        "regimes_used": len(strata),
        "strata": strata,
    }


def _year_stability(
    forward: pd.Series, mask: pd.Series, baseline: pd.Series
) -> dict[str, Any]:
    """Sign consistency across calendar years."""
    event_returns = forward[mask].dropna()
    if event_returns.empty or baseline.empty:
        return {"verdict": "NO_DATA", "years_covered": 0}

    by_year: dict[str, float] = {}
    for year, chunk in event_returns.groupby(event_returns.index.year):
        base_year = baseline[baseline.index.year == year]
        if len(chunk) < 3 or len(base_year) < 20:
            continue
        by_year[str(year)] = round(float(chunk.mean() - base_year.mean()), 3)

    if len(by_year) < 2:
        return {"verdict": "INSUFFICIENT_YEARS", "years_covered": len(by_year), "by_year": by_year}

    values = list(by_year.values())
    positive = sum(1 for v in values if v > 0)
    dominant = max(positive, len(values) - positive)
    share = dominant / len(values)
    return {
        "years_covered": len(values),
        "years_positive": positive,
        "sign_consistency_pct": round(share * 100, 1),
        "by_year": by_year,
        "worst_year": min(values),
        "best_year": max(values),
        "verdict": (
            "STABLE" if share >= 0.7 and len(values) >= 3
            else "MIXED" if share >= 0.55 else "UNSTABLE"
        ),
    }


def _walk_forward(
    forward: pd.Series,
    mask: pd.Series,
    baseline_mask: pd.Series,
    horizon_bars: int,
) -> dict[str, Any]:
    """Chronological train / validation / out-of-sample excess, purged.

    Splits are by time, never random: shuffling a time series and calling the
    result out-of-sample is one of the most common ways to fool yourself.

    Splitting by time is not sufficient on its own. A bar on the last day of
    the training window carries a forward return that runs `horizon_bars` into
    the validation window, so the two windows share outcomes and their
    agreement is partly mechanical. Each window therefore ends `horizon_bars`
    early, and a further embargo of `horizon_bars` is dropped afterwards to
    break the serial correlation that outlives the overlap itself. The cost is
    a few percent of the sample; the alternative is a sign-consistency figure
    that measures the split, not the signal.
    """
    index = forward.dropna().index
    if len(index) < 300:
        return {"status": "INSUFFICIENT_DATA", "bars": len(index)}

    embargo = horizon_bars
    first_cut = int(len(index) * 0.5)
    second_cut = int(len(index) * 0.75)
    gap = horizon_bars + embargo
    if second_cut - first_cut <= gap or len(index) - second_cut <= gap:
        return {
            "status": "INSUFFICIENT_DATA",
            "bars": len(index),
            "note": (
                f"a {horizon_bars}-bar horizon needs a {gap}-bar purge between "
                "splits, which leaves no usable validation window"
            ),
        }

    windows = {
        "train": (0, first_cut - gap),
        "validation": (first_cut, second_cut - gap),
        "oos": (second_cut, len(index)),
    }

    out: dict[str, Any] = {
        "status": "OK",
        "splits": {},
        "purge_bars": horizon_bars,
        "embargo_bars": embargo,
        "bars_discarded_to_purge": 2 * gap,
    }
    excesses: list[float] = []
    for name, (lo, hi) in windows.items():
        if hi <= lo:
            out["splits"][name] = {"status": "INSUFFICIENT_DATA", "n": 0}
            continue
        start, end = index[lo], index[hi - 1]
        window = (forward.index >= start) & (forward.index <= end)
        events = forward[mask & window].dropna()
        baseline = forward[baseline_mask & ~mask & window].dropna()
        if len(events) < 10 or len(baseline) < 30:
            out["splits"][name] = {
                "status": "INSUFFICIENT_DATA", "n": len(events),
                "baseline_n": len(baseline),
            }
            continue
        excess = float(events.mean() - baseline.mean())
        excesses.append(excess)
        out["splits"][name] = {
            "status": "OK", "n": len(events),
            "mean_pct": round(float(events.mean()), 3),
            "baseline_mean_pct": round(float(baseline.mean()), 3),
            "excess_pct": round(excess, 3),
            "period": f"{str(start)[:10]} to {str(end)[:10]}",
        }

    if len(excesses) >= 2:
        signs = {np.sign(e) for e in excesses if e != 0}
        out["sign_consistent_across_splits"] = len(signs) == 1
        out["mean_excess_pct"] = round(float(np.mean(excesses)), 3)
        oos = out["splits"].get("oos", {})
        out["oos_confirms"] = (
            oos.get("status") == "OK"
            and np.sign(oos.get("excess_pct", 0)) == np.sign(out["mean_excess_pct"])
            and abs(oos.get("excess_pct", 0)) >= NEGLIGIBLE_EFFECT_PCT
        )
    else:
        out["status"] = "INSUFFICIENT_SPLITS"
    return out


def build_event_frame(
    asset: Asset, timeframe: Timeframe, step: int = 1
) -> tuple[pd.DataFrame, list[StructuralEvent]]:
    """Replay structure bar by bar, seeing only the past at each step."""
    df = store.load_candles(asset, timeframe)
    if df.empty or len(df) < WINDOW + 60:
        return pd.DataFrame(), []

    range_engine = RangeIntelligenceEngine()
    location_engine = StructuralLocationEngine(range_engine)
    structure_engine = MarketStructureEngine()

    regimes = reconstruct_regime(df)
    momentum = _momentum_bucket(df["close"])
    events: list[StructuralEvent] = []

    for i in range(WINDOW, len(df), step):
        window = df.iloc[:i + 1]
        timestamp = df.index[i]
        regime = str(regimes.iloc[i]) if i < len(regimes) else "UNKNOWN"
        bucket = str(momentum.iloc[i]) if i < len(momentum) else "UNKNOWN"

        # Range location
        try:
            detected = range_engine.detect_from_frame(window)
            if detected.valid and detected.top_zone and detected.bottom_zone:
                price = float(window["close"].iloc[-1])
                state = location_engine._classify(
                    price, detected.top_zone, detected.bottom_zone,
                    detected.position(price),
                )
                events.append(StructuralEvent(
                    timestamp=timestamp, kind="location", label=state.value,
                    regime=regime, momentum=bucket, confidence=detected.confidence,
                ))
        except Exception:
            pass

        # Market structure
        try:
            reading = structure_engine.assess_from_swings(
                _swings_for(window), _blank_reading(asset, timeframe), window
            )
            events.append(StructuralEvent(
                timestamp=timestamp, kind="structure", label=reading.state.value,
                regime=regime, momentum=bucket,
            ))
        except Exception:
            pass

        # Patterns
        try:
            ctx = build_context(window, timeframe)
            if ctx is not None:
                for pattern in detect_all(ctx):
                    events.append(StructuralEvent(
                        timestamp=timestamp, kind="pattern",
                        label=f"{pattern.name}|{pattern.state.value}",
                        regime=regime, momentum=bucket,
                        confidence=pattern.recognition_confidence,
                        extra={"textbook": pattern.direction_if_textbook},
                    ))
        except Exception:
            pass

    return df, events


def _swings_for(window: pd.DataFrame):
    from ..structure.swings import find_causal_swings

    atr = ind.atr(window["high"], window["low"], window["close"], 14)
    swings = find_causal_swings(window["high"], window["low"], window["close"], atr, lookback=5)
    return swings.as_of(window.index[-1])


def _blank_reading(asset: Asset, timeframe: Timeframe):
    from ..structure.market_structure import MarketStructureReading

    return MarketStructureReading(asset=asset.value, timeframe=timeframe.value)


def analyse(
    asset: Asset, timeframe: Timeframe = Timeframe.D1, step: int = 1
) -> dict[str, Any]:
    """Measure every structural label against conditioned baselines."""
    df, events = build_event_frame(asset, timeframe, step)
    out: dict[str, Any] = {
        "asset": asset.value, "timeframe": timeframe.value,
        "status": "OK", "labels": {},
    }
    if df.empty or not events:
        out["status"] = "NO_DATA"
        out["note"] = "not enough history to replay structure"
        return out

    horizons = HORIZONS_BY_TIMEFRAME.get(timeframe.value, [1, 7, 30])
    freq_days = {"1d": 1.0, "4h": 1 / 6, "1h": 1 / 24}.get(timeframe.value, 1.0)
    closes = df["close"]
    forward = {h: (closes.shift(-h) - closes) / closes * 100.0 for h in horizons}

    regimes = reconstruct_regime(df)
    momentum = _momentum_bucket(closes)
    ema200 = closes.ewm(span=200, adjust=False).mean()
    rng = np.random.default_rng(1234)
    random_mask = pd.Series(rng.random(len(df)) < 0.5, index=df.index)
    trend_mask = closes > ema200
    momentum_mask = closes.pct_change(30) > 0

    frame = pd.DataFrame({"kind": [e.kind for e in events],
                          "label": [e.label for e in events],
                          "confidence": [e.confidence for e in events]},
                         index=pd.DatetimeIndex([e.timestamp for e in events]))
    out["total_events"] = len(frame)
    out["bars_scanned"] = len(df)

    tests: list[tuple[str, float]] = []
    for label in sorted(frame["label"].unique()):
        subset = frame[frame["label"] == label]
        timestamps = pd.DatetimeIndex(subset.index.unique())
        kind = str(subset["kind"].iloc[0])

        entry: dict[str, Any] = {
            "kind": kind,
            "raw_occurrences": len(timestamps),
            "mean_recognition_confidence": (
                round(float(subset["confidence"].mean()), 1)
                if subset["confidence"].notna().any() else None
            ),
            "pattern_class": (
                PATTERN_CLASSES.get(label.split("|")[0], "").value
                if kind == "pattern" and label.split("|")[0] in PATTERN_CLASSES else None
            ),
            "horizons": {},
        }

        if len(timestamps) < MIN_OCCURRENCES:
            entry["edge_state"] = PatternEdgeState.INSUFFICIENT_DATA.value
            entry["note"] = f"{len(timestamps)} occurrences, below the {MIN_OCCURRENCES} minimum"
            out["labels"][label] = entry
            continue

        mask = pd.Series(False, index=df.index)
        mask.loc[mask.index.isin(timestamps)] = True
        # Kept only for the descriptive baseline columns. Note that when a
        # label occurs in every regime - which most do - these masks cover the
        # whole sample, so they are NOT a conditioning. The stratified
        # estimator below is what actually holds the regime fixed.
        event_regimes = set(regimes[mask].dropna().unique())
        event_momentum = set(momentum[mask].dropna().unique())
        same_regime_mask = regimes.isin(event_regimes)
        same_both_mask = same_regime_mask & momentum.isin(event_momentum)

        for horizon in horizons:
            fwd = forward[horizon]
            events_returns = fwd[mask].dropna()
            if len(events_returns) < MIN_OCCURRENCES:
                entry["horizons"][f"{horizon}b"] = {"status": "INSUFFICIENT_DATA"}
                continue

            baselines = BaselineSet(
                unconditional=_mean(fwd[~mask]),
                same_regime=_mean(fwd[same_regime_mask & ~mask]),
                same_regime_momentum=_mean(fwd[same_both_mask & ~mask]),
                momentum=_mean(fwd[momentum_mask & ~mask]),
                ema_trend=_mean(fwd[trend_mask & ~mask]),
                random_draw=_mean(fwd[random_mask & ~mask]),
                always_long=_mean(fwd),
            )
            # REGIME STRATIFICATION.
            #
            # An earlier version used fwd[regimes.isin(event_regimes) & ~mask]
            # as the "same regime" baseline. Structural labels occur in every
            # regime, so that mask selected the entire sample and the baseline
            # was silently unconditional - reintroducing exactly the market
            # drift the LOT 4 funding study was corrected for. Comparing
            # within each regime and weighting by the event mix is what
            # actually holds the regime fixed.
            stratified = _stratified_excess(fwd, mask, regimes)
            primary = fwd[same_regime_mask & ~mask].dropna()
            sample = effective_sample(
                pd.DatetimeIndex(events_returns.index), horizon, freq_days
            )

            cell: dict[str, Any] = {
                "status": "OK",
                "raw_n": sample["raw_n"], "episodes": sample["episodes"],
                "effective_n": sample["effective_n"],
                "mean_return_pct": round(float(events_returns.mean()), 3),
                "win_rate": round(float((events_returns > 0).mean() * 100), 1),
                "baselines": baselines.to_dict(),
            }

            cell["excess_vs_unconditional_pct"] = (
                round(float(events_returns.mean() - primary.mean()), 3)
                if len(primary) >= 30 else None
            )
            cell["regime_strata"] = stratified.get("strata", [])

            if stratified.get("excess") is not None:
                excess = stratified["excess"]
                cell["excess_vs_same_regime_pct"] = round(excess, 3)
                cell["regime_matched_baseline_pct"] = stratified["baseline"]
                cell["p_value"] = stratified["p_value"]
                cell["t_stat"] = stratified["t_stat"]
                cell["regimes_used"] = stratified["regimes_used"]
                cell["gross_edge_pct"] = round(excess, 3)
                cell["estimated_friction_pct"] = ROUND_TRIP_COST_PCT
                cell["net_edge_pct"] = round(
                    np.sign(excess) * max(abs(excess) - ROUND_TRIP_COST_PCT, 0.0), 3
                )
                best = baselines.best()
                if best:
                    cell["best_simple_baseline"] = {"name": best[0], "mean_pct": best[1]}
                    cell["beats_best_baseline"] = bool(
                        float(events_returns.mean()) > best[1]
                    )
                cell["stability"] = _year_stability(fwd, mask, primary)
                cell["walk_forward"] = _walk_forward(fwd, mask, same_regime_mask, horizon)
                tests.append((f"{label}|{horizon}b", stratified["p_value"]))
            else:
                cell["note"] = (
                    "no regime had enough events and baseline days for a stratified "
                    "comparison"
                )

            entry["horizons"][f"{horizon}b"] = cell

        out["labels"][label] = entry

    labels = [name for name, _ in tests]
    p_values = [p for _, p in tests]
    survives = benjamini_hochberg(p_values, alpha=0.05)
    survivors = {name for name, ok in zip(labels, survives, strict=True) if ok}

    out["multiple_testing"] = {
        "hypotheses_tested": len(tests),
        "raw_significant": sum(1 for p in p_values if p < 0.05),
        "fdr_significant": len(survivors),
        "expected_false_positives": round(len(tests) * 0.05, 1),
        "survivors": sorted(survivors),
        "method": "Benjamini-Hochberg alpha=0.05 across every label and horizon here",
    }
    _assign_edge_states(out, survivors)
    return out


def _mean(series: pd.Series) -> float | None:
    clean = series.dropna()
    return round(float(clean.mean()), 3) if len(clean) >= 30 else None


def _assign_edge_states(out: dict[str, Any], survivors: set[str]) -> None:
    """Apply the full filter chain. Most labels will end NO_MEASURABLE_EDGE."""
    for label, entry in out["labels"].items():
        if entry.get("edge_state"):
            continue

        admitted: list[str] = []
        rejections: list[str] = []
        unstable = False

        for horizon_key, cell in entry.get("horizons", {}).items():
            if cell.get("status") != "OK" or "excess_vs_same_regime_pct" not in cell:
                continue
            key = f"{label}|{horizon_key}"
            excess = cell["excess_vs_same_regime_pct"]

            if key not in survivors:
                continue
            if abs(excess) < NEGLIGIBLE_EFFECT_PCT:
                rejections.append(f"{horizon_key}: effect {excess:+.2f}% below floor")
                continue
            if cell.get("net_edge_pct", 0) == 0:
                rejections.append(f"{horizon_key}: does not clear {ROUND_TRIP_COST_PCT}% friction")
                continue
            if cell.get("effective_n", 0) < MIN_EFFECTIVE_N:
                rejections.append(
                    f"{horizon_key}: effective_n {cell.get('effective_n')} below {MIN_EFFECTIVE_N}"
                )
                continue
            stability = cell.get("stability", {})
            if stability.get("verdict") != "STABLE":
                unstable = True
                rejections.append(
                    f"{horizon_key}: {stability.get('verdict')} across years "
                    f"({stability.get('years_positive')}/{stability.get('years_covered')})"
                )
                continue
            walk = cell.get("walk_forward", {})
            if not walk.get("oos_confirms"):
                rejections.append(f"{horizon_key}: not confirmed out-of-sample")
                continue
            admitted.append(f"{horizon_key} ({excess:+.2f}%)")

        if admitted:
            first = admitted[0]
            sign = "+" in first
            entry["edge_state"] = (
                PatternEdgeState.POSITIVE_EDGE.value if sign
                else PatternEdgeState.NEGATIVE_EDGE.value
            )
            entry["note"] = f"survives every filter at {', '.join(admitted)}"
        elif unstable:
            entry["edge_state"] = PatternEdgeState.UNSTABLE.value
            entry["note"] = "; ".join(rejections)
        else:
            entry["edge_state"] = PatternEdgeState.NO_MEASURABLE_EDGE.value
            entry["note"] = (
                "; ".join(rejections) if rejections
                else "no horizon survives FDR against a same-regime baseline"
            )


def run_all(
    assets: list[Asset] | None = None,
    timeframes: list[Timeframe] | None = None,
    step: int = 1,
) -> dict[str, Any]:
    assets = assets or Asset.tradables()
    timeframes = timeframes or [Timeframe.D1]
    results: dict[str, Any] = {}
    for asset in assets:
        for timeframe in timeframes:
            key = f"{asset.value}_{timeframe.value}"
            try:
                results[key] = analyse(asset, timeframe, step)
            except Exception as exc:
                log.warning("structural_research_failed", key=key, error=str(exc))
                results[key] = {"status": "ERROR", "error": str(exc)[:250]}
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "results": results,
        "note": (
            "Recognition confidence and predictive edge are separate quantities "
            "throughout. A structure can be recognised cleanly and carry no "
            "measurable forward information."
        ),
    }

"""The two central questions of LOT 5.

Q1 (§66): does knowing BTC sits near a range bottom add anything ONCE we
already know the regime, momentum, volatility, funding and crowding?

Q2 (§67): does each layer of chart-reading sophistication beat the simpler one
out of sample?

    A  simple numeric features    trend, momentum, volatility, RSI, funding, OI
    B  A + structural location    where price sits in its range
    C  B + patterns               detected chart patterns
    D  C + human-like annotations reserved for the annotated dataset

The answer is measured, not argued. Models are deliberately simple and
regularised - a gradient-boosted forest would fit the noise and tell us
nothing about whether the INFORMATION is there. Everything is evaluated
chronologically out of sample, because a shuffled split on a time series
manufactures skill that does not exist.

If B does not beat A, the honest conclusion is that range location adds
nothing beyond what the numeric features already carry, and this module says
so plainly.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import accuracy_score, r2_score, roc_auc_score
from sklearn.preprocessing import StandardScaler

from ..core.enums import Asset, Timeframe
from ..engines.technical import indicators as ind
from ..history import store
from ..logging_setup import get_logger
from ..structure.location import LocationState
from ..structure.patterns import build_context, detect_all
from ..structure.ranges import RangeIntelligenceEngine
from .regime_conditioned import reconstruct_regime

log = get_logger("research.marginal_value")

WINDOW = 150
MIN_ROWS = 400


def build_layered_features(
    asset: Asset, timeframe: Timeframe = Timeframe.D1, step: int = 1
) -> pd.DataFrame:
    """One frame carrying every layer, built causally bar by bar.

    Each row uses only bars up to and including its own timestamp. The forward
    return columns are added at the end and never feed any feature.
    """
    df = store.load_candles(asset, timeframe)
    if df.empty or len(df) < WINDOW + 60:
        return pd.DataFrame()

    close, high, low, volume = df["close"], df["high"], df["low"], df["volume"]

    # --- layer A: simple numeric features, all vectorised and causal --------
    frame = pd.DataFrame(index=df.index)
    frame["rsi_14"] = ind.rsi(close, 14)
    frame["adx_14"] = ind.adx(high, low, close, 14)
    frame["atr_pct"] = ind.atr_percent(high, low, close, 14)
    frame["dist_ema50"] = (close - close.ewm(span=50, adjust=False).mean()) / close * 100
    frame["dist_ema200"] = (close - close.ewm(span=200, adjust=False).mean()) / close * 100
    frame["return_7"] = close.pct_change(7) * 100
    frame["return_30"] = close.pct_change(30) * 100
    frame["rel_volume"] = ind.relative_volume(volume, 20)

    funding = store.load_derivatives(asset, "funding.rate")
    if not funding.empty:
        daily = funding.resample("1D").mean().dropna()
        frame["funding"] = daily.reindex(df.index, method="ffill")
    oi = store.load_derivatives(asset, "oi.contracts_bybit")
    if not oi.empty:
        daily_oi = oi.resample("1D").last().dropna()
        frame["oi_change_7"] = (daily_oi.pct_change(7) * 100).reindex(df.index, method="ffill")

    regimes = reconstruct_regime(df)
    regime_codes = {
        "STRONGLY_BEARISH": -2, "BEARISH": -1, "NEUTRAL": 0,
        "BULLISH": 1, "STRONGLY_BULLISH": 2,
    }
    frame["regime_code"] = regimes.map(regime_codes)

    # --- layers B and C: structural, computed by replay --------------------
    range_engine = RangeIntelligenceEngine()
    location_codes = {state.value: i for i, state in enumerate(LocationState)}

    location_series = pd.Series(np.nan, index=df.index)
    position_series = pd.Series(np.nan, index=df.index)
    range_width_series = pd.Series(np.nan, index=df.index)
    range_conf_series = pd.Series(np.nan, index=df.index)
    pattern_count = pd.Series(0.0, index=df.index)
    pattern_bull = pd.Series(0.0, index=df.index)
    pattern_bear = pd.Series(0.0, index=df.index)
    pattern_conf = pd.Series(np.nan, index=df.index)

    from ..structure.location import StructuralLocationEngine

    location_engine = StructuralLocationEngine(range_engine)

    for i in range(WINDOW, len(df), step):
        window = df.iloc[:i + 1]
        timestamp = df.index[i]
        try:
            detected = range_engine.detect_from_frame(window)
            if detected.valid and detected.top_zone and detected.bottom_zone:
                price = float(window["close"].iloc[-1])
                state = location_engine._classify(
                    price, detected.top_zone, detected.bottom_zone, detected.position(price)
                )
                location_series.loc[timestamp] = location_codes.get(state.value, np.nan)
                position_series.loc[timestamp] = detected.position(price)
                range_width_series.loc[timestamp] = detected.width_atr
                range_conf_series.loc[timestamp] = detected.confidence
        except Exception:
            pass

        try:
            ctx = build_context(window, timeframe)
            if ctx is not None:
                patterns = detect_all(ctx)
                pattern_count.loc[timestamp] = len(patterns)
                pattern_bull.loc[timestamp] = sum(
                    1 for p in patterns if p.direction_if_textbook == "BULLISH"
                )
                pattern_bear.loc[timestamp] = sum(
                    1 for p in patterns if p.direction_if_textbook == "BEARISH"
                )
                if patterns:
                    pattern_conf.loc[timestamp] = max(
                        p.recognition_confidence for p in patterns
                    )
        except Exception:
            pass

    frame["location_code"] = location_series
    frame["range_position"] = position_series
    frame["range_width_atr"] = range_width_series
    frame["range_confidence"] = range_conf_series
    frame["pattern_count"] = pattern_count
    frame["pattern_bullish"] = pattern_bull
    frame["pattern_bearish"] = pattern_bear
    frame["pattern_confidence"] = pattern_conf.fillna(0.0)

    # --- targets, added last and never used as inputs ----------------------
    for horizon in (7, 30):
        frame[f"target_{horizon}"] = (close.shift(-horizon) - close) / close * 100
        frame[f"target_{horizon}_up"] = (frame[f"target_{horizon}"] > 0).astype(int)

    frame["close"] = close
    return frame


LAYER_A = [
    "rsi_14", "adx_14", "atr_pct", "dist_ema50", "dist_ema200",
    "return_7", "return_30", "rel_volume", "regime_code", "funding", "oi_change_7",
]
LAYER_B_EXTRA = ["location_code", "range_position", "range_width_atr", "range_confidence"]
LAYER_C_EXTRA = ["pattern_count", "pattern_bullish", "pattern_bearish", "pattern_confidence"]


def _evaluate_layer(
    frame: pd.DataFrame, features: list[str], horizon: int
) -> dict[str, Any]:
    """Chronological train/test on one feature set."""
    available = [f for f in features if f in frame.columns]
    target_return = f"target_{horizon}"
    target_class = f"target_{horizon}_up"

    subset = frame[[*available, target_return, target_class]].dropna()
    if len(subset) < MIN_ROWS:
        return {
            "status": "INSUFFICIENT_DATA", "rows": len(subset),
            "features_used": available,
            "note": f"{len(subset)} complete rows, need {MIN_ROWS}",
        }

    # Chronological split. Never shuffled: a random split on overlapping
    # forward returns leaks the test period into training almost completely.
    split = int(len(subset) * 0.7)
    train, test = subset.iloc[:split], subset.iloc[split:]

    scaler = StandardScaler()
    x_train = scaler.fit_transform(train[available])
    x_test = scaler.transform(test[available])

    ridge = Ridge(alpha=10.0)
    ridge.fit(x_train, train[target_return])
    r2 = float(r2_score(test[target_return], ridge.predict(x_test)))

    result: dict[str, Any] = {
        "status": "OK",
        "features_used": available,
        "n_features": len(available),
        "train_rows": len(train), "test_rows": len(test),
        "train_period": f"{str(train.index.min())[:10]} to {str(train.index.max())[:10]}",
        "test_period": f"{str(test.index.min())[:10]} to {str(test.index.max())[:10]}",
        "oos_r2": round(r2, 4),
    }

    # Direction classification, which is the more interpretable question.
    if train[target_class].nunique() > 1 and test[target_class].nunique() > 1:
        model = LogisticRegression(C=0.5, max_iter=2000)
        model.fit(x_train, train[target_class])
        predictions = model.predict(x_test)
        probabilities = model.predict_proba(x_test)[:, 1]
        result["oos_accuracy"] = round(float(accuracy_score(test[target_class], predictions)), 4)
        result["oos_auc"] = round(float(roc_auc_score(test[target_class], probabilities)), 4)
        # The baseline that matters: always predicting the majority class.
        majority = float(max(test[target_class].mean(), 1 - test[target_class].mean()))
        result["majority_class_accuracy"] = round(majority, 4)
        result["beats_majority"] = bool(result["oos_accuracy"] > majority)

    return result


def compare_layers(
    asset: Asset, timeframe: Timeframe = Timeframe.D1, horizon: int = 7, step: int = 1,
    frame: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Q2: does each layer of chart reading beat the simpler one out of sample?"""
    if frame is None:
        frame = build_layered_features(asset, timeframe, step)
    if frame.empty:
        return {"asset": asset.value, "status": "NO_DATA"}

    layers = {
        "A_numeric": LAYER_A,
        "B_plus_location": LAYER_A + LAYER_B_EXTRA,
        "C_plus_patterns": LAYER_A + LAYER_B_EXTRA + LAYER_C_EXTRA,
    }
    results = {
        name: _evaluate_layer(frame, features, horizon)
        for name, features in layers.items()
    }

    verdict = _layer_verdict(results)
    return {
        "asset": asset.value, "timeframe": timeframe.value,
        "horizon_days": horizon, "status": "OK",
        "layers": results,
        "verdict": verdict,
        "note": (
            "Layer D (human annotations) is not evaluated: the annotated dataset does "
            "not yet contain enough verified examples. It is INSUFFICIENT_DATA, not "
            "a negative result."
        ),
    }


def _layer_verdict(results: dict[str, Any]) -> dict[str, Any]:
    def metric(name: str, key: str) -> float | None:
        entry = results.get(name, {})
        return entry.get(key) if entry.get("status") == "OK" else None

    a_r2, b_r2, c_r2 = (metric(n, "oos_r2") for n in ("A_numeric", "B_plus_location", "C_plus_patterns"))
    a_auc, b_auc, c_auc = (metric(n, "oos_auc") for n in ("A_numeric", "B_plus_location", "C_plus_patterns"))

    lines: list[str] = []
    location_adds = None
    patterns_add = None

    if a_r2 is not None and b_r2 is not None:
        location_adds = b_r2 > a_r2
        lines.append(
            f"Adding structural location moves out-of-sample R2 from {a_r2:+.4f} to "
            f"{b_r2:+.4f} ({'an improvement' if location_adds else 'no improvement'})."
        )
    if b_r2 is not None and c_r2 is not None:
        patterns_add = c_r2 > b_r2
        lines.append(
            f"Adding patterns moves it from {b_r2:+.4f} to {c_r2:+.4f} "
            f"({'an improvement' if patterns_add else 'no improvement'})."
        )
    if a_auc is not None and b_auc is not None:
        lines.append(f"Direction AUC: A {a_auc:.3f}, B {b_auc:.3f}, C {c_auc or float('nan'):.3f}.")

    # A negative R2 means the model is worse than predicting the mean. When
    # every layer is negative, the honest reading is that none of them carry
    # usable information, and comparing them is comparing degrees of failure.
    all_negative = all(v is not None and v < 0 for v in (a_r2, b_r2, c_r2))
    if all_negative:
        summary = (
            "Every layer has NEGATIVE out-of-sample R2, meaning each predicts forward "
            "returns worse than simply using the training mean. Ranking them is "
            "ranking degrees of failure: no layer carries usable predictive "
            "information at this horizon."
        )
        answer = "NO_LAYER_ADDS_VALUE"
    elif location_adds and patterns_add:
        summary = "Each additional layer improved out-of-sample fit."
        answer = "BOTH_ADD_VALUE"
    elif location_adds:
        summary = "Structural location improved out-of-sample fit; patterns did not."
        answer = "LOCATION_ONLY"
    elif patterns_add:
        summary = "Patterns improved out-of-sample fit; structural location did not."
        answer = "PATTERNS_ONLY"
    else:
        summary = (
            "Neither structural location nor patterns improved out-of-sample fit over "
            "the simple numeric features."
        )
        answer = "NEITHER_ADDS_VALUE"

    return {
        "answer": answer, "summary": summary, "details": lines,
        "location_improves_r2": location_adds,
        "patterns_improve_r2": patterns_add,
    }


def marginal_value_of_location(
    asset: Asset, timeframe: Timeframe = Timeframe.D1, horizon: int = 7,
    step: int = 1, frame: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Q1: is being near a range bottom informative beyond the regime alone?

    The comparison that answers it: forward returns near a range bottom versus
    forward returns on all OTHER days in the SAME regime. If the two are
    indistinguishable, the location told us nothing the regime had not.
    """
    if frame is None:
        frame = build_layered_features(asset, timeframe, step)
    if frame.empty:
        return {"asset": asset.value, "status": "NO_DATA"}

    from scipy.stats import ttest_ind

    location_codes = {state.value: i for i, state in enumerate(LocationState)}
    bottom_codes = {
        location_codes[LocationState.AT_RANGE_BOTTOM.value],
        location_codes[LocationState.NEAR_RANGE_BOTTOM.value],
        location_codes[LocationState.LOWER_THIRD.value],
    }
    top_codes = {
        location_codes[LocationState.AT_RANGE_TOP.value],
        location_codes[LocationState.NEAR_RANGE_TOP.value],
        location_codes[LocationState.UPPER_THIRD.value],
    }

    target = f"target_{horizon}"
    subset = frame[["location_code", "regime_code", target]].dropna()
    if len(subset) < 200:
        return {
            "asset": asset.value, "status": "INSUFFICIENT_DATA",
            "rows": len(subset),
        }

    out: dict[str, Any] = {
        "asset": asset.value, "timeframe": timeframe.value,
        "horizon_days": horizon, "status": "OK", "comparisons": {},
    }

    for name, codes in (("range_bottom", bottom_codes), ("range_top", top_codes)):
        mask = subset["location_code"].isin(codes)
        if mask.sum() < 30:
            out["comparisons"][name] = {
                "status": "INSUFFICIENT_DATA", "n": int(mask.sum()),
            }
            continue

        events = subset.loc[mask, target]
        unconditional = subset.loc[~mask, target]

        # Regime STRATIFICATION, not regime filtering.
        #
        # The first version compared events to "days in any regime where the
        # event occurs". Range-bottom events occur in every regime, so that set
        # was the whole sample and the two baselines came out numerically
        # identical - the conditioning did nothing at all. Matching the regime
        # MIX is what actually holds the regime fixed: compare inside each
        # regime, then weight those comparisons by how often the event appears
        # there.
        strata: list[dict[str, Any]] = []
        weighted_event = 0.0
        weighted_baseline = 0.0
        total_weight = 0
        residual_events: list[float] = []
        residual_baseline: list[float] = []

        for regime_value, regime_rows in subset.loc[mask].groupby("regime_code"):
            regime_baseline = subset.loc[
                (subset["regime_code"] == regime_value) & ~mask, target
            ]
            regime_events = regime_rows[target]
            if len(regime_events) < 10 or len(regime_baseline) < 20:
                continue
            weight = len(regime_events)
            event_mean = float(regime_events.mean())
            baseline_mean = float(regime_baseline.mean())
            strata.append({
                "regime_code": float(regime_value),
                "n_events": int(weight),
                "n_baseline": len(regime_baseline),
                "event_mean_pct": round(event_mean, 3),
                "baseline_mean_pct": round(baseline_mean, 3),
                "excess_pct": round(event_mean - baseline_mean, 3),
            })
            weighted_event += event_mean * weight
            weighted_baseline += baseline_mean * weight
            total_weight += weight
            # Centre both groups on the regime baseline so the test measures
            # the same quantity the weighted estimate reports.
            residual_events.extend((regime_events - baseline_mean).tolist())
            residual_baseline.extend((regime_baseline - baseline_mean).tolist())

        entry: dict[str, Any] = {
            "status": "OK",
            "n": len(events),
            "mean_return_pct": round(float(events.mean()), 3),
            "unconditional_baseline_pct": round(float(unconditional.mean()), 3),
            "excess_vs_unconditional_pct": round(
                float(events.mean() - unconditional.mean()), 3
            ),
            "regime_strata": strata,
            "regimes_used": len(strata),
        }

        if total_weight and strata:
            stratified_excess = (weighted_event - weighted_baseline) / total_weight
            entry["regime_matched_baseline_pct"] = round(
                weighted_baseline / total_weight, 3
            )
            entry["excess_vs_regime_matched_pct"] = round(stratified_excess, 3)

            if len(residual_events) >= 30 and len(residual_baseline) >= 30:
                t_stat, p_value = ttest_ind(
                    residual_events, residual_baseline, equal_var=False
                )
                entry["p_value_vs_regime_matched"] = float(p_value)
                entry["t_stat"] = round(float(t_stat), 3)
                entry["adds_information"] = bool(
                    p_value < 0.05 and abs(stratified_excess) >= 0.5
                )
                entry["direction_vs_theory"] = (
                    "AGREES" if (
                        (name == "range_bottom" and stratified_excess > 0)
                        or (name == "range_top" and stratified_excess < 0)
                    ) else "OPPOSES"
                )
        else:
            entry["note"] = (
                "no regime had at least 10 events and 20 baseline days, so a "
                "stratified comparison is not possible"
            )
        out["comparisons"][name] = entry

    out["answer"] = _location_answer(out["comparisons"])
    return out


def _location_answer(comparisons: dict[str, Any]) -> dict[str, Any]:
    bottom = comparisons.get("range_bottom", {})
    if bottom.get("status") != "OK":
        return {
            "verdict": "INSUFFICIENT_DATA",
            "statement": "not enough range-bottom observations to answer",
        }

    unconditional = bottom.get("excess_vs_unconditional_pct")
    matched = bottom.get("excess_vs_regime_matched_pct")
    adds = bottom.get("adds_information")
    agreement = bottom.get("direction_vs_theory")

    if matched is None:
        return {
            "verdict": "INSUFFICIENT_DATA",
            "statement": "no regime had enough observations for a stratified comparison",
        }

    p_value = bottom.get("p_value_vs_regime_matched", float("nan"))
    statement = (
        f"Being near a range bottom preceded returns {unconditional:+.2f}% relative to "
        f"the unconditional average, and {matched:+.2f}% relative to a REGIME-MATCHED "
        f"baseline (n={bottom.get('n')}, p={p_value:.3f}). "
    )

    if not adds:
        verdict = "NO_MARGINAL_INFORMATION"
        statement += (
            "Once the regime is known, range location adds nothing measurable: the "
            "apparent effect was the regime itself."
        )
    elif agreement == "OPPOSES":
        # An effect that is real but backwards is not support for the practice.
        verdict = "ADDS_INFORMATION_AGAINST_THEORY"
        statement += (
            "The location does carry information beyond the regime - but in the "
            "OPPOSITE direction to the conventional reading: price near a range bottom "
            "preceded returns BELOW the regime-matched baseline, not above it. This "
            "contradicts 'buy the range bottom' rather than supporting it."
        )
    else:
        verdict = "ADDS_INFORMATION"
        statement += (
            "The location carries information beyond the regime alone, in the "
            "direction conventional analysis expects."
        )
    return {
        "verdict": verdict, "statement": statement,
        "direction_vs_theory": agreement,
    }


def run_all(
    assets: list[Asset] | None = None, timeframe: Timeframe = Timeframe.D1,
    horizon: int = 7, step: int = 1,
) -> dict[str, Any]:
    assets = assets or Asset.tradables()
    results: dict[str, Any] = {}
    for asset in assets:
        try:
            frame = build_layered_features(asset, timeframe, step)
            results[asset.value] = {
                "layers": compare_layers(asset, timeframe, horizon, step, frame),
                "location_marginal_value": marginal_value_of_location(
                    asset, timeframe, horizon, step, frame
                ),
            }
        except Exception as exc:
            log.warning("marginal_value_failed", asset=asset.value, error=str(exc))
            results[asset.value] = {"status": "ERROR", "error": str(exc)[:250]}
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "timeframe": timeframe.value, "horizon_days": horizon,
        "assets": results,
    }

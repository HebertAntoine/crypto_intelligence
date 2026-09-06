"""Score calibration: which analysts actually predict anything?

For every domain score the system produces, this measures the relationship
between the score recorded at time t and the return that followed. It answers
the question the brief poses directly: "ETF score between +60 and +100 -> what
did BTC do at J+7, how often was it positive, on how many samples?"

Two hard rules:

  * No weight is ever modified automatically. This layer measures; changing the
    scoring config remains a human decision, and it must not be taken on a
    handful of observations.
  * Results are reported with sample size and split. A relationship visible
    only in-sample is an artefact, and saying so is the point of the module.

Scores come from two sources: reports actually produced by the system
(`reports` table), and - because those only start accumulating now - scores
RECONSTRUCTED historically from stored candles. Reconstruction is clearly
labelled as such, because it replays today's logic over old data rather than
recording what the system would have said at the time.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd

from ..core.enums import Asset
from ..db import repo
from ..engines.technical import indicators as ind
from ..history import store
from ..logging_setup import get_logger
from .etf_study import build_flow_series, build_price_frame, build_signals
from .stats import chronological_split, describe_returns, forward_returns, lagged_correlation

log = get_logger("research.calibration")

HORIZONS = [1, 3, 7, 14, 30]

# Score buckets used throughout the report, matching the scoring convention.
BUCKETS: list[tuple[str, float, float]] = [
    ("strong_negative", -100.0, -60.0),
    ("negative", -60.0, -25.0),
    ("slightly_negative", -25.0, -8.0),
    ("neutral", -8.0, 8.0),
    ("slightly_positive", 8.0, 25.0),
    ("positive", 25.0, 60.0),
    ("strong_positive", 60.0, 100.01),
]


def reconstruct_technical_score(asset: Asset) -> pd.Series:
    """Replay a simplified technical score over stored daily history.

    Uses only causal indicators (EMA, RSI, MACD are all backwards-looking), so
    the value at day t depends only on days <= t.

    This is a RECONSTRUCTION, not a recording: it applies today's logic to old
    data. It is useful for measuring whether the *logic* has predictive value,
    but it cannot tell us what the system would have said in 2019.
    """
    prices = build_price_frame(asset)
    if prices.empty or len(prices) < 220:
        return pd.Series(dtype=float)

    close, high, low, volume = prices["close"], prices["high"], prices["low"], prices["volume"]
    ema20, ema50, ema200 = ind.ema(close, 20), ind.ema(close, 50), ind.ema(close, 200)
    rsi = ind.rsi(close, 14)
    macd_line, macd_signal, _ = ind.macd(close)
    rel_volume = ind.relative_volume(volume, 20)
    adx = ind.adx(high, low, close, 14)

    score = pd.Series(0.0, index=prices.index)
    # Trend alignment, mirroring the live engine's logic.
    score += np.where((close > ema20) & (ema20 > ema50), 25.0, 0.0)
    score += np.where((close < ema20) & (ema20 < ema50), -25.0, 0.0)
    score += np.where(close > ema200, 20.0, -20.0)
    score += ((rsi - 50.0) * 0.6).clip(-20, 20)
    score += np.where(macd_line > macd_signal, 12.0, -12.0)
    score += np.where(adx > 25, np.sign(close - ema50) * 10.0, 0.0)
    score += (rel_volume.clip(0, 3) - 1.0) * 5.0

    return score.clip(-100, 100).rename("technical_score")


def reconstruct_etf_score(asset: Asset) -> pd.Series:
    """Replay the ETF score from stored flows, using the live scoring shape."""
    flows = build_flow_series(asset)
    if flows.empty:
        return pd.Series(dtype=float)

    signals = build_signals(flows)
    score = pd.Series(0.0, index=signals.index)
    score += np.where(signals["flow"] >= 300, 35.0, 0.0)
    score += np.where((signals["flow"] >= 80) & (signals["flow"] < 300), 18.0, 0.0)
    score += np.where(signals["flow"] <= -300, -35.0, 0.0)
    score += np.where((signals["flow"] <= -80) & (signals["flow"] > -300), -18.0, 0.0)
    score += (signals["ma5"].fillna(0) / 80.0 * 10.0).clip(-20, 20)
    score += (signals["acceleration"].fillna(0) / 100.0 * 15.0).clip(-15, 15)
    score += (signals["pos_streak"].fillna(0) * 3.0).clip(0, 15)
    score -= (signals["neg_streak"].fillna(0) * 3.0).clip(0, 15)
    return score.clip(-100, 100).rename("etf_score")


def reconstruct_derivatives_score(asset: Asset) -> pd.Series:
    """Funding-based derivatives score, replayed from stored funding history."""
    funding = store.load_derivatives(asset, "funding.rate")
    if funding.empty:
        return pd.Series(dtype=float)

    daily = funding.resample("1D").mean()
    daily.index = (
        daily.index.tz_convert("UTC") if daily.index.tz else daily.index.tz_localize("UTC")
    )
    # Extreme funding is treated as contrarian, exactly as the live engine does.
    score = pd.Series(0.0, index=daily.index)
    score += np.where(daily >= 0.0025, -30.0, 0.0)
    score += np.where((daily >= 0.0010) & (daily < 0.0025), -12.0, 0.0)
    score += np.where((daily <= -0.0015), 28.0, 0.0)
    score += np.where((daily <= -0.0010) & (daily > -0.0015), 12.0, 0.0)
    return score.clip(-100, 100).rename("derivatives_score")


RECONSTRUCTORS = {
    "technical": reconstruct_technical_score,
    "etf": reconstruct_etf_score,
    "derivatives": reconstruct_derivatives_score,
}


def calibrate_domain(asset: Asset, domain: str) -> dict[str, Any]:
    """Bucketed forward-return statistics for one domain score."""
    builder = RECONSTRUCTORS.get(domain)
    if builder is None:
        return {
            "asset": asset.value, "domain": domain, "available": False,
            "reason": f"No historical reconstruction available for '{domain}'. "
                      "It will be calibrated from live reports once enough accumulate.",
        }

    scores = builder(asset)
    if scores.empty:
        return {
            "asset": asset.value, "domain": domain, "available": False,
            "reason": f"UNAVAILABLE - no history to reconstruct the {domain} score",
        }

    prices = build_price_frame(asset)
    if prices.empty:
        return {
            "asset": asset.value, "domain": domain, "available": False,
            "reason": "UNAVAILABLE - no price history; run `make backfill`",
        }

    fwd = forward_returns(prices["close"], HORIZONS)
    joined = pd.concat([scores, fwd], axis=1).dropna(subset=[scores.name])
    joined = joined[joined.index.isin(fwd.index)]
    if len(joined) < 60:
        return {
            "asset": asset.value, "domain": domain, "available": False,
            "reason": f"INCONCLUSIVE - only {len(joined)} usable days",
        }

    buckets = []
    for label, low, high in BUCKETS:
        subset = joined[(joined[scores.name] >= low) & (joined[scores.name] < high)]
        if subset.empty:
            continue
        entry: dict[str, Any] = {
            "bucket": label, "score_range": [low, high], "n": len(subset), "horizons": {},
        }
        for h in HORIZONS:
            entry["horizons"][f"{h}d"] = describe_returns(subset[f"fwd_{h}"]).to_dict()
        buckets.append(entry)

    # Monotonicity is the real test: a useful score should produce increasing
    # forward returns as it rises. A high correlation with a non-monotonic
    # shape usually means one extreme bucket is doing all the work.
    correlations = {}
    for h in HORIZONS:
        r, p, n = lagged_correlation(joined[scores.name], joined[f"fwd_{h}"])
        correlations[f"{h}d"] = {
            "spearman_r": r, "p_value": p, "n": n,
            "significant": bool(p is not None and p < 0.05 and n >= 30),
        }

    monotonic = _monotonicity(buckets, "7d")
    split = chronological_split(joined.index)

    return {
        "asset": asset.value, "domain": domain, "available": True,
        "source": "reconstructed",
        "period": {
            "start": joined.index.min().isoformat(),
            "end": joined.index.max().isoformat(),
            "days": len(joined),
        },
        "buckets": buckets,
        "correlations": correlations,
        "monotonicity_7d": monotonic,
        "split": split.to_dict(),
        "caveat": (
            "Scores are RECONSTRUCTED by replaying current logic over historical "
            "candles. This measures whether the logic has predictive value, not "
            "what the system would have output at the time. Live-report "
            "calibration replaces this as reports accumulate."
        ),
    }


def _monotonicity(buckets: list[dict], horizon: str) -> dict[str, Any]:
    """Does mean forward return rise with the score bucket?"""
    points = [
        (b["score_range"][0], b["horizons"][horizon]["mean"], b["n"])
        for b in buckets
        if b["horizons"].get(horizon, {}).get("mean") is not None and b["n"] >= 10
    ]
    if len(points) < 3:
        return {"assessable": False, "reason": "fewer than 3 usable buckets"}

    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    rho, p_value = _spearman(xs, ys)
    return {
        "assessable": True,
        "buckets_used": len(points),
        "rank_correlation": rho,
        "p_value": p_value,
        "monotonic": bool(rho is not None and rho > 0.7),
        "interpretation": (
            "Mean return rises consistently with the score - the score orders outcomes."
            if rho is not None and rho > 0.7
            else "Mean return does NOT rise consistently with the score - the score does "
                 "not reliably order outcomes, whatever its correlation suggests."
        ),
    }


def _spearman(xs: list[float], ys: list[float]) -> tuple[float | None, float | None]:
    from scipy import stats as scipy_stats

    if len(xs) < 3 or np.std(xs) == 0 or np.std(ys) == 0:
        return None, None
    r, p = scipy_stats.spearmanr(xs, ys)
    return round(float(r), 4), round(float(p), 5)


def calibrate_from_live_reports(asset: Asset | None = None) -> dict[str, Any]:
    """Calibration from what the system ACTUALLY said, via stored reports.

    This is the ground truth version - no reconstruction, no replay. It only
    becomes meaningful once reports have accumulated, and it says so plainly
    until then.
    """
    reports = repo.list_reports(asset, limit=5000)
    outcomes = repo.get_outcomes(asset)

    if not outcomes:
        return {
            "available": False,
            "reports": len(reports),
            "reason": (
                "No evaluated outcomes yet. Live calibration needs reports that are old "
                "enough for their horizons to have elapsed - run the scheduler for a few "
                "days, then `make evaluate`."
            ),
        }

    index = {r["id"]: r for r in reports}
    by_domain: dict[str, dict[str, list[float]]] = {}

    for outcome in outcomes:
        report = index.get(outcome["report_id"])
        if not report or outcome["return_pct"] is None:
            continue
        for domain, card in (report.get("scores") or {}).items():
            if not isinstance(card, dict) or not card.get("available"):
                continue
            score = card.get("score")
            if score is None:
                continue
            bucket = _bucket_for(score)
            key = f"{domain}:{bucket}:{outcome['horizon']}"
            by_domain.setdefault(domain, {}).setdefault(key, []).append(outcome["return_pct"])

    results: dict[str, Any] = {}
    for domain, entries in by_domain.items():
        rows = []
        for key, values in entries.items():
            _, bucket, horizon = key.split(":")
            stats = describe_returns(values)
            rows.append({"bucket": bucket, "horizon": horizon, **stats.to_dict()})
        results[domain] = sorted(rows, key=lambda r: (r["horizon"], r["bucket"]))

    return {
        "available": True, "source": "live_reports",
        "reports": len(reports), "outcomes": len(outcomes),
        "domains": results,
        "note": (
            "Based on scores the system actually produced. Sample sizes will be small "
            "until the scheduler has run for a while - treat anything under 30 "
            "observations as descriptive only."
        ),
    }


def _bucket_for(score: float) -> str:
    for label, low, high in BUCKETS:
        if low <= score < high:
            return label
    return "neutral"


def run_full_calibration(assets: list[Asset] | None = None) -> dict[str, Any]:
    assets = assets or Asset.tradables()
    out: dict[str, Any] = {"reconstructed": {}, "live": calibrate_from_live_reports()}
    for asset in assets:
        out["reconstructed"][asset.value] = {
            domain: calibrate_domain(asset, domain) for domain in RECONSTRUCTORS
        }
    return out


def persist_calibration(payload: dict[str, Any]) -> int:
    from ..db.base import ResearchResultRow
    from ..db.session import session_scope

    written = 0
    now = datetime.now(UTC)
    with session_scope() as s:
        for asset_value, domains in (payload.get("reconstructed") or {}).items():
            for domain, result in domains.items():
                if not result.get("available"):
                    continue
                period = result.get("period") or {}
                start = pd.Timestamp(period["start"]).to_pydatetime() if period.get("start") else None
                end = pd.Timestamp(period["end"]).to_pydatetime() if period.get("end") else None
                for bucket in result.get("buckets", []):
                    for horizon, metrics in bucket["horizons"].items():
                        rid = f"calib:{asset_value}:{domain}:{bucket['bucket']}:{horizon}"[:80]
                        row = s.get(ResearchResultRow, rid)
                        if row is None:
                            row = ResearchResultRow(
                                id=rid, study="calibration", asset=asset_value,
                                signal=f"{domain}:{bucket['bucket']}", horizon=horizon,
                                split="reconstructed",
                            )
                            s.add(row)
                        row.sample_size = int(metrics.get("n", 0))
                        row.metrics = metrics
                        row.computed_at = now
                        row.data_start = start
                        row.data_end = end
                        written += 1
    return written

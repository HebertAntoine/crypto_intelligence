"""Does funding tell us anything once regime and momentum are held fixed?

The score built in LOT 1 assumed a contrarian reading: high funding means
crowded longs, therefore expect a pullback. LOT 3 measured the opposite - the
p95-100 funding bucket preceded POSITIVE forward returns on all three assets.
That is worth pinning down properly rather than leaving as a curiosity, because
if it holds it means the sign baked into the score is backwards.

Two confounds have to be removed first. Funding is high mostly when price has
been rising, so a raw funding/return relationship may just be momentum wearing
a costume. Conditioning on regime and on recent momentum separates "funding is
informative" from "funding is a slow proxy for trend".

Every bucket is reported, including the empty and the insignificant ones. The
FDR correction spans the whole grid, so a cell that survives here survives
against the full number of questions asked, not against its own p-value alone.

One methodological point that dominates everything else here. BTC, ETH and SOL
all drifted strongly upward over the sample, so testing a bucket's mean return
against ZERO mostly detects that drift: on the first pass every single funding
band looked "significantly positive" at 30 days, including the most negative
one. That is not funding information, it is buy-and-hold. The test that
actually answers the question is whether a band differs from the REST OF THE
SAMPLE under the same conditioning, so the shared drift cancels. Both numbers
are reported, but only the excess-vs-baseline test decides anything.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import ttest_ind

from ..core.enums import Asset
from ..engines.technical import indicators as ind
from ..logging_setup import get_logger
from .derivatives_study import daily_funding, trailing_rank
from .etf_study import build_price_frame
from .regime_conditioned import reconstruct_regime
from .stats import MIN_RELIABLE_SAMPLE, benjamini_hochberg, describe_returns, forward_returns

log = get_logger("research.funding_conditioned")

HORIZONS = [1, 3, 7, 14, 30]

# Percentile edges, matching the live FundingBand split so research and the
# runtime engine are talking about the same buckets.
BANDS: list[tuple[str, float, float]] = [
    ("EXTREME_NEGATIVE", 0.0, 5.0),
    ("NEGATIVE", 5.0, 25.0),
    ("NEUTRAL", 25.0, 75.0),
    ("POSITIVE", 75.0, 95.0),
    ("EXTREME_POSITIVE", 95.0, 100.01),
]

# An effect this small is not tradeable after costs, whatever its p-value.
NEGLIGIBLE_EFFECT_PCT = 0.5


def _momentum_bucket(close: pd.Series) -> pd.Series:
    """Recent trend, so funding is not simply re-measuring it."""
    change = close.pct_change(14) * 100
    buckets = pd.Series(index=close.index, dtype=object)
    buckets[change <= -10] = "FALLING"
    buckets[(change > -10) & (change < 10)] = "FLAT"
    buckets[change >= 10] = "RISING"
    return buckets


def build_frame(asset: Asset) -> pd.DataFrame:
    """Funding percentile, regime, momentum and forward returns on one index."""
    prices = build_price_frame(asset)
    if prices.empty or "close" not in prices:
        return pd.DataFrame()

    funding = daily_funding(asset, prices.index)
    if funding.dropna().empty:
        return pd.DataFrame()

    frame = pd.DataFrame(index=prices.index)
    frame["close"] = prices["close"]
    frame["funding"] = funding
    # Trailing rank only: today's percentile may not know tomorrow's funding.
    frame["funding_pct"] = trailing_rank(funding)
    frame["regime"] = reconstruct_regime(prices)
    frame["momentum"] = _momentum_bucket(prices["close"])
    frame["rsi"] = ind.rsi(prices["close"], 14)

    fwd = forward_returns(prices["close"], HORIZONS)
    for col in fwd.columns:
        frame[col] = fwd[col]
    return frame


def _cell(
    frame: pd.DataFrame, mask: pd.Series, horizon: int, baseline_mask: pd.Series | None = None
) -> dict[str, Any]:
    """Stats for one bucket, plus its excess over the comparable baseline.

    `mean` and `p_value` describe the bucket against zero and are kept only for
    reference. `excess_mean` and `excess_p_value` compare it against the other
    days in the same conditioning group via Welch's t-test, which is the
    comparison that isolates funding from the market's overall drift.
    """
    col = f"fwd_{horizon}"
    if col not in frame:
        return {"n": 0, "note": "horizon not computed"}
    values = frame.loc[mask, col].dropna()
    stats = describe_returns(values)
    result = stats.to_dict()
    result["horizon_days"] = horizon
    result["excess_mean"] = None
    result["excess_p_value"] = None
    result["baseline_mean"] = None
    result["baseline_n"] = 0

    if baseline_mask is None:
        return result
    baseline = frame.loc[baseline_mask & ~mask, col].dropna()
    result["baseline_n"] = len(baseline)
    if len(baseline) >= MIN_RELIABLE_SAMPLE and len(values) >= MIN_RELIABLE_SAMPLE:
        result["baseline_mean"] = round(float(baseline.mean()), 4)
        result["excess_mean"] = round(float(values.mean() - baseline.mean()), 4)
        # Welch: the two groups have no reason to share a variance, and the
        # extreme bands are far smaller than the neutral one.
        t_stat, p_value = ttest_ind(values, baseline, equal_var=False)
        result["excess_t_stat"] = round(float(t_stat), 3)
        result["excess_p_value"] = float(p_value)
    else:
        result["note"] = (
            f"excess not computed: bucket n={len(values)}, baseline n={len(baseline)}, "
            f"minimum {MIN_RELIABLE_SAMPLE} each"
        )
    return result


def analyse_funding_bands(asset: Asset) -> dict[str, Any]:
    """Forward returns per funding band, unconditionally and by regime/momentum."""
    frame = build_frame(asset)
    if frame.empty:
        return {
            "asset": asset.value, "status": "NO_DATA",
            "note": "no overlapping funding and price history",
        }

    usable = frame["funding_pct"].notna().sum()
    out: dict[str, Any] = {
        "asset": asset.value,
        "status": "OK",
        "observations": len(frame),
        "observations_with_percentile": int(usable),
        "period": {
            "start": str(frame.index.min())[:10], "end": str(frame.index.max())[:10],
        },
        "unconditional": {},
        "by_regime": {},
        "by_momentum": {},
    }

    tests: list[tuple[str, float | None]] = []

    # 1. Unconditional: the LOT 3 result, recomputed on trailing percentiles.
    has_pct = frame["funding_pct"].notna()
    for band, low, high in BANDS:
        mask = has_pct & (frame["funding_pct"] >= low) & (frame["funding_pct"] < high)
        cells = {}
        for horizon in HORIZONS:
            cell = _cell(frame, mask, horizon, baseline_mask=has_pct)
            cells[f"{horizon}d"] = cell
            tests.append((f"uncond|{band}|{horizon}d", cell.get("excess_p_value")))
        out["unconditional"][band] = cells

    # 2. Conditioned on regime - is the funding effect just the trend?
    for regime in ("STRONGLY_BULLISH", "BULLISH", "NEUTRAL", "BEARISH", "STRONGLY_BEARISH"):
        regime_mask = frame["regime"] == regime
        if regime_mask.sum() < MIN_RELIABLE_SAMPLE:
            out["by_regime"][regime] = {
                "status": "INSUFFICIENT_DATA",
                "n": int(regime_mask.sum()),
                "note": f"{int(regime_mask.sum())} days, below the {MIN_RELIABLE_SAMPLE} minimum",
            }
            continue
        bands_here: dict[str, Any] = {}
        for band, low, high in BANDS:
            mask = regime_mask & (frame["funding_pct"] >= low) & (frame["funding_pct"] < high)
            cells = {}
            for horizon in HORIZONS:
                # Baseline is the same regime, so the comparison holds trend fixed.
                cell = _cell(frame, mask, horizon, baseline_mask=regime_mask)
                cells[f"{horizon}d"] = cell
                tests.append((f"regime|{regime}|{band}|{horizon}d", cell.get("excess_p_value")))
            bands_here[band] = cells
        out["by_regime"][regime] = {"status": "OK", "n": int(regime_mask.sum()), "bands": bands_here}

    # 3. Conditioned on momentum - the same question, different control.
    for momentum in ("RISING", "FLAT", "FALLING"):
        mom_mask = frame["momentum"] == momentum
        if mom_mask.sum() < MIN_RELIABLE_SAMPLE:
            out["by_momentum"][momentum] = {
                "status": "INSUFFICIENT_DATA", "n": int(mom_mask.sum()),
            }
            continue
        bands_here = {}
        for band, low, high in BANDS:
            mask = mom_mask & (frame["funding_pct"] >= low) & (frame["funding_pct"] < high)
            cells = {}
            for horizon in HORIZONS:
                cell = _cell(frame, mask, horizon, baseline_mask=mom_mask)
                cells[f"{horizon}d"] = cell
                tests.append((f"momentum|{momentum}|{band}|{horizon}d", cell.get("excess_p_value")))
            bands_here[band] = cells
        out["by_momentum"][momentum] = {
            "status": "OK", "n": int(mom_mask.sum()), "bands": bands_here
        }

    # FDR across the entire grid, not per section.
    labels = [label for label, _ in tests]
    p_values = [p for _, p in tests]
    survives = benjamini_hochberg(p_values, alpha=0.05)
    out["multiple_testing"] = {
        "hypotheses_tested": len(tests),
        "raw_significant": sum(1 for p in p_values if p is not None and p < 0.05),
        "survives_fdr": sum(survives),
        "method": (
            "Benjamini-Hochberg, alpha=0.05, across every cell. The p-values corrected "
            "are those of the EXCESS return versus the same-conditioning baseline, not "
            "of the bucket against zero - the latter mostly measures the market's drift."
        ),
        "survivors": [label for label, ok in zip(labels, survives, strict=True) if ok],
    }
    out["survivor_detail"] = _survivor_detail(out, labels, survives, p_values)
    stability = episode_analysis(asset, "EXTREME_POSITIVE", 30)
    out["stability_check"] = stability
    out["conclusion"] = _conclude(asset, out, stability)
    return out


def _survivor_detail(
    out: dict[str, Any], labels: list[str], survives: list[bool], p_values: list[float | None]
) -> list[dict[str, Any]]:
    """Effect sizes for surviving cells, so significance is not read alone."""
    detail = []
    for label, ok, p in zip(labels, survives, p_values, strict=True):
        if not ok:
            continue
        parts = label.split("|")
        cell: dict[str, Any] | None = None
        if parts[0] == "uncond":
            cell = out["unconditional"].get(parts[1], {}).get(parts[2])
        elif parts[0] == "regime":
            section = out["by_regime"].get(parts[1], {})
            cell = section.get("bands", {}).get(parts[2], {}).get(parts[3])
        elif parts[0] == "momentum":
            section = out["by_momentum"].get(parts[1], {})
            cell = section.get("bands", {}).get(parts[2], {}).get(parts[3])
        if not cell:
            continue
        excess = cell.get("excess_mean")
        if excess is None:
            continue
        negligible = abs(excess) < NEGLIGIBLE_EFFECT_PCT
        detail.append({
            "cell": label, "n": cell.get("n"),
            "mean_return_pct": cell.get("mean"),
            "baseline_mean_pct": cell.get("baseline_mean"),
            "excess_vs_baseline_pct": excess,
            "win_rate": cell.get("win_rate"), "excess_p_value": p,
            "effect_size_verdict": "NEGLIGIBLE" if negligible else "MATERIAL",
            "note": (
                f"beats its baseline by {excess:+.2f}%, below the "
                f"{NEGLIGIBLE_EFFECT_PCT}% floor where costs matter"
                if negligible else
                f"forward return {cell.get('mean'):+.2f}% versus a baseline of "
                f"{cell.get('baseline_mean'):+.2f}% over the same days: "
                f"{excess:+.2f}% excess on {cell.get('n')} observations"
            ),
        })
    return detail


def _conclude(
    asset: Asset, out: dict[str, Any], stability: dict[str, Any] | None = None
) -> dict[str, Any]:
    """State the contrarian question directly, including when the answer is no.

    A cell that survives FDR is not yet a finding. The funding bands persist for
    a day or two at a time and the forward windows overlap, so the significance
    test runs on far fewer independent observations than the row count suggests.
    The per-year breakdown is the tiebreaker: an effect that appears in one year
    and reverses in the others is an episode, not a relationship.
    """
    survivors = out["multiple_testing"]["survivors"]
    material = [d for d in out["survivor_detail"] if d["effect_size_verdict"] == "MATERIAL"]

    extreme_pos = out["unconditional"].get("EXTREME_POSITIVE", {})
    directions = []
    for horizon in HORIZONS:
        cell = extreme_pos.get(f"{horizon}d", {})
        # Excess, not raw: the raw mean is positive in every band because the
        # market rose, which says nothing about funding.
        if cell.get("excess_mean") is not None and cell.get("n", 0) >= MIN_RELIABLE_SAMPLE:
            directions.append(cell["excess_mean"])

    contrarian_verdict = "INCONCLUSIVE"
    contrarian_note = "not enough observations in the extreme-funding band to judge"
    if directions:
        mean_dir = float(np.mean(directions))
        survived_extreme = [
            s for s in survivors if s.startswith("uncond|EXTREME_POSITIVE")
        ]

        # Stability gate: refuse to call anything CONTRADICTED or SUPPORTED when
        # the effect lives in one era. This is the same trap the LOT 3 IC
        # decomposition exposed for the technical score.
        if stability and stability.get("status") == "OK":
            years_total = stability.get("years_covered", 0)
            years_positive = stability.get("years_with_positive_excess", 0)
            effective = stability.get("effective_independent_windows", 0)
            concentrated = stability.get("independence_verdict") == "CONCENTRATED"
            majority = years_positive >= years_total * 0.7 if years_total else False

            if concentrated or not majority or effective < 20:
                worst = min(
                    (v.get("excess_pct") for v in stability.get("by_year", {}).values()
                     if v.get("excess_pct") is not None),
                    default=None,
                )
                return {
                    "asset": asset.value,
                    "contrarian_hypothesis": "INCONCLUSIVE",
                    "contrarian_note": (
                        f"Extreme funding days beat their baseline by {mean_dir:+.2f}% on "
                        f"average, and {len(survived_extreme)} horizon(s) survive FDR, but the "
                        f"effect is not stable: positive in only {years_positive} of "
                        f"{years_total} years"
                        + (f" (worst year {worst:+.2f}%)" if worst is not None else "")
                        + f", spread over {stability.get('distinct_episodes')} short episodes "
                        f"leaving roughly {effective} independent windows. The significance "
                        "test assumed independence that overlapping forward windows do not "
                        "provide, so it overstates the evidence. Neither the contrarian "
                        "reading nor its opposite is established."
                    ),
                    "stability_verdict": stability.get("independence_verdict"),
                    "years_with_positive_excess": f"{years_positive}/{years_total}",
                    "effective_independent_windows": effective,
                    "cells_surviving_fdr": len(survivors),
                    "cells_with_material_effect": len(material),
                    "summary": (
                        f"{out['multiple_testing']['hypotheses_tested']} cells tested, "
                        f"{out['multiple_testing']['raw_significant']} significant before "
                        f"correction, {len(survivors)} after FDR - but the headline cells fail "
                        "the year-by-year stability check."
                    ),
                    "action": (
                        "No score change. The existing contrarian sign is not vindicated "
                        "either; it is simply untested by this study. Recommend leaving the "
                        "funding term as-is and marking it as carrying no measured edge."
                    ),
                }

        if not survived_extreme:
            contrarian_verdict = "NO_EFFECT"
            contrarian_note = (
                f"days with extreme funding beat the rest of the sample by "
                f"{mean_dir:+.2f}% on average, but no horizon survives FDR correction. "
                "Funding does not separate itself from the market's baseline drift."
            )
        elif mean_dir > 0.2:
            contrarian_verdict = "CONTRADICTED"
            contrarian_note = (
                f"high funding preceded returns {mean_dir:+.2f}% ABOVE the same-period "
                "baseline, surviving FDR. The contrarian sign assumed by the score is "
                "not what the data shows."
            )
        elif mean_dir < -0.2:
            contrarian_verdict = "SUPPORTED"
            contrarian_note = (
                f"high funding preceded returns {mean_dir:+.2f}% BELOW baseline, "
                "consistent with the contrarian assumption."
            )
        else:
            contrarian_verdict = "NO_EFFECT"
            contrarian_note = (
                f"extreme funding days differ from baseline by {mean_dir:+.2f}%, "
                "indistinguishable from nothing in either direction."
            )

    return {
        "asset": asset.value,
        "contrarian_hypothesis": contrarian_verdict,
        "contrarian_note": contrarian_note,
        "cells_surviving_fdr": len(survivors),
        "cells_with_material_effect": len(material),
        "summary": (
            f"{out['multiple_testing']['hypotheses_tested']} cells tested, "
            f"{out['multiple_testing']['raw_significant']} significant before correction, "
            f"{len(survivors)} after FDR, {len(material)} of those with an excess "
            f"larger than {NEGLIGIBLE_EFFECT_PCT}%. All figures are excess over the "
            f"same-conditioning baseline, not raw returns."
        ),
        "action": (
            "No score change is justified by this study alone; a sign flip needs the "
            "effect to survive out-of-sample as well."
            if not material else
            "Effect survives correction and is material - worth carrying into the "
            "candidate weights for out-of-sample testing, not into the live score directly."
        ),
    }


def run_all(assets: list[Asset] | None = None) -> dict[str, Any]:
    assets = assets or Asset.tradables()
    results = {a.value: analyse_funding_bands(a) for a in assets}
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "horizons_days": HORIZONS,
        "assets": results,
    }


def episode_analysis(asset: Asset, band: str = "EXTREME_POSITIVE", horizon: int = 30) -> dict[str, Any]:
    """Are these independent observations, or a few long episodes?

    A funding band persists for days at a time, so 118 "observations" may be a
    dozen episodes seen repeatedly. Overlapping 30-day forward windows make it
    worse: consecutive days share almost all of their forward return. The
    t-test assumes independence and gets none of it, so a striking p-value can
    rest on very few genuinely distinct events.

    This counts the episodes, and checks whether the effect shows up across
    years or comes from one era.
    """
    frame = build_frame(asset)
    if frame.empty:
        return {"asset": asset.value, "status": "NO_DATA"}

    bounds = {name: (low, high) for name, low, high in BANDS}
    if band not in bounds:
        return {"asset": asset.value, "status": "UNKNOWN_BAND"}
    low, high = bounds[band]

    mask = frame["funding_pct"].notna() & (frame["funding_pct"] >= low) & (frame["funding_pct"] < high)
    col = f"fwd_{horizon}"

    # Consecutive runs of in-band days = one episode.
    groups = (mask != mask.shift()).cumsum()[mask]
    episodes: list[dict[str, Any]] = []
    for _, idx in frame[mask].groupby(groups).groups.items():
        window = frame.loc[idx]
        returns = window[col].dropna()
        episodes.append({
            "start": str(window.index.min())[:10],
            "end": str(window.index.max())[:10],
            "days": len(window),
            "mean_forward_return_pct": round(float(returns.mean()), 2) if len(returns) else None,
        })

    baseline = frame.loc[frame["funding_pct"].notna() & ~mask, col].dropna()
    by_year: dict[str, Any] = {}
    for year, chunk in frame[mask].groupby(frame[mask].index.year):
        returns = chunk[col].dropna()
        base_year = baseline[baseline.index.year == year]
        if len(returns) == 0:
            continue
        by_year[str(year)] = {
            "days_in_band": len(chunk),
            "mean_return_pct": round(float(returns.mean()), 2),
            "baseline_mean_pct": round(float(base_year.mean()), 2) if len(base_year) else None,
            "excess_pct": (
                round(float(returns.mean() - base_year.mean()), 2) if len(base_year) else None
            ),
        }

    excesses = [y["excess_pct"] for y in by_year.values() if y["excess_pct"] is not None]
    positive_years = sum(1 for e in excesses if e > 0)
    episode_returns = [e["mean_forward_return_pct"] for e in episodes if e["mean_forward_return_pct"] is not None]

    # Effective sample: overlapping h-day windows carry roughly n/h independent
    # draws. This is the number the p-value should have been built on.
    effective_n = round(int(mask.sum()) / horizon, 1)

    verdict = "CONCENTRATED"
    if len(episodes) >= 10 and len(excesses) >= 3 and positive_years >= len(excesses) * 0.7:
        verdict = "PERSISTENT"
    elif len(episodes) >= 6 and positive_years >= len(excesses) * 0.6:
        verdict = "MODERATELY_PERSISTENT"

    return {
        "asset": asset.value,
        "band": band,
        "horizon_days": horizon,
        "status": "OK",
        "days_in_band": int(mask.sum()),
        "distinct_episodes": len(episodes),
        "effective_independent_windows": effective_n,
        "median_episode_length_days": (
            round(float(np.median([e["days"] for e in episodes])), 1) if episodes else None
        ),
        "episodes_positive": sum(1 for r in episode_returns if r and r > 0),
        "episodes_measured": len(episode_returns),
        "years_covered": len(by_year),
        "years_with_positive_excess": positive_years,
        "by_year": by_year,
        "episodes": episodes[-12:],
        "independence_verdict": verdict,
        "caveat": (
            f"{int(mask.sum())} in-band days form only {len(episodes)} distinct episodes, and "
            f"{horizon}-day forward windows overlap heavily, leaving roughly {effective_n} "
            "independent observations. The reported p-value assumes independence it does "
            "not have and is optimistic; treat the effect as suggestive, not established."
        ),
    }


def run_episode_checks(assets: list[Asset] | None = None) -> dict[str, Any]:
    assets = assets or Asset.tradables()
    return {
        a.value: {
            "EXTREME_POSITIVE": episode_analysis(a, "EXTREME_POSITIVE", 30),
            "EXTREME_NEGATIVE": episode_analysis(a, "EXTREME_NEGATIVE", 30),
        }
        for a in assets
    }

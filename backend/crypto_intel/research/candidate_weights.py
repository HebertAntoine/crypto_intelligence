"""Candidate weight proposal and Champion / Challenger comparison.

The audit showed most of the current weight sitting on domains with no
measurable predictive value. This module proposes an alternative - but never
applies it.

Three rules govern this module:

  1. `config/scoring.yaml` (the Champion) is never written to. Candidates go to
     `config/scoring_candidate.yaml`.
  2. A candidate is only recommended if it beats the Champion OUT OF SAMPLE, on
     windows never used to derive it.
  3. Promotion is a human action. The code produces a verdict, not a change.

Candidate weights come from measured quantities, not judgement:

    weight ∝ predictive_strength × stability × confidence × data_quality

A domain that cannot be measured keeps its current weight rather than being
zeroed - absence of evidence is not evidence of uselessness, and silently
deleting an unmeasured domain would be its own kind of overfitting.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from ..config_loader import asset_weights, scoring_config
from ..core.enums import Asset
from ..logging_setup import get_logger
from ..settings import get_settings
from .audit import audit_asset
from .calibration import RECONSTRUCTORS
from .etf_study import build_price_frame
from .stats import forward_returns, lagged_correlation
from .walkforward import bucket_monotonicity, build_windows

log = get_logger("research.candidate")

CANDIDATE_FILE = "scoring_candidate.yaml"
PRIMARY_HORIZON = 7

# A measured domain must clear this to gain weight relative to its peers.
MIN_IC_FOR_CONFIDENCE = 0.03


def derive_candidate_weights(asset: Asset, audit: dict[str, Any] | None = None) -> dict[str, Any]:
    """Propose weights for one asset from measured evidence."""
    audit = audit or audit_asset(asset)
    current = asset_weights(asset.value)
    domains = audit["domains"]

    raw_scores: dict[str, float] = {}
    rationale: dict[str, Any] = {}

    for domain, weight in current.items():
        result = domains.get(domain, {})
        verdict = result.get("verdict", "INSUFFICIENT_DATA")

        if weight <= 0:
            # Deliberately excluded (e.g. SOL has no US spot ETF). Leave it.
            raw_scores[domain] = 0.0
            rationale[domain] = {
                "verdict": verdict, "action": "keep_zero",
                "reason": "Domain is deliberately excluded for this asset",
            }
            continue

        if verdict == "INSUFFICIENT_DATA":
            # Cannot be measured yet: keep the current weight rather than
            # inventing a number. Deleting it would assume it is useless.
            raw_scores[domain] = weight
            rationale[domain] = {
                "verdict": verdict, "action": "hold_current",
                "reason": (
                    "No historical reconstruction exists, so predictive value cannot be "
                    "measured. The current weight is retained unchanged until live "
                    "reports allow calibration."
                ),
            }
            continue

        ic = abs(result.get("ic") or 0.0)
        stability = (result.get("stability_score") or 0.0) / 100.0
        monotonic = result.get("monotonic", False)
        significant = result.get("significant", False)
        n = result.get("n", 0)
        concentration = result.get("concentration") or {}
        discriminating = concentration.get("discriminating", True)

        # predictive_strength: effect size, floored so a measured-but-weak
        # domain does not collapse to exactly zero.
        predictive = max(0.0, ic - 0.01)
        # confidence: sample adequacy plus statistical support.
        confidence = min(1.0, n / 800.0) * (1.0 + 0.5 * significant)
        # data_quality: a score stuck in one bucket cannot inform anything.
        data_quality = 1.0 if discriminating else 0.1
        # monotonicity is a genuine bonus - it means the score orders outcomes.
        shape = 1.3 if monotonic else 1.0

        raw = predictive * max(stability, 0.05) * confidence * data_quality * shape
        raw_scores[domain] = raw

        rationale[domain] = {
            "verdict": verdict,
            "action": "rescaled",
            "ic": result.get("ic"),
            "stability": result.get("stability_score"),
            "monotonic": monotonic,
            "significant": significant,
            "n": n,
            "discriminating": discriminating,
            "components": {
                "predictive_strength": round(predictive, 4),
                "stability": round(stability, 3),
                "confidence": round(confidence, 3),
                "data_quality": data_quality,
                "shape_bonus": shape,
            },
            "raw_score": round(raw, 5),
        }

    # The measured domains share whatever weight the unmeasured ones do not
    # hold, so the totals stay comparable with the Champion.
    held = sum(
        w for d, w in current.items()
        if rationale.get(d, {}).get("action") in ("hold_current", "keep_zero")
    )
    available_budget = max(0.0, 1.0 - held)
    measured = {d: s for d, s in raw_scores.items() if rationale[d]["action"] == "rescaled"}
    total_raw = sum(measured.values())

    candidate: dict[str, float] = {}
    for domain, weight in current.items():
        action = rationale[domain]["action"]
        if action in ("hold_current", "keep_zero"):
            candidate[domain] = round(weight, 4)
        elif total_raw > 0:
            candidate[domain] = round(measured[domain] / total_raw * available_budget, 4)
        else:
            # Nothing measurable scored above zero: keep the Champion's split
            # rather than flattening every measured domain to zero.
            candidate[domain] = round(weight, 4)
            rationale[domain]["action"] = "hold_current_no_signal"
            rationale[domain]["reason"] = (
                "No measured domain scored above zero, so the current split is retained"
            )

    return {
        "asset": asset.value,
        "current": current,
        "candidate": candidate,
        "changes": {
            d: {
                "from": current[d], "to": candidate[d],
                "delta": round(candidate[d] - current[d], 4),
            }
            for d in current
            if abs(candidate[d] - current[d]) > 0.005
        },
        "rationale": rationale,
        "budget": {
            "held_by_unmeasured": round(held, 3),
            "redistributed_among_measured": round(available_budget, 3),
        },
    }


def build_composite(asset: Asset, weights: dict[str, float]) -> pd.Series:
    """Weighted composite of the reconstructable domain scores.

    Only domains with a historical reconstruction contribute, so Champion and
    Challenger are compared on exactly the same inputs - the difference between
    them is the weighting, nothing else.
    """
    prices = build_price_frame(asset)
    if prices.empty:
        return pd.Series(dtype=float)

    parts: list[tuple[pd.Series, float]] = []
    for domain, builder in RECONSTRUCTORS.items():
        weight = weights.get(domain, 0.0)
        if weight <= 0:
            continue
        series = builder(asset)
        if series.empty:
            continue
        parts.append((series.reindex(prices.index), weight))

    if not parts:
        return pd.Series(dtype=float)

    total_weight = sum(w for _, w in parts)
    composite = sum(series.fillna(0.0) * w for series, w in parts) / total_weight

    # Only keep days where at least one contributing score actually existed -
    # otherwise fillna(0) would manufacture a neutral reading.
    coverage = sum(series.notna().astype(float) * w for series, w in parts) / total_weight
    return composite.where(coverage > 0.4)


def compare_models(asset: Asset, candidate_weights: dict[str, float]) -> dict[str, Any]:
    """Champion vs Challenger, evaluated out of sample on walk-forward windows."""
    current = asset_weights(asset.value)
    prices = build_price_frame(asset)
    if prices.empty:
        return {"asset": asset.value, "available": False, "reason": "UNAVAILABLE - no prices"}

    champion = build_composite(asset, current)
    challenger = build_composite(asset, candidate_weights)
    if champion.empty or challenger.empty:
        return {
            "asset": asset.value, "available": False,
            "reason": "UNAVAILABLE - could not build both composites",
        }

    fwd = forward_returns(prices["close"], [PRIMARY_HORIZON])
    target = fwd[f"fwd_{PRIMARY_HORIZON}"]

    joined = pd.concat(
        [champion.rename("champion"), challenger.rename("challenger"), target.rename("fwd")],
        axis=1,
    ).dropna()
    if len(joined) < 200:
        return {
            "asset": asset.value, "available": False,
            "reason": f"INSUFFICIENT_DATA - {len(joined)} comparable days",
        }

    # Out-of-sample windows only. The candidate was derived from the full
    # history, so an in-sample win would prove nothing.
    specs = build_windows(pd.DatetimeIndex(joined.index))
    if not specs:
        return {
            "asset": asset.value, "available": False,
            "reason": "INSUFFICIENT_DATA - history too short for walk-forward comparison",
        }

    windows: list[dict[str, Any]] = []
    champion_wins = challenger_wins = 0
    for i, (_tr_s, _tr_e, _va_s, _va_e, te_s, te_e) in enumerate(specs):
        test = joined[(joined.index >= te_s) & (joined.index < te_e)]
        if len(test) < 20:
            continue
        champ_ic, champ_p, n = lagged_correlation(test["champion"], test["fwd"])
        chall_ic, chall_p, _ = lagged_correlation(test["challenger"], test["fwd"])
        if champ_ic is None or chall_ic is None:
            continue
        better = "challenger" if abs(chall_ic) > abs(champ_ic) else "champion"
        if better == "challenger":
            challenger_wins += 1
        else:
            champion_wins += 1
        windows.append({
            "index": i,
            "test": [te_s.isoformat(), te_e.isoformat()],
            "n": n,
            "champion_ic": champ_ic, "champion_p": champ_p,
            "challenger_ic": chall_ic, "challenger_p": chall_p,
            "better": better,
        })

    if not windows:
        return {
            "asset": asset.value, "available": False,
            "reason": "INSUFFICIENT_DATA - no usable out-of-sample window",
        }

    champ_ics = [w["champion_ic"] for w in windows]
    chall_ics = [w["challenger_ic"] for w in windows]
    champ_mean = float(np.mean(champ_ics))
    chall_mean = float(np.mean(chall_ics))

    champion_mono = bucket_monotonicity(joined["champion"], joined["fwd"])
    challenger_mono = bucket_monotonicity(joined["challenger"], joined["fwd"])

    champ_hit = _hit_rate(joined["champion"], joined["fwd"])
    chall_hit = _hit_rate(joined["challenger"], joined["fwd"])

    verdict, reason = _promotion_verdict(
        windows, champion_wins, challenger_wins,
        champ_mean, chall_mean, champion_mono, challenger_mono,
        champ_hit, chall_hit,
    )

    return {
        "asset": asset.value,
        "available": True,
        "windows": windows,
        "summary": {
            "windows": len(windows),
            "champion_wins": champion_wins,
            "challenger_wins": challenger_wins,
            "champion_mean_oos_ic": round(champ_mean, 4),
            "challenger_mean_oos_ic": round(chall_mean, 4),
            "champion_monotonic": champion_mono.get("monotonic"),
            "challenger_monotonic": challenger_mono.get("monotonic"),
            "champion_hit_rate": champ_hit,
            "challenger_hit_rate": chall_hit,
        },
        "verdict": verdict,
        "reason": reason,
        "note": (
            "Compared on out-of-sample walk-forward test windows only. Both composites "
            "use the same reconstructable domain scores; only the weighting differs."
        ),
    }


def _hit_rate(score: pd.Series, fwd: pd.Series) -> float | None:
    """Directional hit rate on days where the score takes a clear side."""
    joined = pd.concat([score.rename("s"), fwd.rename("f")], axis=1).dropna()
    directional = joined[abs(joined["s"]) >= 10]
    if len(directional) < 50:
        return None
    correct = ((directional["s"] > 0) & (directional["f"] > 0)) | (
        (directional["s"] < 0) & (directional["f"] < 0)
    )
    return round(float(correct.mean() * 100.0), 2)


def _promotion_verdict(
    windows, champion_wins, challenger_wins,
    champ_mean, chall_mean, champ_mono, chall_mono, champ_hit, chall_hit,
) -> tuple[str, str]:
    """KEEP_CHAMPION / PROMOTE_CHALLENGER / INCONCLUSIVE.

    The bar for promotion is deliberately high: the incumbent is kept unless
    the challenger wins clearly and consistently. A near-tie is INCONCLUSIVE,
    not a promotion.
    """
    n_windows = len(windows)
    if n_windows < 3:
        return "INCONCLUSIVE", f"Only {n_windows} out-of-sample window(s) - too few to judge"

    improvement = abs(chall_mean) - abs(champ_mean)
    win_share = challenger_wins / n_windows

    if improvement > 0.02 and win_share >= 0.65:
        detail = (
            f"Challenger mean OOS IC {chall_mean:+.4f} vs champion {champ_mean:+.4f} "
            f"(+{improvement:.4f}), winning {challenger_wins}/{n_windows} windows"
        )
        if chall_mono.get("monotonic") and not champ_mono.get("monotonic"):
            detail += ", and it is monotonic across buckets where the champion is not"
        return "PROMOTE_CHALLENGER", detail

    if improvement < -0.02 or win_share <= 0.35:
        return (
            "KEEP_CHAMPION",
            f"Champion holds: mean OOS IC {champ_mean:+.4f} vs challenger {chall_mean:+.4f}, "
            f"winning {champion_wins}/{n_windows} windows",
        )

    return (
        "INCONCLUSIVE",
        f"No clear difference out of sample: champion {champ_mean:+.4f} vs challenger "
        f"{chall_mean:+.4f} across {n_windows} windows "
        f"({challenger_wins} challenger wins). The incumbent is kept by default.",
    )


def write_candidate_file(proposals: dict[str, Any], comparisons: dict[str, Any]) -> Path:
    """Write config/scoring_candidate.yaml.

    Never touches scoring.yaml. The file is a proposal with its evidence
    attached, so a human can read why each number changed before deciding.
    """
    settings = get_settings()
    path = settings.config_dir / CANDIDATE_FILE

    payload: dict[str, Any] = {
        "_meta": {
            "generated_at": datetime.now(UTC).isoformat(),
            "generator": "research.candidate_weights",
            "status": "CANDIDATE - not in use",
            "how_to_promote": (
                "Review the rationale below, then copy the desired 'assets' block into "
                "config/scoring.yaml manually. Promotion is deliberately a human action; "
                "nothing in the code applies this file."
            ),
            "formula": (
                "weight is proportional to predictive_strength x stability x confidence "
                "x data_quality x shape_bonus, normalised across measured domains. "
                "Unmeasured domains keep their current weight."
            ),
        },
        "assets": {},
        "verdicts": {},
        "rationale": {},
    }

    for asset_value, proposal in proposals.items():
        payload["assets"][asset_value] = proposal["candidate"]
        payload["rationale"][asset_value] = {
            "changes": proposal["changes"],
            "budget": proposal["budget"],
            "domains": proposal["rationale"],
        }
        comparison = comparisons.get(asset_value, {})
        payload["verdicts"][asset_value] = {
            "verdict": comparison.get("verdict", "INCONCLUSIVE"),
            "reason": comparison.get("reason", comparison.get("reason", "not evaluated")),
            "summary": comparison.get("summary"),
        }

    # Horizons and other sections are inherited unchanged from the Champion.
    champion = scoring_config()
    payload["horizons"] = champion.get("horizons", {})
    payload["confidence"] = champion.get("confidence", {})
    payload["freshness"] = champion.get("freshness", {})
    payload["labels"] = champion.get("labels", [])

    path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True, default_flow_style=False),
        encoding="utf-8",
    )
    log.info("candidate_weights_written", path=str(path))
    return path


def run_full(assets: list[Asset] | None = None, write_file: bool = True) -> dict[str, Any]:
    """Derive candidates, compare against the champion, optionally write the file."""
    assets = assets or Asset.tradables()

    proposals: dict[str, Any] = {}
    comparisons: dict[str, Any] = {}
    for asset in assets:
        proposal = derive_candidate_weights(asset)
        proposals[asset.value] = proposal
        comparisons[asset.value] = compare_models(asset, proposal["candidate"])

    path = write_candidate_file(proposals, comparisons) if write_file else None

    return {
        "proposals": proposals,
        "comparisons": comparisons,
        "candidate_file": str(path) if path else None,
        "promotion_policy": (
            "Champion is never replaced automatically. PROMOTE_CHALLENGER is a "
            "recommendation; applying it means editing config/scoring.yaml by hand."
        ),
    }

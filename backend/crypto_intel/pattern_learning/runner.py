"""Run the independent pattern-comparison study on stored OHLCV history."""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..core.enums import Asset, Timeframe
from ..history import store
from ..structure.history_scan import scan_cached
from .consensus import compare_with_lmw
from .lmw import TEMPLATE_BY_PATTERN, scan_lmw

DEFAULT_TIMEFRAMES = (Timeframe.D1, Timeframe.H4, Timeframe.H1)


def run_consensus_study(
    assets: list[Asset] | None = None,
    timeframes: list[Timeframe] | None = None,
) -> dict[str, Any]:
    """Compare both detectors without looking at subsequent returns."""
    selected_assets = assets or Asset.tradables()
    selected_timeframes = timeframes or list(DEFAULT_TIMEFRAMES)
    results: dict[str, Any] = {}
    totals: Counter[str] = Counter()

    for timeframe in selected_timeframes:
        for asset in selected_assets:
            key = f"{asset.value}_{timeframe.value}"
            frame = store.load_candles(asset, timeframe)
            if frame.empty:
                results[key] = {"status": "NO_DATA"}
                continue
            ours = scan_cached(asset.value, timeframe, frame)
            lmw = scan_lmw(frame["close"])
            report = compare_with_lmw(ours, lmw)
            summary = report.summary()
            pattern_counts = Counter(
                item.pattern.value for item in report.agreements
            )
            results[key] = {
                "status": "OK",
                "asset": asset.value,
                "timeframe": timeframe.value,
                "bars": len(frame),
                "period": {
                    "start": frame.index.min().isoformat(),
                    "end": frame.index.max().isoformat(),
                },
                "our_patterns": len(ours),
                "lmw_patterns": len(lmw),
                "agreements_by_pattern": dict(sorted(pattern_counts.items())),
                "quality_gate": {
                    "policy": "require independent agreement",
                    "raw_candidates": summary["comparable_ours"],
                    "promoted": summary["independent_agreements"],
                    "rejected": summary["ours_only"],
                    "promotion_rate_pct": summary["agreement_rate_pct"],
                    "independent_confirmation_share_of_promoted_pct": (
                        100.0 if summary["independent_agreements"] else None
                    ),
                    "edge_claim": False,
                },
                **report.to_dict(),
            }
            for field in (
                "independent_agreements",
                "ours_only",
                "lmw_only",
                "not_comparable_ours",
                "comparable_ours",
            ):
                totals[field] += int(summary[field])

    comparable = totals["comparable_ours"]
    total_summary: dict[str, Any] = dict(totals)
    total_summary["agreement_rate_pct"] = (
        round(totals["independent_agreements"] / comparable * 100.0, 1)
        if comparable else None
    )
    total_summary["comparable_coverage_pct"] = round(
        comparable / (comparable + totals["not_comparable_ours"]) * 100.0,
        1,
    ) if comparable + totals["not_comparable_ours"] else None
    total_summary["quality_gate"] = {
        "policy": "require independent agreement",
        "raw_candidates": comparable,
        "promoted": totals["independent_agreements"],
        "rejected": totals["ours_only"],
        "promotion_rate_pct": total_summary["agreement_rate_pct"],
        "independent_confirmation_share_of_promoted_pct": (
            100.0 if totals["independent_agreements"] else None
        ),
        "edge_claim": False,
    }
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "detector_versions": {
            "ours": "structure detector versions embedded per pattern",
            "lmw": "lmw_causal_v1",
        },
        "lmw_supported_patterns": sorted(
            pattern.value for pattern in TEMPLATE_BY_PATTERN
        ),
        "timeframes": [timeframe.value for timeframe in selected_timeframes],
        "assets": [asset.value for asset in selected_assets],
        "summary": total_summary,
        "results": results,
        "interpretation": (
            "Independent agreement raises confidence that the geometry is real. "
            "It is not a trading edge and is never converted into a probability."
        ),
    }


def save_consensus_study(
    result: dict[str, Any],
    path: str | Path = "data/research/pattern_consensus.json",
) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2, default=str))
    return target

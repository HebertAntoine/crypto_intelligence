"""Report evaluation: measure what actually happened after each report.

This is what makes the tool honest about its own quality. Every report is
frozen at time T; later, prices at T+1h ... T+30d are compared against what the
report predicted.

Crucially, outcomes are computed AFTER the fact from stored reports - the
report itself never sees them.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
from pydantic import BaseModel, Field

from ..core.enums import Asset
from ..db import repo

HORIZONS: dict[str, timedelta] = {
    "1h": timedelta(hours=1),
    "4h": timedelta(hours=4),
    "24h": timedelta(hours=24),
    "3d": timedelta(days=3),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}


class EvaluationStats(BaseModel):
    asset: str | None = None
    total_reports: int = 0
    evaluated_outcomes: int = 0
    direction_accuracy: dict[str, float | None] = Field(default_factory=dict)
    sample_sizes: dict[str, int] = Field(default_factory=dict)
    avg_return_when_bullish: dict[str, float | None] = Field(default_factory=dict)
    avg_return_when_bearish: dict[str, float | None] = Field(default_factory=dict)
    calibration: list[dict[str, Any]] = Field(default_factory=list)
    by_domain: dict[str, dict[str, Any]] = Field(default_factory=dict)
    note: str = ""


class OutcomeEvaluator:
    name = "outcome_evaluator"

    def evaluate_pending(self, price_lookup, now: datetime | None = None) -> int:
        """Fill in outcomes for reports old enough to be scored.

        `price_lookup(asset, at) -> float | None` supplies the historical price.
        """
        now = now or datetime.now(UTC)
        reports = repo.reports_needing_evaluation(older_than_minutes=55)
        written = 0

        for report in reports:
            created = report["created_at"]
            if created.tzinfo is None:
                created = created.replace(tzinfo=UTC)
            price_then = report.get("price_at_report")
            if not price_then:
                continue
            asset = Asset(report["asset"])
            # Direction from the medium-horizon conviction.
            conviction = report.get("conviction_medium") or 0.0
            predicted = "BULLISH" if conviction > 8 else ("BEARISH" if conviction < -8 else "NEUTRAL")

            for label, delta in HORIZONS.items():
                target = created + delta
                if target > now:
                    continue
                if repo.has_outcome(report["id"], label):
                    continue
                price_now = price_lookup(asset, target)
                if price_now is None:
                    continue
                repo.save_outcome(report["id"], asset, label, price_then, price_now, predicted)
                written += 1
        return written

    def stats(self, asset: Asset | None = None) -> EvaluationStats:
        outcomes = repo.get_outcomes(asset)
        reports = repo.list_reports(asset, limit=1000)

        if not outcomes:
            return EvaluationStats(
                asset=asset.value if asset else None,
                total_reports=len(reports),
                note=(
                    "No outcomes recorded yet. Statistics appear once reports are at least "
                    "an hour old and prices have been collected for the elapsed horizons."
                ),
            )

        by_horizon: dict[str, list[dict]] = {}
        for o in outcomes:
            by_horizon.setdefault(o["horizon"], []).append(o)

        accuracy: dict[str, float | None] = {}
        samples: dict[str, int] = {}
        avg_bull: dict[str, float | None] = {}
        avg_bear: dict[str, float | None] = {}

        for horizon, rows in by_horizon.items():
            scored = [r for r in rows if r.get("correct") is not None]
            samples[horizon] = len(rows)
            accuracy[horizon] = (
                round(sum(1 for r in scored if r["correct"]) / len(scored) * 100.0, 1)
                if scored else None
            )
            bull = [r["return_pct"] for r in rows
                    if r["predicted_direction"] == "BULLISH" and r["return_pct"] is not None]
            bear = [r["return_pct"] for r in rows
                    if r["predicted_direction"] == "BEARISH" and r["return_pct"] is not None]
            avg_bull[horizon] = round(float(np.mean(bull)), 3) if bull else None
            avg_bear[horizon] = round(float(np.mean(bear)), 3) if bear else None

        calibration = self._calibration(reports, outcomes)
        by_domain = self._by_domain(reports, outcomes)

        note = ""
        small = [h for h, n in samples.items() if n < 20]
        if small:
            note = (
                f"Small samples for horizon(s) {', '.join(sorted(small))} - these figures are "
                "indicative, not statistically meaningful yet."
            )

        return EvaluationStats(
            asset=asset.value if asset else None,
            total_reports=len(reports), evaluated_outcomes=len(outcomes),
            direction_accuracy=accuracy, sample_sizes=samples,
            avg_return_when_bullish=avg_bull, avg_return_when_bearish=avg_bear,
            calibration=calibration, by_domain=by_domain, note=note,
        )

    def _calibration(self, reports: list[dict], outcomes: list[dict]) -> list[dict[str, Any]]:
        """Do stronger convictions actually produce better outcomes?"""
        index = {r["id"]: r for r in reports}
        buckets = {
            "strong_bearish": (-100, -50), "bearish": (-50, -15),
            "neutral": (-15, 15), "bullish": (15, 50), "strong_bullish": (50, 100),
        }
        out = []
        for name, (lo, hi) in buckets.items():
            rows = []
            for o in outcomes:
                r = index.get(o["report_id"])
                if not r:
                    continue
                conv = r.get("conviction_medium")
                if conv is None or not (lo <= conv < hi):
                    continue
                if o["return_pct"] is not None and o["horizon"] == "24h":
                    rows.append(o["return_pct"])
            if rows:
                out.append({
                    "bucket": name, "conviction_range": [lo, hi], "n": len(rows),
                    "avg_return_24h": round(float(np.mean(rows)), 3),
                    "positive_pct": round(sum(1 for v in rows if v > 0) / len(rows) * 100.0, 1),
                })
        return out

    def _by_domain(self, reports: list[dict], outcomes: list[dict]) -> dict[str, dict[str, Any]]:
        """Per-analyst predictiveness - the "ETF score is useless at 4h" question."""
        index = {r["id"]: r for r in reports}
        acc: dict[str, dict[str, list[float]]] = {}

        for o in outcomes:
            r = index.get(o["report_id"])
            if not r or o["return_pct"] is None:
                continue
            for domain, card in (r.get("scores") or {}).items():
                score = card.get("score") if isinstance(card, dict) else None
                if score is None or abs(score) < 10:
                    continue
                acc.setdefault(domain, {}).setdefault(o["horizon"], []).append(
                    o["return_pct"] if score > 0 else -o["return_pct"]
                )

        result: dict[str, dict[str, Any]] = {}
        for domain, horizons in acc.items():
            entry: dict[str, Any] = {}
            for horizon, values in horizons.items():
                if len(values) >= 3:
                    entry[horizon] = {
                        "n": len(values),
                        "avg_aligned_return": round(float(np.mean(values)), 3),
                        "hit_rate": round(sum(1 for v in values if v > 0) / len(values) * 100.0, 1),
                    }
            if entry:
                result[domain] = entry
        return result

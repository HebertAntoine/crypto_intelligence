"""Endpoints for the Charts & Patterns page.

Everything under `/api/analysis` serves one screen: the chart, the figures
detected on it, the context around them and what history says about them.

Routes are added here lot by lot rather than all at once. What exists today is
the availability layer, because every other route on this page has to consult
it before deciding what it is allowed to compute.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Query

from ..history import availability
from ..logging_setup import get_logger

router = APIRouter(tags=["analysis"])
log = get_logger("api.analysis")


@router.get("/analysis/data-availability")
async def data_availability(
    group: str | None = Query(
        None,
        description=(
            "Restrict to one group: candles, derivatives, macro, etf, "
            "live_observations. Omit for everything."
        ),
    ),
    usable_for_backtest: bool | None = Query(
        None, description="Keep only series that do, or do not, support a study."
    ),
) -> dict[str, Any]:
    """What each stored series can honestly be used for.

    Measured from the database on every call rather than cached: the answer
    changes with each collection run, and a stale availability report is worse
    than none - it would let a study run on data it no longer describes.
    """
    report = await asyncio.to_thread(availability.full_report)

    if group is not None:
        selected = report["groups"].get(group)
        if selected is None:
            known = ", ".join(sorted(report["groups"]))
            return {
                "error": f"unknown group '{group}'",
                "known_groups": known,
                "groups": {},
            }
        report["groups"] = {group: selected}

    if usable_for_backtest is not None:
        report["groups"] = {
            name: [r for r in records if r["usable_for_backtest"] is usable_for_backtest]
            for name, records in report["groups"].items()
        }

    return report

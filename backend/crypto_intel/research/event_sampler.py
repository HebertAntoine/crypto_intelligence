"""Which events are genuinely independent, and how long until there are more.

A 30-day forward return computed on Monday and again on Tuesday shares 29 of
its 30 days. Counting both as evidence inflates the sample by roughly the
horizon length. The sampler answers a narrower question than the effective
sample estimate does: not "what is the equivalent independent sample size" but
"which specific events can be kept such that no two forward windows overlap".

That subset is smaller and less powerful than the full set, and it is the only
subset for which the usual independence assumptions actually hold. Both numbers
are reported, because the gap between them is the cost of overlap and deserves
to be visible rather than smoothed away.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import pairwise
from typing import Any

import numpy as np
import pandas as pd


@dataclass(slots=True)
class SampledEvents:
    kept: pd.DatetimeIndex
    dropped: pd.DatetimeIndex
    n_raw: int = 0
    n_independent: int = 0
    overlap_ratio: float = 0.0
    horizon_bars: int = 0
    span_days: float = 0.0
    events_per_year: float = 0.0
    gaps: dict[str, float] = field(default_factory=dict)
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_raw": self.n_raw, "n_independent": self.n_independent,
            "overlap_ratio": self.overlap_ratio, "horizon_bars": self.horizon_bars,
            "span_days": self.span_days, "events_per_year": self.events_per_year,
            "gaps": self.gaps,
            "first_kept": str(self.kept[0])[:10] if len(self.kept) else None,
            "last_kept": str(self.kept[-1])[:10] if len(self.kept) else None,
            "note": self.note,
        }


def sample_independent_events(
    timestamps: pd.DatetimeIndex,
    horizon_bars: int,
    freq_days: float = 1.0,
) -> SampledEvents:
    """Greedy earliest-first selection of non-overlapping forward windows.

    Earliest-first is deliberate. It is the only rule that can be applied
    point-in-time - a live system meeting an event on 3 March cannot know
    whether keeping it costs a better event in June. Selecting to maximise
    count, or to favour large moves, would use the future.
    """
    stamps = pd.DatetimeIndex(timestamps).dropna().sort_values().unique()
    stamps = pd.DatetimeIndex(stamps)
    if len(stamps) == 0:
        return SampledEvents(
            kept=stamps, dropped=stamps, horizon_bars=horizon_bars,
            note="no events",
        )

    window = pd.Timedelta(days=horizon_bars * freq_days)
    kept: list[pd.Timestamp] = []
    dropped: list[pd.Timestamp] = []
    frontier: pd.Timestamp | None = None
    for stamp in stamps:
        if frontier is None or stamp >= frontier:
            kept.append(stamp)
            frontier = stamp + window
        else:
            dropped.append(stamp)

    kept_index = pd.DatetimeIndex(kept)
    span = float((stamps[-1] - stamps[0]).days) if len(stamps) > 1 else 0.0
    result = SampledEvents(
        kept=kept_index,
        dropped=pd.DatetimeIndex(dropped),
        n_raw=len(stamps),
        n_independent=len(kept_index),
        overlap_ratio=round(1 - len(kept_index) / len(stamps), 3),
        horizon_bars=horizon_bars,
        span_days=span,
        events_per_year=(
            round(len(kept_index) / (span / 365.25), 2) if span > 30 else 0.0
        ),
    )

    if len(kept_index) > 1:
        deltas = np.diff(kept_index.to_numpy()).astype("timedelta64[D]").astype(float)
        result.gaps = {
            "min_days": float(deltas.min()),
            "median_days": float(np.median(deltas)),
            "max_days": float(deltas.max()),
        }

    result.note = (
        f"{result.n_independent} of {result.n_raw} events survive the "
        f"non-overlap rule at a {horizon_bars}-bar horizon "
        f"({result.overlap_ratio:.0%} discarded as overlapping). "
        f"Independent events arrive at about {result.events_per_year} per year."
    )
    return result


def clustered_episodes(
    timestamps: pd.DatetimeIndex, gap_bars: int, freq_days: float = 1.0
) -> list[pd.DatetimeIndex]:
    """Group events into episodes separated by at least `gap_bars`.

    Useful where the unit of analysis is the episode rather than the day: nine
    consecutive days above a threshold are one thing that happened, not nine.
    """
    stamps = pd.DatetimeIndex(timestamps).dropna().sort_values()
    if len(stamps) == 0:
        return []
    threshold = pd.Timedelta(days=gap_bars * freq_days)
    episodes: list[list[pd.Timestamp]] = [[stamps[0]]]
    for previous, current in pairwise(stamps):
        if current - previous > threshold:
            episodes.append([current])
        else:
            episodes[-1].append(current)
    return [pd.DatetimeIndex(e) for e in episodes]

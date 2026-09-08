"""The historical scan: every figure a series held, not just today's.

These tests exist because the failure they guard against is silent. A
detector that only ever looks at the last two pivots returns *something* -
it just returns almost nothing, and an empty chart looks like a quiet market
rather than a scan that was never run.

The two properties that make the count trustworthy are asserted directly:
causality (no figure may be dated before it could have been seen) and
identity (the same shape re-detected at ten consecutive pivots is one figure).
"""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest

from crypto_intel.core.enums import Timeframe
from crypto_intel.structure.history_scan import (
    Resolution,
    figures_in_window,
    scan_history,
    within_window,
)
from crypto_intel.structure.patterns import build_context, detect_all


def _frame(closes: np.ndarray) -> pd.DataFrame:
    n = len(closes)
    index = pd.date_range(datetime(2020, 1, 1, tzinfo=UTC), periods=n, freq="D")
    wick = np.abs(closes) * 0.004
    return pd.DataFrame(
        {
            "open": closes - wick * 0.2,
            "high": closes + wick,
            "low": closes - wick,
            "close": closes,
            "volume": np.full(n, 1000.0),
        },
        index=index,
    )


def _leg(start: float, end: float, n: int) -> np.ndarray:
    return np.linspace(start, end, n, endpoint=False)


def _one_double_top() -> np.ndarray:
    return np.concatenate([
        _leg(100, 130, 40),
        _leg(130, 108, 25),
        _leg(108, 129.5, 25),
        _leg(129.5, 112, 25),
    ])


@pytest.fixture(scope="module")
def repeated_frame() -> pd.DataFrame:
    """The same figure three times, separated by quiet drift.

    A scan that only looks at the present finds the last one. A scan that
    replays the detectors finds all three - and must not find nine.
    """
    quiet = _leg(112, 100, 30)
    path = np.concatenate([
        _one_double_top(), quiet,
        _one_double_top(), quiet,
        _one_double_top(),
    ])
    return _frame(path)


class TestItFindsWhatThePresentTenseMisses:
    def test_the_single_shot_detector_sees_only_the_last_figure(self, repeated_frame):
        """The baseline this module exists to fix, asserted rather than assumed."""
        context = build_context(repeated_frame, Timeframe.D1)
        now = [p for p in detect_all(context) if p.name == "double_top"]
        assert len(now) <= 1

    def test_the_scan_finds_every_occurrence(self, repeated_frame):
        tops = [f for f in scan_history(repeated_frame, Timeframe.D1)
                if f.name == "double_top"]
        assert len(tops) >= 3, "a scan that misses earlier figures is the bug"

    def test_the_same_shape_is_not_counted_once_per_pivot(self, repeated_frame):
        """Identity, not repetition.

        The last two pivots stay the last two pivots for several bars, so the
        same figure is re-detected each time. Those are one figure.
        """
        tops = [f for f in scan_history(repeated_frame, Timeframe.D1)
                if f.name == "double_top"]
        assert len(tops) <= 6, f"{len(tops)} double tops in three - duplicates"
        times = [f.first_seen_time for f in tops]
        assert times == sorted(times), "figures must come out oldest first"


class TestCausality:
    def test_no_figure_is_dated_before_it_could_be_seen(self, repeated_frame):
        """A figure dated 2019 must have been recognisable with 2019 data.

        Every defining point must lie at or before the bar the scan credits
        with the sighting; a point after it would mean the detector saw the
        future.
        """
        for figure in scan_history(repeated_frame, Timeframe.D1):
            for point in figure.pattern.geometry.points:
                assert point.time <= figure.first_seen_time, (
                    f"{figure.name}: {point.role} is after its own detection"
                )

    def test_a_scan_of_a_prefix_is_a_prefix_of_the_scan(self, repeated_frame):
        """Bars that print later cannot change what was found earlier.

        This is what makes a cached scan safe to reuse, and what makes the
        count usable as evidence rather than as decoration.
        """
        cut = 150
        early = scan_history(repeated_frame.iloc[:cut], Timeframe.D1)
        full = scan_history(repeated_frame, Timeframe.D1)

        # The final bar is always a detection point, so that a figure
        # recognisable *right now* is found without waiting for the next pivot
        # to confirm. That one sighting is therefore particular to where the
        # series was cut, and is excluded here: everything before it must
        # survive later bars unchanged.
        settled = [f for f in early if f.first_seen_index < cut - 10]
        assert settled, "the prefix found nothing to compare"
        full_keys = {(f.name, f.first_seen_time) for f in full}
        for figure in settled:
            assert (figure.name, figure.first_seen_time) in full_keys, (
                f"{figure.name} at {figure.first_seen_time} "
                "vanished when later bars printed"
            )


class TestResolution:
    def test_a_completed_figure_is_recorded_as_completed(self, repeated_frame):
        figures = scan_history(repeated_frame, Timeframe.D1)
        resolved = [f for f in figures if f.resolution in (
            Resolution.REACHED_TRIGGER, Resolution.REACHED_INVALIDATION
        )]
        assert resolved, "no figure resolved across 375 bars - check the levels"
        for figure in resolved:
            assert figure.resolved_at is not None
            assert figure.resolved_at > figure.first_seen_time
            assert figure.bars_to_resolution >= 1

    def test_resolution_never_becomes_an_edge_claim(self, repeated_frame):
        """§ Recognition is not edge, and neither is one instance's outcome."""
        for figure in scan_history(repeated_frame, Timeframe.D1):
            payload = figure.to_dict()
            assert payload["edge_state"] == "NOT_YET_TESTED"
            assert "not an edge" in payload["resolution_note"]

    def test_a_settled_figure_stops_extending_its_lines(self, repeated_frame):
        """An extended neckline would run across years of unrelated price."""
        for figure in scan_history(repeated_frame, Timeframe.D1):
            if figure.resolution is Resolution.UNRESOLVED:
                continue
            if figure.resolution is Resolution.STILL_OPEN:
                continue
            for line in figure.pattern.geometry.trend_lines:
                assert not line.extend, f"{figure.name} still extends its lines"


class TestEveryFigureIsDrawable:
    def test_no_detector_returns_a_shape_without_geometry(self, repeated_frame):
        """A figure announced without a drawing is worse than no figure.

        Five detectors used to return none: the chart stayed blank while the
        card underneath named a pattern.
        """
        for figure in scan_history(repeated_frame, Timeframe.D1):
            assert not figure.pattern.geometry.is_empty, (
                f"{figure.name} carries no geometry"
            )


class TestWindowing:
    def test_a_figure_half_inside_the_window_is_kept(self, repeated_frame):
        figures = scan_history(repeated_frame, Timeframe.D1)
        assert figures
        first = figures[0]
        # A window that starts inside the figure and ends after it.
        start = first.start_time + (first.end_time - first.start_time) / 2
        end = repeated_frame.index[-1].to_pydatetime()
        assert first in figures_in_window(figures, start, end)

    def test_a_figure_entirely_before_the_window_is_dropped(self, repeated_frame):
        figures = scan_history(repeated_frame, Timeframe.D1)
        first = figures[0]
        start = first.end_time + pd.Timedelta(days=1)
        end = repeated_frame.index[-1].to_pydatetime()
        assert first not in figures_in_window(figures, start, end)

    def test_the_serialised_filter_agrees_with_the_object_one(self, repeated_frame):
        figures = scan_history(repeated_frame, Timeframe.D1)
        start = repeated_frame.index[200].to_pydatetime()
        end = repeated_frame.index[-1].to_pydatetime()
        objects = figures_in_window(figures, start, end)
        payloads = within_window([f.to_dict() for f in figures], start, end)
        assert len(objects) == len(payloads)


class TestItStaysQuietOnNoise:
    def test_a_flat_line_produces_nothing(self):
        """§14 still holds: no shape where there is no shape."""
        flat = _frame(np.full(400, 100.0))
        assert scan_history(flat, Timeframe.D1) == []

    def test_a_series_too_short_to_judge_returns_nothing(self):
        assert scan_history(_frame(_leg(100, 120, 30)), Timeframe.D1) == []

    def test_a_random_walk_does_not_produce_a_figure_every_few_bars(self):
        """The scan asks more often; it must not therefore answer yes more.

        A detector firing on noise would turn this into a figure factory, and
        the whole count would become meaningless.
        """
        rng = np.random.default_rng(20260908)
        walk = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, 1200)))
        figures = scan_history(_frame(walk), Timeframe.D1)
        per_hundred = len(figures) / (len(walk) / 100)
        assert per_hundred < 6, (
            f"{len(figures)} figures on 1200 random bars "
            f"({per_hundred:.1f} per 100) - the detectors fire on noise"
        )

"""The detectors must find textbook figures and reject noise.

Two halves, and the second matters more than the first.

Finding a synthetic double top proves the geometry is implemented. Any naive
detector passes that. The hard requirement from §14 is the other direction: on
random walks, which contain no figures by construction, the detector must stay
quiet. The version before LOT 4 fired on roughly four daily bars out of five,
which is the same as saying nothing at all.

The synthetic series are built to be unambiguous - a human would draw the same
figure - so a failure here is a real regression rather than a threshold being
one percent off.
"""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest

from crypto_intel.core.enums import Timeframe
from crypto_intel.structure.patterns import (
    CRITERIA,
    PatternState,
    build_context,
    detect_all,
    detect_triangle,
    detect_wedge,
)


def _frame(closes: np.ndarray, volume: np.ndarray | None = None) -> pd.DataFrame:
    """Wrap a close path into OHLCV with small, realistic wicks."""
    n = len(closes)
    index = pd.date_range(datetime(2022, 1, 1, tzinfo=UTC), periods=n, freq="D", tz=None)
    index = index.tz_localize(UTC) if index.tz is None else index
    wick = np.abs(closes) * 0.004
    return pd.DataFrame(
        {
            "open": closes - wick * 0.2,
            "high": closes + wick,
            "low": closes - wick,
            "close": closes,
            "volume": volume if volume is not None else np.full(n, 1000.0),
        },
        index=index,
    )


def _leg(start: float, end: float, n: int) -> np.ndarray:
    return np.linspace(start, end, n, endpoint=False)


def _names(df: pd.DataFrame) -> list[str]:
    ctx = build_context(df, Timeframe.D1)
    if ctx is None:
        return []
    return [p.name for p in detect_all(ctx)]


# --- synthetic figures the detector must find ------------------------------


def _double_top_frame() -> pd.DataFrame:
    """Two equal peaks with a deep valley between them, then a decline."""
    closes = np.concatenate([
        _leg(100, 130, 40),    # rise into the first top
        _leg(130, 108, 25),    # valley - a large, unambiguous reaction
        _leg(108, 129.5, 25),  # second top, within a fraction of the first
        _leg(129.5, 112, 25),  # roll over, still above the neckline
    ])
    return _frame(closes)


def _double_bottom_frame() -> pd.DataFrame:
    closes = np.concatenate([
        _leg(130, 100, 40),
        _leg(100, 122, 25),
        _leg(122, 100.5, 25),
        _leg(100.5, 118, 25),
    ])
    return _frame(closes)


def _zigzag(highs: list[float], lows: list[float], leg: int = 18) -> np.ndarray:
    """Alternate low -> high -> low so each listed level becomes a real pivot.

    Building the series from the extremes themselves, rather than from a
    running offset, is what makes the fixtures unambiguous: the detector's
    fitted boundaries pass exactly through the levels written here.
    """
    legs = [_leg(lows[0] + 12, lows[0], leg)]      # approach into the first low
    for i in range(len(lows)):
        legs.append(_leg(lows[i], highs[i], leg))   # rally to the high
        if i + 1 < len(lows):
            legs.append(_leg(highs[i], lows[i + 1], leg))  # decline to the next low
    legs.append(_leg(highs[-1], (highs[-1] + lows[-1]) / 2, leg))
    return np.concatenate(legs)


def _ascending_triangle_frame() -> pd.DataFrame:
    """Flat resistance, rising support that sits on one straight line."""
    return _frame(_zigzag(highs=[130.0, 130.0, 130.0, 130.0],
                          lows=[100.0, 108.0, 116.0, 124.0]))


def _descending_triangle_frame() -> pd.DataFrame:
    """Flat support, falling resistance."""
    return _frame(_zigzag(highs=[130.0, 121.0, 112.0, 103.0],
                          lows=[100.0, 100.0, 100.0, 100.0]))


def _falling_wedge_frame() -> pd.DataFrame:
    """Both boundaries falling, the lower one less steeply - they converge."""
    return _frame(_zigzag(highs=[140.0, 131.0, 122.0, 113.0],
                          lows=[100.0, 97.0, 94.0, 91.0]))


def _rising_wedge_frame() -> pd.DataFrame:
    """Both boundaries rising, the upper one less steeply - they converge."""
    return _frame(_zigzag(highs=[120.0, 123.0, 126.0, 129.0],
                          lows=[100.0, 106.0, 112.0, 118.0]))


@pytest.mark.parametrize(
    "builder,expected",
    [
        (_double_top_frame, "double_top"),
        (_double_bottom_frame, "double_bottom"),
        (_ascending_triangle_frame, "ascending_triangle"),
        (_descending_triangle_frame, "descending_triangle"),
        (_falling_wedge_frame, "falling_wedge"),
        (_rising_wedge_frame, "rising_wedge"),
    ],
)
def test_textbook_figure_is_found(builder, expected):
    """A figure a human would draw without hesitating must be detected."""
    found = _names(builder())
    assert expected in found, f"expected {expected}, detector reported {found or 'nothing'}"


def test_double_top_direction_and_levels_are_coherent():
    ctx = build_context(_double_top_frame(), Timeframe.D1)
    pattern = next(p for p in detect_all(ctx) if p.name == "double_top")

    assert pattern.direction_if_textbook == "BEARISH"
    # The neckline sits below both tops; invalidation sits above them.
    assert pattern.key_levels["neckline"] < pattern.key_levels["first_extreme"]
    assert pattern.invalidation_level >= max(
        pattern.key_levels["first_extreme"], pattern.key_levels["second_extreme"]
    )


def test_ascending_triangle_has_a_flat_top_and_a_rising_bottom():
    ctx = build_context(_ascending_triangle_frame(), Timeframe.D1)
    pattern = next(p for p in detect_all(ctx) if p.name == "ascending_triangle")

    criteria = CRITERIA["triangle"]
    assert abs(pattern.components["upper_slope_atr_per_bar"]) < criteria.flat_slope_atr
    assert pattern.components["lower_slope_atr_per_bar"] > criteria.flat_slope_atr
    assert pattern.direction_if_textbook == "BULLISH"


def test_wedge_boundaries_slope_the_same_way():
    ctx = build_context(_falling_wedge_frame(), Timeframe.D1)
    pattern = next(p for p in detect_all(ctx) if p.name == "falling_wedge")

    upper = pattern.components["upper_slope_atr_per_bar"]
    lower = pattern.components["lower_slope_atr_per_bar"]
    assert np.sign(upper) == np.sign(lower) < 0
    assert pattern.direction_if_textbook == "BULLISH"


# --- geometry --------------------------------------------------------------


def test_detected_figure_carries_drawable_geometry():
    """§6: the frontend must be able to rebuild the figure without recomputing."""
    ctx = build_context(_double_top_frame(), Timeframe.D1)
    pattern = next(p for p in detect_all(ctx) if p.name == "double_top")

    assert not pattern.geometry.is_empty
    assert len(pattern.geometry.points) == 2
    assert pattern.geometry.neckline is not None
    assert pattern.geometry.breakout_area is not None
    payload = pattern.to_dict()["geometry"]
    assert payload["points"][0]["time"].startswith("20")
    assert payload["neckline"]["role"] == "neckline"


def test_triangle_geometry_has_two_boundaries():
    ctx = build_context(_ascending_triangle_frame(), Timeframe.D1)
    pattern = next(p for p in detect_all(ctx) if p.name == "ascending_triangle")

    roles = {line.role for line in pattern.geometry.trend_lines}
    assert roles == {"upper", "lower"}
    assert all(line.extend for line in pattern.geometry.trend_lines)


def test_confidence_is_the_mean_of_its_named_components():
    """§22: the published number must be recomputable from the parts shown."""
    ctx = build_context(_double_top_frame(), Timeframe.D1)
    pattern = next(p for p in detect_all(ctx) if p.name == "double_top")

    named = [
        pattern.components[k]
        for k in ("extreme_agreement", "reaction_depth", "time_separation", "pivot_quality")
    ]
    assert pattern.recognition_confidence == pytest.approx(float(np.mean(named)), abs=0.6)


# --- the part that matters: not finding things -----------------------------


def _random_walk(seed: int, n: int = 400) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    closes = 100 * np.exp(np.cumsum(rng.normal(0, 0.012, n)))
    return _frame(closes, volume=rng.uniform(800, 1200, n))


def _specified_names(df: pd.DataFrame) -> list[str]:
    """Only the detectors whose definition is written down.

    EXPERIMENTAL means the definition still rests on judgement. Holding those
    to the same silence requirement as a specified one would hide which is
    which.
    """
    from crypto_intel.structure.patterns import PATTERN_CLASSES, PatternClass

    ctx = build_context(df, Timeframe.D1)
    if ctx is None:
        return []
    return [
        p.name for p in detect_all(ctx)
        if PATTERN_CLASSES.get(p.name) is not PatternClass.EXPERIMENTAL
    ]


def test_random_walks_rarely_produce_a_specified_pattern():
    """The headline requirement of §14, for the shapes that are specified.

    A random walk contains no figure. Before LOT 4 the detectors fired on the
    large majority of bars of real daily history; the ceiling here is what
    "quality over quantity" has to mean in a number.

    EXPERIMENTAL detectors are excluded and measured separately below - not to
    spare them, but because lumping them in turned one clear pass and one
    clear failure into a single murky number.
    """
    hits = sum(1 for seed in range(40) if _specified_names(_random_walk(seed)))

    rate = hits / 40
    assert rate <= 0.30, (
        f"{hits}/40 random walks produced a specified pattern ({rate:.0%}); "
        "the detectors are firing on noise"
    )


def test_the_flag_detector_is_known_to_fire_on_noise():
    """A measured failure, recorded rather than hidden.

    Flags fire on random walks about as often as on real prices - the noise
    benchmark puts bull flags at 0.44x, meaning they are TWICE as common in
    randomness. This test does not excuse that; it pins the fact so that a
    future definition can be shown to have fixed it, and so that nobody reads
    the silence of the test above as covering flags too.

    When a flag definition finally beats this, the assertion below fails and
    the fix is to move flags into the specified test - which is the point.
    """
    with_flags = sum(1 for seed in range(40) if _names(_random_walk(seed)))
    without = sum(1 for seed in range(40) if _specified_names(_random_walk(seed)))

    assert with_flags > without, (
        "flags no longer add noise detections - re-classify them as specified"
    )
    assert with_flags / 40 > 0.30, (
        "the flag detector has become quiet on noise; promote it and delete "
        "this test"
    )


def test_a_pure_trend_is_not_a_reversal_figure():
    """A clean uptrend has no double top in it, however many wiggles it has."""
    rng = np.random.default_rng(3)
    closes = np.linspace(100, 260, 320) * (1 + rng.normal(0, 0.004, 320))

    found = _names(_frame(closes))

    assert "double_top" not in found
    assert "double_bottom" not in found


def test_flat_noise_is_not_a_triangle():
    """Sideways chop converges on nothing; boundaries must fail alignment."""
    rng = np.random.default_rng(11)
    closes = 100 + rng.normal(0, 0.8, 320)

    found = _names(_frame(closes))

    assert "ascending_triangle" not in found
    assert "descending_triangle" not in found
    assert "symmetrical_triangle" not in found


def test_diverging_boundaries_are_never_a_triangle():
    """A broadening formation is the opposite of a triangle and must be refused."""
    legs = []
    top, bottom = 110.0, 100.0
    for _ in range(5):
        legs.append(_leg(bottom, top, 16))
        legs.append(_leg(top, bottom, 16))
        top += 7.0          # widening, not converging
        bottom -= 7.0
    df = _frame(np.concatenate(legs))
    ctx = build_context(df, Timeframe.D1)

    assert detect_triangle(ctx) is None
    assert detect_wedge(ctx) is None


def test_two_lows_too_far_apart_are_not_one_double_bottom():
    """The max-bars gate: lows a year apart do not form a single figure."""
    closes = np.concatenate([
        _leg(130, 100, 30),
        _leg(100, 125, 150),   # a very long recovery
        _leg(125, 100.4, 150),
        _leg(100.4, 110, 20),
    ])
    ctx = build_context(_frame(closes), Timeframe.D1)
    doubles = [p for p in detect_all(ctx) if p.name == "double_bottom"]

    span_limit = CRITERIA["double"].max_bars
    assert all(p.bars_span <= span_limit for p in doubles)


# --- lifecycle -------------------------------------------------------------


def test_shape_alone_never_confirms():
    """CONFIRMED requires the trigger to be reached, never the geometry."""
    ctx = build_context(_double_top_frame(), Timeframe.D1)
    pattern = next(p for p in detect_all(ctx) if p.name == "double_top")

    last_close = float(ctx.close.iloc[-1])
    if last_close > pattern.key_levels["neckline"]:
        assert pattern.state is not PatternState.CONFIRMED


def test_every_reported_pattern_clears_its_confidence_floor():
    """Nothing marginal reaches the interface at all."""
    for seed in range(15):
        ctx = build_context(_random_walk(seed), Timeframe.D1)
        if ctx is None:
            continue
        for pattern in detect_all(ctx):
            floor = CRITERIA.get(
                "double" if pattern.name.startswith("double")
                else "triangle" if "triangle" in pattern.name
                else "wedge" if "wedge" in pattern.name
                else "",
            )
            if floor is not None:
                assert pattern.recognition_confidence >= floor.min_confidence

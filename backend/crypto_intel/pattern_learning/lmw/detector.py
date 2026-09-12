"""Causal and retrospective implementations of the LMW-style baseline.

The implementation follows the useful separation in Lo, Mamaysky & Wang:

1. smooth price with a kernel regression;
2. extract extrema from the smoothed series;
3. compare consecutive extrema with declared geometric templates.

It does *not* copy a third-party implementation and it does not use returns
after the detection.  Every threshold below describes geometry only.  The
causal mode uses a one-sided kernel and dates an extremum one bar after the
turn, when both neighbours needed by the local-extremum test are known.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from ...structure.geometry import GeometryPoint, PatternGeometry, TrendLine
from ..ontology import StructuralPatternName
from .models import (
    LMWDetection,
    LMWMode,
    LMWResult,
    LMWScoreComponents,
    LMWStatus,
)
from .smoothing import bandwidth_for, causal_kernel_smooth, kernel_smooth
from .templates import TEMPLATES, TemplateSpec


@dataclass(slots=True, frozen=True)
class LMWConfig:
    """Predeclared geometric gates for the independent comparator.

    These defaults were chosen from scale-free properties of a readable
    figure, not from its subsequent return.  Changing them creates a new
    detector version and requires rerunning the comparison from scratch.
    """

    bandwidth_fraction: float = 0.025
    causal_bandwidth_bars: float = 5.0
    min_bars: int = 24
    min_leg_bars: int = 2
    min_span_bars: int = 8
    max_span_bars: int = 180
    min_amplitude_to_noise: float = 4.0
    min_shape_fit: float = 62.0
    min_match_score: float = 68.0
    overlap_is_same: float = 0.80

    def __post_init__(self) -> None:
        if not 0 < self.bandwidth_fraction <= 0.25:
            raise ValueError("bandwidth_fraction must be in (0, 0.25]")
        if self.causal_bandwidth_bars <= 0:
            raise ValueError("causal_bandwidth_bars must be positive")
        if self.min_bars < 3:
            raise ValueError("min_bars must be at least 3")
        if self.min_leg_bars < 1:
            raise ValueError("min_leg_bars must be positive")
        if self.min_span_bars >= self.max_span_bars:
            raise ValueError("min_span_bars must be below max_span_bars")
        if self.min_amplitude_to_noise <= 0:
            raise ValueError("min_amplitude_to_noise must be positive")
        if not 0 <= self.min_shape_fit <= 100:
            raise ValueError("min_shape_fit must be between 0 and 100")
        if not 0 <= self.min_match_score <= 100:
            raise ValueError("min_match_score must be between 0 and 100")
        if not 0 < self.overlap_is_same <= 1:
            raise ValueError("overlap_is_same must be in (0, 1]")


@dataclass(slots=True, frozen=True)
class SmoothedExtremum:
    index: int
    kind: str
    value: float


def extract_extrema(values: np.ndarray) -> list[SmoothedExtremum]:
    """Return strict, alternating local extrema from a smoothed series.

    Flat plateaus are represented once at their centre.  Without this rule a
    rounded top could disappear merely because floating-point smoothing made
    two adjacent values equal.
    """
    array = np.asarray(values, dtype=float)
    if len(array) < 3 or not np.isfinite(array).all():
        return []

    out: list[SmoothedExtremum] = []
    i = 1
    while i < len(array) - 1:
        start = i
        while i < len(array) - 1 and np.isclose(
            array[i], array[i + 1], rtol=1e-10, atol=1e-12
        ):
            i += 1
        end = i
        if end >= len(array) - 1:
            # A plateau reaching the last observation has no right neighbour,
            # so it cannot yet be classified as an extremum.
            break
        value = float(array[start])
        left = float(array[start - 1])
        right = float(array[end + 1])
        kind = "max" if value > left and value > right else (
            "min" if value < left and value < right else ""
        )
        if kind:
            centre = (start + end) // 2
            candidate = SmoothedExtremum(centre, kind, value)
            if out and out[-1].kind == kind:
                # Defensive for numerical shoulders: keep the more extreme
                # point, otherwise a template could contain max/max or min/min.
                previous = out[-1]
                more_extreme = (
                    candidate.value > previous.value
                    if kind == "max"
                    else candidate.value < previous.value
                )
                if more_extreme:
                    out[-1] = candidate
            else:
                out.append(candidate)
        i += 1
    return out


def scan_lmw(
    close: pd.Series,
    *,
    mode: LMWMode = LMWMode.CAUSAL,
    config: LMWConfig | None = None,
    patterns: Iterable[StructuralPatternName] | None = None,
) -> list[LMWDetection]:
    """Find every non-duplicate template match in ``close``.

    The causal output is prefix-stable: adding future bars cannot move or
    remove an already available detection.  Retrospective mode is labelled as
    such and every result is only marked available at the end of the supplied
    sample, because its symmetric kernel has read that whole sample.
    """
    cfg = config or LMWConfig()
    series = _validated_close(close)
    if len(series) < cfg.min_bars:
        return []

    raw = series.to_numpy(dtype=float)
    # A bandwidth derived from the final length would change yesterday's
    # causal curve whenever a new bar arrives.  Causal mode therefore uses a
    # fixed width in bars; only the explicitly retrospective study scales the
    # bandwidth to its complete sample.
    bandwidth = (
        cfg.causal_bandwidth_bars
        if mode.causal
        else bandwidth_for(len(raw), cfg.bandwidth_fraction)
    )
    smoothed = (
        causal_kernel_smooth(raw, bandwidth)
        if mode.causal
        else kernel_smooth(raw, bandwidth)
    )
    extrema = extract_extrema(smoothed)
    allowed = set(patterns) if patterns is not None else None
    templates = [
        template for template in TEMPLATES
        if allowed is None or template.pattern in allowed
    ]

    detections: list[LMWDetection] = []
    for template in templates:
        width = len(template.kinds)
        for offset in range(0, len(extrema) - width + 1):
            candidate = extrema[offset:offset + width]
            if tuple(point.kind for point in candidate) != template.kinds:
                continue
            detection = _evaluate_candidate(
                series,
                raw,
                smoothed,
                candidate,
                template,
                mode,
                cfg,
                bandwidth,
            )
            if detection is not None:
                detections.append(detection)

    return _drop_overlapping(detections, cfg.overlap_is_same)


def detect_latest(
    close: pd.Series,
    *,
    mode: LMWMode = LMWMode.CAUSAL,
    config: LMWConfig | None = None,
    patterns: Iterable[StructuralPatternName] | None = None,
) -> LMWResult:
    """Return the most recently available match, while allowing no-result."""
    cfg = config or LMWConfig()
    if close is None or len(close) < cfg.min_bars:
        return LMWResult(
            status=LMWStatus.INSUFFICIENT_DATA,
            reason=f"at least {cfg.min_bars} finite closes are required",
        )
    try:
        detections = scan_lmw(close, mode=mode, config=cfg, patterns=patterns)
    except ValueError as exc:
        return LMWResult(status=LMWStatus.INSUFFICIENT_DATA, reason=str(exc))
    if not detections:
        return LMWResult(
            status=LMWStatus.NO_VALID_PATTERN,
            reason="no candidate passed every predeclared geometric gate",
        )
    latest = max(
        detections,
        key=lambda item: (item.available_index, item.lmw_match_score),
    )
    return LMWResult(
        status=LMWStatus.DETECTED,
        detection=latest,
        candidates_evaluated=len(detections),
    )


def _validated_close(close: pd.Series) -> pd.Series:
    if close is None or not isinstance(close, pd.Series):
        raise ValueError("close must be a pandas Series")
    if not isinstance(close.index, pd.DatetimeIndex):
        raise ValueError("close must use a DatetimeIndex")
    if not close.index.is_monotonic_increasing or not close.index.is_unique:
        raise ValueError("close timestamps must be unique and increasing")
    numeric = pd.to_numeric(close, errors="coerce").astype(float)
    if not np.isfinite(numeric.to_numpy()).all():
        raise ValueError("close contains missing or non-finite values")
    if (numeric <= 0).any():
        raise ValueError("close prices must be positive")
    return numeric


def _evaluate_candidate(
    close: pd.Series,
    raw: np.ndarray,
    smoothed: np.ndarray,
    extrema: list[SmoothedExtremum],
    template: TemplateSpec,
    mode: LMWMode,
    config: LMWConfig,
    bandwidth: float,
) -> LMWDetection | None:
    locations: NDArray[np.int64] = np.asarray(
        [point.index for point in extrema], dtype=np.int64
    )
    legs = np.diff(locations)
    span = int(locations[-1] - locations[0])
    min_span = max(config.min_span_bars, config.min_leg_bars * len(legs))
    if (
        span < min_span
        or span > config.max_span_bars
        or len(legs) == 0
        or int(legs.min()) < config.min_leg_bars
    ):
        return None

    smooth_points = smoothed[locations]
    low = float(np.min(smooth_points))
    amplitude = float(np.max(smooth_points) - low)
    if amplitude <= np.finfo(float).eps:
        return None
    normalised = (smooth_points - low) / amplitude
    expected: NDArray[np.float64] = np.asarray(template.values, dtype=float)
    shape_error = float(np.sqrt(np.mean((normalised - expected) ** 2)))
    shape_fit = float(np.clip(100.0 * (1.0 - shape_error / 0.50), 0.0, 100.0))
    if shape_fit < config.min_shape_fit:
        return None

    segment = raw[locations[0]:locations[-1] + 1]
    changes = np.abs(np.diff(segment))
    finite_changes = changes[np.isfinite(changes) & (changes > 0)]
    noise = float(np.median(finite_changes)) if len(finite_changes) else 0.0
    amplitude_to_noise = amplitude / noise if noise > 0 else float("inf")
    if amplitude_to_noise < config.min_amplitude_to_noise:
        return None
    extrema_fit = float(np.clip(
        amplitude_to_noise / (config.min_amplitude_to_noise * 2.0) * 100.0,
        0.0,
        100.0,
    ))

    # A readable template distributes its turning points across its duration.
    # This is deliberately temporal only; no future return enters the score.
    actual_positions = (locations - locations[0]) / span
    expected_positions = np.linspace(0.0, 1.0, len(locations))
    timing_error = float(np.sqrt(np.mean((actual_positions - expected_positions) ** 2)))
    symmetry_fit = float(np.clip(100.0 * (1.0 - timing_error / 0.35), 0.0, 100.0))

    preferred_span = max(min_span, 6 * len(legs))
    duration_fit = float(np.clip(span / preferred_span * 100.0, 0.0, 100.0))
    components = LMWScoreComponents(
        shape_fit=round(shape_fit, 1),
        extrema_fit=round(extrema_fit, 1),
        symmetry_fit=round(symmetry_fit, 1),
        duration_fit=round(duration_fit, 1),
    )
    score = components.mean
    if score < config.min_match_score:
        return None

    end_index = int(locations[-1])
    available_index = end_index + 1 if mode.causal else len(close) - 1
    if available_index >= len(close):
        # The last extremum still needs its right neighbour in causal mode.
        return None

    geometry = _geometry(close, locations, template)
    return LMWDetection(
        pattern=template.pattern,
        start_time=close.index[locations[0]].to_pydatetime(),
        end_time=close.index[end_index].to_pydatetime(),
        available_at=close.index[available_index].to_pydatetime(),
        geometry=geometry,
        lmw_match_score=score,
        score_components=components,
        mode=mode,
        orientation=template.orientation,
        detection_delay_bars=available_index - end_index,
        start_index=int(locations[0]),
        end_index=end_index,
        available_index=available_index,
        metadata={
            "bandwidth_bars": round(float(bandwidth), 4),
            "bandwidth_fraction": config.bandwidth_fraction,
            "causal_bandwidth_bars": config.causal_bandwidth_bars,
            "amplitude_to_noise": round(float(amplitude_to_noise), 3),
            "normalised_extrema": [round(float(value), 4) for value in normalised],
            "smoothed_extrema": [round(float(value), 8) for value in smooth_points],
            "thresholds": {
                "min_shape_fit": config.min_shape_fit,
                "min_match_score": config.min_match_score,
                "min_amplitude_to_noise": config.min_amplitude_to_noise,
            },
            "outcome_data_used": False,
        },
    )


def _geometry(
    close: pd.Series,
    locations: NDArray[np.int64],
    template: TemplateSpec,
) -> PatternGeometry:
    points = [
        GeometryPoint(
            time=close.index[int(index)].to_pydatetime(),
            price=round(float(close.iloc[int(index)]), 8),
            role=role,
            kind="smoothed_extremum",
        )
        for index, role in zip(locations, template.roles, strict=True)
    ]
    lines: list[TrendLine] = []
    neckline: TrendLine | None = None

    if template.pattern in (
        StructuralPatternName.DOUBLE_TOP,
        StructuralPatternName.DOUBLE_BOTTOM,
    ):
        neckline = TrendLine(points[1], points[-1], role="neckline", extend=True)
        lines.append(neckline)
    elif template.pattern in (
        StructuralPatternName.HEAD_SHOULDERS,
        StructuralPatternName.INVERSE_HEAD_SHOULDERS,
        StructuralPatternName.TRIPLE_TOP,
        StructuralPatternName.TRIPLE_BOTTOM,
    ):
        neckline = TrendLine(points[1], points[3], role="neckline", extend=True)
        lines.append(neckline)
    elif template.pattern in (
        StructuralPatternName.ASCENDING_TRIANGLE,
        StructuralPatternName.DESCENDING_TRIANGLE,
        StructuralPatternName.SYMMETRICAL_TRIANGLE,
        StructuralPatternName.RECTANGLE_RANGE,
        StructuralPatternName.RISING_WEDGE,
        StructuralPatternName.FALLING_WEDGE,
        StructuralPatternName.BULL_FLAG,
        StructuralPatternName.BEAR_FLAG,
    ):
        upper = [point for point, kind in zip(points, template.kinds, strict=True) if kind == "max"]
        lower = [point for point, kind in zip(points, template.kinds, strict=True) if kind == "min"]
        if len(upper) >= 2:
            lines.append(TrendLine(upper[0], upper[-1], role="upper", extend=True))
        if len(lower) >= 2:
            lines.append(TrendLine(lower[0], lower[-1], role="lower", extend=True))

    return PatternGeometry(points=points, trend_lines=lines, neckline=neckline)


def _drop_overlapping(
    detections: list[LMWDetection], overlap_is_same: float
) -> list[LMWDetection]:
    """Keep the first causal reading of a move, never a later re-reading."""
    ordered = sorted(
        detections,
        key=lambda item: (item.available_index, item.start_index, -item.lmw_match_score),
    )
    kept: list[LMWDetection] = []
    for candidate in ordered:
        duplicate = False
        for earlier in kept:
            if earlier.pattern is not candidate.pattern:
                continue
            intersection = max(
                0,
                min(earlier.end_index, candidate.end_index)
                - max(earlier.start_index, candidate.start_index),
            )
            shorter = min(
                earlier.end_index - earlier.start_index,
                candidate.end_index - candidate.start_index,
            )
            if shorter > 0 and intersection / shorter >= overlap_is_same:
                duplicate = True
                break
        if not duplicate:
            kept.append(candidate)
    return kept

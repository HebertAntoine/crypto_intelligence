"""Shared geometric tests, so a detector cannot accept a shape by accident.

The detectors that came before this module shared a weakness: they checked that
pivots existed in roughly the right order, then declared a pattern. Nothing
asked whether the pivots were actually *aligned*, whether they were meaningful
swings or noise, or whether the figure had a sensible size. Replayed over nine
years of daily bars, that found a pattern on most of them - a detector that
fires on four bars out of five carries no information at all.

Every test here returns a score in 0-100 rather than a boolean, for two reasons.
A detector needs to reject on a hard floor *and* build a confidence out of the
same measurements, and §22 requires the confidence to be decomposable into named
parts. A single function serving both keeps the number that gets published and
the number that gated the decision from drifting apart.

Everything scales with ATR, so "aligned" and "meaningful" mean the same
structural thing on BTC at 90 000 and on SOL at 95.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np

from .swings import CausalSwing


@dataclass(slots=True, frozen=True)
class LineFit:
    """A straight line through pivots, with how well it actually fits them."""

    slope: float              # price units per bar
    intercept: float
    r_squared: float          # 0-1, share of variance the line explains
    slope_atr_per_bar: float  # slope normalised by ATR - comparable across assets
    residual_atr: float       # typical distance of a pivot from the line, in ATR
    points: int

    @property
    def alignment_score(self) -> float:
        """How convincingly the pivots sit on one line.

        R² alone is misleading on three points, where it is almost always high.
        The residual in ATR is the honest check: pivots half an ATR off the line
        are not a trendline whatever the correlation says.
        """
        from_r2 = float(np.clip(self.r_squared, 0.0, 1.0)) * 100.0
        from_residual = float(np.clip((1.0 - self.residual_atr / 0.8), 0.0, 1.0)) * 100.0
        # The weaker of the two governs: a line must pass both tests, and
        # averaging would let a high R² paper over scattered pivots.
        return round(min(from_r2, from_residual), 1)

    def price_at(self, bar_index: float) -> float:
        return self.slope * bar_index + self.intercept


def fit_line(swings: Sequence[CausalSwing], atr: float) -> LineFit | None:
    """Least-squares line through pivot prices, measured against ATR.

    Returns None below two points, or when ATR is unusable - a normalised
    measure needs a scale, and inventing one would make every downstream score
    meaningless.
    """
    if len(swings) < 2 or atr <= 0 or not np.isfinite(atr):
        return None

    x = np.array([s.pivot_index for s in swings], dtype=float)
    y = np.array([s.price for s in swings], dtype=float)
    if len(np.unique(x)) < 2:
        return None

    slope, intercept = np.polyfit(x, y, 1)
    predicted = slope * x + intercept
    residuals = y - predicted

    total_variance = float(np.sum((y - y.mean()) ** 2))
    residual_variance = float(np.sum(residuals**2))
    # A perfectly flat set of pivots has zero variance to explain; that is a
    # perfect horizontal line, not an undefined fit.
    r_squared = 1.0 if total_variance <= 0 else 1.0 - residual_variance / total_variance

    return LineFit(
        slope=float(slope),
        intercept=float(intercept),
        r_squared=float(r_squared),
        slope_atr_per_bar=float(slope) / atr,
        residual_atr=float(np.sqrt(residual_variance / len(y))) / atr,
        points=len(swings),
    )


def pivot_quality(swings: Sequence[CausalSwing]) -> float:
    """How substantial the pivots are, from the reaction each produced.

    `CausalSwing.reaction_atr` already measures how far price moved away from a
    pivot before it was confirmed. A swing low that produced a three-ATR bounce
    is a level the market respected; one that produced a quarter-ATR wobble is
    a rounding artefact that happens dozens of times a year.
    """
    reactions = [s.reaction_atr for s in swings if s.reaction_atr is not None]
    if not reactions:
        return 0.0
    # 1.5 ATR is treated as a fully convincing reaction; below that the score
    # falls off linearly rather than stepping, so a marginal pivot degrades the
    # confidence instead of silently passing.
    scores = [float(np.clip(r / 1.5, 0.0, 1.0)) * 100.0 for r in reactions]
    return round(float(np.mean(scores)), 1)


def symmetry_score(values: Sequence[float], atr: float) -> float:
    """How closely a set of prices agree, in ATR.

    Used for the two tops of a double top, the shoulders of a head and
    shoulders, and any other figure whose definition says "roughly equal".
    """
    if len(values) < 2 or atr <= 0:
        return 0.0
    spread_atr = (max(values) - min(values)) / atr
    return round(float(np.clip(1.0 - spread_atr, 0.0, 1.0)) * 100.0, 1)


def volume_trend_score(volume: Sequence[float], expect_declining: bool = True) -> float:
    """Whether volume behaves the way the textbook figure says it should.

    Triangles and wedges are supposed to form on contracting volume. This is a
    *confirmation*, never a gate: the figure is defined by its geometry, and a
    pattern is not rejected for having the wrong volume profile - the score is
    simply lower, and the reason is visible in the components.
    """
    values = np.asarray([v for v in volume if np.isfinite(v)], dtype=float)
    if len(values) < 6 or values.mean() <= 0:
        return 50.0  # no usable reading - neutral, never a penalty

    half = len(values) // 2
    first, second = values[:half].mean(), values[half:].mean()
    if first <= 0:
        return 50.0

    change = (second - first) / first
    if not expect_declining:
        change = -change
    # -40% volume into the apex reads as fully confirming; +40% as fully against.
    return round(float(np.clip(0.5 - change / 0.8, 0.0, 1.0)) * 100.0, 1)


@dataclass(slots=True)
class PatternCriteria:
    """The hard gates one detector applies before it may report anything.

    Named and stored on the detector rather than inlined, so §14's "minimum
    criteria, tolerances, bar counts, pivot control, slope validation" can be
    read off in one place, and so a rejection can say which gate failed.
    """

    min_bars: int = 20
    max_bars: int = 300
    min_pivots: int = 2
    min_pivot_quality: float = 35.0
    min_alignment: float = 45.0
    min_confidence: float = 55.0
    #: Tolerance for "two comparable extremes", in ATR.
    extreme_tolerance_atr: float = 0.8
    #: A reaction between two tests, below which they are one broad base.
    min_reaction_atr: float = 1.2
    #: Convergence a triangle or wedge must reach: the boundaries must close by
    #: at least this share of their starting width.
    min_convergence: float = 0.35
    #: A boundary is "flat" when its slope is under this many ATR per bar.
    flat_slope_atr: float = 0.02

    def bars_ok(self, span: int) -> bool:
        return self.min_bars <= span <= self.max_bars


@dataclass(slots=True)
class Rejection:
    """Why a candidate was refused. Kept so tuning is not guesswork."""

    gate: str
    detail: str


@dataclass(slots=True)
class QualityReport:
    """Component scores plus the gate that failed, if one did."""

    components: dict[str, float] = field(default_factory=dict)
    rejection: Rejection | None = None

    @property
    def passed(self) -> bool:
        return self.rejection is None

    def reject(self, gate: str, detail: str) -> QualityReport:
        self.rejection = Rejection(gate=gate, detail=detail)
        return self

    def confidence(self) -> float:
        """The mean of the components - the convention `PatternDetection` checks.

        Deliberately a plain mean rather than a weighted blend: a weighting is
        one more unexplained choice, and §22 asks for a number anyone can
        recompute from the parts shown next to it.
        """
        if not self.components:
            return 0.0
        return round(float(np.mean(list(self.components.values()))), 1)

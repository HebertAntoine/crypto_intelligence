"""Chart pattern detection framework.

Design constraint from the brief: never announce a pattern just because
something vaguely similar exists. Every detector must therefore

  * return None when its geometric conditions are not met;
  * produce an explicit confidence, checked against a configured floor;
  * state its invalidation level, so the pattern can be falsified;
  * report a confirmation_state rather than implying certainty.

Adding a pattern means writing one class and registering it. Nothing else in
the system changes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import pandas as pd

from ....core.enums import Timeframe
from ....core.models import PatternMatch
from ..structure import SwingPoint


@dataclass(slots=True)
class PatternContext:
    """Everything a detector may look at. Passed read-only."""

    high: pd.Series
    low: pd.Series
    close: pd.Series
    volume: pd.Series
    swing_highs: list[SwingPoint]
    swing_lows: list[SwingPoint]
    timeframe: Timeframe
    config: dict


class PatternDetector(ABC):
    """One chart pattern."""

    name: str = "unnamed"
    min_bars: int = 20

    @abstractmethod
    def detect(self, ctx: PatternContext) -> PatternMatch | None:
        """Return a match, or None when the pattern is not present.

        Returning None must be the default. A weak or ambiguous shape is not a
        pattern and must not be reported as one.
        """

    def enough_data(self, ctx: PatternContext) -> bool:
        return len(ctx.close) >= self.min_bars


_REGISTRY: dict[str, PatternDetector] = {}


def register(detector: PatternDetector) -> PatternDetector:
    _REGISTRY[detector.name] = detector
    return detector


def all_detectors() -> list[PatternDetector]:
    return list(_REGISTRY.values())


def get_detector(name: str) -> PatternDetector | None:
    return _REGISTRY.get(name)


def registered_names() -> list[str]:
    return sorted(_REGISTRY)

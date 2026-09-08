"""Every figure a series ever contained, not just the one it contains now.

The detectors in `patterns.py` answer one question: *is there a figure ending
at the last bar?* They read `swings[-1]` and `swings[-2]`. Asked once, at the
present, they can return at most one figure per detector - so nine years of
daily bars produced the same handful of shapes as the last fortnight, and the
chart looked empty however far back you scrolled.

The fix is not looser thresholds. It is to ask the same question repeatedly,
at every moment the answer could have changed. A figure is defined by pivots,
so the answer can only change when a pivot is confirmed: replaying the
detectors at each confirmed pivot finds every figure the series ever held,
and finds each one at the exact bar it first became recognisable.

Two properties are preserved, and both are the reason this is trustworthy:

  * **Causality.** Each replay sees bars up to its own detection point and no
    further. A figure dated 2019 was recognisable in 2019 with 2019 data. This
    is what makes a count from this scan usable as evidence rather than as
    decoration.
  * **Identity.** The same figure is re-detected at every pivot until a newer
    pivot displaces it. Those are one figure, not twelve, and they collapse to
    the earliest detection - the moment a reader could first have seen it.

What happened *after* a figure appeared is recorded separately, as a fact:
whether price reached the trigger or the invalidation first. That is an
observation about one instance. It is not an edge, and it never becomes one
here - `edge_state` stays where it is.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

import pandas as pd

from ..core.enums import Timeframe
from ..logging_setup import get_logger
from .patterns import (
    DEFAULT_MIN_CONFIDENCE,
    PatternContext,
    PatternState,
    StructuralPattern,
    detect_all,
)
from .swings import SwingSeries, find_causal_swings

log = get_logger("structure.history_scan")

#: Bars needed before any detector can say anything (`build_context` refuses
#: shorter series). Scanning earlier would only produce `None`.
MIN_BARS = 40


class Resolution(StrEnum):
    """What price did after the figure became recognisable.

    A statement of fact about one instance, deliberately kept apart from
    `edge_state`: that a figure completed says nothing about whether figures
    of its kind predict anything.
    """

    REACHED_TRIGGER = "REACHED_TRIGGER"
    REACHED_INVALIDATION = "REACHED_INVALIDATION"
    UNRESOLVED = "UNRESOLVED"
    #: Still forming at the last bar - nothing has happened yet, and saying
    #: "unresolved" would suggest time had passed without an answer.
    STILL_OPEN = "STILL_OPEN"


@dataclass(slots=True)
class HistoricalPattern:
    """One figure, dated to when it first became recognisable."""

    pattern: StructuralPattern
    #: Bar index at which the shape first satisfied every gate.
    first_seen_index: int
    first_seen_time: datetime
    #: The span the figure occupies on a chart, from its first defining pivot
    #: to the bar that revealed it.
    start_time: datetime
    end_time: datetime
    resolution: Resolution = Resolution.UNRESOLVED
    resolved_at: datetime | None = None
    bars_to_resolution: int | None = None

    @property
    def name(self) -> str:
        return self.pattern.name

    def to_dict(self) -> dict[str, Any]:
        payload = self.pattern.to_dict()
        payload["first_seen_at"] = self.first_seen_time.isoformat()
        payload["span_start"] = self.start_time.isoformat()
        payload["span_end"] = self.end_time.isoformat()
        payload["resolution"] = self.resolution.value
        payload["resolved_at"] = (
            self.resolved_at.isoformat() if self.resolved_at else None
        )
        payload["bars_to_resolution"] = self.bars_to_resolution
        payload["resolution_note"] = (
            "Whether this one figure reached its trigger or its invalidation "
            "first. It describes this instance only and is not an edge."
        )
        return payload


def _identity(pattern: StructuralPattern) -> tuple[Any, ...]:
    """What makes two detections the same figure.

    The defining pivots, not the confidence or the state: those move as bars
    print, while the shape does not. Falling back to the span keeps figures
    without named points (a triangle, a flag) from collapsing into one.
    """
    points = tuple(
        (point.time, round(point.price, 6)) for point in pattern.geometry.points
    )
    if points:
        return (pattern.name, points)
    lines = tuple(
        (line.start.time, line.end.time, line.role)
        for line in pattern.geometry.trend_lines
    )
    if lines:
        return (pattern.name, lines)
    return (pattern.name, pattern.detected_at, pattern.bars_span)


def _detection_points(swings: SwingSeries, n_bars: int) -> list[int]:
    """The bars at which the answer could have changed.

    A figure is built from pivots, so a new figure can only appear when a
    pivot is confirmed. Scanning every bar instead would run the detectors
    twenty times more often to return the same list.

    The final bar is always included: a figure recognisable right now must be
    found even if no pivot has confirmed since.
    """
    points = {
        swing.confirmation_index
        for swing in (swings.highs + swings.lows)
        if MIN_BARS <= swing.confirmation_index < n_bars
    }
    if n_bars > MIN_BARS:
        points.add(n_bars - 1)
    return sorted(points)


def _trigger_level(pattern: StructuralPattern) -> float | None:
    """The price that would complete the figure, as the detector named it."""
    levels = pattern.key_levels or {}
    for key in ("neckline", "breakout", "resistance", "support", "trigger"):
        value = levels.get(key)
        if value is not None:
            return float(value)
    return None


def _resolve(
    pattern: StructuralPattern,
    first_seen_index: int,
    close: pd.Series,
) -> tuple[Resolution, datetime | None, int | None]:
    """Which came first after detection: the trigger or the invalidation.

    Closes only. An intrabar wick through a level is not a break in any of the
    definitions this system uses, and counting it would inflate every figure's
    completion rate.
    """
    trigger = _trigger_level(pattern)
    invalidation = pattern.invalidation_level
    forward = close.iloc[first_seen_index + 1:]
    if forward.empty:
        return Resolution.STILL_OPEN, None, None
    if trigger is None and invalidation is None:
        return Resolution.UNRESOLVED, None, None

    bearish = pattern.direction_if_textbook == "BEARISH"
    for offset, (when, price) in enumerate(forward.items(), start=1):
        value = float(price)
        if trigger is not None:
            broke = value < trigger if bearish else value > trigger
            if broke:
                return Resolution.REACHED_TRIGGER, when, offset
        if invalidation is not None:
            broke = value > invalidation if bearish else value < invalidation
            if broke:
                return Resolution.REACHED_INVALIDATION, when, offset
    return Resolution.UNRESOLVED, None, None


def scan_history(
    df: pd.DataFrame,
    timeframe: Timeframe,
    lookback: int = 5,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    since_index: int = 0,
) -> list[HistoricalPattern]:
    """Replay every detector at every pivot. Returns figures oldest first.

    ATR and swings are computed once over the whole series and then sliced,
    rather than recomputed per detection point: recomputing would be O(n^2)
    and would produce identical numbers.
    """
    if df is None or df.empty or len(df) < MIN_BARS:
        return []

    from ..engines.technical import indicators as ind

    high, low, close, volume = df["high"], df["low"], df["close"], df["volume"]
    atr = ind.atr(high, low, close, 14)
    swings = find_causal_swings(high, low, close, atr, lookback=lookback)

    found: dict[tuple[Any, ...], HistoricalPattern] = {}
    for stop in _detection_points(swings, len(df)):
        # `since_index` sert au balayage incrémental: les pivets antérieurs
        # ont déjà été joués, et les rejouer donnerait exactement la même
        # réponse pour un coût proportionnel à tout l'historique.
        if stop < since_index:
            continue
        when = df.index[stop]
        context = PatternContext(
            high=high.iloc[: stop + 1],
            low=low.iloc[: stop + 1],
            close=close.iloc[: stop + 1],
            volume=volume.iloc[: stop + 1],
            atr=atr.iloc[: stop + 1],
            swings=swings.as_of(when),
            timeframe=timeframe,
        )
        for pattern in detect_all(context, min_confidence=min_confidence):
            key = _identity(pattern)
            if key in found:
                # Already seen, at an earlier bar. The earlier sighting is the
                # honest one: it is when a reader could first have acted.
                continue
            found[key] = HistoricalPattern(
                pattern=pattern,
                first_seen_index=stop,
                first_seen_time=when,
                start_time=_span_start(pattern, when),
                end_time=when,
            )

    ordered = _drop_overlapping(sorted(found.values(), key=lambda item: item.first_seen_time))
    for item in ordered:
        resolution, resolved_at, bars = _resolve(
            item.pattern, item.first_seen_index, close
        )
        item.resolution = resolution
        item.resolved_at = resolved_at
        item.bars_to_resolution = bars
        # A resolved figure stops here. Leaving its neckline extended would
        # draw a line across years of unrelated price for a shape that was
        # settled long ago.
        if resolution in (Resolution.REACHED_TRIGGER, Resolution.REACHED_INVALIDATION):
            item.pattern.state = (
                PatternState.CONFIRMED
                if resolution is Resolution.REACHED_TRIGGER
                else PatternState.FAILED
            )
            _stop_extending(item.pattern)

    log.info(
        "history_scanned",
        timeframe=timeframe.value, bars=len(df), figures=len(ordered),
    )
    return ordered


#: Above this share of overlap, two same-named figures are one move read
#: twice rather than two figures. Flags make this necessary: their pole is a
#: rolling window, so consecutive pivots each yield a slightly shifted copy of
#: the same rally.
OVERLAP_IS_SAME = 0.8


def _drop_overlapping(figures: list[HistoricalPattern]) -> list[HistoricalPattern]:
    """Keep the first sighting of each move, discard its later re-readings.

    Only figures of the same name are compared: a double top and a flag over
    the same bars are two different statements about that stretch of price,
    and both are worth keeping.
    """
    kept: list[HistoricalPattern] = []
    for figure in figures:
        span = (figure.end_time - figure.start_time).total_seconds()
        duplicate = False
        for earlier in kept:
            if earlier.name != figure.name:
                continue
            start = max(earlier.start_time, figure.start_time)
            end = min(earlier.end_time, figure.end_time)
            overlap = (end - start).total_seconds()
            if overlap <= 0:
                continue
            if span <= 0 or overlap / span >= OVERLAP_IS_SAME:
                duplicate = True
                break
        if not duplicate:
            kept.append(figure)
    return kept


def _span_start(pattern: StructuralPattern, fallback: datetime) -> datetime:
    """The earliest moment the figure occupies on a chart."""
    times = [point.time for point in pattern.geometry.points]
    times += [line.start.time for line in pattern.geometry.trend_lines]
    times += [zone.start_time for zone in pattern.geometry.zones]
    return min(times) if times else fallback


def _stop_extending(pattern: StructuralPattern) -> None:
    """Turn off `extend` on a settled figure's lines."""
    pattern.geometry.trend_lines = [
        type(line)(start=line.start, end=line.end, role=line.role, extend=False)
        for line in pattern.geometry.trend_lines
    ]
    neckline = pattern.geometry.neckline
    if neckline is not None:
        pattern.geometry.neckline = type(neckline)(
            start=neckline.start, end=neckline.end,
            role=neckline.role, extend=False,
        )


def figures_in_window(
    figures: list[HistoricalPattern], start: datetime, end: datetime
) -> list[HistoricalPattern]:
    """Those a chart showing `start`..`end` would actually display.

    Overlap, not containment: a figure half inside the window is still visible
    and still worth drawing. One entirely outside is not - drawing it would
    place its points beyond the edge of the frame.
    """
    return [
        figure for figure in figures
        if figure.end_time >= start and figure.start_time <= end
    ]


# --- caching ---------------------------------------------------------------
#
# A full replay costs a few seconds per timeframe. That is fine once and
# unacceptable per request, and the result is deterministic: a figure found at
# bar i was computed from bars up to i and cannot change when later bars
# print. So a scan is reusable until either the series grows or a detector
# changes, and nothing is approximated by reusing it.

import json  # noqa: E402
import pathlib  # noqa: E402

#: Bump when any detector's behaviour changes, so old scans are discarded
#: rather than silently mixed with new ones.
SCAN_VERSION = "lot5-history-1"

SCAN_DIR = pathlib.Path("data/cache/figures")

_memo: dict[tuple[str, str], tuple[str, list[dict[str, Any]]]] = {}


def _scan_path(asset: str, timeframe: str) -> pathlib.Path:
    return SCAN_DIR / f"{asset}_{timeframe}_{SCAN_VERSION}.json"


def _stamp(df: pd.DataFrame) -> str:
    """What identifies this exact series.

    The last bar and the row count are not enough: two different series can
    share both, and reusing one scan for the other would show figures that
    belong to other prices. A few sampled closes make a collision require the
    series to actually match.
    """
    import hashlib

    # Volontairement sans la dernière clôture: elle bouge à chaque tick de la
    # barre en cours, et l'inclure faisait rater le cache à chaque requête —
    # trente secondes de rebalayage pour un prix qui ne change aucun pivot.
    closes = df["close"]
    sample = [
        float(closes.iloc[position])
        for position in (0, len(closes) // 3, 2 * len(closes) // 3)
    ]
    digest = hashlib.sha256(
        "|".join(
            [df.index[0].isoformat(), str(len(df))]
            + [f"{value:.8f}" for value in sample]
        ).encode()
    ).hexdigest()[:16]
    return f"{df.index[-1].isoformat()}|{len(df)}|{digest}"


def scan_cached(
    asset: str,
    timeframe: Timeframe,
    df: pd.DataFrame,
    lookback: int = 5,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
) -> list[dict[str, Any]]:
    """The serialised scan, replayed only when the series has grown.

    Keyed on the last bar: that is what a new scan would change. Returning the
    dictionaries rather than the objects keeps the cache and the API payload
    identical, so a cached response cannot differ in shape from a fresh one.
    """
    if df is None or df.empty:
        return []
    key = (asset, timeframe.value)
    stamp = _stamp(df)

    cached = _memo.get(key)
    if cached is not None and cached[0] == stamp:
        return cached[1]

    path = _scan_path(asset, timeframe.value)
    if path.exists():
        try:
            payload = json.loads(path.read_text())
            if payload.get("stamp") == stamp:
                figures = payload["figures"]
                _memo[key] = (stamp, figures)
                return figures
        except (json.JSONDecodeError, OSError, KeyError) as exc:
            log.debug("scan_cache_unreadable", error=str(exc)[:120])

    figures = _scan_incrementally(
        asset, timeframe, df, lookback, min_confidence
    )
    _memo[key] = (stamp, figures)
    try:
        SCAN_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "stamp": stamp,
            "version": SCAN_VERSION,
            # De quoi reprendre là où on s'est arrêté plutôt que tout rejouer.
            "first_bar": df.index[0].isoformat(),
            "bars": len(df),
            "figures": figures,
        }))
    except OSError as exc:
        # A cache that cannot be written is a slow scan, not a wrong one.
        log.debug("scan_cache_unwritable", error=str(exc)[:120])
    return figures


def _scan_incrementally(
    asset: str,
    timeframe: Timeframe,
    df: pd.DataFrame,
    lookback: int,
    min_confidence: float,
) -> list[dict[str, Any]]:
    """Replay only the pivots the stored scan has not already seen.

    A new bar every fifteen minutes cannot cost a full replay of seventy
    thousand: it would make the first request after each bar take half a
    minute. The stored scan says how far it got; only what came after is
    replayed, and the results are merged.

    The merge is safe because of the property tested in
    `test_a_scan_of_a_prefix_is_a_prefix_of_the_scan`: bars that print later
    cannot change what was found earlier. The one exception is the final bar,
    which is always a detection point - so the resume overlaps backwards far
    enough to redo it.
    """
    previous = _stored_scan(asset, timeframe)
    since = 0
    kept: list[dict[str, Any]] = []
    if previous is not None:
        first_seen, scanned_to, figures = previous
        # Même série ? Le premier horodatage doit correspondre, sinon
        # l'historique a été réécrit et il faut tout reprendre.
        if (
            first_seen == df.index[0].isoformat()
            and 0 < scanned_to <= len(df)
        ):
            # On reprend un peu avant: la dernière barre du balayage
            # précédent était un point de détection particulier à l'endroit
            # où la série s'arrêtait.
            since = max(0, scanned_to - 1)
            cutoff = df.index[since].isoformat()
            kept = [
                figure for figure in figures
                if figure.get("first_seen_at", "") < cutoff
            ]

    fresh = [item.to_dict() for item in scan_history(
        df, timeframe, lookback=lookback,
        min_confidence=min_confidence, since_index=since,
    )]
    if not kept:
        return fresh

    merged = kept + [
        figure for figure in fresh
        if figure.get("first_seen_at", "") >= df.index[since].isoformat()
    ]
    merged.sort(key=lambda figure: figure.get("first_seen_at", ""))
    log.info(
        "history_scanned_incrementally",
        timeframe=timeframe.value, reused=len(kept), computed=len(fresh),
    )
    return merged


def _stored_scan(
    asset: str, timeframe: Timeframe
) -> tuple[str, int, list[dict[str, Any]]] | None:
    """The scan on disk, whatever series it was computed for."""
    path = _scan_path(asset, timeframe.value)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text())
        return (
            payload["first_bar"],
            int(payload["bars"]),
            payload["figures"],
        )
    except (json.JSONDecodeError, OSError, KeyError, TypeError, ValueError):
        return None


def within_window(
    figures: list[dict[str, Any]], start: datetime, end: datetime
) -> list[dict[str, Any]]:
    """The serialised figures a chart showing `start`..`end` would display."""
    kept = []
    for figure in figures:
        try:
            span_start = datetime.fromisoformat(figure["span_start"])
            span_end = datetime.fromisoformat(figure["span_end"])
        except (KeyError, ValueError):
            continue
        if span_end >= start and span_start <= end:
            kept.append(figure)
    return kept
